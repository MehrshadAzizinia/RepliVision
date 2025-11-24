#!/usr/bin/env python3
"""
WiFi Setup Service for Replivision Scanner (Raspberry Pi)
Handles automatic AP mode for initial setup and client mode for normal operation
"""

import subprocess
import json
import time
import os
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from threading import Thread, Event
import logging

# Get user's home directory dynamically
USER_HOME = str(Path.home())
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
AP_SSID = "Replivision-Scanner"
AP_PASSWORD = "repli2025"  # Must be 8-63 characters for WPA
CONFIG_FILE = os.path.join(SCRIPT_DIR, "wifi_configured.json")
STATUS_FILE = "/tmp/replivision_status.txt" # This will store connection status

# Define globals for WiFi interface and AP connection name
WIFI_INTERFACE = "wlan0"
AP_CON_NAME = "Replivision-Scanner-AP"

# Global event to signal when internet connection is active
internet_connected_event = Event()

# HTML Template for setup page
SETUP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Replivision Scanner WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background: #1a1a1a; /* Changed: Overall background color */
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: #222222; /* Changed: Main container background color */
            border-radius: 8px;
            border: 1px solid #333333;
            max-width: 500px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #ffffff;
            margin-bottom: 5px; /* Adjusted margin to bring subtitle closer */
            font-size: 24px;
            font-weight: 500;
            text-align: center;
        }
        .subtitle { /* New style for the subtitle */
            color: #aaaaaa; /* Lighter color for secondary text */
            margin-bottom: 30px; /* Space below subtitle */
            font-size: 12px; /* Smaller font size */
            text-align: center;
            display: block; /* Ensure it takes its own line */
        }
        label {
            display: block;
            margin-bottom: 8px;
            margin-top: 20px;
            color: #dddddd; /* Adjusted for better contrast on new background */
            font-weight: 400;
            font-size: 14px;
        }
        label:first-of-type {
            margin-top: 0;
        }
        select, input {
            width: 100%;
            padding: 12px 14px;
            border: 1px solid #444444; /* Adjusted border color */
            border-radius: 4px;
            font-size: 15px;
            margin-bottom: 0;
            transition: all 0.2s ease;
            background: #333333; /* Changed: Input fields background color */
            color: #ffffff;
        }
        select:focus, input:focus {
            outline: none;
            border-color: #666666; /* Adjusted focus border color */
            background: #383838; /* Slightly lighter on focus */
        }
        select option {
            background: #333333; /* Option background to match input */
            color: #ffffff;
        }
        input::placeholder {
            color: #999999; /* Adjusted placeholder color */
        }
        .button-group {
            display: flex;
            gap: 12px;
            margin-top: 30px;
            justify-content: flex-end;
        }
        button {
            padding: 10px 24px;
            border: 1px solid #444444; /* Adjusted border color */
            border-radius: 4px;
            font-size: 14px;
            font-weight: 400;
            cursor: pointer;
            transition: all 0.2s ease;
            background: #333333; /* Changed: Cancel button background color */
            color: #ffffff;
        }
        button:hover {
            background: #383838; /* Adjusted hover background */
            border-color: #555555; /* Adjusted hover border */
        }
        button:active {
            background: #404040; /* Adjusted active background */
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            background: #333333; /* Ensure disabled also uses base color */
        }
        button.primary {
            background: #ffffff; /* Primary button remains bright for prominence */
            color: #000000;
            border-color: #ffffff;
        }
        button.primary:hover {
            background: #e0e0e0;
            border-color: #e0e0e0;
        }
        button.primary:active {
            background: #d0d0d0;
        }
        button.primary:disabled {
            background: #666666;
            border-color: #666666;
            color: #333333;
        }
        .status {
            margin-top: 20px;
            padding: 12px 14px;
            border-radius: 4px;
            font-size: 14px;
            display: none;
            border: 1px solid;
            color: #ffffff; /* Ensure status text is visible */
        }
        .status.success {
            background: rgba(34,197,94,0.2); /* Slightly darker background for better contrast */
            color: #22c55e;
            border-color: rgba(34,197,94,0.4);
        }
        .status.error {
            background: rgba(239,68,68,0.2); /* Slightly darker background for better contrast */
            color: #ef4444;
            border-color: rgba(239,68,68,0.4);
        }
        .status.info {
            background: rgba(59,130,246,0.2); /* Slightly darker background for better contrast */
            color: #3b82f6;
            border-color: rgba(59,130,246,0.4);
        }
        .loading {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,.3); /* Adjusted for dark background */
            border-radius: 50%;
            border-top-color: #ffffff; /* Adjusted for dark background */
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Replivision Scanner Setup</h1> <!-- Changed H1 text -->
        <span class="subtitle">  Connect your Replivision Scanner to WiFi</span> <!-- New subtitle -->
        
        <form id="wifiForm">
            <label for="ssid">Network</label>
            <select id="ssid" name="ssid" required>
                <option value="">Scanning for networks...</option>
                {% for network in networks %}
                <option value="{{ network.ssid }}">
                    {{ network.ssid }} ({{ network.signal }}%)
                </option>
                {% endfor %}
            </select>
            
            <label for="password">Password</label>
            <input type="password" id="password" name="password" 
                   placeholder="Enter WiFi password" required>
            
            <div class="button-group">
                <button type="button" id="cancelBtn">Cancel</button>
                <button type="submit" id="submitBtn" class="primary">
                    Connect
                </button>
            </div>
        </form>
        
        <div id="status" class="status"></div>
    </div>

    <script>
        const form = document.getElementById('wifiForm');
        const statusDiv = document.getElementById('status');
        const submitBtn = document.getElementById('submitBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        let statusPollingInterval;

        // Cancel just refreshes the page
        cancelBtn.addEventListener('click', () => {
            window.location.reload();
        });

        // Refresh network list on page load
        window.addEventListener('load', () => {
            fetch('/api/scan')
                .then(r => r.json())
                .then(data => {
                    const select = document.getElementById('ssid');
                    select.innerHTML = '<option value="">Select a network...</option>';
                    data.networks.forEach(net => {
                        const opt = document.createElement('option');
                        opt.value = net.ssid;
                        opt.textContent = `${net.ssid} (${net.signal}%)`;
                        select.appendChild(opt);
                    });
                })
                .catch(err => console.error('Scan failed:', err));
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const ssid = document.getElementById('ssid').value;
            const password = document.getElementById('password').value;
            
            if (!ssid || !password) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="loading"></span>Connecting...';
            showStatus('Attempting to connect to WiFi...', 'info');
            
            try {
                const response = await fetch('/api/configure', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ssid, password })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Connection initiated. Checking internet status...', 'info');
                    // Start polling for internet connection status
                    statusPollingInterval = setInterval(pollConnectionStatus, 3000); // Poll every 3 seconds
                } else {
                    showStatus('✗ Connection failed: ' + result.error, 'error');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Connect';
                }
            } catch (error) {
                showStatus('✗ Connection error. Please try again.', 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Connect';
            }
        });
        
        async function pollConnectionStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                if (data.status === 'Connected - Internet Active') {
                    clearInterval(statusPollingInterval);
                    showStatus('✓ Connected successfully. Redirecting...', 'success');
                    // Give a small delay before redirecting to ensure message is seen
                    setTimeout(() => {
                        window.location.href = '/success';
                    }, 2000); 
                } else if (data.status.startsWith('Connected - No Internet')) {
                    clearInterval(statusPollingInterval);
                    showStatus('⚠ Connected to WiFi, but no internet detected. Try another network or check router.', 'error');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Connect';
                } else {
                    showStatus('Connecting... (Waiting for internet)', 'info');
                }
            } catch (error) {
                console.error('Status polling error:', error);
                showStatus('Connection status uncertain. Retrying...', 'info');
            }
        }

        function showStatus(message, type) {
            statusDiv.textContent = message;
            statusDiv.className = 'status ' + type;
            statusDiv.style.display = 'block';
        }
    </script>
