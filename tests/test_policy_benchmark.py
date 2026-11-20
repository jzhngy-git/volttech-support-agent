import unittest

from tools.run_policy_benchmark import evaluate, load_cases


class PolicyBenchmarkTests(unittest.TestCase):
    def test_policy_retrieval_meets_benchmark_thresholds(self):
        report = evaluate(load_cases())

        self.assertEqual(report["case_count"], 45)
        self.assertEqual(report["supported_case_count"], 40)
        self.assertEqual(report["unsupported_case_count"], 5)
        self.assertGreaterEqual(report["recall_at_1"], 0.85, report["failures"])
        self.assertEqual(report["citation_accuracy"], 1.0)
        self.assertEqual(report["unsupported_abstention_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
