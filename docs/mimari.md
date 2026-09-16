# OnyxOps — Mimari

> S-A1 "Alarm Firtinasi" · 3.000 alarm -> <= 15 olay karti

## 1. Tasarim ilkeleri

| Ilke | Karsiligi |
|---|---|
| **Sifir veri kaybi** | Elenen her alarm gerekcesiyle Gurultu Defteri'ne yazilir; kart siniri disinda kalan olaylar tek bir "Diger" kartinda toplanir. Her alarm tam olarak bir yere dusgun olur. |
| **Determinizm** | Rastgelelik yok, sabit siralama var. Ayni girdi her calistirmada ayni kartlari ayni sirayla uretir. Juri tekrar calistirdiginda ayni sonucu gorur. |
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
          │ baseline.py      Servis taban orani + artis pencereleri  │
          │ noise_filter.py  3 kurallik gurultu filtresi -> Ledger   │
          │ clustering.py    Burst (3dk/3x) + slow-burn (9dk/1.8x)   │
          └───────────┬─────────────────────────────────────────────┘
                      │  TemporalCluster listesi + NoiseLedger
   Faz 3  ┌───────────▼─────────────────────────────────────────────┐
          │ correlation.py   Topolojik/mekansal kume birlestirme     │
          │ root_cause.py    5 bilesenli puanlama -> kok + karsi hip.│
          │ similarity.py    Bilinen oruntu + gecmis olay eslesmesi  │
          └───────────┬─────────────────────────────────────────────┘
                      │  Incident listesi
   Faz 4  ┌───────────▼─────────────────────────────────────────────┐
          │ incident_cards.py  JSON sema + oncelik + 15 kart kapagi  │
          │ pipeline.py        Orkestrasyon -> output/*.json         │
          └───────────┬─────────────────────────────────────────────┘
                      │
   Faz 5  ┌───────────▼─────────────────────────────────────────────┐
          │ app.py  Streamlit: Olay Panosu · Aksiyon Takibi ·        │
          │         Gurultu Denetimi · Topoloji · Boru Hatti         │
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
| `src/baseline.py` | Servis taban orani + cift duyarlikli artis penceresi tespiti. |
| `src/noise_filter.py` | Uc kurallik gurultu filtresi -> Gurultu Defteri. |
| `src/clustering.py` | Cift pencereli zamansal kumeleme (burst + slow-burn). |
| `src/correlation.py` | Kumeleri bagimlilik/rack yakinligina gore olaylara birlestirir. |
| `src/root_cause.py` | Alarm puanlamasi, kok neden + karsi hipotez, aciklama uretimi. |
| `src/llm.py` | Opsiyonel Anthropic cagrisi; anahtar yoksa sablona duser. |
| `src/similarity.py` | Bilinen ariza oruntu kutuphanesi + olay imza arsivi ve benzerlik. |
| `src/incident_cards.py` | Zorunlu JSON semasi, oncelik formulu, 15 kart kapagi ve fallback. |
| `src/pipeline.py` | Ucdan uca calistirici; `output/` altina JSON yazar, ozet basar. |
| `src/action_store.py` | Aksiyon durumu (open -> in_progress -> resolved) kalici gunlugu. |
| `src/app.py` | Streamlit panosu. |

## 4. Algoritma

> Asagidaki esiklerin tamami [../src/config.py](../src/config.py) icinde tek
> noktada ve **neden o deger oldugu yazili** olarak durur.

### 4.1 Servis taban orani ve cift duyarlikli artis dedektoru (Faz 2)

Bu veri setinin belirleyici ozelligi: 27 servisin tamami 2 saat boyunca
kesintisiz alarm uretiyor (`mobile-bff` dakikada ~2.3). Bu yuzden sabit zaman
esikleri ("yalniz mi", "bosluk < 4 dk mi") hicbir sey ayirt etmiyor.

Her servis icin dakika basi alarm sayisinin **medyani** taban orani kabul
edilir (medyan patlamalardan etkilenmez). Uzerine iki dedektor kosar:

| Dedektor | Yuvarlanan pencere | Esik | Yakaladigi |
|---|---|---|---|
| `BURST` | 3 dk | taban x3.0 + 3 | Ani patlama |
| `SLOW` | 9 dk | taban x1.8 + 2 | Yavas kotulesme |

Plandaki "cift pencere" kavrami iki farkli **duyarlik** olarak uygulandi.

### 4.2 Gurultu filtresi (Faz 2.1)

Kurallar sirayla denenir; ilk eslesen kural kaydi sahiplenir.

| Kural | Kosul |
|---|---|
| `maintenance_chatter` | Tip `cert_expiry`/`backup_warn`/`ntp_drift`/`log_rotate`/`disk_warn`. Bu bes tipin zaman eksenindeki std'si 33-36 dk; 121 dakikalik pencerede duzgun dagilimin beklenen degeri 121/sqrt(12) = 34.9. Siddetten bagimsiz elenir. |
| `isolated_low_severity` | Siddet <= 2 ve ayni sunucuda +/-30 dk icinde baska alarm yok. |
| `background_baseline` | Ne burst ne slow penceresinde ve siddet <= 3. |

Siddet 4-5 alarmlar **asla** elenmez. Elenen kayit silinmez;
`NoiseEntry(alarm_id, rule, reason)` olarak deftere yazilir.

### 4.3 Zamansal kumeleme (Faz 2.2)

Gurultu ayiklandiktan sonra taban orani modeli **sinyal uzerinde yeniden**
kurulur — artis pencereleri artik olay sinirlarini cok daha keskin cizer.

1. **Burst gecisi** — her burst penceresindeki alarmlar bir kume olur
   (min 3 alarm).
2. **Slow-burn gecisi** — burst'e girmeyen alarmlar slow pencerelerinde
   kumelenir (min 4 alarm, en az bir siddet >= 3).

Kumeye giremeyen sinyal alarmlari `residual` olarak tasinir ve Faz 4'te
"Diger" kartina girer. Veri kaybi sifir.

### 4.4 Topolojik birlestirme (Faz 3.1)

Olcu **baslangic ani yakinligi**dir, aralik ortusmesi degil: slow-burn
kumeleri 20-40 dakikaya yayildigi icin ortusme testi 56 kumeyi tek olaya
cokertiyordu. Bir arizanin imzasi, bagimli servislerin *birbiri ardina
bozulmaya baslamasidir*.

1. **Bagimlilik yakinligi** — servisler grafikte <= 2 atlama mesafesinde ve
   baslangic farki <= 6 dk.
2. **Mekansal yakinlik** — ayni `veri_merkezi/kabin` ve baslangic farki
   <= 4 dk (ortak guc/ag altyapisi).

Birlestirme union-find ile gecislidir; adaylar en yakin baslangictan uzaga
dogru islenir ve **sure freni** uygulanir: olusacak olay 30 dakikayi asiyorsa
birlestirme reddedilir.

### 4.5 Kok neden puanlamasi (Faz 3.2 / 3.3)

Olay icindeki her alarm 0-100 arasi puanlanir:

| Bilesen | Agirlik | Mantik |
|---|---|---|
| `temporal` | 35 | Olay penceresinin basina yakinlik. Neden sonuctan once gelir. |
| `centrality` | 25 | Servise kac servisin (gecisli, atlama agirlikli) dayandigi. |
| `type_prior` | 25 | Olculmus alarm tipi onseli (bkz. asagi). |
| `severity` | 10 | `(severity - 1) / 4`. |
| `blast` | 5 | Alarmin servisinin olay icindeki alarm payi. |

**Onseller olcumle kalibre edildi.** Her tipin zaman eksenindeki std'si
hesaplandi; duzgun dagilim beklentisi 34.9:

| Zamanda sikismis -> neden adayi | Zamanda duzgun -> arka plan |
|---|---|
| `network_down` 0.8 -> 1.00 · `pkt_loss` 0.8 -> 0.80 · `disk_full` 1.5 -> 0.95 · `ext_unreach` 0.9 -> 0.90 | `network_flap` 32.9 -> 0.20 · `latency_high` 33.7 -> 0.10 · `mem_high` 35.9 -> 0.20 · `cpu_high` 36.5 -> 0.20 |

En yuksek puan **kok neden**; en yuksek puanli **farkli servisten** alarm
**karsi hipotez** olur (ayni servisten ikinci bir alarm operatore yeni bir yer
gostermez).

### 4.6 Kart oncelik, kalite kapisi ve 15 kart kapagi (Faz 4)

Oncelik = `0.40·siddet + 0.35·genislik + 0.15·hacim + 0.10·is_kritikligi`
(hepsi 0-1'e normalize).

**Kalite kapisi.** Bir olayin kendi kartini hak etmesi icin sunlardan en az
birini saglamasi gerekir: >= 2 servis, siddet 5, ya da kok neden tipi onseli
>= 0.5. Saglamayanlar (tek serviste kalan, kok nedeni olculen std'si ~35 dk
olan arka plan tipi olan olaylar) toplayici karta **neden alindiklari
yazilarak** tasinir.

Kapasite asilirsa kalan olaylar ve `residual` alarmlar tek bir
`INC-UNCLUSTERED` kartinda birlesir; toplam her zaman <= 15 kalir ve hicbir
alarm kaybolmaz.

### 4.7 Benzer gecmis oruntuler (X-Factor)

Iki kaynaktan eslesme uretilir ([../src/similarity.py](../src/similarity.py)):

* **Bilinen ariza oruntuleri** — alti adi konmus ariza imzasi (kabin ag
  kesintisi, disk dolmasi kaskadi, bellek sizintisi, dis saglayici kesintisi,
  baglanti havuzu tukenmesi, toplu is cakismasi). Her biri bir kok neden tipi
  kumesi, beklenen semptom zinciri ve ilk mudahale playbook'u tasir. Uyum =
  `0.55·kok_tipi + 0.30·semptom_payi + 0.15·semptom_kapsami`; esik 0.45 ve kok
  neden tipinin oruntuye ait olmasi sart.
* **Olay imza arsivi** — her calistirmanin imzalari
  `output/incident_history.json` dosyasina eklenir; sonraki calistirmalar bu
  arsivi **ve ayni calistirmadaki kardes olaylari** tarar. Benzerlik =
  `0.30·kok_tipi + 0.28·servis_jaccard + 0.24·tip_profili_kosinus +
  0.10·konum + 0.08·siddet`.

**Kok neden kapisi:** iki olay ayni kok neden tipini/ailesini ya da ayni kok
servisi paylasmiyorsa benzerlik 0 dondurulur. Yogun servisler
(`order-service`, `session-service`) neredeyse her olaya dokundugu icin salt
kume ortusmesi yaniltici eslesme uretiyordu.

*Determinizm notu:* kartin cekirdegi (kok neden, kanit, karsi hipotez,
oncelik) tamamen deterministiktir; `similar_incidents` bolumu dogasi geregi
arsivin durumuna baglidir.

## 5. Cikti sozlesmesi

`output/incidents.json`:

```jsonc
{
  "generated_at": "...",
  "summary": { "total_alarms": 3000, "noise_alarms": N, "incident_cards": <=15,
               "reduction_ratio": "3000 -> 6",
               "integrity": { "no_data_loss": true } },
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
    "evidence": [...], "recommended_action": { "action", "owner", "status": "open" },
    "similar_patterns": { "known_patterns": [...], "similar_incidents": [...] }
  }]
}
```

`output/noise_ledger.json` elenen her alarmi `reason` + `rule` ile listeler.
`output/action_log.json` aksiyon durum gecislerini zaman damgasiyla tutar.
`output/incident_history.json` calistirmalar arasi olay imza arsividir.

## 6. Kullanilan kutuphaneler

| Kutuphane | Neden |
|---|---|
| `pandas` | CSV okuma ve pano tablolari. |
| `streamlit` | Operator panosu (Faz 5). |
| standart kutuphane | `csv`, `json`, `datetime`, `dataclasses`, `collections`, `statistics`, `bisect`, `math`. |
| `anthropic` *(ops.)* | Kok neden anlatiminin LLM ile zenginlestirilmesi. |

Bilincli olarak **kullanilmayanlar:** `networkx` (32 kenarlik grafik icin
gereksiz agirlik), `scikit-learn` (kumeleme alan mantigiyla yapiliyor, kara
kutu ile degil).
