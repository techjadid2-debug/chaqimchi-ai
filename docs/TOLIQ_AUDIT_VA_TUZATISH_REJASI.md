# Chaqimchi AI — to'liq audit va xatolarni tuzatish rejasi

Saqlangan sana: 2026-09-06.
Holat: reja saqlandi; dastlabki tekshiruv o'tkazilgan, tuzatishlar hali bajarilmagan.

## Maqsad va kelishilgan ustuvorlik

Loyihani dasturchi va oddiy foydalanuvchi nigohidan tekshirish: local edge,
cloud, asosiy sayt, app/owner va admin panellaridagi xatolarni aniqlash,
tuzatish hamda ishlatish va qo'llab-quvvatlashni yaxshilash.

- Ustuvorlik: **avval xatolarni tuzatish (bugfix first)**.
- Qamrov: **barcha qismlar va hujjatlar (hammasi + docs)**.
- Har bir topilma dalil, qayta tekshirish usuli va muhimlik darajasi bilan qayd etiladi.
- Avval xavfsizlik, ma'lumot yaxlitligi va asosiy foydalanuvchi oqimlarini buzadigan xatolar; keyin qulaylik va vizual yaxshilashlar.

## 1. Boshlang'ich holat va ishonchli test natijalari

- [ ] Mavjud arxitektura, ishga tushirish usullari va frontend manba/build bog'lanishini aniqlashtirish.
- [ ] Testlarni qismlar bo'yicha ishga tushirib, takrorlanadigan xatolarni ajratish.
- [ ] Katta test to'plamidagi `Too many open files` sababini tekshirish: SQLite ulanishlari, fayllar, TestClient va fon vazifalarining yopilishi.
- [ ] Port ochishga doir muhit cheklovlarini mahsulot xatolaridan ajratish.
- [ ] Aniqlangan muammolar uchun ustuvor ish ro'yxatini shakllantirish.

## 2. Local edge va mahalliy sozlash paneli

Asosiy manbalar: `chaqimchi_ai/local/`, `chaqimchi_ai/retail/` va ularga tegishli testlar.

- [ ] Ishga tushish, portni band qilish, ikkinchi nusxa va to'g'ri yopilish holatlarini tekshirish.
- [ ] Mahalliy panelning Host/loopback himoyasi va sozlamalarni saqlashini tekshirish.
- [ ] Kamera qo'shish, noto'g'ri manzil/parol, oqim uzilishi va qayta ulanishni tekshirish.
- [ ] Cloud bilan ulash, masofaviy konfiguratsiya va konfiguratsiya yangilanishini tekshirish.
- [ ] Internet uzilishi, offline navbat, qayta yuborish va takroriy hodisalardan himoyani tekshirish.
- [ ] Xato xabarlarini oddiy foydalanuvchiga tushunarli va keyingi harakati aniq bo'ladigan qilish.

## 3. Cloud backend

Asosiy manbalar: `cloud/main.py`, `cloud/store.py`, `cloud/urls.py` va tegishli modullar.

- [ ] Autentifikatsiya, sessiya/token, owner/admin vakolatlari va mijozlar ma'lumotlari ajratilishini tekshirish.
- [ ] Qurilma ulash, kameralar, konfiguratsiya va hodisalar API shartnomalarini frontend/edge bilan solishtirish.
- [ ] SQLite ulanishlari, tranzaksiyalar, parallel so'rovlar va resurslarning yopilishini tekshirish.
- [ ] Fon vazifalarining ishga tushishi, xatolari, bekor qilinishi va shutdown jarayonini tekshirish.
- [ ] Tarif, to'lov, bildirishnoma va hisobot oqimlaridagi xatolarni tekshirish.
- [ ] Subdomenlar, yo'naltirishlar, API manzillari va xato javoblarini tekshirish.

## 4. Asosiy sayt, app/owner va admin

Asosiy manbalar: `cloud/static/site.*`, tegishli statik sahifalar va `frontend/src/`.
React build natijasi `cloud/static/v2/` ichiga chiqadi; o'zgarishlar manba fayllarida qilinadi.

