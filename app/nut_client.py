import os
import socket
import subprocess
from datetime import datetime

def parse_ups_host(ups_host_str):
    if not ups_host_str:
        ups_host_str = "ups@192.168.0.3"
    ups_name = "ups"
    host = "127.0.0.1"
    port = 3493

    if "@" in ups_host_str:
        ups_name, host_part = ups_host_str.split("@", 1)
    else:
        host_part = ups_host_str

    if ":" in host_part:
        host, p_str = host_part.split(":", 1)
        try:
            port = int(p_str)
        except ValueError:
            port = 3493
    else:
        host = host_part

    if host in ("localhost", "127.0.0.1"):
        host = "127.0.0.1"

    return ups_name.strip(), host.strip(), port

def query_nut_socket(ups_name, host, port, timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    s.sendall(f"LIST VAR {ups_name}\n".encode())
    
    data = ""
    while True:
        chunk = s.recv(4096).decode("utf-8", errors="ignore")
        data += chunk
        if "END LIST VAR" in chunk or not chunk:
            break
    s.close()
    
    variables = {}
    for line in data.splitlines():
        line = line.strip()
        prefix = f"VAR {ups_name} "
        if line.startswith(prefix):
            rest = line[len(prefix):]
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                k = parts[0]
                v = parts[1].strip('"')
                variables[k] = v
    return variables

def query_upsc_cli(ups_host, timeout=5.0):
    result = subprocess.run(
        ["upsc", ups_host],
        capture_output=True,
        text=True,
        timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"upsc failed: {result.stderr.strip()}")
    
    data = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data

_working_host_cache = None

def get_candidate_hosts(host):
    global _working_host_cache
    if _working_host_cache:
        return [_working_host_cache, host]

    candidates = [host]
    if host in ("127.0.0.1", "localhost"):
        # We might be in a Docker bridge container trying to reach the host
        candidates.append("host.docker.internal")
        try:
            with open("/proc/net/route") as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) >= 3 and fields[1] == "00000000":
                        gw_hex = fields[2]
                        gw_ip = socket.inet_ntoa(bytes.fromhex(gw_hex)[::-1])
                        if gw_ip not in candidates:
                            candidates.append(gw_ip)
        except Exception:
            pass
        if "172.17.0.1" not in candidates:
            candidates.append("172.17.0.1")
        lan_ip = os.environ.get("UPS_LAN_IP", "192.168.0.3")
        if lan_ip and lan_ip not in candidates:
            candidates.append(lan_ip)
    return candidates

def get_raw_nut_data(ups_host=None):
    global _working_host_cache
    if not ups_host:
        ups_host = os.environ.get("UPS_HOST", "ups@192.168.0.3")

    ups_name, host, port = parse_ups_host(ups_host)
    candidates = get_candidate_hosts(host)

    last_err = None
    for cand in candidates:
        try:
            data = query_nut_socket(ups_name, cand, port, timeout=2.0)
            if data:
                _working_host_cache = cand
                return data
        except Exception as e:
            last_err = e
            if cand == _working_host_cache:
                _working_host_cache = None

    # Fallback to upsc cli if available
    for cand in candidates:
        try:
            cli_target = f"{ups_name}@{cand}:{port}" if port != 3493 else f"{ups_name}@{cand}"
            data = query_upsc_cli(cli_target, timeout=3.0)
            if data:
                _working_host_cache = cand
                return data
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Impossible de joindre le serveur NUT ({ups_host}). Candidats testés: {candidates}")

def format_runtime(seconds):
    try:
        sec = int(seconds)
        mins = sec // 60
        s = sec % 60
        if mins >= 60:
            h = mins // 60
            m = mins % 60
            return f"{h}h {m}min"
        return f"{mins}min {s:02d}s"
    except Exception:
        return f"{seconds}s"

def get_ups_metrics(ups_host=None, power_factor=0.7):
    try:
        raw = get_raw_nut_data(ups_host)
        status = raw.get("ups.status", "UNKNOWN")
        
        status_label = "En ligne"
        status_badge = "online"
        if "OB" in status:
            status_label = "Sur batterie"
            status_badge = "battery"
        elif "LB" in status:
            status_label = "Batterie faible !"
            status_badge = "critical"
        elif "OL" in status:
            status_label = "En ligne (Secteur)"
            status_badge = "online"

        nominal_va = 0
        try:
            nominal_va = int(raw.get("ups.power.nominal", 0))
        except (ValueError, TypeError):
            pass

        load_pct = 0
        try:
            load_pct = int(float(raw.get("ups.load", 0)))
        except (ValueError, TypeError):
            pass

        charge_pct = 100
        try:
            charge_pct = int(float(raw.get("battery.charge", 100)))
        except (ValueError, TypeError):
            pass

        runtime_sec = 0
        try:
            runtime_sec = int(float(raw.get("battery.runtime", 0)))
        except (ValueError, TypeError):
            pass

        voltage_out = 230.0
        try:
            voltage_out = float(raw.get("output.voltage", 230.0))
        except (ValueError, TypeError):
            pass

        freq_out = 50.0
        try:
            freq_out = float(raw.get("output.frequency.nominal", raw.get("output.frequency", 50.0)))
        except (ValueError, TypeError):
            pass

        # Power calculations
        apparent_va = round(nominal_va * (load_pct / 100.0), 1)
        real_watts = round(apparent_va * float(power_factor))

        mfr = raw.get("device.mfr", "EATON")
        model = raw.get("device.model", "Ellipse ECO")
        full_model = f"{mfr} {model}".strip()

        return {
            "success": True,
            "error": None,
            "status": status,
            "status_label": status_label,
            "status_badge": status_badge,
            "is_on_battery": "OB" in status,
            "battery_charge": charge_pct,
            "battery_runtime": runtime_sec,
            "battery_runtime_str": format_runtime(runtime_sec),
            "battery_low_threshold": raw.get("battery.charge.low", "20"),
            "ups_load": load_pct,
            "nominal_va": nominal_va,
            "apparent_va": apparent_va,
            "real_watts": real_watts,
            "power_factor": power_factor,
            "output_voltage": voltage_out,
            "output_frequency": freq_out,
            "device_model": full_model,
            "device_mfr": mfr,
            "outlet_power": raw.get("outlet.power", ""),
            "updated_at": datetime.now().astimezone().isoformat(),
            "raw": raw
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "OFFLINE",
            "status_label": "Hors ligne",
            "status_badge": "offline",
            "is_on_battery": False,
            "battery_charge": 0,
            "battery_runtime": 0,
            "battery_runtime_str": "--",
            "ups_load": 0,
            "nominal_va": 0,
            "apparent_va": 0,
            "real_watts": 0,
            "power_factor": power_factor,
            "output_voltage": 0,
            "output_frequency": 0,
            "device_model": "Onduleur Injoignable",
            "updated_at": datetime.now().astimezone().isoformat()
        }
