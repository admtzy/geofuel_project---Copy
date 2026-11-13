"""Eksperimen pembanding M0-M3 untuk GEO-FUEL.

Contoh Windows PowerShell:
  python experiment.py --offline --n 10 --reps 1 --solver-time-limit 5

Output:
  results/experiment_results.csv
  results/experiment_summary.csv
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import replace
from pathlib import Path

import pandas as pd

from geofuel import config as cfg
from geofuel.data import load_graph, make_instance
from geofuel.economics import SCENARIOS, feasibility
from geofuel.simulation import METHODS, simulate


def parse_int_list(value: str) -> list[int]:
    try:
        result = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Isi daftar angka dipisahkan koma") from exc
    if not result:
        raise argparse.ArgumentTypeError("Daftar tidak boleh kosong")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Eksperimen GEO-FUEL M0-M3")
    parser.add_argument("--n", type=int, default=10, help="Jumlah SPBU; gunakan 0 untuk semua baris CSV")
    parser.add_argument("--event-factor", type=float, default=1.0, help="Pengali permintaan kalender/event, mis. 1.15")
    parser.add_argument("--reps", type=int, default=1, help="Jumlah replikasi setiap skenario")
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--fleet-counts", type=parse_int_list, default=[3, 4, 5])
    parser.add_argument("--solver-time-limit", type=int, default=5)
    parser.add_argument("--epoch-hours", type=float, default=2.0)
    parser.add_argument("--offline", action="store_true", help="Gunakan graf grid SIMULATED")
    parser.add_argument("--station-csv", type=Path, default=cfg.DEFAULT_STATION_CSV,
                        help="CSV SPBU; kolom wajib mengikuti data/spbu_template.csv")
    parser.add_argument("--fleet-csv", type=Path, default=cfg.DEFAULT_FLEET_CSV,
                        help="CSV armada; kolom wajib vehicle_id,capacity_liters")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()

    if args.n < 0 or args.reps < 1:
        parser.error("--n dan --reps harus lebih besar dari nol")
    max_fleet = max(args.fleet_counts)
    if max_fleet > 100 or min(args.fleet_counts) < 1:
        parser.error("fleet-counts harus berada pada rentang 1..100 dan sesuai jumlah baris fleet CSV")

    graph = load_graph(offline=args.offline)
    rows = []
    total_runs = 3 * 3 * len(args.fleet_counts) * args.reps * len(METHODS)
    completed = 0

    for demand_level, traffic_level, fleet_count, repetition in itertools.product(
        range(3), range(3), args.fleet_counts, range(args.reps)
    ):
        seed = args.seed + repetition * 101 + demand_level * 17 + traffic_level * 7 + fleet_count
        instance = make_instance(
            graph, seed=seed, n=(None if args.n == 0 else args.n), demand_level=demand_level,
            event_factor=args.event_factor,
            fleet_count=max_fleet,
            station_csv=args.station_csv,
            fleet_csv=args.fleet_csv,
        )
        instance_for_fleet = replace(
            instance,
            fleet_ids=instance.fleet_ids[:fleet_count],
            fleet_capacities=instance.fleet_capacities[:fleet_count],
            fleet_data_status=instance.fleet_data_status[:fleet_count],
        )

        for method in METHODS:
            output = simulate(
                instance_for_fleet, method=method, traffic_level=traffic_level,
                epoch_hours=args.epoch_hours,
                solver_time_limit=args.solver_time_limit, seed=seed,
            )
            kpi = output["kpi"]
            fallback_cycles = sum(1 for e in output["epochs"] if e.get("fallback_used"))
            rows.append({
                "seed": seed,
                "demand_level": demand_level,
                "traffic_level": traffic_level,
                "event_factor": args.event_factor,
                "fleet_count": fleet_count,
                "repetition": repetition,
                "method": method,
                "network_source": instance.network_source,
                "solver_fallback_cycles": fallback_cycles,
                **{k: v for k, v in kpi.items() if k != "cost_breakdown"},
            })
            completed += 1
            print(f"[{completed}/{total_runs}] demand={demand_level} traffic={traffic_level} "
                  f"fleet={fleet_count} rep={repetition} method={method} "
                  f"cost=Rp{kpi['total_cost_rp']:,.0f} stockout={kpi['stockout_liters']:,.0f} L",
                  flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    raw_path = args.output_dir / "experiment_results.csv"
    summary_path = args.output_dir / "experiment_summary.csv"
    results.to_csv(raw_path, index=False)
    summary = results.groupby("method").agg({
        "total_cost_rp": "mean",
        "distance_km": "mean",
        "driving_hours": "mean",
        "stockout_liters": "mean",
        "service_level": "mean",
        "on_time_rate": "mean",
        "fleet_utilization": "mean",
        "solver_fallback_cycles": "sum",
    }).reset_index()
    summary.to_csv(summary_path, index=False)

    metadata = {
        "experiment": "GEO-FUEL M0-M3",
        "station_csv": str(args.station_csv),
        "fleet_csv": str(args.fleet_csv),
        "station_count": int(len(pd.read_csv(args.station_csv))),
        "n_argument": int(args.n),
        "network_mode": "SIMULATED_GRID_OFFLINE" if args.offline else "OPENSTREETMAP_OSMNX",
        "demand_levels": ["LOW", "MEDIUM", "HIGH"],
        "traffic_levels": ["NORMAL", "CONGESTED", "VERY_CONGESTED"],
        "fleet_counts": args.fleet_counts,
        "repetitions": args.reps,
        "seed": args.seed,
        "operational_data_warning": "Periksa data_status; parameter sintetis bukan data aktual Pertamina.",
    }
    metadata_path = args.output_dir / "experiment_metadata.json"
    metadata_path.write_text(
        __import__("json").dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nRINGKASAN RATA-RATA:")
    print(summary.to_string(index=False))

    paired = results.pivot_table(
        index=["seed", "demand_level", "traffic_level", "fleet_count", "repetition"],
        columns="method", values="total_cost_rp", aggfunc="mean",
    )
    if "M0" in paired and "M3" in paired:
        saving = (paired["M0"] - paired["M3"]).mean()
        print(f"\nRata-rata penghematan M3 terhadap M0: Rp {saving:,.0f} per hari simulasi")
        for scenario_name, scenario_args in SCENARIOS.items():
            result = feasibility(saving, **scenario_args)
            print(scenario_name, {
                "NPV_Rp": round(result["NPV_Rp"], 2),
                "BCR": round(result["BCR"], 4) if result["BCR"] is not None else None,
                "IRR": result["IRR"],
                "Payback_years": result["Payback_years"],
            })

    print(f"\nFile tersimpan: {raw_path}, {summary_path}, dan {metadata_path}")
    print("Pastikan hasil dilaporkan sebagai SIMULASI jika input operasional masih sintetis.")


if __name__ == "__main__":
    main()
