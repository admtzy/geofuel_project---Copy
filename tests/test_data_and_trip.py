import tempfile
import unittest
from pathlib import Path

import pandas as pd

from geofuel import config as cfg
from geofuel.data import load_graph, make_instance
from geofuel.simulation import _evaluate_trip


class DataAndTripTests(unittest.TestCase):
    def test_instance_uses_historical_demand_std(self):
        with tempfile.TemporaryDirectory() as tmp:
            station_csv = Path(tmp) / "stations.csv"
            pd.DataFrame([{
                "station_id": "TEST-01",
                "name": "SPBU TEST",
                "lat": cfg.TERMINAL_LAT + 0.001,
                "lon": cfg.TERMINAL_LON + 0.001,
                "capacity_liters": 30000,
                "initial_stock_liters": 7000,
                "daily_demand_liters": 10000,
                "demand_std_liters_per_day": 3500,
                "mean_lead_time_days": 0.4,
                "lead_time_std_days": 0.08,
                "service_level_z": 1.65,
                "window_start": 6,
                "window_end": 22,
                "data_status": "ACTUAL_VERIFIED",
            }]).to_csv(station_csv, index=False)

            graph = load_graph(offline=True)
            instance = make_instance(
                graph, n=1, fleet_count=1, station_csv=station_csv,
            )

            self.assertAlmostEqual(instance.demand_std_liters_per_day[1], 3500)
            self.assertAlmostEqual(instance.mean_lead_time_days[1], 0.4)
            self.assertGreater(instance.safety_stocks[1], 0)

    def test_trip_loading_is_counted_once(self):
        graph = load_graph(offline=True)
        instance = make_instance(graph, n=1, fleet_count=1)
        trip = _evaluate_trip(
            instance, vehicle_index=0, sequence=[1], deliveries={1: 5000},
            start_time=6.0, traffic_level=0,
        )
        self.assertIsNotNone(trip)
        self.assertAlmostEqual(trip["departure_hour"], 6.0 + cfg.LOADING_HOURS)
        self.assertAlmostEqual(trip["loading_hours"], cfg.LOADING_HOURS)
        self.assertGreater(trip["service_hours"], 0)
        self.assertLess(trip["service_hours"], 1.0)


if __name__ == "__main__":
    unittest.main()
