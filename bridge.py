import asyncio
import json
import logging
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from asyncua import Client
from pymodbus.client import ModbusTcpClient

# Log Yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("IndustrialBridge")

# Konfigürasyonlar
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 5020
OPC_URL = "opc.tcp://127.0.0.1:4840/freeopcua/server/"

# MQTT İstemci Kurulumu
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

def connect_mqtt():
    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logger.info("MQTT Broker connected.")
    except Exception as e:
        logger.error(f"MQTT Broker connection error: {str(e)}")

def publish_to_broker(equipment_id, tag, payload):
    """Veriyi plant/equipment_id/tag topigine QoS 1 ile yayınlar"""
    topic = f"plant/{equipment_id}/{tag}"
    message = json.dumps(payload)
    mqtt_client.publish(topic, message, qos=1)

# !--- OPC-UA SUBSCRIPTION HANDLER ---
class OpcSubHandler:
    """OPC-UA Server'dan gelen tüm veri değişimlerini tek bir merkezden çözen handler"""
    def __init__(self):
        # Düğüm kimliklerini (NodeId) etiketlerle eşleştiren dinamik harita
        self.node_map = {}  # Key: str(NodeId), Value: (equipment_id, tag_name)

    def register_node(self, node_id, equipment_id, tag_name):
        """Hangi node hangi ekipmana ait kaydeder"""
        self.node_map[str(node_id)] = (equipment_id, tag_name)

    async def datachange_notification(self, node, val, data):
        node_str = str(node.nodeid)
        if node_str in self.node_map:
            equipment_id, tag_name = self.node_map[node_str]
            payload = {
              "source": "opc_ua",
              "equipment_id": equipment_id,
              "tag": tag_name,
              "value": float(val),
              "timestamp": datetime.now(timezone.utc).isoformat(),
              "quality": "Good"
            }
            publish_to_broker(equipment_id, tag_name, payload)
        else:
            logger.warning(f"Haritada tanımlı olmayan düğüm bildirimi geldi: {node_str}")

# --- MAIN ORCHESTRATION KISMI ---
async def main():
    connect_mqtt()
    asyncio.create_task(modbus_polling_loop())
    
    logger.info("OPC-UA Server connecting...")
    async with Client(url=OPC_URL) as opc_client:
        idx = await opc_client.get_namespace_index("http://mpi.oilgas.sim")
        print(f'[INFO] Got Dynamic namespace: {idx}')
        
        node_paths = [
            ("centrifugal_pump", "flow", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Centrifugal_Pump", f"{idx}:Flow"]),
            ("centrifugal_pump", "suction_pressure", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Centrifugal_Pump", f"{idx}:SuctionPressure"]),
            ("centrifugal_pump", "discharge_pressure", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Centrifugal_Pump", f"{idx}:DischargePressure"]),
            ("centrifugal_pump", "vibration", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Centrifugal_Pump", f"{idx}:Vibration"]),
            ("gas_compressor", "bearing_temperature", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Gas_Compressor", f"{idx}:BearingTemperature"]),
            ("gas_compressor", "rpm", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Gas_Compressor", f"{idx}:RPM"]),
            ("storage_tank", "level", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Storage_Tank", f"{idx}:Level"]),
            ("storage_tank", "temperature", ["0:Objects", f"{idx}:OilGas_Production", f"{idx}:Storage_Tank", f"{idx}:Temperature"])
        ]
        
       
        handler = OpcSubHandler()
        subscription = await opc_client.create_subscription(500, handler)
        
        for equip_id, tag_name, path in node_paths:
            node = await opc_client.nodes.root.get_child(path)
            
            # Node referansını ve kimliğini handler haritasına işletiyoruz
            handler.register_node(node.nodeid, equip_id, tag_name)
            
            # DOĞRU KULLANIM: İkinci parametre olarak handler GEÇİLMEZ, kütüphane otomatik halleder
            await subscription.subscribe_data_change(node)
            logger.info(f"OPC-UA Node registered to map and subscribed: {equip_id} -> {tag_name}")
            
        while True:
            await asyncio.sleep(1)

# ! --- MODBUS POLLING TASK ---
async def modbus_polling_loop():
    """Saniyede bir Modbus Register'larını okuyan döngü"""
    mb_client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
    
    while True:
        if not mb_client.is_socket_open():
            mb_client.connect()
            await asyncio.sleep(2)
            continue
            
        try:
            # Function Code 03 ile 10 adet register oku
            response = mb_client.read_holding_registers(0, count=10, device_id=0)
            if not response.isError():
                regs = response.registers
                ts = datetime.now(timezone.utc).isoformat()
                
                # Register haritasına göre verileri çöz ve ölçeklendir
                data_map = [
                    ("centrifugal_pump", "flow", regs[0] / 10.0),
                    ("centrifugal_pump", "suction_pressure", regs[1] / 100.0),
                    ("centrifugal_pump", "discharge_pressure", regs[2] / 100.0),
                    ("centrifugal_pump", "vibration", regs[3] / 100.0),
                    ("gas_compressor", "bearing_temperature", regs[6] / 10.0),
                    ("gas_compressor", "rpm", float(regs[7])),
                    ("storage_tank", "level", regs[8] / 10.0),
                    ("storage_tank", "temperature", regs[9] / 10.0)
                ]
                
                for equip, tag, val in data_map:
                    payload = {
                        "source": "modbus_tcp",
                        "equipment_id": equip,
                        "tag": tag,
                        "value": val,
                        "timestamp": ts,
                        "quality": "Good"
                    }
                    publish_to_broker(equip, tag, payload)
                    
        except Exception as e:
            logger.error(f"Modbus Polling error: {str(e)}")
            
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bridge service closing.")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()