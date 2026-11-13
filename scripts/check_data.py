"""Validasi CSV SPBU dan armada sebelum simulasi GEO-FUEL."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from geofuel.data import _read_stations, _read_fleet
from geofuel import config as cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Validasi dataset GEO-FUEL")
    parser.add_argument("--station-csv", type=Path, default=cfg.DEFAULT_STATION_CSV)
    parser.add_argument("--fleet-csv", type=Path, default=cfg.DEFAULT_FLEET_CSV)
    args = parser.parse_args()

    stations = _read_stations(args.station_csv)
    fleet_frame_ids = len(__import__("pandas").read_csv(args.fleet_csv))
    fleet_ids, fleet_caps, fleet_status = _read_fleet(args.fleet_csv, fleet_frame_ids)

    print(f"File SPBU: {args.station_csv}")
    print(f"SPBU ditemukan: {len(stations)}")
    print(f"ID SPBU unik: {stations.station_id.nunique() == len(stations)}")
    if "data_status" in stations:
        print(f"Status data SPBU: {stations.data_status.value_counts(dropna=False).to_dict()}")
    if "location_status" in stations:
        print(f"Status lokasi: {stations.location_status.value_counts(dropna=False).to_dict()}")
    print(f"File armada: {args.fleet_csv}")
    print(f"Armada ditemukan: {len(fleet_ids)}")
    print(f"Status armada: {dict((x, fleet_status.count(x)) for x in set(fleet_status))}")
    print("Validasi struktur CSV berhasil. Validasi ini tidak membuktikan data aktual/benar secara geografis.")


if __name__ == "__main__":
    main()
