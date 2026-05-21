import asyncio
import logging
import random
import numpy as np
from asyncua import Server, ua
from pymodbus.client import ModbusTcpClient
import os

# Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Simulation_Factory")

# Modbus config
MODBUS_HOST = os.getenv("MODBUS_HOST", "127.0.0.1")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
modbus_client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)

# base val
process_state = {
    "pump_flow": 120.0,
    "pump_suc_pres": 2.5,
    "pump_dis_pres": 34.8,
    "pump_vib": 3.8,
    "comp_bearing_temp": 72.3,
    "comp_rpm": 1450.0,
    "tank_level": 65.2,
    "tank_temp": 28.4
}

def generate_next_value(current, drift, noise_std, min_val, max_val):
    # Gaussian Noise eklenmiş Random Walk
    noise = np.random.normal(0, noise_std)
    new_val = current + drift + noise
    return float(np.clip(new_val, min_val, max_val))

async def main():
    opc_server = Server()
    await opc_server.init()
    opc_server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
    opc_server.set_server_name("Production Simulator")

    # Namespace defining
    uri = "http://mpi.oilgas.sim"
    idx = await opc_server.register_namespace(uri)

    # Object tree parent
    objects = opc_server.nodes.objects

# Folders
    og_folder = await objects.add_folder(ua.NodeId(0, idx), ua.QualifiedName("OilGas_Production", idx))
    
    pump_obj = await og_folder.add_folder(ua.NodeId(0, idx), ua.QualifiedName("Centrifugal_Pump", idx))
    comp_obj = await og_folder.add_folder(ua.NodeId(0, idx), ua.QualifiedName("Gas_Compressor", idx))
    tank_obj = await og_folder.add_folder(ua.NodeId(0, idx), ua.QualifiedName("Storage_Tank", idx))

    # Variables
    opc_nodes = {
        "pump_flow": await pump_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("Flow", idx), process_state["pump_flow"], ua.VariantType.Double),
        "pump_suc_pres": await pump_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("SuctionPressure", idx), process_state["pump_suc_pres"], ua.VariantType.Double),
        "pump_dis_pres": await pump_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("DischargePressure", idx), process_state["pump_dis_pres"], ua.VariantType.Double),
        "pump_vib": await pump_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("Vibration", idx), process_state["pump_vib"], ua.VariantType.Double),
        
        "comp_bearing_temp": await comp_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("BearingTemperature", idx), process_state["comp_bearing_temp"], ua.VariantType.Double),
        "comp_rpm": await comp_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("RPM", idx), process_state["comp_rpm"], ua.VariantType.Double),
        
        "tank_level": await tank_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("Level", idx), process_state["tank_level"], ua.VariantType.Double),
        "tank_temp": await tank_obj.add_variable(ua.NodeId(0, idx), ua.QualifiedName("Temperature", idx), process_state["tank_temp"], ua.VariantType.Double),
    }

    # opc-ua writable
    for key, node in opc_nodes.items():
        await node.set_writable()
        logger.info(f"✓ OPC-UA Variable created and writable: {key}")

    # data sending loop
    logger.info("OPC-UA Server starting on port: 4840...")
    async with opc_server:
        logger.info("Checking modbus tcp continer connections...")
        if not modbus_client.connect():
            logger.error(f"Modbus Server ({MODBUS_HOST}:{MODBUS_PORT}) cant connect! is Docker  working?")
            return

        logger.info("Simulation factory is working. Data production started.")
        
        while True:
            # Process value updating
            process_state["pump_flow"] = generate_next_value(process_state["pump_flow"], 0.05, 0.2, 0, 200)
            process_state["pump_suc_pres"] = generate_next_value(process_state["pump_suc_pres"], 0.0, 0.02, 1, 5)
            process_state["pump_dis_pres"] = generate_next_value(process_state["pump_dis_pres"], 0.1, 0.15, 20, 45)
            process_state["pump_vib"] = generate_next_value(process_state["pump_vib"], 0.01, 0.05, 0, 15)
            
            process_state["comp_bearing_temp"] = generate_next_value(process_state["comp_bearing_temp"], 0.1, 0.3, 30, 95)
            process_state["comp_rpm"] = generate_next_value(process_state["comp_rpm"], random.choice([-5, 0, 5]), 2.0, 1400, 1500)
            
            process_state["tank_level"] = generate_next_value(process_state["tank_level"], -0.02, 0.05, 0, 100)
            process_state["tank_temp"] = generate_next_value(process_state["tank_temp"], 0.02, 0.1, -10, 50)

            # opc-ua updateing
            for key, node in opc_nodes.items():
                await node.write_value(process_state[key])

            # ! Modbus TCP update Scaled uint16
            try:
                # Holding register packet set address 
                modbus_payload = [
                    int(process_state["pump_flow"] * 10),          # 40001
                    int(process_state["pump_suc_pres"] * 100),     # 40002
                    int(process_state["pump_dis_pres"] * 100),     # 40003
                    int(process_state["pump_vib"] * 100),          # 40004
                    int(process_state["pump_dis_pres"] * 100),     # 40005 (Simulated compressor enter load)
                    int(process_state["pump_dis_pres"] * 2.5 * 100),# 40006 (compressor exit load)
                    int(process_state["comp_bearing_temp"] * 10),  # 40007
                    int(process_state["comp_rpm"]),                # 40008
                    int(process_state["tank_level"] * 10),         # 40009
                    int(process_state["tank_temp"] * 10)           # 40010
                ]
                
                # Modbus Function Code 16 (Write Multiple Registers
                # First address 0 (Protokol level 0 = second readed 40001 )
                response = modbus_client.write_registers(0, modbus_payload, device_id=0)
                if response.isError():
                    logger.warning(f"Modbus writable error: {response}")
            except Exception as e:
                logger.error(f"Modbus connection issue: {str(e)}")
                modbus_client.connect()

            logger.debug(f"Current flow: {process_state['pump_flow']:.2f} m3/h | Tank Level: {process_state['tank_level']:.2f} %")
            await asyncio.sleep(1) # 1 secodn scan rate

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user.")
        modbus_client.close()