</body>
</html>
"""

SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Setup Complete</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: linear-gradient(145deg, #1e1e30 0%, #252540 100%);
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 1px rgba(255,255,255,0.1) inset;
            max-width: 400px;
            width: 100%;
            padding: 45px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .checkmark {
            font-size: 72px;
            margin-bottom: 25px;
            animation: checkmarkPop 0.5s ease-out;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        @keyframes checkmarkPop {
            0% { transform: scale(0); }
            50% { transform: scale(1.1); }
            100% { transform: scale(1); }
        }
        h1 {
            color: #10b981;
            margin-bottom: 15px;
            font-size: 28px;
            font-weight: 600;
        }
        p {
            color: #a0a0b0;
            line-height: 1.6;
            font-size: 15px;
        }
        .success-message {
            margin-top: 25px;
            padding: 15px;
            background: rgba(16,185,129,0.1);
            border: 1px solid rgba(16,185,129,0.2);
            border-radius: 10px;
            color: #10b981;
            font-size: 14px;
        }
        .close-instruction {
            margin-top: 25px;
            padding: 15px;
            background: rgba(59,130,246,0.1);
            border: 1px solid rgba(59,130,246,0.2);
            border-radius: 10px;
            color: #3b82f6;
            font-size: 14px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="checkmark">✓</div>
        <h1>Success!</h1>
        <p>Your Replivision scanner is now connected to WiFi and ready to use.</p>
        <div class="success-message">
            Connection established successfully. Your scanner is online.
        </div>
        <div class="close-instruction">
            You can close this window now
        </div>
    </div>
</body>
</html>
"""


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
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {cmd}")
        return False, "", "Command timed out"
    except Exception as e:
        logger.error(f"Command failed: {cmd}, Error: {e}")
        return False, "", str(e)


