# OnyxOps — Sunum Runbook'u

> **Kura ile anlik cagriliyorsunuz. Sure kesin, ek sure yok.**
> Bu dosya slayt degil; sahnede yaninizda duracak koreografidir.
> Ekranda **urun** olsun, bu dosya ikinci ekranda/telefonda.

---

## 0. Sahneye cikmadan once (2 dakika — kura beklerken yapin)

```bash
cd ao-hackathon-2026-onyxops
python -m src.pipeline          # cikis kodu 0 gormelisiniz
streamlit run src/app.py        # http://localhost:8501
```

**Kontrol listesi:**

- [ ] Pano acik, **Olaylar & AI Hipotezleri** sekmesinde
- [ ] Tarayici tam ekran (F11), yakinlastirma **%80** (5 kart yan yana sigsin)
- [ ] `output/action_log.json` **silinmis** olsun — tum kartlar "ACIK" baslasin
      (`rm output/action_log.json` sonra sayfayi yenileyin)
- [ ] Terminal ayri bir sekmede hazir (yedek plan icin)
- [ ] Internet **gerekmiyor** — kopsa bile demo calisir

> **Yedek plan:** Pano acilmazsa `python -m src.pipeline` ciktisini terminalde
> gosterin; indirgeme ve butunluk satirlari tek basina hikayeyi anlatir.

---

## 1. Acilis — 20 saniye

> "Gece 02:14. Nobetci muhendisin ekraninda iki saatte **3.000 alarm** akiyor.
> Sorun alarm sayisi degil; hangisinin **kok neden**, hangisinin **turev
> etki**, hangisinin **tamamen alakasiz gurultu** oldugunun gorunmemesi.
> Biz bunu **5 karara** indirdik. Ekranda gordugunuz sey canli calisiyor."

**Ekran:** Ana pano, ozet serit gorunur.

Ozet seridi parmakla gosterip tek cumle:

> "3.000 alarm girdi, **2.295'i gerekceli olarak gurultu**, **705'i bes olaya**
> baglandi, **sinifllandirilamayan sifir**. Indirgeme **600 kat**."

---

## 2. Odak 1 — AI Stratejisi ve Is Akisi (45–60 saniye)

**Ekranda kalin, slayta gecmeyin.** Su uc cumleyi soyleyin:

> **1) Is bolumu.** Projeyi bastan sona **Claude Code / Opus 5** ile,
> `docs/plan.md` icindeki 7 fazlik plani sirayla yurterek gelistirdik. Her faz
> sonunda calisan kod dogrulandi ve commit atildi — git gecmisi faz faz
> okunabilir.

> **2) AI karar vermiyor, AI *aciklamayi* yaziyor.** Kok neden ve karsi
> olasilik **her zaman** deterministik bir puanlama motorundan cikiyor.
> LLM opsiyonel ve **varsayilan kapali**; teslim ciktilari LLM'siz uretildi.
> Gerekcesi su: korelasyon karari jurinin denetleyebilmesi gereken bir sey,
> bir olasilik dagilimina birakilamaz.

> **3) En degerli kisim: AI'in kendi hatasini olcumle duzeltmesi.** Uc kez
> plandan saptik, ucunde de sapmanin gerekcesi **veriden olculdu**.
> (Bir tanesini anlatin — asagidaki kutu.)

### Anlatilacak tek ornek (ezberleyin, 20 saniye)

> "Ilk calistirmada motor en buyuk olayin kok nedenini `network_flap` sandi.
> Sezgisel olarak mantikli — 'ag linki kararsiz'. Ama alarm tiplerinin zaman
> eksenindeki dagilimini olctuk: `network_flap`'in standart sapmasi **32,9
> dakika**. 121 dakikalik bir pencerede tam **duzgun** dagilimin beklenen
> degeri **34,9**. Yani bu tip olayla ilgili degil, arka plan gurultusu —
> 202 alarmi iki saate yayilmis. Buna karsilik `network_down` 0,8,
> `pkt_loss` 0,8. 26 alarm tipinin tamamini bu olcume gore yeniden kalibre
> ettik ve dogru cevap cikti."

**Kanit gostermek isterseniz:** [AI_JURI.md](../AI_JURI.md) §2 ·
[src/config.py](../src/config.py) `ALARM_TYPE_PRIOR` yorumu.

---

## 3. Odak 2 — Canli Demo (2 dakika, en uzun bolum)

Sirayi bozmayin; her adimda **tek cumle** soyleyin.

### Adim 1 — Grafik: "alarm seli artik okunabilir" (20 sn)

Ana grafigi gosterin.

> "Bu, 3.000 alarmin zaman icindeki dagilimi. Gri olan arka plan gurultusu.
> Renkli bloklarin her biri bir olay. Alarm seli burada **gozle ayrisiyor**."

