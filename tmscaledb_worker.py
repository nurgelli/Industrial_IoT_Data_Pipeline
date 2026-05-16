import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
import asyncpg

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("DB_Ingestion_Worker")

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
DB_DSN = "postgresql://postgres:123@127.0.0.1:5432/scada_db"
BUFFER_MAX_SIZE = 100
BUFFER_TIMEOUT = 1.0

PROSES_LIMITLERI = {
    "centrifugal_pump": {
        "flow": {"min": 0.0, "max": 200.0},
        "vibration": {"min": 0.0, "max": 12.0}
    },
    "gas_compressor": {
        "bearing_temperature": {"min": 10.0, "max": 95.0},
        "rpm": {"min": 0.0, "max": 1600.0}
    },
    "storage_tank": {
        "level": {"min": 0.0, "max": 100.0},
        "temperature": {"min": -20.0, "max": 60.0}
    }
}

MAX_STALE_COUNT = 5
MAX_TIMEOUT_SEC = 5.0

class DbgIngestionWorker:
    def __init__(self):
        self.metrics_buffer = []
        self.alerts_buffer = []
        self.lock = asyncio.Lock()
        self.db_pool = None
        self.loop = None
        self.last_flush_time = datetime.now()
        self.mqtt_client = None
        self.sensor_states = {}
        # Thread'ler arası güvenli veri aktarımı için asenkron kuyruk (Queue)
        self.msg_queue = asyncio.Queue()

    async def initialize(self):
        try:
            self.db_pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=5, timeout=30.0)
            logger.info("✓ TimescaleDB Connection Pool established.")
        except Exception as e:
            logger.critical(f"Database pool connection failed: {str(e)}")
            raise

    def evaluate_data_quality(self, equipment_id, tag, value, now_dt):
        cache_key = (equipment_id, tag)
        equip_limits = PROSES_LIMITLERI.get(equipment_id, {})
        tag_limits = equip_limits.get(tag)
        
        if tag_limits:
            if value < tag_limits["min"] or value > tag_limits["max"]:
                logger.error(f"⚠️ KURAL 1 İHLALİ (Out of range): {equipment_id}->{tag} | Değer: {value}")
                return "Bad"

        calculated_quality = "Good"
        if cache_key in self.sensor_states:
            state = self.sensor_states[cache_key]
            if state["last_value"] == value:
                state["count"] += 1
                if state["count"] >= MAX_STALE_COUNT:
                    logger.error(f"⚠️ KURAL 2 İHLALİ (Donmuş Sinyal): {equipment_id}->{tag} ardışık {state['count']} tekrar.")
                    calculated_quality = "Bad"
            else:
                state["count"] = 1
            state["last_value"] = value
            state["last_seen"] = now_dt
        else:
            self.sensor_states[cache_key] = {"last_value": value, "count": 1, "last_seen": now_dt}

        return calculated_quality

    async def monitor_heartbeat_and_timeout(self):
        while True:
            await asyncio.sleep(1.0)
            now = datetime.now(timezone.utc)
            for (equip_id, tag), state in list(self.sensor_states.items()):
                elapsed_time = (now - state["last_seen"]).total_seconds()
                if elapsed_time >= MAX_TIMEOUT_SEC:
                    logger.error(f"🔌 KURAL 3 İHLALİ (Zaman Aşımı): {equip_id}->{tag}")
                    async with self.lock:
                        record = (now, equip_id, tag, state["last_value"], "Bad", "timeout_monitor")
                        self.metrics_buffer.append(record)
                    state["last_seen"] = now

    def handle_mqtt_message(self, client, userdata, msg):
        """MQTT Konteyner thread'inden gelen ham mesajı bloke etmeden asenkron kuyruğa fırlatır"""
        try:
            payload_bytes = msg.payload
            topic = msg.topic
            # Thread-safe asenkron kuyruğa ekleme (Asla kilitlenmez)
            self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, (topic, payload_bytes))
        except Exception as e:
            logger.error(f"Ham mesaj kuyruğa eklenirken hata oluştu: {str(e)}")

    async def consume_queue(self):
        """Ana asyncio döngüsünde çalışan ve kuyruğu güvenle tüketen işçi mekanizması"""
        logger.info("⚙ Asenkron Mesaj Tüketici Hattı Aktif Edildi.")
        while True:
            try:
                topic, payload_bytes = await self.msg_queue.get()
                payload = json.loads(payload_bytes.decode('utf-8'))
                
                # 1. SENARYO: ALARM KANALI
                if topic.startswith("alerts/critical"):
                    logger.info(f"📩 [KUYRUK] İşçiye ham alarm ulaştı: {payload}")
                    
                    ts_str = payload["timestamp"]
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    
                    try:
                        dt = datetime.fromisoformat(ts_str)
                    except ValueError:
                        dt = datetime.now(timezone.utc)

                    alert_record = (
                        dt,
                        payload["equipment_id"],
                        payload["tag"],
                        float(payload["current_value"]),
                        float(payload["historical_mean"]),
                        float(payload["z_score"]),
                        payload["severity"],
                        payload["alert_type"]
                    )
                    
                    async with self.lock:
                        self.alerts_buffer.append(alert_record)
                    await self.flush_buffers()
                
                # 2. SENARYO: PROSES VERİSİ KANALI
                elif topic.startswith("plant/"):
                    equipment_id = payload["equipment_id"]
                    tag = payload["tag"]
                    val = float(payload["value"])
                    
                    ts_str = payload["timestamp"].replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts_str)

                    calculated_quality = self.evaluate_data_quality(equipment_id, tag, val, dt)
                    record = (dt, equipment_id, tag, val, calculated_quality, payload["source"])
                    
                    async with self.lock:
                        self.metrics_buffer.append(record)
                        metrics_len = len(self.metrics_buffer)
                    
                    if metrics_len >= BUFFER_MAX_SIZE:
                        await self.flush_buffers()
                        
                self.msg_queue.task_done()
            except Exception as e:
                logger.error(f"❌ Kuyruk İşleme Hatası: {str(e)}")

    async def flush_buffers(self):
        async with self.lock:
            metrics_to_write = list(self.metrics_buffer)
            alerts_to_write = list(self.alerts_buffer)
            self.metrics_buffer.clear()
            self.alerts_buffer.clear()
            self.last_flush_time = datetime.now()

        if not metrics_to_write and not alerts_to_write:
            return

        try:
            async with self.db_pool.acquire() as conn:
                if metrics_to_write:
                    await conn.copy_records_to_table(
                        'metrics_raw', 
                        records=metrics_to_write,
                        columns=['timestamp', 'equipment_id', 'tag', 'value', 'quality', 'source']
                    )
                if alerts_to_write:
                    await conn.copy_records_to_table(
                        'system_alerts',
                        records=alerts_to_write,
                        columns=['timestamp', 'equipment_id', 'tag', 'current_value', 'historical_mean', 'z_score', 'severity', 'alert_type']
                    )
                    logger.info(f"🚨 [VERİTABANI] {len(alerts_to_write)} adet kritik alarm başarıyla system_alerts tablosuna yazıldı.")
        except Exception as e:
            logger.error(f"❌ Veritabanına toplu yazma başarısız oldu: {str(e)}")

    async def monitor_buffer_timeout(self):
        while True:
            await asyncio.sleep(0.5)
            time_since_last_flush = (datetime.now() - self.last_flush_time).total_seconds()
            if time_since_last_flush >= BUFFER_TIMEOUT and (len(self.metrics_buffer) > 0 or len(self.alerts_buffer) > 0):
                await self.flush_buffers()

    async def shutdown(self):
        logger.info("Kapatma sinyali alındı. Kaynaklar temizleniyor...")
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
        await self.flush_buffers()
        if self.db_pool:
            await self.db_pool.close()
        logger.info("İşçi servis güvenli bir şekilde kapatıldı.")

