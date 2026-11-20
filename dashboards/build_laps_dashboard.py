"""Builds lap_comparison.json (Grafana dashboard). Edit here, then: python dashboards/build_laps_dashboard.py"""
from build_dashboard import DS, panel, rename, write

CMP = "comparison = '${comparison}'"
A, B = "blue", "orange"


DIST = {"matcher": {"id": "byName", "options": "distance_m"},
        "properties": [{"id": "unit", "value": "lengthm"}, {"id": "decimals", "value": 1}]}


def limits(field, lo, hi):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "min", "value": lo}, {"id": "max", "value": hi}]}


def trend(title, sql, y, h, unit=None, overrides=None, field=None):
    # The panel unit would also apply to the x axis, so distance gets its own
    return panel(title, "trend", sql, 0, y, 16, h, fmt="table", unit=unit, overrides=[DIST] + (overrides or []),
                 options={"xField": "distance_m", "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                          "tooltip": {"mode": "multi"}},
                 field={"custom": {"lineWidth": 2, "fillOpacity": 0}, **(field or {})})


def text_stat(title, sql, x, w, color="text", unit=None, decimals=3):
    return panel(title, "stat", sql, x, 0, w, 4, fmt="table", unit=unit,
                 field={"decimals": decimals, "color": {"mode": "fixed", "fixedColor": color}},
                 options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/"},
                          "colorMode": "value", "graphMode": "none", "textMode": "value"})


def var(name, sql, hide=0, label=None):
    return {"name": name, "label": label or name, "type": "query", "datasource": DS, "query": sql,
            "definition": sql, "refresh": 1, "hide": hide, "current": {}, "options": []}




def map_sql(col, cond):
    # Mini-sectors of 200 m: points of the track where this driver gained time
    return f"""WITH ms AS (
    SELECT intDiv(toUInt32(distance_m), 200) AS m, argMax(delta_s, distance_m) - argMin(delta_s, distance_m) AS gain
    FROM wrc.lap_grid WHERE {CMP} GROUP BY m)
SELECT g.x AS x, g.y AS {col}
FROM wrc.lap_grid g JOIN ms ON intDiv(toUInt32(g.distance_m), 200) = ms.m
WHERE g.{CMP} AND ms.gain {cond} ORDER BY g.distance_m"""


track_map = panel("Faster per 200 m", "xychart", map_sql("a_faster", "> 0"), 16, 4, 8, 14, fmt="table",
                  overrides=[rename("a_faster", "${a}", A), rename("b_faster", "${b}", B)],
                  options={"seriesMapping": "manual",
                           "series": [{"x": "x", "y": "a_faster", "frame": 0, "name": "${a}"},
                                      {"x": "x", "y": "b_faster", "frame": 1, "name": "${b}"}],
                           "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                           "tooltip": {"mode": "none"}},
                  field={"custom": {"show": "points", "pointSize": {"fixed": 5}, "axisPlacement": "hidden"}})
track_map["targets"].append({**track_map["targets"][0], "refId": "B", "rawSql": map_sql("b_faster", "<= 0")})

HELP = """Two real laps (OpenF1), compared **by distance**, not by time.

- **Gap**: going up = ${b} losing time there, going down = gaining it back.
- **Corners** (table): time won between the straight before and the straight after.
  *why* = what the faster driver did differently at that corner.
- Checked against official F1 sector times (typically 0.03 s off, then corrected).

Data is ~4 samples/s, so braking points are ±15 m and the gap line
can swing inside slow corners. Corner totals are the reliable part."""

panels = [
    # Row 1: headline numbers
    text_stat("Lap gap (${b} to ${a})",
              f"SELECT concat(toString(round(argMax(delta_s, distance_m), 3)), ' s') FROM wrc.lap_grid WHERE {CMP}", 0, 6),
    text_stat("Biggest single gain",
              f"""SELECT concat(faster, ' +', toString(round(abs(time_diff_s), 3)), ' s in C', toString(corner))
FROM wrc.lap_corners WHERE {CMP} ORDER BY abs(time_diff_s) DESC LIMIT 1""", 6, 10),
    text_stat("Corners won (${a} / ${b})",
              f"""SELECT concat(toString(countIf(time_diff_s > 0)), ' / ', toString(countIf(time_diff_s < 0)))
FROM wrc.lap_corners WHERE {CMP}""", 16, 8),

    # Left column: traces by distance
    trend("Gap by distance (above 0: ${a} ahead)",
          f"SELECT distance_m, delta_s FROM wrc.lap_grid WHERE {CMP} ORDER BY distance_m", 4, 7, unit="s",
          overrides=[rename("delta_s", "Gap ${b} to ${a}", "purple")],
          field={"custom": {"lineWidth": 2, "fillOpacity": 20, "gradientMode": "opacity"}}),
    trend("Speed",
          f"SELECT distance_m, speed_a, speed_b FROM wrc.lap_grid WHERE {CMP} ORDER BY distance_m", 11, 8, unit="velocitykmh",
          overrides=[rename("speed_a", "${a}", A), rename("speed_b", "${b}", B)]),
    trend("Throttle",
          f"SELECT distance_m, throttle_a, throttle_b FROM wrc.lap_grid WHERE {CMP} ORDER BY distance_m", 19, 5, unit="percent",
          overrides=[rename("throttle_a", "${a}", A), rename("throttle_b", "${b}", B)]),
    trend("Brake",
          f"SELECT distance_m, brake_a, brake_b * -1 AS brake_b FROM wrc.lap_grid WHERE {CMP} ORDER BY distance_m", 24, 4,
          overrides=[rename("brake_a", "${a}", A), rename("brake_b", "${b} (shown below 0)", B),
                     limits("brake_a", -1, 1), limits("brake_b", -1, 1)],
          field={"custom": {"lineWidth": 1, "fillOpacity": 60, "lineInterpolation": "stepAfter", "axisPlacement": "hidden"}}),

    # Right: track map. Bottom: corner table
    track_map,
    panel("How to read this", "text", "", 16, 18, 8, 10,
          options={"mode": "markdown", "content": HELP}),
    panel("Where time was won", "table",
          f"""SELECT corner AS C, round(apex_m) AS at_m, faster, round(abs(time_diff_s), 3) AS gain_s, why,
       round(min_speed_a) AS min_kmh_${{a}}, round(min_speed_b) AS min_kmh_${{b}}
FROM wrc.lap_corners WHERE {CMP} ORDER BY corner""", 0, 28, 24, 9, fmt="table",
          overrides=[{"matcher": {"id": "byName", "options": n}, "properties": [{"id": "custom.width", "value": w}]}
                     for n, w in [("C", 50), ("at_m", 80), ("faster", 80), ("gain_s", 80)]]
          + [{"matcher": {"id": "byName", "options": "gain_s"}, "properties": [{"id": "decimals", "value": 3}]}]),
]

dashboard = {
    "uid": "wrc-laps",
    "title": "Lap Comparison",
    "tags": ["wrc", "laps"],
    "schemaVersion": 39,
    "time": {"from": "now-1h", "to": "now"},
    "templating": {"list": [
        var("comparison", "SELECT comparison FROM wrc.lap_grid GROUP BY comparison ORDER BY comparison", label="Comparison"),
        var("a", f"SELECT any(driver_a) FROM wrc.lap_grid WHERE {CMP}", hide=2),
        var("b", f"SELECT any(driver_b) FROM wrc.lap_grid WHERE {CMP}", hide=2),
    ]},
    "panels": panels,
}

if __name__ == "__main__":
    write(dashboard, "lap_comparison.json")
