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

            if dist < self.hazard_dist_m and self._on_road((x1 + x2) / 2, w, road):
                det["hazard"] = True
                hazards.append(det)

        return detections, hazards

    @staticmethod
    def _on_road(cx, width, road):
        # Use detected road edges if we have them, else the middle 60% of the frame
        if road and road.get("left_x") is not None and road.get("right_x") is not None:
            margin = 0.15 * (road["right_x"] - road["left_x"])
            return road["left_x"] - margin <= cx <= road["right_x"] + margin
        return 0.2 * width <= cx <= 0.8 * width