def is_wifi_configured():
    """Check if WiFi has been configured before"""
    return os.path.exists(CONFIG_FILE)


def save_wifi_config(ssid):
    """Save WiFi configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'ssid': ssid, 'configured': True}, f)
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def scan_wifi_networks():
    """Scan for available WiFi networks"""
    success, output, _ = run_command("nmcli -t -f SSID,SIGNAL dev wifi list")
    
    networks = []
    seen_ssids = set()
    
    if success and output:
        for line in output.strip().split('\n'):
            if ':' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    ssid = parts[0].strip()
                    signal = parts[1].strip()
                    
                    if ssid and ssid not in seen_ssids and ssid != AP_SSID:
                        seen_ssids.add(ssid)
                        try:
                            networks.append({
                                'ssid': ssid,
                                'signal': int(signal) if signal else 0
                            })
                        except ValueError:
                            networks.append({'ssid': ssid, 'signal': 0})
    
    # Sort by signal strength
    networks.sort(key=lambda x: x['signal'], reverse=True)
    return networks[:20]  # Return top 20 networks


def start_ap_mode():
    """Start Access Point mode with proper configuration for captive portal"""
    logger.info("Starting Access Point mode...")

    # Section 1. Deactivate ALL existing Wi-Fi client connections on the interface
    success_deactivate_wlan, _, error_deactivate_wlan = run_command(
        f"nmcli connection show --active | grep {WIFI_INTERFACE} | grep wifi | awk '{{print $1}}' | xargs -r -I {{}} nmcli connection down {{}}"
    )
    if success_deactivate_wlan:
        logger.info(f"Deactivated active Wi-Fi client connections on {WIFI_INTERFACE}.")
    else:
        logger.warning(f"Could not deactivate active Wi-Fi client connections on {WIFI_INTERFACE}: {error_deactivate_wlan}")

    # Section 2. Ensure the Wi-Fi device is enabled and not in a weird state
    run_command(f"nmcli radio wifi on")
    run_command(f"nmcli device set {WIFI_INTERFACE} managed on")
    time.sleep(1)

    # Section 3. Clean up any previous AP connection profile
    logger.info(f"Deactivating existing AP connection '{AP_CON_NAME}' if active...")
    run_command(f"nmcli connection down '{AP_CON_NAME}' 2>/dev/null")
    logger.info(f"Deleting existing AP connection profile '{AP_CON_NAME}' if it exists...")
    run_command(f"nmcli connection delete '{AP_CON_NAME}' 2>/dev/null")
    time.sleep(1)

    # Section 4. Create a new, explicit AP connection profile
    cmd_create_ap = (
        f"nmcli connection add type wifi ifname {WIFI_INTERFACE} mode ap "
        f"ssid '{AP_SSID}' con-name '{AP_CON_NAME}' "
        f"wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{AP_PASSWORD}' "
        f"ipv4.method shared ipv4.addresses 10.42.0.1/24 "
        f"ipv6.method ignore"
    )
    success_create, output_create, error_create = run_command(cmd_create_ap)

    if not success_create:
        logger.error(f"Failed to create AP connection profile '{AP_CON_NAME}': {error_create}")
        return False
    else:
        logger.info(f"Created AP connection profile: '{AP_CON_NAME}'")
        time.sleep(1)

    # Section 5. Bring up the newly created AP connection profile
    cmd_up_ap = f"nmcli connection up '{AP_CON_NAME}'"
    success_up, output_up, error_up = run_command(cmd_up_ap)

    if success_up:
        logger.info(f"AP Mode started: SSID='{AP_SSID}' via connection '{AP_CON_NAME}'")
        
        # Section 6. Configure iptables for captive portal detection
        logger.info("Setting up iptables for captive portal...")
        run_command("iptables -t nat -F") # Flush existing NAT rules first
        # Allow traffic to the AP's own web server (port 80) and DNS (port 53)
        # This is crucial: don't redirect traffic meant for the portal itself
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p tcp --dport 80 -d 10.42.0.1 -j ACCEPT")
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p udp --dport 53 -d 10.42.0.1 -j ACCEPT")

        # Redirect all HTTP/HTTPS and DNS traffic not destined for the portal to the portal
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p tcp --dport 80 -j DNAT --to-destination 10.42.0.1:80")
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p tcp --dport 443 -j DNAT --to-destination 10.42.0.1:80")
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p udp --dport 53 -j DNAT --to-destination 10.42.0.1:53")
        run_command(f"iptables -t nat -A PREROUTING -i {WIFI_INTERFACE} -p tcp --dport 53 -j DNAT --to-destination 10.42.0.1:53")
        
        # Post-routing for masquerading (allow clients to access internet once AP is bridge)
        run_command("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE") # Assuming eth0 is upstream
        run_command("sysctl -w net.ipv4.ip_forward=1") # Enable IP forwarding

        update_status("AP Mode Active")
        internet_connected_event.clear() # Clear the event at AP start
        time.sleep(5)
        return True
    else:
        logger.error(f"Failed to bring up AP mode connection '{AP_CON_NAME}': {error_up}")
        status_check = run_command(f"nmcli connection show '{AP_CON_NAME}'")
        logger.error(f"NetworkManager connection '{AP_CON_NAME}' status:\n{status_check[1]}")
        return False


def connect_to_wifi(ssid, password):
    """Connect to WiFi network and save it persistently"""
    logger.info(f"Attempting to connect to: {ssid}")
    
    # Create a persistent WiFi connection profile
    connection_name = f"WiFi-{ssid}"
    
    # Delete any existing connection with this SSID to avoid conflicts
    run_command(f"nmcli connection delete '{connection_name}' 2>/dev/null")
    
    # Create a new connection profile that will persist
    cmd_create = (
        f"nmcli connection add type wifi con-name '{connection_name}' "
        f"ifname {WIFI_INTERFACE} ssid '{ssid}' "
        f"wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{password}' "
        f"connection.autoconnect yes "
        f"connection.autoconnect-priority 100"
    )
    
    success_create, output_create, error_create = run_command(cmd_create)
    
    if not success_create:
        logger.error(f"Failed to create WiFi connection profile: {error_create}")
        update_status(f"Error: Failed to create connection for {ssid}")
        return False, f"Failed to create connection: {error_create}"
    
    logger.info(f"Created persistent WiFi connection profile: {connection_name}")
    time.sleep(1)
    
    # Now activate the connection
    cmd_connect = f"nmcli connection up '{connection_name}'"
    success, output, error = run_command(cmd_connect)
    
    if success:
        logger.info(f"Successfully initiated connection to {ssid}")
        update_status(f"Connecting to {ssid}...")
        
        # Save configuration marker, even if internet isn't fully verified yet
        save_wifi_config(ssid)
        
        return True, "Connection initiated"
    else:
        logger.error(f"Failed to connect: {error}")
        # Clean up the failed connection profile
        run_command(f"nmcli connection delete '{connection_name}' 2>/dev/null")
        update_status(f"Error: Failed to connect to {ssid}")
        return False, error


def check_internet_connection():
    """Check if we have internet connectivity"""
    # Use a more reliable check for internet: DNS lookup + ping
    success_dns, _, _ = run_command("dig +short google.com @8.8.8.8")
    success_ping, _, _ = run_command("ping -c 1 -W 2 8.8.8.8")
    return success_dns and success_ping


def update_status(status_message):
    """Update status file for external monitoring"""
    try:
        with open(STATUS_FILE, 'w') as f:
            f.write(f"{status_message}\n{time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Status updated to: {status_message}")
    except Exception as e:
        logger.error(f"Failed to update status file: {e}")


@app.route('/')
def index():
    """Main setup page"""
    networks = scan_wifi_networks()
    return render_template_string(SETUP_HTML, networks=networks)


@app.route('/success')
def success():
    """Success page"""
    return render_template_string(SUCCESS_HTML)


# --- CAPTIVE PORTAL DETECTION ROUTES ---
# These must be defined before the API routes

@app.route('/hotspot-detect.html')
def apple_captive_portal():
    """Responds to Apple's captive portal detection (iOS/macOS)"""
    logger.info("Apple captive portal check detected - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/library/test/success.html')
def apple_captive_portal_alt():
    """Alternative Apple captive portal check"""
    logger.info("Apple alternative captive portal check - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/hotspot-detect-v2.html')
def apple_captive_portal_v2():
    """Another Apple captive portal endpoint"""
    logger.info("Apple v2 captive portal check - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/generate_204')
def android_captive_portal():
    """Responds to Android captive portal detection"""
    logger.info("Android captive portal check detected - returning captive response")
    return redirect(url_for('index'))

@app.route('/gen_204')
def android_captive_portal_alt():
    """Alternative Android endpoint"""
    logger.info("Android alternative captive portal check - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/connecttest.txt')
def windows_captive_portal():
    """Responds to Windows captive portal detection"""
    logger.info("Windows captive portal check detected - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/redirect')
def windows_captive_redirect():
    """Windows 10 captive portal redirect"""
    logger.info("Windows redirect check - redirecting to setup")
    return redirect(url_for('index'))

@app.route('/ncsi.txt')
def windows_ncsi():
    """Windows NCSI (Network Connectivity Status Indicator)"""
    logger.info("Windows NCSI check - redirecting to setup")
    return redirect(url_for('index'))


@app.route('/api/scan')
def api_scan():
    """API endpoint to scan for networks"""
    networks = scan_wifi_networks()
    return jsonify({'networks': networks})


@app.route('/api/configure', methods=['POST'])
def api_configure():
    """API endpoint to configure WiFi"""
    data = request.get_json()
    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid or not password:
        return jsonify({'success': False, 'error': 'Missing SSID or password'})
    
    # Clear the internet_connected_event as we're starting a new connection attempt
    internet_connected_event.clear()
    update_status(f"Attempting to connect to '{ssid}'...")

    success, message = connect_to_wifi(ssid, password)
    
    if success:
        # Start a background thread to monitor connection and eventually shut down AP
        Thread(target=monitor_and_shutdown_ap, daemon=True).start()
        return jsonify({'success': True, 'message': 'Connection process initiated.'})
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/api/status')
def api_status():
    """API endpoint to check connection status for frontend polling"""
    try:
        if not os.path.exists(STATUS_FILE):
            return jsonify({'status': 'Unknown', 'timestamp': 'N/A'})
        
        with open(STATUS_FILE, 'r') as f:
            lines = f.readlines()
            status_line = lines[0].strip() if lines else 'Unknown'
            timestamp_line = lines[1].strip() if len(lines) > 1 else 'N/A'
            return jsonify({'status': status_line, 'timestamp': timestamp_line})
    except Exception as e:
        logger.error(f"Error reading status file: {e}")
        return jsonify({'status': 'Error reading status', 'timestamp': 'N/A'}), 500


def monitor_and_shutdown_ap():
    """
    Background thread to monitor internet connection and gracefully shut down AP mode.
    This runs after a client has initiated a WiFi connection attempt.
    """
    logger.info("Starting AP monitor and shutdown thread.")
    max_wait_time = 120 # Max 2 minutes to get internet connection
    poll_interval = 5   # Check every 5 seconds
    
    # First, wait for the Pi to connect to the new external WiFi
    for _ in range(max_wait_time // poll_interval):
        # Check if the AP itself is still up. If not, something went wrong early.
        success_ap_active, _, _ = run_command(f"nmcli connection show --active | grep '{AP_CON_NAME}'")
        if not success_ap_active:
            logger.warning("AP connection seems to have gone down prematurely during connection attempt.")
            update_status("Error: AP prematurely down")
            return # Exit thread if AP is not active

        # Check for internet connectivity on the Pi
        if check_internet_connection():
            logger.info("Internet connection detected on Pi.")
            update_status("Connected - Internet Active")
            internet_connected_event.set() # Signal that internet is active
            break # Exit loop, internet is active
        else:
            logger.info("Still waiting for internet connection on Pi...")
            update_status("Connecting... (Waiting for internet)")
            time.sleep(poll_interval)
    else:
        logger.warning("Timed out waiting for internet connection after connecting to new WiFi.")
        update_status("Connected - No Internet Detected (Timeout)")
        internet_connected_event.set() # Signal even on timeout, so client can react (maybe display error)

    # Now, give the client device a generous amount of time to load the success page.
    # The client-side JavaScript will only redirect to /success AFTER internet_connected_event is set
    # and /api/status reports 'Connected - Internet Active'.
    grace_period_for_client_redirect = 30 # seconds
    logger.info(f"Giving client device {grace_period_for_client_redirect} seconds to redirect to success page.")
    time.sleep(grace_period_for_client_redirect)
    
    # Finally, shut down the AP mode
    logger.info("Initiating AP mode shutdown.")
    # Deactivate the AP mode connection
    success_down, _, error_down = run_command(f"nmcli connection down '{AP_CON_NAME}' 2>/dev/null")
    if success_down:
        logger.info(f"AP connection '{AP_CON_NAME}' successfully deactivated.")
    else:
        logger.warning(f"Failed to deactivate AP connection '{AP_CON_NAME}': {error_down}")
    
    # Delete the AP connection profile so it doesn't interfere on next boot
    success_del, _, error_del = run_command(f"nmcli connection delete '{AP_CON_NAME}' 2>/dev/null")
    if success_del:
        logger.info(f"AP connection profile '{AP_CON_NAME}' successfully deleted.")
    else:
        logger.warning(f"Failed to delete AP connection profile '{AP_CON_NAME}' : {error_del}")

    # Flush iptables nat table rules now that AP is down
    logger.info("Flushing iptables nat table rules after AP shutdown.")
    run_command("iptables -t nat -F")
    run_command("sysctl -w net.ipv4.ip_forward=0") # Disable IP forwarding

    # Here you would start your Replivision scanner service
    logger.info("Replivision scanner service (placeholder) would start now.")
    # run_command("systemctl start replivision-app.service")


def main():
    """Main application logic"""
    logger.info("Replivision Scanner WiFi Setup Service starting...")
    
    # Initialize status file
    update_status("Service Starting")

    # Check if we're already configured
    if is_wifi_configured():
        logger.info("WiFi already configured, checking connection...")
        
        # Try to verify connection by checking if any WiFi client connection is active
        # and has internet
        if check_internet_connection():
            logger.info("Internet connection active, setup not needed")
            update_status("Connected - Internet Active")
            # Here you would start your Replivision scanner application
            # run_command("systemctl start replivision-app.service")
            return
        else:
            logger.warning("WiFi configured but no internet detected, falling back to AP mode for setup.")
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
                logger.info("Removed stale WiFi config file")
    
    # Start AP mode for setup
    if start_ap_mode():
        logger.info(f"Setup portal available at: http://10.42.0.1")
        logger.info(f"Connect to WiFi: SSID='{AP_SSID}' Password='{AP_PASSWORD}'")
        
        # Start web server
        try:
            app.run(host='0.0.0.0', port=80, debug=False)
        except PermissionError:
            logger.error("Permission denied to bind to port 80. Run with sudo.")
            logger.info("Trying port 8080 instead...")
            app.run(host='0.0.0.0', port=8080, debug=False)
    else:
        logger.error("Failed to start AP mode")
        update_status("Error: Failed to start AP mode")


if __name__ == '__main__':
    main()