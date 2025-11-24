#!/usr/bin/env python3
"""
Debug script to test WiFi connection manually
Run this to test WiFi configuration without the full web server
"""

import subprocess
import time

def run_command(cmd):
    """Execute shell command and return output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def test_wifi_connection(ssid, password):
    """Test WiFi connection"""
    print(f"\n{'='*60}")
    print(f"Testing WiFi Connection")
    print(f"{'='*60}")
    print(f"SSID: {ssid}")
    print(f"Password: {'*' * len(password)}")
    print(f"{'='*60}\n")

    # Step 1: Check WiFi is enabled
    print("[1/7] Checking WiFi radio status...")
    success, output, error = run_command("nmcli radio wifi")
    if success:
        print(f"   WiFi Radio: {output.strip()}")
        if output.strip() != "enabled":
            print("   Enabling WiFi radio...")
            run_command("nmcli radio wifi on")
    else:
        print(f"   Error: {error}")

    # Step 2: Check current connections
    print("\n[2/7] Checking current connections...")
    success, output, error = run_command("nmcli connection show --active")
    if success:
        print(f"   Active connections:\n{output}")

    # Step 3: Scan for the network
    print(f"\n[3/7] Scanning for network '{ssid}'...")
    success, output, error = run_command(f"nmcli device wifi list | grep '{ssid}'")
    if success:
        print(f"   Found network:\n{output}")
    else:
        print(f"   Network not found in scan! Rescanning...")
        run_command("nmcli device wifi rescan")
        time.sleep(3)
        success, output, error = run_command(f"nmcli device wifi list | grep '{ssid}'")
        if success:
            print(f"   Found network:\n{output}")
        else:
            print(f"   ERROR: Network '{ssid}' not visible!")
            return False

    # Step 4: Delete any existing connection with same SSID
    connection_name = f"WiFi-{ssid}"
    print(f"\n[4/7] Deleting existing connection '{connection_name}' if exists...")
    success, output, error = run_command(f"nmcli connection delete '{connection_name}' 2>/dev/null")
    if success:
        print(f"   Deleted existing connection")
    else:
        print(f"   No existing connection to delete")

    # Step 5: Create new connection
    print(f"\n[5/7] Creating new WiFi connection profile...")
    cmd_create = (
        f"nmcli connection add type wifi con-name '{connection_name}' "
        f"ifname wlan0 ssid '{ssid}' "
        f"wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{password}' "
        f"connection.autoconnect yes "
        f"connection.autoconnect-priority 100"
    )

    print(f"   Command: {cmd_create.replace(password, '***HIDDEN***')}")
    success, output, error = run_command(cmd_create)

    if not success:
        print(f"   ERROR creating connection:")
        print(f"   stdout: {output}")
        print(f"   stderr: {error}")
        return False

    print(f"   Connection profile created successfully")

    # Step 6: Bring up the connection
    print(f"\n[6/7] Activating connection '{connection_name}'...")
    cmd_connect = f"nmcli connection up '{connection_name}'"

    success, output, error = run_command(cmd_connect)

    if not success:
        print(f"   ERROR activating connection:")
        print(f"   stdout: {output}")
        print(f"   stderr: {error}")

        # Additional diagnostics
        print(f"\n   Running additional diagnostics...")

        # Check connection details
        print(f"\n   Connection details:")
        run_command(f"nmcli connection show '{connection_name}'")

        # Check device status
        print(f"\n   Device status:")
        s, o, e = run_command("nmcli device status")
        print(o)

        return False

    print(f"   Connection activated successfully!")
    print(f"   Output: {output}")

    # Step 7: Verify connection
    print(f"\n[7/7] Verifying connection...")
    time.sleep(3)

    # Check if connected
    success, output, error = run_command("nmcli -t -f ACTIVE,SSID dev wifi")
    if success:
        for line in output.strip().split('\n'):
            if line.startswith('yes:'):
                connected_ssid = line.split(':', 1)[1]
                print(f"   Connected to: {connected_ssid}")
                if connected_ssid == ssid:
                    print(f"   ✓ Successfully connected to '{ssid}'!")

                    # Get IP address
                    s, ip_output, _ = run_command("hostname -I")
                    if s:
                        ips = ip_output.strip().split()
                        print(f"   IP Address: {ips[0] if ips else 'Unknown'}")

                    # Test internet
                    print(f"\n   Testing internet connectivity...")
                    s, _, _ = run_command("ping -c 1 -W 2 8.8.8.8")
                    if s:
                        print(f"   ✓ Internet connection working!")
                    else:
                        print(f"   ✗ No internet connection")

                    return True

    print(f"   ✗ Connection verification failed")
    return False


def main():
    print("\n" + "="*60)
    print("WiFi Connection Debug Tool")
    print("="*60)

    # Get SSID and password from user
    ssid = input("\nEnter WiFi SSID: ").strip()
    password = input("Enter WiFi Password: ").strip()

    if not ssid or not password:
        print("\nError: SSID and password are required!")
        return

    # Test connection
    success = test_wifi_connection(ssid, password)

    print("\n" + "="*60)
    if success:
        print("✓ WiFi Connection Successful!")
    else:
        print("✗ WiFi Connection Failed")
    print("="*60)


if __name__ == "__main__":
    main()