def ask_exit(worker, loop):
    loop.create_task(worker.shutdown())
    for task in asyncio.all_tasks(loop):
        if task.get_coro().__name__ != 'shutdown':
            task.cancel()

async def start_worker():
    worker = DbgIngestionWorker()
    worker.loop = asyncio.get_running_loop()
    await worker.initialize()
    
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            worker.loop.add_signal_handler(sig, lambda: ask_exit(worker, worker.loop))

    try:
        worker.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="TimescaleIngestionWorker")
        worker.mqtt_client.on_message = worker.handle_mqtt_message

        worker.mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)

        # Ardışık ve izole abonelik kanalları
        worker.mqtt_client.subscribe("plant/#", qos=1)
        worker.mqtt_client.subscribe("alerts/critical/#", qos=1)

        worker.mqtt_client.loop_start()
        logger.info("✓ MQTT İstemcisi çift kanallı boru hattına başarıyla bağlandı.")
    except Exception as e:
        logger.critical(f"MQTT Bağlantı hatası: {str(e)}")
        await worker.shutdown()
        return

    # Asenkron görevlerin (tasks) başlatılması
    asyncio.create_task(worker.consume_queue())
    asyncio.create_task(worker.monitor_buffer_timeout())
    asyncio.create_task(worker.monitor_heartbeat_and_timeout())
    
    # Ana döngüyü asenkron görevleri ezmeyecek şekilde açık tutuyoruz
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(start_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Uygulama kullanıcı tarafından kapatıldı.")
    except Exception as e:
        logger.exception(f"İşçi durduruldu: {str(e)}")