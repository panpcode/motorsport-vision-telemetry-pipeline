"""Replays recorded car telemetry to Kafka as if it was live."""
import argparse
import csv
import json
import math
import os
import time
from datetime import datetime


def kitti_ts_ms(line):
    # "2011-09-26 13:12:03.968689565" -> epoch ms (strptime handles max 6 decimals)
    return datetime.strptime(line.strip()[:26], "%Y-%m-%d %H:%M:%S.%f").timestamp() * 1000


def load_kitti(drive):
    """Yields (source_ts_ms, sample) from a KITTI drive's OXTS (GPS/IMU) files."""
    oxts = os.path.join(drive, "oxts")
    stamps = open(os.path.join(oxts, "timestamps.txt")).read().split("\n")
    for i, stamp in enumerate(s for s in stamps if s.strip()):
        v = [float(x) for x in open(os.path.join(oxts, "data", f"{i:010d}.txt")).read().split()]
        yield kitti_ts_ms(stamp), {
            "speed_kmh": round(v[8] * 3.6, 2),
            "yaw_rate_deg_s": round(math.degrees(v[22]), 3),
            "accel_long": round(v[14], 3),
            "accel_lat": round(v[15], 3),
            "heading_deg": round(math.degrees(v[5]), 2),
            "lat": v[0], "lon": v[1], "alt": round(v[2], 2),
            "steering_deg": None, "throttle": None, "brake": None,  # not in KITTI
        }


# Columns of telemetry.csv (scripts/decode_forza.py) that go to Kafka as they are
CSV_FLOATS = ["speed_kmh", "yaw_rate_deg_s", "accel_long", "accel_lat", "heading_deg", "throttle", "brake",
              "x", "y", "rpm", "steer", "slip_angle_deg"]


def load_csv(path):
    """Yields (source_ts_ms, sample) from game telemetry.csv."""
    for r in csv.DictReader(open(path)):
        sample = {k: float(r[k]) if r[k] != "" else None for k in CSV_FLOATS}
        sample.update(lap=int(r["lap"]), gear=int(r["gear"]))
        yield float(r["ts_ms"]), sample


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="KITTI drive folder, or game telemetry.csv")
    p.add_argument("--kafka", help="brokers, e.g. localhost:19092 (else print JSON)")
    p.add_argument("--topic", default="motorsport.telemetry")
    p.add_argument("--run-id", default="dev")
    p.add_argument("--start-ms", type=int, help="wall clock time of the first sample (default: now)")
    p.add_argument("--t0-ms", type=float, help="source time that maps to --start-ms (default: first sample)")
    p.add_argument("--no-wait", action="store_true", help="send as fast as possible")
    args = p.parse_args()

    samples = list(load_csv(args.source) if args.source.endswith(".csv") else load_kitti(args.source))
    start_ms = args.start_ms or int(time.time() * 1000)
    t0 = args.t0_ms if args.t0_ms is not None else samples[0][0]

    producer = None
    if args.kafka:
        from confluent_kafka import Producer
        producer = Producer({"bootstrap.servers": args.kafka, "linger.ms": 5})

    for src_ts, sample in samples:
        # Shift recorded time to "now" so the replay looks live
        ts_ms = int(start_ms + (src_ts - t0))
        if not args.no_wait:
            delay = ts_ms / 1000 - time.time()
            if delay > 0:
                time.sleep(delay)

        msg = {"run_id": args.run_id, "ts_ms": ts_ms, **sample}
        if producer:
            producer.produce(args.topic, key=args.run_id, value=json.dumps(msg))
            producer.poll(0)
        else:
            print(json.dumps(msg))

    if producer:
        producer.flush(5)
    print(f"sent {len(samples)} samples, run_id={args.run_id}")


if __name__ == "__main__":
    main()
