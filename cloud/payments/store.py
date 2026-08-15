"""Hisob-faktura va provayder tranzaksiyalari (SQLite, cloud.db bilan bir faylda).

Bitta qoida butun modul bo'ylab: **obuna faqat hisob-faktura to'langanda uzayadi**.
Payme ham, Click ham, "naqd" ham shu bitta yo'ldan o'tadi — `mark_paid()`.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from chaqimchi_ai.licensing.plans import get_plan
from cloud.store import CloudStore, _iso, _utc_now

#: Hisob-faktura holatlari.
PENDING = "pending"
PAID = "paid"
CANCELLED = "cancelled"


def billable_months(months: int) -> int:
    """To'lanadigan oylar: har to'liq yil uchun 2 oy tekin (yillik = oylik × 10).

    `docs/archive/BIZNES_MODEL.md` dagi narx qoidasi shu yerda — bitta joyda.
    """
    years, rest = divmod(max(1, int(months)), 12)
    return years * 10 + rest


class PaymentStore:
    """`CloudStore` ustida ishlaydi: to'lov tugagach obunani o'sha orqali uzaytiradi."""

    def __init__(self, cloud: CloudStore) -> None:
        self.cloud = cloud
        self.db_path = cloud.db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                plan TEXT NOT NULL,
                months INTEGER NOT NULL,
                amount_uzs INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                provider TEXT,
                provider_txn_id TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE INDEX IF NOT EXISTS idx_invoices_site ON invoices(site_id);

            CREATE TABLE IF NOT EXISTS payme_transactions (
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                merchant_txn_id TEXT NOT NULL,
                amount_tiyin INTEGER NOT NULL,
                state INTEGER NOT NULL,
                payme_time INTEGER NOT NULL,
                create_time INTEGER NOT NULL,
                perform_time INTEGER NOT NULL DEFAULT 0,
                cancel_time INTEGER NOT NULL DEFAULT 0,
                reason INTEGER,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            );
            CREATE INDEX IF NOT EXISTS idx_payme_invoice ON payme_transactions(invoice_id);

            -- merchant_prepare_id butun son bo'lishi kerak (Click talabi) — shu sabab rowid.
            CREATE TABLE IF NOT EXISTS click_transactions (
                merchant_prepare_id INTEGER PRIMARY KEY AUTOINCREMENT,
                click_trans_id TEXT NOT NULL UNIQUE,
                invoice_id TEXT NOT NULL,
                amount_uzs INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            );
            CREATE INDEX IF NOT EXISTS idx_click_invoice ON click_transactions(invoice_id);
            """
        )
        conn.commit()
        conn.close()

    # ── Hisob-faktura ────────────────────────────────────────────────────

    def create_invoice(
        self,
        site_id: str,
        months: int = 1,
        *,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sayt tarifi bo'yicha yangi to'lov hisobi. Summa serverda hisoblanadi."""
        site = self.cloud.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")
        months = max(1, min(60, int(months)))

        limits = get_plan(site["plan"])
        feature_summary = self.cloud.site_feature_summary(site_id)
        if feature_summary["assignments"]:
            # Published price-book qiymatlari assignment ichida snapshot qilingan.
            # Shu sabab katalog keyin o'zgarsa mavjud mijoz invoice'i muzlaydi.
            monthly = int(feature_summary["active_quote"]["monthly_uzs"])
        else:
            # Davomat tarifida summa xodim soniga bog'liq.
            monthly = limits.monthly_price(int(site.get("billable_persons") or 0))
        # Yillik chegirma barcha tarifga bir xil qo'llanadi: rasmiy saytdagi
        # "2 oy bepul" va'dasi va hisob-faktura bitta qoidadan chiqishi shart.
        charged_months = billable_months(months)
        amount = monthly * charged_months
        invoice_id = uuid.uuid4().hex[:12]

        conn = self._connect()
        conn.execute(
            """
            INSERT INTO invoices (id, site_id, plan, months, amount_uzs, state, note, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (invoice_id, site_id, site["plan"], months, amount, note, _iso(_utc_now())),
        )
        conn.commit()
        conn.close()
        return self.get_invoice(invoice_id)  # type: ignore[return-value]

    def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            """
            SELECT i.*, s.name AS site_name
            FROM invoices i LEFT JOIN sites s ON s.id = i.site_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_invoices(
        self, site_id: Optional[str] = None, *, limit: int = 100
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        sql = """
            SELECT i.*, s.name AS site_name
            FROM invoices i LEFT JOIN sites s ON s.id = i.site_id
        """
        params: tuple[Any, ...] = ()
        if site_id:
            sql += " WHERE i.site_id = ?"
            params = (site_id,)
        sql += " ORDER BY i.created_at DESC, i.rowid DESC LIMIT ?"
        rows = conn.execute(sql, (*params, max(1, int(limit)))).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def invoice_stats(self) -> Dict[str, Any]:
        """Panel uchun: kutilayotgan to'lovlar va shu paytgacha yig'ilgan summa."""
        conn = self._connect()
        pending = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_uzs), 0) AS total"
            " FROM invoices WHERE state = 'pending'"
        ).fetchone()
        paid = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_uzs), 0) AS total"
            " FROM invoices WHERE state = 'paid'"
        ).fetchone()
        conn.close()
        return {
            "pending_invoices": pending["n"],
            "pending_amount_uzs": int(pending["total"]),
            "paid_invoices": paid["n"],
            "paid_amount_uzs": int(paid["total"]),
        }

    def mark_paid(
        self,
        invoice_id: str,
        provider: str,
        *,
        provider_txn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """To'landi deb belgilaydi **va** obunani uzaytiradi. Takroriy chaqiruv xavfsiz."""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Hisob-faktura topilmadi")
        if invoice["state"] == PAID:
            return invoice
        if invoice["state"] == CANCELLED:
            raise ValueError("Bekor qilingan hisob-fakturani to'lab bo'lmaydi")

        conn = self._connect()
        conn.execute(
            "UPDATE invoices SET state = 'paid', provider = ?, provider_txn_id = ?, paid_at = ?"
            " WHERE id = ? AND state = 'pending'",
            (provider, provider_txn_id, _iso(_utc_now()), invoice_id),
        )
        conn.commit()
        conn.close()

        self.cloud.extend_subscription(invoice["site_id"], invoice["months"])
        return self.get_invoice(invoice_id)  # type: ignore[return-value]

    def mark_refunded(self, invoice_id: str) -> Dict[str, Any]:
        """To'lov qaytarildi: obuna shuncha oyga qisqaradi, hisob bekor bo'ladi."""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Hisob-faktura topilmadi")

        was_paid = invoice["state"] == PAID
        conn = self._connect()
        conn.execute("UPDATE invoices SET state = 'cancelled' WHERE id = ?", (invoice_id,))
        conn.commit()
        conn.close()

        if was_paid:
            self.cloud.reduce_subscription(invoice["site_id"], invoice["months"])
        return self.get_invoice(invoice_id)  # type: ignore[return-value]

    def cancel_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """To'lanmagan hisobni bekor qilish (noto'g'ri ochilgan bo'lsa)."""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Hisob-faktura topilmadi")
        if invoice["state"] == PAID:
            raise ValueError("To'langan hisobni bekor qilib bo'lmaydi — qaytarish (refund) kerak")

        conn = self._connect()
        conn.execute("UPDATE invoices SET state = 'cancelled' WHERE id = ?", (invoice_id,))
        conn.commit()
        conn.close()
        return self.get_invoice(invoice_id)  # type: ignore[return-value]

    # ── Payme tranzaksiyalari ────────────────────────────────────────────

    def payme_get(self, txn_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM payme_transactions WHERE id = ?", (txn_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def payme_active_for_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Shu hisob bo'yicha yaratilgan yoki bajarilgan tranzaksiya (state 1 yoki 2)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM payme_transactions WHERE invoice_id = ? AND state IN (1, 2)"
            " ORDER BY create_time DESC LIMIT 1",
            (invoice_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def payme_create(
        self,
        txn_id: str,
        invoice_id: str,
        amount_tiyin: int,
        payme_time: int,
        create_time: int,
    ) -> Dict[str, Any]:
        merchant_txn_id = uuid.uuid4().hex[:16]
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO payme_transactions
                (id, invoice_id, merchant_txn_id, amount_tiyin, state, payme_time, create_time)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (txn_id, invoice_id, merchant_txn_id, amount_tiyin, payme_time, create_time),
        )
        conn.commit()
        conn.close()
        return self.payme_get(txn_id)  # type: ignore[return-value]

    def payme_set_state(
        self,
        txn_id: str,
        state: int,
        *,
        perform_time: int = 0,
        cancel_time: int = 0,
        reason: Optional[int] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        fields = ["state = ?"]
        values: List[Any] = [state]
        if perform_time:
            fields.append("perform_time = ?")
            values.append(perform_time)
        if cancel_time:
            fields.append("cancel_time = ?")
            values.append(cancel_time)
        if reason is not None:
            fields.append("reason = ?")
            values.append(reason)
        values.append(txn_id)
        conn.execute(f"UPDATE payme_transactions SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return self.payme_get(txn_id)  # type: ignore[return-value]

    def payme_statement(self, from_ms: int, to_ms: int) -> List[Dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM payme_transactions WHERE payme_time BETWEEN ? AND ? ORDER BY payme_time",
            (from_ms, to_ms),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Click tranzaksiyalari ────────────────────────────────────────────

    def click_get(self, click_trans_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM click_transactions WHERE click_trans_id = ?", (click_trans_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def click_prepare(
        self, click_trans_id: str, invoice_id: str, amount_uzs: int
    ) -> Dict[str, Any]:
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO click_transactions
                (click_trans_id, invoice_id, amount_uzs, state, created_at)
            VALUES (?, ?, ?, 'prepared', ?)
            """,
            (click_trans_id, invoice_id, amount_uzs, _iso(_utc_now())),
        )
        conn.commit()
        conn.close()
        return self.click_get(click_trans_id)  # type: ignore[return-value]

    def click_set_state(self, click_trans_id: str, state: str) -> Dict[str, Any]:
        conn = self._connect()
        conn.execute(
            "UPDATE click_transactions SET state = ? WHERE click_trans_id = ?",
            (state, click_trans_id),
        )
        conn.commit()
        conn.close()
        return self.click_get(click_trans_id)  # type: ignore[return-value]
