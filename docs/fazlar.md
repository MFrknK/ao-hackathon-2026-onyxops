# OnyxOps — Faz Gunlugu

Plan: [plan.md](plan.md) · Mimari: [mimari.md](mimari.md) · Juri: [../AI_JURI.md](../AI_JURI.md)

| Faz | Baslik | Durum | Commit |
|---|---|---|---|
| 0 | Iskelet kurulumu ve veri dogrulama | tamam | `chore: proje iskeleti kuruldu ve veri boyutlari dogrulandi` |
| 1 | Veri katmani ve topoloji agaci | tamam | `feat: veri yukleyici, zenginlestirme ve yonlu bagimlilik grafikleri eklendi` |
| 2 | Gurultu filtreleme ve zamansal kumeleme | tamam | `feat: cift pencereli zamansal kumeleme ve gurultu on-filtresi uygulandi` |
| 3 | Topolojik birlestirme ve kok neden puanlamasi | tamam | `feat: topoloji tabanli olay birlestirme ve kok neden puanlama motoru entegre edildi` |
| 4 | Olay karti uretimi ve 15 kart kapagi | tamam | `feat: json olay kartlari uretildi ve 15 kayit siniri (fallback ile) uygulandi` |
| 5 | Pano, aksiyon takibi, gurultu denetimi | tamam | `feat: interaktif olay panosu, aksiyon takibi ve gurultu denetim ekrani kodlandi` |
| 6 | Juri hazirligi ve belgeleme | tamam | `docs: AI_JURI.md, submission.json ve README.md tamamlandi, demo gorselleri eklendi` |

---

## Faz 0 — Iskelet kurulumu ve veri dogrulama

**Gorev 0.1.** Teslim listesi (`README.md`, `AI_JURI.md`, `submission.json`,
`.env.example`, `CLAUDE.md`, `docs/`, `src/`, `prompts/`, `demo/`) kontrol
edildi; bos gelen zorunlu dosyalar dolduruldu. `src/config.py` tum yollarin ve
esiklerin tek kaynagi olarak olusturuldu.

**Gorev 0.2.** `src/verify_setup.py` yazildi — satir sayilarinin yaninda
butunluk kontrolleri de yapiyor: 3000/27/56/32 sayilari, `alarm_id`
benzersizligi, host/servis capraz eslesmesi, `severity` araligi, gozlem
penceresi ve `alarms.json` ile `alarms.csv` esitligi.

**Dogrulama:** `python -m src.verify_setup` -> **23/23 kontrol gecti.**

**Not.** Veri 03:30:20'ye kadar uzaniyor; belgelenen pencere 01:30-03:30. 5
dakikalik tolerans (`OBSERVATION_WINDOW_TOLERANCE_MIN`) tanimlandi.

---

## Faz 1 — Veri katmani ve topoloji agaci

- **1.1** `host_inventory.csv` -> `host -> HostInfo` haritasi ([src/data_loader.py](../src/data_loader.py)).
- **1.2** `service_dependencies.csv` -> yonlu grafik ([src/topology.py](../src/topology.py)).
  32 kenarlik bir grafik icin `networkx` tasimak yerine ihtiyac duyulan dort
  islem (ileri/geri komsuluk, k-atlama erisimi, yonsuz mesafe, merkezilik)
  dogrudan yazildi.
- **1.3** 3.000 alarm okundu, `timestamp` -> `datetime`, envanterden
  zenginlestirme yapildi, kronolojik siralandi.

**Dogrulama:** `python -m src.data_loader` -> 3000 alarm / 56 host / 27 servis
/ 32 kenar; **celiski uyarisi yok** (alarm etiketleri envanterle birebir
tutuyor). En merkezi servis `cache-cluster` (1.000), ardindan `subscriber-db`
(0.900) ve `dns-resolver` (0.850).

---

## Faz 2 — Gurultu filtreleme ve zamansal kumeleme

### Plandan sapma ve gerekcesi

