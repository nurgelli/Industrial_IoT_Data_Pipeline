import asyncio
import json
import logging
import signal
import sys
import sqlite3
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
import asyncpg
import os

# Log Yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("DB_ingestion_Worker")

# Ortam Değişkenleri
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DB_URL = os.getenv("DB_URL", "postgresql://postgres:123@127.0.0.1:5432/scada_db")

# SQLite Konfigürasyonu
SQLITE_DIR = "/app/data"
SQLITE_PATH = os.path.join(SQLITE_DIR, "local_buffer.db")

BUFFER_MAX_SIZE = 100
BUFFER_TIMEOUT = 1.0

MAX_STALE_COUNT = 5
MAX_TIMEOUT_SEC = 5.0

PROCESS_LIMITS = {
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
        self.msg_queue = asyncio.Queue(maxsize=10000)
        self.is_running = True

    def init_sqlite(self):
        """locale buffering with sqlite"""
        os.makedirs(SQLITE_DIR, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS local_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_table TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info(f"local sqlite buffer initialized at {SQLITE_PATH}")

    async def initialize(self):
        try:
            self.db_pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5, timeout=30.0)
            logger.info("TimescaleDB Connection Pool established.")
        except Exception as e:
            logger.warning(f"TimescaleDB Pool initialization standby: {str(e)}")
            self.db_pool = None

    def evaluate_data_quality(self, equipment_id, tag, value, now_dt):
        cache_key = (equipment_id, tag)
        equip_limits = PROCESS_LIMITS.get(equipment_id, {})
        tag_limits = equip_limits.get(tag)
        
        if tag_limits:
            if value < tag_limits["min"] or value > tag_limits["max"]:
                logger.error(f"Rule 1 violated (Out of range): {equipment_id}->{tag} | Value: {value}")
                return "Bad"
        calculated_quality = "Good"

        if cache_key in self.sensor_states:
            state = self.sensor_states[cache_key]
            if state["last_value"] == value:
                state["count"] += 1
                if state["count"] >= MAX_STALE_COUNT:
                    logger.error(f"Rule 2 violated (frozen signal): {equipment_id}->{tag} sequential {state['count']}")
                    calculated_quality = "Bad"
            else:
                state["count"] = 1
            state["last_value"] = value
            state["last_seen"] = now_dt
        else:
            self.sensor_states[cache_key] = {"last_value": value, "count": 1, "last_seen": now_dt}

        return calculated_quality

    async def monitor_heartbeat_and_timeout(self):
        while self.is_running:
            await asyncio.sleep(1.0)
            now = datetime.now(timezone.utc)
            for (equip_id, tag), state in list(self.sensor_states.items()):
                elapsed_time = (now - state["last_seen"]).total_seconds()
                if elapsed_time >= MAX_TIMEOUT_SEC:
                    logger.error(f"rule 3 violated (timeout): {equip_id}->{tag}")
                    async with self.lock:
                        record = (now, equip_id, tag, state["last_value"], "Bad", "timeout_monitor")
                        self.metrics_buffer.append(record)
                    state["last_seen"] = now

    def handle_mqtt_message(self, client, userdata, msg):
        try:
            payload_bytes = msg.payload
            topic = msg.topic
            if self.loop and self.is_running:
                self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, (topic, payload_bytes))
        except Exception as e:
            logger.error(f"While adding Raw message to queue occured error: {str(e)}")

    async def consume_queue(self):
        logger.info("Async msg subscirber is activated")
        while self.is_running:
            try:
                topic, payload_bytes = await self.msg_queue.get()
                payload = json.loads(payload_bytes.decode('utf-8'))
                
                # 1. SENARYO: ALARM KANALI
                if topic.startswith("alerts/critical"):
                    logger.info(f"QUEUE => Raw alarm reached to worker: {payload}")
                    
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
                logger.error(f"Queue processing error: {str(e)}")

    def sync_save_to_sqlite(self, table_name, records):
        """syncronously writing to disk"""
        if not records:
            return
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        serialized_records = []
        for r in records:
            dt_str = r[0].isoformat()
            remaining_data = r[1:]
            serialized_records.append((table_name, json.dumps((dt_str,) + remaining_data)))

        cursor.executemany(
            "INSERT INTO local_buffer (target_table, payload) VALUES (?, ?)",
            serialized_records
        )
        conn.commit()
        conn.close()

    async def save_to_sqlite(self, table_name, records):
        """not blocking Event loop data will reserved to the disk"""
        try:
            await self.loop.run_in_executor(None, self.sync_save_to_sqlite, table_name, records)
            logger.warning(f"⬇ Network/DB Down. {len(records)} records safely buffered to local SQLite for table '{table_name}'.")
        except Exception as e:
            logger.critical(f"CRITICAL: Local SQLite write failed! Data lost risk! Error: {e}")

    async def flush_buffers(self):
        async with self.lock:
            metrics_to_write = list(self.metrics_buffer)
            alerts_to_write = list(self.alerts_buffer)
            self.metrics_buffer.clear()
            self.alerts_buffer.clear()
            self.last_flush_time = datetime.now()

        if not metrics_to_write and not alerts_to_write:
            return

        # Veritabanı havuzu yoksa direkt diske yaz
        if not self.db_pool:
            if metrics_to_write:
                await self.save_to_sqlite('metrics_raw', metrics_to_write)
            if alerts_to_write:
                await self.save_to_sqlite('system_alerts', alerts_to_write)
            return

        try:
            async with self.db_pool.acquire() as conn:
                if metrics_to_write:
                    await conn.copy_records_to_table(
                        'metrics_raw', 
                        records=metrics_to_write,
                        columns=['timestamp', 'equipment_id', 'tag', 'value', 'quality', 'source']
                    )
                    logger.info(f"To DB {len(metrics_to_write)} metrics written to the metrics_raw table successfully.")
                if alerts_to_write:
                    await conn.copy_records_to_table(
                        'system_alerts',
                        records=alerts_to_write,
                        columns=['timestamp', 'equipment_id', 'tag', 'current_value', 'historical_mean', 'z_score', 'severity', 'alert_type']
                    )
                    logger.info(f"To DB {len(alerts_to_write)} critical alarm written to the system_alerts table.")
        except Exception as e:
            logger.error(f"Bulk writing to the main DB failed : {str(e)}. Data is transfering to local_buffer ")
            # Yazma başarısız olursa verileri kurtarmak için SQLite'a gönder
            if metrics_to_write:
                await self.save_to_sqlite('metrics_raw', metrics_to_write)
            if alerts_to_write:
                await self.save_to_sqlite('system_alerts', alerts_to_write)

    def sync_fetch_sqlite(self):
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, target_table, payload FROM local_buffer ORDER BY id ASC LIMIT 100")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def sync_delete_ids_sqlite(self, ids):
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM local_buffer WHERE id IN ({','.join(['?']*len(ids))})", ids)
        conn.commit()
        conn.close()

    async def forward_local_buffer_task(self):
        # in backround datas in local_buffer will be send to the main db
        logger.info("Background Store-and-Forward task started")
        while self.is_running:
            await asyncio.sleep(5.0)
            
            if not self.db_pool:
                try:
                    self.db_pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5, timeout=30.0)
                except:
                    continue

            try:
                rows = await self.loop.run_in_executor(None, self.sync_fetch_sqlite)
                if not rows:
                    continue
                
                logger.info(f"Network status stable. Forwarding {len(rows)} buffered records from SQLite to TimescaleDB...")
                
                metrics_batch = []
                alerts_batch = []
                processed_ids = []
                
                for row_id, target_table, payload_json in rows:
                    raw_tuple = json.loads(payload_json)
                    
                    dt_obj = datetime.fromisoformat(raw_tuple[0])
                    reconstructed_record = (dt_obj,) + tuple(raw_tuple[1:])
                    
                    if target_table == 'metrics_raw':
                        metrics_batch.append(reconstructed_record)
                    elif target_table == 'system_alerts':
                        alerts_batch.append(reconstructed_record)
                    processed_ids.append(row_id)

                async with self.db_pool.acquire() as conn:
                    # to keep FIFO wiriting in transaction
                    async with conn.transaction():
                        if metrics_batch:
                            await conn.copy_records_to_table(
                                'metrics_raw', 
                                records=metrics_batch,
                                columns=['timestamp', 'equipment_id', 'tag', 'value', 'quality', 'source']
                            )
                        if alerts_batch:
                            await conn.copy_records_to_table(
                                'system_alerts',
                                records=alerts_batch,
                                columns=['timestamp', 'equipment_id', 'tag', 'current_value', 'historical_mean', 'z_score', 'severity', 'alert_type']
                            )
                
                # TimescaleDB kopyalama başarılı olduysa yerel diskten sil
                await self.loop.run_in_executor(None, self.sync_delete_ids_sqlite, processed_ids)
                logger.info(f"Successfully migrated {len(processed_ids)} records from SQLite to primary storage.")
                
            except Exception as e:
                logger.warning(f"Migration failed. TimescaleDB still unreachable or Schema error: {e}. Re-buffering active.")

    async def monitor_buffer_timeout(self):
        while self.is_running:
            await asyncio.sleep(0.5)
            time_since_last_flush = (datetime.now() - self.last_flush_time).total_seconds()
            if time_since_last_flush >= BUFFER_TIMEOUT:
                async with self.lock:
                    has_data = len(self.metrics_buffer) > 0 or len(self.alerts_buffer) > 0
                if has_data:
                    await self.flush_buffers()

    async def shutdown(self):
        logger.info("Signal got. Sources cleaning...")
        self.is_running = False
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
        await self.flush_buffers()
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Worker service closed securly")

