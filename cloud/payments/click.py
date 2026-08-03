"""Click SHOP-API — Prepare va Complete callbacklari.

Click form-urlencoded so'rov yuboradi va `error` maydonli JSON kutadi.
Imzo: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id
          [+ merchant_prepare_id, faqat Complete] + amount + action + sign_time)

Hujjat: https://docs.click.uz/click-api-request
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlencode

from cloud.payments.config import ClickConfig
from cloud.payments.store import CANCELLED, PAID, PENDING, PaymentStore

ACTION_PREPARE = "0"
ACTION_COMPLETE = "1"

# Click xato kodlari
OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TXN_NOT_FOUND = -6
ERR_UPDATE_FAILED = -7
ERR_BAD_REQUEST = -8
ERR_CANCELLED = -9

NOTES: Dict[int, str] = {
    OK: "Success",
    ERR_SIGN: "SIGN CHECK FAILED!",
    ERR_AMOUNT: "Incorrect parameter amount",
    ERR_ACTION: "Action not found",
    ERR_ALREADY_PAID: "Already paid",
    ERR_ORDER_NOT_FOUND: "Order does not exist",
    ERR_TXN_NOT_FOUND: "Transaction does not exist",
    ERR_UPDATE_FAILED: "Failed to update user",
    ERR_BAD_REQUEST: "Error in request from click",
    ERR_CANCELLED: "Transaction cancelled",
}

#: Click summani so'mda, kasr bilan yuboradi — tiyinlik farqni e'tiborsiz qoldiramiz.
AMOUNT_TOLERANCE = 0.5


def _reply(params: Mapping[str, str], error: int, **extra: Any) -> Dict[str, Any]:
    return {
        "click_trans_id": params.get("click_trans_id", ""),
        "merchant_trans_id": params.get("merchant_trans_id", ""),
        "error": error,
        "error_note": NOTES.get(error, "Error"),
        **extra,
    }


def make_sign(params: Mapping[str, str], config: ClickConfig, *, with_prepare_id: bool) -> str:
    """Click imzosini bir xil tartibda quradi — tekshirish ham, test ham shundan foydalanadi."""
    pieces = [
        params.get("click_trans_id", ""),
        params.get("service_id", ""),
        config.secret_key,
        params.get("merchant_trans_id", ""),
    ]
    if with_prepare_id:
        pieces.append(params.get("merchant_prepare_id", ""))
    pieces += [
        params.get("amount", ""),
        params.get("action", ""),
        params.get("sign_time", ""),
    ]
    return hashlib.md5("".join(pieces).encode("utf-8")).hexdigest()


def _sign_ok(params: Mapping[str, str], config: ClickConfig, *, with_prepare_id: bool) -> bool:
    if not config.configured:
        return False
    if params.get("service_id", "") != config.service_id:
        return False
    expected = make_sign(params, config, with_prepare_id=with_prepare_id)
    return secrets.compare_digest(expected, str(params.get("sign_string", "")).lower())


def _amount_ok(params: Mapping[str, str], invoice: Mapping[str, Any]) -> bool:
    try:
        sent = float(params.get("amount", ""))
    except ValueError:
        return False
    return abs(sent - float(invoice["amount_uzs"])) <= AMOUNT_TOLERANCE


def _click_error(params: Mapping[str, str]) -> Optional[int]:
    """Click o'z tomonidan xato yuborgan bo'lsa (`error < 0`) — to'lov bo'lmadi."""
    try:
        code = int(params.get("error", "0") or 0)
    except ValueError:
        return None
    return code if code < 0 else None


def handle_prepare(
    params: Mapping[str, str], *, store: PaymentStore, config: ClickConfig
) -> Dict[str, Any]:
    if params.get("action", "") != ACTION_PREPARE:
        return _reply(params, ERR_ACTION)
    if not _sign_ok(params, config, with_prepare_id=False):
        return _reply(params, ERR_SIGN)

    invoice = store.get_invoice(str(params.get("merchant_trans_id", "")).strip())
    if not invoice:
        return _reply(params, ERR_ORDER_NOT_FOUND)
    if invoice["state"] == PAID:
        return _reply(params, ERR_ALREADY_PAID)
    if invoice["state"] == CANCELLED:
        return _reply(params, ERR_CANCELLED)
    if not _amount_ok(params, invoice):
        return _reply(params, ERR_AMOUNT)
    if _click_error(params) is not None:
        return _reply(params, ERR_CANCELLED)

    click_trans_id = str(params.get("click_trans_id", "")).strip()
    if not click_trans_id:
        return _reply(params, ERR_BAD_REQUEST)

    txn = store.click_get(click_trans_id) or store.click_prepare(
        click_trans_id, invoice["id"], int(invoice["amount_uzs"])
    )
    return _reply(params, OK, merchant_prepare_id=txn["merchant_prepare_id"])


def handle_complete(
    params: Mapping[str, str], *, store: PaymentStore, config: ClickConfig
) -> Dict[str, Any]:
    if params.get("action", "") != ACTION_COMPLETE:
        return _reply(params, ERR_ACTION)
    if not _sign_ok(params, config, with_prepare_id=True):
        return _reply(params, ERR_SIGN)

    txn = store.click_get(str(params.get("click_trans_id", "")).strip())
    if not txn or str(txn["merchant_prepare_id"]) != str(params.get("merchant_prepare_id", "")):
        return _reply(params, ERR_TXN_NOT_FOUND)

    invoice = store.get_invoice(txn["invoice_id"])
    if not invoice:
        return _reply(params, ERR_ORDER_NOT_FOUND)

    if _click_error(params) is not None:
        store.click_set_state(txn["click_trans_id"], "cancelled")
        if invoice["state"] == PENDING:
            store.cancel_invoice(invoice["id"])
        return _reply(params, ERR_CANCELLED)

    if txn["state"] == "cancelled" or invoice["state"] == CANCELLED:
        return _reply(params, ERR_CANCELLED)
    if txn["state"] == PAID or invoice["state"] == PAID:
        return _reply(params, ERR_ALREADY_PAID)
    if not _amount_ok(params, invoice):
        return _reply(params, ERR_AMOUNT)

    # Obuna aynan shu yerda uzayadi.
    store.mark_paid(invoice["id"], "click", provider_txn_id=txn["click_trans_id"])
    store.click_set_state(txn["click_trans_id"], PAID)
    return _reply(params, OK, merchant_confirm_id=txn["merchant_prepare_id"])


def checkout_link(config: ClickConfig, invoice: Mapping[str, Any], return_url: str = "") -> str:
    """Mijoz bosadigan Click havolasi."""
    if not config.configured:
        return ""
    query = {
        "service_id": config.service_id,
        "merchant_id": config.merchant_id,
        "amount": int(invoice["amount_uzs"]),
        "transaction_param": invoice["id"],
    }
    if return_url:
        query["return_url"] = return_url
    return f"{config.checkout_url}?{urlencode(query)}"
