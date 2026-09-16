# OnyxOps — Faz Gunlugu

Plan: [plan.md](plan.md) · Mimari: [mimari.md](mimari.md)

Her faz tamamlandiginda bu gunluge ne yapildigi, hangi dosyalarin uretildigi ve
dogrulamanin nasil yapildigi islenir.

| Faz | Baslik | Durum |
|---|---|---|
| 0 | Iskelet kurulumu ve veri dogrulama | ✅ tamam |
| 1 | Veri katmani ve topoloji agaci | ⏳ bekliyor |
| 2 | Gurultu filtreleme ve zamansal kumeleme | ⏳ bekliyor |
| 3 | Topolojik birlestirme ve kok neden puanlamasi | ⏳ bekliyor |
| 4 | Olay karti uretimi ve 15 kart kapagi | ⏳ bekliyor |
| 5 | Pano, aksiyon takibi, gurultu denetimi | ⏳ bekliyor |
| 6 | Juri hazirligi ve belgeleme | ⏳ bekliyor |

---

## Faz 0 — Iskelet kurulumu ve veri dogrulama

**Gorev 0.1 — Repo iskeleti.** Yarisma teslim listesi (`README.md`,
`AI_JURI.md`, `submission.json`, `.env.example`, `CLAUDE.md`, `docs/`,
`src/`, `prompts/`, `demo/`) kontrol edildi. Bos gelen zorunlu dosyalar
dolduruldu; `src/config.py` tum yollarin ve esiklerin tek kaynagi olarak
olusturuldu.

**Gorev 0.2 — Veri dogrulamasi.** `src/verify_setup.py` yazildi. Satir
sayilarinin yaninda butunluk kontrolleri de yapiliyor:

- alarm sayisi = 3000, servis = 27, sunucu = 56, bagimlilik = 32
- `alarm_id` benzersizligi
- her alarm `host`'unun envanterde, her `service`'in katalogda karsiligi olmasi
- `severity` degerlerinin 1-5 araliginda olmasi
- tum zaman damgalarinin 10 Eylul 2026 01:30-03:30 penceresine dusmesi
- `alarms.json` ile `alarms.csv` alarm kimliklerinin birebir esitligi

**Dogrulama:** `python -m src.verify_setup` -> tum kontroller gecti.

**Not:** Veri sozlugunde gozlem penceresi 10 Eylul 2026 olarak veriliyor;
`VERI_SOZLUGU.md` icindeki `2026-11-21T01:42:17` ornegi yalnizca alan
bicimini gosteren bir ornek, gercek veri Eylul penceresinde.
