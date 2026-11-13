import unittest

from geofuel.data import load_graph, make_instance
from geofuel.simulation import simulate


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph = load_graph(offline=True)
        cls.instance = make_instance(graph, n=27, fleet_count=4)

    def test_m1_respects_depot_and_vehicle_capacity(self):
        result = simulate(self.instance, method="M1", traffic_level=1, epoch_hours=2)
        self.assertLessEqual(
            result["kpi"]["delivered_liters"],
            self.instance.terminal_initial_stock_liters + 1e-6,
        )
        for trip in result["trips"]:
            self.assertLessEqual(
                trip["delivered_liters"], trip["capacity_liters"] + 1e-6
            )

    def test_final_station_stock_is_within_capacity(self):
        result = simulate(self.instance, method="M1", traffic_level=0, epoch_hours=2)
        final_stock = result["final_stock"]
        self.assertTrue((final_stock >= -1e-8).all())
        self.assertTrue((final_stock <= self.instance.capacity + 1e-8).all())

    def test_demo_fleet_is_explicitly_simulated(self):
        self.assertTrue(all(status == "SIMULATED" for status in self.instance.fleet_data_status))


if __name__ == "__main__":
    unittest.main()
