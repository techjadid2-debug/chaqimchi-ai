import base64
import hashlib
import time

import pytest
from fastapi.testclient import TestClient

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}
PAYME_KEY = "payme-test-key"
CLICK_SERVICE_ID = "111"
CLICK_SECRET = "click-test-secret"

PAYME_AUTH = {"Authorization": "Basic " + base64.b64encode(f"Paycom:{PAYME_KEY}".encode()).decode()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_PAYME_MERCHANT_ID", "merchant-1")
    monkeypatch.setenv("CHAQIMCHI_PAYME_KEY", PAYME_KEY)
    monkeypatch.setenv("CHAQIMCHI_CLICK_SERVICE_ID", CLICK_SERVICE_ID)
    monkeypatch.setenv("CHAQIMCHI_CLICK_MERCHANT_ID", "222")
    monkeypatch.setenv("CHAQIMCHI_CLICK_SECRET", CLICK_SECRET)
    monkeypatch.delenv("CHAQIMCHI_PUBLIC_URL", raising=False)
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._payments", None)
    from cloud.main import app

    return TestClient(app)


def _invoice(client, *, plan: str = "starter", months: int = 1) -> dict:
    site = client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "To'lov testi", "plan": plan, "subscription_months": 1},
    ).json()
    inv = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/invoices",
        headers=ADMIN,
        json={"months": months},
    ).json()
    inv["site_id"] = site["site_id"]
    return inv


def _subscription_until(client, site_id: str) -> str:
    return client.get(f"/api/v1/admin/sites/{site_id}", headers=ADMIN).json()["subscription_until"]


def _rpc(client, method: str, params: dict, headers=PAYME_AUTH) -> dict:
    return client.post(
        "/api/v1/payments/payme",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 7, "method": method, "params": params},
    ).json()


# ── Admin qismi ──────────────────────────────────────────────────────────


def test_invoice_endpoints_require_admin_key(client) -> None:
    inv = _invoice(client)
    assert client.get("/api/v1/admin/invoices").status_code == 401
    assert client.post(f"/api/v1/admin/sites/{inv['site_id']}/invoices", json={}).status_code == 401
    assert client.post(f"/api/v1/admin/invoices/{inv['id']}/paid", json={}).status_code == 401


def test_invoice_has_provider_links_and_public_page(client) -> None:
    inv = _invoice(client, plan="business", months=12)
    assert inv["amount_uzs"] == 1_490_000 * 10
    assert inv["payme_url"].startswith("https://checkout.paycom.uz/")
    assert "service_id=111" in inv["click_url"]

    public = client.get(f"/api/v1/invoices/{inv['id']}").json()
    assert public["state"] == "pending"
    assert public["site_name"] == "To'lov testi"
    # Ichki maydonlar ochiq javobda yo'q.
    assert "note" not in public

    assert client.get(f"/pay/{inv['id']}").status_code == 200
    assert client.get("/api/v1/invoices/yo-q").status_code == 404


def test_manual_payment_extends_subscription(client) -> None:
    inv = _invoice(client, months=2)
    before = _subscription_until(client, inv["site_id"])

    r = client.post(
        f"/api/v1/admin/invoices/{inv['id']}/paid", headers=ADMIN, json={"provider": "naqd"}
    )
    assert r.status_code == 200
    assert r.json()["state"] == "paid"
    assert _subscription_until(client, inv["site_id"]) > before


def test_providers_endpoint_reports_configuration(client) -> None:
    r = client.get("/api/v1/admin/payments/providers", headers=ADMIN)
    assert r.json() == {"payme": True, "click": True, "public_url": ""}


# ── Payme ────────────────────────────────────────────────────────────────


def test_payme_rejects_bad_credentials(client) -> None:
    inv = _invoice(client)
    params = {"amount": inv["amount_uzs"] * 100, "account": {"invoice_id": inv["id"]}}

    assert _rpc(client, "CheckPerformTransaction", params, headers={})["error"]["code"] == -32504
    bad = {"Authorization": "Basic " + base64.b64encode(b"Paycom:wrong").decode()}
    assert _rpc(client, "CheckPerformTransaction", params, headers=bad)["error"]["code"] == -32504


