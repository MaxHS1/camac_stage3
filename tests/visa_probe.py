import sys, pyvisa

# Use your address; change if MAX shows a different PAD
RESOURCE = sys.argv[1] if len(sys.argv) > 1 else "GPIB0::16::INSTR"

rm = pyvisa.ResourceManager()
print("Backends:", rm)
print("Opening:", RESOURCE)

d = rm.open_resource(RESOURCE)
# Raw binary: no ASCII terminations
d.write_termination = None
d.read_termination  = None
d.send_end = True
d.timeout = 3000  # 3s

def try_write(label, payload: bytes):
    try:
        n = d.write_raw(payload)
        print(f"{label}: wrote {n} bytes OK")
    except Exception as e:
        print(f"{label}: FAILED -> {e!r}")

# 1) Single byte handshake test (EOI asserted)
try_write("WRITE \\x18", b"\x18")

# 2) Minimal CAMAC frame (example NAF envelope variant your code uses)
try_write("WRITE 02 00 00", b"\x02\x00\x00")
