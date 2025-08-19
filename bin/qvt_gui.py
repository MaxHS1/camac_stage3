#!/usr/bin/env python3

import argparse
import csv
import pathlib
import queue
import threading
import time
import tkinter as tk
from collections import defaultdict, deque
from tkinter import ttk, messagebox, filedialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# --- Minimal cfg parser ---
def load_cfg(path: pathlib.Path):
    mods = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            b = int(parts[1]); c = int(parts[2]); n = int(parts[3])
        except ValueError:
            continue
        mods[name] = (b, c, n)
    return mods

from camacdaq_py.camac_backend import CamacBackend

class MultiPoller(threading.Thread):
    def __init__(self, cam: CamacBackend, bcn, addresses, functions, interval_s, q_out, stop_event, csv_writer=None):
        super().__init__(daemon=True)
        self.cam = cam
        self.bcn = bcn
        self.addresses = list(addresses)
        self.functions = list(functions)
        self.interval_s = max(0.02, float(interval_s))
        self.q_out = q_out
        self.stop_event = stop_event
        self.csv_writer = csv_writer
        self._ext = {}
        b, c, n = self.bcn
        for a in self.addresses:
            try:
                self._ext[a] = self.cam.cdreg(b, c, n, a)
            except Exception as e:
                self.q_out.put(("status", f"cdreg failed for A={a}: {e!r}"))

    def run(self):
        if not self._ext:
            self.q_out.put(("status", "No valid addresses to poll."))
            return
        idx = 0
        af_pairs = [(a, f) for a in self.addresses for f in self.functions]
        if not af_pairs:
            self.q_out.put(("status", "No (A,F) pairs selected to poll."))
            return
        while not self.stop_event.is_set():
            a, f = af_pairs[idx]
            idx = (idx + 1) % len(af_pairs)
            ext = self._ext.get(a)
            if ext is None:
                time.sleep(self.interval_s)
                continue
            try:
                val, q = self.cam.cfsa(f, ext, None)
                t = time.time()
                self.q_out.put(("sample", (t, a, f, val, q)))
                if self.csv_writer:
                    b, c, n = self.bcn
                    self.csv_writer.writerow([int(t*1000), b, c, n, a, f, val, q])
            except Exception as e:
                self.q_out.put(("status", f"Read error at A={a},F={f}: {e!r}"))
            time.sleep(self.interval_s)

