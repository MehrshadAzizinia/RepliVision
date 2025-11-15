#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time
import sys
import termios
import tty
import select

# ---------- PIN SETUP (change these if needed) ----------
STEP_PIN = 17   # PUL- on DM542
DIR_PIN  = 27   # DIR- on DM542
EN_PIN   = 22   # ENA- on DM542 (optional)

# ---------- SPEED SETTINGS ----------
# steps per second (approx, python is not real-time)
MIN_SPEED = 50      # slowest
MAX_SPEED = 2000    # fastest
speed = 400         # <-- default speed (modifiable variable)

running = False
direction = 1       # 1 = one direction, -1 = other

step_delay = 1.0 / (2 * speed)  # time between step edges
last_step_time = time.perf_counter()
step_state = False

def update_step_delay():
    global step_delay
    # each step consists of HIGH + LOW -> frequency = speed
    step_delay = 1.0 / (2 * speed)

def init_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(STEP_PIN, GPIO.OUT)
    GPIO.setup(DIR_PIN, GPIO.OUT)
    GPIO.setup(EN_PIN, GPIO.OUT)

    GPIO.output(STEP_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)

    # Enable driver (depends on DM542 config; often LOW = enabled)
    GPIO.output(EN_PIN, GPIO.LOW)

def cleanup():
    GPIO.output(STEP_PIN, GPIO.LOW)
    GPIO.output(EN_PIN, GPIO.HIGH)  # disable driver (if active-low)
    GPIO.cleanup()

def set_direction(dir_val):
    global direction
    direction = dir_val
    # HIGH/LOW decides direction; flip if it runs opposite to what you expect
    GPIO.output(DIR_PIN, GPIO.HIGH if direction > 0 else GPIO.LOW)

def get_key_nonblocking():
    """Return a single character if pressed, else None (non-blocking)."""
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr:
        return sys.stdin.read(1)
    return None

def main():
    global running, speed, last_step_time, step_state

    init_gpio()
    set_direction(1)
    update_step_delay()

    # Set terminal to cbreak mode so we get keypresses instantly
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    print("Controls:")
    print("  SPACE : start/stop")
    print("  d     : toggle direction")
    print("  w     : increase speed")
    print("  s     : decrease speed")
    print("  q     : quit")
    print(f"Initial speed: {speed} steps/sec")

    try:
        while True:
            now = time.perf_counter()

            # Step generation
            if running and (now - last_step_time) >= step_delay:
                last_step_time = now
                step_state = not step_state
                GPIO.output(STEP_PIN, GPIO.HIGH if step_state else GPIO.LOW)

            # Keyboard handling
            ch = get_key_nonblocking()
            if ch:
                if ch == ' ':
                    running = not running
                    print("Running:" if running else "Stopped")
                elif ch == 'd':
                    set_direction(-direction)
                    print("Direction changed")
                elif ch == 'w':
                    speed = min(speed + 100, MAX_SPEED)
                    update_step_delay()
                    print(f"Speed: {speed} steps/sec")
                elif ch == 's':
                    speed = max(speed - 100, MIN_SPEED)
                    update_step_delay()
                    print(f"Speed: {speed} steps/sec")
                elif ch == 'q':
                    print("Quitting...")
                    break

            # small sleep to avoid 100% CPU
            time.sleep(0.0005)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        cleanup()

if __name__ == "__main__":
    main()
