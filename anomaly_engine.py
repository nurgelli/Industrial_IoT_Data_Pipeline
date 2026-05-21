import asyncio
import json
import logging
import sys
from collections import deque
import numpy as np
import paho.mqtt.client as mqtt
import os

# Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Anomaly_Detection_Engine")

# config
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

INPUT_TOPIC = "plant/#"
ALERT_TOPIC_PREFIX = "alerts/critical"

# Algorythm param
WINDOW_SIZE = 30  # For statistics how many data will be used
Z_THRESHOLD = 3.0  # Std 

class AnomalyDetectionEngine:
    def __init__(self):
        self.mqtt_client = None
        self.loop = None
        # {("equipment_id", "tag"): deque([val1, val2, ...], maxlen=30)}
        self.windows = {}

    def handle_mqtt_message(self, client, userdata, msg):
        try:
            if msg.topic.startswith(ALERT_TOPIC_PREFIX):
                return

            payload = json.loads(msg.payload.decode('utf-8'))
            equipment_id = payload["equipment_id"]
            tag = payload["tag"]
            val = float(payload["value"])
            
            # if bad status don analyze
            if payload.get("quality") == "Bad":
                return

            cache_key = (equipment_id, tag)
            if cache_key not in self.windows:
                self.windows[cache_key] = deque(maxlen=WINDOW_SIZE)

            # add to window
            window = self.windows[cache_key]
            window.append(val)

            # if there is not enough data dont calculate statistics
            if len(window) < 15:
                return

            # Z-Score calculate
            vals_array = np.array(window)
            mean = np.mean(vals_array)
            std = np.std(vals_array)

            if std > 0.001:  # prevent to divide 0
                z_score = (val - mean) / std
                
                # Anomali check
                if abs(z_score) > Z_THRESHOLD:
                    logger.error(f"Anomaly detected: {equipment_id}->{tag} val: {val} | mean: {mean:.2f} | Z-Score: {z_score:.2f}")
                    
                    # Alarm task async trigging
                    asyncio.run_coroutine_threadsafe(
                        self.publish_alarm(equipment_id, tag, val, mean, z_score), 
                        self.loop
                    )
        except Exception as e:
            logger.error(f"Anomaly engine processing error: {str(e)}")

    async def publish_alarm(self, equipment_id, tag, current_value, historical_mean, z_score):
        # detected anomly will be send to the topic alarm
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
        self.loop = loop
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="AnomalyEngine")
        self.mqtt_client.on_message = self.handle_mqtt_message
        
        try:
            self.mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.mqtt_client.subscribe(INPUT_TOPIC, qos=1)
            self.mqtt_client.loop_start()
            logger.info(f"Anomaly Engine successfully subscribed to: {INPUT_TOPIC}")
        except Exception as e:
            logger.critical(f"Anomaly Engine MQTT connection failed: {str(e)}")
            sys.exit(1)
async def main():
    loop = asyncio.get_running_loop()
    engine = AnomalyDetectionEngine()
    engine.start(loop)
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Anomaly Engine shutting down.")