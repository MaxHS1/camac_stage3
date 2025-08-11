
#!/usr/bin/env python3
import argparse, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend
from camacdaq_py.daq_system import DAQSystem

def main():
    ap = argparse.ArgumentParser(description="DAQ CLI (real/mock/visa backend)")
    ap.add_argument("--cfg", required=True, help="Path to CIT-style daq.cfg")
    ap.add_argument("--mode", choices=["auto","real","mock","visa"], default="auto", help="Backend selection")
    ap.add_argument("--lib", help="Path to CAMAC shared library (.so/.dylib/.dll)")
    ap.add_argument("--resource", help="VISA resource string (e.g., GPIB0::1::INSTR)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List modules")

    p_read = sub.add_parser("read", help="Read from module")
    p_read.add_argument("name")
    p_read.add_argument("address", type=lambda s:int(s,0))
    p_read.add_argument("--function", "-f", type=int, default=0, help="CAMAC function (0..7 read)")

    p_write = sub.add_parser("write", help="Write to module")
    p_write.add_argument("name")
    p_write.add_argument("address", type=lambda s:int(s,0))
    p_write.add_argument("function", type=int, help="CAMAC function (16..23 write)")
    p_write.add_argument("data", type=lambda s:int(s,0))

    args = ap.parse_args()

    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    daq = DAQSystem(cam)

    text = pathlib.Path(args.cfg).read_text()
    daq.load_cfg_text(text)

    if args.cmd == "list":
        for name, br, cr, st, cmt in daq.list_modules():
            print(f"{name:6s}  B={br} C={cr} N={st}  {cmt or ''}".rstrip())
    elif args.cmd == "read":
        data, q = daq.camac_read(args.name, args.address, args.function)
        print(f"Data={data} (0x{data:X})  Q={q}")
    elif args.cmd == "write":
        q = daq.camac_write(args.name, args.address, args.function, args.data)
        print(f"Write Q={q}")

if __name__ == "__main__":
    main()
