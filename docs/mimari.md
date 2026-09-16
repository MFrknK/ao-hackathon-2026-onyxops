# OnyxOps — Mimari

> S-A1 "Alarm Firtinasi" · 3.000 alarm -> <= 15 olay karti

## 1. Tasarim ilkeleri

| Ilke | Karsiligi |
|---|---|
| **Sifir veri kaybi** | Elenen her alarm gerekcesiyle Gurultu Defteri'ne yazilir; kart siniri disinda kalan olaylar tek bir "Diger" kartinda toplanir. Her alarm tam olarak bir yere dusgun olur. |
| **Determinizm** | Rastgelelik yok, sabit siralama var. Ayni girdi her calistirmada ayni 15 karti uretir. Juri tekrar calistirdiginda ayni sonucu gorur. |
| **Aciklanabilirlik** | Kok neden bir sinir agindan degil, agirliklari `config.py`'de acikca yazili 5 bilesenli bir puandan cikar. Her kartta puan kirilimi ve karsi hipotez bulunur. |
| **LLM opsiyonel** | Karar deterministik motordan; LLM yalnizca dogal dil anlatimini zenginlestirir. Anahtar yoksa sablon motoru devreye girer, urun bozulmaz. |

## 2. Katmanlar

```
                    data/  (alarms.csv · service_dependencies.csv · host_inventory.csv)
                      |
   Faz 1  ┌───────────▼─────────────────────────────────────────────┐
          │ data_loader.py   CSV -> Alarm nesneleri + zenginlestirme │
          │ topology.py      Yonlu bagimlilik grafigi + merkezilik   │
          └───────────┬─────────────────────────────────────────────┘
                      │  3000 zenginlestirilmis alarm + DependencyGraph
   Faz 2  ┌───────────▼─────────────────────────────────────────────┐
          │ noise_filter.py  Yalniz dusuk-siddet alarmlari -> Ledger │
          │ clustering.py    Cift pencere: burst (4dk) + slow (20dk) │
          └───────────┬─────────────────────────────────────────────┘
                      │  TemporalCluster listesi + NoiseLedger
   Faz 3  ┌───────────▼─────────────────────────────────────────────┐
          │ correlation.py   Topolojik/mekansal kume birlestirme     │
          │ root_cause.py    5 bilesenli puanlama -> kok + karsi hip.│
          └───────────┬─────────────────────────────────────────────┘
                      │  Incident listesi
   Faz 4  ┌───────────▼─────────────────────────────────────────────┐
          │ incident_cards.py  JSON sema + oncelik + 15 kart kapagi  │
          │ pipeline.py        Orkestrasyon -> output/*.json         │
          └───────────┬─────────────────────────────────────────────┘
                      │
   Faz 5  ┌───────────▼─────────────────────────────────────────────┐
          │ app.py  Streamlit: Olay Panosu · Aksiyon Takibi ·        │
          │         Gurultu Denetimi · Topoloji                      │
          └─────────────────────────────────────────────────────────┘
```

## 3. Modul sorumluluklari

| Modul | Sorumluluk |
|---|---|
| `src/config.py` | Tum yollar, esikler, agirliklar, alarm tipi onsel degerleri. Tek ayar noktasi. |
| `src/verify_setup.py` | Faz 0. Repo iskeleti + veri paketi butunlugu (3000/27/56/32). |
| `src/models.py` | `Alarm`, `TemporalCluster`, `Incident`, `NoiseEntry` veri siniflari. |
| `src/data_loader.py` | CSV okuma, `datetime` donusumu, host envanteri ile zenginlestirme. |
| `src/topology.py` | Yonlu grafik: ileri/geri komsuluk, `k`-atlama erisimi, merkezilik skorlari. |
| `src/noise_filter.py` | Yalnizlik testi + kronik-bakim tipleri -> Gurultu Defteri. |
| `src/clustering.py` | Cift pencereli zamansal kumeleme (burst + slow-burn). |
| `src/correlation.py` | Kumeleri bagimlilik/rack yakinligina gore olaylara birlestirir. |
| `src/root_cause.py` | Alarm puanlamasi, kok neden + karsi hipotez, aciklama uretimi. |
| `src/llm.py` | Opsiyonel Anthropic cagrisi; anahtar yoksa sablona duser. |
| `src/incident_cards.py` | Zorunlu JSON semasi, oncelik formulu, 15 kart kapagi ve fallback. |
| `src/pipeline.py` | Ucdan uca calistirici; `output/` altina JSON yazar, ozet basar. |
| `src/action_store.py` | Aksiyon durumu (open -> in_progress -> resolved) kalici gunlugu. |
| `src/app.py` | Streamlit panosu. |

## 4. Algoritma

### 4.1 Gurultu filtresi (Faz 2.1)

Bir alarm su kosullarin **tumunu** saglarsa gurultu isaretlenir:

