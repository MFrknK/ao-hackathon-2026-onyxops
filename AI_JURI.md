# AI_JURI.md — OnyxOps

> **S-A1 "Alarm Firtinasi"** · AO Hackathon 2026
> 3.000 alarm -> **6 olay karti** (ust sinir 15) · indirgeme **500x** · veri kaybi **sifir**

---

## 1. Sonuc ozeti

| Olcut | Deger | Kanit |
|---|---|---|
| Islenen alarm | **3.000 / 3.000** (ornekleme yok) | [output/incidents.json](output/incidents.json) `summary.total_alarms` |
| Uretilen kart | **6** (5 olay + 1 toplayici) | `summary.incident_cards` |
| Indirgeme orani | **500x** (3000 -> 6) | `summary.reduction_factor` |
| Elenen gurultu | **1.337** (%44.6), tamami gerekceli | [output/noise_ledger.json](output/noise_ledger.json) |
| Tespit edilen olay | 11 (5'i kendi kartini aldi) | `summary.incidents_detected` |
| Veri butunlugu | 1663 (kart) + 1337 (gurultu) = **3000** | `summary.integrity.no_data_loss: true` |
| Calisma suresi | **0.11 sn** | `summary.runtime_seconds` |

Uretilen kartlar:

| Kart | Alarm | Servis | Kok neden hipotezi | Guven |
|---|---|---|---|---|
| INC-001 | 543 | 14 | `dns-resolver` / **network_down** (dc1/rack-A ag kesintisi) | 0.79 |
| INC-002 | 321 | 7 | `billing-db` / **disk_full** | 0.80 |
| INC-003 | 330 | 6 | `session-service` / **oom_risk** (bellek sizintisi) | 0.76 |
| INC-004 | 124 | 3 | `subscriber-db` / **db_conn_pool** | 0.73 |
| INC-005 | 18 | 1 | `session-service` / **gc_pressure** (sizintinin erken evresi) | 0.76 |
| INC-UNCLUSTERED | 327 | 23 | — (kalan olaylar + artik sinyal, veri kaybi yok) | — |

---

## 2. AI is akisi

Proje bastan sona **Claude Code (Opus 5)** ile, `docs/plan.md` icindeki 7 fazlik plan
sirayla yurutulerek gelistirildi. Her fazin sonunda calisan kod dogrulandi ve
plandaki commit mesajiyla commit atildi.

### Insan / AI is bolumu

| Faz | AI ne yapti | Insan denetimi |
|---|---|---|
| 0 | Iskelet kontrolu + veri dogrulama script'i ([src/verify_setup.py](src/verify_setup.py)) | Beklenen sayilar (3000/27/56/32) plandan verildi |
| 1 | Yukleyici, zenginlestirme, yonlu grafik | — |
| 2 | Gurultu filtresi + kumeleme | **Yonlendirme degisti** (asagida) |
| 3 | Topolojik birlestirme + kok neden motoru | **Iki kez duzeltildi** (asagida) |
| 4 | Kart semasi + 15 kart kapagi + kalite kapisi | — |
| 5 | Streamlit panosu, aksiyon takibi | Canli calistirma + AppTest ile dogrulama |
| 6 | Belgeleme, ekran goruntuleri | Bu dosya |

### AI'nin kendi hatasini olcumle duzelttigi uc nokta

Bu bolum, cozumun "prompt yazdik, cikti aldik" olmadigini gostermek icin
kasitli olarak ayrintili:

**(a) Plandaki gurultu kurali veriyle celisti.**
Plan (Gorev 2.1) "±30 dk icinde ayni sunucuda baska alarmi olmayan dusuk
siddetli kayitlar" diyordu. Veri kesfi bu kuralin **sifir alarm eleyecegini**
gosterdi: 27 servisin tamami 2 saat boyunca kesintisiz alarm uretiyor
(`mobile-bff` dakikada ~2.3). Kural korundu ama yanina olcume dayali iki kural
eklendi. Bkz. [src/noise_filter.py](src/noise_filter.py).

**(b) Sabit zaman penceresi tum veriyi tek kumeye cokertiyordu.**
"Bosluk <= 4 dk ise ayni kume" mantigi, surekli akan bir servisde 2 saatlik
pencerenin tamamini tek kumeye baglar. Bunun yerine her servisin **kendi taban
orani** (dakika basi alarm medyani) olculup, o oranin uzerine cikan artis
pencereleri tespit edildi. Plandaki "cift pencere" kavrami buna gore
yorumlandi: iki farkli **duyarlikta** dedektor (3 dk/3x = burst, 9 dk/1.8x =
slow-burn). Bkz. [src/baseline.py](src/baseline.py).

**(c) Kok neden onselleri sezgiseldi ve yanlis cevap uretti.**
Ilk kalibrasyonda `network_flap` 0.85 onseline sahipti ve en buyuk olayda kok
neden secildi. Olcum bunun hatali oldugunu gosterdi: `network_flap`'in zaman
eksenindeki standart sapmasi **32.9 dk**; 121 dakikalik pencerede tam duzgun
dagilimin beklenen degeri **121/sqrt(12) = 34.9**. Yani bu tip olaylarla
iliskisiz arka plan. Tum 26 alarm tipi bu olcumle yeniden kalibre edildi;
`network_flap`/`mem_high`/`cpu_high` dusuruldu, `network_down` (std 0.8) /
`pkt_loss` (0.8) / `disk_full` (1.5) one cikarildi. Duzeltmeden sonra INC-001'in
kok nedeni `network_flap` yerine **`network_down`** oldu — veriyle uyumlu
sonuc. Olcum tablosu [src/config.py](src/config.py) `ALARM_TYPE_PRIOR` yorumunda.

### LLM'in **karar vermedigi** nokta

Kok neden ve karsi hipotez **her zaman** deterministik puanlama motorundan
cikar ([src/root_cause.py](src/root_cause.py)). LLM yalnizca bu kararin dogal
dil anlatimini zenginlestirir ve tamamen opsiyoneldir
([src/llm.py](src/llm.py), prompt: [prompts/root_cause_explanation.md](prompts/root_cause_explanation.md)).
API anahtari olmadan urun bastan sona calisir — teslim edilen ciktilar sablon
motoruyla uretilmistir. Gerekce: korelasyon karari juri tarafindan denetlenmek
zorunda; bir olasilik dagitimina birakilamaz.

---

## 3. Kullanilan AI araclari ve MCP sunuculari

| Arac | Surum / model | Kullanim |
|---|---|---|
| Claude Code | Opus 5 (1M context) | Tum gelistirme, veri kesfi, hata ayiklama |
| Anthropic API | `claude-sonnet-5` (opsiyonel) | Kok neden anlatiminin zenginlestirilmesi — varsayilan **kapali** |

**MCP sunuculari:** Bu projede MCP sunucusu kullanilmamistir. Tum veri yerel
CSV dosyalarindan okunur; harici sistem erisimi yoktur.

**AI yapilandirma dosyasi:** [CLAUDE.md](CLAUDE.md) — ajanin uymasi gereken
kurallar (veri kaybi yasagi, ornekleme yasagi, determinizm, LLM opsiyonelligi).

---

## 4. X-Factor

### 4.1 Kok neden aciklamasi + karsi hipotez
Her kartta kok nedenin **neden** o oldugunu anlatan dogal dil metni ve
5 bilesenli **puan kirilimi** var. Ayrica her kart bir **karsi hipotez**
tasiyor: farkli bir servisten en yuksek puanli alternatif, puan farki ve
"neden hala masada" gerekcesiyle. Ayni servisten ikinci bir alarm alternatif
sayilmaz — karsi hipotezin degeri operatore *baska bir yere* bakmayi
onermesindedir.
Kod: [src/root_cause.py](src/root_cause.py) · Ekran: [demo/03-kok-neden.png](demo/03-kok-neden.png)

### 4.2 Gurultu denetim gorunumu
Elenen 1.337 alarmin **tamami** silinmeden, hangi kuralla ve neden elendigi
yazili olarak Gurultu Defteri'nde. Panoda kural/siddet/servis/metin filtresiyle
denetlenebiliyor.
Kod: [src/noise_filter.py](src/noise_filter.py) · Cikti: [output/noise_ledger.json](output/noise_ledger.json)
· Ekran: [demo/04-gurultu-denetimi.png](demo/04-gurultu-denetimi.png)

### 4.3 Izlenebilir aksiyon (opsiyonel gereksinim)
Her kartin aksiyonu sahip + durum ile kayit altinda. Durum panodan
`Acik -> Uzerinde calisiliyor -> Cozuldu` seklinde degistiriliyor; her gecis
zaman damgasi ve sahiple `output/action_log.json` dosyasina yaziliyor ve sayfa
yenilense de korunuyor.
Kod: [src/action_store.py](src/action_store.py) · Ekran: [demo/05-aksiyon-takibi.png](demo/05-aksiyon-takibi.png)

### 4.4 Denetlenebilir veri butunlugu
Pipeline her calistirmada `kart alarmlari + gurultu defteri == 3000` esitligini
ve alarm kimliklerinin benzersizligini dogrular; tutmazsa **cikis kodu 1**
verir. Panoda da ayri bir "Boru Hatti" sekmesinde gosterilir.
Kod: [src/pipeline.py](src/pipeline.py) · Ekran: [demo/06-boru-hatti.png](demo/06-boru-hatti.png)

### 4.5 Olculmus, sezgisel olmayan parametreler
Alarm tipi onselleri ve gurultu kurallari veri uzerinde yapilan zamansal
dagilim olcumune dayaniyor (bkz. 2c). Her esik [src/config.py](src/config.py)
icinde tek noktada ve **neden o deger oldugu yazili** olarak duruyor.

---

## 5. Kanit dosya yollari

### Boru hatti (Faz sirasiyla)
| Faz | Dosya | Icerik |
|---|---|---|
| 0 | [src/verify_setup.py](src/verify_setup.py) | Iskelet + veri butunlugu dogrulamasi (23 kontrol) |
| 0 | [src/config.py](src/config.py) | Tum esikler, agirliklar, olculmus onseller — tek ayar noktasi |
| 1 | [src/models.py](src/models.py) | `Alarm`, `TemporalCluster`, `Incident`, `NoiseEntry` |
| 1 | [src/data_loader.py](src/data_loader.py) | CSV okuma, datetime donusumu, envanter zenginlestirmesi |
| 1 | [src/topology.py](src/topology.py) | Yonlu bagimlilik grafigi, etki kumesi, merkezilik |
| 2 | [src/baseline.py](src/baseline.py) | Servis taban orani + cift duyarlikli artis dedektoru |
| 2 | [src/noise_filter.py](src/noise_filter.py) | 3 kurallik gurultu filtresi + Gurultu Defteri |
| 2 | [src/clustering.py](src/clustering.py) | Cift pencereli zamansal kumeleme |
| 3 | [src/correlation.py](src/correlation.py) | Sure frenli union-find ile topolojik birlestirme |
| 3 | [src/root_cause.py](src/root_cause.py) | 5 bilesenli puanlama, karsi hipotez, kanit, aksiyon |
| 3 | [src/llm.py](src/llm.py) | Opsiyonel LLM zenginlestirmesi (karar vermez) |
| 4 | [src/incident_cards.py](src/incident_cards.py) | JSON sema, oncelik formulu, kalite kapisi, 15 kart kapagi |
| 4 | [src/pipeline.py](src/pipeline.py) | Uctan uca calistirici + butunluk dogrulamasi |
| 5 | [src/action_store.py](src/action_store.py) | Aksiyon durum makinesi ve kalici gunluk |
| 5 | [src/app.py](src/app.py) | 5 sekmeli Streamlit operator panosu |

### Ciktilar
- [output/incidents.json](output/incidents.json) — 6 kart + ozet + butunluk kaniti
- [output/noise_ledger.json](output/noise_ledger.json) — elenen 1.337 alarm, gerekceli
- [output/action_log.json](output/action_log.json) — aksiyon durum gecisleri
- [output/topology.json](output/topology.json) — grafik ve merkezilik degerleri

### Belgeler
- [docs/plan.md](docs/plan.md) — faz plani
- [docs/mimari.md](docs/mimari.md) — mimari, algoritmalar, cikti sozlesmesi
- [docs/fazlar.md](docs/fazlar.md) — faz gunlugu, her fazda ne yapildigi
- [prompts/root_cause_explanation.md](prompts/root_cause_explanation.md) — LLM prompt'u
- [CLAUDE.md](CLAUDE.md) — AI ajan yapilandirmasi

---

## 6. Yeniden uretilebilirlik

```bash
python -m pip install -r requirements.txt
python -m src.verify_setup     # 23 kontrol -> hepsi gecmeli
python -m src.pipeline         # 3000 -> 6 kart, cikis kodu 0
streamlit run src/app.py       # pano
```

Boru hatti **deterministiktir**: rastgelelik yok, tum sozluk/kume iterasyonlari
sirali. Ayni girdi her calistirmada ayni 6 karti ayni sirayla uretir. Juri
tekrar calistirdiginda bu belgedeki sayilarin aynisini gorur.
