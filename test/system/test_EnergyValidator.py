import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ProgressManager.Validation.EnergyValidator import EnergyValidator, EnergyAnomalyReport


class TestEnergyAnomalyReport(unittest.TestCase):
    def test_report_creation(self):
        report = EnergyAnomalyReport()
        self.assertFalse(report.has_anomalies())
        self.assertFalse(report.has_errors())

    def test_add_error_anomaly(self):
        report = EnergyAnomalyReport()
        report.add_anomaly('run_1', {'factor_a': 'value1'}, 'energy', -5.0, 'error')
        
        self.assertTrue(report.has_anomalies())
        self.assertTrue(report.has_errors())
        self.assertEqual(len(report.anomalies), 1)
        self.assertEqual(report.anomalies[0]['value'], -5.0)

    def test_add_warning_anomaly(self):
        report = EnergyAnomalyReport()
        report.add_anomaly('run_1', {'factor_a': 'value1'}, 'energy', 0, 'warning')
        
        self.assertTrue(report.has_anomalies())
        self.assertFalse(report.has_errors())

    def test_mixed_anomalies(self):
        report = EnergyAnomalyReport()
        report.add_anomaly('run_1', {'factor_a': 'value1'}, 'energy', -5.0, 'error')
        report.add_anomaly('run_2', {'factor_a': 'value2'}, 'energy', 0, 'warning')
        
        self.assertTrue(report.has_anomalies())
        self.assertTrue(report.has_errors())
        self.assertEqual(len(report.anomalies), 2)


class TestEnergyValidator(unittest.TestCase):
    def test_validate_empty_run_table(self):
        report = EnergyValidator.validate_run_table([], ['energy'])
        self.assertFalse(report.has_anomalies())

    def test_validate_no_energy_columns(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': 10.5}
        ]
        report = EnergyValidator.validate_run_table(run_table, [])
        self.assertFalse(report.has_anomalies())

    def test_validate_positive_energy(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': 10.5},
            {'__run_id': 'run_2', 'factor_a': 'value2', 'energy': 25.0}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        self.assertFalse(report.has_anomalies())

    def test_validate_zero_energy(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': 0}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        self.assertTrue(report.has_anomalies())
        self.assertFalse(report.has_errors())  # Zero is a warning, not an error
        self.assertEqual(report.anomalies[0]['severity'], 'warning')

    def test_validate_negative_energy(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': -5.0}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        self.assertTrue(report.has_anomalies())
        self.assertTrue(report.has_errors())
        self.assertEqual(report.anomalies[0]['severity'], 'error')

    def test_validate_none_energy(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': None}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        self.assertTrue(report.has_anomalies())
        self.assertEqual(report.anomalies[0]['severity'], 'warning')

    def test_validate_multiple_energy_columns(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': 10.0, 'power': 5.0},
            {'__run_id': 'run_2', 'factor_a': 'value2', 'energy': -5.0, 'power': 0}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy', 'power'])
        
        self.assertTrue(report.has_anomalies())
        self.assertTrue(report.has_errors())
        # Should have 2 anomalies: one negative energy, one zero power
        self.assertEqual(len(report.anomalies), 2)

    def test_validate_mixed_valid_invalid(self):
        run_table = [
            {'__run_id': 'run_1', 'factor_a': 'value1', 'energy': 10.5},
            {'__run_id': 'run_2', 'factor_a': 'value2', 'energy': -2.0},
            {'__run_id': 'run_3', 'factor_a': 'value3', 'energy': 25.0}
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        self.assertTrue(report.has_anomalies())
        self.assertTrue(report.has_errors())
        self.assertEqual(len(report.anomalies), 1)  # Only run_2 has anomaly
        self.assertEqual(report.anomalies[0]['run_id'], 'run_2')

    def test_generate_report_text_no_anomalies(self):
        report = EnergyAnomalyReport()
        text = EnergyValidator.generate_report_text(report, ['energy'])
        
        self.assertIn("No anomalies detected", text)
        self.assertIn("✓", text)

    def test_generate_report_text_with_errors(self):
        report = EnergyAnomalyReport()
        report.add_anomaly('run_1', {'factor_a': 'value1'}, 'energy', -5.0, 'error')
        text = EnergyValidator.generate_report_text(report, ['energy'])
        
        self.assertIn("CRITICAL ERRORS", text)
        self.assertIn("run_1", text)
        self.assertIn("-5.0", text)

    def test_extract_treatment_levels(self):
        run_table = [
            {
                '__run_id': 'run_1',
                '__done': 'DONE',
                'factor_a': 'value1',
                'factor_b': 'value2',
                'energy': 10.0
            }
        ]
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        # Energy is positive, so should be no anomalies and no treatment levels extracted
        # Now test with negative energy to get anomaly with treatment levels
        run_table[0]['energy'] = -5.0
        report = EnergyValidator.validate_run_table(run_table, ['energy'])
        
        self.assertTrue(report.has_anomalies())
        anomaly = report.anomalies[0]
        self.assertEqual(anomaly['treatment_levels']['factor_a'], 'value1')
        self.assertEqual(anomaly['treatment_levels']['factor_b'], 'value2')
        # __run_id and __done should not be in treatment_levels
        self.assertNotIn('__run_id', anomaly['treatment_levels'])
        self.assertNotIn('__done', anomaly['treatment_levels'])


if __name__ == '__main__':
    unittest.main()
