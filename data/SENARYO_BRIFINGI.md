# S-A1 — ALARM FIRTINASI
### AO Hackathon 2026 · Senaryo Brifingi · Teslim saati 17:30

---

## Sahne

Eylül ayının bir gecesi, saat 02 : 14. Operasyon merkezindeki alarm ekranı
sessizce akmaya başlar, sonra hızlanır. Farklı izleme sistemlerinden, farklı
servislerden, farklı şiddetlerde alarmlar birbirini kovalar. Nöbetçi mühendis
ekrana baktığında iki saatlik pencerede binlerce satır görür.

O gece birden fazla şey aynı anda ters gitmiştir. Bazıları birbiriyle
ilişkilidir, bazıları tamamen bağımsızdır; alarm ekranında hepsi yan yana
akmaktadır.

## Çözülmesi beklenen problem

Nöbetçi mühendisin karşılaştığı asıl güçlük alarm sayısı değil, alarmlar
arasındaki neden-sonuç ilişkisinin görünmez olmasıdır. Hangi alarmın kök neden,
hangisinin türev etki, hangisinin ise tamamen alakasız gürültü olduğu ayırt
edilemediği için müdahale sırası yanlış kurulur ve çözüm süresi uzar.

**Göreviniz:** Alarm selini, nöbetçi mühendisin okuyup harekete geçebileceği
birkaç karara indirgemek ve bu indirgemenin gerekçesini gösterebilmek.

---

## Zorunlu gereksinimler

1. Verilen alarm akışının **tamamını** okuyup işleyebilmek. Kısmi veri ile
   çalışan çözümler eksik sayılır.
2. Alarmları anlamlı gruplara indirgemek ve her grup için **tek bir olay kartı**
   üretmek.
3. Her olay kartında kök neden hipotezi, etkilenen servis listesi, alarm sayısı
   ve zaman aralığını göstermek.
4. Her kart için önerilen ilk aksiyonu üretmek ve bu aksiyonu **sahip ile durum
   bilgisi** içerecek şekilde kayıt altına almak.
5. *(Opsiyonel)* Bir aksiyonun açıldıktan sonra kapanana kadar **izlenebildiğini**
   demoda göstermek. Yapılması durumunda çözümünüze güç katar.

## Bonus gereksinimler (X-Factor alanı)

- Kök neden hipotezinin neden bu olduğunu doğal dille açıklamak ve **karşı
  olasılıkları** da belirtmek.
- Gürültü olarak elenen alarmların **neden elendiğini** gösteren bir denetim
  görünümü sunmak.
- Benzer geçmiş olay örüntülerini yakalayıp kartın üzerine iliştirmek.

## Kapsam dışı

- Gerçek zamanlı akış işleme altyapısı kurmak gerekli değildir; dosyayı toplu
  okumak yeterlidir.
- Kullanıcı yönetimi, oturum açma ve yetkilendirme beklenmemektedir.
- Kalıcı veritabanı zorunlu değildir; bellek içi saklama kabul edilir.

---

## Kabul kriterleri (kendi kendinizi denetleyin)

- [ ] Uygulama, verilen veri paketiyle sıfırdan ayağa kalkıp sonuç üretiyor
- [ ] 3.000 alarm, en fazla on beş olay kartına indirgenmiş durumda
- [ ] *(Opsiyonel)* En az bir aksiyon demo sırasında açılıp durumu değiştirilerek gösteriliyor
- [ ] Kök neden hipotezleri ekranda gerekçesiyle birlikte görülebiliyor

## Başarınız nasıl ölçülecek

| Ölçüt | Ne bakılacak |
|---|---|
| İndirgeme oranı | Ürettiğiniz kart sayısının toplam alarm sayısına oranı |
| Kök neden isabeti | Doğrulama verisindeki gerçek köklerden kaçını yakaladığınız |
| Yanlış birleştirme | Birbiriyle ilgisiz iki olayı tek karta koyup koymadığınız |
| Gürültü elemesi | Elenen alarmların ne kadarının gerçekten gürültü olduğu |

---

## Peşin yanıtlanan sorular

**Alarmların hepsini kullanmak zorunda mıyız?**
Evet. Veri setinin tamamı işlenmelidir; örnekleme yaparsanız demoda belirtin.

**Kök nedeni bulamazsak sıfır mı alırız?**
Hayır. Doğru gerekçelendirilmiş yanlış hipotez, gerekçesiz doğru hipotezden daha
yüksek puan alabilir.

**Hazır korelasyon kütüphanesi kullanabilir miyiz?**
Evet, tüm açık kaynak kütüphaneler serbesttir. Kullandığınız her kütüphaneyi
README dosyanızda belirtin.

**Arayüz web olmak zorunda mı?**
Hayır. Terminal, masaüstü veya web fark etmez; ancak demoda canlı çalışması gerekir.

**Kaç tane gerçek olay var?**
Söylenmeyecektir. Bunu veriden çıkarmak senaryonun bir parçasıdır.

---

## Teslim

Repo adresiniz başvuru sırasında alınmıştır; ayrıca bir gönderim yapmanıza gerek
yoktur. Değerlendirme **17:30'daki son commit** üzerinden yapılacaktır.
Reponuz public olmalıdır.

Repo şunları içermelidir: `README.md` (kurulum, kullanılan AI araçları, MCP listesi,
ekran görüntüleri), `docs/` klasörü (plan, fazlar, mimari), `.env.example` ve
AI yapılandırma dosyalarınız (`CLAUDE.md`, `.cursorrules`, `copilot-instructions.md`).

Sorularınız için önce takım mentörünüze başvurun.
