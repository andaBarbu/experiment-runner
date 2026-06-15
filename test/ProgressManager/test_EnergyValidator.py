import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ProgressManager.Validation.EnergyValidator import (EnergyValidator,EnergyAnomalyReport)


class TestEnergyValidator(unittest.TestCase):
    def test_positive_energy(self):
        run_table = [
            {
                "__run_id": "run_1",
                "cpu_energy": 10.5
            }]

        report = EnergyValidator.validate_run_table(run_table,["cpu_energy"])
        self.assertFalse(report.has_anomalies())

    def test_zero_energy(self):
        run_table = [
            {
                "__run_id": "run_1",
                "cpu_energy": 0
            }]

        report = EnergyValidator.validate_run_table(run_table,["cpu_energy"])
        self.assertTrue(report.has_anomalies())
        self.assertEqual(len(report.anomalies), 1)

    def test_negative_energy(self):
        run_table = [
            {
                "__run_id": "run_1",
                "cpu_energy": -1
            }]

        report = EnergyValidator.validate_run_table(run_table,["cpu_energy"])
        self.assertTrue(report.has_anomalies())
        self.assertEqual(len(report.anomalies), 1)

    def test_mixed_values(self):
        run_table = [
            {
                "__run_id": "run_1",
                "cpu_energy": 10
            },
            {
                "__run_id": "run_2",
                "cpu_energy": 0
            },
            {
                "__run_id": "run_3",
                "cpu_energy": -1
            }]
        
        report = EnergyValidator.validate_run_table(run_table, ["cpu_energy"])
        self.assertTrue(report.has_anomalies())
        self.assertEqual(len(report.anomalies), 2)

    def test_treatment_levels_saved(self):
        run_table = [
            {
                "__run_id": "run_1",
                "__done": "DONE",
                "fib_type": "iter",
                "problem_size": 1000,
                "cpu_energy": -1
            }]
            
        report = EnergyValidator.validate_run_table(run_table,["cpu_energy"])
        anomaly = report.anomalies[0]

        self.assertEqual(anomaly["treatment_levels"]["fib_type"],"iter")
        self.assertEqual(anomaly["treatment_levels"]["problem_size"], 1000)
        self.assertNotIn("__run_id", anomaly["treatment_levels"])
        self.assertNotIn("__done", anomaly["treatment_levels"])


if __name__ == "__main__":
    unittest.main()