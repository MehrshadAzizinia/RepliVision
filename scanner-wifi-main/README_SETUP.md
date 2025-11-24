# WiFi Setup Service for RepliVision Scanner

This WiFi setup service runs separately from the scanner and provides a captive portal for easy WiFi configuration on your Raspberry Pi.

## Features

- **Automatic Access Point Mode**: Creates a WiFi hotspot when no internet connection is detected
- **Captive Portal**: Automatically opens a web page when you connect
- **Network Scanning**: Shows all available WiFi networks with signal strength
- **Internet Verification**: Ensures the connection has internet before completing setup
- **Persistent Configuration**: Saves WiFi settings across reboots
- **Beautiful Dark UI**: Modern, mobile-friendly interface

## Installation on Raspberry Pi

### 1. Install Dependencies

```bash
# Install Flask
sudo pip3 install flask

# Ensure NetworkManager is installed (should be default on Raspberry Pi OS)
sudo apt-get update
sudo apt-get install -y network-manager
```

### 2. Copy Files to Raspberry Pi

Copy the `wifi_setup.py` file to your Raspberry Pi:

```bash
# From your Mac/PC, copy to RPi
scp scanner-wifi-main/wifi_setup.py pi@raspberrypi:~/RepliVision/RepliVision/
```

### 3. Create Systemd Service

Create a service that runs the WiFi setup automatically on boot:

```bash
sudo nano /etc/systemd/system/replivision-wifi.service
```

Add this content:

```ini
[Unit]
Description=RepliVision Scanner WiFi Setup Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/RepliVision/RepliVision
ExecStart=/usr/bin/python3 /home/pi/RepliVision/RepliVision/wifi_setup.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and exit (Ctrl+X, then Y, then Enter).

### 4. Enable and Start the Service

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable replivision-wifi.service

# Start the service now
sudo systemctl start replivision-wifi.service

# Check the status
sudo systemctl status replivision-wifi.service
```

## How It Works

### First Boot (No WiFi Configured):

1. Service starts and detects no internet connection
2. Creates WiFi Access Point: **"Replivision-Scanner"**
3. Password: **"repli2025"**
4. Web server starts on port 80

### Connecting to Configure WiFi:

1. On your phone/laptop, connect to **"Replivision-Scanner"** WiFi
2. Enter password: **"repli2025"**
3. **A web page should automatically open** (captive portal)
4. If it doesn't auto-open, navigate to: `http://10.42.0.1`
5. Select your home WiFi network from the dropdown
6. Enter your WiFi password
7. Click "Connect"
8. The Pi will connect to your WiFi and verify internet connection
9. Once connected, the Access Point shuts down automatically

### After WiFi is Configured:

1. On subsequent boots, the service checks for internet connection
2. If connected, it does nothing (scanner can run normally)
3. If no connection, it falls back to Access Point mode for reconfiguration

## Using with Scanner

Once WiFi is configured, you can run the scanner normally:

```bash
python3 scanner.py
```

The scanner runs completely separately from the WiFi management system.

## Configuration

Edit `wifi_setup.py` to change these settings:

```python
AP_SSID = "Replivision-Scanner"  # Change AP name
AP_PASSWORD = "repli2025"        # Change AP password (min 8 chars)
```

## Troubleshooting

### Check Service Status:
```bash
sudo systemctl status replivision-wifi.service
```

### View Logs:
```bash
sudo journalctl -u replivision-wifi.service -f
```

### Restart Service:
```bash
sudo systemctl restart replivision-wifi.service
```

### Stop Service:
```bash
sudo systemctl stop replivision-wifi.service
```

### Disable Service:
```bash
sudo systemctl disable replivision-wifi.service
```

### Reset WiFi Configuration:
```bash
# Remove the configuration file
rm ~/RepliVision/RepliVision/wifi_configured.json

# Restart the service
sudo systemctl restart replivision-wifi.service
```

### Manual Test (Without Service):
```bash
# Stop the service first
sudo systemctl stop replivision-wifi.service

# Run manually to see output
sudo python3 ~/RepliVision/RepliVision/wifi_setup.py
```

## File Locations

- **Service file**: `/etc/systemd/system/replivision-wifi.service`
- **Python script**: `/home/pi/RepliVision/RepliVision/wifi_setup.py`
- **Config file**: `/home/pi/RepliVision/RepliVision/wifi_configured.json`
- **Status file**: `/tmp/replivision_status.txt`

## Network Details

- **Access Point IP**: 10.42.0.1
- **Access Point SSID**: Replivision-Scanner
- **Access Point Password**: repli2025
- **WiFi Interface**: wlan0
- **Web Server Port**: 80 (falls back to 8080 if permission denied)

## Security Notes

- The Access Point uses WPA-PSK encryption
- Change the default password in the configuration
- The web interface is only accessible when connected to the AP
- WiFi credentials are stored securely by NetworkManager

## Integration with Scanner

The WiFi service and scanner are completely independent:

1. **WiFi Service** (`wifi_setup.py`):
   - Manages WiFi connectivity
   - Runs as a systemd service
   - Only active when needed

2. **Scanner** (`scanner.py`):
   - Handles motor control and camera recording
   - Run manually when you need to scan
   - Assumes WiFi is already connected

This separation ensures:
- WiFi management doesn't interfere with scanning
- Scanner code stays simple and focused
- Each service can be updated independently
