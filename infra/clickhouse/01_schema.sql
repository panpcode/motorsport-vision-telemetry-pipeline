-- Car telemetry (from the producer)
CREATE TABLE IF NOT EXISTS wrc.telemetry
(
    run_id      LowCardinality(String),
    ts          DateTime64(3),
    speed_kmh   Float32,
    rpm         UInt16,
    gear        UInt8,
    throttle    Float32,
    brake       Float32,
    steering    Float32,
    lat         Float64,
    lon         Float64
)
ENGINE = MergeTree
ORDER BY (run_id, ts);

-- One row per processed video frame (from the CV worker)
CREATE TABLE IF NOT EXISTS wrc.cv_events
(
    run_id            LowCardinality(String),
    ts                DateTime64(3),
    frame_idx         UInt32,
    inference_ms      Float32,
    n_detections      UInt16,
    n_hazards         UInt16,
    min_hazard_dist_m Nullable(Float32),
    lateral_offset    Nullable(Float32),
    apex_dist         Nullable(Float32),
    yaw_rate_deg_s    Nullable(Float32),
    slip_angle_deg    Nullable(Float32),
    speed_est_kmh     Nullable(Float32),
    detections        String  -- raw JSON
)
ENGINE = MergeTree
ORDER BY (run_id, ts);
