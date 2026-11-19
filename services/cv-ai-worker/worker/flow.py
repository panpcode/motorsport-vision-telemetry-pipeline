import math

import cv2
import numpy as np


class MotionEstimator:
    """
    Sparse optical flow (Lucas-Kanade) between frames.
    - yaw rate: sideways shift of far-away points
    - slip angle: where the car is really moving (focus of expansion) vs where it points
    - speed: how fast road points move down the image (needs camera height)
    """

    def __init__(self, fps, hfov_deg=90.0, cam_height_m=1.2, work_width=640,
                 horizon_frac=0.45, hood_frac=0.9, smooth=0.7):
        self.fps = fps
        self.hfov = math.radians(hfov_deg)
        self.cam_h = cam_height_m
        self.work_w = work_width
        self.horizon_frac = horizon_frac
        self.hood_frac = hood_frac
        self.smooth = smooth
        self.prev = None
        self.state = {"yaw_rate_deg_s": None, "slip_angle_deg": None,
                      "speed_est_kmh": None, "foe": None}

    def update(self, frame, ignore_boxes=()):
        h0, w0 = frame.shape[:2]
        scale = self.work_w / w0
        gray = cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        f = (w / 2) / math.tan(self.hfov / 2)

        prev, self.prev = self.prev, gray
        if prev is None:
            return self.state

        # Track points between horizon-ish and the bonnet, skipping moving objects
        mask = np.zeros_like(gray)
        mask[int(h * 0.25):int(h * self.hood_frac), :] = 255
        for x1, y1, x2, y2 in ignore_boxes:
            mask[int(y1 * scale):int(y2 * scale), int(x1 * scale):int(x2 * scale)] = 0

        p0 = cv2.goodFeaturesToTrack(prev, maxCorners=400, qualityLevel=0.01,
                                     minDistance=7, mask=mask)
        if p0 is None or len(p0) < 20:
            return self.state

        p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, gray, p0, None)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev, p1, None)
        # Keep points that track forward and back to the same spot
        good = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm(p0 - back, axis=2)[:, 0] < 1.0)
        p0, p1 = p0[good, 0], p1[good, 0]
        if len(p0) < 20:
            return self.state

        d = p1 - p0
        cx, cy = w / 2, h / 2

        # Yaw: far points (near horizon) shift sideways when the car rotates
        far = np.abs(p0[:, 1] - h * self.horizon_frac) < h * 0.1
        dx_far = np.median(d[far, 0]) if far.sum() >= 5 else np.median(d[:, 0])
        yaw = math.degrees(math.atan2(dx_far, f)) * self.fps  # + = turning left

        # Remove rotation, then find the point all flow vectors come from (FOE)
        d_trans = d.copy()
        d_trans[:, 0] -= dx_far
        foe = self._focus_of_expansion(p0, d_trans)

        slip, speed = None, None
        if foe is not None and 0 <= foe[0] < w and 0 <= foe[1] < h:
            # FOE right of centre = car is moving to the right of where it points
            slip = math.degrees(math.atan2(foe[0] - cx, f))
            speed = self._speed(p0, d_trans, foe[1], f, h)

        self._ema("yaw_rate_deg_s", yaw)
        self._ema("slip_angle_deg", slip)
        self._ema("speed_est_kmh", speed)
        self.state["foe"] = (foe[0] / scale, foe[1] / scale) if foe is not None else None
        return self.state

    @staticmethod
    def _focus_of_expansion(p, d, min_mag=0.5):
        mag = np.linalg.norm(d, axis=1)
        keep = mag > min_mag
        if keep.sum() < 15:
            return None
        p, d = p[keep], d[keep]
        # Each vector defines a line; solve for the point closest to all lines
        A = np.stack([d[:, 1], -d[:, 0]], axis=1)
        b = d[:, 1] * p[:, 0] - d[:, 0] * p[:, 1]
        for _ in range(2):  # second pass drops outliers
            sol, *_ = np.linalg.lstsq(A, b, rcond=None)
            err = np.abs(A @ sol - b) / (np.linalg.norm(A, axis=1) + 1e-6)
            inl = err < np.percentile(err, 70)
            A, b = A[inl], b[inl]
        return sol

    def _speed(self, p, d, horizon_y, f, h):
        # Flat road: point at row y is Z = f*H/(y - y_h) away, so V = dy * f*H / (y - y_h)^2
        dy = d[:, 1]
        below = p[:, 1] - horizon_y
        ground = (below > h * 0.1) & (dy > 0)
        if ground.sum() < 5:
            return None
        v = dy[ground] * self.fps * f * self.cam_h / below[ground] ** 2
        return float(np.median(v)) * 3.6

    def _ema(self, key, val):
        if val is None:
            return
        old = self.state[key]
        new = val if old is None else self.smooth * old + (1 - self.smooth) * val
        self.state[key] = round(new, 2)
