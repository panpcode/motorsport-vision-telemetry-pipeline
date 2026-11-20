import argparse
import json
import time
import uuid
from datetime import datetime

import cv2
import numpy as np

from .detector import HazardDetector
from .draw import annotate
from .flow import MotionEstimator
from .road import RoadTracker, apex_distance
from .sink import JsonlSink, KafkaSink


def kitti_ts_ms(line):
    # "2011-09-26 13:12:03.968689565" -> epoch ms
    return datetime.strptime(line.strip()[:26], "%Y-%m-%d %H:%M:%S.%f").timestamp() * 1000


def parse_args():
    p = argparse.ArgumentParser(description="Onboard video -> CV events")
    p.add_argument("video", help="path to onboard .mp4")
    p.add_argument("--model", default="yolov8n.pt")
    p.add_argument("--device", default=None, help="mps / cuda / cpu (auto if empty)")
    p.add_argument("--hfov", type=float, default=90.0, help="camera horizontal FOV in degrees")
    p.add_argument("--cam-height", type=float, default=1.2, help="camera height above road in m")
    p.add_argument("--out", help="write annotated video here")
    p.add_argument("--events", help="write events as JSON lines here")
    p.add_argument("--kafka", help="Kafka brokers, e.g. localhost:19092")
    p.add_argument("--topic", default="motorsport.cv.events")
    p.add_argument("--run-id", default=None)
    p.add_argument("--timestamps", help="KITTI timestamps.txt with the real time of each frame")
    p.add_argument("--start-ms", type=int, help="wall clock time of the first frame (default: now)")
    p.add_argument("--t0-ms", type=float, help="source time that maps to --start-ms (default: first frame)")
    p.add_argument("--realtime", action="store_true", help="pace frames like a live stream")
    p.add_argument("--show", action="store_true", help="open a preview window")
    p.add_argument("--max-frames", type=int, default=0)
    return p.parse_args()


def main():
    args = parse_args()
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector = HazardDetector(args.model, hfov_deg=args.hfov, device=args.device)
    detector.warmup(w, h)
    road_tracker = RoadTracker()
    motion = MotionEstimator(fps, hfov_deg=args.hfov, cam_height_m=args.cam_height)
    print(f"video {w}x{h} @ {fps:.0f}fps, device={detector.device}")

    sinks = []
    if args.events:
        sinks.append(JsonlSink(args.events))
    if args.kafka:
        sinks.append(KafkaSink(args.kafka, args.topic))
    writer = None
    if args.out:
        writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    run_id = args.run_id or uuid.uuid4().hex[:8]

    # Source time of each frame: from the timestamps file, else from fps
    if args.timestamps:
        frame_src_ms = [kitti_ts_ms(s) for s in open(args.timestamps) if s.strip()]
    else:
        frame_src_ms = None
    t0 = args.t0_ms if args.t0_ms is not None else (frame_src_ms[0] if frame_src_ms else 0.0)
    start_ms = args.start_ms or int(time.time() * 1000)
    infer_times, loop_times = [], []
    idx = 0

    while True:
        ok, frame = cap.read()
        if not ok or (args.max_frames and idx >= args.max_frames):
            break
        t_loop = time.perf_counter()

        road = road_tracker.update(frame)
        t_inf = time.perf_counter()
        detections, hazards = detector.detect(frame, road)
        infer_ms = (time.perf_counter() - t_inf) * 1000
        mot = motion.update(frame, ignore_boxes=[d["bbox"] for d in detections])

        # Recorded frame time, shifted to the replay clock (same rule as the telemetry producer)
        src_ms = frame_src_ms[idx] if frame_src_ms else t0 + idx * 1000 / fps
        ts_ms = int(start_ms + (src_ms - t0))
        event = {
            "run_id": run_id,
            "frame_idx": idx,
            "ts_ms": ts_ms,
            "inference_ms": round(infer_ms, 2),
            "n_detections": len(detections),
            "n_hazards": len(hazards),
            "min_hazard_dist_m": min((d["dist_m"] for d in hazards), default=None),
            "lateral_offset": road["lateral_offset"],
            "apex_dist": apex_distance(road, mot["yaw_rate_deg_s"]),
            "yaw_rate_deg_s": mot["yaw_rate_deg_s"],
            "slip_angle_deg": mot["slip_angle_deg"],
            "speed_est_kmh": mot["speed_est_kmh"],
            "detections": detections,
        }
        for s in sinks:
            s.send(event)

        loop_ms = (time.perf_counter() - t_loop) * 1000
        infer_times.append(infer_ms)
        loop_times.append(loop_ms)

        if writer or args.show:
            vis = annotate(frame, detections, road, mot,
                           {"inference_ms": infer_ms, "fps": 1000 / max(loop_ms, 1)})
            if writer:
                writer.write(vis)
            if args.show:
                cv2.imshow("motorsport-cv", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        idx += 1
        if args.realtime and (not frame_src_ms or idx < len(frame_src_ms)):
            # Wait until the next frame's slot in "live" time
            next_ms = frame_src_ms[idx] if frame_src_ms else t0 + idx * 1000 / fps
            delay = (start_ms + next_ms - t0) / 1000 - time.time()
            if delay > 0:
                time.sleep(delay)

    cap.release()
    if writer:
        writer.release()
    for s in sinks:
        s.close()
    cv2.destroyAllWindows()

    if idx:
        inf, loop = np.array(infer_times[1:] or infer_times), np.array(loop_times[1:] or loop_times)
        summary = {
            "frames": idx,
            "device": detector.device,
            "resolution": f"{w}x{h}",
            "inference_ms_p50": round(float(np.percentile(inf, 50)), 1),
            "inference_ms_p95": round(float(np.percentile(inf, 95)), 1),
            "pipeline_ms_p50": round(float(np.percentile(loop, 50)), 1),
            "pipeline_fps": round(1000 / float(np.mean(loop)), 1),
        }
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
