"""MILP HFVRPTW: formulasi Pyomo dan penyelesaian dengan HiGHS.

Index 0 adalah depot/terminal; index 1..n adalah kandidat SPBU.
Setiap SPBU maksimal dilayani satu kendaraan pada satu siklus perencanaan.
Pengiriman parsial diizinkan melalui variabel q dan unmet u.
"""
from __future__ import annotations

from typing import Any

from . import config as cfg


def solve_hfvrptw(
    distance_km,
    travel_hours,
    required_liters,
    unmet_penalty_per_liter,
    window_start,
    window_end,
    vehicle_capacities,
    depot_available_liters: float,
    start_hour: float,
    end_hour: float = cfg.END_HOUR,
    time_limit_seconds: int = 10,
    mip_gap: float = 0.02,
    min_delivery_liters: float = cfg.MIN_DELIVERY_LITERS,
) -> dict[str, Any]:
    """Selesaikan HFVRPTW menggunakan Pyomo + appsi_highs.

    Mengembalikan rute DAN volume hasil solver. Jika Pyomo/HiGHS tidak ada,
    fungsi mengembalikan status solver_unavailable agar pemanggil dapat
    menerapkan fallback yang diberi label dengan jelas.
    """
    try:
        import pyomo.environ as pyo
    except Exception as exc:
        return {"status": "solver_unavailable", "message": f"Pyomo belum tersedia: {exc}",
                "routes": [], "unmet": {}, "objective": None, "has_solution": False}

    n = len(required_liters) - 1
    vehicle_count = len(vehicle_capacities)
    if n <= 0 or vehicle_count <= 0:
        return {"status": "empty_problem", "message": "Tidak ada SPBU atau kendaraan untuk dioptimasi.",
                "routes": [], "unmet": {}, "objective": 0.0, "has_solution": True}

    N = range(1, n + 1)
    V = range(0, n + 1)
    K = range(vehicle_count)
    max_tau = max(float(x) for x in travel_hours.flat) if hasattr(travel_hours, "flat") else max(map(float, travel_hours))
    big_m = max(100.0, (end_hour - start_hour) + (n + 1) * max_tau + 10.0)

    m = pyo.ConcreteModel(name="GEOFUEL_HFVRPTW")
    m.x = pyo.Var(V, V, K, domain=pyo.Binary)       # kendaraan k bergerak i -> j
    m.y = pyo.Var(N, K, domain=pyo.Binary)          # SPBU i dilayani kendaraan k
    m.z = pyo.Var(K, domain=pyo.Binary)             # kendaraan k digunakan
    m.q = pyo.Var(N, K, domain=pyo.NonNegativeReals)  # liter dikirim oleh k ke i
    m.u = pyo.Var(N, domain=pyo.NonNegativeReals)   # liter kebutuhan belum terpenuhi
    m.T = pyo.Var(N, K, bounds=(start_hour, end_hour))  # waktu mulai pelayanan
    m.L = pyo.Var(N, domain=pyo.NonNegativeReals)   # keterlambatan jam
    m.r = pyo.Var(N, K, bounds=(0, max(1, n)))      # urutan kunjungan MTZ

    for k in K:
        for i in V:
            m.x[i, i, k].fix(0)

    # Fungsi tujuan: jarak + waktu perjalanan/pelayanan + biaya tetap + penalti.
    travel_cost = sum(
        (cfg.COST_PER_KM * float(distance_km[i, j])
         + cfg.COST_PER_DRIVING_HOUR * float(travel_hours[i, j])) * m.x[i, j, k]
        for k in K for i in V for j in V if i != j
    )
    service_cost = sum(
        cfg.COST_PER_DRIVING_HOUR * (
            cfg.UNLOADING_BASE_HOURS * m.y[i, k]
            + m.q[i, k] / cfg.UNLOADING_RATE_LITERS_PER_HOUR
        )
        for i in N for k in K
    )
    # Satu proses loading untuk setiap kendaraan/trip yang digunakan.
    loading_cost = sum(
        cfg.COST_PER_DRIVING_HOUR * cfg.LOADING_HOURS * m.z[k]
        for k in K
    )
    fixed_cost = sum(cfg.FIXED_COST_PER_TRIP * m.z[k] for k in K)
    late_cost = sum(cfg.LATE_PENALTY_PER_HOUR * m.L[i] for i in N)
    shortage_cost = sum(float(unmet_penalty_per_liter[i]) * m.u[i] for i in N)
    m.objective = pyo.Objective(
        expr=travel_cost + service_cost + loading_cost + fixed_cost + late_cost + shortage_cost,
        sense=pyo.minimize,
    )

    m.constraints = pyo.ConstraintList()
    c = m.constraints

    # Kebutuhan: pengiriman + kebutuhan yang tidak terpenuhi = kebutuhan.
    for i in N:
        c.add(sum(m.q[i, k] for k in K) + m.u[i] == float(required_liters[i]))
        c.add(sum(m.y[i, k] for k in K) <= 1)
        for k in K:
            c.add(m.q[i, k] <= float(required_liters[i]) * m.y[i, k])
            c.add(m.q[i, k] >= min(float(min_delivery_liters), float(required_liters[i])) * m.y[i, k])
            c.add(m.y[i, k] <= m.z[k])

            # Aliran masuk dan keluar untuk SPBU yang ditugaskan.
            c.add(sum(m.x[i, j, k] for j in V if j != i) == m.y[i, k])
            c.add(sum(m.x[j, i, k] for j in V if j != i) == m.y[i, k])

            # Jendela penerimaan dan waktu kedatangan dari terminal.
            c.add(m.T[i, k] >= float(window_start[i]) - big_m * (1 - m.y[i, k]))
            c.add(
                m.T[i, k] >= float(start_hour + cfg.LOADING_HOURS + travel_hours[0, i])
                - big_m * (1 - m.x[0, i, k])
            )
            c.add(m.L[i] >= m.T[i, k] - float(window_end[i]) - big_m * (1 - m.y[i, k]))
            c.add(
                m.T[i, k] + cfg.UNLOADING_BASE_HOURS * m.y[i, k] + m.q[i, k] / cfg.UNLOADING_RATE_LITERS_PER_HOUR + float(travel_hours[i, 0])
                <= float(end_hour) + big_m * (1 - m.x[i, 0, k])
            )

            # Urutan kunjungan: aktif hanya jika SPBU ditugaskan.
            c.add(m.r[i, k] >= m.y[i, k])
            c.add(m.r[i, k] <= n * m.y[i, k])

            for j in N:
                if j == i:
                    continue
                c.add(
                    m.T[j, k] >= m.T[i, k] + cfg.UNLOADING_BASE_HOURS * m.y[i, k]
                    + m.q[i, k] / cfg.UNLOADING_RATE_LITERS_PER_HOUR + float(travel_hours[i, j]) - big_m * (1 - m.x[i, j, k])
                )
                # Miller-Tucker-Zemlin untuk mencegah subtour.
                c.add(m.r[j, k] >= m.r[i, k] + 1 - (n + 1) * (1 - m.x[i, j, k]))

    for k in K:
        c.add(sum(m.q[i, k] for i in N) <= float(vehicle_capacities[k]) * m.z[k])
        c.add(sum(m.x[0, j, k] for j in N) == m.z[k])
        c.add(sum(m.x[i, 0, k] for i in N) == m.z[k])

    # Ekstensi supply-chain: total BBM yang dikirim tidak boleh melebihi stok terminal.
    c.add(sum(m.q[i, k] for i in N for k in K) <= max(0.0, float(depot_available_liters)))

    try:
        solver = pyo.SolverFactory("appsi_highs")
        if not solver.available(exception_flag=False):
            return {"status": "solver_unavailable", "message": "Solver appsi_highs tidak tersedia.",
                    "routes": [], "unmet": {}, "objective": None, "has_solution": False}
        solver.config.time_limit = float(time_limit_seconds)
        # HiGHS menerima relative MIP gap sebagai opsi solver.
        solver.highs_options["mip_rel_gap"] = float(mip_gap)
        result = solver.solve(m)
        termination = str(result.solver.termination_condition)
        solver_status = str(result.solver.status)
    except Exception as exc:
        return {"status": "solver_error", "message": str(exc), "routes": [],
                "unmet": {}, "objective": None, "has_solution": False}

    # Hanya ambil hasil apabila variabel keputusan memiliki nilai.
    z_values = [pyo.value(m.z[k], exception=False) for k in K]
    if not any(value is not None and value > 0.5 for value in z_values):
        has_solution = all(pyo.value(m.u[i], exception=False) is not None for i in N)
        if not has_solution:
            return {"status": termination, "solver_status": solver_status,
                    "message": "Solver tidak mengembalikan solusi yang dapat dibaca.",
                    "routes": [], "unmet": {}, "objective": None, "has_solution": False}

    routes: list[dict[str, Any]] = []
    for k in K:
        z_value = pyo.value(m.z[k], exception=False)
        if z_value is None or z_value <= 0.5:
            continue
        sequence: list[int] = []
        deliveries: dict[int, float] = {}
        current = 0
        visited = set()
        while True:
            next_station = None
            for j in V:
                if j == current:
                    continue
                value = pyo.value(m.x[current, j, k], exception=False)
                if value is not None and value > 0.5:
                    next_station = j
                    break
            if next_station in (None, 0) or next_station in visited:
                break
            visited.add(next_station)
            sequence.append(int(next_station))
            q_value = pyo.value(m.q[next_station, k], exception=False) or 0.0
            deliveries[int(next_station)] = max(0.0, float(q_value))
            current = next_station
            if len(sequence) > n:
                break
        if sequence:
            routes.append({"vehicle_index": int(k), "sequence": sequence, "deliveries": deliveries})

    unmet = {}
    for i in N:
        value = pyo.value(m.u[i], exception=False)
        unmet[int(i)] = max(0.0, float(value or 0.0))

    objective_value = pyo.value(m.objective, exception=False)
    return {
        "status": termination,
        "solver_status": solver_status,
        "message": "Solusi MILP berhasil dibaca." if routes else "Solver menghasilkan solusi tanpa rute pengiriman pada siklus ini.",
        "has_solution": True,
        "routes": routes,
        "unmet": unmet,
        "objective": float(objective_value) if objective_value is not None else None,
    }
