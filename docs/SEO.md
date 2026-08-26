# Google'da chiqish — nima qilingan va sizdan nima kutiladi

> Qisqasi: kod tomoni tayyor. Qolgan ikkita qadamni **faqat domen
> egasi** bajara oladi — ular pastda, 10 daqiqalik ish.

## Kod tomonida nima bor

| Narsa | Qayerda | Nima beradi |
|---|---|---|
| `robots.txt` | `cloud/main.py:robots_txt` | Landing va docs ochiq; panel va API yopiq |
| `sitemap.xml` | `cloud/main.py:sitemap_xml` | 9 sahifa + har biriga **`lastmod`** (fayl sanasidan) |
| `canonical` | `cloud/static/site.html` | `www.`, IP yoki `?utm_...` nusxasi alohida sahifa sanalmaydi |
| `og:` teglar | o'sha yerda | Telegram/Facebook havolada rasm va matn ko'rsatadi |
| **JSON-LD** | sahifa oxirida | `Organization`, `SoftwareApplication`, `FAQPage` |

**FAQ razmetkasi** eng foydalisi: Google natijada savollarni ochiladigan
qilib ko'rsatadi, ya'ni odam saytga kirmasdan javobni ko'radi va
ishonch bilan bosadi.

Razmetkadagi har savol sahifada ham borligi test bilan qulflangan
(`tests/test_static_pages.py`) — mos kelmagan FAQ razmetkasi uchun
Google jazolaydi.

## Sizdan kutiladigan ikki qadam

### 1. Search Console'ga qo'shish

1. [search.google.com/search-console](https://search.google.com/search-console)
   ga Google hisobingiz bilan kiring.
2. **«Domain»** turini tanlang (`URL prefix` emas — domain butun
   `chaqimchi.uz` ni, jumladan `www.` va subdomenlarni qamraydi).
3. `chaqimchi.uz` deb yozing → **Continue**.
4. Google bitta **TXT yozuv** beradi, masalan:
   `google-site-verification=abc123...`
5. Uni domen DNS'iga TXT sifatida qo'shing (domen qayerdan olingan
   bo'lsa — o'sha panelda). Yozuv nomi `@` yoki bo'sh.
6. DNS tarqalishini kuting (odatda 10-30 daqiqa) → **Verify**.

> **TXT qo'sha olmasangiz** ayting — sahifaga meta-teg qo'yish yo'li
> ham bor, lekin u faqat `chaqimchi.uz` ni tasdiqlaydi, subdomenlarni
> emas.

### 2. Sitemap'ni yuborish

Tasdiqlangach: chap menyuda **Sitemaps** → `sitemap.xml` deb yozing →
**Submit**.

Shundan keyin Google sahifalarni o'zi aylanib chiqadi.

## Qachon natija ko'rinadi

| Vaqt | Nima bo'ladi |
|---|---|
| 1-3 kun | `site:chaqimchi.uz` bo'yicha birinchi sahifalar chiqadi |
| 1-2 hafta | "chaqimchi" degan brend so'rovda birinchi o'rin |
| 1-3 oy | "do'kon uchun kamera analitikasi" kabi so'rovlarda ko'rina boshlaydi |

Oxirgi qatorga **kafolat yo'q**: u raqobat va kontentga bog'liq.
Brend so'rovi esa deyarli har doim ishlaydi.

## Tekshirish

```bash
curl -sS https://chaqimchi.uz/robots.txt
curl -sS https://chaqimchi.uz/sitemap.xml | grep -c lastmod   # 9 bo'lsin
curl -sS https://chaqimchi.uz/ | grep -o 'rel="canonical"'
curl -sS https://chaqimchi.uz/ | grep -o 'application/ld+json'
```

Razmetkani Google o'zi qanday o'qishini ko'rish:
[Rich Results Test](https://search.google.com/test/rich-results) ga
`https://chaqimchi.uz` ni kiriting — `FAQ` va `Software App` bloklari
ko'rinishi kerak.

## Keyingi bosqich (hozir rejada YO'Q)

Qidiruvdan **muntazam** mijoz kelishi uchun kontent kerak: "do'kon
uchun videoanalitika narxi", "NVR'ga AI qanday ulanadi" kabi
sahifalar. Bu alohida ish va alohida qaror — texnik razmetka o'zi
sahifani birinchi o'ringa olib chiqmaydi.
