"""
Step 2: Smart Meter Data Simulator
Generates realistic energy data for 1000+ meters and publishes via MQTT.
Supports both live mode (5-min intervals) and historical bulk loading.
"""

import json
import logging
import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List

import paho.mqtt.client as mqtt

# ── Configuration ──────────────────────────────────────────────────────────────
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_USERNAME = ""
MQTT_PASSWORD = ""

NUM_METERS    = 1000          # number of smart meters
REPORT_EVERY  = 300           # seconds between readings (5 minutes)
TOPIC_PREFIX  = "energy/meters"
QOS           = 1
# ───────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ── Meter ID generation ─────────────────────────────────────────────────────────

def generate_meter_ids(n: int) -> List[str]:
    """Generate n unique 10-digit meter IDs spread across 9 regions (1-9 prefix)."""
    ids = set()
    region = 1
    while len(ids) < n:
        meter_id = str(random.randint(10 ** 8, 10 ** 9 - 1))
        # Force first digit to cycle across regions 1-9
        meter_id = str(region) + meter_id[1:]
        ids.add(meter_id)
        region = (region % 9) + 1
    return sorted(ids)


# ── Realistic power model ───────────────────────────────────────────────────────

# Base load profile: hourly multipliers (index 0 = midnight)
HOURLY_PROFILE = [
    0.40, 0.35, 0.30, 0.28, 0.27, 0.30,   # 00-05 (low night)
    0.45, 0.70, 0.90, 0.85, 0.80, 0.78,   # 06-11 (morning ramp)
    0.75, 0.72, 0.70, 0.72, 0.78, 0.95,   # 12-17 (afternoon)
    1.00, 0.98, 0.92, 0.80, 0.65, 0.50,   # 18-23 (evening peak)
]

# Per-meter characteristics (set once, stable across time)
METER_CONFIGS = {}

def init_meter_configs(meter_ids: List[str]):
    for mid in meter_ids:
        METER_CONFIGS[mid] = {
            "base_power":    random.uniform(1_000, 8_000),   # W
            "voltage_base":  random.uniform(228, 232),        # V ≈ 230 V nominal
            "freq_base":     random.uniform(49.98, 50.02),    # Hz
            "noise_factor":  random.uniform(0.05, 0.15),
            "energy_accum":  random.uniform(0, 50_000),       # kWh starting offset
        }


def power_at(meter_id: str, ts: datetime) -> dict:
    """Return a realistic meter reading for a given timestamp."""
    cfg = METER_CONFIGS[meter_id]

    hour        = ts.hour + ts.minute / 60.0
    hour_idx    = int(ts.hour) % 24
    base_mult   = HOURLY_PROFILE[hour_idx]

    # Smooth sinusoidal noise within the hour
    intra_noise = math.sin(math.pi * ts.minute / 30) * 0.05

    # Random short-term fluctuation
    rand_noise  = random.gauss(0, cfg["noise_factor"])

    mult  = max(0.1, base_mult + intra_noise + rand_noise)
    power = cfg["base_power"] * mult

    voltage   = cfg["voltage_base"] + random.gauss(0, 0.5)
    frequency = cfg["freq_base"]    + random.gauss(0, 0.01)
    current   = power / voltage if voltage else 0

    # Energy: kWh accumulated (power W × 5 min = W·h / 1000)
    cfg["energy_accum"] += (power * REPORT_EVERY) / 3_600_000
    energy = round(cfg["energy_accum"], 4)

    return {
        "meter_id":  meter_id,
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "power":     round(power, 2),
        "voltage":   round(voltage, 2),
        "current":   round(current, 4),
        "frequency": round(frequency, 3),
        "energy":    energy,
    }


# ── MQTT helpers ────────────────────────────────────────────────────────────────

def make_client() -> mqtt.Client:
    client = mqtt.Client(client_id="energy_simulator", clean_session=True)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def publish_reading(client: mqtt.Client, reading: dict):
    topic   = f"{TOPIC_PREFIX}/{reading['meter_id']}"
    payload = json.dumps(reading)
    client.publish(topic, payload, qos=QOS)


# ── Live simulation (1 hour test, 5-min ticks) ─────────────────────────────────

def run_live(duration_hours: float = 1.0):
    """Publish live readings for all meters, one tick every 5 minutes."""
    meter_ids = generate_meter_ids(NUM_METERS)
    init_meter_configs(meter_ids)
    client    = make_client()

    ticks     = int(duration_hours * 3600 / REPORT_EVERY)
    log.info("Live simulation: %d meters × %d ticks (~%.0f hours)",
             NUM_METERS, ticks, duration_hours)

    for tick in range(ticks):
        ts    = datetime.now(timezone.utc)
        count = 0
        for mid in meter_ids:
            reading = power_at(mid, ts)
            publish_reading(client, reading)
            count += 1

        log.info("Tick %d/%d — published %d readings at %s",
                 tick + 1, ticks, count, ts.strftime("%H:%M:%S"))
        time.sleep(REPORT_EVERY)

    client.loop_stop()
    client.disconnect()
    log.info("Live simulation complete.")


# ── Historical bulk load (4 weeks) ─────────────────────────────────────────────

def run_historical(weeks: int = 4, batch_log_every: int = 10_000):
    """
    Generate 4 weeks of historical data and publish as fast as possible.
    Approx rows: 1000 meters × (4w × 7d × 24h × 12 readings/h) ≈ 8.06 M rows.
    """
    meter_ids = generate_meter_ids(NUM_METERS)
    init_meter_configs(meter_ids)
    client    = make_client()

    end_ts   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # align to nearest 5-min
    end_ts  -= timedelta(minutes=end_ts.minute % 5)
    start_ts = end_ts - timedelta(weeks=weeks)

    total_ticks = int((end_ts - start_ts).total_seconds() / REPORT_EVERY)
    total_rows  = total_ticks * len(meter_ids)
    log.info("Historical load: %d meters × %d ticks = ~%s rows",
             len(meter_ids), total_ticks, f"{total_rows:,}")

    published = 0
    ts = start_ts
    while ts < end_ts:
        for mid in meter_ids:
            reading = power_at(mid, ts)
            publish_reading(client, reading)
            published += 1
            if published % batch_log_every == 0:
                log.info("  Published %s / %s rows (%.1f%%)",
                         f"{published:,}", f"{total_rows:,}",
                         100 * published / total_rows)
        ts += timedelta(seconds=REPORT_EVERY)

    client.loop_stop()
    client.disconnect()
    log.info("Historical load complete — %s rows published.", f"{published:,}")


# ── CLI ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Smart Meter Simulator")
    sub    = parser.add_subparsers(dest="mode", required=True)

    live_p = sub.add_parser("live", help="Live simulation (default 1 hour)")
    live_p.add_argument("--hours",   type=float, default=1.0,
                        help="Duration in hours (default 1)")
    live_p.add_argument("--meters",  type=int,   default=NUM_METERS)

    hist_p = sub.add_parser("historical", help="Bulk historical load")
    hist_p.add_argument("--weeks",   type=int,   default=4)
    hist_p.add_argument("--meters",  type=int,   default=NUM_METERS)

    args = parser.parse_args()
    NUM_METERS = args.meters

    if args.mode == "live":
        run_live(duration_hours=args.hours)
    else:
        run_historical(weeks=args.weeks)