def ask_exit(worker, loop):
    loop.create_task(worker.shutdown())
    for task in asyncio.all_tasks(loop):
        if task.get_coro().__name__ != 'shutdown':
            task.cancel()

async def start_worker():
    worker = DbgIngestionWorker()
    worker.loop = asyncio.get_running_loop()
    
    # SQLite init
    worker.init_sqlite()
    
    # DB init
    await worker.initialize()
    
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            worker.loop.add_signal_handler(sig, lambda: ask_exit(worker, worker.loop))

    try:
        worker.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="TimescaleIngestionWorker")
        worker.mqtt_client.on_message = worker.handle_mqtt_message
        worker.mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)

        worker.mqtt_client.subscribe("plant/#", qos=1)
        worker.mqtt_client.subscribe("alerts/critical/#", qos=1)

        worker.mqtt_client.loop_start()
        logger.info("MQTT Sub two way success")
    except Exception as e:
        logger.critical(f"MQTT connection error: {str(e)}")
        await worker.shutdown()
        return

    # async task creting
    asyncio.create_task(worker.consume_queue())
    asyncio.create_task(worker.forward_local_buffer_task())
    asyncio.create_task(worker.monitor_buffer_timeout())
    asyncio.create_task(worker.monitor_heartbeat_and_timeout())
    
    while worker.is_running:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(start_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("User interrupted")
    except Exception as e:
        logger.exception(f"Worker stopped: {str(e)}")