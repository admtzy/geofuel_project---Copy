"""Analisis kelayakan investasi: NPV, BCR, IRR, payback period."""
from __future__ import annotations


def _npv(rate: float, cash_flows: list[float]) -> float:
    return sum(value / ((1.0 + rate) ** year) for year, value in enumerate(cash_flows))


def irr(cash_flows: list[float], low: float = -0.90, high: float = 8.0) -> float | None:
    """IRR dengan bisection; None jika tidak ditemukan perubahan tanda NPV."""
    def f(rate: float) -> float:
        return _npv(rate, cash_flows)

    f_low, f_high = f(low), f(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        return None
    for _ in range(120):
        mid = (low + high) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_low * f_mid <= 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2.0


def feasibility(
    saving_per_day: float,
    capex: float = 450_000_000.0,
    opex_per_year: float = 90_000_000.0,
    years: int = 5,
    discount_rate: float = 0.10,
    operating_days: int = 330,
    saving_multiplier: float = 1.0,
    opex_multiplier: float = 1.0,
    ramp: tuple[float, ...] = (0.5, 0.8),
) -> dict:
    """Hitung proyeksi investasi dari penghematan simulasi.

    Seluruh CAPEX/OPEX default adalah asumsi ilustratif, bukan penawaran vendor.
    """
    if years < 1:
        raise ValueError("years minimal 1")
    if discount_rate <= -1:
        raise ValueError("discount_rate harus lebih besar dari -1")

    cash_flows = [-float(capex)]
    present_value_benefit = 0.0
    present_value_cost = float(capex)
    cumulative = -float(capex)
    payback = None

    for year in range(1, years + 1):
        adoption = ramp[year - 1] if year <= len(ramp) else 1.0
        benefit = max(0.0, saving_per_day) * operating_days * saving_multiplier * adoption
        annual_opex = opex_per_year * opex_multiplier
        net = benefit - annual_opex
        cash_flows.append(net)
        present_value_benefit += benefit / ((1 + discount_rate) ** year)
        present_value_cost += annual_opex / ((1 + discount_rate) ** year)
        if payback is None and net > 0 and cumulative + net >= 0:
            payback = year - 1 + (-cumulative) / net
        cumulative += net

    npv = _npv(discount_rate, cash_flows)
    bcr = present_value_benefit / present_value_cost if present_value_cost > 0 else None
    return {
        "NPV_Rp": npv,
        "BCR": bcr,
        "IRR": irr(cash_flows),
        "Payback_years": payback,
        "cash_flows": cash_flows,
    }


SCENARIOS = {
    "optimistis": {"saving_multiplier": 1.25, "opex_multiplier": 0.90},
    "moderat": {"saving_multiplier": 1.00, "opex_multiplier": 1.00},
    "pesimistis": {"saving_multiplier": 0.50, "opex_multiplier": 1.30},
}
