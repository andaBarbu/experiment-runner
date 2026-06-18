from typing import Dict, List, Tuple, Any
from pathlib import Path
from ProgressManager.Output.OutputProcedure import OutputProcedure as output


class EnergyAnomalyReport:
    """Represents energy measurement anomalies found during validation."""
    
    def __init__(self):
        self.anomalies: List[Dict[str, Any]] = []
    
    def add_anomaly(self, run_id: str, treatment_levels: Dict[str, Any], column_name: str, value: Any):
        """Add an anomaly to the report.
            The anomaly followes the structure:
                run_id: The run identifier
                treatment_levels: Dictionary of factor names to treatment levels for this run
                column_name: The energy column name where anomaly was detected
                value: The anomalous value
        """
        self.anomalies.append({
            'run_id': run_id,
            'treatment_levels': treatment_levels,
            'column_name': column_name,
            'value': value,
        })
    
    def has_anomalies(self) -> bool:
        """Check if any anomalies were found."""
        return len(self.anomalies) > 0


class EnergyValidator:
    """Validates energy measurements for anomalies (zero or negative values)."""
    
    @staticmethod
    def validate_run_table(run_table: List[Dict[str, Any]], energy_columns: List[str]) -> EnergyAnomalyReport:
        """Validate energy measurements in a run table."""
        report = EnergyAnomalyReport()
        
        if not energy_columns:
            return report
        
        for run in run_table:
            run_id = run.get('__run_id', 'unknown')
            # Extract treatment levels
            treatment_levels = {
                k: v for k, v in run.items() 
                if not k.startswith('__')
            }
            
            for column_name in energy_columns:
                if column_name not in run:
                    continue
                value = run[column_name]
                
                # Check for None or missing values
                if value is None:
                    report.add_anomaly(run_id, treatment_levels, column_name, value)
                    continue
                try: 
                    numeric_value = float(value) 
                    if numeric_value < 0: 
                        report.add_anomaly(run_id, treatment_levels, column_name, numeric_value) 
                    elif numeric_value == 0: 
                        report.add_anomaly(run_id, treatment_levels, column_name, numeric_value) 
                except (ValueError, TypeError): 
                    report.add_anomaly(run_id, treatment_levels, column_name, value)
        return report
    
    @staticmethod
    def generate_report_text(report: EnergyAnomalyReport, energy_columns: List[str]) -> str:
        """ Generate the report text."""
        lines = []
        lines.append("=" * 80)
        lines.append("ENERGY MEASUREMENT VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        if report.has_anomalies():
            lines.append(f"Found {len(report.anomalies)} anomalous energy measurements")
            lines.append("-" * 80)

            for anomaly in report.anomalies:
                lines.append(f"Run ID: {anomaly['run_id']}")
                lines.append(f"Column: {anomaly['column_name']}")
                lines.append(f"Value: {anomaly['value']}")
                lines.append(f"Treatment levels: {anomaly['treatment_levels']}")
                lines.append("")

        lines.append("=" * 80)
        lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def save_report_to_file(report: EnergyAnomalyReport, energy_columns: List[str],log_file: Path) -> None:
        """Save validation report to a file."""

        report_text = EnergyValidator.generate_report_text(report, energy_columns)
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'w') as f:
                f.write(report_text)
            output.console_log_OK(f"Energy validation report saved to: {log_file}")
        except Exception as e:
            output.console_log_FAIL(f"Failed to write energy validation report: {e}")
