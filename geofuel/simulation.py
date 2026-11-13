"""Adaptive Decision Engine: simulasi stok, armada, dan rolling-horizon re-optimization."""
from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from . import config as cfg
from . import inventory
from .model import solve_hfvrptw
from .data import Instance

METHODS = ("M0", "M1", "M2", "M3")


def _plan_factor(method: str, hour: float, traffic_level: int) -> float:
    """M0-M2 merencanakan dengan free-flow; M3 memakai faktor lalu lintas skenario."""
    return cfg.traffic_factor(hour, traffic_level) if method == "M3" else 1.0


def _assess_candidates(I: Instance, stock: np.ndarray, now: float,
                       method: str, traffic_level: int,
                       reserved_until: dict[int, float]) -> list[dict[str, Any]]:
    factor = _plan_factor(method, now, traffic_level)
    candidates = []
    for i in range(1, I.n + 1):
        if reserved_until.get(i, -math.inf) > now + 1e-8:
            continue
        travel = float(I.travel_hours[0, i]) * factor
        info = inventory.assess_station(
            stock_liters=stock[i], daily_demand_liters=I.daily_demand[i],
            tank_capacity_liters=I.capacity[i], safety_stock_liters=I.safety_stocks[i],
            travel_time_hours=travel,
        )
        if info["needs_replenishment"]:
            info.update({
                "index": i,
                "station_id": I.station_ids[i],
                "station_name": I.station_names[i],
                "travel_time_plan_hours": travel,
            })
            candidates.append(info)
    candidates.sort(key=lambda x: (x["time_to_safety_hours"], -x["urgency"]))
    return candidates


def _nearest_neighbour_order(I: Instance, selected: list[int]) -> list[int]:
    remaining = list(selected)
    ordered = []
    current = 0
    while remaining:
        nxt = min(remaining, key=lambda i: float(I.distance_km[current, i]))
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return ordered


def _heuristic_plans(I: Instance, candidates: list[dict[str, Any]],
                     idle_vehicle_indices: list[int], method: str,
                     depot_available_liters: float) -> list[dict[str, Any]]:
    """Heuristik pembanding M0 (jarak) dan M1 (urgensi stok)."""
    remaining = {c["index"]: c for c in candidates}
    plans: list[dict[str, Any]] = []
    depot_remaining = max(0.0, float(depot_available_liters))
    vehicles = sorted(idle_vehicle_indices, key=lambda k: -I.fleet_capacities[k])

    for vehicle_index in vehicles:
        capacity_left = float(I.fleet_capacities[vehicle_index])
        selected: list[int] = []
        volumes: dict[int, float] = {}
        current = 0

        while remaining and capacity_left >= cfg.MIN_DELIVERY_LITERS and depot_remaining >= cfg.MIN_DELIVERY_LITERS:
            if method == "M0":
                station_index = min(
                    remaining,
                    key=lambda i: float(I.distance_km[current, i]),
                )
            else:  # M1: ambil yang paling dekat ke batas safety stock terlebih dahulu
                station_index = min(
                    remaining,
                    key=lambda i: (
                        float(remaining[i]["time_to_safety_hours"]),
                        -float(remaining[i]["urgency"]),
                    ),
                )

            needed = float(remaining[station_index]["required_liters"])
            amount = min(needed, capacity_left, depot_remaining)
            if amount < cfg.MIN_DELIVERY_LITERS:
                remaining.pop(station_index)
                continue
            selected.append(station_index)
            volumes[station_index] = amount
            capacity_left -= amount
            depot_remaining -= amount
            remaining.pop(station_index)
            current = station_index

        if selected:
            if method == "M1":
                # Prioritas menentukan siapa yang dipilih; urutan perjalanan dibuat lebih efisien.
                selected = _nearest_neighbour_order(I, selected)
            plans.append({"vehicle_index": vehicle_index, "sequence": selected,
                          "deliveries": volumes, "source": "heuristic"})
    return plans


