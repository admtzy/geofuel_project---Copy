"""Inventory Intelligence: DOI, safety stock, time-to-risk, dan kebutuhan BBM.

Rumus diselaraskan dengan persamaan 8-15 pada dokumen GEO-FUEL.
Seluruh satuan dibuat eksplisit: stok liter, konsumsi liter/hari, waktu jam.
"""
from __future__ import annotations

import math
from . import config as cfg


def safety_stock(
    daily_demand_liters: float,
    mean_lead_time_days: float = cfg.MEAN_LEAD_TIME_DAYS,
    demand_std_fraction: float = cfg.DEMAND_STD_FRACTION,
    lead_time_std_days: float = cfg.LEAD_TIME_STD_DAYS,
    z: float = cfg.SERVICE_LEVEL_Z,
    demand_std_liters_per_day: float | None = None,
) -> float:
    """Safety stock dengan variasi permintaan dan lead time.

    SS = z * sqrt(L*sigma_d^2 + d^2*sigma_L^2)
    sigma_d = (
        max(0.0, float(demand_std_liters_per_day))
        if demand_std_liters_per_day is not None
        and math.isfinite(float(demand_std_liters_per_day))
        else demand_std_fraction * d
    )
    """
    d = max(0.0, float(daily_demand_liters))
    # Gunakan simpangan baku historis jika tersedia. Jika tidak, gunakan
    # persentase asumsi dari konsumsi harian.
    sigma_d = (
        max(0.0, float(demand_std_liters_per_day))
        if demand_std_liters_per_day is not None
        and math.isfinite(float(demand_std_liters_per_day))
        else demand_std_fraction * d
    )
    variance = mean_lead_time_days * sigma_d**2 + (d * lead_time_std_days) ** 2
    return float(z * math.sqrt(max(0.0, variance)))


def days_of_inventory(stock_liters: float, daily_demand_liters: float) -> float:
    d = float(daily_demand_liters)
    if d <= 0:
        return math.inf
    return max(0.0, float(stock_liters)) / d


def time_to_safety_hours(stock_liters: float, safety_stock_liters: float,
                         daily_demand_liters: float) -> float:
    """Jam sampai stok menyentuh safety stock; negatif berarti sudah di bawah SS."""
    d = float(daily_demand_liters)
    if d <= 0:
        return math.inf
    return (float(stock_liters) - float(safety_stock_liters)) / d * 24.0


def project_stock_at_arrival(stock_liters: float, daily_demand_liters: float,
                             lead_time_hours: float) -> tuple[float, float]:
    """Kembalikan (stok proyeksi non-negatif, potensi stockout sebelum tiba)."""
    raw = float(stock_liters) - float(daily_demand_liters) * max(0.0, lead_time_hours) / 24.0
    return max(0.0, raw), max(0.0, -raw)


def required_delivery(projected_stock_liters: float, tank_capacity_liters: float,
                      target_fill_ratio: float = cfg.TARGET_FILL_RATIO) -> float:
    """Volume untuk mencapai target stok tanpa melebihi kapasitas tangki.

    Mengikuti prinsip Persamaan (13): min(ruang tangki, kebutuhan menuju target).
    """
    capacity = max(0.0, float(tank_capacity_liters))
    stock = min(capacity, max(0.0, float(projected_stock_liters)))
    target_ratio = min(1.0, max(0.0, float(target_fill_ratio)))
    target_stock = capacity * target_ratio
    free_space = max(0.0, capacity - stock)
    target_gap = max(0.0, target_stock - stock)
    return min(free_space, target_gap)


def urgency_score(time_to_safety_h: float, effective_lead_h: float,
                  buffer_h: float = cfg.PRIORITY_BUFFER_HOURS,
                  lookahead_h: float = cfg.PRIORITY_LOOKAHEAD_HOURS) -> float:
    """Skor 0..1 berdasarkan sisa waktu dibanding lead time.

    Skor 1 berarti risiko sudah terjadi/sebelum pengiriman selesai.
    Skor 0 berarti masih jauh di luar jendela prioritas.
    """
    slack = float(time_to_safety_h) - float(effective_lead_h)
    if slack <= 0:
        return 1.0
    horizon = max(0.01, float(buffer_h) + float(lookahead_h))
    return max(0.0, min(1.0, 1.0 - slack / horizon))


