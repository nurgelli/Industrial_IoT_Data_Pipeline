# Grafana Integration (Step 7)

## Overview

Grafana is used for real-time visualization and monitoring of SCADA pipeline data. It connects to TimescaleDB and provides dashboards for sensor and process data.

## Usage

- Access Grafana at: http://localhost:3000
- Default credentials: `admin` / `admin`
- The TimescaleDB datasource and a sample dashboard are provisioned automatically.

## Customization

- Add more dashboards in `grafana/provisioning/dashboards/`.
- Edit the datasource config in `grafana/provisioning/datasources/timescaledb.yaml`.

## Troubleshooting

- Ensure TimescaleDB is running and accessible.
- Check container logs for errors: `docker logs scada_grafana`

## Next Steps

- Extend dashboards for analytics, ML, and alerting in later steps.