def test_payme_check_perform_validates_invoice_and_amount(client) -> None:
    inv = _invoice(client)
    amount = inv["amount_uzs"] * 100

    ok = _rpc(
        client,
        "CheckPerformTransaction",
        {"amount": amount, "account": {"invoice_id": inv["id"]}},
    )
    assert ok["result"] == {"allow": True}

    wrong_amount = _rpc(
        client, "CheckPerformTransaction", {"amount": 1, "account": {"invoice_id": inv["id"]}}
    )
    assert wrong_amount["error"]["code"] == -31001

    unknown = _rpc(
        client, "CheckPerformTransaction", {"amount": amount, "account": {"invoice_id": "yo-q"}}
    )
    assert unknown["error"]["code"] == -31050
    assert unknown["error"]["data"] == "invoice_id"

    assert _rpc(client, "NoSuchMethod", {})["error"]["code"] == -32601


def test_payme_full_flow_extends_then_refunds(client) -> None:
    inv = _invoice(client, months=3)
    amount = inv["amount_uzs"] * 100
    before = _subscription_until(client, inv["site_id"])
    params = {
        "id": "payme-txn-1",
        "time": int(time.time() * 1000),
        "amount": amount,
        "account": {"invoice_id": inv["id"]},
    }

    created = _rpc(client, "CreateTransaction", params)["result"]
    assert created["state"] == 1
    # Takroriy CreateTransaction — o'sha tranzaksiya qaytadi.
    assert _rpc(client, "CreateTransaction", params)["result"] == created

    # Shu hisob bo'yicha ikkinchi tranzaksiya ochilmaydi.
    second = _rpc(client, "CreateTransaction", {**params, "id": "payme-txn-2"})
    assert second["error"]["code"] == -31051

    performed = _rpc(client, "PerformTransaction", {"id": "payme-txn-1"})["result"]
    assert performed["state"] == 2
    assert performed["transaction"] == created["transaction"]
    after_perform = _subscription_until(client, inv["site_id"])
    assert after_perform > before
    assert client.get(f"/api/v1/invoices/{inv['id']}").json()["state"] == "paid"

    # Takroriy PerformTransaction obunani ikkinchi marta uzaytirmaydi.
    assert _rpc(client, "PerformTransaction", {"id": "payme-txn-1"})["result"] == performed
    assert _subscription_until(client, inv["site_id"]) == after_perform

    checked = _rpc(client, "CheckTransaction", {"id": "payme-txn-1"})["result"]
    assert checked["state"] == 2
    assert checked["perform_time"] == performed["perform_time"]

    statement = _rpc(client, "GetStatement", {"from": 0, "to": int(time.time() * 1000) + 1000})
    assert [t["id"] for t in statement["result"]["transactions"]] == ["payme-txn-1"]

    cancelled = _rpc(client, "CancelTransaction", {"id": "payme-txn-1", "reason": 5})["result"]
    assert cancelled["state"] == -2
    # Xizmat qaytarildi — obuna avvalgi holatiga tushdi.
    assert _subscription_until(client, inv["site_id"]) == before
    assert client.get(f"/api/v1/invoices/{inv['id']}").json()["state"] == "cancelled"


def test_payme_cancel_before_perform_frees_invoice(client) -> None:
    inv = _invoice(client)
    params = {
        "id": "txn-cancel",
        "time": int(time.time() * 1000),
        "amount": inv["amount_uzs"] * 100,
        "account": {"invoice_id": inv["id"]},
    }
    _rpc(client, "CreateTransaction", params)

    cancelled = _rpc(client, "CancelTransaction", {"id": "txn-cancel", "reason": 3})["result"]
    assert cancelled["state"] == -1
    # Takroriy bekor qilish — o'sha javob.
    assert _rpc(client, "CancelTransaction", {"id": "txn-cancel"})["result"]["state"] == -1

    assert _rpc(client, "PerformTransaction", {"id": "txn-cancel"})["error"]["code"] == -31008
    assert _rpc(client, "CheckTransaction", {"id": "yo-q"})["error"]["code"] == -31003


