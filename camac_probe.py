#!/usr/bin/env python3
"""
camac_probe.py — Safe sweep tester for KS 3988 via CamacBackendNI

- Reads stations from a config like:
    # name  branch crate station
    QVT   1 1 2
    GATE  1 1 9
    ADC   1 1 15
    HV    1 1 19
- Sweeps subaddresses (A) and function codes (F) with short timeouts.
- Never hangs: catches VISA timeouts and keeps going.
- Prints a summary of any 'hits' (Q=1, X=1, or nonzero data).

Usage examples:
    python camac_probe.py --cfg .\\config\\daq.cfg --resource GPIB0::16::INSTR
    python camac_probe.py --cfg daq.cfg --resource GPIB0::16::INSTR --a 0-3 --f 0-31 --timeout 300
"""

import argparse
import pathlib
import sys
import time
from typing import Dict, List, Tuple

try:
    from camac_backend_win import CamacBackendNI
except Exception as e:
    print(f"ERROR: import CamacBackendNI failed: {e}")
    sys.exit(1)


def parse_cfg(path: pathlib.Path) -> Dict[str, int]:
    """Return {NAME: stationN} from the cfg file."""
    stations = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.replace(",", " ").split()
        if len(parts) >= 4:
            name = parts[0]
            try:
                # branch = int(parts[1]); crate = int(parts[2]);
                n = int(parts[3])
                stations[name] = n
            except Exception:
                pass
    return stations


def parse_range(s: str, lo: int, hi: int) -> List[int]:
    """Parse 'a-b' or single 'n' into a clamped inclusive list."""
    if "-" in s:
        a, b = s.split("-", 1)
        a = max(lo, min(hi, int(a)))
        b = max(lo, min(hi, int(b)))
        if a > b:
            a, b = b, a
        return list(range(a, b + 1))
    else:
        v = max(lo, min(hi, int(s)))
        return [v]


def main():
    ap = argparse.ArgumentParser(description="Safe CAMAC probe (NI GPIB + KS 3988)")
    ap.add_argument("--cfg", required=True, help="Path to daq.cfg")
    ap.add_argument("--resource", default="GPIB0::16::INSTR", help="VISA resource, e.g. GPIB0::16::INSTR")
    ap.add_argument("--timeout", type=int, default=500, help="Per-call VISA timeout in ms (default 500)")
    ap.add_argument("--a", default="0-3", help="Subaddress A range (e.g. '0-3' or '0')")
    ap.add_argument("--f", default="0-31", help="Function F range (e.g. '0-7' or '0-31')")
    ap.add_argument("--repeats", type=int, default=1, help="Optional repeats per (N,A,F)")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.cfg)
    if not cfg_path.exists():
        print(f"ERROR: cfg not found: {cfg_path}")
        sys.exit(2)

    stations = parse_cfg(cfg_path)
    if not stations:
        print("ERROR: no stations parsed from cfg.")
        sys.exit(3)

    a_list = parse_range(args.a, 0, 15)
    f_list = parse_range(args.f, 0, 31)

    print("=== Probe plan ===")
    for name, n in stations.items():
        print(f"  {name:>6} -> N={n}")
    print(f"  A range : {a_list}")
    print(f"  F range : {f_list}")
    print(f"  repeats : {args.repeats}")
    print(f"  resource: {args.resource}")
    print(f"  timeout : {args.timeout} ms")
    print("==================")

    # Init backend with short timeout
    cam = CamacBackendNI(resource=args.resource, timeout_ms=args.timeout)

    # Optional: crate init (status-only; should not hang)
    try:
        cam.cccz()
    except Exception as e:
        print(f"Warning: cccz failed: {e}")

    hits: List[Tuple[str,int,int,int,int,int,int]] = []
    total = len(stations) * len(a_list) * len(f_list) * max(1, args.repeats)
    i = 0

    t0 = time.time()
    try:
        for name, n in stations.items():
            for A in a_list:
                ext = cam.cdreg(0, n, A, 0)
                for F in f_list:
                    for r in range(max(1, args.repeats)):
                        i += 1
                        # progress line
                        print(f"\r[{i}/{total}] {name}: N={n} A={A} F={F} try={r+1}   ", end="", flush=True)
                        try:
                            q, x, d = cam.cfsa(F, ext)
                            if q or x or d:
                                hits.append((name, n, A, F, q, x, (d if d is not None else -1)))
                                print(f"\n   HIT -> {name} N={n} A={A} F={F}  Q={q} X={x} D={d}")
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            # swallow timeouts/IO errors; continue
                            # print(f"\n   ERR {name} N={n} A={A} F={F}: {e}")
                            pass
        print()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    dt = time.time() - t0
    print("\n=== Summary ===")
    print(f"Elapsed: {dt:.2f} s, Probed: {i} cycles")
    if not hits:
        print("No hits (Q/X/data all zero). Try adjusting A/F ranges or verify module power.")
    else:
        # Deduplicate hits
        dedup = {}
        for h in hits:
            key = h[:4]  # (name,n,A,F)
            dedup.setdefault(key, h)
        print(f"{len(dedup)} unique (N,A,F) with activity:")
        for (name, n, A, F), (_n1,_n2,_n3,_n4,q,x,d) in dedup.items():
            d_str = "None" if d == -1 else str(d)
            print(f"  {name:>6}  N={n:>2} A={A:>2} F={F:>2}  -> Q={q} X={x} D={d_str}")


if __name__ == "__main__":
    main()