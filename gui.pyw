import json
import os
import tkinter as tk
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

C_BG, C_CARD, C_TXT, C_MUTED = "#0c1424", "#162235", "#ffffff", "#8fa3bf"
BANNER_DURATION_MS = 5 * 60 * 1000  # 5 minutes in milliseconds


class JsonFileHandler(FileSystemEventHandler):
    def __init__(self, target_path, callback):
        self.target_path = os.path.abspath(target_path)
        self.callback = callback

    def _check_and_trigger(self, event):
        if event.is_directory:
            return
        paths = [os.path.abspath(event.src_path)]
        if hasattr(event, "dest_path"):
            paths.append(os.path.abspath(event.dest_path))

        if self.target_path in paths:
            self.callback()

    def on_modified(self, event):
        self._check_and_trigger(event)

    def on_created(self, event):
        self._check_and_trigger(event)

    def on_moved(self, event):
        self._check_and_trigger(event)


class RailDetectorApp(tk.Tk):
    def __init__(self, json_path="rail_telemetry.json"):
        super().__init__()
        self.json_path = os.path.abspath(json_path)
        self.idx = 0
        self.records = []
        self._reload_job = None
        self._banner_job = None

        self.title("Rail Detector Monitor")
        self.geometry("480x620")
        self.configure(bg=C_BG)
        self.setup_ui()

        # Load initial data without triggering the update banner
        self.reload_data(show_banner=False)

        # File Watcher Architecture
        handler = JsonFileHandler(self.json_path, self.schedule_reload)
        self.obs = Observer()
        watch_dir = os.path.dirname(self.json_path) or "."
        self.obs.schedule(handler, path=watch_dir, recursive=False)
        self.obs.start()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.obs.stop()
        self.obs.join()
        self.destroy()

    def schedule_reload(self):
        """Thread-safe debounce: waits 150ms for file writes to finish before reloading."""
        def _debounce():
            if self._reload_job is not None:
                self.after_cancel(self._reload_job)
            self._reload_job = self.after(150, lambda: self.reload_data(show_banner=True))

        self.after(0, _debounce)

    def setup_ui(self):
        # Header & Status Row
        self.hdr = tk.Frame(self, bg="#0f1b2d", height=45)
        self.hdr.pack(fill="x")
        self.hdr.pack_propagate(False)
        tk.Label(self.hdr, text="DefectMon", fg="#3b82f6", bg="#0f1b2d", font=("Segoe UI", 11, "bold")).pack(side="left", padx=15)

        # Update Notification Banner (Hidden by default)
        self.banner_frame = tk.Frame(self, bg="#1e3a5f", highlightbackground="#3b82f6", highlightthickness=1)
        self.banner_lbl = tk.Label(
            self.banner_frame,
            text="",
            fg="#93c5fd",
            bg="#1e3a5f",
            font=("Segoe UI", 9, "bold"),
            pady=6
        )
        self.banner_lbl.pack(fill="x", padx=10)

        # Decoded Message Box
        self.lbl_section = tk.Label(self, text="Latest decoded message", fg=C_TXT, bg=C_BG, font=("Segoe UI", 10, "bold"))
        self.lbl_section.pack(anchor="w", padx=15, pady=(10, 0))
        
        self.msg_f = tk.Frame(self, bg=C_CARD, highlightbackground="#1e2d42", highlightthickness=1)
        self.msg_f.pack(fill="both", expand=True, padx=15, pady=5)

        self.lbl_tag = tk.Label(self.msg_f, text="", fg=C_MUTED, bg=C_CARD, font=("Segoe UI", 8, "bold"))
        self.lbl_tag.pack(anchor="w", padx=15, pady=(8, 2))
        tk.Label(self.msg_f, text="Detector announcement", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=15)

        self.lbl_mp = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_mp.pack(anchor="w", padx=15, pady=2)
        self.lbl_rw = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_rw.pack(anchor="w", padx=15, pady=2)
        self.lbl_df = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_df.pack(anchor="w", padx=15, pady=2)
        self.lbl_tk = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_tk.pack(anchor="w", padx=15, pady=2)
        self.lbl_dn = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_dn.pack(anchor="w", padx=15, pady=2)
        self.lbl_tp = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_tp.pack(anchor="w", padx=15, pady=2)
        self.lbl_xl = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_xl.pack(anchor="w", padx=15, pady=2)
        self.lbl_sp = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_sp.pack(anchor="w", padx=15, pady=2)
        self.lbl_tl = tk.Label(self.msg_f, text="", fg=C_TXT, bg=C_CARD, font=("Segoe UI", 10))
        self.lbl_tl.pack(anchor="w", padx=15, pady=2)

        # Bottom Frame Action Navigation
        bf = tk.Frame(self, bg=C_BG)
        bf.pack(fill="x", padx=15, pady=10)
        tk.Button(bf, text="◀ Previous", bg=C_CARD, fg=C_TXT, bd=0, font=("Segoe UI", 10), command=lambda: self.move(-1)).pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=6)
        tk.Button(bf, text="Next ▶", bg=C_CARD, fg=C_TXT, bd=0, font=("Segoe UI", 10), command=lambda: self.move(1)).pack(side="right", fill="x", expand=True, padx=(5, 0), ipady=6)

    def show_update_banner(self):
        """Displays the update banner for 5 minutes and resets the timer if updated again."""
        now_str = datetime.now().strftime("%I:%M:%S %p")
        self.banner_lbl.config(text=f"● NEW DATA RECEIVED AT {now_str}")
        
        # Pack directly below the header, pushing the rest of the UI down cleanly
        self.banner_frame.pack(fill="x", padx=15, pady=(10, 0), after=self.hdr)

        # Cancel any existing 5-minute countdown and start a fresh one
        if self._banner_job is not None:
            self.after_cancel(self._banner_job)
        self._banner_job = self.after(BANNER_DURATION_MS, self.hide_update_banner)

    def hide_update_banner(self):
        self._banner_job = None
        self.banner_frame.pack_forget()

    def reload_data(self, show_banner=False):
        self._reload_job = None
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.records = data
                    self.idx = max(0, len(self.records) - 1)
                    if show_banner:
                        self.show_update_banner()
            except (json.JSONDecodeError, OSError) as e:
                print(f"Skipping partial/locked read: {e}")
                return
        self.show_record()

    def move(self, step):
        if self.records and (0 <= self.idx + step < len(self.records)):
            self.idx += step
            self.show_record()

    def show_record(self):
        if not self.records:
            self.lbl_tag.config(text="NO RECORDS FOUND")
            return
        r = self.records[self.idx]
        t = r.get("telemetry", {})

        self.lbl_tag.config(text=f"RECORD {self.idx + 1}/{len(self.records)} — {r.get('timestamp')}")
        self.lbl_mp.config(text=f"Milepost: {t.get('milepost') or '—'}")
        self.lbl_rw.config(text=f"Railway: {t.get('railroad') or '—'}")

        df = t.get("defects")
        df_text, df_color = ("!! DEFECT DETECTED !!", "#ef4444") if df is True else (("No defects", "#10b981") if df is False else ("Unknown", C_TXT))
        self.lbl_df.config(text=f"Defects: {df_text}", fg=df_color)

        self.lbl_tk.config(text=f"Track: {t.get('track') or '—'}")
        self.lbl_dn.config(text=f"Direction: {t.get('direction') or '—'}")
        self.lbl_tp.config(text=f"Temperature (F): {t.get('temperature_f') or '—'}")
        self.lbl_xl.config(text=f"Total Axles: {t.get('total_axles') or '—'}")
        self.lbl_sp.config(text=f"Speed (MPH): {t.get('speed_mph') or '—'}")
        self.lbl_tl.config(text=f"Train Length (Feet): {t.get('train_length_feet') or '—'}")


if __name__ == "__main__":
    RailDetectorApp("rail_telemetry.json").mainloop()
