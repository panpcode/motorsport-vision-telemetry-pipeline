-- Lap comparison: two laps on a common distance grid (one row every 5 m)
CREATE TABLE IF NOT EXISTS wrc.lap_grid
(
    comparison  LowCardinality(String),
    driver_a    LowCardinality(String),
    driver_b    LowCardinality(String),
    distance_m  Float32,
    delta_s     Float32,   -- > 0: B behind A
    speed_a     Float32,
    speed_b     Float32,
    throttle_a  Float32,
    throttle_b  Float32,
    brake_a     UInt8,
    brake_b     UInt8,
    gear_a      UInt8,
    gear_b      UInt8,
    x           Float32,
    y           Float32
)
ENGINE = ReplacingMergeTree
ORDER BY (comparison, distance_m);

-- Where time was gained or lost, one row per corner
CREATE TABLE IF NOT EXISTS wrc.lap_corners
(
    comparison   LowCardinality(String),
    corner       UInt8,
    apex_m       Float32,
    time_diff_s  Float32,  -- > 0: A faster
    faster       LowCardinality(String),
    why          String,
    brake_m_a    Nullable(Float32),
    brake_m_b    Nullable(Float32),
    min_speed_a  Float32,
    min_speed_b  Float32
)
ENGINE = ReplacingMergeTree
ORDER BY (comparison, corner);
