#!/usr/bin/env python3
"""
Raspberry Pi 5 Dual Camera Scanner with Motor Control
Records from two Camera Module 3 Wide cameras simultaneously while spinning the motor,
then stitches the videos together.
"""

import os
import time
import threading
from datetime import datetime
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
from libcamera import Transform
import RPi.GPIO as GPIO
import socket
import subprocess
import shlex

# Global abort event for scan cancellation
abort_scan = threading.Event()


# CONFIGURATION 
# ============================================================================

RECORDING_DURATION = 70  # Duration in seconds for recording
OUTPUT_DIR = "recordings"  # Directory to store recordings

# Motor Settings
MOTOR_SPEED = 200  # Motor speed in steps per second

# Motor Pin 
STEP_PIN = 17   # PUL- on DM542
DIR_PIN  = 27   # DIR- on DM542
# EN_PIN not used motor driver enable is hardwired

# Start button
BUTTON_PIN = 23  

# RGB LED Pin Configuration
LED_RED = 15    
LED_GREEN = 24  
LED_BLUE = 22   

# Camera Settings
RESOLUTION = (1920, 1080)  # Video resolution
FRAMERATE = 30  # Frames per second
CAMERA_0_INDEX = 0
CAMERA_1_INDEX = 1


# Network Check Functions
# ============================================================================

def check_internet_connection():
    """Check if there's an active internet connection."""
    try:
        # Try to connect
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        pass

    try:
        # Try to ping google.com
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "google.com"],
            capture_output=True,
            timeout=3
        )
        return result.returncode == 0
    except:
        return False


# MacBook File Transfer Functions (Used for testing)
# ============================================================================

def load_macbook_config():
    """Load MacBook transfer configuration from secure config file."""
    config_file = os.path.expanduser("~/.macbook_transfer_config")
    config = {}

    try:
        if not os.path.exists(config_file):
            print(f"[WARNING] MacBook config file not found: {config_file}")
            return None

        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"').strip("'")
                    config[key] = value

        # Validate required fields
        required = ['MACBOOK_USER', 'MACBOOK_IP', 'MACBOOK_PASSWORD', 'MACBOOK_DEST_DIR']
        for field in required:
            if field not in config:
                print(f"[ERROR] Missing required field in config: {field}")
                return None

        return config
    except Exception as e:
        print(f"[ERROR] Failed to load MacBook config: {e}")
        return None

