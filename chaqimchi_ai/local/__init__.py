"""Mijozning o'z kompyuterida ishlaydigan Chaqimchi AI.

Bu paket `cloud/` dan **mustaqil**: mijoz mashinasida admin paneli, to'lov
callbacklari yoki lead API ishlashi kerak emas va xavfli ham.  Windows
o'rnatuvchisi faqat `chaqimchi_ai/`, `config/` va `models/` ni ko'chiradi.

Ikkita qism bor:

* **Sozlash ustasi** (`app.py`) — kamera topish, sinash, chiziq chizish va
  ishga tushirish.  Foydalanuvchi buni brauzerda ko'radi.
* **Nazoratchi** (`supervisor.py`) — haqiqiy AI zanjirini
  (`chaqimchi_ai.retail.service`) alohida jarayon sifatida boshqaradi.

Zanjirning o'zi umuman o'zgarmaydi: u `retail.cameras_source: config`
rejimida lokal YAML dan kamera ro'yxatini oladi, ya'ni cloud ulanmasa ham
to'liq ishlaydi.
"""

from __future__ import annotations

__all__ = ["paths", "config_store", "supervisor", "camera_probe"]
