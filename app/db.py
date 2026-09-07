import os
import sqlite3
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def get_db_path():
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "conso.db")
    # Search common relative locations
    for candidate in ["data/conso.db", "../data/conso.db", "/app/data/conso.db"]:
        if os.path.exists(os.path.dirname(candidate)) or os.path.exists(candidate):
            return candidate
    return "data/conso.db"

def get_config_path():
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "value.json")
    for candidate in ["data/value.json", "../data/value.json", "/app/data/value.json"]:
        if os.path.exists(os.path.dirname(candidate)) or os.path.exists(candidate):
            return candidate
    return "data/value.json"

def get_connection():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # High-concurrency pragmas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conso (
            timestamp TEXT PRIMARY KEY,
            watts INTEGER NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conso_timestamp ON conso(timestamp)")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coupures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start TEXT NOT NULL,
            end TEXT,
            duration_seconds INTEGER
        )
    """)
    # Migration if table already existed without duration_seconds
    columns = [c[1] for c in cursor.execute("PRAGMA table_info(coupures)").fetchall()]
    if "duration_seconds" not in columns:
        cursor.execute("ALTER TABLE coupures ADD COLUMN duration_seconds INTEGER")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_coupures_start ON coupures(start)")
    
    conn.commit()
    conn.close()

def insert_conso(timestamp, watts):
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO conso (timestamp, watts) VALUES (?, ?)", (timestamp, int(watts)))
        conn.commit()
    finally:
        conn.close()

def get_conso_series(range_key="24h", timezone_str="Europe/Paris"):
    """
    Returns time series with automatic downsampling based on range_key.
    Guarantees between 60 and 400 data points to prevent browser lag.
    """
    range_config = {
        "1h":  {"delta": 3600,     "bucket": 0},     # raw (60 pts)
        "2h":  {"delta": 7200,     "bucket": 0},     # raw (120 pts)
        "4h":  {"delta": 14400,    "bucket": 60},    # 1-min avg (240 pts)
        "6h":  {"delta": 21600,    "bucket": 60},    # 1-min avg (360 pts)
        "8h":  {"delta": 28800,    "bucket": 120},   # 2-min avg (240 pts)
        "12h": {"delta": 43200,    "bucket": 120},   # 2-min avg (360 pts)
        "24h": {"delta": 86400,    "bucket": 300},   # 5-min avg (288 pts)
        "48h": {"delta": 172800,   "bucket": 600},   # 10-min avg (288 pts)
        "7d":  {"delta": 604800,   "bucket": 1800},  # 30-min avg (336 pts)
        "14d": {"delta": 1209600,  "bucket": 3600},  # 1-hour avg (336 pts)
        "30d": {"delta": 2592000,  "bucket": 7200},  # 2-hour avg (360 pts)
        "1y":  {"delta": 31536000, "bucket": 86400}, # 1-day avg (365 pts)
        "all": {"delta": None,     "bucket": 86400}  # daily avg
    }
    
    cfg = range_config.get(range_key, range_config["24h"])
    delta = cfg["delta"]
    bucket = cfg["bucket"]
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Determine current time reference.
        # If DB has no records close to current real time (e.g. offline dev dataset),
        # fallback to latest recorded timestamp so user can still visualize their data!
        now_ts = int(time.time())
        latest_row = cursor.execute("SELECT MAX(timestamp) FROM conso").fetchone()
        latest_str = latest_row[0] if latest_row else None
        
        ref_ts = now_ts
        if latest_str:
            # Check if latest recorded timestamp is in the future or recent
            try:
                latest_epoch = cursor.execute("SELECT unixepoch(?)", (latest_str,)).fetchone()[0]
                if latest_epoch and (now_ts - latest_epoch > (delta if delta else 86400)):
                    # Database is from an older snapshot, use latest_epoch as reference
                    ref_ts = latest_epoch
            except Exception:
                pass

        if delta is not None:
            cutoff_epoch = ref_ts - delta
        else:
            cutoff_epoch = 0
            
        if bucket == 0:
            # Raw measurements (1h / 2h)
            query = """
                SELECT timestamp, watts, watts as min_watts, watts as max_watts
                FROM conso
                WHERE unixepoch(timestamp) >= ?
                ORDER BY timestamp ASC
            """
            rows = cursor.execute(query, (cutoff_epoch,)).fetchall()
            return [
                {
                    "timestamp": r["timestamp"],
                    "watts": r["watts"],
                    "min_watts": r["min_watts"],
                    "max_watts": r["max_watts"]
                }
                for r in rows
            ]
        else:
            # Bucketed aggregation
            query = f"""
                SELECT 
                    datetime((unixepoch(timestamp) / {bucket}) * {bucket}, 'unixepoch') as bucket_time,
                    ROUND(AVG(watts), 1) as avg_watts,
                    MIN(watts) as min_watts,
                    MAX(watts) as max_watts
                FROM conso
                WHERE unixepoch(timestamp) >= ?
                GROUP BY (unixepoch(timestamp) / {bucket})
                ORDER BY bucket_time ASC
            """
            rows = cursor.execute(query, (cutoff_epoch,)).fetchall()
            return [
                {
                    "timestamp": r["bucket_time"] + "+00:00",
                    "watts": r["avg_watts"],
                    "min_watts": r["min_watts"],
                    "max_watts": r["max_watts"]
                }
                for r in rows
            ]
    finally:
        conn.close()

def get_energy_stats(price_per_kwh=0.25, currency="€", power_factor=0.7):
    """
    Computes summary energy statistics in milliseconds using SQL aggregations.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        now_ts = int(time.time())
        latest_row = cursor.execute("SELECT MAX(timestamp) FROM conso").fetchone()
        latest_str = latest_row[0] if latest_row else None
        ref_ts = now_ts
        if latest_str:
            try:
                latest_epoch = cursor.execute("SELECT unixepoch(?)", (latest_str,)).fetchone()[0]
                if latest_epoch and (now_ts - latest_epoch > 86400):
                    ref_ts = latest_epoch
            except Exception:
                pass

        # 24h stats
        day_epoch = ref_ts - 86400
        stats_24h = cursor.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(watts) as avg_watts,
                MIN(watts) as min_watts,
                MAX(watts) as max_watts,
                SUM(watts) as sum_watts
            FROM conso
            WHERE unixepoch(timestamp) >= ?
        """, (day_epoch,)).fetchone()
        
        # 30d stats
        month_epoch = ref_ts - (30 * 86400)
        stats_30d = cursor.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(watts) as avg_watts,
                SUM(watts) as sum_watts
            FROM conso
            WHERE unixepoch(timestamp) >= ?
        """, (month_epoch,)).fetchone()
        
        # All time stats
        stats_all = cursor.execute("""
            SELECT 
                COUNT(*) as count,
                MIN(timestamp) as min_ts,
                MAX(timestamp) as max_ts,
                SUM(watts) as sum_watts
            FROM conso
        """, ()).fetchone()
        
        # 1 minute = 1/60 hr -> kWh = sum(watts) / 60 / 1000 = sum(watts) / 60000
        kwh_24h = round((stats_24h["sum_watts"] or 0) / 60000.0, 2)
        cost_24h = round(kwh_24h * price_per_kwh, 2)
        
        avg_watts_recent = stats_24h["avg_watts"] or stats_30d["avg_watts"] or 0
        # Projected monthly kWh = avg_watts * 24 * 30 / 1000
        projected_monthly_kwh = round((avg_watts_recent * 24 * 30) / 1000.0, 1)
        projected_monthly_cost = round(projected_monthly_kwh * price_per_kwh, 2)
        
        # Projected yearly kWh = projected_monthly_kwh * 12
        projected_yearly_kwh = round(projected_monthly_kwh * 12.16, 1)
        projected_yearly_cost = round(projected_yearly_kwh * price_per_kwh, 2)
        
        total_kwh = round((stats_all["sum_watts"] or 0) / 60000.0, 1)
        total_cost = round(total_kwh * price_per_kwh, 2)

        return {
            "avg_watts_24h": round(stats_24h["avg_watts"] or 0, 1),
            "min_watts_24h": stats_24h["min_watts"] or 0,
            "max_watts_24h": stats_24h["max_watts"] or 0,
            "kwh_24h": kwh_24h,
            "cost_24h": cost_24h,
            "projected_monthly_kwh": projected_monthly_kwh,
            "projected_monthly_cost": projected_monthly_cost,
            "projected_yearly_kwh": projected_yearly_kwh,
            "projected_yearly_cost": projected_yearly_cost,
            "total_kwh": total_kwh,
            "total_cost": total_cost,
            "total_records": stats_all["count"],
            "currency": currency,
            "price_per_kwh": price_per_kwh,
            "power_factor": power_factor
        }
    finally:
        conn.close()

