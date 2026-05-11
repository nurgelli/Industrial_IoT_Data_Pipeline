"""
Test Script for Layer 1a & 1b
OPC-UA Server ve Modbus TCP Server'ı test et
"""

import subprocess
import time
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    logger.info("="*80)
    logger.info("STEP 2 TEST: Data Sources (OPC-UA + Modbus)")
    logger.info("="*80)
    
    # Terminal windows aç
    logger.info("\n📝 Test Talimatları:")
    logger.info("1. Bu script öncesinde venv aktivasyon yap:")
    logger.info("   venv\\Scripts\\activate\n")
    
    logger.info("2. Terminal 1'de OPC-UA server başlat:")
    logger.info("   python src/layer1_data_source/opc_ua_server.py\n")
    
    logger.info("3. Terminal 2'de Modbus server başlat:")
    logger.info("   python src/layer1_data_source/modbus_server.py\n")
    
    logger.info("4. Terminal 3'te OPC-UA client ile test et:")
    logger.info("   python scripts/test_opc_client.py\n")
    
    logger.info("5. Terminal 4'te Modbus client ile test et:")
    logger.info("   python scripts/test_modbus_client.py\n")
    
    logger.info("="*80)
    logger.info("✓ Test yapısını başlat!")
    logger.info("="*80)


if __name__ == "__main__":
    main()
