# camac_backend_win.py
import os, struct, time
from typing import Optional, Tuple, Callable, List
from pyvisa import ResourceManager

DBG = os.environ.get("CAMAC_DEBUG", "0") not in ("", "0", "false", "False")

def log(msg: str):
    if DBG:
        ts = time.strftime("%H:%M:%S") + f".{int((time.time()%1)*1000):03d}"
        print(f"[{ts}] {msg}", flush=True)

class CamacBackendNI:
    """
    CAMAC backend for a Kinetic Systems 3988 GPIB–CAMAC controller via NI-VISA.
    - Auto-probes several N-A-F encodings and caches the first that returns data.
    - Crate-control functions read status only (no data), preventing timeouts.
    Usage:
        cam = CamacBackendNI("GPIB0::16::INSTR")
        ext = cam.cdreg(0, 5, 0, 0)
        q,x,d = cam.cfsa(0, ext)
        cam.cccz()
    """

    def __init__(self, resource: str = "GPIB0::16::INSTR", timeout_ms: int = 2000):
        rm = ResourceManager()
        self.dev = rm.open_resource(resource)
        self.dev.timeout = timeout_ms
        # raw binary I/O
        self.dev.write_termination = ""
        self.dev.read_termination  = ""
        self._naf_encoder: Optional[Callable[[int,int,int,int,bool], bytes]] = None
        self._expect_status_only_overrides = set()  # f codes we know are status-only
        log(f"[GPIB] OPEN {resource} (timeout {timeout_ms} ms)")

    # ------------------------
    # Required GUI helpers
    # ------------------------
    def cdreg(self, _ext_unused, n: int, a: int, f: int):
        """Return a simple handle for station/subaddress (N,A)."""
        return (n & 0x1F, a & 0x0F, f & 0x1F)

    # ------------------------
    # Core cycle with auto-probe
    # ------------------------
    def cfsa(self, f: int, ext, data: int = 0) -> Tuple[int,int,Optional[int]]:
        """
        Perform one CAMAC cycle.
        Returns (Q, X, data_or_None). For writes, data_or_None is None.
        Auto-probes several N-A-F encodings on first successful read.
        """
        n, a, _ = ext
        is_read = (f < 16)
        # Special handling: some crate control ops are status-only
        status_only = (f in self._expect_status_only_overrides)

        # Build candidates (encoder functions) to try until one returns non-timeout.
        if self._naf_encoder is None:
            candidates: List[Callable[[int,int,int,int,bool], bytes]] = [
                _enc_triplet_big,      # [N(5)|A(4)|F(6)|0] -> 3 bytes BE   (our first guess)
                _enc_triplet_little,   # same bits but LE ordering
                _enc_triplet_msblow,   # MSB..LSB padding variant
                _enc_triplet_with_data_header,  # add simple header before NAF
            ]
        else:
            # we already learned a working encoder
            candidates = [self._naf_encoder]

        last_err = None
        for enc in candidates:
            try:
                payload = enc(n, a, f, data, is_read)
                # For writes, append 3-byte data if encoder didn’t already
                if not is_read and _needs_data_after_cmd(enc):
                    payload += struct.pack(">I", data)[1:]  # 3 bytes MSB→LSB

                # Write command
                _w(self.dev, payload)

                if is_read and not status_only:
                    # Try reading 3 data bytes; if short, keep reading a bit more
                    datab = _r(self.dev, 3, tolerate_short=True)
                    if len(datab) < 3:
                        # not enough? maybe controller sends combined data+status later
                        more = _r(self.dev, 1, tolerate_short=True)
                        datab += more
                    if len(datab) >= 3:
                        d = (datab[0] << 16) | (datab[1] << 8) | datab[2]
                    else:
                        # data not delivered in this variant; try next encoder
                        raise TimeoutError("no 24-bit data returned")

                    # Status (best-effort)
                    statusb = _r(self.dev, 1, tolerate_short=True)
                    q, x = _parse_status(statusb[0]) if statusb else (0,0)
                    self._naf_encoder = enc  # cache working encoder
                    return (q, x, d)

                else:
                    # status-only path (write or crate control)
                    statusb = _r(self.dev, 1, tolerate_short=True)
                    q, x = _parse_status(statusb[0]) if statusb else (0,0)
                    self._naf_encoder = enc  # cache
                    return (q, x, None)

            except Exception as e:
                last_err = e
                log(f"[NAF] encoder {enc.__name__} failed: {e}")

        # If we get here, nothing worked
        if is_read and not status_only:
            log("[NAF] all encoders failed to fetch data; returning (0,0,0)")
            return (0,0,0)
        else:
            log("[NAF] all encoders failed on status-only op; returning (0,0,None)")
            return (0,0,None)

    # ------------------------
    # Multi-word loop
    # ------------------------
    def cssa(self, f: int, ext, count: int, data_buf=None):
        out = []
        for i in range(count):
            d_in = 0 if data_buf is None else data_buf[i]
            out.append(self.cfsa(f, ext, d_in))
        return out

    # ------------------------
    # Crate control (status-only)
    # ------------------------
    def cccc(self):
        """Crate Clear (C)."""
        self._expect_status_only_overrides.update({9})
        self.cfsa(9, (30, 0, 0))

    def cccz(self):
        """Crate Initialize (Z)."""
        self._expect_status_only_overrides.update({8})
        self.cfsa(8, (30, 0, 0))

    def ccci(self, inhibit: bool):
        """Crate Inhibit (I) set/clear (status-only)."""
        f = 17 if inhibit else 16
        self._expect_status_only_overrides.update({16,17})
        self.cfsa(f, (30, 0, 0))

    def test_lam(self, n: int) -> bool:
        # Standard CAMAC often uses F8 A0 to test LAM — treat as read (may or may not return data)
        q, x, _d = self.cfsa(8, (n & 0x1F, 0, 0))
        return bool(q)

    def clear_lam(self, n: int):
        # F10 A0 clear LAM, status-only
        self._expect_status_only_overrides.add(10)
        self.cfsa(10, (n & 0x1F, 0, 0))

    # Convenience
    def read_module(self, n: int, a: int = 0, f: int = 0):
        return self.cfsa(f, (n & 0x1F, a & 0x0F, f & 0x1F))

    def write_module(self, n: int, a: int, f: int, data: int):
        return self.cfsa(f, (n & 0x1F, a & 0x0F, f & 0x1F), data)

