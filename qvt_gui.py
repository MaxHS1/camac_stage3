#!/usr/bin/env python3
"""
Crystal Test GUI — classic-style UI with working QVT controls
- Landing screen: left vertical menu, right content pane (matches the uploaded style)
- QVT page:
    * Zoom: toggles matplotlib zoom mode (like toolbar)
    * All: reset view to full channel range & data
    * Fit: autoscale Y to current data in current X window
    * Print: save figure to PNG/PDF/SVG
- Timer works and auto-stops at Run Time
- X axis shows channel (A), Y shows latest counts per channel for selected F

Backends:
    --mode mock / real / visa (existing), and also supports --mode ni if you added it.
"""

import argparse
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from collections import defaultdict, deque

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


# ---------- Optional backends ----------
def make_backend(mode, lib_path, resource):
    """
    Creates the backend based on CLI flags.
    - If mode == 'ni' and camac_backend_win exists, use it.
    - Else fall back to original camacdaq backend.
    """
    if mode == "ni":
        try:
            from camac_backend_win import CamacBackendNI as CamacBackend
            return CamacBackend(resource=resource)
        except Exception as e:
            raise SystemExit(f"NI backend failed: {e}")
    else:
        # original path
        try:
            from camacdaq_py.camac_backend import CamacBackend
        except Exception as e:
            raise SystemExit(f"Could not import camacdaq_py.camac_backend: {e}")
        return CamacBackend(mode=mode, lib_path=lib_path, resource=resource)


# ---------- Config parsing ----------
def load_cfg(path: pathlib.Path):
    """
    Very small cfg parser; expects lines like:
      # name  branch crate station
      QVT   1 1 2
    Returns {name: (branch, crate, station)}
    """
    mods = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            b, c, n = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            continue
        mods[name] = (b, c, n)
    return mods


# ---------- Polling thread ----------
class MultiPoller(threading.Thread):
    """
    Round-robin poller across (A, F) for a single (b, c, n).
    Emits ('sample', (t, A, F, value, Q)) and ('status', text) into q_out.
    """
    def __init__(self, cam, bcn, addrs, funcs, interval_s, q_out, stop_event, csv_writer=None):
        super().__init__(daemon=True)
        self.cam = cam
        self.bcn = bcn  # (b,c,n) though b,c unused by GPIB backend
        self.addrs = list(addrs)
        self.funcs = list(funcs)
        self.interval_s = max(0.02, float(interval_s))
        self.q_out = q_out
        self.stop_event = stop_event
        self.csv_writer = csv_writer
        self._ext = {}
        b, c, n = bcn
        for a in self.addrs:
            try:
                self._ext[a] = self.cam.cdreg(b, c, n, a)
            except Exception as e:
                self.q_out.put(("status", f"cdreg fail A={a}: {e!r}"))

    def run(self):
        pairs = [(a, f) for a in self.addrs for f in self.funcs]
        if not pairs:
            self.q_out.put(("status", "No (A,F) pairs to poll."))
            return
        idx = 0
        while not self.stop_event.is_set():
            a, f = pairs[idx]
            idx = (idx + 1) % len(pairs)
            ext = self._ext.get(a)
            if ext is None:
                time.sleep(self.interval_s)
                continue
            try:
                # cam.cfsa returns backend-specific tuples; standardize to (val,q)
                res = self.cam.cfsa(f, ext)
                if isinstance(res, tuple) and len(res) == 2:
                    val, q = res
                elif isinstance(res, tuple) and len(res) == 3:
                    q, _x, d = res
                    val = d if d is not None else 0
                else:
                    # fallback
                    val, q = 0, 0
                t = time.time()
                self.q_out.put(("sample", (t, a, f, int(val) if val is not None else 0, int(q))))
                if self.csv_writer:
                    b, c, n = self.bcn
                    self.csv_writer.writerow([int(t * 1000), b, c, n, a, f, val, q])
            except Exception as e:
                self.q_out.put(("status", f"Read error A={a},F={f}: {e!r}"))
            time.sleep(self.interval_s)