def transfer_to_macbook(file_path):
    """Transfer a file to MacBook via SCP."""
    print("\n[TRANSFER] Initiating file transfer to MacBook...")

    # Load configuration
    config = load_macbook_config()
    if not config:
        print("[ERROR] Cannot transfer file - MacBook configuration not available")
        return False

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return False

    file_size = os.path.getsize(file_path)
    print(f"[TRANSFER] File: {file_path}")
    print(f"[TRANSFER] Size: {file_size / 1024 / 1024:.2f} MB")
    print(f"[TRANSFER] Destination: {config['MACBOOK_USER']}@{config['MACBOOK_IP']}:{config['MACBOOK_DEST_DIR']}")

    try:
        # Build SCP command using sshpass for password authentication
        cmd = [
            'sshpass',
            '-p', config['MACBOOK_PASSWORD'],
            'scp',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            file_path,
            f"{config['MACBOOK_USER']}@{config['MACBOOK_IP']}:{config['MACBOOK_DEST_DIR']}/"
        ]

        print("[TRANSFER] Starting transfer...")
        start_time = time.time()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for large files
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"[SUCCESS] File transferred successfully in {elapsed:.1f} seconds!")
            print(f"[INFO] File saved to MacBook at: {config['MACBOOK_DEST_DIR']}/{os.path.basename(file_path)}")
            return True
        else:
            print(f"[ERROR] Transfer failed with return code {result.returncode}")
            if result.stderr:
                print(f"[ERROR] {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("[ERROR] Transfer timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Transfer failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# LED Status Controller
# ============================================================================

class LEDController:
    """Handles RGB LED status indicators."""

    def __init__(self):
        self.pwm_red = None
        self.pwm_green = None
        self.pwm_blue = None
        self.blink_thread = None
        self.blinking = False

    def init_gpio(self):
        """Initialize LED GPIO pins with PWM."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(LED_RED, GPIO.OUT)
        GPIO.setup(LED_GREEN, GPIO.OUT)
        GPIO.setup(LED_BLUE, GPIO.OUT)

        # Setup PWM at 1000 Hz
        self.pwm_red = GPIO.PWM(LED_RED, 1000)
        self.pwm_green = GPIO.PWM(LED_GREEN, 1000)
        self.pwm_blue = GPIO.PWM(LED_BLUE, 1000)

        # Start all off (100% for common anode = off)
        self.pwm_red.start(100)
        self.pwm_green.start(100)
        self.pwm_blue.start(100)

        print("[LED] Initialized")

    def set_color(self, r, g, b):
        """
        Set LED color using PWM duty cycle (0-100).
        For common ANODE LED: 0 = full brightness, 100 = off
        r, g, b: 0 = full brightness, 100 = off
        """
        self.stop_blinking()
        if self.pwm_red and self.pwm_green and self.pwm_blue:
            # Invert for common anode: 100-value
            self.pwm_red.ChangeDutyCycle(100 - r)
            self.pwm_green.ChangeDutyCycle(100 - g)
            self.pwm_blue.ChangeDutyCycle(100 - b)

    def green(self):
        """Set LED to green (ready status)."""
        self.set_color(0, 100, 0)  # R=0 (off), G=100 (on), B=0 (off)
        print("[LED] Status: GREEN (Ready)")

    def blue(self):
        """Set LED to blue (scanning status)."""
        self.set_color(0, 0, 100)  # R=0 (off), G=0 (off), B=100 (on)
        print("[LED] Status: BLUE (Scanning)")

    def red(self):
        """Set LED to solid red (error status)."""
        self.set_color(100, 0, 0)  # R=100 (on), G=0 (off), B=0 (off)
        print("[LED] Status: RED (Error)")

    def _blink_red_loop(self):
        """Internal method for blinking red LED."""
        while self.blinking:
            if self.pwm_red:
                # Common anode: 0 = on, 100 = off
                self.pwm_red.ChangeDutyCycle(0)    # Red ON
                self.pwm_green.ChangeDutyCycle(100)  # Green OFF
                self.pwm_blue.ChangeDutyCycle(100)   # Blue OFF
            time.sleep(0.5)
            if self.blinking and self.pwm_red:
                self.pwm_red.ChangeDutyCycle(100)  # Red OFF
            time.sleep(0.5)

    def blink_red(self):
        """Start blinking red LED (network error status)."""
        self.stop_blinking()
        self.blinking = True
        self.blink_thread = threading.Thread(target=self._blink_red_loop, daemon=True)
        self.blink_thread.start()
        print("[LED] Status: BLINKING RED (Network Error)")

    def stop_blinking(self):
        """Stop any blinking operation."""
        if self.blinking:
            self.blinking = False
            if self.blink_thread:
                self.blink_thread.join(timeout=1.5)

    def off(self):
        """Turn off LED."""
        self.set_color(0, 0, 0)  # All 0 = all off (inverted to 100 internally)

    def cleanup(self):
        """Clean up LED resources."""
        self.stop_blinking()
        try:
            if self.pwm_red:
                self.pwm_red.stop()
        except:
            pass
        try:
            if self.pwm_green:
                self.pwm_green.stop()
        except:
            pass
        try:
            if self.pwm_blue:
                self.pwm_blue.stop()
        except:
            pass
        print("[LED] Cleaned up")


# Button Control Functions
# ============================================================================

def button_abort_callback(channel):
    """Callback function for button press during scanning to abort."""
    # Verify it's a real button press not noise
    time.sleep(0.05)  # Brief delay for debounce

    # Check if button is actually pressed
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
        if not abort_scan.is_set():  # Only trigger once
            print("\n[BUTTON] ABORT button pressed! Canceling scan...")
            abort_scan.set()

def init_button():
    """Initialize button GPIO with pull-up resistor."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print(f"[BUTTON] Initialized on GPIO {BUTTON_PIN}")

def wait_for_button_press():
    """Wait for button press with improved debouncing to avoid false triggers."""
    print(f"\n[BUTTON] Waiting for button press on GPIO {BUTTON_PIN}...")
    print("[BUTTON] Press the button to start scanning...")

    while True:
        # Wait for button press (LOW when pressed, due to pull-up)
        GPIO.wait_for_edge(BUTTON_PIN, GPIO.FALLING)

        # Debounce delay
        time.sleep(0.1)

        # Verify button is still pressed (not just noise/glitch)
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            # Wait a bit longer to ensure it's a wanted press
            time.sleep(0.05)

            # Double check it's still pressed
            if GPIO.input(BUTTON_PIN) == GPIO.LOW:
                print("[BUTTON] Button pressed! Starting scan...\n")

                # Wait for button release to avoid immediate re-trigger
                while GPIO.input(BUTTON_PIN) == GPIO.LOW:
                    time.sleep(0.05)
                time.sleep(0.1)  # Small delay after release

                return
            else:
                print("[BUTTON] False trigger detected, ignoring...")
        else:
            print("[BUTTON] False trigger detected, ignoring...")

def enable_abort_button():
    """Enable button interrupt for aborting during scan."""
    abort_scan.clear()  # Clear any previous abort signal
    try:
        GPIO.remove_event_detect(BUTTON_PIN)  # Remove any existing detection
    except RuntimeError:
        pass

    # Add a small delay to ensure GPIO is ready
    time.sleep(0.1)

    # Increased bouncetime to 500ms to reduce false triggers from motor noise
    GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=button_abort_callback, bouncetime=500)
    print("[BUTTON] Abort feature enabled - press button to cancel scan")
    print("[BUTTON] Abort status: Ready to detect button press")