class CamacGUI(tk.Tk):
    READ_FUNCS_DEFAULT = [0, 2, 4, 8, 9, 10, 24, 26, 30]

    def __init__(self, cam: CamacBackend, modules: dict[str, tuple[int,int,int]]):
        super().__init__()
        self.title("CAMAC Multi-Gate Interactive Panel")
        self.cam = cam
        self.modules = modules
        self.poll_thread = None
        self.poll_stop = threading.Event()
        self.ui_queue = queue.Queue()
        self.csv_file = None
        self.csv_writer = None
        self.buffers = defaultdict(lambda: deque(maxlen=1000))
        self.latest = {}

        # --- Top controls ---
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Module:").grid(row=0, column=0, sticky="w")
        self.cmb_module = ttk.Combobox(top, values=sorted(self.modules.keys()), state="readonly", width=24)
        self.cmb_module.grid(row=0, column=1, sticky="w", padx=(4, 12))
        if self.modules:
            self.cmb_module.set(sorted(self.modules.keys())[0])
        ttk.Label(top, text="Poll interval (ms/read):").grid(row=0, column=2, sticky="e")
        self.spn_ms = ttk.Spinbox(top, from_=10, to=2000, increment=10, width=8)
        self.spn_ms.set(100)
        self.spn_ms.grid(row=0, column=3, sticky="w", padx=(4, 12))
        ttk.Label(top, text="Buffer length:").grid(row=0, column=4, sticky="e")
        self.spn_buf = ttk.Spinbox(top, from_=100, to=20000, increment=100, width=8)
        self.spn_buf.set(2000)
        self.spn_buf.grid(row=0, column=5, sticky="w", padx=(4, 12))
        self.btn_start = ttk.Button(top, text="Start Polling", command=self.on_start)
        self.btn_start.grid(row=0, column=6, padx=(6, 3))
        self.btn_stop = ttk.Button(top, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.grid(row=0, column=7, padx=(3, 0))

        # --- Address & Function selection ---
        sel = ttk.LabelFrame(self, text="Addresses & Functions", padding=8)
        sel.pack(fill="x", padx=10, pady=(0, 8))
        addr_frame = ttk.Frame(sel)
        addr_frame.pack(side="left", padx=8)
        ttk.Label(addr_frame, text="Addresses (A)").pack(anchor="w")
        self.addr_vars = {}
        grid = ttk.Frame(addr_frame)
        grid.pack()
        for a in range(16):
            var = tk.BooleanVar(value=True)
            self.addr_vars[a] = var
            cb = ttk.Checkbutton(grid, text=str(a), variable=var)
            cb.grid(row=a//8, column=a%8, sticky="w")
        fn_frame = ttk.Frame(sel)
        fn_frame.pack(side="left", padx=20)
        ttk.Label(fn_frame, text="Read Functions (F)").pack(anchor="w")
        self.fn_vars = {}
        gridf = ttk.Frame(fn_frame)
        gridf.pack()
        for i, f in enumerate(self.READ_FUNCS_DEFAULT):
            var = tk.BooleanVar(value=True if f in (0,2,4,8,9,10) else False)
            self.fn_vars[f] = var
            cb = ttk.Checkbutton(gridf, text=str(f), variable=var)
            cb.grid(row=i//6, column=i%6, sticky="w")
        right_opts = ttk.Frame(sel)
        right_opts.pack(side="left", padx=20)
        self.var_log = tk.BooleanVar(value=False)
        ttk.Checkbutton(right_opts, text="Log CSV", variable=self.var_log, command=self.on_toggle_log).pack(anchor="w")
        ttk.Button(right_opts, text="Export Table CSV", command=self.export_table_csv).pack(anchor="w", pady=(6,0))
        ttk.Button(right_opts, text="Clear Buffers", command=self.clear_buffers).pack(anchor="w", pady=(6,0))

        # --- Middle split ---
        mid = ttk.Frame(self, padding=10)
        mid.pack(fill="both", expand=True)
        plot_frame = ttk.LabelFrame(mid, text="Live Plot", padding=6)
        plot_frame.pack(side="left", fill="both", expand=True, padx=(0,8))
        self.fig = Figure(figsize=(6, 3.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Data")
        self.ax.grid(True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        series_bar = ttk.Frame(plot_frame)
        series_bar.pack(fill="x", pady=(6,0))
        ttk.Label(series_bar, text="Show series: A").pack(side="left")
        self.cmb_plot_a = ttk.Combobox(series_bar, values=[str(i) for i in range(16)], width=4, state="readonly")
        self.cmb_plot_a.set("0")
        self.cmb_plot_a.pack(side="left", padx=(2,8))
        ttk.Label(series_bar, text="F").pack(side="left")
        self.cmb_plot_f = ttk.Combobox(series_bar, values=[str(f) for f in self.READ_FUNCS_DEFAULT], width=4, state="readonly")
        self.cmb_plot_f.set(str(self.READ_FUNCS_DEFAULT[0]))
        self.cmb_plot_f.pack(side="left", padx=(2,8))
        ttk.Button(series_bar, text="Refresh Plot", command=self.draw_plot).pack(side="left")
        table_frame = ttk.LabelFrame(mid, text="Latest Values", padding=6)
        table_frame.pack(side="left", fill="both", expand=True)
        cols = ("A","F","Time","Value","Q")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=70 if c in ("A","F","Q") else 120, anchor="center")
        self.tree.pack(fill="both", expand=True)

        # --- Status bar ---
        stat = ttk.Frame(self, padding=(10,6))
        stat.pack(fill="x")
        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(stat, textvariable=self.var_status).pack(side="left")

        self.after(60, self._drain_queue)
        self.after(250, self._auto_plot_refresh)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def selected_addrs(self):
        return [a for a, v in self.addr_vars.items() if v.get()]

    def selected_funcs(self):
        return [f for f, v in self.fn_vars.items() if v.get()]

    def set_buffer_len(self, n):
        n = max(10, int(n))
        for k in list(self.buffers.keys()):
            old = self.buffers[k]
            self.buffers[k] = deque(old, maxlen=n)

    def on_start(self):
        if self.poll_thread and self.poll_thread.is_alive():
            messagebox.showinfo("Polling", "Already polling.")
            return
        try:
            name = self.cmb_module.get()
            if name not in self.modules:
                raise RuntimeError("No module selected.")
            bcn = self.modules[name]
            ms = int(self.spn_ms.get())
            self.set_buffer_len(int(self.spn_buf.get()))
            addrs = self.selected_addrs()
            fns = self.selected_funcs()
            if not addrs or not fns:
                raise RuntimeError("Select at least one Address and one Function.")
            writer = None
            if self.var_log.get():
                p = filedialog.asksaveasfilename(
                    title="Choose CSV log file",
                    defaultextension=".csv",
                    initialfile=f"{name.lower()}_multilog.csv",
                    filetypes=[("CSV files","*.csv"),("All files","*.*")]
                )
                if p:
                    self.csv_file = open(p, "w", newline="")
                    self.csv_writer = csv.writer(self.csv_file)
                    self.csv_writer.writerow(["ms","branch","crate","station","address","function","data","q"])
                    writer = self.csv_writer
                    self._set_status(f"Logging to {p}")
                else:
                    self.var_log.set(False)
            self.poll_stop.clear()
            self.poll_thread = MultiPoller(
                cam=self.cam,
                bcn=bcn,
                addresses=addrs,
                functions=fns,
                interval_s=ms/1000.0,
                q_out=self.ui_queue,
                stop_event=self.poll_stop,
                csv_writer=writer
            )
            self.poll_thread.start()
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self._set_status(f"Polling {name} | A={addrs} | F={fns} | {ms} ms/read")
        except Exception as e:
            self._set_status(f"Start error: {e!r}")
            messagebox.showerror("Start error", str(e))

    def on_stop(self):
        self._stop_poll()
        self._set_status("Polling stopped.")

    def _stop_poll(self):
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_stop.set()
            self.poll_thread.join(timeout=1.0)
        self.poll_thread = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if self.csv_file:
            try:
                self.csv_file.flush()
                self.csv_file.close()
            finally:
                self.csv_file = None
                self.csv_writer = None

    def on_toggle_log(self):
        pass

    def export_table_csv(self):
        p = filedialog.asksaveasfilename(
            title="Export current table to CSV",
            defaultextension=".csv",
            initialfile="camac_latest.csv",
            filetypes=[("CSV files","*.csv")]
        )
        if not p:
            return
        try:
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["A","F","unix_ms","value","Q"])
                for (a,f), (t,val,q) in sorted(self.latest.items()):
                    w.writerow([a, f, int(t*1000), val, q])
            self._set_status(f"Exported table to {p}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def clear_buffers(self):
        self.buffers.clear()
        self.latest.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.ax.cla()
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Data")
        self.ax.grid(True)
        self.canvas.draw_idle()
        self._set_status("Cleared buffers.")

    def _set_status(self, s):
        self.var_status.set(s)

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status":
                    self._set_status(str(payload))
                elif kind == "sample":
                    t, a, f, val, q = payload
                    key = (a, f)
                    self.latest[key] = (t, val, q)
                    buf = self.buffers[key]
                    buf.append((t, val))
                    self._upsert_row(a, f, t, val, q)
        except queue.Empty:
            pass
        self.after(60, self._drain_queue)

    def _upsert_row(self, a, f, t, val, q):
        iid = f"{a}:{f}"
        timestr = time.strftime('%H:%M:%S', time.localtime(t))
        if self.tree.exists(iid):
            self.tree.item(iid, values=(a, f, timestr, val, q))
        else:
            self.tree.insert("", "end", iid=iid, values=(a, f, timestr, val, q))

    def draw_plot(self):
        try:
            a = int(self.cmb_plot_a.get())
            f = int(self.cmb_plot_f.get())
            key = (a, f)
            buf = self.buffers.get(key)
            self.ax.cla()
            self.ax.set_xlabel("Time (s)")
            self.ax.set_ylabel("Data")
            self.ax.grid(True)
            if buf and len(buf) >= 2:
                t0 = buf[0][0]
                xs = [t - t0 for (t, v) in buf]
                ys = [v for (t, v) in buf]
                self.ax.plot(xs, ys, linewidth=1.2)
                self.ax.set_title(f"A={a}, F={f} (n={len(buf)})")
            else:
                self.ax.set_title(f"A={a}, F={f} (no data yet)")
            self.canvas.draw_idle()
        except Exception as e:
            self._set_status(f"Plot error: {e!r}")

    def _auto_plot_refresh(self):
        self.draw_plot()
        self.after(700, self._auto_plot_refresh)

    def on_close(self):
        self._stop_poll()
        self.destroy()

def main():
    ap = argparse.ArgumentParser(description="CAMAC Multi-Gate Interactive GUI")
    ap.add_argument("--cfg", required=True, help="Path to daq.cfg")
    ap.add_argument("--mode", choices=["auto","real","mock","visa"], default="auto")
    ap.add_argument("--lib", help="Path to native CAMAC .so/.dll (real mode)")
    ap.add_argument("--resource", help="VISA resource (e.g., GPIB0::16::INSTR)")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.cfg)
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")
    modules = load_cfg(cfg_path)
    if not modules:
        raise SystemExit("No modules parsed from cfg.")
    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    app = CamacGUI(cam, modules)
    app.geometry("1100x640")
    app.mainloop()

if __name__ == "__main__":
    main()