# ---------- QVT Data window (spectrum with working controls) ----------
class QVTWindow(ttk.Frame):
    """
    Embedded page that shows a spectrum snapshot:
      X = channel/address (0..15 or observed), Y = latest value for that address for the selected F
    """
    def __init__(self, master, latest_map, selected_f_var: tk.IntVar, autofit_var: tk.BooleanVar):
        super().__init__(master)
        self.latest_map = latest_map
        self.selected_f_var = selected_f_var
        self.autofit_var = autofit_var

        # Top controls (toolbar-like)
        top = ttk.Frame(self, padding=(6, 6, 6, 0))
        top.pack(fill="x")

        self.btn_exit = ttk.Button(top, text="Close", command=self._on_close)
        self.btn_exit.pack(side="left", padx=4)

        self.btn_zoom = ttk.Button(top, text="Zoom", command=self._toggle_zoom)
        self.btn_zoom.pack(side="left", padx=4)

        self.btn_all = ttk.Button(top, text="All", command=self._view_all)
        self.btn_all.pack(side="left", padx=4)

        self.btn_fit = ttk.Button(top, text="Fit", command=self._fit_y_to_data)
        self.btn_fit.pack(side="left", padx=4)

        self.btn_print = ttk.Button(top, text="Print", command=self._save_figure)
        self.btn_print.pack(side="left", padx=4)

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(top, text="F code").pack(side="left")
        self.cmb_f = ttk.Combobox(top, width=6, state="readonly",
                                  values=[str(x) for x in range(0, 32)])
        self.cmb_f.set(str(self.selected_f_var.get()))
        self.cmb_f.bind("<<ComboboxSelected>>", self._on_pick_f)
        self.cmb_f.pack(side="left", padx=(4, 10))

        ttk.Label(top, text="Fit Region (channels)").pack(side="left", padx=(4, 4))
        self.ent_fit = ttk.Entry(top, width=10)
        self.ent_fit.insert(0, "0 15")
        self.ent_fit.pack(side="left")

        ttk.Checkbutton(top, text="Auto Fit", variable=self.autofit_var).pack(side="left", padx=(14, 4))

        # Plot body
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        self.fig = Figure(figsize=(6.6, 3.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("QVT Counts")
        self.ax.set_xlabel("Channel")
        self.ax.set_ylabel("Count")
        self.ax.grid(True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=body)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Hidden native toolbar to leverage zoom logic
        self._toolbar = NavigationToolbar2Tk(self.canvas, body, pack_toolbar=False)
        self._toolbar.update()
        self._zoom_active = False

        self.after(300, self._refresh_plot)

    def _on_close(self):
        # Parent handles showing/hiding this frame; here we can just clear
        self.pack_forget()

    def _on_pick_f(self, _evt=None):
        try:
            self.selected_f_var.set(int(self.cmb_f.get()))
        except Exception:
            pass

    def _toggle_zoom(self):
        # Toggle matplotlib's built-in zoom
        if not self._zoom_active:
            self._toolbar.zoom()
            self._zoom_active = True
            self.btn_zoom.state(["pressed"])
        else:
            # Calling zoom() again toggles it off
            self._toolbar.zoom()
            self._zoom_active = False
            self.btn_zoom.state(["!pressed"])

    def _view_all(self):
        # Reset to full channels (0..15) and Y autoscale to all available data
        xs, ys = self._current_xy()
        if not xs:
            # default full axis
            self.ax.set_xlim(-0.5, 15.5)
            self.ax.set_ylim(0, 1)
        else:
            xmin = min(0, min(xs) - 0.5)
            xmax = max(15, max(xs) + 0.5)
            ymax = max(1, max(ys) * 1.15)
            self.ax.set_xlim(xmin, xmax)
            self.ax.set_ylim(0, ymax)
        self.canvas.draw_idle()

    def _fit_y_to_data(self):
        # Fit Y only to currently visible X range
        xs, ys = self._current_xy()
        if not xs:
            return
        # Determine which bars are inside current xlim
        x0, x1 = self.ax.get_xlim()
        in_view = [y for x, y in zip(xs, ys) if (x >= x0 and x <= x1)]
        if not in_view:
            return
        ymax = max(1, max(in_view) * 1.15)
        self.ax.set_ylim(0, ymax)
        self.canvas.draw_idle()

    def _save_figure(self):
        # Save as PNG/PDF/SVG
        fname = filedialog.asksaveasfilename(
            title="Save QVT Figure",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg"), ("All files", "*.*")]
        )
        if not fname:
            return
        try:
            self.fig.savefig(fname, bbox_inches="tight")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _current_xy(self):
        # Build spectrum for selected F from latest_map
        f = self.selected_f_var.get()
        channels_seen = sorted({a for (a, ff) in self.latest_map.keys() if ff == f})
        xs, ys = [], []
        for a in channels_seen:
            _t, val, _q = self.latest_map[(a, f)]
            xs.append(a)
            ys.append(val)
        return xs, ys

    def _refresh_plot(self):
        # Redraw plot each tick
        xs, ys = self._current_xy()
        self.ax.cla()
        self.ax.set_title("QVT Counts")
        self.ax.set_xlabel("Channel")
        self.ax.set_ylabel("Count")
        self.ax.grid(True)

        if xs:
            self.ax.bar(xs, ys, width=0.8)
            # Fit region
            try:
                lo_s, hi_s = self.ent_fit.get().strip().split()
                lo, hi = int(lo_s), int(hi_s)
                self.ax.set_xlim(lo - 0.5, hi + 0.5)
            except Exception:
                pass
            if self.autofit_var.get():
                self._fit_y_to_data()
        else:
            # default axes
            self.ax.set_xlim(-0.5, 15.5)
            self.ax.set_ylim(0, 1)

        self.canvas.draw_idle()
        self.after(400, self._refresh_plot)


# ---------- Main Application ----------
class CrystalTestGUI(tk.Tk):
    def __init__(self, cam, modules: dict[str, tuple[int, int, int]]):
        super().__init__()
        self.title("Crystal Test")
        self.cam = cam
        self.modules = modules

        # Defaults / params
        self.params = {
            "module": sorted(self.modules)[0] if self.modules else "",
            "addrs": list(range(16)),
            "funcs": [0, 2, 4],
            "ms": 100,
            "buf": 2000,
        }

        # Backend/polling
        self.poll_thread = None
        self.poll_stop = threading.Event()
        self.ui_queue = queue.Queue()

        # Data stores
        self.buffers = defaultdict(lambda: deque(maxlen=self.params["buf"]))  # (A,F) -> deque[(t,val)]
        self.latest = {}  # (A,F) -> (t,val,q)

        # Tk variables
        self.var_running = tk.BooleanVar(value=False)
        self.var_run_time = tk.IntVar(value=10)
        self.var_status = tk.StringVar(value="Ready.")
        self.var_autofit = tk.BooleanVar(value=True)
        self.var_selected_f = tk.IntVar(value=min(self.params["funcs"]) if self.params["funcs"] else 0)

        # Timing
        self._timer_start_ts = None
        self._timer_job = None

        # Build UI (left menu + right content)
        self._build_shell()

        # Default page
        self.show_dashboard()

        # Loops
        self.after(60, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

    # ----- Shell Layout -----
    def _build_shell(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        # Left menu
        self.left = ttk.Frame(root)
        self.left.pack(side="left", fill="y", padx=(0, 8))

        title = ttk.Label(self.left, text="CIT HEP\nCrystal Test", anchor="center",
                          font=("Helvetica", 16, "bold"), foreground="#2a4ee0", padding=(4, 6))
        title.pack(fill="x", pady=(0, 6))

        self.btn_dash = ttk.Button(self.left, text="Dashboard", command=self.show_dashboard, width=18)
        self.btn_dash.pack(fill="x", pady=4)

        self.btn_qvt = ttk.Button(self.left, text="QVT Data", command=self.show_qvt, width=18)
        self.btn_qvt.pack(fill="x", pady=4)

        self.btn_settings = ttk.Button(self.left, text="Settings", command=self.show_settings, width=18)
        self.btn_settings.pack(fill="x", pady=4)

        self.btn_exit = ttk.Button(self.left, text="Exit", command=self.on_exit, width=18)
        self.btn_exit.pack(side="bottom", fill="x", pady=(6, 0))

        # Right content
        self.right = ttk.Frame(root)
        self.right.pack(side="left", fill="both", expand=True)

        # Status bar
        self.status = ttk.Label(self, textvariable=self.var_status, anchor="w", relief="sunken")
        self.status.pack(fill="x", padx=8, pady=(6, 0))

    # ----- Pages -----
    def clear_right(self):
        for w in self.right.winfo_children():
            w.destroy()

    def show_dashboard(self):
        self.clear_right()
        frm = ttk.Frame(self.right, padding=8)
        frm.pack(fill="both", expand=True)

        # timer top row
        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="Run Time (s):").pack(side="left", padx=(0, 6))
        spn = ttk.Spinbox(top, from_=0, to=36000, width=8, textvariable=self.var_run_time)
        spn.pack(side="left")

        self.lbl_timer = ttk.Label(top, text="00:00.00", relief="sunken", width=10)
        self.lbl_timer.pack(side="right")

        # center controls
        ctrls = ttk.Frame(frm)
        ctrls.pack(fill="x", pady=(12, 6))

        self.btn_start = ttk.Button(ctrls, text="Start", width=18, command=self.on_start_stop)
        self.btn_start.grid(row=0, column=0, padx=4, pady=4)

        ttk.Checkbutton(ctrls, text="Auto Fit", variable=self.var_autofit).grid(row=0, column=1, padx=8)
        ttk.Label(ctrls, text="Module:").grid(row=1, column=0, sticky="e", padx=4, pady=4)

        cmb = ttk.Combobox(ctrls, state="readonly", width=18, values=sorted(self.modules))
        if self.params["module"] in self.modules:
            cmb.set(self.params["module"])
        elif self.modules:
            cmb.set(sorted(self.modules)[0])

        def _set_module(_evt=None):
            self.params["module"] = cmb.get()
        cmb.bind("<<ComboboxSelected>>", _set_module)
        cmb.grid(row=1, column=1, sticky="w", padx=4, pady=4)

        # small note
        ttk.Label(frm, text="Tip: Use the left menu to open the QVT Data plot.",
                  foreground="#555").pack(anchor="w", pady=(12, 0))

    def show_qvt(self):
        self.clear_right()
        # embed the QVT page in the right pane
        self.qvt_page = QVTWindow(self.right, self.latest, self.var_selected_f, self.var_autofit)
        self.qvt_page.pack(fill="both", expand=True)

    def show_settings(self):
        self.clear_right()
        s = ttk.Frame(self.right, padding=10)
        s.pack(fill="both", expand=True)
        ttk.Label(s, text="Polling Settings", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(s)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Addresses (A):").pack(side="left")
        ent_a = ttk.Entry(row, width=24)
        ent_a.insert(0, ",".join(str(a) for a in self.params["addrs"]))
        ent_a.pack(side="left", padx=8)

        row2 = ttk.Frame(s)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="Functions (F):").pack(side="left")
        ent_f = ttk.Entry(row2, width=24)
        ent_f.insert(0, ",".join(str(f) for f in self.params["funcs"]))
        ent_f.pack(side="left", padx=8)

        row3 = ttk.Frame(s)
        row3.pack(fill="x", pady=4)
        ttk.Label(row3, text="Interval (ms):").pack(side="left")
        spn_ms = ttk.Spinbox(row3, from_=20, to=5000, increment=10, width=8)
        spn_ms.delete(0, "end")
        spn_ms.insert(0, str(self.params["ms"]))
        spn_ms.pack(side="left", padx=8)

        def _apply():
            try:
                self.params["addrs"] = [int(x) for x in ent_a.get().replace(" ", "").split(",") if x != ""]
                self.params["funcs"] = [int(x) for x in ent_f.get().replace(" ", "").split(",") if x != ""]
                self.params["ms"] = int(spn_ms.get())
                messagebox.showinfo("Settings", "Polling settings applied.")
            except Exception as e:
                messagebox.showerror("Invalid settings", str(e))

        ttk.Button(s, text="Apply", command=_apply).pack(anchor="w", pady=(10, 0))

    # ----- Start/Stop / Timer -----
    def on_start_stop(self):
        if self.var_running.get():
            self._stop_poll()
            self.var_running.set(False)
            self.btn_start.configure(text="Start")
            self._stop_timer()
            if hasattr(self, "lbl_timer"):
                self.lbl_timer.configure(text="00:00.00")
            self._set_status("Stopped.")
            return

        name = self.params["module"]
        if name not in self.modules:
            messagebox.showerror("Error", "No valid module found in cfg.")
            return
        bcn = self.modules[name]
        ms = self.params["ms"]
        addrs = self.params["addrs"]
        funcs = self.params["funcs"]
        if not addrs or not funcs:
            messagebox.showerror("Error", "Empty (A,F) selection.")
            return

        self.poll_stop.clear()
        self.poll_thread = MultiPoller(self.cam, bcn, addrs, funcs, ms / 1000.0,
                                       self.ui_queue, self.poll_stop, csv_writer=None)
        self.poll_thread.start()

        # Select default F (lowest)
        self.var_selected_f.set(min(funcs))

        self.var_running.set(True)
        if hasattr(self, "btn_start"):
            self.btn_start.configure(text="Stop")
        self._set_status(f"Polling {name} | A={addrs} | F={funcs} | {ms} ms/read")
        self._start_timer()

        # auto open QVT page if not visible
        if not any(isinstance(w, QVTWindow) for w in self.right.winfo_children()):
            self.show_qvt()

    def _start_timer(self):
        self._timer_start_ts = time.time()
        self._tick_timer()

    def _stop_timer(self):
        if self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None

    def _tick_timer(self):
        if not self.var_running.get():
            return
        elapsed = time.time() - (self._timer_start_ts or time.time())
        m, s = divmod(elapsed, 60.0)
        if hasattr(self, "lbl_timer"):
            self.lbl_timer.configure(text=f"{int(m):02d}:{s:05.2f}")

        duration = max(0, int(self.var_run_time.get()))
        if duration and elapsed >= duration:
            self.on_start_stop()
            return

        self._timer_job = self.after(100, self._tick_timer)

    # ----- Queue drain -----
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status":
                    self._set_status(str(payload))
                elif kind == "sample":
                    t, a, f, val, q = payload
                    self.latest[(a, f)] = (t, val, q)
                    self.buffers[(a, f)].append((t, val))
        except queue.Empty:
            pass
        self.after(60, self._drain_queue)

    # ----- Helpers / Exit -----
    def _set_status(self, s: str):
        self.var_status.set(s)

    def _stop_poll(self):
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_stop.set()
            self.poll_thread.join(timeout=1.0)
        self.poll_thread = None

    def on_exit(self):
        self._stop_poll()
        try:
            if hasattr(self.cam, "close"):
                self.cam.close()
        except Exception:
            pass
        self.destroy()


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Classic Crystal Test GUI (QVT page with working controls)")
    ap.add_argument("--cfg", required=True, help="Path to daq.cfg")
    ap.add_argument("--mode", choices=["auto", "real", "mock", "visa", "ni"], default="auto",
                    help="Backend mode")
    ap.add_argument("--lib", help="Path to native CAMAC .so/.dll (real mode)")
    ap.add_argument("--resource", help="VISA resource (e.g., GPIB0::16::INSTR)")
    args = ap.parse_args()

    cfg = pathlib.Path(args.cfg)
    if not cfg.exists():
        raise SystemExit(f"Config not found: {cfg}")
    modules = load_cfg(cfg)
    if not modules:
        raise SystemExit("No modules parsed from cfg.")

    cam = make_backend(args.mode, args.lib, args.resource)

    app = CrystalTestGUI(cam, modules)
    app.geometry("900x520")
    app.mainloop()


if __name__ == "__main__":
    main()