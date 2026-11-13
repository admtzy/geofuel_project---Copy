
"""Geospatial Data Layer: jaringan jalan dan instance simulasi GEO-FUEL."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from . import config as cfg
from .inventory import safety_stock


@dataclass
class Instance:
    """Satu instance distribusi: indeks 0 = terminal, 1..n = SPBU."""
    n: int
    station_ids: list[str]
    station_names: list[str]
    station_data_status: list[str]
    station_latlon: list[tuple[float, float]]
    facility_nodes: list[Any]
    capacity: np.ndarray
    initial_stock: np.ndarray
    daily_demand: np.ndarray
    hourly_demand: np.ndarray
    safety_stocks: np.ndarray
    demand_std_liters_per_day: np.ndarray
    mean_lead_time_days: np.ndarray
    lead_time_std_days: np.ndarray
    service_level_z: np.ndarray
    window_start: np.ndarray
    window_end: np.ndarray
    distance_km: np.ndarray
    travel_hours: np.ndarray
    paths: dict[tuple[int, int], list[Any]]
    fleet_ids: list[str]
    fleet_capacities: list[float]
    fleet_data_status: list[str]
    network_source: str
    terminal_name: str
    terminal_latlon: tuple[float, float]
    terminal_initial_stock_liters: float


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Jarak geodesik dua koordinat (latitude, longitude) dalam meter."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(
        math.sqrt(max(0.0, min(1.0, h)))
    )


def _clean_coordinates(
    coordinates: list[tuple[float, float]],
    tolerance_m: float = 0.5,
) -> list[tuple[float, float]]:
    """Menghapus titik berurutan yang terlalu berdekatan."""
    cleaned: list[tuple[float, float]] = []

    for point in coordinates:
        point = (float(point[0]), float(point[1]))

        if not cleaned or haversine_m(cleaned[-1], point) > tolerance_m:
            cleaned.append(point)

    return cleaned


def _edge_geometry_latlon(
    G: nx.DiGraph,
    u: Any,
    v: Any,
    edge_data: dict,
) -> list[tuple[float, float]]:
    """
    Mengambil geometri ruas jalan dalam format (latitude, longitude).

    Geometri OSM/Shapely biasanya menyimpan koordinat (longitude, latitude).
    Urutan koordinat diperiksa agar sesuai dengan arah edge u -> v.
    """
    start = (
        float(G.nodes[u]["y"]),
        float(G.nodes[u]["x"]),
    )
    end = (
        float(G.nodes[v]["y"]),
        float(G.nodes[v]["x"]),
    )

    geometry = edge_data.get("geometry")

    if geometry is None:
        return [start, end]

    try:
        if hasattr(geometry, "coords"):
            raw_coordinates = list(geometry.coords)
        else:
            raw_coordinates = list(geometry)

        # OSM/Shapely: (longitude, latitude)
        coordinates = [
            (float(lat), float(lon))
            for lon, lat, *rest in raw_coordinates
        ]

        if len(coordinates) < 2:
            return [start, end]

        # Tentukan apakah geometri sudah searah u -> v atau harus dibalik.
        forward_error = (
            haversine_m(start, coordinates[0])
            + haversine_m(end, coordinates[-1])
        )
        reverse_error = (
            haversine_m(start, coordinates[-1])
            + haversine_m(end, coordinates[0])
        )

        if reverse_error < forward_error:
            coordinates.reverse()

        # Pastikan titik awal dan akhir tepat pada koordinat node graf.
        coordinates[0] = start
        coordinates[-1] = end

        coordinates = _clean_coordinates(coordinates)

        if len(coordinates) < 2:
            return [start, end]

        return coordinates

    except Exception:
        # Jika geometri tidak dapat dibaca, gunakan fallback endpoint.
        return [start, end]


def _make_offline_grid(
    terminal: tuple[float, float] | None = None,
    size: int = 19,
    spacing_deg: float = 0.0022,
) -> nx.DiGraph:
    """Jaringan grid BIDIRECTIONAL untuk pengujian tanpa internet.

    Grid ini bukan jaringan jalan Bandung. Hanya dipakai agar fungsi
    aplikasi bisa diuji tanpa akses OpenStreetMap.
    """
    terminal = terminal or (cfg.TERMINAL_LAT, cfg.TERMINAL_LON)

    G = nx.DiGraph()
    center = size // 2

    for row in range(size):
        for col in range(size):
            node = row * size + col

            lat = terminal[0] + (row - center) * spacing_deg
            lon = (
                terminal[1]
                + (col - center)
                * spacing_deg
                / max(0.5, math.cos(math.radians(terminal[0])))
            )

            G.add_node(node, y=lat, x=lon)

    for row in range(size):
        for col in range(size):
            u = row * size + col

            for dr, dc in ((1, 0), (0, 1)):
                nr, nc = row + dr, col + dc

                if nr >= size or nc >= size:
                    continue

                v = nr * size + nc

                a = (G.nodes[u]["y"], G.nodes[u]["x"])
                b = (G.nodes[v]["y"], G.nodes[v]["x"])

                length = haversine_m(a, b)

                arterial = (
                    (dr == 1 and col % 4 == 0)
                    or (dc == 1 and row % 4 == 0)
                )

                speed_kmh = 42.0 if arterial else 26.0
                travel_seconds = length / (speed_kmh * 1000 / 3600)

                attrs = {
                    "length": length,
                    "travel_time": travel_seconds,
                    "highway": (
                        "simulated_arterial"
                        if arterial
                        else "simulated_local"
                    ),
                    # Grid simulasi hanya memiliki ruas lurus.
                    "geometry_latlon": [a, b],
                }

                G.add_edge(u, v, **attrs)
                G.add_edge(v, u, **attrs)

    G.graph["data_source"] = "SIMULATED_GRID_OFFLINE"
    return G


def load_graph(
    offline: bool = False,
    dist_m: int = cfg.OSM_NETWORK_RADIUS_M,
    terminal: tuple[float, float] | None = None,
) -> nx.DiGraph:
    """
    Memuat jaringan OSMnx atau grid sintetis jika mode offline dipilih.

    PENTING:
    - offline=True: menggunakan grid simulasi.
    - offline=False: harus berhasil mengambil jaringan OSM.
    - Jika OSM gagal dimuat, fungsi memberikan error agar aplikasi
      tidak diam-diam menampilkan grid simulasi sebagai jalan aktual.

    Geometri setiap ruas disimpan pada atribut geometry_latlon.
    """
    terminal = terminal or (cfg.TERMINAL_LAT, cfg.TERMINAL_LON)

    if offline:
        return _make_offline_grid(terminal)

    try:
        import osmnx as ox

        raw = ox.graph_from_point(
            terminal,
            dist=dist_m,
            network_type="drive",
            simplify=True,
        )

        raw = ox.add_edge_speeds(raw)
        raw = ox.add_edge_travel_times(raw)

        G = nx.DiGraph()

        # Salin seluruh node.
        for node, data in raw.nodes(data=True):
            G.add_node(
                node,
                x=float(data["x"]),
                y=float(data["y"]),
            )

        # Salin edge. Untuk pasangan node yang memiliki beberapa edge,
        # pilih edge dengan panjang paling pendek karena Dijkstra
        # di bawah menggunakan weight="length".
        for u, v, key, data in raw.edges(keys=True, data=True):
            length = float(data.get("length", 0.0))

            if not np.isfinite(length) or length <= 0:
                continue

            travel_time = data.get("travel_time")

            if (
                travel_time is None
                or not np.isfinite(float(travel_time))
                or float(travel_time) <= 0
            ):
                speed = float(data.get("speed_kph", 30.0) or 30.0)
                travel_time = length / max(
                    1.0,
                    speed * 1000 / 3600,
                )

            attrs = {
                "length": length,
                "travel_time": max(0.01, float(travel_time)),
                "highway": data.get("highway", "unknown"),
                "osm_key": key,
            }

            # Ambil geometri lengkap dan ubah menjadi (lat, lon).
            attrs["geometry_latlon"] = _edge_geometry_latlon(
                G,
                u,
                v,
                data,
            )

            # Pilih edge dengan panjang terkecil agar konsisten
            # dengan pencarian rute berbobot length.
            if not G.has_edge(u, v):
                G.add_edge(u, v, **attrs)
            else:
                current = G[u][v]

                current_length = float(
                    current.get("length", float("inf"))
                )

                current_time = float(
                    current.get("travel_time", float("inf"))
                )

                new_is_better = (
                    attrs["length"] < current_length
                    or (
                        math.isclose(
                            attrs["length"],
                            current_length,
                            rel_tol=1e-9,
                        )
                        and attrs["travel_time"] < current_time
                    )
                )

                if new_is_better:
                    G[u][v].update(attrs)

        if not G.nodes or not G.edges:
            raise RuntimeError("Jaringan OpenStreetMap kosong.")

        nearest = min(
            G.nodes,
            key=lambda node: haversine_m(
                terminal,
                (
                    G.nodes[node]["y"],
                    G.nodes[node]["x"],
                ),
            ),
        )

        component = next(
            (
                c
                for c in nx.strongly_connected_components(G)
                if nearest in c
            ),
            None,
        )

        if not component or len(component) < 10:
            raise RuntimeError(
                "Komponen jalan dua arah di sekitar terminal terlalu kecil."
            )

        G = G.subgraph(component).copy()

        G.graph["data_source"] = "OPENSTREETMAP_OSMNX"
        G.graph["osm_dist_m"] = dist_m
        G.graph["geometry_available"] = True

        return G

    except Exception as exc:
        raise ValueError(
            "Gagal memuat jaringan jalan OpenStreetMap. "
            "Pastikan internet aktif, OSMnx terpasang, dan koordinat "
            f"terminal benar. Detail: {exc}. "
            "Jika ingin menjalankan mode tanpa internet, aktifkan "
            "opsi grid SIMULATED (offline)."
        ) from exc


def _nearest_node(
    G: nx.DiGraph,
    lat: float,
    lon: float,
) -> Any:
    if not G.nodes:
        raise ValueError("Graf jalan kosong.")

    return min(
        G.nodes,
        key=lambda node: (
            (G.nodes[node]["y"] - lat) ** 2
            + (G.nodes[node]["x"] - lon) ** 2
        ),
    )


def _hourly_profile() -> np.ndarray:
    """Profil konsumsi harian dengan puncak pagi dan sore."""
    profile = np.array(
        [
            0.55
            + 0.90 * math.exp(-((hour - 8) / 2.5) ** 2)
            + 0.80 * math.exp(-((hour - 17) / 2.5) ** 2)
            for hour in range(24)
        ],
        dtype=float,
    )

    return profile / profile.mean()


def _read_stations(csv_path: str | Path) -> pd.DataFrame:
    path = Path(csv_path)

    if not path.is_absolute():
        path = cfg.PROJECT_ROOT / path

    if not path.exists():
        raise FileNotFoundError(
            f"File data SPBU tidak ditemukan: {path}. "
            "Gunakan data/stations_demo.csv atau siapkan CSV aktual "
            "sesuai data/spbu_template.csv."
        )

    df = pd.read_csv(path)

    required = {
        "station_id",
        "name",
        "lat",
        "lon",
        "capacity_liters",
        "initial_stock_liters",
        "daily_demand_liters",
    }

    missing = sorted(required - set(df.columns))

    if missing:
        raise ValueError(
            f"Kolom CSV SPBU belum lengkap: {missing}"
        )

    if df.empty:
        raise ValueError("CSV SPBU tidak memiliki baris data.")

    if df["station_id"].astype(str).duplicated().any():
        raise ValueError(
            "station_id pada CSV SPBU harus unik."
        )

    numeric_cols = [
        "lat",
        "lon",
        "capacity_liters",
        "initial_stock_liters",
        "daily_demand_liters",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="raise")

    if (
        not df["lat"].between(-90, 90).all()
        or not df["lon"].between(-180, 180).all()
    ):
        raise ValueError(
            "Koordinat latitude/longitude di luar rentang valid."
        )

    if (
        (df["capacity_liters"] <= 0).any()
        or (df["daily_demand_liters"] <= 0).any()
    ):
        raise ValueError(
            "Kapasitas tangki dan konsumsi harian harus lebih besar dari nol."
        )

    if (df["initial_stock_liters"] < 0).any():
        raise ValueError("Stok awal tidak boleh negatif.")

    if (
        df["initial_stock_liters"] > df["capacity_liters"]
    ).any():
        raise ValueError(
            "Stok awal tidak boleh melebihi kapasitas tangki."
        )

    if "window_start" not in df:
        df["window_start"] = cfg.START_HOUR

    if "window_end" not in df:
        df["window_end"] = cfg.END_HOUR

    if "data_status" not in df:
        df["data_status"] = "UNVERIFIED"

    df["data_status"] = (
        df["data_status"]
        .fillna("UNVERIFIED")
        .astype(str)
        .str.strip()
    )

    df.loc[
        df["data_status"] == "",
        "data_status",
    ] = "UNVERIFIED"

    optional_defaults = {
        "demand_std_liters_per_day": np.nan,
        "mean_lead_time_days": cfg.MEAN_LEAD_TIME_DAYS,
        "lead_time_std_days": cfg.LEAD_TIME_STD_DAYS,
        "service_level_z": cfg.SERVICE_LEVEL_Z,
    }

    for col, default in optional_defaults.items():
        if col not in df:
            df[col] = default

        df[col] = (
            pd.to_numeric(df[col], errors="coerce")
            .fillna(default)
        )

    if (df["demand_std_liters_per_day"] < 0).any():
        raise ValueError(
            "demand_std_liters_per_day tidak boleh negatif."
        )

    if (
        (df["mean_lead_time_days"] < 0).any()
        or (df["lead_time_std_days"] < 0).any()
    ):
        raise ValueError(
            "Parameter lead time tidak boleh negatif."
        )

    if (df["service_level_z"] < 0).any():
        raise ValueError("service_level_z tidak boleh negatif.")

    df["window_start"] = pd.to_numeric(
        df["window_start"],
        errors="raise",
    )

    df["window_end"] = pd.to_numeric(
        df["window_end"],
        errors="raise",
    )

    if (
        (df["window_start"] < 0).any()
        or (df["window_end"] > 24).any()
    ):
        raise ValueError(
            "window_start/window_end harus dalam jam 0..24."
        )

    if (df["window_end"] <= df["window_start"]).any():
        raise ValueError(
            "window_end harus lebih besar dari window_start."
        )

    if (
        (df["mean_lead_time_days"] <= 0).any()
        or (df["lead_time_std_days"] < 0).any()
    ):
        raise ValueError(
            "Parameter lead time harus positif/non-negatif."
        )

    if (df["service_level_z"] <= 0).any():
        raise ValueError(
            "service_level_z harus lebih besar dari nol."
        )

    return df.reset_index(drop=True)


def _read_fleet(
    csv_path: str | Path,
    fleet_count: int,
) -> tuple[list[str], list[float], list[str]]:
    path = Path(csv_path)

    if not path.is_absolute():
        path = cfg.PROJECT_ROOT / path

    if not path.exists():
        ids = [
            f"MT-SIM-{i+1:02d}"
            for i in range(len(cfg.DEFAULT_FLEET_CAPACITIES))
        ]

        capacities = list(
            map(float, cfg.DEFAULT_FLEET_CAPACITIES)
        )

        statuses = ["SIMULATED"] * len(ids)

    else:
        fleet = pd.read_csv(path)

        required = {
            "vehicle_id",
            "capacity_liters",
        }

        missing = sorted(required - set(fleet.columns))

        if missing:
            raise ValueError(
                f"Kolom CSV armada belum lengkap: {missing}"
            )

        fleet["capacity_liters"] = pd.to_numeric(
            fleet["capacity_liters"],
            errors="raise",
        )

        if (fleet["capacity_liters"] <= 0).any():
            raise ValueError(
                "Kapasitas armada harus lebih besar dari nol."
            )

        ids = (
            fleet["vehicle_id"]
            .astype(str)
            .str.strip()
            .tolist()
        )

        if any(not vehicle_id for vehicle_id in ids):
            raise ValueError("vehicle_id tidak boleh kosong.")

        if len(set(ids)) != len(ids):
            raise ValueError(
                "vehicle_id pada CSV armada harus unik."
            )

        capacities = (
            fleet["capacity_liters"]
            .astype(float)
            .tolist()
        )

        if "data_status" not in fleet:
            fleet["data_status"] = "UNVERIFIED"

        fleet["data_status"] = (
            fleet["data_status"]
            .fillna("UNVERIFIED")
            .astype(str)
            .str.strip()
        )

        fleet.loc[
            fleet["data_status"] == "",
            "data_status",
        ] = "UNVERIFIED"

        statuses = fleet["data_status"].tolist()

    if not 1 <= fleet_count <= len(ids):
        raise ValueError(
            f"fleet_count harus 1..{len(ids)}"
        )

    return (
        ids[:fleet_count],
        capacities[:fleet_count],
        statuses[:fleet_count],
    )


def make_instance(
    G: nx.DiGraph,
    seed: int = 7,
    n: int | None = 10,
    demand_level: int = 1,
    event_factor: float = 1.0,
    fleet_count: int = 4,
    station_csv: str | Path = cfg.DEFAULT_STATION_CSV,
    fleet_csv: str | Path = cfg.DEFAULT_FLEET_CSV,
    terminal: tuple[float, float] | None = None,
) -> Instance:
    """Bentuk data input dan matriks perjalanan untuk satu eksperimen."""
    if n is not None and n < 1:
        raise ValueError("n minimal 1 atau None untuk memakai semua SPBU.")
    if not np.isfinite(event_factor) or event_factor <= 0:
        raise ValueError("event_factor harus angka positif.")

    if demand_level not in (0, 1, 2):
        raise ValueError(
            "demand_level harus 0, 1, atau 2."
        )

    terminal = terminal or (
        cfg.TERMINAL_LAT,
        cfg.TERMINAL_LON,
    )

    df_all = _read_stations(station_csv)
    df = (df_all if n is None else df_all.head(n)).copy()

    if df.empty:
        raise ValueError("CSV tidak berisi SPBU.")

    terminal_node = _nearest_node(G, *terminal)

    terminal_snap_m = haversine_m(
        terminal,
        (
            float(G.nodes[terminal_node]["y"]),
            float(G.nodes[terminal_node]["x"]),
        ),
    )

    if terminal_snap_m > cfg.MAX_SNAP_DISTANCE_M:
        raise ValueError(
            f"Koordinat terminal berjarak {terminal_snap_m:.0f} m "
            "dari jaringan jalan terdekat. Periksa koordinat atau "
            "perluas cakupan jaringan."
        )

    station_nodes = []

    for row in df.itertuples():
        coord = (float(row.lat), float(row.lon))
        node = _nearest_node(G, *coord)

        snap_distance = haversine_m(
            coord,
            (
                float(G.nodes[node]["y"]),
                float(G.nodes[node]["x"]),
            ),
        )

        if snap_distance > cfg.MAX_SNAP_DISTANCE_M:
            raise ValueError(
                f"Koordinat {row.station_id} berjarak "
                f"{snap_distance:.0f} m dari jaringan jalan. "
                "Periksa koordinat SPBU atau perluas cakupan jaringan."
            )

        station_nodes.append(node)

    facilities = [terminal_node] + station_nodes

    count = len(facilities)

    distance = np.zeros((count, count), dtype=float)
    travel = np.zeros((count, count), dtype=float)

    paths: dict[tuple[int, int], list[Any]] = {}

    # Hitung rute terpendek berdasarkan panjang jalan.
    # Path menyimpan urutan node; geometri setiap edge disimpan di G.
    for i, source in enumerate(facilities):
        distances, path_map = nx.single_source_dijkstra(
            G,
            source,
            weight="length",
        )

        for j, target in enumerate(facilities):
            if target not in path_map:
                raise ValueError(
                    f"Tidak ada lintasan jalan terarah dari fasilitas "
                    f"{i} ke {j}. Periksa lokasi atau jaringan jalan."
                )

            path = path_map[target]
            paths[(i, j)] = path

            if i == j:
                continue

            distance[i, j] = (
                float(distances[target]) / 1000.0
            )

            seconds = 0.0

            for u, v in zip(path, path[1:]):
                seconds += float(
                    G[u][v].get("travel_time", 0.0)
                )

            travel[i, j] = seconds / 3600.0

    fleet_ids, fleet_caps, fleet_statuses = _read_fleet(
        fleet_csv,
        fleet_count,
    )

    factor = cfg.demand_factor(demand_level) * float(event_factor)
    rng = np.random.default_rng(seed)

    capacity = np.zeros(count, dtype=float)
    initial = np.zeros(count, dtype=float)
    demand = np.zeros(count, dtype=float)

    window_start = np.zeros(count, dtype=float)
    window_end = np.zeros(count, dtype=float)

    station_ids = ["TERMINAL"]
    station_names = [cfg.TERMINAL_NAME]
    data_status = ["CONFIGURATION"]

    hourly = np.zeros((count, 24), dtype=float)
    profile = _hourly_profile()

    for idx, row in enumerate(df.itertuples(), start=1):
        capacity[idx] = float(row.capacity_liters)
        initial[idx] = float(row.initial_stock_liters)
        demand[idx] = float(row.daily_demand_liters) * factor

        window_start[idx] = float(row.window_start)
        window_end[idx] = float(row.window_end)

        noise = np.clip(
            rng.normal(1.0, 0.06, size=24),
            0.75,
            1.25,
        )

        station_profile = profile * noise
        station_profile = (
            station_profile / station_profile.mean()
        )

        hourly[idx, :] = (
            demand[idx] * station_profile / 24.0
        )

        station_ids.append(str(row.station_id))
        station_names.append(str(row.name))
        data_status.append(str(row.data_status))

    safety = np.zeros(count, dtype=float)
    demand_std = np.zeros(count, dtype=float)
    mean_lead = np.zeros(count, dtype=float)
    lead_std = np.zeros(count, dtype=float)
    service_z = np.zeros(count, dtype=float)

    for idx, row in enumerate(df.itertuples(), start=1):
        row_std = float(row.demand_std_liters_per_day)

        if not np.isfinite(row_std):
            row_std = (
                cfg.DEMAND_STD_FRACTION
                * float(row.daily_demand_liters)
                * factor
            )
        else:
            row_std *= factor

        demand_std[idx] = row_std
        mean_lead[idx] = float(row.mean_lead_time_days)
        lead_std[idx] = float(row.lead_time_std_days)
        service_z[idx] = float(row.service_level_z)

        safety[idx] = safety_stock(
            demand[idx],
            mean_lead_time_days=mean_lead[idx],
            lead_time_std_days=lead_std[idx],
            z=service_z[idx],
            demand_std_liters_per_day=demand_std[idx],
        )

    snapped_terminal = (
        float(G.nodes[terminal_node]["y"]),
        float(G.nodes[terminal_node]["x"]),
    )

    snapped_stations = [snapped_terminal] + [
        (
            float(G.nodes[node]["y"]),
            float(G.nodes[node]["x"]),
        )
        for node in station_nodes
    ]

    return Instance(
        n=len(df),
        station_ids=station_ids,
        station_names=station_names,
        station_data_status=data_status,
        station_latlon=snapped_stations,
        facility_nodes=facilities,
        capacity=capacity,
        initial_stock=initial,
        daily_demand=demand,
        hourly_demand=hourly,
        safety_stocks=safety,
        demand_std_liters_per_day=demand_std,
        mean_lead_time_days=mean_lead,
        lead_time_std_days=lead_std,
        service_level_z=service_z,
        window_start=window_start,
        window_end=window_end,
        distance_km=distance,
        travel_hours=travel,
        paths=paths,
        fleet_ids=fleet_ids,
        fleet_capacities=fleet_caps,
        fleet_data_status=fleet_statuses,
        network_source=str(
            G.graph.get("data_source", "UNKNOWN")
        ),
        terminal_name=cfg.TERMINAL_NAME,
        terminal_latlon=snapped_terminal,
        terminal_initial_stock_liters=(
            cfg.TERMINAL_INITIAL_STOCK_LITERS
        ),
    )
