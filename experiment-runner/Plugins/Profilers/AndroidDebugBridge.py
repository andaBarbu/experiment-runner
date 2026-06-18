from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional, Dict, Any
from enum import Enum, auto
import re
import subprocess
import threading
import csv
from datetime import datetime
import pandas as pd

from Plugins.Profilers.DataSource import CLISource, ParameterDict
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.RunnerConfig import RunnerConfig


class DataColumns(Enum):
    """Battery metrics that can be collected from Android devices via ADB dumpsys battery"""
    BATTERY_PERCENTAGE  = auto()
    BATTERY_TEMPERATURE = auto()
    BATTERY_VOLTAGE     = auto()
    CURRENT_NOW         = auto()
    CHARGE_COUNTER      = auto()
    BATTERY_HEALTH      = auto()
    CHARGING_STATUS     = auto()
    POWER_DRAW          = auto()

    _PATTERN = re.compile(r'(android_battery__)(.+)')

    @property
    def name(self) -> str:
        return f'android_battery__{super().name.lower()}'

class AndroidBatteryMonitor(CLISource):
    """Monitor battery and energy metrics from Android devices via ADB during experiment execution.
    This plugin connects to Android devices via ADB and periodically collects battery statistics."""
    source_name = "adb"
    supported_platforms = ["Linux", "Darwin"]

    ANDROID_BATTERY_PARAMETERS = {}
    
    def __init__(self, device_serial: Optional[str] = None, poll_interval: int = 2, out_file: Path = "android_battery.csv", data_columns: Optional[Iterable[str]] = None):
        super().__init__()
        
        self.device_serial = device_serial
        self.poll_interval = poll_interval
        self.logfile = out_file
        self.stop_monitoring = threading.Event()
        self.monitoring_thread = None
        self.monitor_error: Optional[Exception] = None
        
        # Validate ADB availability
        self._validate_adb_available()
    
    @property
    def parameters(self) -> ParameterDict:
        return ParameterDict(self.ANDROID_BATTERY_PARAMETERS)
    
    def _validate_adb_available(self):
        """Verify ADB is installed and accessible."""
        try:
            result = subprocess.run(['adb', 'version'], capture_output=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("ADB version check failed.")
        except FileNotFoundError:
            raise RuntimeError("ADB not found.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("ADB timeout - check ADB installation")
    
    def _get_device_serial(self) -> str:
        if self.device_serial:
            return self.device_serial

        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        devices = []

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("List of devices"):
                continue
            if "\tdevice" in line:
                devices.append(line.split()[0])
        if not devices:
            raise RuntimeError("No ADB devices found")
        
        return devices[0]

    def _parse_battery_data(self, dumpsys_output: str) -> Dict[str, Any]:
        """Parse dumpsys battery output and extract metrics."""
        data = {}
        if not dumpsys_output:
            return data

        patterns = {
            'percentage'     : r'^\s*level:\s+(\d+)',
            'temperature'    : r'^\s*temperature:\s+(\d+)',
            'voltage'        : r'^\s*voltage:\s+(\d+)',
            'health'         : r'^\s*health:\s+(\d+)',
            'status'         : r'^\s*status:\s+(\d+)',
            'current_now'    : r'^\s*current now:\s+(-?\d+)',
            'charge_counter' : r'^\s*charge counter:\s+(\d+)',
        }        
        
        for key, pattern in patterns.items():
            match = re.search(pattern,  dumpsys_output, re.MULTILINE)
            if match: data[key] = match.group(1)
        
        # Calculate power draw estimate
        if 'voltage' in data and 'current_now' in data:
            try:
                voltage_mv = int(data['voltage'])
                current_ua = int(data['current_now'])
                voltage_v = voltage_mv / 1000.0
                current_ma = abs(float(data["current_now"]))
                power_mw = voltage_v * current_ma
                data['power_draw'] = f"{power_mw:.2f}"
            except (ValueError, KeyError):
                pass
        return data
    
    def start(self):
        """Start monitoring battery metrics."""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            raise RuntimeError("Android energy monitoring is already running")

        self.stop_monitoring.clear()
        self.measurements = []
        self.monitor_error = None
        try:
            self.logfile.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create log directory: {e}")

        self._get_device_serial()
        self.monitoring_thread = threading.Thread(target=self._monitor_loop, name="AndroidEnergyMonitor", daemon=True)
        self.monitoring_thread.start()
    
    def _monitor_loop(self):
        try:
            device_serial = self._get_device_serial()
            with open(self.logfile, 'w', newline='') as csvfile:
                fieldnames = [
                    'timestamp',
                    'percentage',
                    'temperature',
                    'voltage',
                    'health',
                    'status',
                    'current_now',
                    'charge_counter',
                    'power_draw'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                while not self.stop_monitoring.is_set():
                    result = subprocess.run(
                        [
                            'adb',
                            '-s',
                            device_serial,
                            'shell',
                            'dumpsys battery'
                        ],
                        capture_output=True, text=True, timeout=10)

                    if result.returncode != 0:
                        raise RuntimeError(f"ADB command failed:\n{result.stderr}")

                    metrics = self._parse_battery_data(result.stdout)
                    metrics['timestamp'] = datetime.now().isoformat()
                    self.measurements.append(metrics)
                    writer.writerow(metrics)
                    csvfile.flush()
                    self.stop_monitoring.wait(self.poll_interval)
        except Exception as e:
            self.monitor_error = e
            self.stop_monitoring.set()

    def stop(self) -> str:
        if not self.monitoring_thread:
            return ""
        self.stop_monitoring.set()
        self.monitoring_thread.join()
        if self.monitor_error:
            raise RuntimeError(f"AndroidBatteryMonitor failed: {self.monitor_error}")
        self.monitoring_thread = None

        return str(self.logfile)
    
    def __del__(self):
        """Cleanup on deletion."""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.stop_monitoring.set()
            self.monitoring_thread.join(timeout=5)
    
    @staticmethod
    def parse_log(logfile: Path) -> Dict[str, Any]:
        """Parse battery metrics CSV log file."""
        try:
            df = pd.read_csv(logfile)
            return df.to_dict(orient='records')
        except Exception as e:
            print(f"Could not parse Android battery log: {e}")
            return {}


# Decorator functions following CodecarbonWrapper pattern
def battery_monitor(device_serial=None, poll_interval=2, data_columns=None):
    def battery_monitor_decorator(cls):
        cols = data_columns or [col.name for col in DataColumns]

        cls.create_run_table_model = add_data_columns(cols)(cls.create_run_table_model)
        cls.start_measurement = start_battery_monitor(device_serial, poll_interval)(cls.start_measurement)
        cls.stop_measurement = stop_battery_monitor(cls.stop_measurement)
        cls.populate_run_data = populate_data_columns(cls.populate_run_data)
        return cls

    return battery_monitor_decorator

def start_battery_monitor(device_serial: Optional[str] = None, poll_interval: int = 2):
    def start_battery_monitor_decorator(func):
        def wrapper(*args, **kwargs):
            self: RunnerConfig = args[0]
            context: RunnerContext = args[1]
            logfile = (context.run_dir.resolve()/ "android_battery.csv")

            self.__android_battery_monitor__ = (AndroidBatteryMonitor(device_serial=device_serial, poll_interval=poll_interval, out_file=logfile))
            self.__android_battery_monitor__.start()
            return func(*args, **kwargs)

        return wrapper

    return start_battery_monitor_decorator

def stop_battery_monitor(func):
    def wrapper(*args, **kwargs):
        self: RunnerConfig = args[0]
        ret_val = func(*args, **kwargs)

        if hasattr(self, "__android_battery_monitor__"):
            self.__android_battery_monitor__.stop()
        return ret_val

    return wrapper

def add_data_columns(data_cols: Iterable[str]):
    """Decorator to add Android battery data columns to run table."""
    def add_data_columns_decorator(func):
        def wrapper(*args, **kwargs):
            self: RunnerConfig = args[0]
            
            func(*args, **kwargs)
            for dc in data_cols:
                col_name = f'android_battery__{dc.lower()}' if not dc.startswith('android_battery__') else dc
                if col_name not in self.run_table_model.get_data_columns():
                    self.run_table_model.get_data_columns().append(col_name)
            return self.run_table_model

        return wrapper

    return add_data_columns_decorator

def populate_data_columns(func):
    def wrapper(*args, **kwargs):
        self: RunnerConfig = args[0]
        ret_val = func(*args, **kwargs)

        if ret_val is None:
            ret_val = {}
        if not hasattr(self, "__android_battery_monitor__"):
            return ret_val
        try:
            df = pd.read_csv(self.__android_battery_monitor__.logfile)
            if df.empty:
                return ret_val

            metric_map = {
                "battery_percentage": "percentage",
                "battery_temperature": "temperature",
                "battery_voltage": "voltage",
                "battery_health": "health",
                "charging_status": "status",
                "charge_rate": "charge_rate",
                "current_now": "current_now",
                "power_draw": "power_draw"
            }

            for dc in self.run_table_model.get_data_columns():
                m = DataColumns._PATTERN.value.match(dc)
                if not m:
                    continue
                metric_name = m.group(2)
                csv_column = metric_map.get(metric_name)

                if csv_column is None:
                    continue
                if csv_column not in df.columns:
                    continue

                values = pd.to_numeric(df[csv_column], errors="coerce").dropna()
                if len(values) == 0:
                    continue
                ret_val[dc] = float(values.mean())
        except Exception as e:

            print(f"Error reading Android battery metrics: {e}")
        return ret_val
        
    return wrapper