- [ ] Sayt → tarif → yuklab olish/ulash → kabinetga kirish oqimini tekshirish.
- [ ] Saytdagi tariflar, imkoniyatlar va o'rnatish ko'rsatmalarini amaldagi API hamda mahsulot bilan solishtirish.
- [ ] Owner panelida qurilma/kamera, hodisalar, hisobot va sozlamalar bilan ishlashni tekshirish.
- [ ] Admin panelining asosiy boshqaruv amallari, validatsiya va xato holatlarini tekshirish.
- [ ] Yuklanish, bo'sh natija, server xatosi, sessiya tugashi va qayta urinish holatlarini tekshirish.
- [ ] Mobil ekran, klaviatura orqali boshqarish, formalar va tugmalarning tushunarliligini tekshirish.
- [ ] Router, API chaqiruvlari va eski statik/yangi React sahifalar o'rtasidagi moslikni tekshirish.
- [ ] Tasdiqlangan funksional xatolardan keyin UI/UX yaxshilashlarini amalga oshirish.

## 5. Tuzatish va tekshirish tartibi

1. Muammoni qayta yuzaga keltirish va sababini aniqlash.
2. Ta'sir qiladigan qatlamlar va foydalanuvchi oqimini belgilash.
3. Sababni bartaraf etadigan o'zgarishni amalga oshirish.
4. Muhim mantiqiy xatolarga zarur regressiya testini qo'shish.
5. Tegishli testlar, frontend typecheck va buildni tekshirish.
6. O'zgargan oqimni foydalanuvchi sifatida tekshirish va natijani hujjatlashtirish.

## 6. Hujjatlar

- [ ] README va arxitektura hujjatlaridagi manba/build hamda local/cloud chegaralarini yangilash.
- [ ] O'rnatish, sozlash va nosozlikni aniqlash yo'riqnomalarini amaldagi holatga moslashtirish.
- [ ] Auditda tasdiqlangan topilmalar, tuzatishlar va qolgan ishlarni qayd etish.
- [ ] Test buyruqlari, zarur muhit va tekshirilmagan tashqi bog'liqliklarni yozish.

Bog'liq mavjud hujjatlar: [arxitektura xaritasi](ARXITEKTURA_XARITASI.md),
[oldingi audit](AUDIT_TAHLIL.md), [ish daftari](ISH_DAFTARI.md),
[production runbook](PRODUCTION_RUNBOOK.md).

## Dastlabki tekshiruvdan ma'lum holat

Quyidagilar reja tuzilishidan oldingi tekshiruv natijalari; yakuniy qabul natijasi emas.

- Frontend `npm run typecheck` tekshiruvi muvaffaqiyatli o'tgan.
- Statik sahifalar, cloud API, owner kameralar, pricing, connect/events UI,
  platform hosts va remote config bo'yicha alohida test guruhlari o'tgan.
- Local paneldagi ikkita port testi muhitda socket bind taqiqlangani bilan
  to'qnashgan (`PermissionError: Operation not permitted`). Bular hozircha
  tasdiqlangan mahsulot xatosi hisoblanmaydi.
- Katta pytest ishga tushirishida `Too many open files` va SQLite
  `unable to open database file` xatolari kuzatilgan. Resurs tugashi sababli
  keyingi xatolar bir-biriga bog'liq bo'lishi mumkin; sabab hali ajratilmagan.
- To'liq test to'plami muvaffaqiyatli yakunlangani tasdiqlanmagan.

## Yakuniy qabul mezonlari va taxminlar

- [ ] Topilgan kritik/yuqori muhimlikdagi xatolar tuzatilgan yoki aniq tashqi to'sig'i va keyingi qadami qayd etilgan.
- [ ] Tuzatilgan qismlarning testlari, frontend typecheck va build muvaffaqiyatli.
- [ ] Asosiy foydalanuvchi oqimlari hamda xato/offline holatlari tekshirilgan.
- [ ] To'liq regressiya natijasi va muhit sabab bajarilmagan tekshiruvlar alohida ko'rsatilgan.
- [ ] Hujjatlar amaldagi xatti-harakat va tekshiruv natijalariga mos.

Auditning boshlang'ich manbasi — ushbu repository. Haqiqiy kamera, Windows
qurilmasi yoki jonli cloud muhiti talab qiladigan sinovlar mavjud muhitga
qarab bajariladi; bajarilmagan sinov o'tgan deb belgilanmaydi. Katta
arxitektura migratsiyasi va yangi mahsulot funksiyalari zarurati audit
dalillaridan keyin alohida baholanadi. Bu rejani saqlashning o'zi kodni
o'zgartirish yoki production deploy bajarilganini anglatmaydi.
