
# CAMAC Stage 3 – Python DAQ with real/mock backends

## Quick start (mock)
```
python3 -m venv venv
source venv/bin/activate
pip install -e .
python bin/ctalk.py --mode auto
python bin/daq.py --cfg sample.cfg --mode auto list
```

## Real backend
Set CAMAC_LIB to your shared library path (so/dylib/dll), or pass --lib.
```
export CAMAC_LIB=/absolute/path/to/libcamac_gpib.so
python bin/ctalk.py --mode real
python bin/daq.py --cfg /path/to/daq.cfg --mode real list
```
