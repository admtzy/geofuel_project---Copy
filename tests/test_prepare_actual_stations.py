import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.prepare_actual_stations import main


class PrepareActualStationsTests(unittest.TestCase):
    def _run_script(self, master: Path, sales: Path, output: Path, min_days: int = 3):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = [
                "prepare_actual_stations.py",
                "--master", str(master),
                "--sales", str(sales),
                "--output", str(output),
                "--min-days", str(min_days),
            ]
            main()
        finally:
            sys.argv = old_argv

    def test_builds_daily_average_and_std(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = root / "master.csv"
            sales = root / "sales.csv"
            output = root / "output.csv"
            pd.DataFrame([{
                "station_id": "S1", "name": "SPBU 1", "address": "Alamat",
                "lat": -6.9, "lon": 107.7, "capacity_liters": 30000,
                "initial_stock_liters": 10000, "data_status": "UNVERIFIED",
            }]).to_csv(master, index=False)
            pd.DataFrame([
                {"station_id": "S1", "date": "2026-10-01", "sales_liters": 1000},
                {"station_id": "S1", "date": "2026-10-02", "sales_liters": 2000},
                {"station_id": "S1", "date": "2026-10-03", "sales_liters": 3000},
            ]).to_csv(sales, index=False)
            self._run_script(master, sales, output, min_days=3)
            result = pd.read_csv(output)
            self.assertAlmostEqual(result.loc[0, "daily_demand_liters"], 2000)
            self.assertAlmostEqual(result.loc[0, "demand_std_liters_per_day"], 1000)
            self.assertEqual(result.loc[0, "data_status"], "UNVERIFIED")

    def test_rejects_missing_calendar_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = root / "master.csv"
            sales = root / "sales.csv"
            output = root / "output.csv"
            pd.DataFrame([{
                "station_id": "S1", "name": "SPBU 1", "address": "Alamat",
                "lat": -6.9, "lon": 107.7, "capacity_liters": 30000,
                "initial_stock_liters": 10000, "data_status": "UNVERIFIED",
            }]).to_csv(master, index=False)
            pd.DataFrame([
                {"station_id": "S1", "date": "2026-10-01", "sales_liters": 1000},
                {"station_id": "S1", "date": "2026-10-03", "sales_liters": 3000},
            ]).to_csv(sales, index=False)
            with self.assertRaisesRegex(ValueError, "tanggal penjualan yang hilang"):
                self._run_script(master, sales, output, min_days=2)


if __name__ == "__main__":
    unittest.main()
