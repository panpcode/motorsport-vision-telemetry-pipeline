"""
Records raw UDP telemetry packets from a racing game, with the PC's clock time.
Runs on Windows/Mac/Linux, standard Python 3 only (no installs).

    python record_udp_telemetry.py              # listens on port 20777
    python record_udp_telemetry.py --port 20778

Stop with Ctrl+C. Output: telemetry_<date>_<time>.csv  (ts_ns,packet_hex per line)
"""
import argparse
import socket
import time
from datetime import datetime


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=20777)
    args = p.parse_args()

    out = f"telemetry_{datetime.now():%Y%m%d_%H%M%S}.csv"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(1.0)

    print(f"Listening on UDP port {args.port}, writing {out}")
    print("Start OBS recording, then drive. Ctrl+C to stop.")
    count, sizes, last_print = 0, set(), time.time()
    with open(out, "w") as f:
        f.write("ts_ns,packet_hex\n")
        try:
            while True:
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    if count == 0 and time.time() - last_print > 5:
                        print("  no packets yet - is UDP telemetry enabled in the game?")
                        last_print = time.time()
                    continue
                f.write(f"{time.time_ns()},{data.hex()}\n")
                count += 1
                sizes.add(len(data))
                if time.time() - last_print > 5:
                    print(f"  {count} packets, sizes {sorted(sizes)} bytes")
                    last_print = time.time()
        except KeyboardInterrupt:
            pass
    print(f"Saved {count} packets to {out}")


if __name__ == "__main__":
    main()
