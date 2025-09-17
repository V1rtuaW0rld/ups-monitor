from flask import Flask, render_template, jsonify, request
from dateutil.parser import isoparse
import sqlite3
import subprocess
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Europe/Paris"))
import sqlite3

conso_buffer = []
last_minute = None

app = Flask(__name__)

def insert_conso(timestamp, watts):
    conn = sqlite3.connect("data/conso.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO conso (timestamp, watts) VALUES (?, ?)", (timestamp, watts))
    conn.commit()
    conn.close()

def get_ups_data():
    global conso_buffer, last_minute

    try:
        result = subprocess.run(
            ["upsc", "ups@192.168.0.3"],
            capture_output=True,
            text=True,
            timeout=5
        )

        data = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()

        # 🔋 Si l'onduleur est sur batterie, on enregistre l'heure
        if data.get("ups.status") == "OB":
            timestamp = datetime.now().astimezone().isoformat()
            with open("last_ob.json", "w") as f:
                json.dump({"last_ob": timestamp}, f)

        # ⚡ Calcul de la conso estimée
        try:
            nominalVA = int(data.get("ups.power.nominal", "0"))
            loadPercent = int(data.get("ups.load", "0"))
        except ValueError:
            nominalVA = 0
            loadPercent = 0
        factor = 0.7  # ou dynamique si tu veux
        va = nominalVA * (loadPercent / 100)
        watts = round(va * factor)

        # 🕒 Timestamp minute
        now = datetime.now().astimezone()
        current_minute = now.replace(second=0, microsecond=0)

        conso_buffer.append(watts)

        # ⏱️ Si on change de minute → on insère la moyenne
        if last_minute and current_minute != last_minute:
            avg = sum(conso_buffer) / len(conso_buffer)
            insert_conso(last_minute.isoformat(), round(avg))
            conso_buffer = []

        last_minute = current_minute

        return data

    except Exception as e:
        return {"error": str(e)}



@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/ups")
def ups_api():
    return jsonify(get_ups_data())

@app.route("/api/last-ob")
def last_ob():
    if os.path.exists("last_ob.json"):
        with open("last_ob.json") as f:
            return jsonify(json.load(f))
    else:
        return jsonify({"last_ob": None})


@app.route("/api/conso")
def conso():
    import sqlite3
    import time
    from dateutil.parser import isoparse
    from flask import request, jsonify

    range_map = {
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "8h": 28800,
        "24h": 86400,
        "48h": 172800,
        "7d": 604800,
        "14d": 1209600,
        "30d": 2592000
    }

    range_key = request.args.get("range", "1h")
    delta = range_map.get(range_key, 3600)
    now = time.time()
    cutoff = now - delta

    conn = sqlite3.connect("data/conso.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, watts FROM conso ORDER BY timestamp ASC")
    rows = cursor.fetchall()
    conn.close()

    filtered = []
    for ts, w in rows:
        try:
            t = isoparse(ts).timestamp()
            if t >= cutoff:
                filtered.append({"timestamp": ts, "watts": float(w)})
        except:
            continue

    return jsonify(filtered)


@app.route("/api/value", methods=["GET"])
def get_value():
    try:
        with open("data/value.json") as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({"price_per_kwh": 0.26, "currency": "€"})

@app.route("/api/save-value", methods=["POST"])
def save_value():
    try:
        data = json.loads(request.data)
        with open("data/value.json", "w") as f:
            json.dump(data, f)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/avg-monthly-cost")
def avg_monthly_cost():
    path = "data/conso.db"
    if not os.path.exists(path):
        return jsonify({"kwh": 0, "cost": 0, "unit": "€"})

    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, watts FROM conso ORDER BY timestamp ASC")
    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return jsonify({"kwh": 0, "cost": 0, "unit": "€"})

    total_kwh = 0
    for i in range(1, len(rows)):
        try:
            t1 = isoparse(rows[i-1][0]).timestamp()
            t2 = isoparse(rows[i][0]).timestamp()
        except Exception:
            continue  # ignore malformed timestamps

        w = float(rows[i][1])
        dt_hours = (t2 - t1) / 3600
        total_kwh += (w / 1000) * dt_hours

    try:
        t_start = isoparse(rows[0][0]).timestamp()
        t_end = isoparse(rows[-1][0]).timestamp()
        duration_hours = (t_end - t_start) / 3600
    except Exception:
        return jsonify({"kwh": 0, "cost": 0, "unit": "€"})

    if duration_hours == 0:
        return jsonify({"kwh": 0, "cost": 0, "unit": "€"})

    kwh_per_month = total_kwh * (24 * 30 / duration_hours)

    try:
        with open("data/value.json") as f:
            value = json.load(f)
            price = float(value.get("price_per_kwh", 0.26))
            unit = value.get("currency", "€")
    except:
        price = 0.26
        unit = "€"

    cost = kwh_per_month * price
    return jsonify({
        "kwh": round(kwh_per_month, 2),
        "cost": round(cost, 2),
        "unit": unit
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010)