# Smart Energy Grid Monitoring System

> Group Project – Due Sunday, May 23, 2026

## Quick Start (5 commands)

```bash
# 1. Start EMQX + TimescaleDB
docker-compose up -d

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start the MQTT subscriber (leave running in a terminal)
python subscriber/subscriber.py

# 4. Load 4 weeks of historical data (~8.4 M rows)
python simulator/simulator.py historical --weeks 4

# 5. Launch the dashboard
python dashboard/dashboard.py
# Open http://localhost:8050
```

---

## File Structure

```
smart_energy_grid/
├── docker-compose.yml          ← EMQX 5.6 + TimescaleDB 16
├── requirements.txt            ← paho-mqtt, psycopg2, dash, plotly, pandas
│
├── sql/
│   ├── create_db.sql           ← Step 0: DB creation (auto-run by Docker)
│   └── setup_timescaledb.sql   ← Steps 3–6: hypertables, compression, CAGs
│
├── subscriber/
│   └── subscriber.py           ← Step 1: MQTT → PostgreSQL bridge
│
├── simulator/
│   └── simulator.py            ← Step 2: realistic meter data generator
│
├── db/
│   └── benchmark.py            ← Steps 3–6: automated perf benchmarking
│
├── dashboard/
│   └── dashboard.py            ← Step 7: Plotly Dash analytics dashboard
│
└── docs/
    └── generate_report.js      ← Generates the technical report .docx
```

---

## Step-by-Step Guide

### Step 1 – MQTT Subscriber
```bash
python subscriber/subscriber.py
```
Subscribes to `energy/meters/#` on EMQX, batches rows of 100, and inserts into the `energy_readings` PostgreSQL table.

### Step 2 – Data Simulator

**Live mode** (real-time, 5-min ticks):
```bash
python simulator/simulator.py live --hours 1 --meters 1000
```

**Historical bulk load** (4 weeks ≈ 8.4 M rows):
```bash
python simulator/simulator.py historical --weeks 4 --meters 1000
```

### Steps 3–6 – TimescaleDB Setup & Analysis
```bash
# Connect to the DB and run all SQL
psql -U postgres -d energy_db -f sql/setup_timescaledb.sql

# Then run the automated benchmark
python db/benchmark.py
```
The benchmark outputs a formatted table comparing execution times across 3-hour, 1-day, and 1-week chunk configurations, pre/post compression, and raw vs continuous aggregate query performance.

### Step 7 – Dashboard
```bash
python dashboard/dashboard.py
```
Open http://localhost:8050

Panels:
- Real-time readings (last 1 hour, 5-min buckets)
- Today vs yesterday hourly comparison
- 7-day weekly power trend
- Monthly kWh by region (meter first digit)
- Query performance: raw data vs continuous aggregates
- Disk usage comparison across hypertable configurations
- Recent chunk information table

---

## DB Connection Settings

Edit the `DB_CONFIG` dict in any Python file to match your environment:

```python
DB_CONFIG = dict(
    host="localhost", port=5432,
    dbname="energy_db", user="postgres", password="postgres"
)
```

If running without Docker, ensure TimescaleDB extension is installed and run:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

---

## Deliverables Checklist

- [x] `subscriber/subscriber.py` – MQTT subscriber with PostgreSQL storage
- [x] `simulator/simulator.py` – 1000-meter simulator with realistic patterns
- [x] `sql/setup_timescaledb.sql` – All hypertable, compression, CAG SQL
- [x] `db/benchmark.py` – Performance measurement script
- [x] `dashboard/dashboard.py` – Full analytics dashboard (Dash)
- [x] `docker-compose.yml` – Reproducible infrastructure
- [ ] `docs/Technical_Report.pdf` – Fill in benchmark results, add screenshots
- [ ] GitHub repository with all code pushed
