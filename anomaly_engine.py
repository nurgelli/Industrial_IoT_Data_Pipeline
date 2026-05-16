import asyncio
import json
import logging
import sys
from collections import deque
import numpy as np
import paho.mqtt.client as mqtt

# Log Yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Anomaly_Detection_Engine")

# Konfigürasyonlar
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
INPUT_TOPIC = "plant/#"
ALERT_TOPIC_PREFIX = "alerts/critical"

# Algoritma Parametreleri
WINDOW_SIZE = 30  # İstatistiksel hesaplama için son kaç veri noktası baz alınacak?
Z_THRESHOLD = 3.0  # Kaç standart sapma üzeri anomali kabul edilecek?

class AnomalyDetectionEngine:
    def __init__(self):
        self.mqtt_client = None
        self.loop = None
        # Her sensörün geçmiş verisini tutacak bellek yapısı
        # Yapı: {("equipment_id", "tag"): deque([val1, val2, ...], maxlen=30)}
        self.windows = {}

    def handle_mqtt_message(self, client, userdata, msg):
        try:
            # Gelen alarm topikleri kendi ürettiğimiz alarmlar ise işlemeyi atla (Döngü engelleme)
            if msg.topic.startswith(ALERT_TOPIC_PREFIX):
                return

            payload = json.loads(msg.payload.decode('utf-8'))
            equipment_id = payload["equipment_id"]
            tag = payload["tag"]
            val = float(payload["value"])
            
            # Kural Motorundan elenmiş 'Bad' verileri analize dahil etme
            if payload.get("quality") == "Bad":
                return

            cache_key = (equipment_id, tag)
            if cache_key not in self.windows:
                self.windows[cache_key] = deque(maxlen=WINDOW_SIZE)

            # Değeri kayan pencereye ekle
            window = self.windows[cache_key]
            window.append(val)

            # Pencere yeterli doluluğa ulaşmadan istatistik hesaplama (En az 15 veri noktası şart)
            if len(window) < 15:
                return

            # Z-Score Hesaplama
            vals_array = np.array(window)
            mean = np.mean(vals_array)
            std = np.std(vals_array)

            if std > 0.001:  # Sıfıra bölme hatasını engelle (Donmuş sinyal değilse)
                z_score = (val - mean) / std
                
                # Anomali Kontrolü
                if abs(z_score) > Z_THRESHOLD:
                    logger.error(f"🚨 ANOMALİ TESPİT EDİLDİ: {equipment_id}->{tag} | Değer: {val} | Ortalama: {mean:.2f} | Z-Score: {z_score:.2f}")
                    
                    # Alarm Görevini Asenkron Olarak Tetikle
                    asyncio.run_coroutine_threadsafe(
                        self.publish_alarm(equipment_id, tag, val, mean, z_score), 
                        self.loop
                    )
        except Exception as e:
            logger.error(f"Anomaly engine processing error: {str(e)}")

    async def publish_alarm(self, equipment_id, tag, current_value, historical_mean, z_score):
        """Tespit edilen anomaliyi kurumsal alarm topigine fırlatır"""
        alert_topic = f"{ALERT_TOPIC_PREFIX}/{equipment_id}/{tag}"
        alert_payload = {
            "alert_type": "STATISTICAL_ANOMALY",
            "equipment_id": equipment_id,
            "tag": tag,
            "current_value": current_value,
            "historical_mean": historical_mean,
            "z_score": z_score,
            "severity": "CRITICAL",
            "timestamp": np.datetime64('now').astype(str) + "Z"
        }
        
        try:
            self.mqtt_client.publish(alert_topic, json.dumps(alert_payload), qos=1)
            logger.info(f"✔ Alarm published to MQTT topic: {alert_topic}")
        except Exception as e:
            logger.error(f"Failed to publish MQTT alarm: {str(e)}")

    def start(self, loop):
        """Mevcut aktif event loop'u dışarıdan alır"""
        self.loop = loop
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="AnomalyEngine")
        self.mqtt_client.on_message = self.handle_mqtt_message
        
        try:
            self.mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.mqtt_client.subscribe(INPUT_TOPIC, qos=1)
            self.mqtt_client.loop_start()
            logger.info(f"✓ Anomaly Engine successfully subscribed to: {INPUT_TOPIC}")
        except Exception as e:
            logger.critical(f"Anomaly Engine MQTT connection failed: {str(e)}")
            sys.exit(1)
async def main():
    # Tek ve merkezi event loop oluşturuluyor
    loop = asyncio.get_running_loop()
    engine = AnomalyDetectionEngine()
    engine.start(loop)
    
    # Ana döngü loop'u bloke etmeden açık tutar
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Anomaly Engine shutting down.")