import os
import yaml
from analytics_engine import AnalyticsEngine

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def test_anomaly_detection():
    config_path = os.getenv('ANALYTICS_TEST_CONFIG', 'test_layer9_config.yaml')
    if os.path.exists(config_path):
        config = load_config(config_path)
        db_config = config['postgres']
        mqtt_config = config['mqtt']
    else:
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'user': 'postgres',
            'password': 'postgres_pwd',
            'dbname': 'scada_prod'
        }
        mqtt_config = {
            'host': 'localhost',
            'topic': 'scada/analytics/anomalies'
        }
    engine = AnalyticsEngine(db_config, mqtt_config)
    df = engine.fetch_data()
    anomalies = engine.detect_anomalies(df)
    print(f"Detected {len(anomalies)} anomalies.")

if __name__ == '__main__':
    test_anomaly_detection()
