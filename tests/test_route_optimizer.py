import unittest

from src.route_optimizer import optimize_day_route, optimize_itinerary


HOTEL = {"lat": 28.6139, "lon": 77.2090}
ATTRACTIONS = [
    {"id": "a", "name": "Museum", "area": "Old Town", "lat": 28.6150, "lon": 77.2100,
     "visit_minutes": 60, "open_time": "09:00", "close_time": "17:00"},
    {"id": "b", "name": "Market", "area": "Old Town", "lat": 28.6170, "lon": 77.2120,
     "visit_minutes": 45, "open_time": "10:00", "close_time": "19:00"},
]


class RouteOptimizerTests(unittest.TestCase):
    def test_ast_returns_all_selected_stops_and_hotel_return(self):
        result = optimize_day_route(HOTEL, ATTRACTIONS, "09:00", "19:00")
        self.assertTrue(result["feasible"])
        self.assertEqual({stop["id"] for stop in result["route"]}, {"a", "b"})
        self.assertIn("A*", result["algorithm"])
        self.assertLessEqual(result["hotel_return_time"], "19:00")

    def test_strict_area_grouping_uses_separate_days(self):
        attractions = ATTRACTIONS + [{**ATTRACTIONS[0], "id": "c", "name": "Park", "area": "Riverside"}]
        result = optimize_itinerary(HOTEL, attractions)
        self.assertEqual(len(result["days"]), 2)
        self.assertEqual(result["scheduled_count"], 3)

    def test_infeasible_day_explains_conflict(self):
        attractions = [{**ATTRACTIONS[0], "visit_minutes": 600}]
        result = optimize_day_route(HOTEL, attractions, "09:00", "10:00")
        self.assertFalse(result["feasible"])
        self.assertTrue(result["reasons"])
        self.assertTrue(result["suggestions"])

    def test_rejects_invalid_opening_time(self):
        attractions = [{**ATTRACTIONS[0], "open_time": "later"}]
        with self.assertRaises(ValueError):
            optimize_day_route(HOTEL, attractions)

    def test_empty_attraction_list(self):
        result = optimize_day_route(HOTEL, [])
        self.assertTrue(result["feasible"])
        self.assertEqual(result["route"], [])


    def test_route_includes_distance_and_buffer_details(self):
        hotel = {"lat": 28.6139, "lon": 77.2090}
        attractions = [
            {"id": "a", "name": "A", "area": "Center", "lat": 28.615, "lon": 77.210, "visit_minutes": 30, "open_time": "09:00", "close_time": "18:00"},
            {"id": "b", "name": "B", "area": "Center", "lat": 28.617, "lon": 77.212, "visit_minutes": 30, "open_time": "09:00", "close_time": "18:00"},
            {"id": "c", "name": "C", "area": "Center", "lat": 28.619, "lon": 77.214, "visit_minutes": 30, "open_time": "09:00", "close_time": "18:00"},
        ]
        result = optimize_itinerary(hotel, attractions, "09:00", "19:00", buffer_minutes=15, meal_break_minutes=45)
        day = result["days"][0]
        self.assertTrue(day["feasible"])
        self.assertGreater(day["total_distance_km"], 0)
        self.assertEqual(day["total_buffer_minutes"], 2 * 15 + 45)
        self.assertIn("distance_from_previous_km", day["route"][0])

if __name__ == "__main__":
    unittest.main()
