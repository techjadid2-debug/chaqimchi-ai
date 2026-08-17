# Telegram botni bezash (BotFather) — 5 daqiqalik ro'yxat

Buyruqlar menyusi kod tomonidan avtomatik o'rnatiladi (`setMyCommands`,
cloud har start bo'lganda). Quyidagilarni esa faqat bot egasi BotFather
orqali qila oladi — bir marta qilinadi.

Telegram'da [@BotFather](https://t.me/BotFather) ni oching va tartib
bilan quyidagilarni bajaring. Har buyruqdan keyin BotFather qaysi botga
tegishli ekanini so'raydi — o'z botingizni tanlang.

## 1. Avatar (rasm)

1. `/setuserpic` yuboring.
2. Botni tanlang.
3. Shu papkadagi `docs/bot/avatar.png` faylini rasm sifatida yuboring
   (fayl emas, aynan rasm — "Photo" sifatida).

## 2. Qisqa tavsif (bot profilida ko'rinadi)

`/setdescription` yuboring, botni tanlang, keyin shu matnni yuboring:

```
Do'koningiz nazorati: kirdi-chiqdi hisobi, navbat, kamera holati va kunlik hisobot — hammasi shu botda. Boshlash uchun /start bosing.
```

## 3. "Nima qila oladi" matni (bot haqida sahifada)

`/setabouttext` yuboring, botni tanlang, keyin shu matnni yuboring:

```
Chaqimchi AI — do'kon uchun aqlli kamera-nazorat. Kunlik va haftalik hisobotlar, jonli kamera rasmlari, muhim ogohlantirishlar.
```

## 4. Bot nomi (agar hali qo'yilmagan bo'lsa)

`/setname` yuboring, botni tanlang, keyin:

```
Chaqimchi AI
```

## Tekshirish

- Botga kirib `/start` bosing — yangi xush kelibsiz xabari va tugmalar
  chiqadi.
- Xabar maydonidagi `/` tugmasini bosing — menyuda `/hisobot`,
  `/kamera`, `/panel`, `/yordam` ko'rinadi (cloud qayta ishga
  tushgandan keyin).
- Bot profilini oching — avatar va tavsif ko'rinadi.

## Eslatma

- Buyruqlar menyusini BotFather'da qo'lda kiritmang (`/setcommands`
  kerak emas) — kod o'zi o'rnatadi va keyingi o'zgarishda avtomatik
  yangilanadi.
