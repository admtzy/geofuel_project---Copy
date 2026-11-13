"""Build a runnable GEO-FUEL input from official SPBU identities + public geocoding.

Important: ESDM provides station identity/status, not inventory/sales/fleet data.
The operational fields generated here are explicit scenario assumptions. They
are never labelled as Pertamina actual data.

Usage:
  python scripts/build_public_runnable_dataset.py
  python scripts/build_public_runnable_dataset.py --capacity 35000 --demand 9000 --stock-fraction 0.35

Nominatim is queried sequentially (>=1.1 s/request). Every returned coordinate
is a candidate and must be checked manually before being treated as verified.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = ROOT / "data" / "spbu_kota_bandung_esdm_2025.csv"
DEFAULT_STATIONS = ROOT / "data" / "stations_public_runnable.csv"
DEFAULT_FLEET = ROOT / "data" / "fleet_scenario.csv"
DEFAULT_GEOCODE_LOG = ROOT / "data" / "spbu_geocode_candidates.csv"


def _valid_latlon(lat: Any, lon: Any) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -7.1 <= lat <= -6.7 and 107.3 <= lon <= 108.0


def geocode_one(session: requests.Session, query: str, retries: int = 3):
    last_error = ""
    for attempt in range(retries):
        try:
            response = session.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "jsonv2", "limit": 3, "countrycodes": "id"},
                timeout=(10, 35),
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            items = response.json()
            for item in items:
                if _valid_latlon(item.get("lat"), item.get("lon")):
                    return float(item["lat"]), float(item["lon"]), item.get("display_name", ""), "OSM_CANDIDATE"
            return None, None, "No Bandung candidate returned", "NOT_FOUND"
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
            time.sleep(2 ** attempt)
    return None, None, last_error, "REQUEST_FAILED"


def main() -> None:
    ap = argparse.ArgumentParser(description="Membuat input runnable dari master SPBU ESDM + geocoding OSM")
    ap.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    ap.add_argument("--stations-output", type=Path, default=DEFAULT_STATIONS)
    ap.add_argument("--fleet-output", type=Path, default=DEFAULT_FLEET)
    ap.add_argument("--geocode-log", type=Path, default=DEFAULT_GEOCODE_LOG)
    ap.add_argument("--capacity", type=float, default=30000, help="Asumsi kapasitas tangki per SPBU (liter)")
    ap.add_argument("--demand", type=float, default=8000, help="Asumsi demand harian per SPBU (liter/hari)")
    ap.add_argument("--stock-fraction", type=float, default=0.15, help="Asumsi stok awal sebagai fraksi kapasitas")
    ap.add_argument("--pause", type=float, default=1.2)
    ap.add_argument("--no-geocode", action="store_true", help="Gunakan hanya koordinat yang sudah ada di master")
    args = ap.parse_args()

    if not args.master.exists():
        raise FileNotFoundError(f"Master ESDM tidak ditemukan: {args.master}")
    if args.capacity <= 0 or args.demand <= 0 or not 0 < args.stock_fraction <= 1:
        ap.error("capacity/demand harus >0 dan stock-fraction harus pada rentang (0,1]")
    if args.pause < 1.1:
        ap.error("Nominatim public policy: gunakan pause minimal 1.1 detik")

    master = pd.read_csv(args.master, dtype={"station_id": str, "official_spbu_code": str}).fillna("")
    needed = {"station_id", "official_spbu_code", "name", "address", "operational_status_as_of_2025_S1", "lat", "lon"}
    missing = needed - set(master.columns)
    if missing:
        raise ValueError(f"Kolom master ESDM kurang: {sorted(missing)}")
    master = master[master["operational_status_as_of_2025_S1"].astype(str).str.lower().eq("beroperasi")].copy()

    session = requests.Session()
    session.headers.update({"User-Agent": "GEO-FUEL-academic-research/1.0 (geocoding; contact project maintainer)"})
    geo_rows = []
    for idx, row in master.iterrows():
        lat, lon, display, status = None, None, "", ""
        if _valid_latlon(row.get("lat"), row.get("lon")):
            lat, lon = float(row["lat"]), float(row["lon"])
            display, status = "Coordinate already present in source master; manual check required", str(row.get("location_status") or "EXISTING_CANDIDATE")
        elif not args.no_geocode:
            query = f"{row['name']}, {row['address']}, Kota Bandung, Jawa Barat, Indonesia"
            lat, lon, display, status = geocode_one(session, query)
            time.sleep(max(1.1, args.pause))
        else:
            display, status = "No coordinate in master; geocoding disabled", "NO_COORDINATE"
        source_label = str(row.get("location_source") or "").strip()
        if not source_label:
            source_label = "OpenStreetMap Nominatim" if status == "OSM_CANDIDATE" else "UNSPECIFIED_CANDIDATE"
        geo_rows.append({
            "station_id": str(row["station_id"]), "official_spbu_code": str(row["official_spbu_code"]),
            "name": row["name"], "address": row["address"], "lat_candidate": lat, "lon_candidate": lon,
            "geocode_display_name": display, "location_status": status,
            "location_source": source_label,
            "official_identity_source": "ESDM Semester I 2025",
        })
        print(f"[{len(geo_rows)}/{len(master)}] {row['official_spbu_code']}: {status}", flush=True)

    geo = pd.DataFrame(geo_rows)
    args.geocode_log.parent.mkdir(parents=True, exist_ok=True)
    geo.to_csv(args.geocode_log, index=False, encoding="utf-8-sig")
    valid = geo[geo.apply(lambda r: _valid_latlon(r["lat_candidate"], r["lon_candidate"]), axis=1)].copy()
    if valid.empty:
        raise RuntimeError(
            "Tidak ada koordinat SPBU yang valid. File log geocoding tetap disimpan. "
            "Periksa koneksi internet atau jalankan scripts/import_spbu_osm.py untuk mendapatkan POI OSM."
        )

    # The optimizer requires operational fields. These are explicit assumptions,
    # not observations from Pertamina. User can change them via CLI arguments.
    stations = pd.DataFrame({
        "station_id": valid["station_id"].astype(str),
        "name": valid["name"].astype(str),
        "lat": pd.to_numeric(valid["lat_candidate"], errors="raise"),
        "lon": pd.to_numeric(valid["lon_candidate"], errors="raise"),
        "capacity_liters": float(args.capacity),
        "initial_stock_liters": float(args.capacity * args.stock_fraction),
        "daily_demand_liters": float(args.demand),
        "demand_std_liters_per_day": float(args.demand * 0.15),
        "mean_lead_time_days": 0.35,
        "lead_time_std_days": 0.10,
        "service_level_z": 1.65,
        "window_start": 6,
        "window_end": 22,
        "data_status": "PUBLIC_IDENTITY_PLUS_SCENARIO_ASSUMPTIONS",
        "location_status": valid["location_status"].astype(str),
        "location_source": valid["location_source"].astype(str),
        "source_url": "https://migas.esdm.go.id/cms/uploads/informasi-publik/BU_hilir/2025%20-%20BBM%20Semester%20I/Penyalur%20Agen%20Retail%20PT%20PPN%20SMT%20I%202025.pdf",
        "operational_parameter_note": "CAPACITY/STOCK/DEMAND/LEAD_TIME ARE USER-EDITABLE SCENARIO ASSUMPTIONS; NOT ACTUAL PERTAMINA DATA",
    })
    args.stations_output.parent.mkdir(parents=True, exist_ok=True)
    stations.to_csv(args.stations_output, index=False, encoding="utf-8-sig")

    fleet = pd.DataFrame({
        "vehicle_id": ["SCENARIO_MT_01", "SCENARIO_MT_02", "SCENARIO_MT_03", "SCENARIO_MT_04", "SCENARIO_MT_05", "SCENARIO_MT_06"],
        "capacity_liters": [8000, 16000, 24000, 16000, 24000, 8000],
        "data_status": "SCENARIO_ASSUMPTION_NOT_ACTUAL_FLEET",
    })
    args.fleet_output.parent.mkdir(parents=True, exist_ok=True)
    fleet.to_csv(args.fleet_output, index=False, encoding="utf-8-sig")

    print("\nDATASET SIAP DIPAKAI OLEH LOADER GEO-FUEL")
    print(f"Identitas SPBU ESDM beroperasi: {len(master)}")
    print(f"Koordinat kandidat tersedia: {len(valid)}")
    print(f"Input stasiun: {args.stations_output}")
    print(f"Input armada: {args.fleet_output}")
    print(f"Log kandidat koordinat: {args.geocode_log}")
    print("PERINGATAN: koordinat perlu pemeriksaan manual; semua parameter operasional adalah asumsi skenario.")
    print("Atribusi OSM: © OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright")


if __name__ == "__main__":
    main()
