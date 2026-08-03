"""Payme Merchant API (JSON-RPC 2.0).

Payme serveri bitta endpointga POST qiladi va **doim HTTP 200** kutadi —
xato JSON ichida `error` sifatida qaytadi. Shu sabab bu modul hech qachon
HTTPException ko'tarmaydi, faqat javob lug'atini qaytaradi.

Hujjat: https://developer.help.paycom.uz/metody-merchant-api
"""

from __future__ import annotations

import base64
import binascii
import secrets
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

from cloud.payments.config import TIYIN, PaymeConfig
from cloud.payments.store import PENDING, PaymentStore

#: Tranzaksiya holatlari (Payme spetsifikatsiyasi).
STATE_CREATED = 1
STATE_PERFORMED = 2
STATE_CANCELLED = -1
STATE_CANCELLED_AFTER_PERFORM = -2

#: Yaratilgan tranzaksiya 12 soatdan keyin kuchini yo'qotadi.
TIMEOUT_MS = 12 * 60 * 60 * 1000

#: Avtomatik bekor qilish sababi — "vaqti tugadi".
REASON_TIMEOUT = 4

# JSON-RPC / Payme xato kodlari
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INSUFFICIENT_PRIVILEGE = -32504
ERR_INVALID_AMOUNT = -31001
ERR_TXN_NOT_FOUND = -31003
ERR_CANNOT_PERFORM = -31008
# -31007 (bekor qilib bo'lmaydi) ishlatilmaydi: obuna qaytariladigan xizmat,
# shuning uchun bajarilgan tranzaksiya ham bekor qilinadi (oylar qaytariladi).
#: -31050..-31099 — `account` (bizda hisob-faktura) bilan bog'liq xatolar.
ERR_INVOICE_NOT_FOUND = -31050
ERR_INVOICE_UNAVAILABLE = -31051


def _msg(uz: str, ru: str, en: str) -> Dict[str, str]:
    return {"uz": uz, "ru": ru, "en": en}


class PaymeError(Exception):
    def __init__(self, code: int, message: Dict[str, str], data: Optional[str] = None) -> None:
        super().__init__(message.get("en", ""))
        self.code = code
        self.message = message
        self.data = data

    def as_dict(self) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


def _now_ms() -> int:
    return int(time.time() * 1000)


def _check_auth(auth_header: Optional[str], config: PaymeConfig) -> None:
    """`Authorization: Basic base64("Paycom:<merchant key>")`."""
    denied = PaymeError(
        ERR_INSUFFICIENT_PRIVILEGE,
        _msg("Ruxsat yo'q", "Недостаточно привилегий", "Insufficient privilege"),
    )
    if not config.configured or not auth_header:
        raise denied
    scheme, _, encoded = auth_header.partition(" ")
    if scheme.lower() != "basic":
        raise denied
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise denied from exc
    login, _, password = decoded.partition(":")
    if login != "Paycom" or not secrets.compare_digest(password, config.key):
        raise denied


def _load_invoice(
    params: Dict[str, Any], store: PaymentStore, config: PaymeConfig
) -> Dict[str, Any]:
    account = params.get("account")
    if not isinstance(account, dict):
        raise PaymeError(
            ERR_INVOICE_NOT_FOUND,
            _msg("Hisob raqami yo'q", "Счёт не указан", "Account is missing"),
            config.account_field,
        )
    invoice_id = str(account.get(config.account_field, "")).strip()
    invoice = store.get_invoice(invoice_id) if invoice_id else None
    if not invoice:
        raise PaymeError(
            ERR_INVOICE_NOT_FOUND,
            _msg("Hisob-faktura topilmadi", "Счёт не найден", "Invoice not found"),
            config.account_field,
        )
    return invoice


def _require_payable(invoice: Dict[str, Any], config: PaymeConfig) -> None:
    if invoice["state"] != PENDING:
        raise PaymeError(
            ERR_INVOICE_UNAVAILABLE,
            _msg(
                "Hisob-faktura to'langan yoki bekor qilingan",
                "Счёт уже оплачен или отменён",
                "Invoice is already paid or cancelled",
            ),
            config.account_field,
        )


def _check_amount(params: Dict[str, Any], invoice: Dict[str, Any]) -> int:
    expected = int(invoice["amount_uzs"]) * TIYIN
    amount = params.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or int(amount) != expected:
        raise PaymeError(
            ERR_INVALID_AMOUNT, _msg("Summa noto'g'ri", "Неверная сумма", "Incorrect amount")
        )
    return expected


