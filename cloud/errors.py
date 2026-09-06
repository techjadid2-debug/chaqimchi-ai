"""Xato javoblari — matn va KOD bir vaqtda.

## Nega alohida istisno kerak

`HTTPException(404, "Do'kon topilmadi")` matnni to'g'ridan-to'g'ri
javobga yozadi va panel uni o'zgartirmasdan ko'rsatadi
(`frontend/src/api.ts` dagi `body.detail`).  Uch tilga o'tganda o'sha
matn so'rov tilida bo'lishi kerak.

`HTTPException(detail={...})` bilan qilib bo'lmaydi: FastAPI lug'atni
javob ILDIZIGA qo'yadi, ya'ni `body.detail` obyektga aylanadi va mijoz
`[object Object]` ko'radi.  Shuning uchun o'z istisnomiz bor —
`detail` satrligicha qoladi, yoniga esa mashina o'qiydigan `code`
qo'shiladi.

Natijada panelda **birorta o'zgarish talab qilinmaydi**: eski kod
`detail` ni o'qiyveradi, yangi testlar esa matnga emas, `code` ga
bog'lanadi.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from cloud import i18n


class ApiError(Exception):
    """Mijozga ko'rinadigan xato.

    `key` — katalogdagi kalit (`error.owner.site_not_found`), `params`
    esa matn ichidagi o'rinbosarlar.  Kalit topilmasa `i18n.t` kalitning
    o'zini qaytaradi: xato yo'qolib ketmaydi, faqat xunuk ko'rinadi va
    QA'da darrov ko'zga tashlanadi.
    """

    def __init__(self, key: str, status: int = 400, **params: Any) -> None:
        super().__init__(key)
        self.key = key
        self.status = status
        self.params: Dict[str, Any] = params


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, ApiError) else ApiError("error.unknown", 500)
    return JSONResponse(
        {
            "detail": i18n.t(error.key, **error.params),
            "code": error.key,
        },
        status_code=error.status,
    )
