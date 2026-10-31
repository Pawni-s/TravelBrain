import unittest

from src.budget_analyzer import analyze_budget


class BudgetAnalyzerTests(unittest.TestCase):
    def test_within_budget_and_profile_allocation(self):
        result = analyze_budget(20000, {
            "travel": 6000, "accommodation": 8000, "food": 3000,
            "local_transport": 1000, "activities": 1000, "miscellaneous": 0,
        }, profile="luxury")
        self.assertEqual(result["total"], 19000)
        self.assertEqual(result["remaining"], 1000)
        self.assertFalse(result["over_budget"])
        self.assertEqual(result["profile"], "luxury")
        targets = {item["key"]: item["target"] for item in result["allocation"]}
        self.assertGreater(targets["accommodation"], targets["activities"])

    def test_different_profiles_have_different_targets(self):
        costs = {"travel": 100, "accommodation": 100, "food": 100, "activities": 100}
        luxury = analyze_budget(10000, costs, "luxury")
        adventure = analyze_budget(10000, costs, "adventure")
        luxury_targets = {item["key"]: item["target"] for item in luxury["allocation"]}
        adventure_targets = {item["key"]: item["target"] for item in adventure["allocation"]}
        self.assertGreater(luxury_targets["accommodation"], adventure_targets["accommodation"])
        self.assertGreater(adventure_targets["activities"], luxury_targets["activities"])

    def test_over_budget_soft_limit_explains_tradeoff(self):
        result = analyze_budget(10000, {"travel": 6000, "accommodation": 6000}, "adventure")
        self.assertEqual(result["total"], 12000)
        self.assertEqual(result["remaining"], -2000)
        self.assertTrue(result["over_budget"])
        self.assertTrue(any("exceed the budget" in item for item in result["recommendations"]))

    def test_rejects_zero_budget(self):
        with self.assertRaises(ValueError):
            analyze_budget(0, {})

    def test_rejects_negative_cost(self):
        with self.assertRaises(ValueError):
            analyze_budget(1000, {"food": -5})

    def test_rejects_non_numeric_cost(self):
        with self.assertRaises(ValueError):
            analyze_budget(1000, {"food": "many"})

    def test_rejects_unknown_profile(self):
        with self.assertRaises(ValueError):
            analyze_budget(1000, {}, "party")


    def test_currency_is_kept_consistent(self):
        result = analyze_budget(1000, {"food": 200}, "food", currency="USD")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["currency_symbol"], "$")
        self.assertIn("USD", result["disclaimer"])

    def test_unknown_currency_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_budget(1000, {}, currency="XYZ")

if __name__ == "__main__":
    unittest.main()