def _account_of(invoice: Dict[str, Any], config: PaymeConfig) -> Dict[str, str]:
    return {config.account_field: invoice["id"]}


def _expire_if_stale(txn: Dict[str, Any], store: PaymentStore) -> Dict[str, Any]:
    """12 soatdan oshgan `created` tranzaksiyani avtomatik bekor qiladi."""
    if txn["state"] != STATE_CREATED or _now_ms() - int(txn["create_time"]) <= TIMEOUT_MS:
        return txn
    return store.payme_set_state(
        txn["id"], STATE_CANCELLED, cancel_time=_now_ms(), reason=REASON_TIMEOUT
    )


# ── Metodlar ─────────────────────────────────────────────────────────────


def _check_perform(
    params: Dict[str, Any], store: PaymentStore, config: PaymeConfig
) -> Dict[str, Any]:
    invoice = _load_invoice(params, store, config)
    _check_amount(params, invoice)
    _require_payable(invoice, config)
    return {"allow": True}


def _create(params: Dict[str, Any], store: PaymentStore, config: PaymeConfig) -> Dict[str, Any]:
    txn_id = str(params.get("id") or "").strip()
    if not txn_id:
        raise PaymeError(
            ERR_INVALID_REQUEST, _msg("So'rov noto'g'ri", "Неверный запрос", "Invalid request")
        )

    existing = store.payme_get(txn_id)
    if existing:
        existing = _expire_if_stale(existing, store)
        if existing["state"] != STATE_CREATED:
            raise PaymeError(
                ERR_CANNOT_PERFORM,
                _msg(
                    "Tranzaksiyani bajarib bo'lmaydi",
                    "Невозможно выполнить операцию",
                    "Unable to perform transaction",
                ),
            )
        return {
            "create_time": existing["create_time"],
            "transaction": existing["merchant_txn_id"],
            "state": STATE_CREATED,
        }

    invoice = _load_invoice(params, store, config)
    amount = _check_amount(params, invoice)
    _require_payable(invoice, config)

    if store.payme_active_for_invoice(invoice["id"]):
        raise PaymeError(
            ERR_INVOICE_UNAVAILABLE,
            _msg(
                "Bu hisob bo'yicha tranzaksiya allaqachon bor",
                "По этому счёту уже есть операция",
                "A transaction already exists for this invoice",
            ),
            config.account_field,
        )

    payme_time = int(params.get("time") or _now_ms())
    create_time = _now_ms()
    if create_time - payme_time > TIMEOUT_MS:
        raise PaymeError(
            ERR_CANNOT_PERFORM,
            _msg("Tranzaksiya vaqti o'tgan", "Время операции истекло", "Transaction has expired"),
        )

    txn = store.payme_create(txn_id, invoice["id"], amount, payme_time, create_time)
    return {
        "create_time": txn["create_time"],
        "transaction": txn["merchant_txn_id"],
        "state": STATE_CREATED,
    }


def _perform(params: Dict[str, Any], store: PaymentStore, config: PaymeConfig) -> Dict[str, Any]:
    txn = _find_txn(params, store)

    if txn["state"] == STATE_PERFORMED:
        return {
            "transaction": txn["merchant_txn_id"],
            "perform_time": txn["perform_time"],
            "state": STATE_PERFORMED,
        }

    txn = _expire_if_stale(txn, store)
    if txn["state"] != STATE_CREATED:
        raise PaymeError(
            ERR_CANNOT_PERFORM,
            _msg(
                "Tranzaksiyani bajarib bo'lmaydi",
                "Невозможно выполнить операцию",
                "Unable to perform transaction",
            ),
        )

    perform_time = _now_ms()
    txn = store.payme_set_state(txn["id"], STATE_PERFORMED, perform_time=perform_time)
    # Obuna aynan shu yerda uzayadi.
    store.mark_paid(txn["invoice_id"], "payme", provider_txn_id=txn["id"])
    return {
        "transaction": txn["merchant_txn_id"],
        "perform_time": perform_time,
        "state": STATE_PERFORMED,
    }


