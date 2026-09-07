import os
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, jsonify, request

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import nut_client

# Environment variables
TIMEZONE_STR = os.environ.get("TIMEZONE", "Europe/Paris")
UPS_HOST = os.environ.get("UPS_HOST", "ups@192.168.0.3")
PORT = int(os.environ.get("PORT", 5010))

app = Flask(__name__)
app.json.ensure_ascii = False

# In-memory shared state for high-performance non-blocking reads
_state_lock = threading.Lock()
_cached_metrics = None
_last_polled_time = 0
_conso_buffer = []
_last_minute_str = None

def get_current_time():
    try:
        return datetime.now(ZoneInfo(TIMEZONE_STR))
    except Exception:
        return datetime.now().astimezone()

def background_poller_worker():
    """
    Background worker that runs 24/7.
    Polls NUT every 5s, detects outages, averages watts per minute,
    and inserts into SQLite smoothly in WAL mode.
    """
    global _cached_metrics, _last_polled_time, _conso_buffer, _last_minute_str

    print(f"[*] Background UPS poller started for {UPS_HOST} (Timezone: {TIMEZONE_STR})")
    
    # Ensure tables exist
    try:
        db.init_db()
    except Exception as e:
        print(f"[!] Warning on db init: {e}")

    while True:
        try:
            cfg = db.get_saved_config()
            pf = cfg.get("power_factor", 0.7)
            
            # 1. Fetch metrics from NUT
            metrics = nut_client.get_ups_metrics(UPS_HOST, power_factor=pf)
            now_dt = get_current_time()
            iso_now = now_dt.isoformat()
            
            with _state_lock:
                _cached_metrics = metrics
                _last_polled_time = time.time()
                
            # 2. Outage tracking
            status = metrics.get("status", "OL")
            try:
                db.log_outage_event(status, iso_now)
            except Exception as oe:
                print(f"[!] Error logging outage: {oe}")

            # 3. Minute-averaging for consumption recording
            if metrics.get("success", False):
                watts = metrics.get("real_watts", 0)
                _conso_buffer.append(watts)
                
                # Check minute rollover
                current_minute_str = now_dt.strftime("%Y-%m-%dT%H:%M:00") + now_dt.strftime("%z")
                # Format with colon in timezone (+0200 -> +02:00)
                if len(current_minute_str) >= 5 and current_minute_str[-5] in ('+', '-'):
                    current_minute_str = current_minute_str[:-2] + ":" + current_minute_str[-2:]
                
                if _last_minute_str and current_minute_str != _last_minute_str:
                    if _conso_buffer:
                        avg_watts = round(sum(_conso_buffer) / len(_conso_buffer))
                        try:
                            db.insert_conso(_last_minute_str, avg_watts)
                        except Exception as de:
                            print(f"[!] Error recording conso: {de}")
                        _conso_buffer = []
                _last_minute_str = current_minute_str

        except Exception as err:
            print(f"[!] Poller loop error: {err}")

        time.sleep(5)

# Start poller daemon thread
poller_thread = threading.Thread(target=background_poller_worker, daemon=True)
poller_thread.start()

# --- WEB ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/ups")
def api_ups():
    """
    Returns instantaneous UPS metrics from in-memory cache.
    Zero DB locks, instant response.
    """
    global _cached_metrics
    with _state_lock:
        data = _cached_metrics

    if not data:
        cfg = db.get_saved_config()
        data = nut_client.get_ups_metrics(UPS_HOST, power_factor=cfg.get("power_factor", 0.7))

    return jsonify(data)

@app.route("/api/conso")
def api_conso():
    """
    Returns time series with automatic downsampling.
    Range parameter: 1h, 2h, 4h, 6h, 8h, 12h, 24h, 48h, 7d, 14d, 30d, 1y, all.
    """
    range_key = request.args.get("range", "24h")
    try:
        series = db.get_conso_series(range_key, timezone_str=TIMEZONE_STR)
        return jsonify(series)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def api_stats():
    """
    Returns energy stats (24h, 30d, all-time, projected costs).
    """
    try:
        cfg = db.get_saved_config()
        stats = db.get_energy_stats(
            price_per_kwh=cfg.get("price_per_kwh", 0.25),
            currency=cfg.get("currency", "€"),
            power_factor=cfg.get("power_factor", 0.7)
        )
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/outages")
def api_outages():
    """
    Returns recent power outages.
    """
    try:
        limit = int(request.args.get("limit", 10))
        outages = db.get_recent_outages(limit=limit)
        return jsonify(outages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    """
    Get or update user settings (kWh price, currency, power factor).
    """
    if request.method == "POST":
        try:
            req_data = request.get_json(force=True)
            current = db.get_saved_config()
            
            if "price_per_kwh" in req_data:
                current["price_per_kwh"] = float(req_data["price_per_kwh"])
            if "currency" in req_data:
                current["currency"] = str(req_data["currency"]).strip()
            if "power_factor" in req_data:
                current["power_factor"] = float(req_data["power_factor"])
                
            db.save_config(current)
            return jsonify({"status": "ok", "config": current})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    else:
        return jsonify(db.get_saved_config())

# Legacy compatibility endpoints
@app.route("/api/value", methods=["GET"])
def api_legacy_value():
    cfg = db.get_saved_config()
    return jsonify({"price_per_kwh": cfg["price_per_kwh"], "currency": cfg["currency"]})

@app.route("/api/save-value", methods=["POST"])
def api_legacy_save_value():
    try:
        req_data = request.get_json(force=True)
        current = db.get_saved_config()
        if "price_per_kwh" in req_data:
            current["price_per_kwh"] = float(req_data["price_per_kwh"])
        if "currency" in req_data:
            current["currency"] = str(req_data["currency"]).strip()
        db.save_config(current)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/last-ob")
def api_legacy_last_ob():
    outages = db.get_recent_outages(limit=1)
    if outages:
        return jsonify({"last_ob": outages[0]["start"]})
    return jsonify({"last_ob": None})

if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=PORT)