def disable_abort_button():
    """Disable button interrupt after scan."""
    try:
        GPIO.remove_event_detect(BUTTON_PIN)
        print("[BUTTON] Abort feature disabled")
    except RuntimeError:
        pass


# Motor Control Class
# ============================================================================

class MotorController:
    """Handles stepper motor control during recording."""

    def __init__(self, speed=MOTOR_SPEED):
        self.speed = speed
        self.running = False
        self.step_delay = 1.0 / (2 * self.speed)
        self.motor_thread = None

    def init_gpio(self):
        """Initialize GPIO pins for motor control."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(STEP_PIN, GPIO.OUT)
        GPIO.setup(DIR_PIN, GPIO.OUT)

        GPIO.output(STEP_PIN, GPIO.LOW)
        GPIO.output(DIR_PIN, GPIO.LOW)

    def cleanup(self):
        """Clean up GPIO resources."""
        GPIO.output(STEP_PIN, GPIO.LOW)
        

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


# Camera Recording Class
# ============================================================================

class DualCameraRecorder:
    """Handles recording from two cameras simultaneously."""

    def __init__(self, duration=RECORDING_DURATION, output_dir=OUTPUT_DIR):
        self.duration = duration
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create output directory structure
        os.makedirs(self.output_dir, exist_ok=True)
        self.temp_dir = os.path.join(self.output_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        # Output filenames
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
            f"stitched_{self.timestamp}.mp4"
        )

    def record_both_cameras(self):
        """Record from both cameras simultaneously for the specified duration."""
        print("\n[RECORDING] Initializing cameras...")

        picam0 = None
        picam1 = None

        try:
            # Initialize cameras
            picam0 = Picamera2(CAMERA_0_INDEX)
            picam1 = Picamera2(CAMERA_1_INDEX)

            # Configure cameras
            config0 = picam0.create_video_configuration(
                main={"size": RESOLUTION, "format": "RGB888"},
                encode="main",
                transform=Transform(hflip=True, vflip=True)  # Rotate 180 degrees
            )
            config1 = picam1.create_video_configuration(
                main={"size": RESOLUTION, "format": "RGB888"},
                encode="main"
            )

            picam0.configure(config0)
            picam1.configure(config1)

            # Setup encoders
            encoder0 = H264Encoder(bitrate=10000000)
            encoder1 = H264Encoder(bitrate=10000000)

            # Setup outputs
            output0 = FfmpegOutput(self.camera0_file)
            output1 = FfmpegOutput(self.camera1_file)

            print(f"[RECORDING] Starting {self.duration} second recording...")
            print(f"  Camera 0: {self.camera0_file}")
            print(f"  Camera 1: {self.camera1_file}")

            # Start recording on both cameras
            picam0.start_recording(encoder0, output0)
            picam1.start_recording(encoder1, output1)

            # Wait for the full duration or abort signal
            start_time = time.time()
            while (time.time() - start_time) < self.duration:
                # Check for abort signal
                if abort_scan.is_set():
                    print("\n[RECORDING] ABORT DETECTED! Stopping recording...")
                    break

                elapsed = time.time() - start_time
                remaining = self.duration - elapsed
                # Show abort status in recording progress (for debugging)
                abort_status = " [ABORT ARMED]" if not abort_scan.is_set() else " [ABORTING...]"
                print(f"\r[RECORDING] Time: {elapsed:.1f}s / {self.duration}s (Remaining: {remaining:.1f}s){abort_status}", end='', flush=True)
                time.sleep(1)

            if not abort_scan.is_set():
                print("\n[RECORDING] Stopping recording...")
            else:
                print("[RECORDING] Recording aborted by user")

            # Stop recording
            picam0.stop_recording()
            picam1.stop_recording()

            # Close cameras
            picam0.close()
            picam1.close()

            if abort_scan.is_set():
                print("[ABORTED] Recording stopped by user.")
                return False
            else:
                print("[SUCCESS] Recording completed!")
                return True

        except Exception as e:
            print(f"\n[ERROR] Recording failed: {str(e)}")
            import traceback
            traceback.print_exc()

            # Cleanup on error
            try:
                if picam0:
                    picam0.stop_recording()
                    picam0.close()
            except:
                pass

            try:
                if picam1:
                    picam1.stop_recording()
                    picam1.close()
            except:
                pass

            return False

    def stitch_videos(self):
        """Concatenate videos sequentially (camera 0 then camera 1)."""
        print("\n[STITCHING] Concatenating videos sequentially...")

        concat_file = os.path.join(self.temp_dir, f"concat_{self.timestamp}.txt")

        try:
            # Check if input files exist
            if not os.path.exists(self.camera0_file):
                print(f"[ERROR] Camera 0 file not found: {self.camera0_file}")
                return False
            if not os.path.exists(self.camera1_file):
                print(f"[ERROR] Camera 1 file not found: {self.camera1_file}")
                return False

            # Check file sizes
            size0 = os.path.getsize(self.camera0_file)
            size1 = os.path.getsize(self.camera1_file)
            print(f"[INFO] Camera 0 file size: {size0 / 1024 / 1024:.2f} MB")
            print(f"[INFO] Camera 1 file size: {size1 / 1024 / 1024:.2f} MB")

            if size0 == 0 or size1 == 0:
                print("[ERROR] One or both video files are empty!")
                return False

            # Write file list for ffmpeg concat demuxer
            with open(concat_file, 'w') as f:
                f.write(f"file '{os.path.abspath(self.camera0_file)}'\n")
                f.write(f"file '{os.path.abspath(self.camera1_file)}'\n")

            print(f"[INFO] Concat file created: {concat_file}")

            # Use ffmpeg concat demuxer for sequential concatenation
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # Just copy streams no re-encoding
                self.final_file
            ]

            print("[STITCHING] Running ffmpeg command...")
            print(f"[CMD] {' '.join(cmd)}")

            import subprocess
            
            # Run with timeout and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                print(f"[ERROR] ffmpeg failed with return code {result.returncode}")
                print(f"[STDERR] {result.stderr}")
                return False

            # Verify output file was created
            if not os.path.exists(self.final_file):
                print(f"[ERROR] Output file was not created: {self.final_file}")
                return False

            output_size = os.path.getsize(self.final_file)
            print(f"[SUCCESS] Videos concatenated successfully!")
            print(f"[OUTPUT] Final video: {self.final_file}")
            print(f"[OUTPUT] File size: {output_size / 1024 / 1024:.2f} MB")
            print(f"[INFO] Total duration: ~{self.duration * 2} seconds (camera 0 + camera 1)")

            # Clean up temporary files
            print("[CLEANUP] Removing temporary files...")
            os.remove(concat_file)
            os.remove(self.camera0_file)
            os.remove(self.camera1_file)

            # Remove temp directory if empty
            try:
                os.rmdir(self.temp_dir)
                print("[CLEANUP] Removed temp directory")
            except:
                pass

            return True

        except subprocess.TimeoutExpired:
            print("[ERROR] ffmpeg timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to concatenate videos: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        


# Main Scanner Class
# ============================================================================

class Scanner:
    """Main scanner class that coordinates motor, camera recording, and LED status."""

    def __init__(self, duration=RECORDING_DURATION, motor_speed=MOTOR_SPEED, led_controller=None):
        self.duration = duration
        self.motor = MotorController(speed=motor_speed)
        self.recorder = DualCameraRecorder(duration=duration, output_dir=OUTPUT_DIR)
        self.led = led_controller  # Use shared LED controller

    def run(self):
        """Execute the complete scanning workflow."""
        print("\n" + "="*60)
        print("RASPBERRY PI 5 DUAL CAMERA SCANNER WITH MOTOR")
        print("="*60)
        print(f"Recording Duration: {self.duration} seconds")
        print(f"Motor Speed: {self.motor.speed} steps/sec")
        print("="*60)

        try:
            # Initialize motor
            self.motor.init_gpio()

            # Enable abort button
            enable_abort_button()

            # Set LED to blue - starting scan
            self.led.blue()

            # Start motor
            self.motor.start()

            # Small delay to let motor reach steady state
            time.sleep(0.5)

            # Record from both cameras 
            recording_success = self.recorder.record_both_cameras()

            # Stop motor
            self.motor.stop()

            # Disable abort button
            disable_abort_button()

            # Check if scan was aborted
            if abort_scan.is_set():
                print("\n[ABORTED] Scan was canceled by user.")
                self.led.red()  # Show abort status with red LED
                time.sleep(3)   # Keep abort status visible
                print("[INFO] Transitioning to ready state...")
                self.led.green()  # Transition to green to show ready again
                time.sleep(2)   # Show ready state
                self.motor.cleanup()
                return False

            # Check if recording failed
            if not recording_success:
                print("\n[FAILED] Recording workflow terminated due to errors.")
                self.led.red()  # Show error status
                time.sleep(3)   # Keep error visible
                print("[INFO] Transitioning to ready state...")
                self.led.green()  # Transition to green to show ready again
                time.sleep(2)   # Show ready state
                self.motor.cleanup()
                return False

            # Stitch the videos together
            if not self.recorder.stitch_videos():
                print("\n[FAILED] Video stitching failed.")
                self.led.red()  
                time.sleep(3)   
                print("[INFO] Transitioning to ready state...")
                self.led.green()  
                time.sleep(2)  
                self.motor.cleanup()
                return False

            # Transfer file to MacBook (Testing Purposes)
            print("\n[INFO] Transferring file to MacBook...")
            transfer_success = transfer_to_macbook(self.recorder.final_file)

            if transfer_success:
                print("[SUCCESS] File successfully transferred to MacBook!")
            else:
                print("[WARNING] File transfer to MacBook failed, but recording was successful.")
                print(f"[INFO] File is still available locally at: {self.recorder.final_file}")

            # Cleanup motor GPIO
            self.motor.cleanup()

            # Set LED to green
            self.led.green()

            print("\n" + "="*60)
            print("WORKFLOW COMPLETE!")
            print("="*60)
            print(f"Final output: {self.recorder.final_file}")
            if transfer_success:
                print(f"MacBook copy: ~/Documents/rpiTransfer/{os.path.basename(self.recorder.final_file)}\n")
            else:
                print()

            # Keep green LED on for a moment
            time.sleep(2)

            return True

        except Exception as e:
            print(f"\n[ERROR] Scanner error: {str(e)}")
            disable_abort_button()  # Make sure to disable abort on error
            self.led.red()  
            time.sleep(3)   
            print("[INFO] Transitioning to ready state...")
            self.led.green()  
            time.sleep(2)   
            self.motor.stop()
            self.motor.cleanup()
            return False


# Main
# ============================================================================

def main():
    """Main function to run the scanner in continuous loop mode."""
    led = None
    try:
        # Initialize LED once at startup
        led = LEDController()
        led.init_gpio()

        # Initialize button once at startup
        init_button()

        print("\n" + "="*60)
        print("SCANNER READY - CONTINUOUS MODE")
        print("Press Ctrl+C to exit")
        print("="*60)

        # Main continuous loop
        while True:
            try:
                # Check network connection and wait until established
                print("\n[NETWORK] Checking internet connection...")
                while not check_internet_connection():
                    print("[WARNING] No internet connection detected! Waiting for connection...")
                    led.blink_red()
                    time.sleep(5)  # Wait 5 seconds before checking again
                    print("[NETWORK] Rechecking internet connection...")

                # Internet is connected
                print("[SUCCESS] Internet connection established!")

                # Set LED to green
                led.green()

                # Wait for button press to start
                wait_for_button_press()

                # Create and run scanner (pass shared LED controller)
                scanner = Scanner(
                    duration=RECORDING_DURATION,
                    motor_speed=MOTOR_SPEED,
                    led_controller=led
                )
                success = scanner.run()

                if success:
                    print("[DONE] Scanner completed successfully!")
                    print("[INFO] Ready for next scan...")
                else:
                    print("[FAILED] Scanner completed with errors.")
                    print("[INFO] Ready for next scan...")

                # Brief pause before next cycle
                time.sleep(1)

            except Exception as scan_error:
                print(f"\n[ERROR] Scan error: {str(scan_error)}")
                import traceback
                traceback.print_exc()

                # Show error on LED
                try:
                    led.red()
                    time.sleep(3)
                except:
                    pass
                print("[INFO] Restarting cycle...")
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Scanner stopped by user.")
        try:
            if led:
                led.cleanup()
            try:
                GPIO.output(STEP_PIN, GPIO.LOW)
            except:
                pass
            GPIO.cleanup()
        except:
            pass
        return 0

    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            if led:
                try:
                    led.red()
                    time.sleep(2)
                except:
                    pass
                led.cleanup()
            try:
                GPIO.output(STEP_PIN, GPIO.LOW)
            except:
                pass
            GPIO.cleanup()
        except:
            pass
        return 1

if __name__ == "__main__":
    exit(main())