#!/usr/bin/env python3
"""
Battery Discharge Logger GUI
RP2040 Zero — Real-time voltage curve plotter

pip install pyserial matplotlib
"""

import sys
import time
import threading
import datetime
import csv
import os

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import serial
import serial.tools.list_ports

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import AutoMinorLocator
import matplotlib.gridspec as gridspec

# ── Colours ───────────────────────────────────────────────────────────────────
BG       = "#0a0e14"
PANEL    = "#0f1620"
BORDER   = "#1e2d3d"
ACCENT   = "#00d4ff"
GREEN    = "#39ff14"
AMBER    = "#ffb300"
RED      = "#ff3c3c"
DIM      = "#3a4a5a"
TEXT     = "#cdd9e5"
SUBTEXT  = "#607080"

RP2040_IDS = [
    (0x2E8A, 0x0005),
    (0x2E8A, 0x000A),
    (0x2E8A, 0x0003),
    (0x2E8A, 0x0004),
]

def fmt_time(s):
    s = int(s)
    h, rem = divmod(s, 3600)
    m, s   = divmod(rem, 60)
    if h:   return f"{h}h {m:02d}m {s:02d}s"
    if m:   return f"{m}m {s:02d}s"
    return f"{s}s"

def find_rp2040():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        for vid, pid in RP2040_IDS:
            if p.vid == vid and p.pid == pid:
                return p.device
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ("rp2040","pico","waveshare")):
            return p.device
    return None

def all_ports():
    return [p.device for p in serial.tools.list_ports.comports()]

