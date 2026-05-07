#!/usr/bin/env python3
"""
Validate local SSH setup for distributed testing

Usage:
    python validate_local_test_setup.py
    python validate_local_test_setup.py --full
"""
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, timeout=5):
    """Run command and return (rc, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)

def check_ssh_server():
    """Check if SSH server is running"""
    print("Checking SSH server...")
    rc, _, _ = run_cmd("sudo service ssh status")
    if rc == 0:
        print("  ✓ SSH server is running")
        return True
    else:
        print("  ✗ SSH server NOT running")
        print("    Fix with: sudo service ssh start")
        return False

def check_ssh_keys():
    """Check if SSH keys exist"""
    print("Checking SSH keys...")
    key_path = Path.home() / ".ssh" / "id_rsa"
    if key_path.exists():
        print("  ✓ SSH key exists")
        return True
    else:
        print("  ✗ SSH key NOT found")
        print("    Fix with: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N \"\"")
        return False

def check_localhost_ssh(port=22):
    """Check SSH to localhost"""
    print(f"Checking SSH localhost:{port}...")
    rc, stdout, stderr = run_cmd(f"ssh -p {port} -o ConnectTimeout=3 localhost 'echo OK'")
    if rc == 0 and "OK" in stdout:
        print(f"  ✓ SSH localhost:{port} working")
        return True
    else:
        print(f"  ✗ SSH localhost:{port} FAILED")
        if "refused" in stderr or "Connection refused" in stderr:
            print(f"    Port {port} not listening on SSH")
        elif "Permission denied" in stderr:
            print(f"    Permission denied - check SSH keys")
        else:
            print(f"    Error: {stderr}")
        return False

def check_ports_configured():
    """Check if sshd_config has multiple ports"""
    print("Checking SSH config for multiple ports...")
    rc, stdout, _ = run_cmd("grep -E '^Port ' /etc/ssh/sshd_config || true")
    ports = []
    for line in stdout.split('\n'):
        if line.strip().startswith('Port '):
            port = line.strip().split()[-1]
            ports.append(port)
    
    if len(ports) >= 4:  # Should have 22, 2201, 2202, 2203
        print(f"  ✓ Found {len(ports)} ports configured: {', '.join(ports)}")
        return ports
    else:
        print(f"  ⚠ Found {len(ports)} port(s): {', '.join(ports) if ports else 'none'}")
        print("    Configure /etc/ssh/sshd_config with:")
        print("      Port 22")
        print("      Port 2201")
        print("      Port 2202")
        print("      Port 2203")
        print("    Then: sudo service ssh restart")
        return ports

def check_all_test_ports(ports=[2201, 2202, 2203]):
    """Check if all test ports are accessible"""
    print(f"Checking test ports: {', '.join(map(str, ports))}...")
    all_ok = True
    for port in ports:
        if check_localhost_ssh(port):
            pass  # Already printed
        else:
            all_ok = False
    return all_ok

def main():
    print("=" * 50)
    print("Distributed Testing - Setup Validation")
    print("=" * 50)
    print()
    
    checks = [
        ("SSH Server", check_ssh_server),
        ("SSH Keys", check_ssh_keys),
        ("Default SSH (port 22)", lambda: check_localhost_ssh(22)),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append((name, False))
        print()
    
    # Check ports
    ports = check_ports_configured()
    print()
    
    # Full test mode
    if "--full" in sys.argv and len(ports) >= 4:
        print("Running full port connectivity test...")
        print()
        if check_all_test_ports():
            print()
            print("=" * 50)
            print("✓ All checks passed!")
            print("=" * 50)
            print()
            print("Ready to test distributed execution:")
            print()
            print("  python experiment-runner/ test_distributed_config.py \\")
            print("    --distribute \"localhost:2201,localhost:2202,localhost:2203\"")
            print()
            return 0
    
    # Summary
    print("=" * 50)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Setup Status: {passed}/{total} checks passed")
    print("=" * 50)
    print()
    
    if passed < total:
        print("⚠ Some checks failed - follow the fixes above")
        return 1
    elif len(ports) < 4:
        print("⚠ Test ports not configured yet")
        print("  Run 'sudo nano /etc/ssh/sshd_config' and add:")
        print("    Port 2201")
        print("    Port 2202")
        print("    Port 2203")
        print("  Then: sudo service ssh restart")
        print()
        print("  After that, run with --full flag:")
        print("  python validate_local_test_setup.py --full")
        return 1
    else:
        print("✓ Basic setup looks good")
        print("  Run with --full flag to test all ports:")
        print("  python validate_local_test_setup.py --full")
        return 0

if __name__ == "__main__":
    sys.exit(main())
