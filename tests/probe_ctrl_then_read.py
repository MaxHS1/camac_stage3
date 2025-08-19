import sys, pathlib, time
sys.path.insert(0, r"C:\DAQ\camac_stage3")
from camacdaq_py.camac_backend import CamacBackend

cam = CamacBackend(mode="visa", resource="GPIB0::16::INSTR")
try: cam.impl.dev.timeout = 200
except: pass
cam.impl._width_bytes = 2

ext = cam.cdreg(1,1,3,0)

# CONTROL first (e.g., F=24), ignore data value
d,q = cam.cfsa(24, ext, None)
print("CTRL F=24 A=0 -> Q=", q)
time.sleep(0.1)

# Then try reads
for f in (0,2,4):
    d,q = cam.cfsa(f, ext, None)
    print(f"READ F={f} A=0 -> Data={d} Q={q}")