def _milp_plans(I: Instance, candidates: list[dict[str, Any]],
                idle_vehicle_indices: list[int], method: str, now: float,
                traffic_level: int, solver_time_limit: int,
                depot_available_liters: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not candidates or not idle_vehicle_indices:
        return [], {"status": "not_run", "message": "Tidak ada kandidat atau kendaraan idle."}

    station_indices = [c["index"] for c in candidates]
    local_to_global = {local: global_i for local, global_i in enumerate(station_indices, start=1)}
    all_indices = [0] + station_indices
    factor = _plan_factor(method, now, traffic_level)
    D = I.distance_km[np.ix_(all_indices, all_indices)]
    T = I.travel_hours[np.ix_(all_indices, all_indices)] * factor

    count = len(station_indices)
    qreq = np.zeros(count + 1, dtype=float)
    penalty = np.zeros(count + 1, dtype=float)
    a = np.zeros(count + 1, dtype=float)
    b = np.zeros(count + 1, dtype=float)
    candidate_by_index = {c["index"]: c for c in candidates}
    for local, global_i in local_to_global.items():
        c = candidate_by_index[global_i]
        qreq[local] = float(c["required_liters"])
        penalty[local] = inventory.unmet_penalty_per_liter(float(c["urgency"]))
        a[local] = float(I.window_start[global_i])
        b[local] = float(I.window_end[global_i])

    caps = [float(I.fleet_capacities[k]) for k in idle_vehicle_indices]
    started = time.perf_counter()
    result = solve_hfvrptw(
        distance_km=D, travel_hours=T, required_liters=qreq,
        unmet_penalty_per_liter=penalty, window_start=a, window_end=b,
        vehicle_capacities=caps, depot_available_liters=depot_available_liters,
        start_hour=now, end_hour=cfg.END_HOUR, time_limit_seconds=solver_time_limit,
    )
    result["solve_seconds"] = round(time.perf_counter() - started, 3)

    plans = []
    for route in result.get("routes", []):
        global_sequence = [local_to_global[x] for x in route["sequence"]]
        global_deliveries = {
            local_to_global[int(local_i)]: float(amount)
            for local_i, amount in route["deliveries"].items()
            if int(local_i) in local_to_global and float(amount) >= cfg.MIN_DELIVERY_LITERS
        }
        global_sequence = [i for i in global_sequence if i in global_deliveries]
        if global_sequence:
            plans.append({
                "vehicle_index": idle_vehicle_indices[int(route["vehicle_index"])],
                "sequence": global_sequence,
                "deliveries": global_deliveries,
                "source": "MILP",
            })
    return plans, result


def _evaluate_trip(I: Instance, vehicle_index: int, sequence: list[int],
                   deliveries: dict[int, float], start_time: float,
                   traffic_level: int) -> dict[str, Any] | None:
    """Evaluasi satu rute dengan kondisi lalu lintas yang dialami saat simulasi."""
    if not sequence:
        return None
    current_time = float(start_time) + cfg.LOADING_HOURS
    current_location = 0
    distance_total = 0.0
    driving_hours = 0.0
    # Kendaraan berangkat setelah satu kali proses loading. Loading dicatat
    # terpisah dari waktu bongkar agar biaya waktu tidak menghitungnya dua kali.
    loading_hours = float(cfg.LOADING_HOURS)
    service_hours = 0.0
    departure_time = current_time
    lateness_hours = 0.0
    stops: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []

    for station_index in sequence:
        quantity = float(deliveries.get(station_index, 0.0))
        if quantity < cfg.MIN_DELIVERY_LITERS:
            continue
        depart = current_time
        multiplier = cfg.traffic_factor(depart, traffic_level)
        drive = float(I.travel_hours[current_location, station_index]) * multiplier
        arrive = depart + drive
        service_start = max(arrive, float(I.window_start[station_index]))
        late = max(0.0, service_start - float(I.window_end[station_index]))
        unload = cfg.UNLOADING_BASE_HOURS + quantity / cfg.UNLOADING_RATE_LITERS_PER_HOUR
        service_end = service_start + unload
        if service_end > cfg.END_HOUR + 1e-8:
            return None

        distance_leg = float(I.distance_km[current_location, station_index])
        distance_total += distance_leg
        driving_hours += drive
        service_hours += unload
        lateness_hours += late
        legs.append({
            "from_index": current_location, "to_index": station_index,
            "depart_hour": depart, "arrive_hour": arrive,
        })
        stops.append({
            "index": station_index,
            "station_id": I.station_ids[station_index],
            "station_name": I.station_names[station_index],
            "quantity_liters": quantity,
            "arrival_hour": arrive,
            "service_start_hour": service_start,
            "service_end_hour": service_end,
            "lateness_hours": late,
            "on_time": late <= 1e-8,
        })
        current_time = service_end
        current_location = station_index

    if not stops:
        return None

    depart = current_time
    multiplier = cfg.traffic_factor(depart, traffic_level)
    return_drive = float(I.travel_hours[current_location, 0]) * multiplier
    return_time = depart + return_drive
    if return_time > cfg.END_HOUR + 1e-8:
        return None
    distance_total += float(I.distance_km[current_location, 0])
    driving_hours += return_drive
    legs.append({
        "from_index": current_location, "to_index": 0,
        "depart_hour": depart, "arrive_hour": return_time,
    })

    delivered = sum(stop["quantity_liters"] for stop in stops)
    return {
        "vehicle_index": vehicle_index,
        "vehicle_id": I.fleet_ids[vehicle_index],
        "capacity_liters": float(I.fleet_capacities[vehicle_index]),
        "start_hour": float(start_time),
        "departure_hour": float(departure_time),
        "loading_hours": loading_hours,
        "end_hour": float(return_time),
        "elapsed_hours": float(return_time - start_time),
        "distance_km": float(distance_total),
        "driving_hours": float(driving_hours),
        "service_hours": float(service_hours),
        "lateness_hours": float(lateness_hours),
        "delivered_liters": float(delivered),
        "sequence": [s["index"] for s in stops],
        "stops": stops,
        "legs": legs,
    }


def simulate(I: Instance, method: str = "M3", traffic_level: int = 1,
             epoch_hours: float = cfg.DEFAULT_EPOCH_HOURS,
             solver_time_limit: int = 10, seed: int = 7) -> dict[str, Any]:
    """Simulasikan distribusi 06.00-22.00 dan re-optimasi rolling horizon."""
    if method not in METHODS:
        raise ValueError(f"method harus salah satu dari {METHODS}")
    if epoch_hours <= 0:
        raise ValueError("epoch_hours harus lebih besar dari nol")
    if traffic_level not in (0, 1, 2):
        raise ValueError("traffic_level harus 0, 1, atau 2")

    stock = I.initial_stock.copy().astype(float)
    depot_stock = float(I.terminal_initial_stock_liters)
    current_time = cfg.START_HOUR
    hist_times = [current_time]
    hist_stock = [stock.copy()]
    pending_deliveries: list[dict[str, Any]] = []
    reserved_until: dict[int, float] = {}
    trips: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    available_at = [cfg.START_HOUR] * len(I.fleet_capacities)
    stockout_by_station = np.zeros(I.n + 1, dtype=float)
    total_demand = 0.0

    def apply_due_deliveries() -> None:
        for event in pending_deliveries:
            if not event["applied"] and event["delivery_hour"] <= current_time + 1e-8:
                idx = int(event["station_index"])
                stock[idx] = min(I.capacity[idx], stock[idx] + float(event["quantity_liters"]))
                event["applied"] = True

    def advance_to(target_time: float) -> None:
        nonlocal current_time, total_demand
        target_time = min(cfg.END_HOUR, float(target_time))
        while current_time < target_time - 1e-9:
            apply_due_deliveries()
            next_events = [e["delivery_hour"] for e in pending_deliveries
                           if not e["applied"] and e["delivery_hour"] > current_time + 1e-8]
            next_event = min(next_events) if next_events else target_time
            next_hour_boundary = math.floor(current_time + 1e-9) + 1.0
            step_end = min(current_time + cfg.SIMULATION_STEP_HOURS, target_time, next_event, next_hour_boundary)
            dt = step_end - current_time
            if dt <= 1e-9:
                current_time = step_end
                apply_due_deliveries()
                continue
            hour_index = min(23, max(0, int(math.floor(current_time + 1e-9))))
            demand_step = I.hourly_demand[:, hour_index] * dt
            demand_step[0] = 0.0
            available_stock = stock.copy()
            consumed = np.minimum(available_stock, demand_step)
            shortage = demand_step - consumed
            stock[:] = available_stock - consumed
            stockout_by_station[:] += shortage
            total_demand += float(demand_step.sum())
            current_time = step_end
            apply_due_deliveries()
            hist_times.append(float(current_time))
            hist_stock.append(stock.copy())

    decision_times = np.arange(cfg.START_HOUR, cfg.END_HOUR, epoch_hours)
    for decision_time in decision_times:
        advance_to(float(decision_time))
        idle = [k for k, ready in enumerate(available_at) if ready <= current_time + 1e-8]
        if not idle:
            continue

        candidates = _assess_candidates(I, stock, current_time, method, traffic_level, reserved_until)
        epoch_entry: dict[str, Any] = {
            "time_hour": float(current_time),
            "traffic_factor": float(cfg.traffic_factor(current_time, traffic_level)),
            "idle_vehicles": [{"vehicle_id": I.fleet_ids[k],
                               "capacity_liters": float(I.fleet_capacities[k])} for k in idle],
            "candidates": [dict(c) for c in candidates],
            "solver_status": "heuristic",
            "solve_seconds": 0.0,
            "routes": [],
        }

        if not candidates:
            epoch_entry["message"] = "Tidak ada SPBU yang melewati ambang pemesanan ulang."
            log.append(epoch_entry)
            continue

        if method in ("M0", "M1"):
            plans = _heuristic_plans(I, candidates, idle, method, depot_stock)
        else:
            plans, solver_result = _milp_plans(
                I, candidates, idle, method, current_time, traffic_level, solver_time_limit, depot_stock
            )
            epoch_entry["solver_status"] = solver_result.get("status", "unknown")
            epoch_entry["solve_seconds"] = float(solver_result.get("solve_seconds", 0.0))
            epoch_entry["solver_message"] = solver_result.get("message", "")
            epoch_entry["solver_objective"] = solver_result.get("objective")
            epoch_entry["unmet_by_candidate"] = solver_result.get("unmet", {})
            if not plans and not solver_result.get("has_solution", False):
                # Fallback hanya ketika solver tidak mengembalikan solusi yang terbaca.
                # Hasil fallback tetap diberi label dan bukan klaim hasil MILP.
                plans = _heuristic_plans(I, candidates, idle, "M1", depot_stock)
                epoch_entry["fallback_used"] = True
            else:
                # Solusi valid tanpa rute adalah keputusan solver (misalnya stok depot
                # tidak cukup atau biaya melayani kandidat lebih besar dari penalti).
                epoch_entry["fallback_used"] = False

        for plan in plans:
            vehicle_index = int(plan["vehicle_index"])
            sequence = list(plan["sequence"])
            deliveries = {int(k): float(v) for k, v in plan["deliveries"].items()}

            # Jika kemacetan membuat rute melewati jam operasional, buang stop terakhir
            # sampai rute yang tersisa dapat kembali ke terminal sebelum 22.00.
            trip = None
            while sequence:
                trip = _evaluate_trip(I, vehicle_index, sequence, deliveries, current_time, traffic_level)
                if trip is not None:
                    break
                removed = sequence.pop()
                deliveries.pop(removed, None)
            if trip is None:
                continue

            trip["method"] = method
            trip["planning_source"] = plan.get("source", "unknown")
            trips.append(trip)
            depot_stock = max(0.0, depot_stock - float(trip["delivered_liters"]))
            available_at[vehicle_index] = trip["end_hour"]
            for stop in trip["stops"]:
                idx = int(stop["index"])
                pending_deliveries.append({
                    "station_index": idx,
                    "quantity_liters": float(stop["quantity_liters"]),
                    "delivery_hour": float(stop["service_end_hour"]),
                    "applied": False,
                })
                reserved_until[idx] = float(trip["end_hour"])
            epoch_entry["routes"].append({
                "vehicle_id": trip["vehicle_id"],
                "vehicle_index": vehicle_index,
                "capacity_liters": trip["capacity_liters"],
                "sequence": trip["sequence"],
                "station_ids": [s["station_id"] for s in trip["stops"]],
                "deliveries": [
                    {"station_id": s["station_id"], "liters": s["quantity_liters"]}
                    for s in trip["stops"]
                ],
                "start_hour": trip["start_hour"],
                "end_hour": trip["end_hour"],
                "distance_km": trip["distance_km"],
                "delivered_liters": trip["delivered_liters"],
            })
        if not epoch_entry["routes"] and not epoch_entry.get("message"):
            epoch_entry["message"] = "Kandidat ada, tetapi tidak ada rute yang dijadwalkan pada siklus ini."
        log.append(epoch_entry)

    advance_to(cfg.END_HOUR)

    total_distance = sum(t["distance_km"] for t in trips)
    total_driving_hours = sum(t["driving_hours"] for t in trips)
    total_service_hours = sum(t["service_hours"] for t in trips)
    total_loading_hours = sum(t["loading_hours"] for t in trips)
    total_lateness = sum(t["lateness_hours"] for t in trips)
    delivered_liters = sum(t["delivered_liters"] for t in trips)
    used_capacity = sum(t["capacity_liters"] for t in trips)
    total_stops = sum(len(t["stops"]) for t in trips)
    ontime_stops = sum(1 for t in trips for s in t["stops"] if s["on_time"])
    stockout_liters = float(stockout_by_station.sum())

    distance_cost = cfg.COST_PER_KM * total_distance
    time_cost = cfg.COST_PER_DRIVING_HOUR * (total_driving_hours + total_service_hours + total_loading_hours)
    fixed_cost = cfg.FIXED_COST_PER_TRIP * len(trips)
    lateness_cost = cfg.LATE_PENALTY_PER_HOUR * total_lateness
    stockout_cost = cfg.UNMET_PENALTY_PER_LITER * stockout_liters
    total_cost = distance_cost + time_cost + fixed_cost + lateness_cost + stockout_cost

    service_level = 1.0 if total_demand <= 0 else max(0.0, 1.0 - stockout_liters / total_demand)
    kpi = {
        "total_cost_rp": float(total_cost),
        "distance_km": float(total_distance),
        "driving_hours": float(total_driving_hours),
        "service_hours": float(total_service_hours),
        "loading_hours": float(total_loading_hours),
        "trip_elapsed_hours": float(sum(t["elapsed_hours"] for t in trips)),
        "trips": int(len(trips)),
        "stops_served": int(total_stops),
        "delivered_liters": float(delivered_liters),
        "demand_liters_during_horizon": float(total_demand),
        "stockout_liters": stockout_liters,
        "service_level": float(service_level),
        "on_time_rate": float(ontime_stops / total_stops if total_stops else 1.0),
        "fleet_utilization": float(delivered_liters / used_capacity if used_capacity else 0.0),
        "stations_with_stockout": int((stockout_by_station[1:] > 1e-6).sum()),
        "terminal_stock_remaining_liters": float(depot_stock),
        "cost_breakdown": {
            "distance_cost_rp": float(distance_cost),
            "time_cost_rp": float(time_cost),
            "fixed_trip_cost_rp": float(fixed_cost),
            "late_penalty_rp": float(lateness_cost),
            "stockout_penalty_rp": float(stockout_cost),
        },
    }

    return {
        "method": method,
        "traffic_level": traffic_level,
        "network_source": I.network_source,
        "times": [float(x) for x in hist_times],
        "stock_history": np.asarray(hist_stock, dtype=float),
        "final_stock": stock.copy(),
        "terminal_stock_remaining_liters": float(depot_stock),
        "stockout_by_station": stockout_by_station.copy(),
        "trips": trips,
        "epochs": log,
        "kpi": kpi,
    }