Plandaki Gorev 2.1 kurali ("+/-30 dk icinde ayni sunucuda baska alarmi olmayan
dusuk siddetli kayitlar") veri kesfinde **sifir alarm eledi**: 27 servisin
tamami 2 saat boyunca kesintisiz alarm uretiyor, `mobile-bff` dakikada ~2.3.
Ayni sebeple sabit "bosluk < 4 dk" kumelemesi de tum pencereyi tek kumeye
cokertiyordu.

Bunun yerine **servis bazli taban orani** modeli kuruldu
([src/baseline.py](../src/baseline.py)): her servisin dakika basi alarm
medyani olculuyor, o oranin uzerine cikan artis pencereleri tespit ediliyor.
Plandaki "cift pencere" kavrami iki farkli **duyarlikta dedektor** olarak
yorumlandi:

| Dedektor | Pencere | Esik | Yakaladigi |
|---|---|---|---|
| `BURST` | 3 dk | taban x3 + 3 | Ani patlama (rack-A ag kesintisi, disk dolmasi) |
| `SLOW`  | 9 dk | taban x1.8 + 2 | Yavas kotulesme (session-service bellek sizintisi) |

### Gorev 2.1 — Gurultu filtresi (3 kural)

| Kural | Adet | Mantik |
|---|---|---|
| `maintenance_chatter` | 975 | `cert_expiry`, `backup_warn`, `ntp_drift`, `log_rotate`, `disk_warn` — zamanda std ~34 dk (= duzgun dagilim beklentisi 34.9). Mesajlar da aksiyon gerektirmiyor ("Disk kullanimi yuzde 29 dolu", siddet 4). |
| `isolated_low_severity` | 0 | Plandaki asil kural; dogrulugu icin korundu. |
| `background_baseline` | 362 | Servis hicbir artis penceresinde degil ve siddet <= 3. |

Siddet 4-5 alarmlar asla elenmez; kumelenemezlerse "Diger" kartina artik
olarak duser. Elenen her kayit gerekcesiyle Gurultu Defteri'ne yazilir.

**Sonuc:** 1.337 gurultu (%44.6), 1.663 sinyal.

### Gorev 2.2 — Cift pencereli kumeleme

**Sonuc:** 56 kume (25 burst + 31 slow-burn), 1.431 alarm kumelendi, 232 artik.
Denge kontrolu: 1431 + 232 = 1663 ✔

---

## Faz 3 — Topolojik birlestirme ve kok neden puanlamasi

### Gorev 3.1 — Birlestirme (iki duzeltme gerektirdi)

**Ilk deneme: 56 kume -> 1 olay.** Aralik ortusmesine bakan union-find, 20-40
dakikaya yayilan slow-burn kumeleri yuzunden her seyi zincirledi.

**Duzeltme.** Olcu **baslangic ani yakinligina** cevrildi (bir arizanin imzasi,
bagimli servislerin birbiri ardina bozulmaya baslamasidir) ve gecisli
birlesmeye bir **sure freni** eklendi (`INCIDENT_MAX_SPAN_MIN`). Adaylar en
yakin baslangictan uzaga dogru islenir; boylece en guclu baglar once kurulur.

Parametre taramasi yapildi:

| span / onset | Olay sayisi | Not |
|---|---|---|
| 60 / 10 | 4 | Ana olaylar birbirine karisiyor |
| 40 / 8 | 7 | — |
| **30 / 6** | **11** | **Secilen** — ana olaylar butun, ayrik olaylar ayri |
| 25 / 5 | 16 | 01:35 olayini yanlis yere boluyor |

### Gorev 3.2 / 3.3 — Kok neden (onseller yeniden kalibre edildi)

Ilk calistirmada en buyuk olayin kok nedeni `network_flap` secildi. Olcum bunun
yanlis oldugunu gosterdi: bu tipin zaman eksenindeki std'si **32.9 dk**, yani
121 dakikalik pencerede duzgun dagilim (34.9) demek — 202 alarmi iki saate
yayilmis arka plan.

26 alarm tipinin tamami bu olcume gore yeniden kalibre edildi
([src/config.py](../src/config.py) `ALARM_TYPE_PRIOR`):

| Zamanda sikismis -> onsel yukseltildi | Zamanda duzgun -> onsel dusuruldu |
|---|---|
| `network_down` (std 0.8) 1.00 · `pkt_loss` (0.8) 0.80 · `disk_full` (1.5) 0.95 · `ext_unreach` (0.9) 0.90 | `network_flap` (32.9) 0.85 -> **0.20** · `mem_high` (35.9) 0.60 -> **0.20** · `cpu_high` (36.5) 0.55 -> **0.20** |

**Duzeltmeden sonra:** INC-001'in kok nedeni `network_down`, INC-002'nin
`disk_full` oldu — veriyle uyumlu sonuclar.

Karsi hipotez, tercihen **farkli bir servisten** en yuksek puanli alarm olarak
secilir; ayni servisten ikinci bir alarm operatore yeni bir yer gostermez.

---

## Faz 4 — Olay karti uretimi ve 15 kart kapagi

**Gorev 4.1.** Zorunlu JSON semasi + `status: "open"` + sahip
([src/incident_cards.py](../src/incident_cards.py)).

**Gorev 4.2.** Oncelik = `0.40·siddet + 0.35·genislik + 0.15·hacim +
0.10·is_kritikligi`. Kapasite asilirsa fazlasi tek toplayici karta girer.

**Ek: kalite kapisi.** Ilk calistirmada 12 kart cikti ama 7'si tek servisli,
kok nedeni `cpu_high`/`network_flap`/`mem_high` (yani olculen std'si ~35 dk
olan arka plan tipleri) olan zayif kartlardi. Bir olayin kendi kartini
hak etmesi icin su uclerden birini saglamasi sarti kondu: >= 2 servis, siddet
5, veya kok neden tipi onseli >= 0.5. Elenenler toplayici karta **neden
elendikleri yazilarak** tasiniyor — silinmiyor.

**Sonuc:** 3000 -> **6 kart** (500x). Butunluk: 1663 + 1337 = 3000 ✔

---

## Faz 5 — Pano, aksiyon takibi, gurultu denetimi

[src/app.py](../src/app.py) — 5 sekme: Olay Panosu, Aksiyon Takibi, Gurultu
Denetimi, Topoloji, Boru Hatti. Aksiyon durumu
([src/action_store.py](../src/action_store.py)) `output/action_log.json`
dosyasinda kalici tutulur; motor yeniden calissa bile operatorun kapattigi
aksiyon yeniden acilmaz.

**Dogrulama.** Streamlit `AppTest` ile kosuldu: **0 exception**, 5 sekme, 44
metrik, 6 tablo render oluyor. Durum degisikligi test edildi:
`open -> in_progress` gecisi zaman damgasiyla diske yazildi ve okundu.
Kullanimdan kalkan `use_container_width` cagrilari `width="stretch"` ile
degistirildi.

---

## Faz 6 — Juri hazirligi ve belgeleme

- [AI_JURI.md](../AI_JURI.md) — sonuclar, AI is akisi, AI'nin kendi hatasini
  olcumle duzelttigi uc nokta, X-Factor, kanit dosya yollari.
- [src/capture_demo.py](../src/capture_demo.py) — Playwright ile 10 ekran
  goruntusu; sekmelerde geziyor ve bir aksiyonun durumunu **canli**
  degistirerek izlenebilirligi belgeliyor. Tekrar uretilebilir.
- [README.md](../README.md) — kurulum, sonuc tablosu, ekran goruntuleri,
  kullanilan AI araclari ve kutuphaneler.
- [submission.json](../submission.json) — olculen tum sonuclar.

### Git gecmisi duzeltmesi

Calisma sirasinda ortamda commit komutlari tekrar calistigi icin iki commit
ikizlendi ve `--amend` sonrasi yerel gecmis `origin/main` ile ayristi. Icerik
ayni oldugu dogrulandiktan sonra (`tree a2e9d43` her iki tarafta da ayni)
gecmis `0ae620d` uzerine yeniden kuruldu ve `--force-with-lease` ile
gonderildi. Kaybolan icerik yok.
