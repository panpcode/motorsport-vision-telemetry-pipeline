-- Extra telemetry from games (Forza). Older datasets leave them NULL.
ALTER TABLE motorsport.telemetry
    ADD COLUMN IF NOT EXISTS x              Nullable(Float32),  -- track position, m
    ADD COLUMN IF NOT EXISTS y              Nullable(Float32),
    ADD COLUMN IF NOT EXISTS lap            Nullable(UInt16),
    ADD COLUMN IF NOT EXISTS gear           Nullable(UInt8),
    ADD COLUMN IF NOT EXISTS rpm            Nullable(Float32),
    ADD COLUMN IF NOT EXISTS steer          Nullable(Float32),  -- -1..1, + = left
    ADD COLUMN IF NOT EXISTS slip_angle_deg Nullable(Float32);  -- travel vs heading, + = moving right
