"""Writes a lap comparison to ClickHouse over HTTP (batch job, so no Kafka needed)."""
import base64
import json
import urllib.parse
import urllib.request


class ClickHouse:
    def __init__(self, url="http://localhost:8123", user="motorsport", password="motorsport"):
        self.url = url
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def run(self, sql, body=None):
        # With a body (insert data), the SQL goes in the URL; otherwise the SQL is the body
        if body is None:
            url, data = self.url, sql.encode()
        else:
            url, data = f"{self.url}/?query={urllib.parse.quote(sql)}", body
        req = urllib.request.Request(url, data=data, headers={"Authorization": self.auth})
        return urllib.request.urlopen(req, timeout=30).read().decode()

    def insert(self, table, rows):
        body = "\n".join(json.dumps(r) for r in rows).encode()
        self.run(f"INSERT INTO {table} FORMAT JSONEachRow", body)


def save(res, comparison, ch=None):
    ch = ch or ClickHouse()
    a, b, delta = res["a"], res["b"], res["delta"]
    A, B = res["lap_a"]["driver"], res["lap_b"]["driver"]
    for table in ("motorsport.lap_grid", "motorsport.lap_corners"):  # re-running replaces the old rows
        ch.run(f"DELETE FROM {table} WHERE comparison = '{comparison}'")

    ch.insert("motorsport.lap_grid", [{
        "comparison": comparison, "driver_a": A, "driver_b": B,
        "distance_m": float(a["d"][i]), "delta_s": float(delta[i]),
        "speed_a": float(a["speed"][i]), "speed_b": float(b["speed"][i]),
        "throttle_a": float(a["throttle"][i]), "throttle_b": float(b["throttle"][i]),
        "brake_a": int(a["brake"][i]), "brake_b": int(b["brake"][i]),
        "gear_a": int(a["gear"][i]), "gear_b": int(b["gear"][i]),
        "x": float(a["x"][i]), "y": float(a["y"][i]),
    } for i in range(len(a["d"]))])

    ch.insert("motorsport.lap_corners", [{
        "comparison": comparison, "corner": c["corner"], "apex_m": c["apex_m"],
        "time_diff_s": c["time_diff_s"],
        "faster": c["faster"], "why": c["why"],
        "brake_m_a": c["a"]["brake_m"], "brake_m_b": c["b"]["brake_m"],
        "min_speed_a": c["a"]["min_speed"], "min_speed_b": c["b"]["min_speed"],
    } for c in res["corners"]])
