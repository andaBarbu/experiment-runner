from EventManager.Models.RunnerEvents import RunnerEvents
from EventManager.EventSubscriptionController import EventSubscriptionController
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.OperationType import OperationType
from ProgressManager.Output.OutputProcedure import OutputProcedure as output
from ProgressManager.Validation.RequirementsValidator import (validate_experiment_requirements)

from typing import Dict, Any, Optional, List
from pathlib import Path
from os.path import dirname, realpath

import os
import pandas as pd
import time
import subprocess
import shlex
import sys


class RunnerConfig:
    ROOT_DIR = Path(dirname(realpath(__file__)))

    name: str = "new_runner_experiment"

    default_output = ROOT_DIR / "experiments"

    results_output_path: Path = Path(
        os.getenv("EXPERIMENT_RUNNER_OUTPUT_PATH", str(default_output))
    )

    operation_type: OperationType = OperationType.AUTO

    time_between_runs_in_ms: int = 1000

    ENERGIBRIDGE_PATH = "/home/andabarbu/.cargo/bin/energibridge"
    
    """Path to log file for energy validation report. Relative to experiment output directory."""
    energy_validation_log_file: str             = "energy_validation_report.log"

    """List of data column names that contain energy measurements (e.g., ['energy', 'joules', 'watts']).
    Only used if enable_energy_validation is True."""
    energy_validation_columns:  List[str]       = [ ]

    def __init__(self):

        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.VALIDATE_EXPERIMENT, self.validate_experiment),
            (RunnerEvents.BEFORE_EXPERIMENT, self.before_experiment),
            (RunnerEvents.BEFORE_RUN, self.before_run),
            (RunnerEvents.START_RUN, self.start_run),
            (RunnerEvents.START_MEASUREMENT, self.start_measurement),
            (RunnerEvents.INTERACT, self.interact),
            (RunnerEvents.STOP_MEASUREMENT, self.stop_measurement),
            (RunnerEvents.STOP_RUN, self.stop_run),
            (RunnerEvents.POPULATE_RUN_DATA, self.populate_run_data),
            (RunnerEvents.AFTER_EXPERIMENT, self.after_experiment)
        ])

        self.run_table_model = None
        self.profiler = None

        output.console_log("Custom config loaded")

    def validate_experiment(self) -> None:
        validate_experiment_requirements(Path(__file__))

    def create_run_table_model(self) -> RunTableModel:

        factor1 = FactorModel("fib_type", ['iter', 'mem', 'rec'])
        factor2 = FactorModel("problem_size", [10, 35, 40, 5000, 10000])

        self.run_table_model = RunTableModel(
            factors=[factor1, factor2],
            exclude_combinations=[
                {factor2: [10]},
                {factor1: ['rec'], factor2: [5000, 10000]},
                {factor1: ['mem', 'iter'], factor2: [35, 40]},
            ],
            repetitions=10,

            # IMPORTANT:
            data_columns=[
                "cpu_energy",
                "core0_energy",
                "core1_energy",
                "core2_energy",
                "core3_energy",
                "core4_energy",
                "core5_energy",
                "core6_energy",
                "core7_energy"
            ]
        )

        return self.run_table_model

    def before_experiment(self) -> None:
        pass

    def before_run(self) -> None:
        pass

    def start_run(self, context: RunnerContext) -> None:
        pass

    def start_measurement(self, context: RunnerContext) -> None:

        fib_type = context.execute_run["fib_type"]
        problem_size = context.execute_run["problem_size"]

        output_csv = context.run_dir / "energibridge.csv"

        profiler_cmd = (
            f'{self.ENERGIBRIDGE_PATH} '
            f'--max-execution 20 '
            f'--output {output_csv} '
            f'--summary '
            f'{sys.executable} '
            f'examples/hello-world-fibonacci/fibonacci_{fib_type}.py '
            f'{problem_size}'
        )

        output.console_log(f"Running: {profiler_cmd}")

        energibridge_log = open(
            context.run_dir / "energibridge.log",
            "w"
        )

        self.profiler = subprocess.Popen(
            shlex.split(profiler_cmd),
            stdout=energibridge_log,
            stderr=energibridge_log,
            cwd=str(self.ROOT_DIR.parent.parent)
        )

    def interact(self, context: RunnerContext) -> None:

        output.console_log("Running program for 20 seconds")

        time.sleep(20)

    def stop_measurement(self, context: RunnerContext) -> None:

        if self.profiler:
            self.profiler.wait()

    def stop_run(self, context: RunnerContext) -> None:
        pass

    def populate_run_data(
        self,
        context: RunnerContext
    ) -> Optional[Dict[str, Any]]:

        csv_path = context.run_dir / "energibridge.csv"

        if not csv_path.exists():
            output.console_log(f"CSV missing: {csv_path}")
            return None

        if csv_path.stat().st_size == 0:
            output.console_log("CSV empty")
            return None

        try:
            df = pd.read_csv(csv_path)

        except Exception as e:
            output.console_log(f"CSV read error: {e}")
            return None

        required_columns = [
            "CPU_ENERGY (J)",
            "CORE0_ENERGY (J)",
            "CORE1_ENERGY (J)",
            "CORE2_ENERGY (J)",
            "CORE3_ENERGY (J)",
            "CORE4_ENERGY (J)",
            "CORE5_ENERGY (J)",
            "CORE6_ENERGY (J)",
            "CORE7_ENERGY (J)"
        ]

        for col in required_columns:
            if col not in df.columns:
                output.console_log(f"Missing column: {col}")
                return None

        run_data = {
            "cpu_energy": round(
                df["CPU_ENERGY (J)"].iloc[-1]
                - df["CPU_ENERGY (J)"].iloc[0],
                3
            ),

            "core0_energy": round(
                df["CORE0_ENERGY (J)"].iloc[-1]
                - df["CORE0_ENERGY (J)"].iloc[0],
                3
            ),

            "core1_energy": round(
                df["CORE1_ENERGY (J)"].iloc[-1]
                - df["CORE1_ENERGY (J)"].iloc[0],
                3
            ),

            "core2_energy": round(
                df["CORE2_ENERGY (J)"].iloc[-1]
                - df["CORE2_ENERGY (J)"].iloc[0],
                3
            ),

            "core3_energy": round(
                df["CORE3_ENERGY (J)"].iloc[-1]
                - df["CORE3_ENERGY (J)"].iloc[0],
                3
            ),

            "core4_energy": round(
                df["CORE4_ENERGY (J)"].iloc[-1]
                - df["CORE4_ENERGY (J)"].iloc[0],
                3
            ),

            "core5_energy": round(
                df["CORE5_ENERGY (J)"].iloc[-1]
                - df["CORE5_ENERGY (J)"].iloc[0],
                3
            ),

            "core6_energy": round(
                df["CORE6_ENERGY (J)"].iloc[-1]
                - df["CORE6_ENERGY (J)"].iloc[0],
                3
            ),

            "core7_energy": round(
                df["CORE7_ENERGY (J)"].iloc[-1]
                - df["CORE7_ENERGY (J)"].iloc[0],
                3
            )
        }

        output.console_log(f"Run data: {run_data}")

        return run_data


    def after_experiment(self) -> None:
        pass

    experiment_path: Path = None