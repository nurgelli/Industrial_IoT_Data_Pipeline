# Layer 9: Analytics & Machine Learning

This layer performs analytics and machine learning on cleaned SCADA data from TimescaleDB. It detects anomalies and publishes results to MQTT for further processing or alerting.

## Main Components

- `analytics_engine.py`: Fetches data, runs anomaly detection, publishes results.
- `test_layer9.py`: Test script for analytics pipeline.

## Configuration

- Database and MQTT settings are provided in the script or can be moved to `settings.yaml`.

## Extending

- Add more analytics/ML models in `analytics_engine.py`.
- Integrate with alerting or dashboard layers as needed.
