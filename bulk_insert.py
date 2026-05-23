#!/usr/bin/env python3
"""
Direct bulk insert — loads 4 weeks of smart meter data
straight into PostgreSQL, bypassing MQTT entirely.
"""
import psycopg2
import random
import math
from datetime import datetime, timezone, timedelta

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "energy_db",
    "user": "postgres",
    "password": "postgres",
}

NUM_METERS   = 1000
WEEKS        = 4
INTERVAL_MIN = 5
BATCH_SIZE   = 10000

def get_meter_ids(n):
    random.seed(42)
    return [str(random.randint(1000000000, 9999999999)) for _ in range(n)]

def power_factor(hour):
    """Realistic load curve: peaks at 8am and 7pm."""
    morning = math.exp(-0.5 * ((hour - 8) / 2) ** 2)
    evening = math.exp(-0.5 * ((hour - 19) / 2) ** 2)
    base    = 0.2
    return base + 0.5 * morning + 0.8 * evening

def generate_reading(meter_id, ts):
    hour   = ts.hour + ts.minute / 60
    factor = power_factor(hour)
    power   = round(random.gauss(3000 * factor + 500, 200), 2)
    power   = max(100, power)
    voltage = round(random.gauss(230, 2), 2)
    current = round(power / voltage, 2)
    freq    = round(random.gauss(50, 0.05), 3)
    energy  = round(power * INTERVAL_MIN / 60, 4)
    return (meter_id, ts, power, voltage, current, freq, energy)

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Find the latest timestamp already in the DB
    cur.execute("SELECT MAX(timestamp) FROM energy_readings;")
    row = cur.fetchone()
    if row[0]:
        start = row[0] + timedelta(minutes=INTERVAL_MIN)
        print(f"Resuming from {start}")
    else:
        start = datetime.now(timezone.utc) - timedelta(weeks=WEEKS)
        print(f"Starting fresh from {start}")

    end   = datetime.now(timezone.utc)
    meter_ids = get_meter_ids(NUM_METERS)

    # Build list of timestamps
    ts = start
    timestamps = []
    while ts <= end:
        timestamps.append(ts)
        ts += timedelta(minutes=INTERVAL_MIN)

    total = len(timestamps) * NUM_METERS
    print(f"Inserting {total:,} rows ({len(timestamps)} ticks × {NUM_METERS} meters)…")

    batch  = []
    done   = 0

    for tick_ts in timestamps:
        for meter_id in meter_ids:
            batch.append(generate_reading(meter_id, tick_ts))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(
                    """INSERT INTO energy_readings
                       (meter_id, timestamp, power, voltage, current, frequency, energy)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    batch
                )
                conn.commit()
                done += len(batch)
                batch = []
                pct = done / total * 100
                print(f"  Inserted {done:,} / {total:,} ({pct:.1f}%)")

    if batch:
        cur.executemany(
            """INSERT INTO energy_readings
               (meter_id, timestamp, power, voltage, current, frequency, energy)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            batch
        )
        conn.commit()
        done += len(batch)

    print(f"Done — {done:,} rows inserted.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
