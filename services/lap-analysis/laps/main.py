"""Compare two drivers' laps: where time was gained or lost, and why.

    python -m laps.main --year 2025 --event "Yas Marina" --session Qualifying VER NOR
"""
import argparse
import os

from .compare import compare, fmt_lap, report
from .openf1 import find_session, load_lap
from .plot import plot


def main():
    p = argparse.ArgumentParser(description="Lap comparison from real F1 telemetry (OpenF1)")
    p.add_argument("driver_a", help="reference driver, e.g. VER")
    p.add_argument("driver_b", help="driver to compare, e.g. NOR")
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--event", default="Yas Marina", help="location, circuit or country name")
    p.add_argument("--session", default="Qualifying", help="Qualifying, Race, Practice 1, Sprint ...")
    p.add_argument("--lap-a", type=int, help="lap number (default: fastest)")
    p.add_argument("--lap-b", type=int)
    p.add_argument("--out", default="output", help="folder for the figure")
    p.add_argument("--clickhouse", help="save for Grafana, e.g. http://localhost:8123")
    args = p.parse_args()

    s = find_session(args.year, args.event, args.session)
    lap_a = load_lap(s["session_key"], args.driver_a, args.lap_a)
    lap_b = load_lap(s["session_key"], args.driver_b, args.lap_b)
    res = compare(lap_a, lap_b)
    name = f"{args.year} {s['location']} {args.session}: {args.driver_a} vs {args.driver_b}"
    res["title"] = f"{name}  ({fmt_lap(lap_a['lap_time'])} vs {fmt_lap(lap_b['lap_time'])})"

    print(name)
    print(report(res))

    os.makedirs(args.out, exist_ok=True)
    fig = os.path.join(args.out, f"laps_{args.year}_{s['location'].replace(' ', '_')}_{args.driver_a}_{args.driver_b}.png")
    plot(res, fig)
    print(f"\nfigure: {fig}")

    if args.clickhouse:
        from .store import ClickHouse, save
        save(res, name, ClickHouse(args.clickhouse))
        print(f"saved to ClickHouse as '{name}'")


if __name__ == "__main__":
    main()
