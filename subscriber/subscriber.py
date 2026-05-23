"""
Step 1: MQTT Subscriber - Subscribes to energy/meters/# and stores data in PostgreSQL
"""

import json
import logging
import signal
import sys
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import execute_batch

# ── Configuration ──────────────────────────────────────────────────────────────
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_TOPIC    = "energy/meters/#"
MQTT_USERNAME = ""           # set if EMQX auth is enabled
MQTT_PASSWORD = ""

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "energy_db",
    "user":     "postgres",
    "password": "postgres",
}

BATCH_SIZE = 100             # flush to DB every N messages
# ───────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Global state
db_conn  = None
db_cur   = None
buffer   = []


# ── Database helpers ────────────────────────────────────────────────────────────

def connect_db():
    global db_conn, db_cur
    db_conn = psycopg2.connect(**DB_CONFIG)
    db_conn.autocommit = False
    db_cur  = db_conn.cursor()
    log.info("Connected to PostgreSQL.")


def create_table():
    """Create energy_readings table (plain PostgreSQL table – Step 1)."""
    db_cur.execute("""
        CREATE TABLE IF NOT EXISTS energy_readings (
            id        BIGSERIAL,
            meter_id  CHAR(10)         NOT NULL,
            timestamp TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
            power     DOUBLE PRECISION NOT NULL,   -- watts
            voltage   DOUBLE PRECISION NOT NULL,   -- volts
            current   DOUBLE PRECISION NOT NULL,   -- amps
            frequency DOUBLE PRECISION NOT NULL,   -- Hz
            energy    DOUBLE PRECISION NOT NULL    -- kWh (cumulative)
        );
    """)
    db_cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_energy_readings_ts
            ON energy_readings (timestamp DESC);
    """)
    db_cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_energy_readings_meter
            ON energy_readings (meter_id, timestamp DESC);
    """)
    db_conn.commit()
    log.info("Table 'energy_readings' ready.")


def flush_buffer():
    global buffer
    if not buffer:
        return
    try:
        execute_batch(
            db_cur,
            """
            INSERT INTO energy_readings
                (meter_id, timestamp, power, voltage, current, frequency, energy)
            VALUES
                (%(meter_id)s, %(timestamp)s, %(power)s,
                 %(voltage)s, %(current)s, %(frequency)s, %(energy)s)
            """,
            buffer,
            page_size=BATCH_SIZE,
        )
        db_conn.commit()
        log.info("Flushed %d rows to DB.", len(buffer))
    except Exception as exc:
        db_conn.rollback()
        log.error("DB flush failed: %s", exc)
    finally:
        buffer = []


# ── MQTT callbacks ──────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to EMQX broker.")
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("Subscribed to '%s'.", MQTT_TOPIC)
    else:
        log.error("MQTT connection failed, rc=%d", rc)


def on_message(client, userdata, msg):
    global buffer
    try:
        payload = json.loads(msg.payload.decode("utf-8"))

        # Extract meter_id from topic  energy/meters/{meter_id}
        meter_id = msg.topic.split("/")[-1].zfill(10)

        row = {
            "meter_id":  meter_id,
            "timestamp": payload.get("timestamp", datetime.utcnow().isoformat()),
            "power":     float(payload["power"]),
            "voltage":   float(payload["voltage"]),
            "current":   float(payload["current"]),
            "frequency": float(payload["frequency"]),
            "energy":    float(payload["energy"]),
        }
        buffer.append(row)

        if len(buffer) >= BATCH_SIZE:
            flush_buffer()

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        log.warning("Bad message on %s: %s | %s", msg.topic, exc, msg.payload[:120])


def on_disconnect(client, userdata, rc):
    log.warning("Disconnected from broker (rc=%d). Will auto-reconnect.", rc)


# ── Graceful shutdown ───────────────────────────────────────────────────────────

def shutdown(signum, frame):
    log.info("Shutting down subscriber …")
    flush_buffer()
    if db_conn:
        db_conn.close()
    sys.exit(0)


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    connect_db()
    create_table()

    client = mqtt.Client(client_id="energy_subscriber", clean_session=True)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
