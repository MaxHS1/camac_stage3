#!/usr/bin/env python3
import argparse, pathlib, sys, csv, time, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend
from camacdaq_py.daq_system import DAQSystem

def now_iso():
    return dt.datetime.now().isoformat(timespec="milliseconds")

def parse_targets(spec: str):
    """
    spec format:  NAME:A:F;NAME2:A2:F2;...
    A and F are integers (0x.. ok). Example: "QVT:0:0;GATE:0:0"
    """
    out=[]
    for part in spec.split(";"):
        part=part.strip()
        if not part: continue
        name, a, f = part.split(":")
        out.append((name, int(a,0), int(f)))
    return out

def main():
    ap = argparse.ArgumentParser(description="Continuous CAMAC acquisition to CSV")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--mode", choices=["auto","real","mock","visa"], default="visa")
    ap.add_argument("--resource")
    ap.add_argument("--lib")
    ap.add_argument("--targets", required=True, help='Semi-colon list: NAME:A:F;NAME2:A2:F2 (e.g., "QVT:0:0;GATE:0:0")')
    ap.add_argument("--rate", type=float, default=10.0, help="Samples per second per target (default 10 Hz)")
    ap.add_argument("--duration", type=float, default=10.0, help="Seconds to run (default 10)")
    ap.add_argument("--out", default=None, help="Output CSV file (default logs/acq_YYYYmmdd_HHMMSS.csv)")
    args = ap.parse_args()

    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    daq = DAQSystem(cam)
    text = pathlib.Path(args.cfg).read_text()
    daq.load_cfg_text(text)

    targets = parse_targets(args.targets)
    if not targets:
        raise SystemExit("No targets parsed. Example: --targets \"QVT:0:0;GATE:0:0\"")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = pathlib.Path(args.out or f"logs/acq_{ts}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    period = 1.0 / max(1e-9, args.rate)
    print(f"[INFO] targets={targets}  rate={args.rate} Hz  duration={args.duration}s  csv={out_path}")

    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","module","address","function","data_dec","data_hex","q"])
        t_end = time.perf_counter() + args.duration
        next_tick = time.perf_counter()
        n=0
        while time.perf_counter() < t_end:
            for name, a, fn in targets:
                data, q = daq.camac_read(name, a, fn)
                w.writerow([now_iso(), name, a, fn, data, f"0x{data:X}", int(bool(q))])
            n += 1
            next_tick += period
            sleep = next_tick - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
        print(f"[DONE] wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
