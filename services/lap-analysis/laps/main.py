"""Compare two laps: where time was gained or lost, and why.

    python -m laps.main --year 2025 --event "Yas Marina" --session Qualifying VER NOR
    python -m laps.main --csv sample-data/forza/<session>/telemetry.csv      # own game laps
"""
import argparse
import os

from .compare import compare, fmt_lap, report
from .plot import plot


def f1_laps(args):
    from .openf1 import find_session, load_lap

    if not (args.driver_a and args.driver_b):
        raise SystemExit("give two drivers, e.g. VER NOR (or --csv for game laps)")
    s = find_session(args.year, args.event, args.session)
    lap_a = load_lap(s["session_key"], args.driver_a, args.lap_a)
    lap_b = load_lap(s["session_key"], args.driver_b, args.lap_b)
    name = f"{args.year} {s['location']} {args.session}: {args.driver_a} vs {args.driver_b}"
    fig = f"laps_{args.year}_{s['location'].replace(' ', '_')}_{args.driver_a}_{args.driver_b}.png"
    return lap_a, lap_b, name, fig


def game_laps(args):
    from .game import load_pair

    (lap_a, lap_b), all_laps = load_pair(args.csv, args.lap_a, args.lap_b)
    print("laps: " + "  ".join(f"L{n} {fmt_lap(l['lap_time'])}" for n, l in sorted(all_laps.items())))
    session = os.path.basename(os.path.dirname(os.path.abspath(args.csv)))
    name = f"{session}: {lap_a['driver']} vs {lap_b['driver']}"
    return lap_a, lap_b, name, f"laps_{session}_{lap_a['driver']}_{lap_b['driver']}.png"


def main():
    p = argparse.ArgumentParser(description="Lap comparison from real F1 telemetry (OpenF1) or game telemetry")
    p.add_argument("driver_a", nargs="?", help="reference driver, e.g. VER")
    p.add_argument("driver_b", nargs="?", help="driver to compare, e.g. NOR")
    p.add_argument("--csv", help="game telemetry.csv (from scripts/decode_forza.py) instead of OpenF1")
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--event", default="Yas Marina", help="location, circuit or country name")
    p.add_argument("--session", default="Qualifying", help="Qualifying, Race, Practice 1, Sprint ...")
    p.add_argument("--lap-a", type=int, help="lap number (default: fastest)")
    p.add_argument("--lap-b", type=int, help="lap number (default: second fastest for --csv)")
    p.add_argument("--out", default="output", help="folder for the figure")
    p.add_argument("--clickhouse", help="save for Grafana, e.g. http://localhost:8123")
    args = p.parse_args()

    lap_a, lap_b, name, fig = game_laps(args) if args.csv else f1_laps(args)
    res = compare(lap_a, lap_b)
    res["title"] = f"{name}  ({fmt_lap(lap_a['lap_time'])} vs {fmt_lap(lap_b['lap_time'])})"

    print(name)
    print(report(res))
    if "game_distance_m" in lap_a:
        # Same check as the F1 sector times: our integrated distance vs the game's own odometer
        print(f"Distance check: integrated {res['length_m']:.0f} m vs game {lap_a['game_distance_m']:.0f} m")

    os.makedirs(args.out, exist_ok=True)
    fig = os.path.join(args.out, fig)
    plot(res, fig)
    print(f"\nfigure: {fig}")

    if args.clickhouse:
        from .store import ClickHouse, save
        save(res, name, ClickHouse(args.clickhouse))
        print(f"saved to ClickHouse as '{name}'")


if __name__ == "__main__":
    main()
