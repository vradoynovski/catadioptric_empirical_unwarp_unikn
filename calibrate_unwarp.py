"""
Interactive unwarp calibration tool.

Usage:
    python calibrate_unwarp.py <video_or_image>

Controls:
    Trackbars : adjust cx, cy, inner_r, outer_r, p
    H key     : run Hough circle detection to auto-initialize outer circle + center
    A / D     : previous / next frame
    S key     : save current values to unwarp_cfg.json
    Q key     : quit without saving
"""

import cv2
import json
import numpy as np
import sys
from pathlib import Path

CFG_PATH    = "unwarp_cfg.json"
WINDOW_RAW  = "Raw  (H=Hough  S=Save  Q=Quit  </>=frame)"
WINDOW_PANO = "Unwarp preview"
PANEL_W     = 380   # width of the labelled value panel next to the raw image

# ── load source ──────────────────────────────────────────────────────────────
src = sys.argv[1] if len(sys.argv) > 1 else None
assert src, "Usage: python calibrate_unwarp.py <video_or_image>"

cap = None
frames = []
frame_idx = 0

path = Path(src)
if path.suffix.lower() in (".mp4", ".avi", ".mov", ".mkv"):
    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened(), f"Cannot open {src}"
    # sample up to 300 evenly spaced frames for navigation
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step  = max(1, total // 300)
    for i in range(0, total, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, f = cap.read()
        if ret:
            frames.append(f)
    cap.release()
else:
    frames = [cv2.imread(str(path))]
    assert frames[0] is not None, f"Cannot read {src}"

H_raw, W_raw = frames[0].shape[:2]

# ── load existing config or defaults ─────────────────────────────────────────
defaults = {
    "x1": 0, "y1": 0, "x2": W_raw, "y2": H_raw,
    "inner_radius": 30, "outer_radius": min(H_raw, W_raw) // 2,
    "output_width": 1300, "output_height": 200,
    "p": 1.0, "angle_offset": -1.5707963267948966,
}
if Path(CFG_PATH).exists():
    with open(CFG_PATH) as f:
        saved = json.load(f)
    defaults.update(saved)

# center of the cropped region
crop_cx = (defaults["x1"] + defaults["x2"]) // 2
crop_cy = (defaults["y1"] + defaults["y2"]) // 2

# ── trackbar state ────────────────────────────────────────────────────────────
TB_MAX = {"cx": W_raw, "cy": H_raw, "inner_r": 300, "outer_r": 600, "p100": 200, "out_w": 3000, "out_h": 400}

state = {
    "cx":      crop_cx,
    "cy":      crop_cy,
    "inner_r": defaults["inner_radius"],
    "outer_r": defaults["outer_radius"],
    "p100":    int(defaults.get("p", 1.0) * 100),
    "out_w":   defaults.get("output_width", 900),
    "out_h":   defaults.get("output_height", 150),
}

# ── helpers ───────────────────────────────────────────────────────────────────
def unwrap_preview(frame, cx, cy, r_in, r_out, p, W_out=900, H_out=150, out_h=None):
    H_out = out_h if out_h and out_h > 0 else H_out
    angle_offset = -np.pi / 2
    r_norm = np.linspace(1.0, 0.0, H_out, dtype=np.float32)
    r_corr = r_in + (r_norm ** p) * (r_out - r_in)
    theta  = np.linspace(0, 2 * np.pi, W_out, endpoint=False, dtype=np.float32) - angle_offset
    map_x  = (cx + r_corr[:, None] * np.cos(theta)[None, :]).astype(np.float32)
    map_y  = (cy + r_corr[:, None] * np.sin(theta)[None, :]).astype(np.float32)
    pano   = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return cv2.flip(pano, 1)


def draw_overlay(frame, cx, cy, r_in, r_out, p, out_w, out_h, frame_no, frame_total):
    vis = frame.copy()
    cv2.circle(vis, (cx, cy), r_out, (0, 255, 0), 2)
    cv2.circle(vis, (cx, cy), r_in,  (0, 0, 255), 2)
    cv2.drawMarker(vis, (cx, cy), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)

    x1 = max(0, cx - r_out)
    y1 = max(0, cy - r_out)
    x2 = min(frame.shape[1], cx + r_out)
    y2 = min(frame.shape[0], cy + r_out)

    # One line per trackbar, in slider order, so the sliders can be matched
    # to their meaning even when the backend doesn't render trackbar labels.
    lines = [
        (f"1  cx       {cx:>5}   center x",                    (235, 235, 235)),
        (f"2  cy       {cy:>5}   center y",                    (235, 235, 235)),
        (f"3  inner_r  {r_in:>5}   red circle",                (90, 90, 255)),
        (f"4  outer_r  {r_out:>5}   green circle",             (90, 230, 90)),
        (f"5  p x100   {int(round(p * 100)):>5}   radial warp", (235, 235, 235)),
        (f"6  out_w    {out_w:>5}   pano width",               (235, 235, 235)),
        (f"7  out_h    {out_h:>5}   pano height",              (235, 235, 235)),
        (f"crop  {x1},{y1} - {x2},{y2}",                       (150, 150, 150)),
        (f"frame {frame_no}/{frame_total}   A/D = prev/next",  (150, 150, 150)),
    ]
    # Side panel next to the image instead of text on top of it, so the
    # picture stays clear while aligning the circles.
    panel_h = max(vis.shape[0], 40 + len(lines) * 28)
    panel = np.full((panel_h, PANEL_W, 3), 35, np.uint8)
    for i, (text, color) in enumerate(lines):
        cv2.putText(panel, text, (12, 28 + i * 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    if vis.shape[0] < panel_h:
        vis = cv2.copyMakeBorder(vis, 0, panel_h - vis.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(35, 35, 35))
    return np.hstack([vis, panel])


def hough_init(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=min(H_raw, W_raw) // 2,
        param1=80, param2=40,
        minRadius=min(H_raw, W_raw) // 6,
        maxRadius=min(H_raw, W_raw) // 2,
    )
    if circles is not None:
        c = np.round(circles[0][0]).astype(int)
        return int(c[0]), int(c[1]), int(c[2])
    return None


def refresh():
    cx     = cv2.getTrackbarPos("cx",      WINDOW_RAW)
    cy     = cv2.getTrackbarPos("cy",      WINDOW_RAW)
    r_in   = cv2.getTrackbarPos("inner_r", WINDOW_RAW)
    r_out  = cv2.getTrackbarPos("outer_r", WINDOW_RAW)
    p      = cv2.getTrackbarPos("p x100",  WINDOW_RAW) / 100.0
    out_w  = cv2.getTrackbarPos("out_w",   WINDOW_RAW)
    out_h  = cv2.getTrackbarPos("out_h",   WINDOW_RAW)

    r_in  = max(1, r_in)
    r_out = max(r_in + 1, r_out)
    out_w = max(10, out_w)
    out_h = max(10, out_h)

    frame = frames[frame_idx]
    cv2.imshow(WINDOW_RAW, draw_overlay(frame, cx, cy, r_in, r_out, p, out_w, out_h,
                                        frame_idx + 1, len(frames)))
    pano = unwrap_preview(frame, cx, cy, r_in, r_out, p, W_out=out_w, out_h=out_h)

    # Numeric output_width/output_height, drawn directly on the preview --
    # the native trackbar label isn't visible on every platform/display, and
    # this is the number that actually gets saved to the config, not just
    # whatever the slider looks like it's pointing at.
    label = f"output_width={out_w}  output_height={out_h}  p={p:.2f}"
    cv2.putText(pano, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(pano, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.resizeWindow(WINDOW_PANO, min(1600, max(400, out_w)), max(60, out_h + 30))
    cv2.imshow(WINDOW_PANO, pano)


def on_tb(_):
    refresh()


# ── windows & trackbars ───────────────────────────────────────────────────────
cv2.namedWindow(WINDOW_RAW,  cv2.WINDOW_NORMAL)
cv2.namedWindow(WINDOW_PANO, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_RAW,  1200, 800)
cv2.resizeWindow(WINDOW_PANO, 1200, 300)
cv2.moveWindow(WINDOW_RAW,  0,   0)
cv2.moveWindow(WINDOW_PANO, 0, 850)

for name, maxval in TB_MAX.items():
    label = name if name != "p100" else "p x100"
    cv2.createTrackbar(label, WINDOW_RAW, state[name], maxval, on_tb)

refresh()

# ── event loop ────────────────────────────────────────────────────────────────
while True:
    key = cv2.waitKey(50) & 0xFF

    if key == ord("q"):
        break

    elif key == ord("s"):
        cx    = cv2.getTrackbarPos("cx",      WINDOW_RAW)
        cy    = cv2.getTrackbarPos("cy",      WINDOW_RAW)
        r_in  = cv2.getTrackbarPos("inner_r", WINDOW_RAW)
        r_out = cv2.getTrackbarPos("outer_r", WINDOW_RAW)
        p     = cv2.getTrackbarPos("p x100",  WINDOW_RAW) / 100.0
        out_w = max(10, cv2.getTrackbarPos("out_w", WINDOW_RAW))
        out_h = max(10, cv2.getTrackbarPos("out_h", WINDOW_RAW))

        half_w = r_out
        half_h = r_out
        cfg_out = {
            "x1": max(0, cx - half_w),
            "y1": max(0, cy - half_h),
            "x2": min(W_raw, cx + half_w),
            "y2": min(H_raw, cy + half_h),
            "inner_radius":  r_in,
            "outer_radius":  r_out,
            "output_width":  out_w,
            "output_height": out_h,
            "p":             round(p, 4),
            "angle_offset":  defaults["angle_offset"],
        }
        with open(CFG_PATH, "w") as f:
            json.dump(cfg_out, f, indent=2)
        print(f"Saved to {CFG_PATH}: {cfg_out}")

    elif key == ord("h"):
        result = hough_init(frames[frame_idx])
        if result:
            cx, cy, r_out = result
            r_in = max(1, r_out // 5)
            cv2.setTrackbarPos("cx",      WINDOW_RAW, cx)
            cv2.setTrackbarPos("cy",      WINDOW_RAW, cy)
            cv2.setTrackbarPos("outer_r", WINDOW_RAW, r_out)
            cv2.setTrackbarPos("inner_r", WINDOW_RAW, r_in)
            print(f"Hough: cx={cx}  cy={cy}  outer_r={r_out}")
        else:
            print("Hough found no circle — tune param1/param2 manually.")
        refresh()

    elif key == ord("a"):
        frame_idx = max(0, frame_idx - 1)
        refresh()

    elif key == ord("d"):
        frame_idx = min(len(frames) - 1, frame_idx + 1)
        refresh()

cv2.destroyAllWindows()
