-- Car telemetry (from the producer). Columns a dataset doesn't have stay NULL.
-- ORDER BY (run_id, ts): queries read one run over a time range, so rows are stored that way (it is also the index).
CREATE TABLE IF NOT EXISTS motorsport.telemetry
(
    run_id          LowCardinality(String),
    ts              DateTime64(3),
    speed_kmh       Float32,
    yaw_rate_deg_s  Nullable(Float32),
    accel_long      Nullable(Float32),  -- m/s^2, + = accelerating
    accel_lat       Nullable(Float32),  -- m/s^2, + = to the left
    heading_deg     Nullable(Float32),
    lat             Nullable(Float64),
    lon             Nullable(Float64),
    alt             Nullable(Float32),
    steering_deg    Nullable(Float32),
    throttle        Nullable(Float32),
    brake           Nullable(Float32)
)
ENGINE = MergeTree
ORDER BY (run_id, ts);

-- One row per processed video frame (from the CV worker)
CREATE TABLE IF NOT EXISTS motorsport.cv_events
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
