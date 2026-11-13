import unittest

from geofuel.inventory import (
    safety_stock,
    days_of_inventory,
    time_to_safety_hours,
    required_delivery,
    assess_station,
)


class InventoryTests(unittest.TestCase):
    def test_doi(self):
        self.assertAlmostEqual(days_of_inventory(2000, 8000), 0.25)

    def test_time_to_safety(self):
        self.assertAlmostEqual(time_to_safety_hours(2000, 1000, 8000), 3.0)
        self.assertLess(time_to_safety_hours(500, 1000, 8000), 0)

    def test_safety_stock_positive(self):
        self.assertGreater(safety_stock(10000), 0)

    def test_required_delivery_does_not_exceed_capacity(self):
        self.assertAlmostEqual(required_delivery(10000, 30000, 0.85), 15500)
        self.assertLessEqual(required_delivery(0, 30000, 0.85), 30000)

    def test_critical_station(self):
        result = assess_station(
            stock_liters=1000, daily_demand_liters=10000,
            tank_capacity_liters=30000, safety_stock_liters=2000,
            travel_time_hours=1.0,
        )
        self.assertEqual(result["priority"], "KRITIS")
        self.assertTrue(result["needs_replenishment"])
        self.assertGreater(result["required_liters"], 0)


if __name__ == "__main__":
    unittest.main()
