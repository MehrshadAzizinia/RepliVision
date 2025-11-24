#!/usr/bin/env python3
"""
Raspberry Pi 5 Dual Camera Scanner with Motor Control and WiFi Captive Portal
Records from two Camera Module 3 Wide cameras simultaneously while spinning the motor,
then stitches the videos together. Includes WiFi Access Point with captive portal for easy WiFi configuration.
"""

import os
import sys
import time
import json
import threading
import subprocess
from datetime import datetime
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import RPi.GPIO as GPIO
from flask import Flask, render_template_string, request, jsonify, redirect

# ============================================================================
# CONFIGURATION - Modify these variables as needed
# ============================================================================

# Motor Settings
MOTOR_SPEED = 200  # Motor speed in steps per second (adjust as needed)
RECORDING_DURATION = 10  # Duration in seconds for recording and motor spinning

# Motor Pin Configuration
STEP_PIN = 17   # PUL- on DM542
DIR_PIN  = 27   # DIR- on DM542
EN_PIN   = 22   # ENA- on DM542 (optional)

# Camera Settings
RESOLUTION = (1920, 1080)  # Video resolution (width, height)
FRAMERATE = 30  # Frames per second
CAMERA_0_INDEX = 0  # First camera index
CAMERA_1_INDEX = 1  # Second camera index

# Output Settings
OUTPUT_DIR = "."  # Current working directory for final output

# WiFi Captive Portal Settings
CAPTIVE_PORTAL_ENABLED = True  # Enable/disable WiFi captive portal
AP_SSID = "RepliVision-Setup"  # Access Point SSID
AP_PASSWORD = "replivision"  # Access Point password (min 8 chars)
WEB_SERVER_PORT = 80  # Web server port for captive portal

# ============================================================================
# HTML Templates for Captive Portal
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RepliVision WiFi Setup</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            max-width: 500px;
            width: 100%;
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
            text-align: center;
        }

        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }

        .status {
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            font-weight: 500;
        }

        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .status.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }

        select, input[type="password"], input[type="text"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
            font-family: inherit;
        }

        select:focus, input:focus {
            outline: none;
            border-color: #667eea;
        }

        .btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-top: 10px;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .btn:active {
            transform: translateY(0);
        }

        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .btn-secondary {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            margin-top: 10px;
        }

        .network-item {
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .network-item:hover {
            border-color: #667eea;
            background: #f8f9ff;
        }

        .network-item.selected {
            border-color: #667eea;
            background: #667eea;
            color: white;
        }

        .signal-strength {
            font-size: 12px;
            color: #666;
        }

        .network-item.selected .signal-strength {
            color: #fff;
        }

        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }

        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .hidden {
            display: none;
        }

        .current-status {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }

        .current-status strong {
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎥 RepliVision Scanner</h1>
        <p class="subtitle">WiFi Configuration Portal</p>

        {% if current_wifi %}
        <div class="current-status">
            <strong>Currently Connected:</strong> {{ current_wifi }}
        </div>
        {% endif %}

        {% if status_message %}
        <div class="status {{ status_type }}">
            {{ status_message }}
        </div>
        {% endif %}

        <form method="POST" action="/configure" id="wifiForm">
            <div class="form-group">
                <label for="ssid">Select WiFi Network:</label>
                <select name="ssid" id="ssid" required>
                    <option value="">-- Select Network --</option>
                    {% for network in networks %}
                    <option value="{{ network.ssid }}">{{ network.ssid }} ({{ network.signal }}%)</option>
                    {% endfor %}
                </select>
            </div>

            <div class="form-group">
                <label for="password">WiFi Password:</label>
                <input type="password" name="password" id="password" placeholder="Enter password" required>
            </div>

            <button type="submit" class="btn" id="connectBtn">Connect to WiFi</button>
        </form>

        <button type="button" class="btn btn-secondary" onclick="location.reload()">Refresh Networks</button>

        <button type="button" class="btn btn-secondary" onclick="startScanner()" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">Start Scanner</button>
    </div>

    <script>
        document.getElementById('wifiForm').addEventListener('submit', function(e) {
            e.preventDefault();

            const btn = document.getElementById('connectBtn');
            btn.disabled = true;
            btn.textContent = 'Connecting...';

            const formData = new FormData(this);

            fetch('/configure', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('✅ Successfully connected to WiFi!\\n\\nIP Address: ' + data.ip + '\\n\\nThe scanner will now switch to the new network. You may need to reconnect your device to the same network.');
                    setTimeout(() => location.reload(), 3000);
                } else {
                    alert('❌ Connection failed: ' + data.message);
                    btn.disabled = false;
                    btn.textContent = 'Connect to WiFi';
                }
            })
            .catch(error => {
                alert('❌ Error: ' + error);
                btn.disabled = false;
                btn.textContent = 'Connect to WiFi';
            });
        });

        function startScanner() {
            fetch('/start_scanner', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('✅ Scanner started!\\n\\nThe motor and cameras will begin recording.');
                } else {
                    alert('❌ Failed to start scanner: ' + data.message);
                }
            })
            .catch(error => {
                alert('❌ Error: ' + error);
            });
        }
    </script>