def _cancel(params: Dict[str, Any], store: PaymentStore, config: PaymeConfig) -> Dict[str, Any]:
    txn = _find_txn(params, store)
    reason = params.get("reason")
    reason_int = int(reason) if isinstance(reason, (int, float)) else None

    if txn["state"] in (STATE_CANCELLED, STATE_CANCELLED_AFTER_PERFORM):
        return {
            "transaction": txn["merchant_txn_id"],
            "cancel_time": txn["cancel_time"],
            "state": txn["state"],
        }

    cancel_time = _now_ms()
    if txn["state"] == STATE_PERFORMED:
        # Obuna xizmati qaytariladi: to'langan oylar obunadan ayiriladi.
        new_state = STATE_CANCELLED_AFTER_PERFORM
        store.mark_refunded(txn["invoice_id"])
    else:
        new_state = STATE_CANCELLED
        store.cancel_invoice(txn["invoice_id"])

    txn = store.payme_set_state(txn["id"], new_state, cancel_time=cancel_time, reason=reason_int)
    return {
        "transaction": txn["merchant_txn_id"],
        "cancel_time": cancel_time,
        "state": new_state,
    }


def _check(params: Dict[str, Any], store: PaymentStore, config: PaymeConfig) -> Dict[str, Any]:
    txn = _find_txn(params, store)
    return {
        "create_time": txn["create_time"],
        "perform_time": txn["perform_time"],
        "cancel_time": txn["cancel_time"],
        "transaction": txn["merchant_txn_id"],
        "state": txn["state"],
        "reason": txn["reason"],
    }


def _statement(params: Dict[str, Any], store: PaymentStore, config: PaymeConfig) -> Dict[str, Any]:
    from_ms = int(params.get("from") or 0)
    to_ms = int(params.get("to") or _now_ms())
    out = []
    for txn in store.payme_statement(from_ms, to_ms):
        invoice = store.get_invoice(txn["invoice_id"])
        out.append(
            {
                "id": txn["id"],
                "time": txn["payme_time"],
                "amount": txn["amount_tiyin"],
                "account": _account_of(invoice, config) if invoice else {},
                "create_time": txn["create_time"],
                "perform_time": txn["perform_time"],
                "cancel_time": txn["cancel_time"],
                "transaction": txn["merchant_txn_id"],
                "state": txn["state"],
                "reason": txn["reason"],
            }
        )
    return {"transactions": out}


def _find_txn(params: Dict[str, Any], store: PaymentStore) -> Dict[str, Any]:
    txn = store.payme_get(str(params.get("id") or "").strip())
    if not txn:
        raise PaymeError(
            ERR_TXN_NOT_FOUND,
            _msg("Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found"),
        )
    return txn


Method = Callable[[Dict[str, Any], PaymentStore, PaymeConfig], Dict[str, Any]]

METHODS: Dict[str, Method] = {
    "CheckPerformTransaction": _check_perform,
    "CreateTransaction": _create,
    "PerformTransaction": _perform,
    "CancelTransaction": _cancel,
    "CheckTransaction": _check,
    "GetStatement": _statement,
}


def handle(
    payload: Any,
    *,
    auth_header: Optional[str],
    store: PaymentStore,
    config: PaymeConfig,
) -> Dict[str, Any]:
    """Payme so'rovini bajaradi va JSON-RPC javobini qaytaradi (doim HTTP 200 bilan)."""
    rpc_id = payload.get("id") if isinstance(payload, dict) else None
    try:
        _check_auth(auth_header, config)
        if not isinstance(payload, dict):
            raise PaymeError(
                ERR_INVALID_REQUEST, _msg("So'rov noto'g'ri", "Неверный запрос", "Invalid request")
            )
        method = METHODS.get(str(payload.get("method") or ""))
        if method is None:
            raise PaymeError(
                ERR_METHOD_NOT_FOUND, _msg("Metod topilmadi", "Метод не найден", "Method not found")
            )
        params = payload.get("params")
        result = method(params if isinstance(params, dict) else {}, store, config)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
    except PaymeError as err:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err.as_dict()}


def checkout_link(config: PaymeConfig, invoice: Dict[str, Any], return_url: str = "") -> str:
    """Mijoz bosadigan Payme havolasi (base64 parametrlar bilan)."""
    if not config.configured:
        return ""
    parts = [
        f"m={config.merchant_id}",
        f"ac.{config.account_field}={invoice['id']}",
        f"a={int(invoice['amount_uzs']) * TIYIN}",
    ]
    if return_url:
        parts.append(f"c={return_url}")
    encoded = base64.b64encode(";".join(parts).encode("utf-8")).decode("ascii")
    return f"{config.checkout_url.rstrip('/')}/{quote(encoded, safe='')}"
