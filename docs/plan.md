Hedef: 3.000 sentetik alarmı, bağımlılık (topology) ve zaman (temporal) verilerini kullanarak analiz etmek; gürültüleri ayıklayıp maksimum 15 "Olay Kartı"na (Incident Card) indirgemek. Her kart kök neden hipotezini, kanıtlarını ve izlenebilir bir aksiyonu içermelidir.

Faz 0: İskelet Kurulumu ve Veri Doğrulama 
Görev 0.1: GitHub yarışma gereksinimlerine uygun klasör yapısını (src/, docs/, prompts/, demo/) ve zorunlu dosyaları (README.md, AI_JURI.md, submission.json, .env.example, CLAUDE.md) kontrol et.

Görev 0.2: Verilen alarms.csv, service_dependencies.csv ve host_inventory.csv dosyalarını oku. Toplam alarm sayısının (3000), servis sayısının (27), sunucu sayısının (56) ve bağımlılık sayısının (32) doğruluğunu test eden küçük bir script yazıp konsola yazdır.

Gerekçe: Verinin eksiksiz alındığını doğrulamak.

Git İşlemi: git add . && git commit -m "chore: proje iskeleti kuruldu ve veri boyutlari dogrulandi"

Faz 1: Veri Katmanı ve Topoloji Ağacı İnşası 
Görev 1.1: host_inventory.csv verilerini belleğe alıp host -> {service, datacenter, rack, criticality} eşleşmesini sağlayan bir sözlük/harita (map) oluştur.

Görev 1.2: service_dependencies.csv üzerinden, bağımlılıkların yönünü (kaynak -> hedef) ve kritiklik seviyelerini içeren yönlü bir bellek içi grafik (Directed Graph) inşa et.

Görev 1.3: alarms.csv dosyasındaki her satırı (3000 kayıt) oku. timestamp alanını kronolojik sıralamaya uygun DateTime objesine çevir. Her alarm nesnesine Görev 1.1'deki ilgili sunucu/servis bilgilerini (zenginleştirme - enrichment) ekle.

Git İşlemi: git add . && git commit -m "feat: veri yukleyici, zenginlestirme ve yonlu bagimlilik grafikleri eklendi"

Faz 2: Gürültü Filtreleme ve Zamansal Kümeleme 
Görev 2.1 (Gürültü Filtresi): Alarm listesini tara. severity değeri 1 veya 2 olan ve kendi zaman penceresinde (örneğin ±30 dk) aynı sunucuda/serviste başka alarmı olmayan kayıtları "Gürültü (Noise)" olarak işaretle. Bu kayıtları silme, "Gürültü Defteri"ne (Noise Ledger) kaydederek neden elendiklerini not düş.

Görev 2.2 (Zamansal Kümeleme): Kalan "geçerli" alarmları, çift pencereli (kısa: patlama/burst, uzun: yavaş/slow-burn) bir mantıkla zaman damgalarına ve aynı/komşu serviste olmalarına göre kümelere ayır.

Gerekçe: Alarmların önemli bir bölümünün arka plan gürültüsü olması ve yavaş gelişen olayları yakalayabilmek.

Git İşlemi: git add . && git commit -m "feat: cift pencereli zamansal kumeleme ve gurultu on-filtresi uygulandi"

Faz 3: Topolojik Birleştirme ve Kök Neden Puanlaması 
Görev 3.1 (Topolojik Birleştirme): Faz 2'den çıkan zamansal kümeleri, Faz 1'de oluşturulan Bağımlılık Grafiğine göre analiz et. Eğer iki farklı küme, birbirine bağımlı servislerde (veya aynı DC/Rack'te) ve yakın zaman aralığında oluşmuşsa, bu kümeleri tek bir "Olay (Incident)" altında birleştir.

Görev 3.2 (Kök Neden Analizi): Her bir Olay içindeki alarmları puanla. Puanlama kriterleri: Zaman (en eski olan), Topolojik Merkezilik (en çok servisin bağımlı olduğu) ve Alarm Tipi Eğilimi (ör: network_down veya db_write_fail olanlar puan kazanır, timeout semptom kabul edilir).

Görev 3.3: En yüksek puanı alan alarmı "Kök Neden (Root Cause)", ikinci en yüksek puanlıyı "Karşı Hipotez (Counter-Hypothesis)" olarak belirle. Yapay Zekayı kullanarak (veya şablonla) bu kararın açıklamasını (explanation) oluştur.

Git İşlemi: git add . && git commit -m "feat: topoloji tabanli olay birlestirme ve kok neden puanlama motoru entegre edildi"

Faz 4: Olay Kartı Oluşturma ve Üst Sınır (Kapak) Mantığı 
Görev 4.1: Çıkan olayları, zorunlu şemaya uygun bir JSON yapısına (incident_id, root_cause_hypothesis, affected_services, alarm_count, time_range, recommended_action, vb.) dönüştür. Aksiyon için varsayılan durumu status: "open" olarak ayarla.

Görev 4.2: Olay sayısını kontrol et. Ciddiyet ve etki genişliği formülüne (severity x breadth) göre en kritik 15 olayı seç. Eğer 15'ten fazla olay varsa, kalanları "Diğer / Kümelenmemiş (Unclustered)" adlı tek bir kartta topla (Veri kaybı sıfır).

Git İşlemi: git add . && git commit -m "feat: json olay kartlari uretildi ve 15 kayit siniri (fallback ile) uygulandi"

Faz 5: UI/Pano (Dashboard) ve Aksiyon Takibi 
Görev 5.1: Streamlit (veya belirlenen UI aracı) kullanarak, üretilen <=15 olayın listelendiği Ana Panoyu (Incident Board) kodla.

Görev 5.2: Her kart için "Durum (Status)" değiştirebilme özelliği ekle (Açık -> Üzerinde Çalışılıyor -> Çözüldü). Bunun UI üzerinde tıklandığında değiştiğini ve zaman damgasının güncellendiğini göster.

Görev 5.3 (Bonus): Gürültü olarak elenen alarmların "Neden (Reason)" alanıyla birlikte listelendiği ayrı bir "Gürültü Denetimi (Noise Audit)" sekmesi/sayfası oluştur.

Git İşlemi: git add . && git commit -m "feat: interaktif olay panosu, aksiyon takibi ve gurultu denetim ekrani kodlandi"

Faz 6: Jüri Hazırlığı ve Belgeleme 
Görev 6.1: AI_JURI.md dosyasını, yukarıda kodlanan kanıt dosya yollarını (özellikle AI iş akışı ve X-Factor kısımlarını) referans vererek doldur.

Görev 6.2: Projenin son halinin ekran görüntülerini alıp demo/ klasörüne kaydet ve README.md içerisine ekle.

Görev 6.3: submission.json dosyasını doldur.

Git İşlemi: git add . && git commit -m "docs: AI_JURI.md, submission.json ve README.md tamamlandi, demo gorselleri eklendi"