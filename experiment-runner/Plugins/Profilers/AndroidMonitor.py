from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional, Dict, Any
from enum import Enum, auto
import re
import subprocess
import threading
import time
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
    BATTERY_HEALTH      = auto()
    CHARGING_STATUS     = auto()
    CHARGE_RATE         = auto()
    CURRENT_NOW         = auto()
    POWER_DRAW          = auto()

    _PATTERN = re.compile(r'(android_energy__)(.+)')

    @property
    def name(self) -> str:
        return f'android_energy__{super().name.lower()}'


class AndroidBatteryMonitor(CLISource):
    """Monitor battery and energy metrics from Android devices via ADB during experiment execution.
    
    This plugin connects to Android devices via ADB and periodically collects battery statistics,
    associating them with specific experiment runs through timestamping and run identifiers.
    """
    
    source_name = "adb"
    supported_platforms = ["Linux", "Darwin"]
    
    ANDROID_BATTERY_PARAMETERS = {}
    
    def __init__(self, device_serial: Optional[str] = None, poll_interval: int = 2, out_file: Path = "android_battery.csv", data_columns: Optional[Iterable[str]] = None):
        """
        Initialize AndroidBatteryMonitor.
        Args:
            device_serial: ADB device serial. If None, uses first connected device.
            poll_interval: Interval in seconds between battery stat polls.
            out_file: Path for CSV output file.
            data_columns: List of data columns to collect (defaults to all available).
        """
        super().__init__()
        
        self.device_serial = device_serial
        self.poll_interval = poll_interval
        self.logfile = out_file
        self.stop_monitoring = threading.Event()
        self.monitoring_thread = None
        self.measurements = []
        
        # Store data columns for later reference
        self.selected_data_columns = data_columns or [col.name for col in DataColumns]
        
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
                raise RuntimeError("ADB version check failed")
        except FileNotFoundError:
            raise RuntimeError("ADB not found. Please install Android SDK Platform Tools")
        except subprocess.TimeoutExpired:
            raise RuntimeError("ADB timeout - check ADB installation")
    
    def _get_device_serial(self) -> str:
        """Get target device serial, prompt if needed."""
        if self.device_serial:
            return self.device_serial
        
        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
            devices = [line.split()[0] for line in result.stdout.split('\n') 
                      if line.strip() and 'device' not in line and line[0] != '*']
            if not devices:
                raise RuntimeError("No ADB devices found. Connect a device or start an emulator")
            return devices[0]
        except Exception as e:
            raise RuntimeError(f"Failed to detect ADB devices: {e}")
    
    def _parse_battery_data(self, dumpsys_output: str) -> Dict[str, Any]:
        """Parse dumpsys battery output and extract metrics."""
        data = {}
        
        if not dumpsys_output:
            return data
        
        # Extract values using regex patterns
        patterns = {
            'percentage': r'level:\s+(\d+)',
            'temperature': r'temperature:\s+(\d+)',
            'voltage': r'voltage:\s+(\d+)',
            'health': r'health:\s+(\d+)',
            'status': r'status:\s+(\d+)',
            'current_now': r'current now:\s+(-?\d+)',
            'charge_rate': r'current now:\s+(-?\d+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, dumpsys_output)
            if match:
                data[key] = match.group(1)
        
        # Calculate power draw estimate (if current is available)
        if 'voltage' in data and 'current_now' in data:
            try:
                voltage_mv = int(data['voltage'])
                current_ua = int(data['current_now'])
                # Power (mW) = Voltage (mV) * Current (mA) / 1000
                power_mw = (voltage_mv * abs(current_ua)) / 1000000.0
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
        
        try:
            self.logfile.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create log directory: {e}")
        
        self.monitoring_thread = threading.Thread(
            target=self._monitor_loop,
            name="AndroidEnergyMonitor",
            daemon=False
        )
        self.monitoring_thread.start()
    
    def _monitor_loop(self):
        """Main monitoring loop running in separate thread."""
        device_serial = self._get_device_serial()
        
        with open(self.logfile, 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'percentage', 'temperature', 'voltage', 'health', 
                         'status', 'current_now', 'charge_rate', 'power_draw']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            while not self.stop_monitoring.is_set():
                try:
                    result = subprocess.run(
                        ['adb', '-s', device_serial, 'shell', 'dumpsys battery'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        metrics = self._parse_battery_data(result.stdout)
                        metrics['timestamp'] = datetime.now().isoformat()
                        self.measurements.append(metrics)
                        writer.writerow(metrics)
                        csvfile.flush()
                    
                    self.stop_monitoring.wait(self.poll_interval)
                
                except subprocess.TimeoutExpired:
                    pass
                except Exception as e:
                    print(f"Error during battery monitoring: {e}")
                    break
    
    def stop(self, wait=False) -> str:
        """Stop monitoring and return aggregated metrics."""
        if not self.monitoring_thread:
            return ""
        
        self.stop_monitoring.set()
        
        if wait or self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=self.poll_interval * 2)
        
        if self.monitoring_thread.is_alive():
            raise RuntimeError("Android monitoring thread failed to stop")
        
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
def battery_monitor(device_serial: Optional[str] = None,
                   poll_interval: int = 2,
                   data_columns: Optional[Iterable[str]] = None):
    """Main decorator to enable Android battery monitoring.
    
    Args:
        device_serial: ADB device serial (optional)
        poll_interval: Polling interval in seconds
        data_columns: List of metrics to collect
    """
    def battery_monitor_decorator(cls: RunnerConfig.__class__):
        cols = data_columns or [col.name for col in DataColumns]
        
        cls.create_run_table_model = add_data_columns(cols)(cls.create_run_table_model)
        cls.start_measurement = start_battery_monitor(device_serial, poll_interval)(cls.start_measurement)
        cls.stop_measurement = stop_battery_monitor(cls.stop_measurement)
        cls.populate_run_data = populate_data_columns(cls.populate_run_data)
        
        return cls
    return battery_monitor_decorator


def start_battery_monitor(device_serial: Optional[str] = None, poll_interval: int = 2):
    """Decorator to start battery monitoring at measurement start."""
    def start_battery_monitor_decorator(func):
        def wrapper(*args, **kwargs):
            self: RunnerConfig = args[0]
            context: RunnerContext = args[1]
            
            logfile = context.run_dir.resolve() / 'android_battery.csv'
            self.__android_battery_monitor__ = AndroidBatteryMonitor(
                device_serial=device_serial,
                poll_interval=poll_interval,
                out_file=logfile
            )
            self.__android_battery_monitor__.start()
            return func(*args, **kwargs)
        return wrapper
    return start_battery_monitor_decorator


def stop_battery_monitor(func):
    """Decorator to stop battery monitoring at measurement stop."""
    def wrapper(*args, **kwargs):
        self: RunnerConfig = args[0]
        
        ret_val = func(*args, **kwargs)
        if hasattr(self, '__android_battery_monitor__'):
            self.__android_battery_monitor__.stop(wait=True)
        return ret_val
    return wrapper


def add_data_columns(data_cols: Iterable[str]):
    """Decorator to add Android battery data columns to run table."""
    def add_data_columns_decorator(func):
        def wrapper(*args, **kwargs):
            self: RunnerConfig = args[0]
            
            func(*args, **kwargs)  # will set self.run_table_model
            for dc in data_cols:
                col_name = f'android_battery__{dc.lower()}' if not dc.startswith('android_battery__') else dc
                if col_name not in self.run_table_model.get_data_columns():
                    self.run_table_model.get_data_columns().append(col_name)
            return self.run_table_model
        return wrapper
    return add_data_columns_decorator


def populate_data_columns(func):
    """Decorator to populate Android battery data columns from CSV."""
    def wrapper(*args, **kwargs):
        self: RunnerConfig = args[0]
        
        ret_val = func(*args, **kwargs)
        if ret_val is None:
            ret_val = {}
        
        if hasattr(self, '__android_battery_monitor__'):
            try:
                df = pd.read_csv(self.__android_battery_monitor__.logfile)
                if not df.empty:
                    # Aggregate metrics (mean, min, max)
                    for col in df.columns:
                        if col != 'timestamp':
                            try:
                                values = pd.to_numeric(df[col], errors='coerce').dropna()
                                if not values.empty:
                                    ret_val[f'android_battery__{col}_mean'] = values.mean()
                                    ret_val[f'android_battery__{col}_max'] = values.max()
                                    ret_val[f'android_battery__{col}_min'] = values.min()
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                print(f"Error reading Android battery metrics: {e}")
        
        return ret_val
    return wrapper
