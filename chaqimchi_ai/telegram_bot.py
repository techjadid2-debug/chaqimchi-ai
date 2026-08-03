import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.AsyncClient()

    async def send_message(self, text: str):
        if not self.token or not self.chat_id:
            return

        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            await self.client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Telegram xabar yuborishda xato: {e}")

    async def send_photo(self, photo_bytes: bytes, caption: str):
        if not self.token or not self.chat_id:
            return

        try:
            url = f"{self.api_url}/sendPhoto"
            files = {"photo": ("alert.jpg", photo_bytes, "image/jpeg")}
            data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"}
            await self.client.post(url, data=data, files=files)
        except Exception as e:
            logger.error(f"Telegram rasm yuborishda xato: {e}")

    async def close(self):
        await self.client.aclose()

# Singleton-like helper
_bot_instance: Optional[TelegramBot] = None
_last_alerts: Dict[str, float] = {}

async def init_bot(token: Optional[str], chat_id: Optional[str]):
    global _bot_instance
    if token and chat_id:
        _bot_instance = TelegramBot(token, chat_id)
        logger.info("Telegram bot faollashtirildi.")
    else:
        logger.warning("Telegram bot token yoki chat_id berilmagan.")


async def close_bot() -> None:
    """Klientni yopib, global holatni tozalash.

    Bungacha `TelegramBot.close()` hech qachon chaqirilmagan — har ishga
    tushirishda bitta `httpx.AsyncClient` oqib ketardi.
    """
    global _bot_instance
    if _bot_instance is not None:
        try:
            await _bot_instance.close()
        finally:
            _bot_instance = None
    _last_alerts.clear()

async def send_alert(name: str, score: float, photo_bytes: Optional[bytes] = None, interval: int = 60):
    global _bot_instance, _last_alerts
    if _bot_instance is None:
        return

    import time
    now = time.time()
    if name in _last_alerts and (now - _last_alerts[name]) < interval:
        return # Juda tez-tez xabar yubormaslik uchun

    _last_alerts[name] = now

    caption = f"🚨 <b>Diqqat! Shaxs aniqlandi</b>\n\n👤 Ism: <b>{name}</b>\n📈 Ishonch: {score:.1%}\n⏰ Vaqt: {time.strftime('%H:%M:%S')}"

    if photo_bytes:
        await _bot_instance.send_photo(photo_bytes, caption)
    else:
        await _bot_instance.send_message(caption)