# ═════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Battery Discharge Logger")
        self.configure(bg=BG)
        self.geometry("1280x820")
        self.minsize(960, 640)

        # Data
        self.elapsed  = []
        self.voltage  = []
        self.lock     = threading.Lock()
        self.ser      = None
        self.reading  = False
        self.log_file = None
        self.log_writer = None
        self.session_start = None

        self._build_ui()
        self._scan_ports()
        self._start_animation()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=BG, height=56)
        topbar.pack(fill="x", padx=0, pady=0)
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⬡ BATTERY DISCHARGE LOGGER",
                 font=("Courier New", 13, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left", padx=20, pady=14)

        # Status pill
        self.status_var = tk.StringVar(value="DISCONNECTED")
        self.status_lbl = tk.Label(topbar, textvariable=self.status_var,
                                   font=("Courier New", 9, "bold"),
                                   fg=BG, bg=RED,
                                   padx=10, pady=3)
        self.status_lbl.pack(side="right", padx=20, pady=14)

        # ── Main layout: sidebar + plot ───────────────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        sidebar = tk.Frame(main, bg=PANEL, width=220,
                           highlightbackground=BORDER, highlightthickness=1)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)

        plot_frame = tk.Frame(main, bg=BG)
        plot_frame.pack(side="left", fill="both", expand=True)

        self._build_sidebar(sidebar)
        self._build_plot(plot_frame)

    def _section(self, parent, title):
        tk.Label(parent, text=title,
                 font=("Courier New", 8, "bold"),
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=14, pady=(16,4))
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14)

    def _build_sidebar(self, sb):
        # ── Connection ────────────────────────────────────────────────────────
        self._section(sb, "CONNECTION")

        tk.Label(sb, text="Port", font=("Courier New", 8),
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=14, pady=(8,2))

        port_row = tk.Frame(sb, bg=PANEL)
        port_row.pack(fill="x", padx=14)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var,
                                        width=13, state="readonly",
                                        font=("Courier New", 9))
        self.port_combo.pack(side="left")

        tk.Button(port_row, text="↺", font=("Courier New", 10),
                  fg=ACCENT, bg=PANEL, activeforeground=BG,
                  activebackground=ACCENT, bd=0, cursor="hand2",
                  command=self._scan_ports).pack(side="left", padx=(6,0))

        self.connect_btn = self._btn(sb, "CONNECT", self._toggle_connect,
                                     color=GREEN)

        # ── Live readings ─────────────────────────────────────────────────────
        self._section(sb, "LIVE")

        self.v_var  = tk.StringVar(value="—")
        self.t_var  = tk.StringVar(value="—")
        self.n_var  = tk.StringVar(value="0")
        self.mn_var = tk.StringVar(value="—")
        self.mx_var = tk.StringVar(value="—")

        for label, var in [("VOLTAGE",  self.v_var),
                            ("ELAPSED",  self.t_var),
                            ("SAMPLES",  self.n_var),
                            ("MIN V",    self.mn_var),
                            ("MAX V",    self.mx_var)]:
            row = tk.Frame(sb, bg=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            tk.Label(row, text=label, font=("Courier New", 7),
                     fg=SUBTEXT, bg=PANEL, width=8, anchor="w").pack(side="left")
            tk.Label(row, textvariable=var, font=("Courier New", 11, "bold"),
                     fg=ACCENT, bg=PANEL, anchor="e").pack(side="right")

        # ── Controls ──────────────────────────────────────────────────────────
        self._section(sb, "CONTROLS")

        self._btn(sb, "▶  START NOW", self._reset_session, color=GREEN)
        self._btn(sb, "⬛  CLEAR GRAPH", self._clear_graph, color=AMBER)
        self._btn(sb, "📂  LOAD CSV", self._load_csv, color=ACCENT)
        self._btn(sb, "💾  SAVE CSV", self._save_csv, color=ACCENT)

        # ── Log file ──────────────────────────────────────────────────────────
        self._section(sb, "AUTO-SAVE")
        self.logfile_var = tk.StringVar(value="auto  (next to script)")
        tk.Label(sb, textvariable=self.logfile_var,
                 font=("Courier New", 7), fg=SUBTEXT, bg=PANEL,
                 wraplength=190, justify="left").pack(anchor="w", padx=14, pady=4)

    def _btn(self, parent, text, cmd, color=ACCENT):
        b = tk.Button(parent, text=text,
                      font=("Courier New", 9, "bold"),
                      fg=color, bg=PANEL,
                      activeforeground=BG, activebackground=color,
                      bd=0, relief="flat", cursor="hand2",
                      highlightbackground=color, highlightthickness=1,
                      padx=8, pady=6,
                      command=cmd)
        b.pack(fill="x", padx=14, pady=(6,0))
        return b

    def _build_plot(self, frame):
        fig = plt.Figure(facecolor=BG)
        fig.subplots_adjust(left=0.08, right=0.97, top=0.93,
                            bottom=0.10, hspace=0.45)

        gs  = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[3, 1],
                                hspace=0.45)
        self.ax_main = fig.add_subplot(gs[0])
        self.ax_dvdt = fig.add_subplot(gs[1])

        for ax in (self.ax_main, self.ax_dvdt):
            ax.set_facecolor(PANEL)
            ax.tick_params(colors=SUBTEXT, labelsize=8)
            ax.xaxis.label.set_color(SUBTEXT)
            ax.yaxis.label.set_color(SUBTEXT)
            for sp in ax.spines.values():
                sp.set_edgecolor(BORDER)
            ax.grid(color=BORDER, linewidth=0.7, alpha=1.0)
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.tick_params(which="minor", color=DIM, length=2)

        # Main plot elements
        self.line_v, = self.ax_main.plot([], [], color=ACCENT,
                                          linewidth=1.8, zorder=3)
        self.line_smooth, = self.ax_main.plot([], [], color=GREEN,
                                               linewidth=1.0, linestyle="--",
                                               alpha=0.6, zorder=2)
        self.dot, = self.ax_main.plot([], [], "o", color=ACCENT,
                                       markersize=6, zorder=5)

        self.ax_main.set_ylabel("Voltage (V)", fontsize=9)
        self.ax_main.set_title("DISCHARGE CURVE",
                                color=TEXT, fontsize=10,
                                fontfamily="Courier New", fontweight="bold",
                                loc="left", pad=8)

        # Reference lines (drawn once, updated in animate)
        self.ref_lines = {}
        for rv, rc in [(20.0, DIM), (16.0, DIM), (12.0, AMBER), (8.0, RED)]:
            l = self.ax_main.axhline(rv, color=rc, linewidth=0.8,
                                      linestyle=":", alpha=0.5, zorder=1)
            t = self.ax_main.text(0, rv, f" {rv:.0f}V",
                                   color=rc, fontsize=7,
                                   va="bottom", fontfamily="Courier New")
            self.ref_lines[rv] = (l, t)

        # dV/dt plot
        self.line_dvdt, = self.ax_dvdt.plot([], [], color=AMBER,
                                             linewidth=1.2, zorder=3)
        self.ax_dvdt.axhline(0, color=BORDER, linewidth=0.8)
        self.ax_dvdt.set_ylabel("dV/dt  (V/hr)", fontsize=8)
        self.ax_dvdt.set_xlabel("", fontsize=8)

        # X-axis formatter (shared)
        self._x_label = ""

        self.canvas = FigureCanvasTkAgg(fig, master=frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.fig = fig

    # ── Port scanning ─────────────────────────────────────────────────────────
    def _scan_ports(self):
        ports = all_ports()
        self.port_combo["values"] = ports
        detected = find_rp2040()
        if detected:
            self.port_var.set(detected)
        elif ports:
            self.port_var.set(ports[0])

    # ── Connect / disconnect ──────────────────────────────────────────────────
    def _toggle_connect(self):
        if self.reading:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showerror("No port", "Select a serial port first.")
            return
        try:
            self.ser = serial.Serial(port, 115200, timeout=2)
            time.sleep(1.5)
            self.ser.reset_input_buffer()
        except Exception as e:
            messagebox.showerror("Connection failed", str(e))
            return

        self.reading = True
        self._new_log_file()
        self.connect_btn.config(text="⬛  DISCONNECT", fg=RED)
        self._set_status("CONNECTED", GREEN)
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _disconnect(self):
        self.reading = False
        if self.ser:
            try: self.ser.close()
            except: pass
            self.ser = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.connect_btn.config(text="CONNECT", fg=GREEN)
        self._set_status("DISCONNECTED", RED)

    def _set_status(self, text, color):
        self.status_var.set(text)
        self.status_lbl.config(bg=color)

    # ── Serial read loop (background thread) ──────────────────────────────────
    def _read_loop(self):
        while self.reading and self.ser:
            try:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line or line.startswith("#") or line.startswith("elapsed"):
                    continue

                parts = line.split(",")
                if len(parts) != 2:
                    continue
                t = float(parts[0])
                v = float(parts[1])

                with self.lock:
                    self.elapsed.append(t)
                    self.voltage.append(v)
                    if self.log_writer:
                        self.log_writer.writerow([int(t), f"{v:.4f}"])
                        self.log_file.flush()

            except Exception:
                continue

    # ── Reset / Start Now ─────────────────────────────────────────────────────
    def _reset_session(self):
        if not self.ser or not self.reading:
            messagebox.showwarning("Not connected", "Connect to device first.")
            return
        with self.lock:
            self.elapsed.clear()
            self.voltage.clear()
        if self.log_file:
            self.log_file.close()
        self._new_log_file()
        try:
            self.ser.write(b"RESET\n")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _clear_graph(self):
        with self.lock:
            self.elapsed.clear()
            self.voltage.clear()

    # ── CSV save ──────────────────────────────────────────────────────────────
    def _new_log_file(self):
        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"battery_{ts}.csv")
        self.log_file   = open(filename, "w", newline="")
        self.log_writer = csv.writer(self.log_file)
        self.log_writer.writerow(["elapsed_s", "voltage_v"])
        self.logfile_var.set(os.path.basename(filename))

    def _save_csv(self):
        with self.lock:
            if not self.elapsed:
                messagebox.showinfo("No data", "No data to save yet.")
                return
            e, v = list(self.elapsed), list(self.voltage)

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"battery_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["elapsed_s", "voltage_v"])
            for t, volt in zip(e, v):
                w.writerow([int(t), f"{volt:.4f}"])
        messagebox.showinfo("Saved", f"Saved {len(e)} samples to:\n{path}")


    def _load_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        e, v = [], []
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        e.append(float(row["elapsed_s"]))
                        v.append(float(row["voltage_v"]))
                    except (KeyError, ValueError):
                        continue
        except Exception as ex:
            messagebox.showerror("Load failed", str(ex))
            return

        if not e:
            messagebox.showerror("Empty file", "No valid data found in that CSV.")
            return

        with self.lock:
            self.elapsed = e
            self.voltage = v

        self.logfile_var.set(os.path.basename(path))
        messagebox.showinfo("Loaded", f"Loaded {len(e)} samples from:\n{os.path.basename(path)}")

    # ── Animation ─────────────────────────────────────────────────────────────
    def _start_animation(self):
        self._anim = animation.FuncAnimation(
            self.fig, self._animate, interval=1000, blit=False, cache_frame_data=False
        )

    def _animate(self, _):
        with self.lock:
            if len(self.elapsed) < 2:
                return
            e = list(self.elapsed)
            v = list(self.voltage)

        import numpy as np
        ea = np.array(e, dtype=float)
        va = np.array(v, dtype=float)

        # ── Choose x-axis unit based on total duration ────────────────────────
        total_s = ea[-1]
        if total_s < 120:
            x = ea
            xlabel = "Elapsed (seconds)"
        elif total_s < 7200:
            x = ea / 60.0
            xlabel = "Elapsed (minutes)"
        else:
            x = ea / 3600.0
            xlabel = "Elapsed (hours)"

        # ── Main curve ────────────────────────────────────────────────────────
        self.line_v.set_data(x, va)
        self.dot.set_data([x[-1]], [va[-1]])

        # Smooth curve if enough points
        if len(ea) >= 8:
            from scipy.interpolate import UnivariateSpline
            try:
                sp   = UnivariateSpline(ea, va, k=3, s=len(ea) * 0.02)
                xs   = np.linspace(ea[0], ea[-1], 500)
                xsp  = xs / (1 if total_s < 120 else 60 if total_s < 7200 else 3600)
                self.line_smooth.set_data(xsp, sp(xs))
            except Exception:
                self.line_smooth.set_data([], [])
        else:
            self.line_smooth.set_data([], [])

        # ── dV/dt ─────────────────────────────────────────────────────────────
        if len(ea) >= 3:
            dv = np.gradient(va, ea) * 3600
            self.line_dvdt.set_data(x, dv)
            self.ax_dvdt.relim()
            self.ax_dvdt.autoscale_view()
        self.ax_dvdt.set_xlabel(xlabel, fontsize=8)

        # ── Reference lines ───────────────────────────────────────────────────
        v_min, v_max = va.min(), va.max()
        x_end = x[-1]
        for rv, (line, txt) in self.ref_lines.items():
            visible = (v_min - 1) <= rv <= (v_max + 2)
            line.set_visible(visible)
            txt.set_visible(visible)
            if visible:
                txt.set_x(x_end * 0.01)

        # ── Axis limits ───────────────────────────────────────────────────────
        pad = (v_max - v_min) * 0.05 if v_max != v_min else 0.5
        self.ax_main.set_xlim(x[0], x[-1] * 1.02)
        self.ax_main.set_ylim(v_min - pad - 0.5, v_max + pad + 0.5)
        self.ax_main.set_xlabel(xlabel, fontsize=8)
        self.ax_dvdt.set_xlim(x[0], x[-1] * 1.02)

        # ── Live stats sidebar ────────────────────────────────────────────────
        self.v_var.set(f"{va[-1]:.3f}V")
        self.t_var.set(fmt_time(total_s))
        self.n_var.set(str(len(va)))
        self.mn_var.set(f"{v_min:.3f}V")
        self.mx_var.set(f"{v_max:.3f}V")

        self.canvas.draw_idle()

    def on_close(self):
        self._disconnect()
        self.destroy()

# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Check dependencies
    missing = []
    try: import serial
    except ImportError: missing.append("pyserial")
    try: import matplotlib
    except ImportError: missing.append("matplotlib")
    try: import numpy
    except ImportError: missing.append("numpy")

    if missing:
        print(f"Missing packages. Run:  pip install {' '.join(missing)}")
        sys.exit(1)

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()