# ------------------------
# Encoder variants
# ------------------------

def _enc_triplet_big(n,a,f,data,is_read) -> bytes:
    """
    Pack N-A-F into 24-bit command: [N(5)|A(4)|F(6)|0] big-endian triplet.
    """
    cmd = ((n & 0x1F) << 11) | ((a & 0x0F) << 7) | ((f & 0x3F) << 1)
    b = cmd.to_bytes(3, "big")
    log(f"[ENC big] N={n} A={a} F={f} -> {b.hex()}")
    return b

def _enc_triplet_little(n,a,f,data,is_read) -> bytes:
    """
    Same bit layout but little-endian ordering of the 3 bytes.
    """
    cmd = ((n & 0x1F) << 11) | ((a & 0x0F) << 7) | ((f & 0x3F) << 1)
    b = cmd.to_bytes(3, "little")
    log(f"[ENC lit] N={n} A={a} F={f} -> {b.hex()}")
    return b

def _enc_triplet_msblow(n,a,f,data,is_read) -> bytes:
    """
    Variant with an extra 0 low bit (some docs show F<<1|0) and MSB-first padding already covered.
    Here we just reuse big but ensure the low spare bit is 0 (already the case).
    """
    return _enc_triplet_big(n,a,f,data,is_read)

def _enc_triplet_with_data_header(n,a,f,data,is_read) -> bytes:
    """
    Some controllers expect an initial 'mode' or 'cmd' byte before the NAF triplet.
    Use 0x31 as a harmless probe (commonly '16-bit single' on some devices).
    """
    core = _enc_triplet_big(n,a,f,data,is_read)
    b = bytes([0x31]) + core
    log(f"[ENC hdr] 31 + {core.hex()} -> {b.hex()}")
    return b

def _needs_data_after_cmd(enc: Callable) -> bool:
    """Return True if encoder didn’t include data already for write cycles."""
    # All our encoders currently put only the command; data follows separately.
    return True

def _parse_status(b: int) -> Tuple[int,int]:
    """
    Heuristic: bit0 = Q, bit1 = X  (adjust once manual is confirmed)
    """
    q = b & 1
    x = (b >> 1) & 1
    return q, x

# ------------------------
# I/O helpers (with small reads tolerant mode)
# ------------------------

def _w(dev, data: bytes):
    log(f"[WRITE] {data.hex()}")
    dev.write_raw(data)

def _r(dev, n: int, tolerate_short: bool=False) -> bytes:
    try:
        buf = dev.read_bytes(n)
        log(f"[READ ] ({n} req) {buf.hex()}")
        return buf
    except Exception as e:
        if tolerate_short:
            log(f"[READ ] short/timeout after request {n}: {e}")
            return b""
        raise