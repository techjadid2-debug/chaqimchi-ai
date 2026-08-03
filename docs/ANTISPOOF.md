# Anti-spoofing — soxta yuzdan himoya

Maqsad: telefon ekranidagi yoki bosma qog‘ozdagi yuzni tirik odamdan ajratish.

## Qisqacha: nimani kutish mumkin

| Backend | Model kerakmi | Nimani tutadi | Nimani tutmaydi |
|---------|---------------|---------------|-----------------|
| `heuristic` (standart) | yo‘q | Xira kadr, ekran piksel panjarasi ko‘rinib turgan surat, rangi yuvilgan bosma | Yuqori sifatli ekran, katta monitor, qalin bosma, video hujum |
| `onnx` | ha | Modelning sifatiga bog‘liq | — |

**Ochiq aytamiz:** `heuristic` — bu **filtr**, to‘liq himoya emas. U oson hujumlarni
to‘xtatadi, lekin qasddan tayyorlangan hujumni to‘xtatmaydi.

Agar tizim **eshik ochish yoki to‘lov** uchun ishlatilsa, faqat yuzga tayanmang —
ikkinchi omil qo‘shing (PIN, karta, xodim tasdiqlashi).

## Yoqish

```yaml
antispoof:
  enabled: true
  backend: heuristic
  min_score: 0.5           # shundan past ball — soxta
  min_blur_variance: 80.0  # qattiq chegara: xira kadr har doim rad etiladi
```

Rad etilgan urinishlar logda ko‘rinadi va metrikaga yoziladi:

```bash
curl http://127.0.0.1:8742/api/metrics | grep spoofs
curl http://127.0.0.1:8742/metrics | grep chaqimchi_spoofs_total
```

## Heuristika qanday ishlaydi

Uchta signal vaznli o‘rtacha bilan qo‘shiladi (`0`–`1`, yuqori = tirikroq):

| Signal | Vazn | Nimani o‘lchaydi |
|--------|------|------------------|
| `moire` | 0.50 | Furye spektrida davriy cho‘qqi — ekran piksel panjarasi. O‘lchangan: toza yuz ~2.5–4 sigma, ekran panjarasi ~6–11 sigma |
| `chroma` | 0.30 | To‘yinganlik tarqoqligi — ekran va bosma rang gammasini siqadi |
| `specular` | 0.20 | To‘yingan (>=250) piksellar ulushi — tekis sirtdan qaytgan porlash |

Bundan tashqari **qattiq chegara**: `min_blur_variance` dan xira kadr boshqa
signallardan qat’i nazar rad etiladi.

**O‘tkirlik ataylab musbat ovoz sifatida ishlatilmaydi.** O‘lchov shuni ko‘rsatdi:
ekran panjarasi Laplacian dispersiyasini **oshiradi** (tirik yuz ~130, ekrandagi
o‘sha yuz ~2500), ya’ni "o‘tkir = tirik" qoidasi soxta tomonni qo‘llab-quvvatlar edi.

### O‘lchangan natijalar

Uchta haqiqiy surat va ular asosida taqlid qilingan hujumlarda:

| Variant | Ball |
|---------|------|
| Haqiqiy yuz | 0.99–1.00 |
| Ekran (panjara ko‘rinadi) | 0.36–0.40 → **rad etildi** |
| Ekran (nozik panjara) | 0.66–1.00 → o‘tib ketdi |
| Bosma qog‘oz | 0.73–0.99 → asosan o‘tib ketdi |

Ya’ni: tirik yuzni noto‘g‘ri rad etish xavfi past, lekin hujumlarning bir qismi o‘tadi.

## O‘z suratlaringizda tekshirish

Bu eng muhim qadam — yuqoridagi raqamlar taqlid qilingan hujumlarga tegishli,
sizning kamerangiz va sizning yorug‘ligingizga emas.

```bash
mkdir -p data/antispoof/real data/antispoof/spoof
# real/  → kameraga qarab turgan odamlarning kadrlari
# spoof/ → telefon ekranida yuz ko'rsatilgan holda olingan kadrlar
python scripts/validate_antispoof.py
```

Chiqishda: tirikni rad etish ulushi (FRR), soxtani o‘tkazib yuborish ulushi (FAR)
va tavsiya etilgan `min_score`. Har ikkala papkada kamida 20 tadan surat bo‘lsin.

## ONNX model ulash

```yaml
antispoof:
  enabled: true
  backend: onnx
  model_path: models/antispoof.onnx
  live_index: 1     # modelning "tirik" sinf indeksi
  min_score: 0.5
```

Kutilgan interfeys: kirish `[1, 3, N, N]` float32, BGR, `[0, 1]` (piksel/255);
chiqish `[1, C]` logitlar (softmax modul ichida qo‘llanadi).

Model topilmasa yoki yuklanmasa — server ishdan to‘xtamaydi, ogohlantirish
yozib heuristikaga qaytadi.

**Modelni ulashdan oldin `scripts/validate_antispoof.py` bilan tekshiring.**

## Tekshirilgan va rad etilgan modellar

Ochiq manbadagi MiniFASNet modellari sinovdan o‘tkazildi va **ishlatilmadi**:

- `garciafido/minifasnet-v2-anti-spoofing-onnx` (HuggingFace)
- Upstream `2.7_80x80_MiniFASNetV2.pth` + `4_0_0_80x80_MiniFASNetV1SE.pth`
  ([minivision-ai/Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing)) —
  SHA-256 tekshirilgan, PyTorch → ONNX konvertatsiyasi qayta bajarilgan
  (torch va ONNX natijalari farqi 8e-07, `state_dict` to‘liq mos)

Natija: har uchala model **barcha rasmga bir xil javob berdi** — upstream’ning
o‘z namuna suratlarida ham (`image_T1.jpg` = haqiqiy, `image_F1/F2.jpg` = soxta):

```
rasm             kutilgan   yig'indi (p0, p1, p2)      xulosa
image_T1.jpg     HAQIQIY    [0.059 0.032 1.909]        SOXTA  ✗
image_F1.jpg     SOXTA      [0.061 0.033 1.906]        SOXTA  ✓
image_F2.jpg     SOXTA      [0.063 0.029 1.908]        SOXTA  ✓
```

Uchala rasmda ehtimollar deyarli bir xil — model rasm mazmuniga javob bermayapti.
Shuning uchun bu modellar loyihaga qo‘shilmadi.

Ishonchli neyron anti-spoof kerak bo‘lsa: tijoriy SDK (masalan iBeta sertifikatlangan)
yoki o‘z hujum ma’lumotlaringizda o‘qitilgan model. Har qanday holatda —
`scripts/validate_antispoof.py` bilan o‘lchab, keyin ishga qo‘ying.