</body>
</html>
"""

# ============================================================================
# WiFi Captive Portal Server
# ============================================================================

class WiFiCaptivePortal:
    """
    WiFi Access Point with Captive Portal for easy WiFi configuration.
    Creates a WiFi AP that users can connect to, then shows a web page for WiFi setup.
    """

    def __init__(self, ap_ssid=AP_SSID, ap_password=AP_PASSWORD, port=WEB_SERVER_PORT):
        """
        Initialize the WiFi captive portal.

        Args:
            ap_ssid: Access Point SSID name
            ap_password: Access Point password
            port: Web server port
        """
        self.ap_ssid = ap_ssid
        self.ap_password = ap_password
        self.port = port
        self.app = Flask(__name__)
        self.server_thread = None
        self.running = False
        self.scanner_instance = None

        # Setup Flask routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes for the web interface."""

        @self.app.route('/')
        @self.app.route('/index.html')
        @self.app.route('/generate_204')  # Android captive portal detection
        @self.app.route('/gen_204')  # Android
        @self.app.route('/hotspot-detect.html')  # iOS captive portal detection
        @self.app.route('/connecttest.txt')  # Windows
        @self.app.route('/redirect')
        def index():
            """Main page - shows WiFi configuration interface."""
            networks = self._scan_wifi_networks()
            current_wifi = self._get_current_wifi()

            return render_template_string(
                HTML_TEMPLATE,
                networks=networks,
                current_wifi=current_wifi,
                status_message=request.args.get('message'),
                status_type=request.args.get('type', 'info')
            )

        @self.app.route('/configure', methods=['POST'])
        def configure():
            """Configure WiFi with provided credentials."""
            ssid = request.form.get('ssid')
            password = request.form.get('password')

            if not ssid or not password:
                return jsonify({
                    'status': 'error',
                    'message': 'SSID and password are required'
                })

            result = self._configure_wifi(ssid, password)
            return jsonify(result)

        @self.app.route('/start_scanner', methods=['POST'])
        def start_scanner():
            """Start the scanner workflow."""
            if self.scanner_instance:
                threading.Thread(target=self.scanner_instance.run_scan, daemon=True).start()
                return jsonify({'status': 'success', 'message': 'Scanner started'})
            else:
                return jsonify({'status': 'error', 'message': 'Scanner not initialized'})

    def _scan_wifi_networks(self):
        """Scan and return available WiFi networks."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi', 'list'],
                capture_output=True,
                text=True,
                timeout=10
            )

            networks = []
            seen_ssids = set()

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            ssid, signal = parts
                            ssid = ssid.strip()
                            # Skip empty SSIDs and duplicates
                            if ssid and ssid not in seen_ssids and ssid != self.ap_ssid:
                                seen_ssids.add(ssid)
                                networks.append({
                                    'ssid': ssid,
                                    'signal': signal.strip()
                                })

            # Sort by signal strength
            networks.sort(key=lambda x: int(x['signal']), reverse=True)
            return networks[:20]  # Return top 20 networks

        except Exception as e:
            print(f"[PORTAL] Error scanning WiFi: {e}")
            return []

    def _get_current_wifi(self):
        """Get currently connected WiFi network."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('yes:'):
                        return line.split(':', 1)[1]
            return None
        except:
            return None

    def _configure_wifi(self, ssid, password):
        """Configure WiFi connection."""
        try:
            print(f"[PORTAL] Configuring WiFi for SSID: {ssid}")

            # Delete existing connection if it exists
            subprocess.run(
                ['nmcli', 'connection', 'delete', ssid],
                capture_output=True,
                timeout=10
            )

            # Connect to new network
            result = subprocess.run(
                ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                print(f"[PORTAL] Successfully configured WiFi: {ssid}")
                time.sleep(2)

                # Get IP address
                ip_result = subprocess.run(
                    ['hostname', '-I'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                ip_address = ip_result.stdout.strip().split()[0] if ip_result.returncode == 0 else "Unknown"

                return {
                    'status': 'success',
                    'message': f'Connected to {ssid}',
                    'ssid': ssid,
                    'ip': ip_address
                }
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                print(f"[PORTAL] Failed to configure WiFi: {error_msg}")
                return {
                    'status': 'error',
                    'message': f'Failed to connect: {error_msg}'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Configuration error: {str(e)}'
            }

    def _create_access_point(self):
        """Create WiFi Access Point using nmcli."""
        try:
            print(f"[PORTAL] Creating Access Point: {self.ap_ssid}")

            # Delete existing hotspot connection if it exists
            subprocess.run(
                ['nmcli', 'connection', 'delete', 'Hotspot'],
                capture_output=True
            )

            # Create new hotspot
            result = subprocess.run(
                [
                    'nmcli', 'device', 'wifi', 'hotspot',
                    'ssid', self.ap_ssid,
                    'password', self.ap_password
                ],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                print(f"[PORTAL] Access Point created successfully")
                print(f"[PORTAL] SSID: {self.ap_ssid}")
                print(f"[PORTAL] Password: {self.ap_password}")
                return True
            else:
                print(f"[PORTAL] Failed to create AP: {result.stderr}")
                return False

        except Exception as e:
            print(f"[PORTAL] Error creating Access Point: {e}")
            return False

    def start(self, scanner_instance=None):
        """Start the captive portal (AP + web server)."""
        if self.running:
            return

        self.scanner_instance = scanner_instance
        self.running = True

        # Create Access Point
        if not self._create_access_point():
            print("[PORTAL] Warning: Could not create Access Point")

        # Start web server in a thread
        def run_server():
            try:
                print(f"[PORTAL] Starting web server on port {self.port}")
                print(f"[PORTAL] Connect to WiFi: {self.ap_ssid}")
                print(f"[PORTAL] Then open: http://192.168.4.1 or http://10.42.0.1")
                self.app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)
            except Exception as e:
                print(f"[PORTAL] Web server error: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

    def stop(self):
        """Stop the captive portal."""
        if self.running:
            print("[PORTAL] Stopping captive portal...")
            self.running = False

            # Delete hotspot connection
            try:
                subprocess.run(
                    ['nmcli', 'connection', 'delete', 'Hotspot'],
                    capture_output=True,
                    timeout=10
                )
            except:
                pass

# ============================================================================
# Motor Control Class
# ============================================================================

class MotorController:
    """Handles stepper motor control during recording."""

    def __init__(self, speed=MOTOR_SPEED):
        """
        Initialize the motor controller.

        Args:
            speed: Motor speed in steps per second
        """
        self.speed = speed
        self.running = False
        self.step_delay = 1.0 / (2 * self.speed)
        self.motor_thread = None

    def init_gpio(self):
        """Initialize GPIO pins for motor control."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(STEP_PIN, GPIO.OUT)
        GPIO.setup(DIR_PIN, GPIO.OUT)
        GPIO.setup(EN_PIN, GPIO.OUT)

        GPIO.output(STEP_PIN, GPIO.LOW)
        GPIO.output(DIR_PIN, GPIO.LOW)

        # Enable driver (LOW = enabled on most drivers)
        GPIO.output(EN_PIN, GPIO.LOW)

    def cleanup(self):
        """Clean up GPIO resources."""
        GPIO.output(STEP_PIN, GPIO.LOW)
        GPIO.output(EN_PIN, GPIO.HIGH)  # Disable driver
        GPIO.cleanup()

    def _run_motor(self):
        """Internal method to generate step pulses."""
        last_step_time = time.perf_counter()
        step_state = False

        while self.running:
            now = time.perf_counter()

            if (now - last_step_time) >= self.step_delay:
                last_step_time = now
                step_state = not step_state
                GPIO.output(STEP_PIN, GPIO.HIGH if step_state else GPIO.LOW)

            # Small sleep to avoid 100% CPU usage
            time.sleep(0.0001)

    def start(self):
        """Start the motor spinning."""
        if not self.running:
            self.running = True
            self.motor_thread = threading.Thread(target=self._run_motor, daemon=True)
            self.motor_thread.start()
            print(f"[MOTOR] Started at {self.speed} steps/sec")

    def stop(self):
        """Stop the motor."""
        if self.running:
            self.running = False
            if self.motor_thread:
                self.motor_thread.join()
            GPIO.output(STEP_PIN, GPIO.LOW)
            print("[MOTOR] Stopped")

# ============================================================================
# Camera Recording Class
# ============================================================================

class DualCameraRecorder:
    """Handles recording from two Raspberry Pi cameras simultaneously."""

    def __init__(self, duration=RECORDING_DURATION, output_dir=OUTPUT_DIR):
        """
        Initialize the dual camera recorder.

        Args:
            duration: Recording duration in seconds
            output_dir: Directory to save recordings
        """
        self.duration = duration
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

        # Output filenames (temporary files in temp directory)
        self.temp_dir = os.path.join(self.output_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.camera0_file = os.path.join(
            self.temp_dir,
            f"camera0_{self.timestamp}.mp4"
        )
        self.camera1_file = os.path.join(
            self.temp_dir,
            f"camera1_{self.timestamp}.mp4"
        )
        self.final_file = os.path.join(
            self.output_dir,
            f"final_{self.timestamp}.mp4"
        )

        # Thread synchronization
        self.recording_complete = {"camera0": False, "camera1": False}
        self.recording_errors = {"camera0": None, "camera1": None}

    def record_camera(self, camera_index, output_file, camera_name):
        """
        Record from a single camera.

        Args:
            camera_index: Camera device index
            output_file: Output MP4 file path
            camera_name: Name identifier for the camera (for logging)
        """
        try:
            print(f"[{camera_name}] Initializing camera {camera_index}...")

            # Initialize camera
            picam = Picamera2(camera_index)

            # Configure camera for video recording
            video_config = picam.create_video_configuration(
                main={"size": RESOLUTION, "format": "RGB888"},
                controls={"FrameRate": FRAMERATE}
            )
            picam.configure(video_config)

            # Setup H.264 encoder with MP4 output
            encoder = H264Encoder(bitrate=10000000)  # 10 Mbps bitrate
            output = FfmpegOutput(output_file)

            print(f"[{camera_name}] Starting recording to {output_file}...")

            # Start recording
            picam.start_recording(encoder, output)

            # Record for specified duration
            time.sleep(self.duration)

            # Stop recording
            picam.stop_recording()
            picam.close()

            print(f"[{camera_name}] Recording complete!")
            self.recording_complete[camera_name] = True

        except Exception as e:
            error_msg = f"Error recording from {camera_name}: {str(e)}"
            print(f"[{camera_name}] {error_msg}")
            self.recording_errors[camera_name] = error_msg
            self.recording_complete[camera_name] = True

    def record_both_cameras(self):
        """Record from both cameras simultaneously using threads."""
        print(f"\n{'='*60}")
        print(f"Starting dual camera recording")
        print(f"Duration: {self.duration} seconds")
        print(f"Resolution: {RESOLUTION[0]}x{RESOLUTION[1]} @ {FRAMERATE}fps")
        print(f"{'='*60}\n")

        # Create threads for simultaneous recording
        thread0 = threading.Thread(
            target=self.record_camera,
            args=(CAMERA_0_INDEX, self.camera0_file, "camera0")
        )
        thread1 = threading.Thread(
            target=self.record_camera,
            args=(CAMERA_1_INDEX, self.camera1_file, "camera1")
        )

        # Start both threads
        thread0.start()
        thread1.start()

        # Wait for both threads to complete
        thread0.join()
        thread1.join()

        # Check for errors
        if self.recording_errors["camera0"] or self.recording_errors["camera1"]:
            print("\n[ERROR] Recording failed:")
            for camera, error in self.recording_errors.items():
                if error:
                    print(f"  - {camera}: {error}")
            return False

        print("\n[SUCCESS] Both cameras recorded successfully!")
        return True

    def stitch_videos(self):
        """
        Stitch (concatenate) the two MP4 files together.
        Camera 0 video will play first, followed by Camera 1 video.
        """
        print(f"\n{'='*60}")
        print(f"Stitching videos together...")
        print(f"{'='*60}\n")

        # Check if both input files exist
        if not os.path.exists(self.camera0_file):
            print(f"[ERROR] Camera 0 file not found: {self.camera0_file}")
            return False

        if not os.path.exists(self.camera1_file):
            print(f"[ERROR] Camera 1 file not found: {self.camera1_file}")
            return False

        # Create a temporary file list for ffmpeg concat
        concat_file = os.path.join(self.temp_dir, f"concat_{self.timestamp}.txt")

        try:
            # Write file list for ffmpeg concat demuxer
            with open(concat_file, 'w') as f:
                f.write(f"file '{os.path.abspath(self.camera0_file)}'\n")
                f.write(f"file '{os.path.abspath(self.camera1_file)}'\n")

            print(f"[INFO] Concatenating:")
            print(f"  1. {self.camera0_file}")
            print(f"  2. {self.camera1_file}")
            print(f"  -> {self.final_file}\n")

            # Use ffmpeg to concatenate videos
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # Copy without re-encoding for speed
                self.final_file,
                '-y'  # Overwrite output file if exists
            ]

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                print(f"[ERROR] FFmpeg failed:")
                print(result.stderr)
                return False

            print(f"[SUCCESS] Videos stitched successfully!")
            print(f"[OUTPUT] Final video: {self.final_file}")

            # Clean up temporary files
            os.remove(concat_file)
            os.remove(self.camera0_file)
            os.remove(self.camera1_file)

            # Remove temp directory if empty
            try:
                os.rmdir(self.temp_dir)
            except:
                pass

            return True

        except Exception as e:
            print(f"[ERROR] Failed to stitch videos: {str(e)}")
            return False

# ============================================================================
# Main Scanner Class
# ============================================================================

class Scanner:
    """Main scanner class that coordinates motor, camera recording, and captive portal."""

    def __init__(self, duration=RECORDING_DURATION, motor_speed=MOTOR_SPEED,
                 enable_portal=CAPTIVE_PORTAL_ENABLED):
        """
        Initialize the scanner.

        Args:
            duration: Recording duration in seconds
            motor_speed: Motor speed in steps per second
            enable_portal: Enable WiFi captive portal
        """
        self.duration = duration
        self.motor = MotorController(speed=motor_speed)
        self.recorder = DualCameraRecorder(duration=duration, output_dir=OUTPUT_DIR)
        self.portal = None

        if enable_portal:
            self.portal = WiFiCaptivePortal(
                ap_ssid=AP_SSID,
                ap_password=AP_PASSWORD,
                port=WEB_SERVER_PORT
            )

    def run_scan(self):
        """Execute the scanning workflow (motor + cameras)."""
        print("\n" + "="*60)
        print("STARTING SCANNER WORKFLOW")
        print("="*60)

        try:
            # Initialize motor
            self.motor.init_gpio()

            # Start motor
            self.motor.start()

            # Small delay to let motor reach steady state
            time.sleep(0.5)

            # Record from both cameras
            if not self.recorder.record_both_cameras():
                print("\n[FAILED] Recording workflow terminated due to errors.")
                self.motor.stop()
                self.motor.cleanup()
                return False

            # Stop motor
            self.motor.stop()

            # Stitch the videos together
            if not self.recorder.stitch_videos():
                print("\n[FAILED] Video stitching failed.")
                self.motor.cleanup()
                return False

            # Cleanup motor GPIO
            self.motor.cleanup()

            print("\n" + "="*60)
            print("SCAN COMPLETE!")
            print("="*60)
            print(f"Final output: {self.recorder.final_file}\n")

            return True

        except Exception as e:
            print(f"\n[ERROR] Scanner error: {str(e)}")
            try:
                self.motor.stop()
                self.motor.cleanup()
            except:
                pass
            return False

    def run(self):
        """Main run method - starts portal and keeps it running."""
        print("\n" + "="*60)
        print("RASPBERRY PI 5 DUAL CAMERA SCANNER")
        print("="*60)
        print(f"Recording Duration: {self.duration} seconds")
        print(f"Motor Speed: {self.motor.speed} steps/sec")
        print(f"WiFi Portal: {'Enabled' if self.portal else 'Disabled'}")
        print("="*60)

        if self.portal:
            self.portal.start(scanner_instance=self)
            print("\n[INFO] WiFi Captive Portal is running")
            print(f"[INFO] Connect to WiFi: {AP_SSID}")
            print(f"[INFO] Password: {AP_PASSWORD}")
            print("[INFO] A web page should open automatically")
            print("[INFO] Or navigate to: http://192.168.4.1 or http://10.42.0.1")
            print("[INFO] Use the web interface to configure WiFi or start scanning")
            print("[INFO] Press Ctrl+C to exit\n")

            try:
                # Keep running
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.portal.stop()
        else:
            # No portal, just run scan immediately
            return self.run_scan()

    def stop(self):
        """Stop all scanner components."""
        if self.portal:
            self.portal.stop()
        try:
            self.motor.stop()
            self.motor.cleanup()
        except:
            pass

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main function to run the scanner."""
    scanner = None

    try:
        scanner = Scanner(
            duration=RECORDING_DURATION,
            motor_speed=MOTOR_SPEED,
            enable_portal=CAPTIVE_PORTAL_ENABLED
        )
        scanner.run()
        return 0

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Scanner stopped by user.")
        if scanner:
            scanner.stop()
        # Ensure motor is stopped and GPIO cleaned up
        try:
            GPIO.output(STEP_PIN, GPIO.LOW)
            GPIO.output(EN_PIN, GPIO.HIGH)
            GPIO.cleanup()
        except:
            pass
        return 1
    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        if scanner:
            scanner.stop()
        # Ensure motor is stopped and GPIO cleaned up
        try:
            GPIO.output(STEP_PIN, GPIO.LOW)
            GPIO.output(EN_PIN, GPIO.HIGH)
            GPIO.cleanup()
        except:
            pass
        return 1


if __name__ == "__main__":
    exit(main())
