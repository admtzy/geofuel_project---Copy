"""Gabungkan master SPBU dengan riwayat penjualan harian.

Contoh:
python scripts/prepare_actual_stations.py \
  --master data/station_master_actual.csv \
  --sales data/daily_sales_actual.csv \
  --output data/stations_actual.csv \
  --min-days 14

CSV penjualan harus berisi satu atau lebih transaksi per tanggal. Jika pada
hari tertentu tidak ada penjualan, masukkan satu baris dengan sales_liters=0
agar hari tersebut tidak dianggap sebagai data yang hilang. Untuk setiap SPBU,
seluruh tanggal kalender di antara tanggal awal dan akhir harus tercatat.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Menyiapkan CSV input aktual GEO-FUEL")
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--sales", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/stations_actual.csv"))
    parser.add_argument("--min-days", type=int, default=14)
    args = parser.parse_args()

    if args.min_days < 2:
        parser.error("--min-days minimal 2 agar simpangan baku dapat dihitung")
    if not args.master.exists():
        raise FileNotFoundError(f"Master SPBU tidak ditemukan: {args.master}")
    if not args.sales.exists():
        raise FileNotFoundError(f"Riwayat penjualan tidak ditemukan: {args.sales}")

    master = pd.read_csv(args.master)
    sales = pd.read_csv(args.sales)
    required_master = {
        "station_id", "name", "lat", "lon", "capacity_liters", "initial_stock_liters"
    }
    required_sales = {"station_id", "date", "sales_liters"}
    missing_master = sorted(required_master - set(master.columns))
    missing_sales = sorted(required_sales - set(sales.columns))
    if missing_master:
        raise ValueError(f"Kolom master kurang: {missing_master}")
    if missing_sales:
        raise ValueError(f"Kolom sales kurang: {missing_sales}")
    if master["station_id"].astype(str).duplicated().any():
        raise ValueError("station_id pada master harus unik")

    sales["station_id"] = sales["station_id"].astype(str)
    master["station_id"] = master["station_id"].astype(str)
    sales["date"] = pd.to_datetime(sales["date"], errors="raise").dt.normalize()
    sales["sales_liters"] = pd.to_numeric(sales["sales_liters"], errors="raise")
    if (sales["sales_liters"] < 0).any():
        raise ValueError("sales_liters tidak boleh negatif")

    # Tolak transaksi dari ID yang tidak ada di master agar salah ketik tidak hilang diam-diam.
    unknown_ids = sorted(set(sales["station_id"]) - set(master["station_id"]))
    if unknown_ids:
        raise ValueError(f"Riwayat penjualan berisi station_id yang tidak ada di master: {unknown_ids}")

    # Jika ada beberapa transaksi per SPBU/tanggal, jumlahkan menjadi penjualan harian.
    daily = sales.groupby(["station_id", "date"], as_index=False)["sales_liters"].sum()

    # Pastikan seluruh hari kalender pada rentang observasi tercatat. Hari tanpa
    # penjualan harus dimasukkan sebagai 0; tanggal yang hilang bukan otomatis 0.
    gaps = []
    for station_id, group in daily.groupby("station_id"):
        observed = set(pd.to_datetime(group["date"]).dt.normalize())
        date_min = pd.to_datetime(group["date"]).min()
        date_max = pd.to_datetime(group["date"]).max()
        expected = set(pd.date_range(date_min, date_max, freq="D"))
        missing_dates = sorted(expected - observed)
        if missing_dates:
            preview = ", ".join(str(value.date()) for value in missing_dates[:5])
            suffix = " ..." if len(missing_dates) > 5 else ""
            gaps.append(f"{station_id}: {preview}{suffix}")
    if gaps:
        raise ValueError(
            "Ada tanggal penjualan yang hilang. Isi hari tanpa penjualan dengan 0 "
            "atau periksa sumber data: " + "; ".join(gaps)
        )

    summary = daily.groupby("station_id")["sales_liters"].agg(
        daily_demand_liters="mean",
        demand_std_liters_per_day="std",
        sales_observation_days="count",
    ).reset_index()

    too_few = summary[summary["sales_observation_days"] < args.min_days]
    if not too_few.empty:
        detail = ", ".join(
            f"{row.station_id} ({int(row.sales_observation_days)} hari)"
            for row in too_few.itertuples()
        )
        raise ValueError(
            f"Riwayat belum mencapai {args.min_days} hari untuk: {detail}. "
            "Tambahkan riwayat atau turunkan --min-days dengan alasan yang jelas."
        )

    output = master.merge(summary, on="station_id", how="left", validate="one_to_one")
    missing = output[output["daily_demand_liters"].isna()]["station_id"].tolist()
    if missing:
        raise ValueError(f"Master memiliki SPBU tanpa riwayat penjualan: {missing}")
    if "data_status" not in output:
        output["data_status"] = "UNVERIFIED"
    output["data_status"] = output["data_status"].fillna("UNVERIFIED")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"Berhasil membuat: {args.output}")
    print(f"Jumlah SPBU: {len(output)}")
    print(f"Jumlah observasi per SPBU minimal: {int(output['sales_observation_days'].min())} hari")
    print("Catatan: script tidak mengubah data_status menjadi ACTUAL_VERIFIED secara otomatis.")
    print(output[["station_id", "daily_demand_liters", "demand_std_liters_per_day", "sales_observation_days"]].to_string(index=False))


if __name__ == "__main__":
    main()
