import cv2
import numpy as np


class RoadTracker:
    """Finds left/right road edges with Canny + Hough lines."""

    def __init__(self, horizon_frac=0.55, hood_frac=0.9, smooth=0.8):
        self.horizon_frac = horizon_frac  # top of search area (fraction of height)
        self.hood_frac = hood_frac        # bottom, above the bonnet/dash
        self.smooth = smooth
        self.left = None   # line as (slope, intercept) in x = m*y + b form
        self.right = None

    def update(self, frame):
        h, w = frame.shape[:2]
        y_top, y_bot = int(h * self.horizon_frac), int(h * self.hood_frac)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)

        # Keep only a trapezoid in front of the car
        mask = np.zeros_like(edges)
        poly = np.array([[(0, y_bot), (int(w * 0.4), y_top),
                          (int(w * 0.6), y_top), (w, y_bot)]], dtype=np.int32)
        cv2.fillPoly(mask, poly, 255)
        edges = cv2.bitwise_and(edges, mask)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40,
                                minLineLength=h // 20, maxLineGap=h // 30)

        left, right = [], []
        if lines is not None:
            for x1, y1, x2, y2 in lines[:, 0]:
                if y1 == y2:
                    continue
                m = (x2 - x1) / (y2 - y1)  # dx/dy
                b = x1 - m * y1
                length = np.hypot(x2 - x1, y2 - y1)
                # Left edge leans right going up (dx/dy < 0 in image coords)
                if -3 < m < -0.3:
                    left.append((m, b, length))
                elif 0.3 < m < 3:
                    right.append((m, b, length))

        self.left = self._blend(self.left, self._fit(left))
        self.right = self._blend(self.right, self._fit(right))
        return self._result(w, y_top, y_bot, bool(left), bool(right))

    @staticmethod
    def _fit(segs):
        if not segs:
            return None
        a = np.array(segs)
        return tuple(np.average(a[:, :2], axis=0, weights=a[:, 2]))

    def _blend(self, old, new):
        if new is None:
            return old
        if old is None:
            return new
        s = self.smooth
        return (s * old[0] + (1 - s) * new[0], s * old[1] + (1 - s) * new[1])

    def _result(self, w, y_top, y_bot, saw_left, saw_right):
        x_at = lambda line, y: line[0] * y + line[1] if line else None
        lx, rx = x_at(self.left, y_bot), x_at(self.right, y_bot)
        out = {
            "left_x": lx, "right_x": rx, "y_top": y_top, "y_bot": y_bot,
            "left_top": x_at(self.left, y_top), "right_top": x_at(self.right, y_top),
            "confidence": (saw_left + saw_right) / 2,
            "lateral_offset": None,
        }
        if lx is not None and rx is not None and rx - lx > w * 0.1:
            center = (lx + rx) / 2
            # -1 = on left edge, 0 = middle, +1 = on right edge
            out["lateral_offset"] = round((w / 2 - center) / ((rx - lx) / 2), 3)
        return out


def apex_distance(road, yaw_rate_deg_s, min_yaw=5.0):
    """How close to the inside edge of a corner (0 = on the edge, 1 = outside edge)."""
    off = road.get("lateral_offset")
    if off is None or yaw_rate_deg_s is None or abs(yaw_rate_deg_s) < min_yaw:
        return None
    # Positive yaw = turning left, so inside edge is the left one (offset -1)
    pos = (off + 1) / 2  # 0 = left edge, 1 = right edge
    d = pos if yaw_rate_deg_s > 0 else 1 - pos
    return round(min(max(d, 0.0), 1.0), 3)
