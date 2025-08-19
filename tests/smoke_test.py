#!/usr/bin/env python3
"""
Simple end-to-end smoke test for the CAMAC Python rewrite.

Usage (examples):
  python tests/smoke_test.py --cfg config\daq.cfg --mode visa --resource "GPIB0::16::INSTR"
  python tests/smoke_test.py --cfg config\daq.cfg --mode visa --resource "GPIB0::16::INSTR" --module QVT --addr 0 --func 0
"""

import argparse
import pathlib
import sys

# ensure we can import the project package
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from camacdaq_py.camac_backend import CamacBackend
from camacdaq_py.daq_system import DAQSystem

def main():
    ap = argparse.ArgumentParser(description="CAMAC smoke test (list + read + optional write)")
    ap.add_argument("--cfg", required=True, help="Path to daq.cfg (plain format: NAME BRANCH CRATE STATION ...)")
    ap.add_argument("--mode", choices=["auto","real","mock","visa"], default="visa")
    ap.add_argument("--resource", help="VISA resource, e.g. GPIB0::16::INSTR")
    ap.add_argument("--lib", help="Path to native lib (for --mode real)")
    ap.add_argument("--module", default="QVT", help="Module name in cfg for read test (default: QVT)")
    ap.add_argument("--addr", type=lambda s:int(s,0), default=0, help="CAMAC address (A) to read (default: 0)")
    ap.add_argument("--func", type=int, default=0, help="CAMAC function (F) for read 0..7 (default: 0)")

    # Optional write test
    ap.add_argument("--write-module", default=None, help="Module name in cfg for write test (e.g., GATE)")
    ap.add_argument("--write-addr", type=lambda s:int(s,0), default=0, help="CAMAC address (A) to write")
    ap.add_argument("--write-func", type=int, default=16, help="CAMAC write function (16..23) (default: 16)")
    ap.add_argument("--write-data", type=lambda s:int(s,0), default=0x1234, help="Data to write (default: 0x1234)")

    args = ap.parse_args()

    print(f"[INFO] Backend mode={args.mode}  resource={args.resource or ''}  lib={args.lib or ''}")
    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    daq = DAQSystem(cam)

    text = pathlib.Path(args.cfg).read_text()
    names = daq.load_cfg_text(text)

    if not names:
        print("[FAIL] No modules parsed from cfg. Check format: 'NAME BRANCH CRATE STATION [comment]'.")
        return 2

    print("[OK] Parsed modules:")
    for name, br, cr, st, cmt in daq.list_modules():
        print(f"  - {name:6s}  B={br} C={cr} N={st}  {cmt or ''}".rstrip())

    # Read test
    try:
        data, q = daq.camac_read(args.module, args.addr, args.func)
        print(f"[OK] READ {args.module} A={args.addr} F={args.func}  => Data={data} (0x{data:X})  Q={q}")
    except Exception as e:
        print(f"[FAIL] READ {args.module} A={args.addr} F={args.func}  => {e}")
        return 3

    # Optional write test
    if args.write_module:
        try:
            q = daq.camac_write(args.write_module, args.write_addr, args.write_func, args.write_data)
            print(f"[OK] WRITE {args.write_module} A={args.write_addr} F={args.write_func} Data=0x{args.write_data:X}  Q={q}")
        except Exception as e:
            print(f"[FAIL] WRITE {args.write_module} A={args.write_addr} F={args.write_func} Data=0x{args.write_data:X}  => {e}")
            return 4

    print("[DONE] Smoke test finished.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
