import unittest
import shutil
import tempfile
import sys

from pathlib import Path
from typing import AnyStr

sys.path.append("experiment-runner")

from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.RunnerConfig import RunnerConfig
from Plugins.Profilers.AndroidDebugBridge import (
    AndroidBatteryMonitor,
    battery_monitor,
    start_battery_monitor,
    stop_battery_monitor,
    add_data_columns,
    populate_data_columns,
    DataColumns
)

class TestADBIndividual(unittest.TestCase):

    class BatteryConfig(RunnerConfig):

        tmpdir: AnyStr = tempfile.mkdtemp()

        def clear(self):
            shutil.rmtree(self.__class__.tmpdir)

        @add_data_columns([
            DataColumns.BATTERY_PERCENTAGE.name,
            DataColumns.BATTERY_TEMPERATURE.name,
            DataColumns.CURRENT_NOW.name
        ])
        def create_run_table_model(self):
            return super().create_run_table_model()

        @start_battery_monitor(
            poll_interval=1
        )
        def start_measurement(self, context: RunnerContext):
            super().start_measurement(context)

        def interact(self, context: RunnerContext):
            import time
            time.sleep(3)

        @stop_battery_monitor
        def stop_measurement(self, context: RunnerContext):
            super().stop_measurement(context)

        @populate_data_columns
        def populate_run_data(self, context: RunnerContext):
            return {
                "avg_cpu": 52.3
            }

    def setUp(self):
        self.runner_config = self.__class__.BatteryConfig()

    def tearDown(self):
        self.runner_config.clear()

    def test_monitor(self):

        class FakeContext:
            run_dir = Path(self.runner_config.tmpdir)

        context = FakeContext()

        self.runner_config.start_measurement(context)
        self.runner_config.interact(context)
        self.runner_config.stop_measurement(context)

        run_data = self.runner_config.populate_run_data(context)

        self.assertTrue(
            (
                Path(self.runner_config.tmpdir)
                / "android_battery.csv"
            ).is_file()
        )

        print(run_data)

class TestADBCombined(unittest.TestCase):

    tmpdir: AnyStr = tempfile.mkdtemp()

    @battery_monitor(
        poll_interval=1,
        data_columns=[
            DataColumns.BATTERY_PERCENTAGE.name,
            DataColumns.BATTERY_TEMPERATURE.name,
            DataColumns.CURRENT_NOW.name,
            DataColumns.POWER_DRAW.name
        ]
    )
    class BatteryConfig(RunnerConfig):

        def clear(self):
            shutil.rmtree(
                TestADBCombined.tmpdir
            )

        def interact(self, context):
            import time
            time.sleep(3)

        def populate_run_data(self, context):
            return {
                "avg_cpu": 52.3
            }

    def setUp(self):
        self.runner_config = self.__class__.BatteryConfig()

    def tearDown(self):
        self.runner_config.clear()

    def test_monitor(self):

        class FakeContext:
            run_dir = Path(
                TestADBCombined.tmpdir
            )

        context = FakeContext()

        self.runner_config.start_measurement(context)
        self.runner_config.interact(context)
        self.runner_config.stop_measurement(context)

        run_data = self.runner_config.populate_run_data(context)

        self.assertTrue(
            (
                Path(TestADBCombined.tmpdir)
                / "android_battery.csv"
            ).is_file()
        )

        print(run_data)