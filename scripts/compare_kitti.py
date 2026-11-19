"""Compare CV estimates (events.jsonl) with KITTI GPS/IMU ground truth, frame by frame."""
import argparse
import json
import math
import os

import numpy as np

# OXTS columns we need (see oxts/dataformat.txt)
VF, WU = 8, 22  # forward speed (m/s), yaw rate (rad/s, + = left)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("events")
    p.add_argument("--drive", default="sample-data/2011_09_26_drive_0015")
    p.add_argument("--skip", type=int, default=10, help="ignore first frames (filters warming up)")
    args = p.parse_args()

    events = [json.loads(line) for line in open(args.events)]
    oxts_dir = os.path.join(args.drive, "oxts", "data")

    rows = []
    for e in events[args.skip:]:
        vals = open(os.path.join(oxts_dir, f'{e["frame_idx"]:010d}.txt')).read().split()
        true_speed = float(vals[VF]) * 3.6
        true_yaw = math.degrees(float(vals[WU]))
        rows.append((true_speed, e["speed_est_kmh"], true_yaw, e["yaw_rate_deg_s"]))

    def report(name, truth, est):
        ok = [(t, s) for t, s in zip(truth, est) if s is not None]
        t, s = np.array(ok).T
        mae = np.mean(np.abs(s - t))
        corr = np.corrcoef(t, s)[0, 1] if len(t) > 2 else float("nan")
        print(f"{name:6s} MAE {mae:6.2f}  corr {corr:5.2f}  true mean {t.mean():6.1f}  est mean {s.mean():6.1f}  n={len(t)}")

    truth_v, est_v, truth_y, est_y = zip(*rows)
    report("speed", truth_v, est_v)
    report("yaw", truth_y, est_y)


if __name__ == "__main__":
    main()
