# wrc-vision-telemetry-pipeline

Turns rally onboard video into structured, real-time data: hazard detection, road position, yaw/slip and speed estimated from the image alone, streamed next to car telemetry.

```
onboard.mp4 ─► cv-ai-worker (YOLOv8 + OpenCV) ─► Redpanda ─► ingester (Go) ─► ClickHouse ─► Grafana
telemetry   ─► video-producer ──────────────────┘                    └─► LocalStack S3 (clips)
```

## Status

- [x] Infra: Redpanda, ClickHouse, Grafana, LocalStack (`docker compose`)
- [x] CV worker: detection, road edges, optical flow, Kafka output
- [ ] Telemetry producer
- [ ] Go ingester (Kafka → ClickHouse)
- [ ] Grafana dashboard

## Quick start

```bash
make setup                     # Python venv + deps
make up                        # infra containers
cp ~/some-onboard.mp4 sample-data/onboard.mp4
make cv                        # -> output/annotated.mp4 + output/events.jsonl
make cv-kafka                  # live mode, events to topic wrc.cv.events
```

UIs: Redpanda Console http://localhost:8080 · Grafana http://localhost:3000 (admin/admin)

> The CV worker runs natively, not in Docker, so it can use the Apple Silicon GPU (MPS).

## What the CV worker measures

| Field | How |
|---|---|
| `detections`, `n_hazards` | YOLOv8 (cars, people, animals). Distance from pinhole model: `f · real_height / box_height` |
| `lateral_offset` | Canny + Hough road edges. -1 = left edge, 0 = centre, +1 = right edge |
| `apex_dist` | Distance to the inside edge while cornering (0 = on the apex) |
| `yaw_rate_deg_s` | Sideways optical flow of far points |
| `slip_angle_deg` | Angle between camera heading and the focus of expansion (true travel direction) |
| `speed_est_kmh` | Ground-point flow + camera height (flat road assumption) |

Tested on a synthetic clip with known motion (72 km/h, 5.7° slip): estimated 5.7° slip and ~73–79 km/h.

## Benchmarks

Run `make cv` and the worker prints p50/p95 latency for your machine. Only real numbers go here.

| Machine | Input | YOLO p50 | Pipeline FPS |
|---|---|---|---|
| Apple Silicon (MPS), yolov8n | 640x360 synthetic | 10 ms | ~48 |
