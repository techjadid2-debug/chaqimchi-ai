"""Hisob-faktura va provayder tranzaksiyalari (SQLite, cloud.db bilan bir faylda).

Bitta qoida butun modul bo'ylab: **obuna faqat hisob-faktura to'langanda uzayadi**.
Payme ham, Click ham, "naqd" ham shu bitta yo'ldan o'tadi — `mark_paid()`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

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

    def _connect(self) -> Any:
        """Ulanish `CloudStore` niki bilan BIR XIL bazaga.

        Ilgari bu yerda o'z `sqlite3.connect` i turardi.  Cloud
        PostgreSQL'ga o'tganda u jimgina eski SQLite fayliga yozib
        turaverardi: obuna bir bazada, hisob-faktura boshqasida —
        ya'ni to'lov obunani uzaytirmay qolardi.  Dialekt bitta
        joydan olinishi shu sababdan.
        """
        return self.cloud._connect()

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
                -- Yozuv tartibi.  `created_at` bir soniya aniqligida va
                -- bitta saytga bir soniyada ikki hisob ochilishi mumkin.
                -- Ilgari tartibni SQLite `rowid` i hal qilardi, lekin
                -- PostgreSQL'da u YO'Q — `cloud/store.py: device_jobs`
                -- dagi bilan bir xil yechim.
                seq INTEGER NOT NULL DEFAULT 0,
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

            -- Saqlangan karta.  KARTA RAQAMI SAQLANMAYDI: bazada faqat
            -- provayderning tokeni (shifrlangan) va oxirgi to'rt raqam
            -- turadi.  Token o'zi ham «pul yechish huquqi», shuning
            -- uchun u kamera RTSP manzili bilan bir xil yo'ldan
            -- o'tadi — Fernet (`_card_cipher`).
            --
            -- Har saytda ko'pi bilan BITTA faol karta: ikkita bo'lsa
            -- «qaysi biridan yechildi» degan savol paydo bo'ladi va
            -- avtomatik to'lov uchun bu javobsiz qolardi.  Yangi karta
            -- ulanganda eskisi `active=0` bo'ladi.
            CREATE TABLE IF NOT EXISTS payment_cards (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                token_ciphertext TEXT NOT NULL,
                masked_pan TEXT NOT NULL,
                expires_at TEXT,
                verified_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cards_site ON payment_cards(site_id, active);
            """
        )
        # Ishlab turgan bazaga `seq`.  Eski qatorlarga 0 tushadi — ular
        # baribir `created_at` bo'yicha oldinda.
        if "seq" not in self._columns(conn, "invoices"):
            conn.execute("ALTER TABLE invoices ADD COLUMN seq INTEGER NOT NULL DEFAULT 0")
        # Avtomatik yechish urinishlari.  Ishlab turgan bazaga
        # qo'shiladi: jadval `payment_cards` bilan birga yaratilgan
        # bo'lsa ham, eski nusxalarda bu ustunlar yo'q.
        card_columns = self._columns(conn, "payment_cards")
        if "attempts" not in card_columns:
            conn.execute(
                "ALTER TABLE payment_cards ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "last_attempt_at" not in card_columns:
            conn.execute("ALTER TABLE payment_cards ADD COLUMN last_attempt_at TEXT")
        conn.commit()
        conn.close()

    def _columns(self, conn: Any, table: str) -> set:
        """Jadval ustunlari.  `PRAGMA` faqat SQLite'da bor."""
        if self.cloud.postgres:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=?",
                (table,),
            ).fetchall()
            return {str(dict(row)["column_name"]) for row in rows}
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

    # ── Saqlangan karta ──────────────────────────────────────────────────

    @staticmethod
    def _card_cipher() -> Fernet:
        """Provayder tokenini shifrlaydi.

        Token — «pul yechish huquqi», ya'ni kamera parolidan ham
        qimmatroq: bazaning nusxasi sizib ketsa u bilan to'lov
        qilish mumkin.  Shuning uchun ALOHIDA kalit
        (`ENES_CARD_SECRET_KEY`) — kamera kaliti bilan bir xil emas:
        ikkalasi bitta kalitda bo'lsa bittasining almashtirilishi
        ikkinchisini ham buzardi.
        """
        key = os.environ.get("ENES_CARD_SECRET_KEY", "").strip()
        if not key:
            if os.environ.get("ENES_ENV", "development") == "production":
                raise RuntimeError("ENES_CARD_SECRET_KEY sozlanmagan")
            key = base64.urlsafe_b64encode(
                hashlib.sha256(b"enes-development-card-key").digest()
            ).decode("ascii")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("ENES_CARD_SECRET_KEY Fernet kaliti noto'g'ri") from exc

    def save_card(
        self,
        site_id: str,
        *,
        provider: str,
        token: str,
        masked_pan: str,
        expires_at: Optional[str] = None,
        verified: bool = False,
    ) -> Dict[str, Any]:
        """Kartani saqlaydi va saytdagi eskisini o'chiradi (bittadan ortiq emas)."""
        if provider not in {"payme", "click"}:
            raise ValueError(f"Noma'lum to'lov provayderi: {provider}")
        if not token:
            raise ValueError("Karta tokeni bo'sh")
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "UPDATE payment_cards SET active=0,updated_at=? WHERE site_id=? AND active=1",
            (now, site_id),
        )
        card_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO payment_cards"
            "(id,site_id,provider,token_ciphertext,masked_pan,expires_at,verified_at,"
            "active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)",
            (
                card_id,
                site_id,
                provider,
                self._card_cipher().encrypt(token.encode("utf-8")).decode("ascii"),
                masked_pan[:32],
                expires_at,
                now if verified else None,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return self.get_card(site_id) or {}

    def mark_card_verified(self, site_id: str) -> Dict[str, Any]:
        """SMS kodi tasdiqlandi — kartadan pul yechish mumkin."""
        now = _iso(_utc_now())
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE payment_cards SET verified_at=?,last_error=NULL,updated_at=? "
            "WHERE site_id=? AND active=1",
            (now, now, site_id),
        )
        conn.commit()
        conn.close()
        if not cursor.rowcount:
            raise ValueError("Saqlangan karta topilmadi")
        return self.get_card(site_id) or {}

    def get_card(self, site_id: str, *, include_token: bool = False) -> Optional[Dict[str, Any]]:
        """Saytning faol kartasi.

        `include_token` ATAYLAB standart holda `False`: token javobga,
        logga yoki panelga HECH QACHON chiqmasligi kerak va uni
        so'rash ongli qaror bo'lsin (`charge()` dan tashqari
        chaqiruvchi yo'q).
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM payment_cards WHERE site_id=? AND active=1", (site_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        item = dict(row)
        ciphertext = str(item.pop("token_ciphertext", ""))
        item["active"] = bool(item["active"])
        item["verified"] = bool(item.get("verified_at"))
        if include_token:
            try:
                item["token"] = self._card_cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
            except (InvalidToken, UnicodeDecodeError) as exc:
                raise RuntimeError(f"{site_id}: karta tokeni o'qilmadi") from exc
        return item

    def forget_card(self, site_id: str) -> bool:
        """Kartani butunlay o'chiradi.

        `active=0` YETARLI EMAS: mijoz «kartani o'chir» deganda token
        bazada qolib ketmasligi kerak — u pul yechish huquqi.
        """
        conn = self._connect()
        cursor = conn.execute("DELETE FROM payment_cards WHERE site_id=?", (site_id,))
        conn.commit()
        conn.close()
        return bool(cursor.rowcount)

    def record_card_error(self, site_id: str, message: str) -> None:
        """Oxirgi yechish xatosi — panel va admin uchun.

        Kartani O'CHIRMAYDI: bir marta muvaffaqiyatsiz yechish
        (mablag' yetmadi) kartani yaroqsiz qilmaydi va uni o'chirish
        mijozni qayta ulashga majburlardi.
        """
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "UPDATE payment_cards SET last_error=?,updated_at=? WHERE site_id=? AND active=1",
            (str(message)[:300], now, site_id),
        )
        conn.commit()
        conn.close()

    def begin_charge_attempt(self, site_id: str, *, max_attempts: int = 3) -> bool:
        """Yechishdan OLDIN belgi qo'yadi.  `False` — urinmang.

        Belgi yechishdan OLDIN qo'yiladi va bu ataylab: jarayon
        yechish O'RTASIDA yiqilsa (provayder javobi kelgan, biz uni
        yozishga ulgurmagan) keyingi yurishda ikkinchi marta
        yechilardi — mijozdan ikki barobar pul olish eng qimmat xato.
        Kunlik hisobotdagi belgi ham aynan shu sababdan avval qo'yiladi.

        Ikki darvoza:
        * kuniga ko'pi bilan BITTA urinish — provayder tomonidagi
          vaqtincha nosozlik kun bo'yi takrorlanmasin;
        * davr uchun `max_attempts` — uchtadan keyin qo'lda to'lovga
          qaytadi va ega xabar oladi.
        """
        card = self.get_card(site_id)
        if card is None or not card.get("verified"):
            return False
        if int(card.get("attempts") or 0) >= max_attempts:
            return False
        last = str(card.get("last_attempt_at") or "")
        today = _iso(_utc_now())[:10]
        if last[:10] == today:
            return False
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "UPDATE payment_cards SET attempts=attempts+1,last_attempt_at=?,updated_at=? "
            "WHERE site_id=? AND active=1",
            (now, now, site_id),
        )
        conn.commit()
        conn.close()
        return True

    def finish_charge_attempt(self, site_id: str, *, ok: bool, error: str = "") -> None:
        """Muvaffaqiyatda hisob NOLLANADI — keyingi davr toza boshlansin."""
        now = _iso(_utc_now())
        conn = self._connect()
        if ok:
            conn.execute(
                "UPDATE payment_cards SET attempts=0,last_error=NULL,updated_at=? "
                "WHERE site_id=? AND active=1",
                (now, site_id),
            )
        else:
            conn.execute(
                "UPDATE payment_cards SET last_error=?,updated_at=? WHERE site_id=? AND active=1",
                (str(error)[:300], now, site_id),
            )
        conn.commit()
        conn.close()

    def sites_with_active_cards(self) -> List[str]:
        """Avtomatik yechish uchun nomzodlar — tasdiqlangan kartalar."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT site_id FROM payment_cards WHERE active=1 AND verified_at IS NOT NULL"
        ).fetchall()
        conn.close()
        return [str(dict(row)["site_id"]) for row in rows]

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

        # Narx tarmog'i `CloudStore.effective_monthly_uzs()` da — o'sha bitta
        # manbadan panel ham, hisob-faktura ham oladi.  Shartnoma bo'lsa
        # undagi muzlatilgan kotirovka ishlatiladi (katalog keyin o'zgarsa
        # mavjud mijoz narxi siljimaydi), aks holda tarif narxi.
        monthly = self.cloud.effective_monthly_uzs(site_id)
        # Yillik chegirma barcha tarifga bir xil qo'llanadi: rasmiy saytdagi
        # "2 oy bepul" va'dasi va hisob-faktura bitta qoidadan chiqishi shart.
        charged_months = billable_months(months)
        amount = monthly * charged_months
        invoice_id = uuid.uuid4().hex[:12]

        conn = self._connect()
        conn.execute(
            """
            INSERT INTO invoices
                (id, site_id, plan, months, amount_uzs, state, note, created_at, seq)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?,
                    (SELECT COALESCE(MAX(seq),0)+1 FROM invoices))
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
        sql += " ORDER BY i.created_at DESC, i.seq DESC LIMIT ?"
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
        cursor = conn.execute(
            "UPDATE invoices SET state = 'paid', provider = ?, provider_txn_id = ?, paid_at = ?"
            " WHERE id = ? AND state = 'pending'",
            (provider, provider_txn_id, _iso(_utc_now()), invoice_id),
        )
        changed = cursor.rowcount
        conn.commit()
        conn.close()

        if not changed:
            # Boshqa oqim bizdan oldin to'ladi deb belgilagan.
            #
            # Yuqoridagi `state == PAID` tekshiruvi buni USHLAMAYDI: u
            # o'qish, bu esa yozish — orasida bo'shliq bor.  Payme va Click
            # bir vaqtda javob qaytarsa (yoki provayder qayta urinsa)
            # ikkalasi ham `pending` ni o'qiydi, ikkinchisining UPDATE'i
            # 0 qator o'zgartiradi, lekin bungacha `extend_subscription`
            # BARIBIR chaqirilardi — obuna ikki barobar uzayardi.
            #
            # Endi darvoza `rowcount`: obunani faqat holatni HAQIQATAN
            # o'zgartirgan oqim uzaytiradi.
            return self.get_invoice(invoice_id)  # type: ignore[return-value]

        self.cloud.extend_subscription(invoice["site_id"], invoice["months"])
        return self.get_invoice(invoice_id)  # type: ignore[return-value]

    def mark_refunded(self, invoice_id: str) -> Dict[str, Any]:
        """To'lov qaytarildi: obuna shuncha oyga qisqaradi, hisob bekor bo'ladi."""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Hisob-faktura topilmadi")

        conn = self._connect()
        # `WHERE state = 'paid'` — `mark_paid` dagi bilan bir xil sabab:
        # ikki marta qaytarish obunani ikki barobar qisqartirmasin.
        cursor = conn.execute(
            "UPDATE invoices SET state = 'cancelled' WHERE id = ? AND state = 'paid'",
            (invoice_id,),
        )
        was_paid = bool(cursor.rowcount)
        if not was_paid:
            # To'lanmagan hisob ham bekor qilinaveradi — faqat obunaga
            # tegilmaydi.
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
