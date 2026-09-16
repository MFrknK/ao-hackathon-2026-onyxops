# CLAUDE.md — OnyxOps ajan yapilandirmasi

Bu dosya Claude Code'un bu repoda calisirken uyacagi kurallari tanimlar.

## Proje

**S-A1 "Alarm Firtinasi"** (AO Hackathon 2026). 2 saatlik pencerede uretilmis
3.000 sentetik alarmi, servis bagimlilik topolojisi ve zaman bilgisini
kullanarak **en fazla 15 olay kartina** indirgeyen bir korelasyon motoru ve
operator panosu.

Calisma plani: [docs/plan.md](docs/plan.md) · Mimari: [docs/mimari.md](docs/mimari.md)
· Faz gunlugu: [docs/fazlar.md](docs/fazlar.md)

## Mutlak kurallar

1. **Veri kaybi yasak.** 3.000 alarmin tamami islenir. Gurultu olarak elenen
   her alarm, eleme gerekcesiyle birlikte Gurultu Defteri'ne (`noise_ledger`)
   yazilir; hicbir alarm sessizce dusurulmez. Kartlara giremeyen kalan olaylar
   `INC-UNCLUSTERED` kartinda toplanir.
2. **Ornekleme yok.** `head`, `nrows`, `LIMIT` gibi kisaltmalarla calisma;
   pipeline her zaman tam veri setini okur.
3. **Determinizm.** Ayni girdi ayni ciktiyi uretmelidir. Skorlamada ve
   kumelemede rastgelelik kullanma; sozluk/kume iterasyonlarini sirali hale
   getir (`sorted`).
4. **LLM opsiyoneldir.** API anahtari olmadan da uygulama bastan sona
   calismalidir. LLM yalnizca aciklama metnini *zenginlestirir*; kok neden
   karari her zaman deterministik puanlama motorundan gelir.
5. **Sir saklanmaz.** Anahtarlar yalnizca `.env` icinde; `.env.example`
   disinda hicbir dosyaya gercek deger yazilmaz.

## Kod standartlari

- Python 3.11+. Yalnizca `pandas` + standart kutuphane zorunlu; UI icin
  `streamlit`. Agir grafik kutuphanesi (networkx vb.) yerine `src/topology.py`
  icindeki kucuk yonlu grafik uygulamasi kullanilir.
- Modul basina tek sorumluluk; `src/pipeline.py` disinda global durum yok.
- Tur ipuclari (`from __future__ import annotations`) ve `@dataclass` tercih edilir.
- Yorumlar ve kullanici metinleri **Turkce**, kod tanimlayicilari **Ingilizce**.
- Turkce metinlerde ASCII kullan (veri setinin kendisi de ASCII'dir).

## Calistirma

```bash
python -m src.verify_setup     # Faz 0 — iskelet + veri dogrulamasi
python -m src.pipeline         # Faz 1-4 — olay kartlarini uretir
streamlit run src/app.py       # Faz 5 — operator panosu
```

## Degisiklik yaparken

- Esik/agirlik degistirecegin zaman degeri `src/config.py` icinde degistir;
  modullere sabit gomme.
- Pipeline'a dokunduysan `python -m src.pipeline` calistirip kart sayisinin
  <= 15 ve islenen alarm sayisinin 3.000 oldugunu dogrula.
- Her faz sonunda `docs/fazlar.md` gunlugunu guncelle ve plandaki commit
  mesajiyla commit at.