def test_payme_rejects_stale_transaction_time(client) -> None:
    inv = _invoice(client)
    old = int(time.time() * 1000) - 13 * 60 * 60 * 1000
    r = _rpc(
        client,
        "CreateTransaction",
        {
            "id": "txn-old",
            "time": old,
            "amount": inv["amount_uzs"] * 100,
            "account": {"invoice_id": inv["id"]},
        },
    )
    assert r["error"]["code"] == -31008


# ── Click ────────────────────────────────────────────────────────────────


def _click_sign(params: dict, *, with_prepare_id: bool) -> str:
    keys = ["click_trans_id", "service_id", None, "merchant_trans_id"]
    if with_prepare_id:
        keys.append("merchant_prepare_id")
    keys += ["amount", "action", "sign_time"]
    raw = "".join(CLICK_SECRET if k is None else str(params.get(k, "")) for k in keys)
    return hashlib.md5(raw.encode()).hexdigest()


def _click_body(invoice: dict, action: str, **extra) -> dict:
    params = {
        "click_trans_id": "9001",
        "service_id": CLICK_SERVICE_ID,
        "click_paydoc_id": "7001",
        "merchant_trans_id": invoice["id"],
        "amount": f"{invoice['amount_uzs']}.00",
        "action": action,
        "error": "0",
        "error_note": "",
        "sign_time": "2026-08-01 10:00:00",
        **extra,
    }
    params["sign_string"] = _click_sign(params, with_prepare_id=action == "1")
    return params


def _prepare(client, invoice: dict, **extra):
    return client.post("/api/v1/payments/click/prepare", data=_click_body(invoice, "0", **extra))


def _complete(client, invoice: dict, prepare_id, **extra):
    body = _click_body(invoice, "1", merchant_prepare_id=str(prepare_id), **extra)
    return client.post("/api/v1/payments/click/complete", data=body)


def test_click_rejects_bad_signature(client) -> None:
    inv = _invoice(client)
    body = _click_body(inv, "0")
    body["sign_string"] = "0" * 32
    r = client.post("/api/v1/payments/click/prepare", data=body)
    assert r.json()["error"] == -1


def test_click_prepare_complete_extends_subscription(client) -> None:
    inv = _invoice(client, months=2)
    before = _subscription_until(client, inv["site_id"])

    prepared = _prepare(client, inv).json()
    assert prepared["error"] == 0
    prepare_id = prepared["merchant_prepare_id"]
    # Takroriy Prepare — o'sha identifikator.
    assert _prepare(client, inv).json()["merchant_prepare_id"] == prepare_id

    completed = _complete(client, inv, prepare_id).json()
    assert completed["error"] == 0
    assert completed["merchant_confirm_id"] == prepare_id
    after = _subscription_until(client, inv["site_id"])
    assert after > before

    # Ikkinchi Complete — allaqachon to'langan, obuna o'zgarmaydi.
    assert _complete(client, inv, prepare_id).json()["error"] == -4
    assert _subscription_until(client, inv["site_id"]) == after


def test_click_validates_order_amount_and_transaction(client) -> None:
    inv = _invoice(client)

    missing = _prepare(client, {"id": "yo-q", "amount_uzs": inv["amount_uzs"]})
    assert missing.json()["error"] == -5

    bad_amount = _prepare(client, {**inv, "amount_uzs": inv["amount_uzs"] + 1000})
    assert bad_amount.json()["error"] == -2

    prepare_id = _prepare(client, inv).json()["merchant_prepare_id"]
    assert _complete(client, inv, prepare_id + 999).json()["error"] == -6


def test_click_error_flag_cancels_invoice(client) -> None:
    inv = _invoice(client)
    prepare_id = _prepare(client, inv).json()["merchant_prepare_id"]

    r = _complete(client, inv, prepare_id, error="-5001", error_note="Ошибка")
    assert r.json()["error"] == -9
    assert client.get(f"/api/v1/invoices/{inv['id']}").json()["state"] == "cancelled"
