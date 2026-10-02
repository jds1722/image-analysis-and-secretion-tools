from __future__ import annotations

import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parent
ANALYZER = APP_DIR / "tif_bead_intensity_analyzer.py"
DEFAULT_INPUT = APP_DIR / "halo_masked_zero_test"
DEFAULT_OUTPUT = APP_DIR / "bead_measurements"


class BeadAnalyzerUi(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bead Intensity Analyzer")
        self.geometry("1280x780")
        self.minsize(1040, 680)
        self.resizable(True, True)

        self.log_queue: queue.Queue[object] = queue.Queue()
        self.running_process: subprocess.Popen[str] | None = None
        self.preview_images: list[tk.PhotoImage] = []
        self.preview_paths: list[Path] = []
        self.preview_display_paths = [APP_DIR / ".bead_preview_1.png", APP_DIR / ".bead_preview_2.png"]
        self.preview_resize_job: str | None = None

        self.input_path = tk.StringVar(value=str(DEFAULT_INPUT))
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT))
        self.status = tk.StringVar(value="Ready")

        self.params: dict[str, tk.StringVar] = {
            "layer1": tk.StringVar(value="1"),
            "diameter1": tk.StringVar(value="9"),
            "brightness_min1": tk.StringVar(value="10000"),
            "brightness_max1": tk.StringVar(value="65535"),
            "layer2": tk.StringVar(value="3"),
            "diameter2": tk.StringVar(value="9"),
            "brightness_min2": tk.StringVar(value="30000"),
            "brightness_max2": tk.StringVar(value="65535"),
            "diameter_tolerance": tk.StringVar(value="0.35"),
            "min_dist": tk.StringVar(value="6"),
            "dp": tk.StringVar(value="1.2"),
            "param1": tk.StringVar(value="80"),
            "param2": tk.StringVar(value="10"),
            "blur_kernel": tk.StringVar(value="3"),
            "min_roi_fraction": tk.StringVar(value="0.20"),
        }

        self._build_style()
        self._build_layout()
        self.after(100, self._drain_log_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.configure("Panel.TFrame", padding=12)
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Status.TLabel", foreground="#315a85")
        style.configure("Run.TButton", padding=(12, 7))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0, minsize=410)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(left, text="Input Folder", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        input_row = ttk.Frame(left)
        input_row.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.input_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="Browse", command=self._browse_input).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Output Folder", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=3, column=0, sticky="ew", pady=(8, 12))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._browse_output).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Detection And Measurement", style="Title.TLabel").grid(row=4, column=0, sticky="w")
        form = ttk.Frame(left)
        form.grid(row=5, column=0, sticky="ew", pady=(8, 12))
        form.columnconfigure(1, weight=1)

        fields = [
            ("layer 1 index", "layer1"),
            ("layer 1 bead diameter", "diameter1"),
            ("layer 1 brightness min", "brightness_min1"),
            ("layer 1 brightness max", "brightness_max1"),
            ("layer 2 index", "layer2"),
            ("layer 2 bead diameter", "diameter2"),
            ("layer 2 brightness min", "brightness_min2"),
            ("layer 2 brightness max", "brightness_max2"),
            ("diameter tolerance", "diameter_tolerance"),
            ("min dist", "min_dist"),
            ("dp", "dp"),
            ("param1", "param1"),
            ("param2", "param2"),
            ("blur kernel", "blur_kernel"),
            ("min ROI fraction", "min_roi_fraction"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=self.params[key], width=18).grid(row=row, column=1, sticky="ew", pady=2)

        buttons = ttk.Frame(left)
        buttons.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.preview_button = ttk.Button(buttons, text="Preview", style="Run.TButton", command=self._run_preview)
        self.preview_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.apply_button = ttk.Button(buttons, text="Apply", style="Run.TButton", command=self._run_apply)
        self.apply_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(left, textvariable=self.status, style="Status.TLabel", wraplength=370).grid(row=7, column=0, sticky="ew")

        ttk.Label(right, text="Layer Preview 1", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="Layer Preview 2", style="Title.TLabel").grid(row=0, column=1, sticky="w")
        self.preview_labels = [
            ttk.Label(right, text="No preview", anchor="center"),
            ttk.Label(right, text="No preview", anchor="center"),
        ]
        self.preview_labels[0].grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(8, 12))
        self.preview_labels[1].grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(8, 12))
        for label in self.preview_labels:
            label.bind("<Configure>", self._schedule_preview_resize)

        ttk.Label(right, text="Log", style="Title.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        log_frame = ttk.Frame(right)
        log_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=9, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _browse_input(self) -> None:
        path = filedialog.askdirectory(title="Select folder containing masked segment TIFFs")
        if path:
            self.input_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir.set(path)

    def _first_input_file(self) -> Path | None:
        path = Path(self.input_path.get().strip())
        if path.is_file():
            return path
        if path.is_dir():
            files = sorted([*path.glob("*.tif"), *path.glob("*.tiff")])
            if files:
                return files[0]
        return None

    def _base_args(self, input_path: Path | None = None) -> list[str] | None:
        target = input_path or Path(self.input_path.get().strip())
        if not target.exists():
            messagebox.showerror("Missing input", "Select an existing input folder.")
            return None
        specs: list[tuple[str, str, type]] = [
            ("layer 1 index", "layer1", int),
            ("layer 1 bead diameter", "diameter1", float),
            ("layer 1 brightness min", "brightness_min1", int),
            ("layer 1 brightness max", "brightness_max1", int),
            ("layer 2 index", "layer2", int),
            ("layer 2 bead diameter", "diameter2", float),
            ("layer 2 brightness min", "brightness_min2", int),
            ("layer 2 brightness max", "brightness_max2", int),
            ("diameter tolerance", "diameter_tolerance", float),
            ("min dist", "min_dist", float),
            ("dp", "dp", float),
            ("param1", "param1", float),
            ("param2", "param2", float),
            ("blur kernel", "blur_kernel", int),
            ("min ROI fraction", "min_roi_fraction", float),
        ]
        values: dict[str, str] = {}
        try:
            for label, key, caster in specs:
                raw = self.params[key].get().strip()
                caster(raw)
                values[key] = raw
        except ValueError:
            messagebox.showerror("Invalid value", f"Check numeric input for {label}.")
            return None

        return [
            str(target),
            "--layer1",
            values["layer1"],
            "--diameter1",
            values["diameter1"],
            "--brightness-min1",
            values["brightness_min1"],
            "--brightness-max1",
            values["brightness_max1"],
            "--layer2",
            values["layer2"],
            "--diameter2",
            values["diameter2"],
            "--brightness-min2",
            values["brightness_min2"],
            "--brightness-max2",
            values["brightness_max2"],
            "--diameter-tolerance",
            values["diameter_tolerance"],
            "--min-dist",
            values["min_dist"],
            "--dp",
            values["dp"],
            "--param1",
            values["param1"],
            "--param2",
            values["param2"],
            "--blur-kernel",
            values["blur_kernel"],
            "--min-roi-fraction",
            values["min_roi_fraction"],
        ]

    def _run_preview(self) -> None:
        preview_file = self._first_input_file()
        if preview_file is None:
            messagebox.showerror("Missing input", "Input folder has no TIFF files.")
            return
        args = self._base_args(preview_file)
        if args is None:
            return
        preview_dir = APP_DIR / "bead_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        temp_csv = APP_DIR / ".bead_preview_measurements.csv"
        command = [
            sys.executable,
            str(ANALYZER),
            *args,
            "--output-csv",
            str(temp_csv),
            "--preview-dir",
            str(preview_dir),
        ]
        self.preview_paths = [
            preview_dir / f"{preview_file.stem}_layer{self.params['layer1'].get().strip()}_beads.png",
            preview_dir / f"{preview_file.stem}_layer{self.params['layer2'].get().strip()}_beads.png",
        ]
        self._start_command(command, "Running preview...", on_success=self._load_previews)

    def _run_apply(self) -> None:
        args = self._base_args()
        if args is None:
            return
        raw_output = self.output_dir.get().strip()
        if not raw_output:
            messagebox.showerror("Missing output", "Select an output folder.")
            return
        output_dir = Path(raw_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = output_dir / f"bead_measurements_{timestamp}.csv"
        preview_dir = output_dir / "previews"
        command = [
            sys.executable,
            str(ANALYZER),
            *args,
            "--output-csv",
            str(output_csv),
            "--preview-dir",
            str(preview_dir),
        ]
        self._start_command(command, f"Applying. Output CSV: {output_csv}", on_success=lambda: self.status.set(f"Saved: {output_csv}"))

    def _start_command(self, command: list[str], status: str, on_success: object) -> None:
        if self.running_process is not None:
            messagebox.showinfo("Busy", "A command is already running.")
            return
        self._set_running(True)
        self.status.set(status)
        self._append_log("\n$ " + " ".join(command) + "\n")
        threading.Thread(target=self._run_command_thread, args=(command, on_success), daemon=True).start()

    def _run_command_thread(self, command: list[str], on_success: object) -> None:
        return_code = 1
        try:
            self.running_process = subprocess.Popen(
                command,
                cwd=WORKSPACE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert self.running_process.stdout is not None
            for line in self.running_process.stdout:
                self.log_queue.put(line)
            return_code = self.running_process.wait()
        except Exception as exc:
            self.log_queue.put(f"ERROR: {exc}\n")
        finally:
            self.running_process = None
            self.log_queue.put(("__DONE__", return_code, on_success))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    self._set_running(False)
                    return_code = int(item[1])
                    on_success = item[2]
                    if return_code == 0:
                        self.status.set("Done")
                        if callable(on_success):
                            on_success()
                    else:
                        self.status.set(f"Failed with exit code {return_code}")
                    continue
                self._append_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.preview_button.configure(state=state)
        self.apply_button.configure(state=state)

    def _load_previews(self) -> None:
        if not all(path.exists() for path in self.preview_paths):
            self.status.set("Preview finished, but one or more preview PNG files were not created.")
            return
        if self._refresh_preview_images():
            self.status.set("Preview loaded")

    def _schedule_preview_resize(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        if not self.preview_paths:
            return
        if self.preview_resize_job is not None:
            self.after_cancel(self.preview_resize_job)
        self.preview_resize_job = self.after(120, self._refresh_preview_images)

    def _refresh_preview_images(self) -> bool:
        self.preview_resize_job = None
        if len(self.preview_paths) != 2 or not all(path.exists() for path in self.preview_paths):
            return False
        self.preview_images = []
        for index, path in enumerate(self.preview_paths):
            source = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if source is None:
                return False
            height, width = source.shape[:2]
            label = self.preview_labels[index]
            max_width = max(1, label.winfo_width() - 20)
            max_height = max(1, label.winfo_height() - 20)
            scale = min(max_width / width, max_height / height)
            target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
            resized = cv2.resize(source, target, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            if not cv2.imwrite(str(self.preview_display_paths[index]), resized):
                return False
            image = tk.PhotoImage(file=str(self.preview_display_paths[index]))
            self.preview_images.append(image)
            label.configure(image=image, text="")
        return True


if __name__ == "__main__":
    BeadAnalyzerUi().mainloop()
