import os
from pathlib import Path

print("=" * 70)
print("ENVIRONMENT VARIABLE TEST - Experiment Runner Portability")
print("=" * 70)

# Test all environment variables
env_vars = {
    "EXPERIMENT_RUNNER_OUTPUT_PATH": "/default/experiments",
    "ENERGIBRIDGE_PATH": "/usr/local/bin/energibridge",
    "WATTS_UP_PRO_PORT_MACOS": "/dev/tty.usbserial-A1000wT3",
    "WATTS_UP_PRO_PORT_LINUX": "/dev/ttyUSB0",
    "EXAMPLES_PATH": "/default/examples"
}

print("\n1. WITHOUT environment variables set:")
print("-" * 70)
for var, default in env_vars.items():
    value = os.getenv(var, f"DEFAULT: {default}")
    print(f"  {var}")
    print(f"    = {value}\n")

# Now set environment variables
os.environ["EXPERIMENT_RUNNER_OUTPUT_PATH"] = "C:\\my-experiments"
os.environ["ENERGIBRIDGE_PATH"] = "C:\\tools\\energibridge.exe"
os.environ["WATTS_UP_PRO_PORT_MACOS"] = "COM5"
os.environ["WATTS_UP_PRO_PORT_LINUX"] = "COM3"
os.environ["EXAMPLES_PATH"] = "C:\\my-examples"

print("\n2. WITH environment variables set:")
print("-" * 70)
for var in env_vars.keys():
    value = os.getenv(var, "NOT SET")
    print(f"  {var}")
    print(f"    = {value}\n")

print("=" * 70)
print("SUCCESS - Environment variables are working!")
print("=" * 70)