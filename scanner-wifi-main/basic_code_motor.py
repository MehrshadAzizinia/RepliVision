#!/usr/bin/env python3
"""
Raspberry Pi 5 Dual Camera Scanner with Motor Control
Records from two Camera Module 3 Wide cameras simultaneously while spinning the motor,
then stitches the videos together.
"""

import os
import time
import threading
import subprocess
from datetime import datetime
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import RPi.GPIO as GPIO

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

            # Start motor
            self.motor.start()

            # Small delay to let motor reach steady state
            time.sleep(0.5)

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
    """Main function to run the scanner."""
    try:
        scanner = Scanner(
            duration=RECORDING_DURATION,
            motor_speed=MOTOR_SPEED
        )
        success = scanner.run()

        if success:
            print("[DONE] Scanner completed successfully!")
            return 0
        else:
            print("[DONE] Scanner completed with errors.")
            return 1

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


if __name__ == "__main__":
    exit(main())
