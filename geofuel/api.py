
"""FastAPI service GEO-FUEL + WebGIS Leaflet."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone
from threading import Lock

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config as cfg
from .data import Instance, haversine_m, load_graph, make_instance
from .inventory import assess_station
from .simulation import METHODS, simulate


_gps_lock = Lock()
_gps_positions: dict[str, dict] = {}


class GPSUpdate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=300)
    heading: float | None = Field(default=None, ge=0, lt=360)
    recorded_at: datetime | None = None


app = FastAPI(
    title="GEO-FUEL API",
    description=(
        "Prototipe sistem pendukung keputusan distribusi BBM "
        "berbasis geospasial dan optimasi."
    ),
    version="1.0.0",
)


class RunRequest(BaseModel):
    seed: int = 7
    n: int = Field(default=10, ge=0, le=30)
    demand_level: int = Field(default=1, ge=0, le=2)
    traffic_level: int = Field(default=1, ge=0, le=2)
    fleet_count: int = Field(default=4, ge=1, le=100)
    epoch_hours: float = Field(
        default=cfg.DEFAULT_EPOCH_HOURS,
        gt=0,
        le=8,
    )
    method: Literal["M0", "M1", "M2", "M3"] = "M3"
    solver_time_limit: int = Field(default=10, ge=1, le=120)
    offline: bool = False
    overrides: dict[str, dict[str, float]] = Field(
        default_factory=dict
    )


@lru_cache(maxsize=2)
def _get_graph(offline: bool):
    """
    Cache graf agar jaringan tidak diunduh ulang pada setiap simulasi.

    Setelah mengganti data.py, restart server FastAPI agar cache lama
    tidak tetap digunakan.
    """
    return load_graph(offline=offline)


def _apply_overrides(
    I: Instance,
    overrides: dict[str, dict[str, float]],
) -> None:
    """Override stok/kapasitas/konsumsi dari UI; nilai tetap dalam liter."""
    id_to_index = {
        I.station_ids[i]: i
        for i in range(1, I.n + 1)
    }

    for key, values in overrides.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            index = id_to_index.get(str(key), -1)

        if not 1 <= index <= I.n:
            continue

        if "capacity_liters" in values:
            capacity = float(values["capacity_liters"])

            if capacity <= 0:
                raise ValueError(
                    f"Kapasitas SPBU indeks {index} harus > 0."
                )

            I.capacity[index] = capacity

        if "initial_stock_liters" in values:
            stock = float(values["initial_stock_liters"])

            if stock < 0:
                raise ValueError(
                    f"Stok awal SPBU indeks {index} tidak boleh negatif."
                )

            if stock > I.capacity[index]:
                raise ValueError(
                    f"Stok awal SPBU indeks {index} "
                    "melebihi kapasitas tangki."
                )

            I.initial_stock[index] = stock

        if I.initial_stock[index] > I.capacity[index]:
            raise ValueError(
                f"Stok awal SPBU indeks {index} melebihi "
                "kapasitas tangki setelah perubahan kapasitas."
            )

        if "daily_demand_liters" in values:
            demand = float(values["daily_demand_liters"])

            if demand <= 0:
                raise ValueError(
                    f"Konsumsi SPBU indeks {index} harus > 0."
                )

            old_demand = float(I.daily_demand[index])
            scale = demand / old_demand if old_demand > 0 else 0.0

            I.hourly_demand[index, :] *= scale
            I.demand_std_liters_per_day[index] *= scale
            I.daily_demand[index] = demand

    from .inventory import safety_stock

    for i in range(1, I.n + 1):
        I.safety_stocks[i] = safety_stock(
            I.daily_demand[i],
            mean_lead_time_days=I.mean_lead_time_days[i],
            lead_time_std_days=I.lead_time_std_days[i],
            z=I.service_level_z[i],
            demand_std_liters_per_day=(
                I.demand_std_liters_per_day[i]
            ),
        )


def _node_coordinate(G, node) -> tuple[float, float]:
    """Mengambil koordinat node dalam format latitude, longitude."""
    return (
        float(G.nodes[node]["y"]),
        float(G.nodes[node]["x"]),
    )


def _path_geometry(
    I: Instance,
    G,
    from_index: int,
    to_index: int,
    depart_hour: float,
    arrive_hour: float,
    spacing_m: float = 18.0,
) -> list[list[float]]:
    """
    Menghasilkan titik animasi berdasarkan geometri ruas jalan.

    Format keluaran:
        [latitude, longitude, waktu_simulasi]

    Tidak lagi menghubungkan node dengan garis lurus apabila edge
    memiliki geometri jalan OSM yang lengkap.
    """
    node_path = I.paths[(from_index, to_index)]

    if not node_path:
        return []

    if len(node_path) == 1:
        lat, lon = _node_coordinate(G, node_path[0])

        return [
            [lat, lon, float(depart_hour)],
            [lat, lon, float(arrive_hour)],
        ]

    # 1. Rangkai geometri semua edge sesuai urutan path Dijkstra.
    road_coordinates: list[tuple[float, float]] = []

    for u, v in zip(node_path, node_path[1:]):
        edge_data = G.get_edge_data(u, v)

        if edge_data is None:
            raise ValueError(
                f"Geometri edge jalan tidak ditemukan untuk {u} -> {v}."
            )

        geometry = edge_data.get("geometry_latlon")

        if not geometry or len(geometry) < 2:
            # Fallback hanya untuk edge yang memang tidak memiliki
            # geometri. Pada OSM yang normal, geometry_latlon tersedia.
            geometry = [
                _node_coordinate(G, u),
                _node_coordinate(G, v),
            ]

        edge_coordinates = [
            (float(point[0]), float(point[1]))
            for point in geometry
        ]

        # Hindari titik awal berulang pada sambungan antar-edge.
        if road_coordinates:
            if haversine_m(
                road_coordinates[-1],
                edge_coordinates[0],
            ) < 1.0:
                edge_coordinates = edge_coordinates[1:]

        road_coordinates.extend(edge_coordinates)

    if not road_coordinates:
        return []

    if len(road_coordinates) == 1:
        lat, lon = road_coordinates[0]

        return [
            [lat, lon, float(depart_hour)],
            [lat, lon, float(arrive_hour)],
        ]

    # 2. Densifikasi di sepanjang bentuk geometri jalan.
    # Titik baru dibuat pada setiap segmen geometri, bukan garis
    # lurus langsung dari node awal menuju node akhir.
    dense_coordinates = [road_coordinates[0]]
    cumulative_distances = [0.0]

    for a, b in zip(
        road_coordinates,
        road_coordinates[1:],
    ):
        length = haversine_m(a, b)

        if length <= 0.01:
            continue

        pieces = max(
            1,
            int(math.ceil(length / spacing_m)),
        )

        for part in range(1, pieces + 1):
            fraction = part / pieces

            lat = (
                a[0]
                + (b[0] - a[0]) * fraction
            )

            lon = (
                a[1]
                + (b[1] - a[1]) * fraction
            )

            dense_coordinates.append((lat, lon))

            cumulative_distances.append(
                cumulative_distances[-1]
                + length / pieces
            )

    # 3. Distribusikan waktu perjalanan mengikuti jarak kumulatif.
    total_distance = cumulative_distances[-1]

    if total_distance <= 0:
        total_distance = 1.0

    duration = float(arrive_hour) - float(depart_hour)

    result = []

    for (lat, lon), distance in zip(
        dense_coordinates,
        cumulative_distances,
    ):
        fraction = distance / total_distance

        timestamp = (
            float(depart_hour)
            + fraction * duration
        )

        result.append([
            float(lat),
            float(lon),
            float(timestamp),
        ])

    # Pastikan waktu titik awal dan akhir tepat.
    result[0][2] = float(depart_hour)
    result[-1][2] = float(arrive_hour)

    return result


def _serialize_result(
    I: Instance,
    G,
    output: dict,
) -> dict:
    stations = []
    history = output["stock_history"]

    for i in range(1, I.n + 1):
        lead = (
            float(I.travel_hours[0, i])
            + cfg.LOADING_HOURS
        )

        baseline = assess_station(
            stock_liters=float(I.initial_stock[i]),
            daily_demand_liters=float(I.daily_demand[i]),
            tank_capacity_liters=float(I.capacity[i]),
            safety_stock_liters=float(I.safety_stocks[i]),
            travel_time_hours=float(I.travel_hours[0, i]),
        )

        stations.append({
            "index": i,
            "station_id": I.station_ids[i],
            "name": I.station_names[i],
            "data_status": I.station_data_status[i],
            "lat": I.station_latlon[i][0],
            "lon": I.station_latlon[i][1],
            "capacity_liters": float(I.capacity[i]),
            "initial_stock_liters": float(I.initial_stock[i]),
            "daily_demand_liters": float(I.daily_demand[i]),
            "safety_stock_liters": float(I.safety_stocks[i]),
            "demand_std_liters_per_day": float(
                I.demand_std_liters_per_day[i]
            ),
            "mean_lead_time_days": float(
                I.mean_lead_time_days[i]
            ),
            "lead_time_std_days": float(
                I.lead_time_std_days[i]
            ),
            "service_level_z": float(I.service_level_z[i]),
            "doi_days_initial": float(
                baseline["doi_days"]
            ),
            "time_to_safety_hours_initial": float(
                baseline["time_to_safety_hours"]
            ),
            "lead_time_hours_freeflow": lead,
            "effective_lead_hours_freeflow": float(
                baseline["effective_lead_hours"]
            ),
            "priority_initial": baseline["priority"],
            "needs_replenishment_initial": (
                baseline["needs_replenishment"]
            ),
            "reorder_point_liters": float(
                baseline["reorder_point_liters"]
            ),
            "decision_reason_initial": (
                baseline["decision_reason"]
            ),
            "stock_history": [
                float(row[i])
                for row in history
            ],
        })

    trips = []

    for trip in output["trips"]:
        path_points: list[list[float]] = []

        terminal_xy = [
            float(I.terminal_latlon[0]),
            float(I.terminal_latlon[1]),
        ]

        # Kendaraan berada di terminal selama proses loading.
        path_points.append([
            terminal_xy[0],
            terminal_xy[1],
            float(trip["start_hour"]),
        ])

        if trip["departure_hour"] > trip["start_hour"]:
            path_points.append([
                terminal_xy[0],
                terminal_xy[1],
                float(trip["departure_hour"]),
            ])

        stop_by_index = {
            int(stop["index"]): stop
            for stop in trip["stops"]
        }

        # Buat geometri setiap perjalanan: terminal -> SPBU -> terminal.
        for leg in trip["legs"]:
            segment = _path_geometry(
                I=I,
                G=G,
                from_index=int(leg["from_index"]),
                to_index=int(leg["to_index"]),
                depart_hour=float(leg["depart_hour"]),
                arrive_hour=float(leg["arrive_hour"]),
            )

            if (
                path_points
                and segment
                and haversine_m(
                    (path_points[-1][0], path_points[-1][1]),
                    (segment[0][0], segment[0][1]),
                ) < 1.0
            ):
                segment = segment[1:]

            path_points.extend(segment)

            stop = stop_by_index.get(
                int(leg["to_index"])
            )

            if stop is not None:
                if segment:
                    lat = segment[-1][0]
                    lon = segment[-1][1]
                else:
                    lat, lon = I.station_latlon[
                        int(leg["to_index"])
                    ]

                # Marker diam selama proses bongkar BBM.
                path_points.append([
                    float(lat),
                    float(lon),
                    float(stop["service_end_hour"]),
                ])

        # Pastikan titik terakhir berada di terminal saat trip selesai.
        if (
            not path_points
            or path_points[-1][2] < float(trip["end_hour"])
        ):
            path_points.append([
                terminal_xy[0],
                terminal_xy[1],
                float(trip["end_hour"]),
            ])

        trips.append({
            "vehicle_id": trip["vehicle_id"],
            "vehicle_index": trip["vehicle_index"],
            "capacity_liters": trip["capacity_liters"],
            "start_hour": trip["start_hour"],
            "departure_hour": trip["departure_hour"],
            "end_hour": trip["end_hour"],
            "elapsed_hours": trip["elapsed_hours"],
            "loading_hours": trip["loading_hours"],
            "distance_km": trip["distance_km"],
            "driving_hours": trip["driving_hours"],
            "service_hours": trip["service_hours"],
            "delivered_liters": trip["delivered_liters"],
            "method": trip["method"],
            "stops": trip["stops"],
            "path": path_points,
        })

    return {
        "method": output["method"],
        "network_source": output["network_source"],
        "terminal": {
            "name": I.terminal_name,
            "lat": I.terminal_latlon[0],
            "lon": I.terminal_latlon[1],
            "data_status": cfg.TERMINAL_DATA_STATUS,
            "stock_status": cfg.TERMINAL_STOCK_STATUS,
            "initial_stock_liters": float(
                I.terminal_initial_stock_liters
            ),
            "remaining_stock_liters": float(
                output["terminal_stock_remaining_liters"]
            ),
        },
        "stations": stations,
        "trips": trips,
        "times": output["times"],
        "epochs": output["epochs"],
        "kpi": output["kpi"],
        "warnings": _warnings(I),
    }


def _warnings(I: Instance) -> list[str]:
    warnings = []

    if I.network_source != "OPENSTREETMAP_OSMNX":
        warnings.append(
            "Jaringan jalan yang digunakan adalah grid SIMULATED, "
            "bukan jaringan jalan aktual."
        )

    if cfg.TERMINAL_DATA_STATUS.upper() != "ACTUAL_VERIFIED":
        warnings.append(
            "Koordinat/nama terminal belum berstatus ACTUAL_VERIFIED."
        )

    if cfg.TERMINAL_STOCK_STATUS.upper() != "ACTUAL_VERIFIED":
        warnings.append(
            "Stok awal terminal adalah asumsi/simulasi, "
            "bukan stok terminal aktual."
        )

    if any(
        status.upper() != "ACTUAL_VERIFIED"
        for status in I.station_data_status[1:]
    ):
        warnings.append(
            "Ada data SPBU yang belum berstatus ACTUAL_VERIFIED. "
            "Periksa data_status pada CSV."
        )

    if any(
        status.upper() != "ACTUAL_VERIFIED"
        for status in I.fleet_data_status
    ):
        warnings.append(
            "Ada data armada yang belum berstatus ACTUAL_VERIFIED. "
            "Periksa data_status pada CSV armada."
        )

    warnings.append(
        "Faktor lalu lintas adalah skenario sintetis, "
        "bukan pengukuran lalu lintas real-time per ruas."
    )

    warnings.append(
        "Sistem memodelkan satu jenis produk BBM per run; "
        "kompartemen multi-produk belum dimodelkan."
    )

    return warnings


def _prepare(req: RunRequest):
    G = _get_graph(req.offline)

    I = make_instance(
        G,
        seed=req.seed,
        n=(None if req.n == 0 else req.n),
        demand_level=req.demand_level,
        fleet_count=req.fleet_count,
    )

    _apply_overrides(I, req.overrides)

    return G, I


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "application": "GEO-FUEL",
        "version": "1.0.0",
        "methods": METHODS,
    }


@app.post("/api/gps/update")
def gps_update(update: GPSUpdate):
    """Terima posisi GPS kendaraan dari Android/tracker melalui HTTP POST."""
    recorded = update.recorded_at or datetime.now(timezone.utc)
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    payload = update.model_dump()
    payload["recorded_at"] = recorded.astimezone(timezone.utc).isoformat()
    payload["received_at"] = datetime.now(timezone.utc).isoformat()
    payload["source_status"] = "DEVICE_REPORTED"
    with _gps_lock:
        _gps_positions[update.vehicle_id] = payload
    return {"ok": True, "position": payload}


@app.get("/api/gps/positions")
def gps_positions():
    """Posisi terbaru yang diterima server; kosong jika belum ada perangkat."""
    with _gps_lock:
        positions = list(_gps_positions.values())
    return {"count": len(positions), "positions": positions,
            "note": "DEVICE_REPORTED berarti dikirim perangkat; bukan verifikasi independen."}


@app.delete("/api/gps/positions/{vehicle_id}")
def gps_clear(vehicle_id: str):
    with _gps_lock:
        removed = _gps_positions.pop(vehicle_id, None)
    return {"ok": True, "removed": removed is not None}


@app.get("/api/data-info")
def data_info():
    return {
        "terminal": {
            "name": cfg.TERMINAL_NAME,
            "lat": cfg.TERMINAL_LAT,
            "lon": cfg.TERMINAL_LON,
            "data_status": cfg.TERMINAL_DATA_STATUS,
            "stock_status": cfg.TERMINAL_STOCK_STATUS,
        },
        "station_csv": str(cfg.DEFAULT_STATION_CSV),
        "fleet_csv": str(cfg.DEFAULT_FLEET_CSV),
        "traffic_scenarios": cfg.TRAFFIC_LABELS,
        "demand_scenarios": cfg.DEMAND_LABELS,
        "terminal_initial_stock_liters": (
            cfg.TERMINAL_INITIAL_STOCK_LITERS
        ),
        "terminal_stock_status": cfg.TERMINAL_STOCK_STATUS,
        "note": (
            "Periksa label data_status dan ganti data demo "
            "sebelum membuat klaim operasional aktual."
        ),
    }


@app.post("/api/run")
def run(req: RunRequest):
    try:
        G, I = _prepare(req)

        output = simulate(
            I,
            method=req.method,
            traffic_level=req.traffic_level,
            epoch_hours=req.epoch_hours,
            solver_time_limit=req.solver_time_limit,
            seed=req.seed,
        )

        return _serialize_result(I, G, output)

    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menjalankan simulasi: {exc}",
        ) from exc


@app.post("/api/compare")
def compare(req: RunRequest):
    """Jalankan M0-M3 pada instance yang sama untuk perbandingan adil."""
    try:
        G, I = _prepare(req)

        outputs = {}

        for method in METHODS:
            result = simulate(
                I,
                method=method,
                traffic_level=req.traffic_level,
                epoch_hours=req.epoch_hours,
                solver_time_limit=req.solver_time_limit,
                seed=req.seed,
            )

            outputs[method] = {
                "kpi": result["kpi"],
                "solver_fallback_cycles": sum(
                    1
                    for epoch in result["epochs"]
                    if epoch.get("fallback_used")
                ),
                "solver_statuses": sorted(
                    set(
                        str(
                            epoch.get(
                                "solver_status",
                                "not_run",
                            )
                        )
                        for epoch in result["epochs"]
                    )
                ),
            }

        return {
            "comparison": outputs,
            "network_source": I.network_source,
            "warnings": _warnings(I),
        }

    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal membandingkan metode: {exc}",
        ) from exc


STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount(
    "/",
    StaticFiles(
        directory=str(STATIC_DIR),
        html=True,
    ),
    name="web",
)
