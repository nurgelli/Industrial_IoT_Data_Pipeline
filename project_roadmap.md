# PROJE ÜRETİM HATTI (PRODUCTION PIPELINE) YOL HARİTASI
## Petrol ve Gaz Endüstriyel Veri Analitiği Portfolyo Projesi Checklist'i

Bu döküman, 8GB RAM kısıtına sahip bir yerel geliştirme ortamında, uluslararası petrol ve gaz şirketlerinin (Petronas, Dragon Oil, ADNOC vb.) standartlarına uygun uçtan uca (End-to-End) bir endüstriyel veri hattı mimarisinin inşa adımlarını içerir. Proje boyunca bu adımlar referans alınacaktır.

---

## AŞAMA 1: Protokol Seviyesi ve Veri Üretimi (Data Generation)
- [x] **Adım 1.1:** Sahadaki fiziksel varlıkların (Centrifugal Pump, Gas Compressor, Storage Tank) belirlenmesi ve endüstriyel parametre sınırlarının çizilmesi.
- [x] **Adım 1.2:** Modbus TCP Holding Register Haritasının (Mapping Table) çıkartılması ve 16-bit tamsayı ölçeklendirme mantığının kurulması.
- [x] **Adım 1.3:** `compose.yaml` içerisine `oitc/modbus-server` entegrasyonu.
- [x] **Adım 1.4:** Python ile asenkron, gürültülü (Gaussian Noise) ve gerçekçi veri üreten `simul_factory.py` simülatörünün yazılması (Hem OPC-UA hem Modbus TCP desteği).

---

## AŞAMA 2: Veri Entegrasyon Köprüsü (Industrial Bridge) ve Mesaj Dağıtımı
- [x] **Adım 2.1:** Eclipse Mosquitto MQTT Broker altyapısının `compose.yaml` dosyasına eklenmesi ve konfigüre edilmesi.
- [x] **Adım 2.2:** Birleşik JSON Veri Şemasının (Unified Schema) tasarlanması (Source, Equipment_ID, Tag, Value, Timestamp, Quality).
- [x] **Adım 2.3:** Modbus TCP için Polling (zaman tabanlı) ve OPC-UA için Subscription (olay tabanlı) veri toplama mekanizmalarını içeren `bridge.py` köprü yazılımının tamamlanması.

---

## AŞAMA 3: Veri Depolama ve Zaman Serisi Veritabanı Katmanı (TimescaleDB)
- [ ] **Adım 3.1:** `timescale/timescaledb` Docker imajının indirilmesi ve sistem kaynaklarına göre (RAM/Storage) optimize edilerek ayağa kaldırılması.
- [ ] **Adım 3.2:** İlişkisel Meta-data tablosu (Varlık tanımları) ve zaman serisi ana tablosunun (Hypertable) SQL şemalarının tasarlanması.
- [ ] **Adım 3.3:** Sektör standardı indeksleme stratejilerinin uygulanması (Timestamp + Equipment_ID bileşik indeksleri).
- [ ] **Adım 3.4:** MQTT Broker'dan gelen verileri asenkron olarak tüketen (Subscribe) ve TimescaleDB'ye toplu yazma (Bulk Insert) yapan `db_ingestion_worker.py` servisinin yazılması.

---

## AŞAMA 4: Endüstriyel Veri Kalitesi ve Veri Ambarı Optimizasyonu
- [ ] **Adım 4.1:** **Data Quality Rule Engine:** Sahadan gelen veri kesintileri, donmuş sinyaller (stale data) ve mantık dışı taşmalar için veri kalitesi kontrol algoritmasının yazılması.
- [ ] **Adım 4.2:** **Data Compression / Retention Policy:** TimescaleDB yerel sıkıştırma (Compression) algoritmalarının konfigüre edilmesi ve ham verilerin depolama maliyetini düşürme stratejisi.
- [ ] **Adım 4.3:** **Continuous Aggregations:** Grafana katmanının yükünü hafifletmek için veritabanı seviyesinde saatlik/günlük istatistiksel özet tablolarının (Mean, Max, Min, StdDev) otomatik tetikleyicilerle oluşturulması.

---

## AŞAMA 5: Analitik ve Gelişmiş Anomali Tespiti (Analytics & ML)
- [ ] **Adım 5.1:** Pompa kavitasyonu (cavitation) ve kompresör yatak aşırı ısınması gibi spesifik O&G arızalarının matematiksel kurallarla simüle edilmesi.
- [ ] **Adım 5.2:** Geçen pencereli (Rolling Window) istatistiksel analizler kullanılarak (Z-Score yöntemi) anlık anomali tespiti yapan analitik servisinin yazılması.
- [ ] **Adım 5.3:** Tespit edilen anomalilerin MQTT üzerinden `alerts/critical/...` topigine fırlatılması ve sistem alarm günlüğünün tutulması.

---

## AŞAMA 6: Görselleştirme ve İzleme Merkezinin Kurulması (Grafana)
- [ ] **Adım 6.1:** Grafana servisinin sisteme dahil edilmesi ve TimescaleDB veri kaynağı (Data Source) entegrasyonu.
- [ ] **Adım 6.2:** Gerçek zamanlı operasyonel SCADA paneli (Dashboard) tasarımı (Anlık akış, basınç değişimleri, tank seviye göstergeleri).
- [ ] **Adım 6.3:** Yönetici Özeti (Executive Summary) ve Analitik Paneli tasarımı (Geçmişe dönük anomali sıklığı, ekipman bazlı duruş tahminleri).

---

## AŞAMA 7: Kurumsal Portfolyo Paketleme ve Sunum Stratejisi
- [ ] **Adım 7.1:** Tüm mimarinin tek bir `compose.yaml` ile (Network izolasyonları ve Volume yedeklemeleri dahil) ayağa kalkacak şekilde nihai hale getirilmesi.
- [ ] **Adım 7.2:** GitHub / GitLab reposu için profesyonel, mimari diyagram içeren, sistem metriklerini açıklayan ingilizce `README.md` dökümantasyonunun yazılması.
- [ ] **Adım 7.3:** Uluslararası mülakatçılara projenin mimari üstünlüklerini (Neden MQTT kullanıldı? Neden TimescaleDB seçildi? Veri kalitesi nasıl sağlandı?) aktaracak teknik savunma argümanlarının hazırlanması.

---

### KRİTİK NOT:
Herhangi bir adım tamamlanmadan bir sonrakine geçilmeyecektir. Sistem kararlılığı, her aşamanın log çıktıları ve kaynak tüketimleri izlenerek doğrulanacaktır.
