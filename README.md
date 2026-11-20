# motorsport-vision-telemetry-pipeline

Data tools for motorsport (rally, circuit racing): onboard video turned into real-time data (hazards, road position, yaw/slip and speed from the image alone) streamed next to car telemetry, plus lap comparison that shows where a driver gains or loses time.

```
camera frames ─► cv-ai-worker (YOLOv8 + OpenCV) ─► Redpanda ─► ingester (Go) ─► ClickHouse ─► Grafana
GPS/IMU       ─► telemetry-producer ──────────────┘                    └─► LocalStack S3 (clips)
```

## Status

- [x] Infra: Redpanda, ClickHouse, Grafana, LocalStack (`docker compose`)
- [x] CV worker: detection, road edges, optical flow, Kafka output
- [x] Sample data with real telemetry (KITTI) + accuracy check
- [x] Telemetry producer + live replay on a shared clock (`make demo`)
- [x] Go ingester (Kafka → ClickHouse) + joined view `frames_with_telemetry`
- [x] Grafana dashboard (auto-provisioned, live refresh)
- [x] Lap comparison on real F1 data: where time was gained or lost, and why

## Quick start

```bash
make setup      # Python venv + deps
make up         # infra containers
make sample     # KITTI drive: front camera + GPS/IMU (~250 MB)
make cv         # -> output/annotated.mp4 + output/events.jsonl
make compare    # CV estimates vs real GPS/IMU
make demo       # live replay: telemetry + CV events to Redpanda (SHOW=1 for preview)
make laps       # real F1 laps compared: VER vs NOR, Abu Dhabi 2025 quali
```

## How video and telemetry stay in sync

Both streams carry their recorded timestamps. On replay, both services map them onto the same wall clock (`ts = start + (recorded − t0)`), with the same `run_id`, `start` and `t0` passed by `make demo`. The Go ingester writes both to ClickHouse, and the view `motorsport.frames_with_telemetry` joins each frame to its nearest telemetry sample (`ASOF JOIN`).

Measured on the KITTI sample:

| Step | Latency |
|---|---|
| Frame ↔ telemetry sample (sync gap) | 1–13 ms |
| Telemetry producer → Kafka | p50 4 ms |
| Frame time → CV event in Kafka (includes inference) | p50 32 ms, p95 39 ms |
| Kafka → ClickHouse (Go ingester, 50 ms batches) | p50 12 ms, p95 ~15 ms |

## Lap comparison: where time is won

`make laps` takes two real laps and finds where one driver gains on the other, corner by corner:

```
make laps A=VER B=NOR EVENT="Yas Marina" YEAR=2025 SESSION=Qualifying

VER 1:22.207  vs  NOR 1:22.408  (gap +0.201 s, track 5223 m)
Delta checked against official sector times: max error 0.036 s, corrected

C3  @ 2630 m  NOR loses 0.121 s  -  VER: brakes 15 m later
C4  @ 3675 m  VER loses 0.047 s  -  NOR: full throttle 60 m earlier
...
```

How it works:

1. **Distance, not time.** Speed is integrated into distance, so both laps can be compared at the same point on track. The gap at each metre is the time difference there.
2. **Corners** are the clear speed dips. A chicane with no real straight between its two dips counts as one corner.
3. **Time per corner** is measured from the straight before to the straight after. This is where the gap line is most reliable.
4. **Why**: braking point, minimum speed, where full throttle comes back, top speed after. Only differences above the data resolution are reported (15 m, 3 km/h).
5. **Check against official timing.** The distance from integrated speed drifts a few metres, so the gap is compared with the official F1 sector times. Measured error over 6 laps: mean 0.03 s, max 0.10 s. The gap is then corrected to match them.

The output goes to `output/laps_*.png` and to the Grafana dashboard **Lap Comparison**. That dashboard shows the gap, speed, throttle and brake by distance, a track map of who is faster every 200 m, and the corner table.

The analysis only needs time, speed, throttle, brake and x/y per sample, so the same code works on game telemetry.

Data: [OpenF1](https://openf1.org) (free historical data, no account). FastF1 needs a paid F1 TV login since 2026. Samples come about 4 times a second, so braking points are ±15 m. The gap line can swing inside slow corners, but the corner totals stay reliable.

## Recording your own rally data

`scripts/record_udp_telemetry.py` records raw UDP telemetry from a racing game (plain Python, no installs) while OBS records the onboard video. Packets are stored raw with the PC clock time and decoded later.

UIs: Grafana http://localhost:3000 (Vision + Telemetry and Lap Comparison dashboards, no login) · Redpanda Console http://localhost:8080

Run `make demo` and watch the dashboard update live (pick the newest run in the *Run* dropdown).

> The CV worker runs natively, not in Docker, so it can use the Apple Silicon GPU (MPS).

## Data

Video sources need real telemetry recorded with them to be useful here; broadcast onboards don't have it. The sample uses a **KITTI raw** drive: front camera frames plus GPS/IMU (speed, yaw rate, position) with timestamps for every frame. `make sample` fetches only those files from the archive, not the full 1.2 GB.

> KITTI raw data © Geiger, Lenz, Stiller, Urtasun — *Vision meets Robotics: The KITTI Dataset*, IJRR 2013. Licensed [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/). Not included in this repo.

## What the CV worker measures

| Field | How |
|---|---|
| `detections`, `n_hazards` | YOLOv8 (cars, people, animals). Distance from pinhole model: `f · real_height / box_height`. Hazard = within 60 m and on the road |
| `lateral_offset` | Canny + Hough road edges. -1 = left edge, 0 = centre, +1 = right edge |
| `apex_dist` | Distance to the inside edge while cornering (0 = on the apex) |
| `yaw_rate_deg_s` | Sideways optical flow of far points |
| `slip_angle_deg` | Angle between camera heading and the focus of expansion (true travel direction) |
| `speed_est_kmh` | Ground-point flow + camera height (flat road assumption) |

## Accuracy (vs KITTI GPS/IMU)

KITTI drive `2011_09_26_drive_0015`, 297 frames, `make compare`:

| Signal | Mean abs error | Correlation | Note |
|---|---|---|---|
| Speed | 5.1 km/h (true mean 42 km/h) | 0.87 | |
| Yaw rate | 1.4 °/s | 0.20 | Mostly straight drive (true yaw within ±1.4 °/s), so this is mostly noise. Needs a drive with corners |

## Benchmarks

Measured by the worker itself (`make cv` prints p50/p95). Only real numbers go here.

| Machine | Input | YOLO p50 | Pipeline FPS |
|---|---|---|---|
| Apple Silicon (MPS), yolov8n | KITTI 1242x374 | 8.6 ms | ~60 |
