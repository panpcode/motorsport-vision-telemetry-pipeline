"""Builds wrc_telemetry.json (Grafana dashboard). Edit here, then: python dashboards/build_dashboard.py"""
import json
import os

DS = {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"}
RUN = "run_id = '${run_id}'"
_id = 0


def query(sql, fmt="time_series"):
    return {"datasource": DS, "refId": "A", "editorType": "sql", "rawSql": sql.strip(),
            "format": 0 if fmt == "time_series" else 1, "queryType": "timeseries" if fmt == "time_series" else "table"}


def panel(title, ptype, sql, x, y, w, h, fmt="time_series", unit=None, overrides=None, options=None, field=None):
    global _id
    _id += 1
    defaults = {"unit": unit} if unit else {}
    if field:
        defaults.update(field)
    p = {"id": _id, "type": ptype, "title": title, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [query(sql, fmt)],
         "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
         "options": options or {}}
    return p


def rename(field, name, color=None, right_axis_unit=None):
    props = [{"id": "displayName", "value": name}]
    if color:
        props.append({"id": "color", "value": {"mode": "fixed", "fixedColor": color}})
    if right_axis_unit:
        props += [{"id": "custom.axisPlacement", "value": "right"}, {"id": "unit", "value": right_axis_unit}]
    return {"matcher": {"id": "byName", "options": field}, "properties": props}


def stat(title, sql, x, unit, thresholds=None, decimals=1):
    field = {"decimals": decimals, "color": {"mode": "thresholds"},
             "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "blue", "value": None}]}}
    return panel(title, "stat", sql, x, 0, 4, 4, fmt="table", unit=unit, field=field,
                 options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"})


panels = [
    # Row 1: live numbers
    stat("Speed (GPS)", f"SELECT speed_kmh FROM wrc.telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts DESC LIMIT 1", 0, "velocitykmh"),
    stat("Speed (from video)", f"SELECT cv_speed_kmh FROM wrc.frames_with_telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts DESC LIMIT 1", 4, "velocitykmh"),
    stat("Hazards on road", f"SELECT n_hazards FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts DESC LIMIT 1", 8, "none",
         [{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 3}], decimals=0),
    stat("Nearest hazard", f"SELECT min_hazard_dist_m FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts DESC LIMIT 1", 12, "lengthm",
         [{"color": "red", "value": None}, {"color": "orange", "value": 15}, {"color": "green", "value": 30}], decimals=0),
    stat("Inference p95", f"SELECT quantile(0.95)(inference_ms) FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts)", 16, "ms",
         [{"color": "green", "value": None}, {"color": "orange", "value": 33}, {"color": "red", "value": 50}]),
    stat("Video/telemetry sync", f"SELECT max(abs(sync_gap_ms)) FROM wrc.frames_with_telemetry WHERE {RUN} AND $__timeFilter(ts)", 20, "ms",
         [{"color": "green", "value": None}, {"color": "orange", "value": 50}, {"color": "red", "value": 100}], decimals=0),

    # Row 2: speed + yaw, sensor vs vision
    panel("Speed: GPS vs video", "timeseries",
          f"SELECT ts, speed_kmh, cv_speed_kmh FROM wrc.frames_with_telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          0, 4, 12, 8, unit="velocitykmh",
          overrides=[rename("speed_kmh", "GPS", "blue"), rename("cv_speed_kmh", "Video (optical flow)", "orange")]),
    panel("Yaw rate: IMU vs video", "timeseries",
          f"SELECT ts, yaw_rate_deg_s, cv_yaw_rate_deg_s FROM wrc.frames_with_telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          12, 4, 12, 8, unit="deg/s",
          overrides=[rename("yaw_rate_deg_s", "IMU", "blue"), rename("cv_yaw_rate_deg_s", "Video (optical flow)", "orange")]),

    # Row 3: hazards + road position
    panel("Hazard distance (on-road objects)", "timeseries",
          f"SELECT ts, min_hazard_dist_m FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          0, 12, 12, 8, unit="lengthm",
          overrides=[rename("min_hazard_dist_m", "Nearest hazard")],
          field={"color": {"mode": "thresholds"},
                 "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "orange", "value": 15}, {"color": "green", "value": 30}]},
                 "custom": {"drawStyle": "points", "pointSize": 6, "thresholdsStyle": {"mode": "line+area"}}}),
    panel("Road position & slip", "timeseries",
          f"SELECT ts, lateral_offset, cv_slip_angle_deg FROM wrc.frames_with_telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          12, 12, 12, 8,
          overrides=[rename("lateral_offset", "Lateral offset (-1 left edge, +1 right edge)", "green"),
                     rename("cv_slip_angle_deg", "Slip angle", "purple", right_axis_unit="degree")]),

    # Row 4: map + hazard log
    panel("GPS track", "geomap",
          f"SELECT lat, lon, speed_kmh FROM wrc.telemetry WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          0, 20, 12, 10, fmt="table",
          options={"view": {"id": "fit", "lat": 0, "lon": 0, "zoom": 15},
                   "basemap": {"type": "osm-standard", "name": "Map"},
                   "layers": [{"type": "markers", "name": "Track",
                               "location": {"mode": "coords", "latitude": "lat", "longitude": "lon"},
                               "config": {"size": {"fixed": 4}, "color": {"field": "speed_kmh", "fixed": "blue"}}}],
                   "controls": {"showZoom": True}},
          field={"color": {"mode": "continuous-BlYlRd"}}),
    panel("Hazard alerts (< 20 m)", "table",
          f"""SELECT ts, frame_idx, round(min_hazard_dist_m) AS distance_m, n_hazards,
       arrayStringConcat(arrayDistinct(arrayMap(d -> JSONExtractString(d, 'cls'),
           arrayFilter(d -> JSONExtractBool(d, 'hazard'), JSONExtractArrayRaw(detections)))), ', ') AS objects
FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts) AND min_hazard_dist_m < 20 ORDER BY ts DESC LIMIT 50""",
          12, 20, 12, 10, fmt="table"),

    # Row 5: pipeline health
    panel("CV inference time", "timeseries",
          f"SELECT ts, inference_ms FROM wrc.cv_events WHERE {RUN} AND $__timeFilter(ts) ORDER BY ts",
          0, 30, 24, 6, unit="ms", overrides=[rename("inference_ms", "YOLOv8 inference")]),
]

dashboard = {
    "uid": "wrc-telemetry",
    "title": "WRC Vision + Telemetry",
    "tags": ["wrc", "telemetry", "computer-vision"],
    "timezone": "browser",
    "refresh": "1s",
    "time": {"from": "now-1m", "to": "now"},
    "schemaVersion": 39,
    "templating": {"list": [{
        "name": "run_id", "label": "Run", "type": "query", "datasource": DS,
        "query": "SELECT run_id FROM wrc.cv_events GROUP BY run_id ORDER BY max(ts) DESC",
        "definition": "SELECT run_id FROM wrc.cv_events GROUP BY run_id ORDER BY max(ts) DESC",
        "refresh": 2, "current": {}, "options": [],
    }]},
    "panels": panels,
}



def write(dash, name):
    out = os.path.join(os.path.dirname(__file__), name)
    with open(out, "w") as f:
        json.dump(dash, f, indent=2)
    print(f"wrote {out}")


if __name__ == "__main__":
    write(dashboard, "wrc_telemetry.json")
