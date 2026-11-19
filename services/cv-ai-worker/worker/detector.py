import math

import torch
from ultralytics import YOLO

# Typical real heights (m) for COCO classes we care about
REAL_HEIGHT_M = {
    "person": 1.7, "car": 1.5, "truck": 3.0, "bus": 3.0,
    "motorcycle": 1.4, "bicycle": 1.1, "dog": 0.6, "horse": 1.6,
    "cow": 1.5, "sheep": 0.9, "bird": 0.3, "bear": 1.2,
}


def pick_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class HazardDetector:
    def __init__(self, model_path="yolov8n.pt", hfov_deg=90.0, conf=0.35,
                 hazard_dist_m=60.0, device=None):
        self.model = YOLO(model_path)
        self.device = device or pick_device()
        self.hfov = math.radians(hfov_deg)
        self.conf = conf
        self.hazard_dist_m = hazard_dist_m
        self.classes = [i for i, n in self.model.names.items() if n in REAL_HEIGHT_M]

    def focal_px(self, width):
        return (width / 2) / math.tan(self.hfov / 2)

    def detect(self, frame, road=None):
        h, w = frame.shape[:2]
        f = self.focal_px(w)
        res = self.model.predict(frame, conf=self.conf, classes=self.classes,
                                 device=self.device, verbose=False)[0]

        detections, hazards = [], []
        for box in res.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            name = self.model.names[int(box.cls)]
            # Pinhole camera: distance = f * real_height / pixel_height
            dist = f * REAL_HEIGHT_M[name] / max(y2 - y1, 1.0)
            det = {
                "cls": name,
                "conf": round(float(box.conf), 3),
                "bbox": [round(x1), round(y1), round(x2), round(y2)],
                "dist_m": round(dist, 1),
            }
            detections.append(det)

            if dist < self.hazard_dist_m and self._on_road(x1, x2, y2, w, road):
                det["hazard"] = True
                hazards.append(det)

        return detections, hazards

    @staticmethod
    def _on_road(x1, x2, y_bottom, width, road):
        # Road edges at the object's own height (where it touches the ground)
        if road and road.get("left_line") and road.get("right_line"):
            (ml, bl), (mr, br) = road["left_line"], road["right_line"]
            left, right = ml * y_bottom + bl, mr * y_bottom + br
            margin = 0.15 * (right - left)
            return x2 > left - margin and x1 < right + margin  # box overlaps the road
        return 0.2 * width <= (x1 + x2) / 2 <= 0.8 * width