- `severity <= 2`, **ve**
- ±30 dk penceresinde ayni host ve ayni serviste baska alarm yok (yalnizlik), **veya**
- tipi kronik-bakim kumesinde (`cert_expiry`, `backup_warn`, `ntp_drift`,
  `log_rotate`, `disk_warn`) ve ayni pencerede ayni serviste yuksek siddetli
  (>=3) bir alarm yok.

Elenen kayit **silinmez**; `NoiseEntry(alarm_id, reason, rule)` olarak deftere
yazilir ve panoda denetlenebilir.

### 4.2 Cift pencereli kumeleme (Faz 2.2)

Ayni servis icin alarmlar kronolojik gezilir:

- **Burst yolu** — ardisik iki alarm arasi `<= 4 dk` ise ayni kumeye eklenir.
  Ani patlamalari sikica yakalar.
- **Slow-burn yolu** — burst kumesine giremeyen alarmlar `<= 20 dk` bosluk
  toleransiyla ikinci bir gecisten gecirilir; en az 4 alarm toplayan diziler
  kume olur. Saatlere yayilan sizma tipi olaylar bu yolla yakalanir.

Her kume `window_kind = "burst" | "slow_burn"` etiketi tasir.

### 4.3 Topolojik birlestirme (Faz 3.1)

Iki kume su durumda ayni olaya baglanir:

1. **Bagimlilik yakinligi** — servisleri bagimlilik grafiginde <= 2 atlama
   mesafesindeyse ve zaman araliklari arasindaki bosluk <= 12 dk ise, **veya**
2. **Mekansal yakinlik** — ayni `veri_merkezi`+`kabin` ikilisini paylasiyor ve
   bosluk <= 6 dk ise (ortak guc/ag altyapisi varsayimi).

Birlestirme birlesim-bulma (union-find) ile gecisli olarak uygulanir.

### 4.4 Kok neden puanlamasi (Faz 3.2 / 3.3)

Olay icindeki her alarm 0-100 arasi puanlanir:

| Bilesen | Agirlik | Mantik |
|---|---|---|
| `temporal` | 35 | Olay penceresinin basina yakinlik. Once gelen neden adayidir. |
| `centrality` | 25 | Servisin grafikte kac servis tarafindan (1 ve 2 atlama) bagimli olundugu. |
| `type_prior` | 25 | Alarm tipi onseli: `network_down` 1.00 ... `timeout` 0.10. |
| `severity` | 10 | `(severity - 1) / 4`. |
| `blast` | 5 | Alarmin host/servisinin olay icindeki alarm payi. |

En yuksek puan **kok neden**, ikinci **karsi hipotez** olur. Karsi hipotez
secilirken kok nedenden farkli servis tercih edilir — ayni servisten ikinci bir
alarm "alternatif" sayilmaz.

### 4.5 15 kart kapagi (Faz 4.2)

Oncelik = `0.40·siddet + 0.35·genislik + 0.15·hacim + 0.10·is_kritikligi`
(hepsi 0-1'e normalize). En yuksek 14 olay kendi kartini alir; kalan tum
olaylar tek bir `INC-UNCLUSTERED` kartinda birlesir — boylece toplam <= 15
kalirken hicbir alarm kaybolmaz.

## 5. Cikti sozlesmesi

`output/incidents.json`:

```jsonc
{
  "generated_at": "...",
  "summary": { "total_alarms": 3000, "noise_alarms": N, "incident_cards": <=15,
               "reduction_ratio": "3000 -> 15" },
  "incidents": [{
    "incident_id": "INC-001",
    "title": "...",
    "root_cause_hypothesis": { "alarm_id", "service", "host", "alarm_type",
                               "confidence", "score_breakdown", "explanation" },
    "counter_hypothesis":    { "alarm_id", "service", "reason" },
    "affected_services": [...], "affected_hosts": [...],
    "alarm_count": N, "alarm_ids": [...],
    "time_range": { "start", "end", "duration_minutes" },
    "max_severity": 5, "priority_score": 0.0,
    "evidence": [...], "recommended_action": { "action", "owner", "status": "open" }
  }]
}
```

`output/noise_ledger.json` elenen her alarmi `reason` + `rule` ile listeler.
`output/action_log.json` aksiyon durum gecislerini zaman damgasiyla tutar.

## 6. Kullanilan kutuphaneler

| Kutuphane | Neden |
|---|---|
| `pandas` | CSV okuma ve pano tablolari. |
| `streamlit` | Operator panosu (Faz 5). |
| standart kutuphane | `csv`, `json`, `datetime`, `dataclasses`, `collections`, `itertools`. |
| `anthropic` *(ops.)* | Kok neden anlatiminin LLM ile zenginlestirilmesi. |

Bilincli olarak **kullanilmayanlar:** `networkx` (32 kenarlik grafik icin
gereksiz agirlik), `scikit-learn` (kumeleme alan mantigiyla yapiliyor, kara
kutu ile degil).
