# wrc-vision-telemetry-pipeline

Turns onboard video into structured, real-time data: hazard detection, road position, yaw/slip and speed estimated from the image alone, streamed next to car telemetry and checked against real GPS/IMU.

```
camera frames ─► cv-ai-worker (YOLOv8 + OpenCV) ─► Redpanda ─► ingester (Go) ─► ClickHouse ─► Grafana
GPS/IMU       ─► telemetry-producer ──────────────┘                    └─► LocalStack S3 (clips)
```

## Status

- [x] Infra: Redpanda, ClickHouse, Grafana, LocalStack (`docker compose`)
- [x] CV worker: detection, road edges, optical flow, Kafka output
- [x] Sample data with real telemetry (KITTI) + accuracy check
- [x] Telemetry producer + live replay on a shared clock (`make demo`)
- [ ] Go ingester (Kafka → ClickHouse)
- [ ] Grafana dashboard

## Quick start

```bash
make setup      # Python venv + deps
make up         # infra containers
make sample     # KITTI drive: front camera + GPS/IMU (~250 MB)
make cv         # -> output/annotated.mp4 + output/events.jsonl
make compare    # CV estimates vs real GPS/IMU
make demo       # live replay: telemetry + CV events to Redpanda (SHOW=1 for preview)
```

## How video and telemetry stay in sync

Both streams carry their recorded timestamps. On replay, both services map them onto the same wall clock (`ts = start + (recorded − t0)`), with the same `run_id`, `start` and `t0` passed by `make demo`. Downstream they are joined by time (ClickHouse `ASOF JOIN`).

Measured on the KITTI sample: each frame lands within 1–13 ms of its telemetry sample. Kafka arrival lag is p50 4 ms for telemetry and p50 32 ms / p95 39 ms for CV events, which includes the processing time.

UIs: Redpanda Console http://localhost:8080 · Grafana http://localhost:3000 (admin/admin)

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
