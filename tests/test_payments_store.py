from datetime import datetime

import pytest

from cloud.payments.store import PaymentStore, billable_months
from cloud.store import CloudStore


@pytest.fixture
def stores(tmp_path):
    cloud = CloudStore(tmp_path / "cloud.db")
    return cloud, PaymentStore(cloud)


def _until(cloud: CloudStore, site_id: str) -> datetime:
    site = cloud.get_site(site_id)
    return datetime.strptime(site["subscription_until"], "%Y-%m-%d %H:%M:%S")


def test_billable_months_gives_two_free_per_year() -> None:
    assert billable_months(1) == 1
    assert billable_months(6) == 6
    assert billable_months(12) == 10
    assert billable_months(15) == 13
    assert billable_months(24) == 20


def test_invoice_amount_follows_plan(stores) -> None:
    cloud, pay = stores
    site = cloud.create_site("Do'kon", "business", subscription_months=1)

    monthly = pay.create_invoice(site["site_id"], 1)
    assert monthly["amount_uzs"] == 1_490_000
    assert monthly["state"] == "pending"

    yearly = pay.create_invoice(site["site_id"], 12)
    assert yearly["amount_uzs"] == 1_490_000 * 10


def test_unknown_site_cannot_be_invoiced(stores) -> None:
    _, pay = stores
    with pytest.raises(ValueError):
        pay.create_invoice("yo'q-sayt", 1)


def test_mark_paid_extends_subscription_once(stores) -> None:
    cloud, pay = stores
    site = cloud.create_site("Ombor", "starter", subscription_months=1)
    before = _until(cloud, site["site_id"])

    invoice = pay.create_invoice(site["site_id"], 3)
    paid = pay.mark_paid(invoice["id"], "naqd")
    assert paid["state"] == "paid"
    assert paid["paid_at"]

    after = _until(cloud, site["site_id"])
    assert (after - before).days == 90

    # Takroriy chaqiruv obunani ikkinchi marta uzaytirmaydi.
    pay.mark_paid(invoice["id"], "naqd")
    assert _until(cloud, site["site_id"]) == after


def test_refund_rolls_subscription_back(stores) -> None:
    cloud, pay = stores
    site = cloud.create_site("Qaytarish", "starter", subscription_months=1)
    before = _until(cloud, site["site_id"])

    invoice = pay.create_invoice(site["site_id"], 2)
    pay.mark_paid(invoice["id"], "payme")
    assert _until(cloud, site["site_id"]) > before

    refunded = pay.mark_refunded(invoice["id"])
    assert refunded["state"] == "cancelled"
    assert _until(cloud, site["site_id"]) == before


def test_cancelled_invoice_cannot_be_paid(stores) -> None:
    cloud, pay = stores
    site = cloud.create_site("Bekor", "starter")
    invoice = pay.create_invoice(site["site_id"], 1)

    assert pay.cancel_invoice(invoice["id"])["state"] == "cancelled"
    with pytest.raises(ValueError):
        pay.mark_paid(invoice["id"], "naqd")


def test_paid_invoice_cannot_be_cancelled(stores) -> None:
    cloud, pay = stores
    site = cloud.create_site("To'langan", "starter")
    invoice = pay.create_invoice(site["site_id"], 1)
    pay.mark_paid(invoice["id"], "click")

    with pytest.raises(ValueError):
        pay.cancel_invoice(invoice["id"])


def test_invoice_stats_and_listing(stores) -> None:
    cloud, pay = stores
    a = cloud.create_site("A", "starter")
    b = cloud.create_site("B", "business")
    pay.create_invoice(a["site_id"], 1)
    paid = pay.create_invoice(b["site_id"], 1)
    pay.mark_paid(paid["id"], "bank")

    stats = pay.invoice_stats()
    assert stats["pending_invoices"] == 1
    assert stats["pending_amount_uzs"] == 790_000
    assert stats["paid_invoices"] == 1
    assert stats["paid_amount_uzs"] == 1_490_000

    assert len(pay.list_invoices()) == 2
    assert [i["site_id"] for i in pay.list_invoices(a["site_id"])] == [a["site_id"]]
