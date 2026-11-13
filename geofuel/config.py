"""Konfigurasi GEO-FUEL.

Semua angka operasional dan biaya default adalah ASUMSI SIMULASI, bukan data
resmi Pertamina. Koordinat terminal juga harus diverifikasi sebelum penelitian.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Pembaca .env ringan agar pengguna Windows tidak harus mengatur environment
# variable satu per satu. File .env tidak ikut dibagikan karena bisa berisi rahasia.
_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        os.environ.setdefault(_key.strip(), _value.strip().strip("\"'"))

DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_STATION_CSV = Path(os.getenv("GEOFUEL_STATION_CSV", DATA_DIR / "stations_demo.csv"))
DEFAULT_FLEET_CSV = Path(os.getenv("GEOFUEL_FLEET_CSV", DATA_DIR / "fleet_demo.csv"))

# Koordinat awal dari proyek lama. Statusnya PERKIRAAN dan harus diverifikasi.
TERMINAL_NAME = os.getenv("GEOFUEL_TERMINAL_NAME", "Fuel Terminal Ujung Berung (perlu verifikasi)")
TERMINAL_LAT = float(os.getenv("GEOFUEL_TERMINAL_LAT", "-6.9158"))
TERMINAL_LON = float(os.getenv("GEOFUEL_TERMINAL_LON", "107.7036"))
OSM_NETWORK_RADIUS_M = int(os.getenv("GEOFUEL_OSM_RADIUS_M", "10000"))
TERMINAL_INITIAL_STOCK_LITERS = float(os.getenv("GEOFUEL_TERMINAL_INITIAL_STOCK_LITERS", "180000"))
TERMINAL_DATA_STATUS = os.getenv("GEOFUEL_TERMINAL_DATA_STATUS", "UNVERIFIED")
TERMINAL_STOCK_STATUS = os.getenv("GEOFUEL_TERMINAL_STOCK_STATUS", "SIMULATED")
MAX_SNAP_DISTANCE_M = float(os.getenv("GEOFUEL_MAX_SNAP_DISTANCE_M", "1500"))

# Horizon simulasi satu hari.
START_HOUR = 6.0
END_HOUR = 22.0
SIMULATION_STEP_HOURS = 0.25  # 15 menit
DEFAULT_EPOCH_HOURS = 2.0     # rolling horizon: rencana ulang tiap 2 jam

# Parameter persediaan. Perlu validasi dengan data operasi jika tersedia.
SERVICE_LEVEL_Z = 1.65
MEAN_LEAD_TIME_DAYS = 0.35
DEMAND_STD_FRACTION = 0.20
LEAD_TIME_STD_DAYS = 0.10
TARGET_FILL_RATIO = 0.85
PRIORITY_BUFFER_HOURS = 2.0
PRIORITY_LOOKAHEAD_HOURS = 12.0
MIN_DELIVERY_LITERS = 500.0

# Waktu loading/unloading (asumsi simulasi).
LOADING_HOURS = 0.25
UNLOADING_BASE_HOURS = 0.15
UNLOADING_RATE_LITERS_PER_HOUR = 40000.0

# Parameter biaya (asumsi simulasi), mengikuti struktur objective dokumen.
COST_PER_KM = 5800.0
COST_PER_DRIVING_HOUR = 45000.0
FIXED_COST_PER_TRIP = 150000.0
LATE_PENALTY_PER_HOUR = 120000.0
UNMET_PENALTY_PER_LITER = 1200.0
URGENCY_PENALTY_MULTIPLIER = 5.0

# Kapasitas armada default; fleet_demo.csv menjadi sumber utama prototipe.
DEFAULT_FLEET_CAPACITIES = [16000, 8000, 24000, 16000, 24000, 8000]

# Faktor skenario lalu lintas sintetis: normal, padat, sangat padat.
TRAFFIC_BASE_FACTORS = (1.0, 1.35, 1.80)
TRAFFIC_LABELS = {0: "Normal", 1: "Padat", 2: "Sangat padat"}

# Skala permintaan sintetis: rendah, sedang, tinggi.
DEMAND_FACTORS = (0.80, 1.00, 1.25)
DEMAND_LABELS = {0: "Rendah", 1: "Sedang", 2: "Tinggi"}


def traffic_factor(hour: float, level: int) -> float:
    """Faktor waktu perjalanan sintetis dengan puncak pagi dan sore.

    Ini BUKAN data lalu lintas live maupun kecepatan per ruas jalan.
    """
    if level not in (0, 1, 2):
        raise ValueError("traffic level harus 0, 1, atau 2")
    morning_peak = math.exp(-((hour - 8.0) / 1.2) ** 2)
    evening_peak = math.exp(-((hour - 17.5) / 1.5) ** 2)
    peak_multiplier = 1.0 + 0.25 * (morning_peak + evening_peak)
    return TRAFFIC_BASE_FACTORS[level] * peak_multiplier


def demand_factor(level: int) -> float:
    if level not in (0, 1, 2):
        raise ValueError("demand level harus 0, 1, atau 2")
    return DEMAND_FACTORS[level]
