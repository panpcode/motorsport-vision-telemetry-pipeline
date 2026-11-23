package main

import "encoding/json"

// Message from topic motorsport.telemetry (pointer = may be null)
type Telemetry struct {
	RunID       string   `json:"run_id"`
	TsMs        int64    `json:"ts_ms"`
	SpeedKmh    float32  `json:"speed_kmh"`
	YawRateDegS *float32 `json:"yaw_rate_deg_s"`
	AccelLong   *float32 `json:"accel_long"`
	AccelLat    *float32 `json:"accel_lat"`
	HeadingDeg  *float32 `json:"heading_deg"`
	Lat         *float64 `json:"lat"`
	Lon         *float64 `json:"lon"`
	Alt         *float32 `json:"alt"`
	SteeringDeg *float32 `json:"steering_deg"`
	Throttle    *float32 `json:"throttle"`
	Brake       *float32 `json:"brake"`
	// Games only (Forza)
	X            *float32 `json:"x"`
	Y            *float32 `json:"y"`
	Lap          *uint16  `json:"lap"`
	Gear         *uint8   `json:"gear"`
	Rpm          *float32 `json:"rpm"`
	Steer        *float32 `json:"steer"`
	SlipAngleDeg *float32 `json:"slip_angle_deg"`
}

// Message from topic motorsport.cv.events
type CVEvent struct {
	RunID          string          `json:"run_id"`
	FrameIdx       uint32          `json:"frame_idx"`
	TsMs           int64           `json:"ts_ms"`
	InferenceMs    float32         `json:"inference_ms"`
	NDetections    uint16          `json:"n_detections"`
	NHazards       uint16          `json:"n_hazards"`
	MinHazardDistM *float32        `json:"min_hazard_dist_m"`
	LateralOffset  *float32        `json:"lateral_offset"`
	ApexDist       *float32        `json:"apex_dist"`
	YawRateDegS    *float32        `json:"yaw_rate_deg_s"`
	SlipAngleDeg   *float32        `json:"slip_angle_deg"`
	SpeedEstKmh    *float32        `json:"speed_est_kmh"`
	Detections     json.RawMessage `json:"detections"`
}
