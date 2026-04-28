from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

DB_PATH = "sensor_data.db"

app = Flask(__name__)
CORS(app)


# ---------- DB helpers ----------

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Reading tabell
def init_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                temperature REAL,
                humidity REAL,
                uptime_s INTEGER,
                rssi INTEGER,
                soil_raw INTEGER,
                soil_pct INTEGER,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                last_seen TEXT,
                last_rssi INTEGER,
                last_uptime_s INTEGER
            )
        """)


def to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def to_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat()


# ---------- Routes ----------

#Heartbeat
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    payload = request.get_json(silent=True) or {}

    device_id = str(payload.get("device_id") or "nano33iot-1")
    uptime_s = to_int(payload.get("uptime_s"))
    rssi = to_int(payload.get("rssi"))
    now = now_local_iso()

    with db_connect() as conn:
        conn.execute("""
            INSERT INTO devices (device_id, last_seen, last_rssi, last_uptime_s)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                last_seen=excluded.last_seen,
                last_rssi=excluded.last_rssi,
                last_uptime_s=excluded.last_uptime_s
        """, (device_id, now, rssi, uptime_s))

    return jsonify({"status": "ok"}), 200

@app.route("/devices", methods=["GET"])
def devices():
    with db_connect() as conn:
        rows = conn.execute("""
            SELECT device_id, last_seen, last_rssi, last_uptime_s
            FROM devices
        """).fetchall()

    return jsonify([dict(r) for r in rows])

@app.route("/data", methods=["POST"])
def receive_data():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}

    device_id = str(payload.get("device_id") or "nano33iot-1")
    temperature = to_float(payload.get("temperature"))
    humidity = to_float(payload.get("humidity"))
    uptime_s = to_int(payload.get("uptime_s"))
    rssi = to_int(payload.get("rssi"))
    soil_raw = to_int(payload.get("soil_raw"))
    soil_pct = to_int(payload.get("soil_pct"))
    created_at = now_local_iso()

    if temperature is None or humidity is None:
        return jsonify({"error": "temperature and humidity required"}), 400

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO readings
              (device_id, temperature, humidity, uptime_s, rssi, soil_raw, soil_pct, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (device_id, temperature, humidity, uptime_s, rssi, soil_raw, soil_pct, created_at),
        )

    with db_connect() as conn:
        conn.execute("""
            INSERT INTO devices (device_id, last_seen, last_rssi, last_uptime_s)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                last_seen=excluded.last_seen,
                last_rssi=excluded.last_rssi,
                last_uptime_s=excluded.last_uptime_s
        """, (device_id, created_at, rssi, uptime_s))

    print(
        f"Saved: {device_id} "
        f"T={temperature} H={humidity} uptime_s={uptime_s} "
        f"rssi={rssi} soil_raw={soil_raw} soil_pct={soil_pct} at {created_at}"
    )
    return jsonify({"status": "ok"}), 200


def fetch_latest_row() -> Optional[sqlite3.Row]:
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT device_id, temperature, humidity, uptime_s, rssi, soil_raw, soil_pct, created_at
            FROM readings
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


@app.route("/latest", methods=["GET"])
def latest():
    row = fetch_latest_row()
    if not row:
        return jsonify({"error": "no data yet"}), 404
    return jsonify(dict(row))


@app.route("/history", methods=["GET"])
def history():
    try:
        n = int(request.args.get("limit", 50))
    except ValueError:
        n = 50
    n = max(1, min(n, 500))

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT device_id, temperature, humidity, uptime_s, rssi, soil_raw, soil_pct, created_at
            FROM readings
            ORDER BY id DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()

    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
