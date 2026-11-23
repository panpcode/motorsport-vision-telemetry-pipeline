-- Each video frame joined with its nearest telemetry sample (before or after it),
-- so it works for any sample rate: KITTI 10 Hz, Forza 60 Hz.
-- Apply to a running ClickHouse with: make migrate
CREATE OR REPLACE VIEW motorsport.frames_with_telemetry AS
WITH m AS
(
    SELECT
        c.run_id AS run_id, c.ts AS ts, c.frame_idx AS frame_idx,
        c.speed_est_kmh AS speed_est_kmh, c.yaw_rate_deg_s AS yaw_rate_deg_s, c.slip_angle_deg AS slip_angle_deg,
        c.n_hazards AS n_hazards, c.min_hazard_dist_m AS min_hazard_dist_m,
        c.lateral_offset AS lateral_offset, c.apex_dist AS apex_dist,
        -- unmatched ASOF side comes back as 1970, so take the other one
        multiIf(toUnixTimestamp64Milli(n.ts) = 0, p.ts,
                toUnixTimestamp64Milli(p.ts) = 0, n.ts,
                dateDiff('millisecond', c.ts, n.ts) < dateDiff('millisecond', p.ts, c.ts), n.ts, p.ts) AS nearest_ts
    FROM motorsport.cv_events AS c
    ASOF LEFT JOIN (SELECT run_id, ts FROM motorsport.telemetry) AS p ON c.run_id = p.run_id AND c.ts >= p.ts
    ASOF LEFT JOIN (SELECT run_id, ts FROM motorsport.telemetry) AS n ON c.run_id = n.run_id AND c.ts <= n.ts
)
SELECT
    m.run_id AS run_id,
    m.ts AS ts,
    m.frame_idx AS frame_idx,
    dateDiff('millisecond', t.ts, m.ts) AS sync_gap_ms,
    t.speed_kmh AS speed_kmh,
    m.speed_est_kmh AS cv_speed_kmh,
    t.yaw_rate_deg_s AS yaw_rate_deg_s,
    m.yaw_rate_deg_s AS cv_yaw_rate_deg_s,
    t.slip_angle_deg AS slip_angle_deg,
    m.slip_angle_deg AS cv_slip_angle_deg,
    t.accel_lat AS accel_lat,
    t.steering_deg AS steering_deg,
    t.steer AS steer,
    m.n_hazards AS n_hazards,
    m.min_hazard_dist_m AS min_hazard_dist_m,
    m.lateral_offset AS lateral_offset,
    m.apex_dist AS apex_dist,
    t.lat AS lat,
    t.lon AS lon,
    t.x AS x,
    t.y AS y
FROM m
-- LEFT ANY: one sample per frame (several frames may share a sample)
ANY LEFT JOIN motorsport.telemetry AS t ON t.run_id = m.run_id AND t.ts = m.nearest_ts
-- No sample near this frame (video running before/after telemetry): drop it
WHERE abs(sync_gap_ms) <= 200;
