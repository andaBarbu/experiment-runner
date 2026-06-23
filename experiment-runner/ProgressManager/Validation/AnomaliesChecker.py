from typing import Dict, List, Any, Set
import pandas as pd
from pathlib import Path
from ProgressManager.Output.OutputProcedure import OutputProcedure as output

META_COLUMNS = {
    "Delta",
    "Time",
    "timestamp",
    "run_id"
}

class AnomalyReport:
    def __init__(self):
        self.anomalies: List[Dict[str, Any]] = []

    def add_anomaly(
        self,
        run_id: str,
        treatment_levels: Dict[str, Any],
        file_path: str,
        row_number: int,
        column_name: str,
        value: Any,
        anomaly_type: str
    ):
        self.anomalies.append({
            "run_id": run_id,
            "treatment_levels": treatment_levels,
            "file_path": file_path,
            "row_number": row_number,
            "column_name": column_name,
            "value": value,
            "anomaly_type": anomaly_type
        })

    def has_anomalies(self) -> bool:
        return len(self.anomalies) > 0


class ResultsValidator:
    """
        Validates experiment output logs and detects:
        - NaN values
        - negative values
        - zero values
        - missing files
    """
    @staticmethod
    def _detect_numeric_columns(df: pd.DataFrame) -> List[str]:
        """
        Automatically detect columns that contain numeric signals.
        """
        numeric_cols = []

        for col in df.columns:
            if col in META_COLUMNS:
                continue

            series = pd.to_numeric(df[col], errors="coerce")

            # keep column if it has at least some numeric values
            if series.notna().any():
                numeric_cols.append(col)
        return numeric_cols

    @staticmethod
    def generate_report_text(report: AnomalyReport) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("GENERIC MEASUREMENT VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append("")

        if not report.has_anomalies():
            lines.append("No anomalies found.")
            return "\n".join(lines)

        runs: Dict[str, List[Dict[str, Any]]] = {}

        for a in report.anomalies:
            runs.setdefault(a["run_id"], []).append(a)

        for run_id, anomalies in runs.items():
            treatment = anomalies[0]["treatment_levels"]

            lines.append("-" * 80)
            lines.append(f"RUN: {run_id}")
            lines.append(f"TREATMENT: {treatment}")
            lines.append("-" * 80)

            for a in anomalies:
                lines.append(
                    f"[{a['anomaly_type']}] "
                    f"{a['column_name']} = {a['value']} "
                    f"(row {a['row_number']})"
                )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def validate_output_log(
        run_dir: Path,
        run_id: str,
        treatment_levels: Dict[str, Any],
    ) -> AnomalyReport:

        report = AnomalyReport()

        csv_files = list(run_dir.glob("*.csv"))
        if not csv_files:
            report.add_anomaly(
                run_id,
                treatment_levels,
                str(run_dir),
                -1,
                "FILE_MISSING",
                None,
                "missing_file"
            )
            return report

        csv_file = csv_files[0]
        df = pd.read_csv(csv_file)
        columns_to_check = ResultsValidator._detect_numeric_columns(df)

        for column in columns_to_check:
            values = pd.to_numeric(df[column], errors="coerce")
            for row_number, value in values.items():
                if pd.isna(value):
                    report.add_anomaly(run_id, treatment_levels, str(csv_file), row_number, column, value, "NaN")
                elif value < 0:
                    report.add_anomaly(run_id, treatment_levels, str(csv_file), row_number, column, value, "negative")
                elif value == 0:
                    report.add_anomaly(run_id, treatment_levels, str(csv_file), row_number, column, value, "zero")
        return report 

    @staticmethod
    def save_report_to_file(report: EnergyAnomalyReport, log_file: Path) -> None:
        """Save validation report to a file."""
        report_text = ResultsValidator.generate_report_text(report)

        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'w') as f:
                f.write(report_text)
            output.console_log_OK(f"Results validation report saved to: {log_file}")
        except Exception as e:
            output.console_log_FAIL(f"Failed to write results validation report: {e}")
    