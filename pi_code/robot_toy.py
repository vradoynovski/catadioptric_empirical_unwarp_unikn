# robot_toy.py
# Run on the Pi via SSH. Control with WASD + Q/E to turn, X to stop, ESC to quit.

import os
import sys
import threading
import time
import tty
import termios
from datetime import datetime
import cv2
import RPi.GPIO as GPIO
import Adafruit_PCA9685

# ── Motor setup ─────────────────────────────────────────────────────────────
pwm = Adafruit_PCA9685.PCA9685()
pwm.set_pwm_freq(60)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

IN1, IN2 = 23, 24
IN3, IN4 = 27, 22
ENA, ENB = 0, 1

for pin in (IN1, IN2, IN3, IN4):
    GPIO.setup(pin, GPIO.OUT)

# ── Speed constants ──────────────────────────────────────────────────────────
DRIVE_SPEED = 1600   # PWM value for both wheels when going straight
TURN_SPEED  = 1600   # outer wheel speed when turning
SPIN_SPEED  = 1600   # each wheel speed when spinning in place

# ── Low-level motor primitives ───────────────────────────────────────────────
def _set_motors(left, right):
    """Positive = forward, negative = backward, 0 = stop."""
    GPIO.output(IN1, GPIO.HIGH if left  < 0 else GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW  if left  < 0 else GPIO.HIGH)
    GPIO.output(IN3, GPIO.HIGH if right < 0 else GPIO.LOW)
    GPIO.output(IN4, GPIO.LOW  if right < 0 else GPIO.HIGH)
    pwm.set_pwm(ENA, 0, abs(int(left)))
    pwm.set_pwm(ENB, 0, abs(int(right)))

def stop():
    for pin in (IN1, IN2, IN3, IN4):
        GPIO.output(pin, GPIO.LOW)
    pwm.set_pwm(ENA, 0, 0)
    pwm.set_pwm(ENB, 0, 0)

# ── Commands ─────────────────────────────────────────────────────────────────
COMMANDS = {
    'w': ('Forward',        lambda: _set_motors( DRIVE_SPEED,  DRIVE_SPEED)),
    's': ('Backward',       lambda: _set_motors(-DRIVE_SPEED, -DRIVE_SPEED)),
    'a': ('Arc left',       lambda: _set_motors( TURN_SPEED // 2,  TURN_SPEED)),
    'd': ('Arc right',      lambda: _set_motors( TURN_SPEED,  TURN_SPEED // 2)),
    'q': ('Spin left',      lambda: _set_motors(-SPIN_SPEED,  SPIN_SPEED)),
    'e': ('Spin right',     lambda: _set_motors( SPIN_SPEED, -SPIN_SPEED)),
    'x': ('Stop',           stop),
}
QUIT_KEY = '\x1b'  # ESC
RECORD_KEY = 'r'

# ── Video recording ──────────────────────────────────────────────────────────
CAM_INDEX = 0
REC_DIR   = "recordings"

class Recorder:
    """Toggle raw camera recording to REC_DIR/rec_<timestamp>.avi in a background thread."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()

    @property
    def active(self):
        return self._thread is not None

    def toggle(self):
        if self.active:
            self.stop()
        else:
            self.start()

    def start(self):
        os.makedirs(REC_DIR, exist_ok=True)
        path = os.path.join(REC_DIR, datetime.now().strftime("rec_%Y%m%d_%H%M%S.avi"))
        cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(CAM_INDEX)
        if not cap.isOpened():
            print("  Recording failed: could not open camera")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(cap, path), daemon=True)
        self._thread.start()
        print(f"  Recording -> {path}")

    def stop(self):
        if not self.active:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None
        print("  Recording stopped")

    def _run(self, cap, path):
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if fps and fps > 0 else 30.0
        writer = None
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.005)
                    continue
                if writer is None:
                    h, w = frame.shape[:2]
                    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
                writer.write(frame)
        finally:
            if writer is not None:
                writer.release()
            cap.release()

# ── Raw key capture ──────────────────────────────────────────────────────────
def get_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ── Main loop ────────────────────────────────────────────────────────────────
def main():
    print("Robot toy controller")
    print("  W/S  — forward / backward")
    print("  A/D  — arc left / right")
    print("  Q/E  — spin left / right in place")
    print("  X    — stop")
    print("  R    — start / stop video recording")
    print("  ESC  — quit")
    print()

    recorder = Recorder()
    try:
        while True:
            key = get_key().lower()

            if key == QUIT_KEY:
                print("\nQuitting.")
                break

            if key == RECORD_KEY:
                recorder.toggle()
                continue

            if key in COMMANDS:
                label, action = COMMANDS[key]
                print(f"  {label}")
                action()
            # ignore any other keys silently

    finally:
        recorder.stop()
        stop()
        GPIO.cleanup()

if __name__ == '__main__':
    main()
