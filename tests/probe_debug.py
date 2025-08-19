import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend

cam = CamacBackend(mode="visa", resource="GPIB0::16::INSTR")
try: cam.impl.dev.timeout = 200
except: pass

# try 16-bit first; change to 3 or 1 after this test
cam.impl._width_bytes = 1
cam.impl.set_debug(1)   # <<< enable binary prints

ext = cam.cdreg(1,1,3,0)     # B=1, C=1, N=3, A=0
d,q = cam.cfsa(0, ext, None) # F=0 read variant
print("RESULT F=0 A=0:", d, q)
