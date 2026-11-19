import cv2
import numpy as np

GREEN, RED, CYAN, YELLOW, WHITE = (0, 220, 0), (0, 0, 255), (255, 200, 0), (0, 220, 255), (255, 255, 255)


def annotate(frame, detections, road, motion, stats):
    out = frame.copy()

    # Road area
    if road["left_x"] is not None and road["right_x"] is not None:
        pts = np.array([[road["left_x"], road["y_bot"]], [road["left_top"], road["y_top"]],
                        [road["right_top"], road["y_top"]], [road["right_x"], road["y_bot"]]], np.int32)
        overlay = out.copy()
        cv2.fillPoly(overlay, [pts], (0, 120, 0))
        out = cv2.addWeighted(overlay, 0.25, out, 0.75, 0)
        cv2.polylines(out, [pts], True, CYAN, 2)

    # Detections
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        color = RED if d.get("hazard") else GREEN
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f'{d["cls"]} {d["dist_m"]:.0f}m', (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # Focus of expansion = where the car is really heading
    if motion.get("foe"):
        fx, fy = map(int, motion["foe"])
        cv2.drawMarker(out, (fx, fy), YELLOW, cv2.MARKER_CROSS, 30, 2)

    # HUD
    fmt = lambda v, u: "--" if v is None else f"{v:.1f}{u}"
    lines = [
        f'infer {stats["inference_ms"]:.0f}ms  fps {stats["fps"]:.0f}',
        f'speed~ {fmt(motion["speed_est_kmh"], " km/h")}',
        f'yaw {fmt(motion["yaw_rate_deg_s"], " deg/s")}',
        f'slip {fmt(motion["slip_angle_deg"], " deg")}',
        f'lateral {fmt(road["lateral_offset"], "")}',
    ]
    cv2.rectangle(out, (10, 10), (300, 20 + 26 * len(lines)), (0, 0, 0), -1)
    for i, t in enumerate(lines):
        cv2.putText(out, t, (18, 34 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1)
    return out
