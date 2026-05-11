import numpy as np
import pandas as pd
import psycopg2
import paho.mqtt.publish as publish

class AnalyticsEngine:
    def __init__(self, db_config, mqtt_config):
        self.db_config = db_config
        self.mqtt_config = mqtt_config

    def fetch_data(self):
        conn = psycopg2.connect(**self.db_config)
        df = pd.read_sql('SELECT * FROM sensor_data ORDER BY time DESC LIMIT 1000', conn)
        conn.close()
        return df

    def detect_anomalies(self, df):
        # Simple z-score anomaly detection
        df['zscore'] = (df['value'] - df['value'].mean()) / df['value'].std()
        anomalies = df[np.abs(df['zscore']) > 3]
        return anomalies

    def publish_anomalies(self, anomalies):
        for _, row in anomalies.iterrows():
            payload = row.to_json()
            publish.single(self.mqtt_config['topic'], payload, hostname=self.mqtt_config['host'])

    def run(self):
        df = self.fetch_data()
        anomalies = self.detect_anomalies(df)
        if not anomalies.empty:
            self.publish_anomalies(anomalies)
