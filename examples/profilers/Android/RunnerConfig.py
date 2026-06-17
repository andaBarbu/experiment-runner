"""
Example RunnerConfig demonstrating Mobile Energy Monitoring with AndroidEnergyMonitor.

This example shows how to automatically collect battery and energy metrics from
Android devices during experiment execution using ADB.

Prerequisites:
  - Android SDK Platform Tools installed (adb command available)
  - Android device connected via USB or emulator running
  - USB debugging enabled on device (for physical devices)

To run this example:
  python experiment-runner/ examples/android-energy-monitoring/RunnerConfig.py
"""

from EventManager.Models.RunnerEvents import RunnerEvents
from EventManager.EventSubscriptionController import EventSubscriptionController
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.OperationType import OperationType
from ProgressManager.Output.OutputProcedure import OutputProcedure as output

from Plugins.Profilers.AndroidMonitor import AndroidBatteryMonitor, battery_monitor
from typing import Dict, List, Any, Optional
from pathlib import Path
from os.path import dirname, realpath
import time


# Apply the battery monitoring decorator to automatically collect battery metrics
@AndroidBatteryMonitor.battery_monitor(
    device_serial=None,  # Auto-detect first connected device
    poll_interval=1,     # Poll battery stats every 1 second
    data_columns=['battery_percentage', 'battery_temperature', 'battery_voltage', 
                 'charge_rate', 'power_draw']
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

    def __init__(self):
        """Initialize the runner config and subscribe to events."""
        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.BEFORE_EXPERIMENT, self.before_experiment),
            (RunnerEvents.BEFORE_RUN       , self.before_run       ),
            (RunnerEvents.START_RUN        , self.start_run        ),
            (RunnerEvents.START_MEASUREMENT, self.start_measurement),
            (RunnerEvents.INTERACT         , self.interact         ),
            (RunnerEvents.STOP_MEASUREMENT , self.stop_measurement ),
            (RunnerEvents.STOP_RUN         , self.stop_run         ),
            (RunnerEvents.POPULATE_RUN_DATA, self.populate_run_data),
            (RunnerEvents.AFTER_EXPERIMENT , self.after_experiment )
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
            repetitions=3,
            # Add custom data columns (energy columns are added by decorator)
            data_columns=['workload_duration_ms', 'task_completion_status']
        )
        return self.run_table_model

    def before_experiment(self) -> None:
        """Called before experiment starts."""
        output.console_log("Starting Android energy monitoring experiment...")
        output.console_log("Ensure your Android device is connected via USB or emulator is running")

    def before_run(self) -> None:
        """Called before each run."""
        output.console_log(f"Preparing device for run...")

    def start_run(self, context: RunnerContext) -> None:
        """Start a single experiment run.
        
        In a real scenario, this would start your Android app or workload.
        For this example, we just wait a bit.
        """
        output.console_log(f"Started run: {context.variation}")

    def start_measurement(self, context: RunnerContext) -> None:
        """Start measurement - energy monitoring begins here automatically."""
        output.console_log("Energy monitoring started (battery metrics being collected)")

    def interact(self, context: RunnerContext) -> None:
        """Perform the actual workload/experiment.
        
        In a real scenario, this would run your Android app or background task.
        """
        # Simulate different workloads based on factor levels
        workload = context.variation['workload']
        brightness = context.variation['screen_brightness']
        
        duration_ms = {
            'light': 5000,
            'medium': 10000,
            'heavy': 15000
        }.get(workload, 5000)
        
        output.console_log(f"Running {workload} workload for {duration_ms}ms (brightness: {brightness})")
        
        # Simulate workload
        time.sleep(duration_ms / 1000.0)
        
        output.console_log(f"Workload completed")

    def stop_measurement(self, context: RunnerContext) -> None:
        """Stop measurement - energy monitoring ends here automatically."""
        output.console_log("Energy monitoring stopped")

    def stop_run(self, context: RunnerContext) -> None:
        """Stop the current run."""
        output.console_log(f"Stopped run: {context.variation}")

    def populate_run_data(self, context: RunnerContext) -> Optional[Dict[str, Any]]:
        """Populate data columns for this run.
        
        The @AndroidEnergyMonitor.energy_monitor decorator automatically
        populates energy-related columns. This method can add custom data.
        """
        # In a real scenario, you would parse workload results here
        workload = context.variation['workload']
        
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
