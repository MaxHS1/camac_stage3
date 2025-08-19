# bin/capture.py
from __future__ import annotations
import argparse, csv, subprocess, sys, time
from datetime import datetime
from pathlib import Path

def run_read(cfg: str, mode: str, resource: str|None, module: str, address: int, function: int|None):
    cmd = [sys.executable, str(Path(__file__).with_name("daq.py")), "--cfg", cfg, "--mode", mode]
    if resource and mode == "visa":
        cmd += ["--resource", resource]
    cmd += ["read", module, str(address)]
    if function is not None:
        cmd += ["--function", str(function)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "daq.py read failed")
    # daq.py prints just the integer value (by design)
    return int(p.stdout.strip())

def main():
    ap = argparse.ArgumentParser(description="Capture repeated CAMAC reads to CSV")
    ap.add_argument("--cfg", required=True, help="Path to daq.cfg")
    ap.add_argument("--mode", choices=["mock","visa","real","auto"], default="mock")
    ap.add_argument("--resource", help='VISA resource, e.g. "GPIB0::16::INSTR" (visa mode only)')
    ap.add_argument("--module", required=True, help="Module name as in daq.cfg (e.g., QVT)")
    ap.add_argument("--address", type=int, required=True, help="CAMAC A (subaddress)")
    ap.add_argument("--function", type=int, help="CAMAC F (default: 0 for read)")
    ap.add_argument("--interval", type=float, default=0.5, help="Seconds between reads")
    ap.add_argument("--count", type=int, default=10, help="Number of samples")
    ap.add_argument("--out", required=True, help="Output CSV path")
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fn = args.function if args.function is not None else 0

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for _ in range(args.count):
            ts = datetime.now().isoformat(timespec="milliseconds")
            try:
                val = run_read(args.cfg, args.mode, args.resource, args.module, args.address, fn)
            except Exception as e:
                val = ""
                # write the error to stderr but keep the CSV row (blank value)
                print(f"[capture] read error: {e}", file=sys.stderr)
            w.writerow([ts, val])
            f.flush()
            time.sleep(max(0.0, args.interval))
    print(f"Wrote {args.count} rows to {args.out}")

if __name__ == "__main__":
    main()