**Gostergedeki 'Gurultu (Arka Plan)' yazisina tiklayin** → gri kaybolur.

> "Gurultuyu kapatiyorum. Geriye kalan sey gecenin gercek hikayesi: dort
> ayri ariza, dort ayri zaman diliminde."

Tekrar tiklayip geri acin. Bir cubugun uzerine gelin → tooltip tum serileri
gosterir.

> "Herhangi bir dakikada hangi olaydan kac alarm geldigini gorebiliyoruz."

### Adim 2 — Kart: kok neden ve **karsi olasilik** (30 sn)

**INC-002 Billing DB Disk Dolulugu** kartini gosterin.

> "Kart bize dort sey soyluyor: kok neden hipotezi, kaniti, **karsi olasiligi**
> ve ilk aksiyonu — sahibiyle birlikte."

Kok neden kutusunu okutun, sonra **karsi olasilik** satirini isaret edin:

> "Burasi onemli. Sistem 'kesin bu' demiyor. 'Puana **11,2 puan yakin** bir
> alternatif var, su sunucudaki metrikleri de kontrol et' diyor. Nobetci
> muhendise duşunme payi birakiyor."

### Adim 3 — **(193 Alarm)** dugmesi: kanita inme (25 sn)

Kart basligindaki mavi **(193 Alarm)** dugmesine basin → terminal log acilir.

> "Ve hicbir sey kara kutu degil. Alarm sayisina basiyorum — bu kartin
> arkasindaki **ham alarm akisi**. Muhendis hipotezi kabul etmek zorunda
> degil, kayitlari tek tek dogrulayabilir."

Kapatin.

### Adim 4 — Aksiyon takibi (20 sn)

Kartin altindaki **Durum: ACIK** menusunden **UZERINDE CALISILIYOR** secin.

> "Aksiyon acildi, sahibi DBA ekibi. Durumu degistiriyorum..."

Sayfa yenilenir, rozet sarıya doner.

> "...zaman damgasiyla diske yazildi. Sayfayi yenilesem de kalici. Aksiyon
> acilistan kapanisa kadar **izlenebilir**."

### Adim 5 — Denetim gorunumu (25 sn)

**Denetim Gorunumu (Audit Log)** sekmesine gecin.

> "Peki eledigimiz 2.295 alarm? **Hicbiri silinmedi.** Her biri, **hangi
> kuralla ve neden** elendigi yazili olarak burada."

Bir satiri isaret edin (`maintenance_chatter` olan).

> "Ornegin bu: 'Disk kullanimi yuzde 29 dolu' — siddeti 4 ama bu bir olay
> degil. Bakim ciriltisi oldugunu **olcerek** soyluyoruz, tahmin ederek degil."

### Adim 6 — Butunluk (10 sn)

**Boru Hatti** sekmesi, yesil kutu.

> "Ve matematik tutuyor: **705 + 2.295 = 3.000**. Tek bir alarm bile
> kaybolmadi. Tutmazsa program hata koduyla cikiyor."

---

## 4. Odak 3 — X-Factor (40 saniye)

**Olaylar sekmesine donun**, INC-004 veya INC-005 kartinda
**Kanitlar · puan kirilimi · benzer olaylar** panelini acin.

### Soylenecek (en carpici olan bu — vurgulayin)

> "Asil sihir burada. Sistem urettigi her olayin **imzasini arsivliyor** ve
> yeni olaylari hem bu arsivle hem de birbiriyle karsilastiriyor."

**Benzer olaylar** satirini gosterin (INC-004 kartinda).

> "Bu iki kart birbirinden bagimsiz uretildi — biri 03:09'da, digeri 03:24'te.
> Ama motor diyor ki: '**%92 benzer** — ayni kok neden tipi, ayni kok servis,
> alarm tipi profili neredeyse ayni.' Yani iki ayri pencerede yasanmis
> **tekrar eden bir arizayi** sistem kendisi fark etti ve birbirine bagladi.
> Nobetci muhendis bunu gorunce 'bu havuz ikinci kez tukendi, gecici cozum
> yetmiyor' diyebilir."

Sonra ustteki **Gecmis Oruntu** cipini gosterin:

> "Ustelik her kart bilinen bir ariza imzasiyla eslesiyor — INC-003 icin
> '**Dis saglayici kesintisi, %94 uyum**' — ve yaninda **ilk mudahale
> playbook'u** geliyor. Yani sistem sadece 'burada bir sorun var' demiyor;
> '**bunu daha once gorduk, su adimlari izle**' diyor."

### Yedek X-Factor cumlesi (sure kalirsa)

