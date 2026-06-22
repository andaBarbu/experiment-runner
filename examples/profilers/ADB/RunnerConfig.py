from EventManager.Models.RunnerEvents import RunnerEvents
from EventManager.EventSubscriptionController import EventSubscriptionController
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.OperationType import OperationType
from ProgressManager.Output.OutputProcedure import OutputProcedure as output
from ProgressManager.Validation.RequirementsValidator import (validate_experiment_requirements)
from Plugins.Profilers.AndroidDebugBridge import AndroidBatteryMonitor, battery_monitor

from typing import Dict, List, Any, Optional
from pathlib import Path
from os.path import dirname, realpath
import time

@battery_monitor(
    device_serial=None,
    data_columns=[
        'battery_percentage',
        'battery_temperature',
        'battery_voltage',
        'charge_rate',
        'power_draw'
    ]
)
class RunnerConfig:
    ROOT_DIR = Path(dirname(realpath(__file__)))

    # ================================ USER SPECIFIC CONFIG ================================
    """The name of the experiment."""
    name: str = "android_energy_monitoring_experiment"

    """The path in which Experiment Runner will create a folder with the name `self.name`"""
    results_output_path: Path = ROOT_DIR / 'experiments'

    """Experiment operation type"""
    operation_type: OperationType = OperationType.AUTO

    """Time between runs (cooldown period)"""
    time_between_runs_in_ms: int = 3000
    
    
    """Path to log file for energy validation report. Relative to experiment output directory."""
    energy_validation_log_file: str             = "energy_validation_report.log"

    """List of data column names that contain energy measurements (e.g., ['energy', 'joules', 'watts'])."""
    

    # Dynamic configurations can be one-time satisfied here before the program takes the config as-is
    # e.g. Setting some variable based on some criteria
    def __init__(self):
        """Executes immediately after program start, on config load"""

        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.VALIDATE_EXPERIMENT, self.validate_experiment),
            (RunnerEvents.BEFORE_EXPERIMENT  , self.before_experiment),
            (RunnerEvents.BEFORE_RUN         , self.before_run       ),
            (RunnerEvents.START_RUN          , self.start_run        ),
            (RunnerEvents.START_MEASUREMENT  , self.start_measurement),
            (RunnerEvents.INTERACT           , self.interact         ),
            (RunnerEvents.STOP_MEASUREMENT   , self.stop_measurement ),
            (RunnerEvents.STOP_RUN           , self.stop_run         ),
            (RunnerEvents.POPULATE_RUN_DATA  , self.populate_run_data),
            (RunnerEvents.AFTER_EXPERIMENT   , self.after_experiment )
        ])
        self.run_table_model = None

        output.console_log("Android Energy Monitoring config loaded")

    def create_run_table_model(self) -> RunTableModel:
        """Define the experimental design with factors and data columns.
        
        Note: The @AndroidEnergyMonitor.energy_monitor decorator automatically
        adds energy data columns to this model.
        """
        # Define experimental factors
        workload_factor = FactorModel("workload", ['light', 'medium', 'heavy'])
        screen_factor = FactorModel("screen_brightness", ['low', 'high'])
        
        self.run_table_model = RunTableModel(
            factors=[workload_factor, screen_factor],
            repetitions=1,
            # Add custom data columns (energy columns are added by decorator)
            data_columns=['workload_duration_ms', 'task_completion_status']
        )
        return self.run_table_model

    def validate_experiment(self) -> None:
        """Perform any experiment validation here. If any validation fails, raise an exception with details on the failure."""
        validate_experiment_requirements(Path(__file__))
        output.console_log("Config.validate_experiment() called!")

    def before_experiment(self) -> None:
        """Called before experiment starts."""
        output.console_log("Starting Android energy monitoring experiment...")
        output.console_log("Ensure your Android device is connected via USB or emulator is running")

    def before_run(self) -> None:
        """Called before each run."""
        output.console_log(f"Preparing device for run...")

    def start_run(self, context: RunnerContext) -> None:
        """Start a single experiment run."""
        output.console_log("Config.start_run() called!")

    def start_measurement(self, context: RunnerContext) -> None:
        """Start measurement - energy monitoring begins here automatically."""
        output.console_log("Energy monitoring started (battery metrics being collected)")

    def interact(self, context: RunnerContext):
        workload = context.execute_run['workload']
        brightness = context.execute_run['screen_brightness']

        duration_ms = {
            'light': 5000,
            'medium': 10000,
            'heavy': 15000
        }[workload]

        output.console_log(
            f"Running {workload} workload "
            f"for {duration_ms}ms "
            f"(brightness: {brightness})"
        )

        time.sleep(duration_ms / 1000)

        output.console_log("Workload completed")

    def stop_measurement(self, context: RunnerContext) -> None:
        """Stop measurement - energy monitoring ends here automatically."""
        output.console_log("Energy monitoring stopped")

    def stop_run(self, context: RunnerContext) -> None:
        """Stop the current run."""
        output.console_log(f"Stopped run: {context.execute_run['__run_id']}")

    def populate_run_data(self, context: RunnerContext) -> Optional[Dict[str, Any]]:
        """Populate data columns for this run. """
        workload = context.execute_run['workload']
        
        duration_ms = {
            'light': 5000,
            'medium': 10000,
            'heavy': 15000
        }.get(workload, 5000)
        
        return {
            'workload_duration_ms': duration_ms,
            'task_completion_status': 'success'
        }

    def after_experiment(self) -> None:
        """Called after experiment completes."""
        output.console_log("Android energy monitoring experiment completed!")
        output.console_log("Results stored in experiments/android_energy_monitoring_experiment/")

    # ================================ DO NOT ALTER BELOW THIS LINE ================================
    experiment_path: Path = None