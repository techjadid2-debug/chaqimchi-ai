# Arxiv hujjatlari

Quyidagi fayllar tarixiy qarorlarni saqlaydi, lekin yangi implementatsiya yoki
sotuv va’dasi uchun manba emas:

- `docs/archive/CHAQIMCHI_LITE.md` — Orange Pi/Lite kontrakti;
- `docs/archive/PRODUCTION_SET1.md` — Orange Pi production set;
- `docs/archive/REJA.md` — umumiy Face platforma roadmap’i;
- `docs/archive/BIZNES_MODEL.md` va `docs/archive/MOLIYA_VA_BOZOR.md` — eski taxminiy tariflar.
- `docs/KORISH_AGENTI.md` — AI kadr talqini. **Kod ham, hujjat ham o'chirildi**
  (`git tag archive/vision-agent`): talablar bo'yicha og'ir AI faqat cloudda
  ishlaydi, edge'da emas.
- **Lokal Face ID davomat to'plami** — `webapp/` va `chaqimchi_ai/` dagi yuz
  tanish modullari (~6 000 qator) **o'chirildi**
  (`git tag archive/attendance-local`): hech bir mijozga yetkazilmasdi,
  lekin CI va reponi og'irlashtirardi. Qaror: yuz tanish keyinchalik
  **cloud** tomonda quriladi; kerak bo'lsa kod tegdan qaytariladi:
  `git checkout archive/attendance-local -- webapp`.

`docs/ARXITEKTURA.md` va `docs/ANTISPOOF.md` — arxivlangan lokal Face
yadrosining reference hujjatlari; faol mahsulotga tegishli emas.

Faol hujjat: [Do‘kon MVP](../DOKON_MVP.md).