> "Bir de sunu ekleyeyim: benzerlik motorunun ilk surumu yanlis calisiyordu.
> Sadece ortak servise bakinca ag kesintisi ile bellek sizintisi 'benzer'
> cikiyordu, cunku bu sistemde `order-service` zaten her olaya dokunuyor.
> Bir **kok neden kapisi** ekledik: ortak servis tek basina benzerlik
> sayilmaz. Sekiz sahte eslesme elendi, anlamli olan tek cift kaldi."

---

## 5. Kapanis — 15 saniye

> "Ozetle: 3.000 alarm → **5 karar**, %76 gurultu **gerekceli** olarak elendi,
> sifir veri kaybi, her hipotezin arkasinda ham kayit var ve her kart bir
> playbook'la geliyor. Motor **0,08 saniyede** calisiyor ve **deterministik** —
> tekrar calistirdiginizda ayni bes karti ayni sirayla gorursunuz.
> Tesekkurler."

---

## 6. Sure planlari

| Bolum | 5 dk | 3 dk (kisa) |
|---|---|---|
| Acilis | 20 sn | 15 sn |
| Odak 1 — AI stratejisi | 60 sn | 30 sn (sadece "AI karar vermez" + olcum ornegi) |
| Odak 2 — Canli demo | 120 sn | 90 sn (Adim 1-2-3-5, aksiyon ve butunlugu atla) |
| Odak 3 — X-Factor | 40 sn | 30 sn (sadece benzer olay eslesmesi) |
| Kapanis | 15 sn | 15 sn |

**Sure daralirsa ilk feda edilecekler:** Adim 4 (aksiyon takibi) ve Adim 6
(butunluk). **Asla feda etmeyin:** Adim 3 (ham log — "kara kutu degil" mesaji)
ve Odak 3.

---

## 7. Muhtemel juri sorulari ve durust cevaplar

**"Kac gercek olay vardi, hepsini yakaladiniz mi?"**
> Dogrulama verisi bizde yok. Veriden **dort belirgin ariza penceresi** ve
> bunlarin bir tanesinin iki evresi cikti. Kartlarin kok nedenleri veriyle
> tutarli: rack-A'da yogunlasan paket kaybi, billing-db'de disk dolmasi, dis
> odeme saglayicisinda erisilemezlik, abone veritabaninda havuz tukenmesi.

**"Neden 15 degil de 5 kart?"**
> Kalite kapisi koyduk: bir olayin kendi kartini hak etmesi icin en az 10
> alarm, ya birden fazla servis ya kritik siddet ya da kok nedeninin gercek
> bir "neden" tipi olmasi gerekiyor. Gecemeyen kayitlar silinmiyor, gerekcesi
> yazilarak deftere gidiyor. Bos kart uretmektense az ve saglam kart urettik.

**"LLM olmadan bu AI projesi sayilir mi?"**
> AI'i iki yerde kullandik: **gelistirme surecinin tamaminda** (Claude Code
> ile veri kesfi, algoritma tasarimi, kalibrasyon) ve **urun icinde opsiyonel
> aciklama zenginlestirmesi** olarak. Korelasyon kararini bilincli olarak
> deterministik tuttuk cunku denetlenebilir olmasi gerekiyordu. Bu bir
> eksiklik degil, tasarim karari — ve `ONYXOPS_USE_LLM=true` ile aciklamalar
> aninda LLM'e devrediliyor.

**"Yanlis birlestirme yaptiniz mi?"**
> Riskli oldugunu bildigimiz iki yer var ve ikisini de olcerek sinirladik:
> birlestirme olcusunu aralik ortusmesinden **baslangic ani yakinligina**
> cevirdik, ustune gecisli birlesmeye **sure freni** koyduk. Ilk denemede
> 56 kume tek olaya cokmustu; bu iki degisiklikle ayristi.

**"Test yazdiniz mi?"**
> Birim testi yok — bunu durustce soyleyelim. Bunun yerine her calistirmada
> kosan **bir butunluk invarianti** var: kart alarmlari + gurultu defteri
> 3.000'e esit olmali ve alarm kimlikleri benzersiz olmali; tutmazsa program
> hata koduyla cikiyor. Ayrica `python -m src.verify_setup` veri paketi ve
> repo iskeleti icin 23 kontrol kosuyor.

**"Gercek zamanli calisir mi?"**
> Boru hatti toplu okuma icin yazildi (senaryonun kapsam disi maddesi), ama
> 3.000 alarmi **0,08 saniyede** isliyor. Kayan pencere ile akisa uyarlamak
> mimari bir degisiklik gerektirmez.

---

## 8. Sahnede soylenmeyecekler

- "Sanirim", "galiba", "tam bitiremedik" — kesin konusun, urun calisiyor.
- Kod satiri okumak — juri kodu sonra inceleyecek, sahnede **urun** gorsun.
- Mimari detay anlatmak (baseline medyani, union-find...) — **sorulursa**
  anlatin, kendiliginden girmeyin.
- Ekran goruntusu gostermek — **canli urun** varken asla.
