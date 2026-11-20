-- Each video frame joined with its nearest telemetry sample.
-- The +50 ms lets a frame match a sample recorded just after it (samples are ~100 ms apart).
CREATE VIEW IF NOT EXISTS motorsport.frames_with_telemetry AS
SELECT
    c.run_id AS run_id,
    c.ts AS ts,
    c.frame_idx AS frame_idx,
    dateDiff('millisecond', t.ts, c.ts) AS sync_gap_ms,
    t.speed_kmh AS speed_kmh,
    c.speed_est_kmh AS cv_speed_kmh,
    t.yaw_rate_deg_s AS yaw_rate_deg_s,
    c.yaw_rate_deg_s AS cv_yaw_rate_deg_s,
    c.slip_angle_deg AS cv_slip_angle_deg,
    t.accel_lat AS accel_lat,
    t.steering_deg AS steering_deg,
    c.n_hazards AS n_hazards,
    c.min_hazard_dist_m AS min_hazard_dist_m,
    c.lateral_offset AS lateral_offset,
    c.apex_dist AS apex_dist,
    t.lat AS lat,
    t.lon AS lon
FROM (SELECT *, ts + toIntervalMillisecond(50) AS ts_match FROM motorsport.cv_events) AS c
ASOF JOIN motorsport.telemetry AS t ON c.run_id = t.run_id AND c.ts_match >= t.ts;
