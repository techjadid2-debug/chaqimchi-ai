"""Avtomatik konversiya (capture rate) — qurilma tomonidagi sanoq.

Konversiyaning maxraji ("nechta odam do'kongacha yetdi") ikki xil
manbadan kelishi mumkin (docs/RAQOBAT_RETAILSOLUTION.md, §5.A):

* **A1** — qo'shimcha kamerasiz: kirish kamerasida eshik oldida
  KO'RINGAN odam (ichkariga kirgan + kirmay ketgan);
* **A2** — tashqi kamera: do'kon oldidan O'TGAN odam.

Ikkalasi ham bitta savolga bog'lanadi: bu kamerada shu oynada nechta
NOYOB odam ko'rindi.  Shuning uchun bitta sanagich yetadi — `SeenCounter`.
`entered` (chiziqni kesib kirgan) allaqachon `line_crossed` dan cloudga
boradi, ya'ni bu yerda faqat MAXRAJ hisoblanadi; nisbatni cloud chiqaradi
(`cloud/value.py: capture_rate`).  A1/A2 orasidagi tanlov ham cloudda
(`cloud/value.py: select_passed`), chunki u qaysi kamera qaysi rolda
ekaniga bog'liq.

Nega qurilmada, cloudda emas: cloud `person_detected` ni ko'rmaydi (u
daqiqasiga ~100 ta, ataylab yuborilmaydi), ya'ni "nechta odam ko'rindi"
faqat shu yerda, treklar tirik joyda ma'lum.
"""

from __future__ import annotations

from typing import Dict, Set


class SeenCounter:
    """Oynada ko'ringan noyob odamlar soni — capture rate maxraji.

    Bir kadrlik xato deteksiya odam deb sanalmasligi kerak: track KAMIDA
    `min_frames` marta ko'rinsagina hisobga qo'shiladi.  Standart 2
    (ketma-ket ikki kadr) — bitta yolg'on quti "yana bir mijoz keldi"
    deb konversiya maxrajini shishirmasin, natijada foiz sun'iy pasaymasin.

    Bir track oyna ichida necha marta ko'rinsa ham BIR marta sanaladi;
    oyna tugab (`flush`) yangidan boshlangach qaytsa, yangi odam kabi
    sanaladi — bu `line_crossed` re-entry mantiqi bilan bir xil (chiqib
    qaytgan odam ikki tashrif).
    """

    def __init__(self, *, min_frames: int = 2) -> None:
        if min_frames < 1:
            raise ValueError("min_frames musbat bo'lishi kerak")
        self._min_frames = min_frames
        #: Hali chegaraga yetmagan tracklar: track → ko'ringan kadrlar soni.
        self._frames: Dict[int, int] = {}
        #: Chegaradan o'tib, oyna sanog'iga kirgan tracklar.
        self._counted: Set[int] = set()

    def mark(self, track_id: int) -> None:
        """Track bu kadrda ko'rindi."""
        tid = int(track_id)
        if tid in self._counted:
            return
        self._frames[tid] = self._frames.get(tid, 0) + 1
        if self._frames[tid] >= self._min_frames:
            self._counted.add(tid)
            # Sanaldi — endi kadrlar hisobini saqlab turishning hojati yo'q.
            del self._frames[tid]

    def flush(self) -> int:
        """Oynadagi sonni qaytaradi va sanoqni noldan boshlaydi.

        Yarim yo'lda qolgan (chegaraga yetmagan) tracklar ham unutiladi:
        oyna chegarasi ular uchun ham chegara, aks holda kam ko'ringan
        odam keyingi oynaga "oqib" o'tib, ikki oynada bir marta sanalardi.
        """
        count = len(self._counted)
        self._counted.clear()
        self._frames.clear()
        return count

    @property
    def pending(self) -> int:
        """Shu ondagi sanoq (flushsiz) — heartbeat/diagnostika uchun."""
        return len(self._counted)