def log_outage_event(status_now, current_iso):
    """
    Detects transition between Online (OL) and On Battery (OB).
    Updates or inserts into coupures table.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if status_now == "OB":
            # Check if there is an active ongoing outage
            open_outage = cursor.execute("SELECT id FROM coupures WHERE end IS NULL ORDER BY id DESC LIMIT 1").fetchone()
            if not open_outage:
                cursor.execute("INSERT INTO coupures (start) VALUES (?)", (current_iso,))
                conn.commit()
        elif status_now in ("OL", "OFF", "OVER"):
            # If an outage was ongoing, close it!
            open_outage = cursor.execute("SELECT id, start FROM coupures WHERE end IS NULL ORDER BY id DESC LIMIT 1").fetchone()
            if open_outage:
                outage_id = open_outage["id"]
                start_str = open_outage["start"]
                # Calculate duration in seconds
                try:
                    t_start = cursor.execute("SELECT unixepoch(?)", (start_str,)).fetchone()[0]
                    t_end = cursor.execute("SELECT unixepoch(?)", (current_iso,)).fetchone()[0]
                    duration = max(1, t_end - t_start)
                except Exception:
                    duration = 0
                cursor.execute("UPDATE coupures SET end = ?, duration_seconds = ? WHERE id = ?", (current_iso, duration, outage_id))
                conn.commit()
    finally:
        conn.close()

def get_recent_outages(limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        rows = cursor.execute("""
            SELECT id, start, end, duration_seconds
            FROM coupures
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        result = []
        for r in rows:
            dur = r["duration_seconds"]
            dur_str = "En cours..."
            if dur is not None:
                mins = dur // 60
                secs = dur % 60
                if mins > 0:
                    dur_str = f"{mins} min {secs} s"
                else:
                    dur_str = f"{secs} s"
            result.append({
                "id": r["id"],
                "start": r["start"],
                "end": r["end"],
                "duration_seconds": dur,
                "duration_formatted": dur_str
            })
        return result
    finally:
        conn.close()

def get_saved_config():
    path = get_config_path()
    default_cfg = {"price_per_kwh": 0.25, "currency": "€", "power_factor": 0.7}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "price_per_kwh": float(data.get("price_per_kwh", 0.25)),
                    "currency": str(data.get("currency", "€")),
                    "power_factor": float(data.get("power_factor", 0.7))
                }
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    path = get_config_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
