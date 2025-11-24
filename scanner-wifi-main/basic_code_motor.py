#!/usr/bin/env python3
"""
Raspberry Pi 5 Dual Camera Scanner
Records from two Camera Module 3 Wide cameras simultaneously and stitches the videos together.
Raspberry Pi 5 Dual Camera Scanner with Motor Control
Records from two Camera Module 3 Wide cameras simultaneously while spinning the motor,
then stitches the videos together.
"""

import os
@@ -12,18 +13,101 @@
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import RPi.GPIO as GPIO

# ============================================================================
# CONFIGURATION - Modify these variables as needed
# ============================================================================

RECORDING_DURATION = 10  # Duration in seconds for recording
OUTPUT_DIR = "recordings"  # Directory to store recordings
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
@@ -46,13 +130,16 @@ def __init__(self, duration=RECORDING_DURATION, output_dir=OUTPUT_DIR):
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

        # Output filenames
        # Output filenames (temporary files in temp directory)
        self.temp_dir = os.path.join(self.output_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.camera0_file = os.path.join(
            self.output_dir,
            self.temp_dir,
            f"camera0_{self.timestamp}.mp4"
        )
        self.camera1_file = os.path.join(
            self.output_dir,
            self.temp_dir,
            f"camera1_{self.timestamp}.mp4"
        )
        self.final_file = os.path.join(
@@ -167,7 +254,7 @@ def stitch_videos(self):
            return False

        # Create a temporary file list for ffmpeg concat
        concat_file = os.path.join(self.output_dir, f"concat_{self.timestamp}.txt")
        concat_file = os.path.join(self.temp_dir, f"concat_{self.timestamp}.txt")

        try:
            # Write file list for ffmpeg concat demuxer
@@ -207,56 +294,105 @@ def stitch_videos(self):
            print(f"[SUCCESS] Videos stitched successfully!")
            print(f"[OUTPUT] Final video: {self.final_file}")

            # Clean up temporary concat file
            # Clean up temporary files
            os.remove(concat_file)
            os.remove(self.camera0_file)
            os.remove(self.camera1_file)

            # Optionally, keep or remove individual camera files
            print(f"\n[INFO] Individual camera files preserved:")
            print(f"  - {self.camera0_file}")
            print(f"  - {self.camera1_file}")
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
    """Main scanner class that coordinates motor and camera recording."""

    def __init__(self, duration=RECORDING_DURATION, motor_speed=MOTOR_SPEED):
        """
        Initialize the scanner.

        Args:
            duration: Recording duration in seconds
            motor_speed: Motor speed in steps per second
        """
        self.duration = duration
        self.motor = MotorController(speed=motor_speed)
        self.recorder = DualCameraRecorder(duration=duration, output_dir=OUTPUT_DIR)

    def run(self):
        """Execute the complete recording and stitching workflow."""
        """Execute the complete scanning workflow."""
        print("\n" + "="*60)
        print("RASPBERRY PI 5 DUAL CAMERA SCANNER")
        print("RASPBERRY PI 5 DUAL CAMERA SCANNER WITH MOTOR")
        print("="*60)
        print(f"Recording Duration: {self.duration} seconds")
        print(f"Motor Speed: {self.motor.speed} steps/sec")
        print("="*60)

        # Step 1: Record from both cameras
        if not self.record_both_cameras():
            print("\n[FAILED] Recording workflow terminated due to errors.")
            return False
        try:
            # Initialize motor
            self.motor.init_gpio()

        # Step 2: Stitch the videos together
        if not self.stitch_videos():
            print("\n[FAILED] Video stitching failed.")
            return False
            # Start motor
            self.motor.start()

        print("\n" + "="*60)
        print("WORKFLOW COMPLETE!")
        print("="*60)
        print(f"Final output: {self.final_file}\n")
            # Small delay to let motor reach steady state
            time.sleep(0.5)

        return True
            # Record from both cameras (this will run for the duration)
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
            print("WORKFLOW COMPLETE!")
            print("="*60)
            print(f"Final output: {self.recorder.final_file}\n")

            return True

        except Exception as e:
            print(f"\n[ERROR] Scanner error: {str(e)}")
            self.motor.stop()
            self.motor.cleanup()
            return False

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main function to run the dual camera scanner."""
    """Main function to run the scanner."""
    try:
        recorder = DualCameraRecorder(
        scanner = Scanner(
            duration=RECORDING_DURATION,
            output_dir=OUTPUT_DIR
            motor_speed=MOTOR_SPEED
        )
        success = recorder.run()
        success = scanner.run()

        if success:
            print("[DONE] Scanner completed successfully!")
@@ -267,11 +403,25 @@ def main():

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Scanner stopped by user.")
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
        # Ensure motor is stopped and GPIO cleaned up
        try:
            GPIO.output(STEP_PIN, GPIO.LOW)
            GPIO.output(EN_PIN, GPIO.HIGH)
            GPIO.cleanup()
        except:
            pass
        return 1