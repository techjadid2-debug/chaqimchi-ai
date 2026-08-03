# O‘rnatuvchi qo‘llanmasi

## 1. Cloud (markaz)

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"
make run-cloud
```

## 2. Yangi mijoz

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"
python scripts/provision_site.py "Oq Saroy Do'kon" --plan starter --months 12
```

Chiqadi: `site_id`, `pairing_code`, narxlar.

## 3. Mini PC (mijoz joyida)

`config/config.yaml`:

```yaml
license:
  enabled: true
  cloud_url: "http://YOUR_CLOUD_IP:8750"
  pairing_code: "ABC123"   # bir martalik
```

```bash
make install-dev
make run-web
```

Logda `device_token` chiqsa — keyingi safar:

```yaml
license:
  enabled: true
  cloud_url: "http://YOUR_CLOUD_IP:8750"
  site_id: "..."
  device_token: "..."
```

## 4. Obuna uzaytirish (to‘lovdan keyin)

```bash
curl -X POST "http://127.0.0.1:8750/api/v1/admin/sites/SITE_ID/extend" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"months": 1}'
```

## 5. Holatlar

| status | Ma’nosi |
|--------|---------|
| active | Hammasi ishlaydi |
| grace | Muddati o‘tgan, 14 kun ichida to‘lov |
| expired | Kameralar ishlamaydi |
| suspended | Admin to‘xtatgan |