def priority_label(stock_liters: float, safety_stock_liters: float,
                   time_to_safety_h: float, effective_lead_h: float,
                   buffer_h: float = cfg.PRIORITY_BUFFER_HOURS) -> str:
    if stock_liters <= safety_stock_liters:
        return "KRITIS"
    if time_to_safety_h <= effective_lead_h:
        return "TINGGI"
    if time_to_safety_h <= effective_lead_h + buffer_h:
        return "SEDANG"
    return "AMAN"


def assess_station(stock_liters: float, daily_demand_liters: float,
                   tank_capacity_liters: float, safety_stock_liters: float,
                   travel_time_hours: float, target_fill_ratio: float = cfg.TARGET_FILL_RATIO,
                   loading_hours: float = cfg.LOADING_HOURS,
                   unloading_base_hours: float = cfg.UNLOADING_BASE_HOURS,
                   unloading_rate_lph: float = cfg.UNLOADING_RATE_LITERS_PER_HOUR,
                   priority_buffer_hours: float = cfg.PRIORITY_BUFFER_HOURS) -> dict:
    """Hitung apakah SPBU perlu dikirim dan berapa liter yang dibutuhkan.

    Lead time sampai kendaraan mulai tiba = loading + perjalanan.
    Volume dihitung dari proyeksi stok saat tiba. Durasi bongkar ditambahkan
    untuk mengukur kapan proses replenishment selesai.
    """
    stock = max(0.0, float(stock_liters))
    demand = max(0.0, float(daily_demand_liters))
    capacity = max(0.0, float(tank_capacity_liters))
    ss = max(0.0, float(safety_stock_liters))
    travel = max(0.0, float(travel_time_hours))

    lead_until_arrival = max(0.0, loading_hours) + travel
    stock_at_arrival, potential_stockout = project_stock_at_arrival(
        stock, demand, lead_until_arrival
    )
    quantity = required_delivery(stock_at_arrival, capacity, target_fill_ratio)
    unload_hours = max(0.0, unloading_base_hours)
    if unloading_rate_lph > 0:
        unload_hours += quantity / unloading_rate_lph
    effective_lead = lead_until_arrival + unload_hours

    doi = days_of_inventory(stock, demand)
    risk_hours = time_to_safety_hours(stock, ss, demand)
    projected_at_completion, stockout_before_completion = project_stock_at_arrival(
        stock, demand, effective_lead
    )
    label = priority_label(stock, ss, risk_hours, effective_lead, priority_buffer_hours)
    reorder_horizon = effective_lead + max(0.0, priority_buffer_hours)
    reorder_point = min(
        capacity,
        ss + demand * reorder_horizon / 24.0,
    )
    triggered = (stock <= ss) or (risk_hours <= reorder_horizon)
    urgency = urgency_score(risk_hours, effective_lead, priority_buffer_hours)

    if stock <= ss:
        decision_reason = "Stok saat ini sudah menyentuh atau melewati safety stock."
    elif risk_hours <= effective_lead:
        decision_reason = "Stok diperkirakan menyentuh safety stock sebelum pengiriman selesai."
    elif risk_hours <= reorder_horizon:
        decision_reason = "Stok diperkirakan menyentuh safety stock dalam lead time dan buffer prioritas."
    else:
        decision_reason = "Stok masih cukup untuk menunggu pada horizon perencanaan ini."

    return {
        "stock_liters": stock,
        "daily_demand_liters": demand,
        "tank_capacity_liters": capacity,
        "safety_stock_liters": ss,
        "reorder_point_liters": reorder_point,
        "doi_days": doi,
        "time_to_safety_hours": risk_hours,
        "lead_until_arrival_hours": lead_until_arrival,
        "effective_lead_hours": effective_lead,
        "projected_stock_at_arrival_liters": stock_at_arrival,
        "projected_stock_at_completion_liters": projected_at_completion,
        "potential_stockout_before_arrival_liters": potential_stockout,
        "potential_stockout_before_completion_liters": stockout_before_completion,
        "required_liters": quantity,
        "priority": label,
        "urgency": urgency,
        "decision_reason": decision_reason,
        "needs_replenishment": bool(triggered and quantity >= cfg.MIN_DELIVERY_LITERS),
    }


def unmet_penalty_per_liter(urgency: float) -> float:
    return cfg.UNMET_PENALTY_PER_LITER * (1.0 + cfg.URGENCY_PENALTY_MULTIPLIER * max(0.0, min(1.0, urgency)))
