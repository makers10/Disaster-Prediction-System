# Disaster Prediction System

An AI-powered, event-driven platform that ingests multi-source environmental data to predict floods, heatwaves, droughts, landslides, and cyclones. It delivers risk assessments, probabilistic forecasts, and time-to-impact estimates to citizens, governments, and emergency responders through alerts, dashboards, and a conversational AI interface.

## Architecture

The system follows a microservices pattern with Apache Kafka as the central event bus. Services communicate asynchronously via Kafka topics for high-throughput data flows, and synchronously via REST/gRPC for query-response patterns.

```
services/
├── data-ingestion/       # Go — sensor, satellite, weather, historical data ingestion
├── prediction-engine/    # Python — SSM + Transformer + GNN ensemble prediction
├── alert-service/        # TypeScript — SMS, push, and voice alert dispatch
├── dashboard-service/    # TypeScript — REST API + React SPA live map
├── xai-module/           # Python — SHAP-based explainability
├── crowd-report/         # TypeScript — user-submitted disaster reports
├── evacuation-planner/   # Python — Dijkstra/A* evacuation route computation
└── smart-infra-alerter/  # Python — infrastructure asset alert generation

shared/
├── types/index.ts        # TypeScript interfaces for all data models
└── schemas/              # JSON Schema files for Kafka topic payloads
```

## Prerequisites

- Docker and Docker Compose
- Go 1.21+
- Python 3.11+
- Node.js 20+

## Starting the Infrastructure Stack

```bash
docker compose up -d
```

This starts:
- Apache Kafka (port 9092) with Zookeeper
- PostgreSQL 15 (port 5432) — relational data store
- InfluxDB 2.7 (port 8086) — time-series prediction data
- Redis 7 (port 6379) — caching layer
- kafka-init — creates all required Kafka topics on startup

### Kafka Topics

| Topic | Partitions | Description |
|---|---|---|
| `raw.sensor.reading` | 6 | Raw IoT sensor readings |
| `raw.weather.forecast` | 3 | Raw weather API forecasts |
| `validated.sensor.reading` | 6 | Validated and normalized sensor readings |
| `prediction.generated` | 6 | Disaster risk predictions from the engine |
| `alert.dispatched` | 3 | Dispatched alert records |
| `features.satellite.cnn` | 3 | CNN-extracted satellite features |
| `crowd.report.submitted` | 3 | User-submitted crowd reports |
| `evacuation.route.updated` | 3 | Computed/updated evacuation routes |
| `satellite.feed.unavailable` | 1 | Satellite feed unavailability events |
| `crowd.report.threshold.exceeded` | 3 | Crowd report threshold trigger events |

## Running Individual Services

### Data Ingestion (Go)
```bash
cd services/data-ingestion
go run main.go
```

### Prediction Engine (Python)
```bash
cd services/prediction-engine
pip install -r requirements.txt
python main.py
```

### Alert Service (TypeScript)
```bash
cd services/alert-service
npm install
npm run dev
```

### Dashboard Service (TypeScript)
```bash
cd services/dashboard-service
npm install
npm run dev
```

### XAI Module (Python)
```bash
cd services/xai-module
pip install -r requirements.txt
python main.py
```

### Crowd Report Service (TypeScript)
```bash
cd services/crowd-report
npm install
npm run dev
```

### Evacuation Planner (Python)
```bash
cd services/evacuation-planner
pip install -r requirements.txt
python main.py
```

### Smart Infrastructure Alerter (Python)
```bash
cd services/smart-infra-alerter
pip install -r requirements.txt
python main.py
```

## Stopping the Stack

```bash
docker compose down
```

To also remove persistent volumes:
```bash
docker compose down -v
```

## Delivery Phases

- **Phase 1**: Sensor + weather ingestion, flood/heatwave prediction, SMS/app alerts, live map dashboard
- **Phase 2**: All 5 disaster types, multi-language, voice alerts, historical dashboard, conversational AI
- **Phase 3**: Satellite imagery + CNN, XAI explanations, crowd reporting
- **Phase 4**: GNN propagation, evacuation planning, smart infrastructure alerts, government data feeds
