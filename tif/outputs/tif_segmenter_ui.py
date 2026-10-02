from __future__ import annotations

import queue
import re
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
SEGMENTER = APP_DIR / "multilayer_tif_circle_segmenter.py"
DEFAULT_TIF = next((WORKSPACE_DIR / "work").glob("*.tif"), "")
DEFAULT_OUTPUT_DIR = APP_DIR / "segments"


def extract_well_prefix(path: Path) -> str:
    match = re.match(r"^(Well[A-Za-z]+[0-9]+)", path.stem)
    return match.group(1) if match else ""


def prefixed_name(prefix: str, name: str) -> str:
    return f"{prefix}_{name}" if prefix else name


class SegmenterUi(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Multilayer TIF Circle Segmenter")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.resizable(True, True)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.running_process: subprocess.Popen[str] | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.preview_source_path: Path | None = None
        self.preview_display_path = APP_DIR / ".preview_display.png"
        self.preview_resize_job: str | None = None

        self.input_path = tk.StringVar(value=str(DEFAULT_TIF) if DEFAULT_TIF else "")
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.last_input_dir = DEFAULT_TIF.parent if DEFAULT_TIF else WORKSPACE_DIR / "work"
        self.last_output_dir = DEFAULT_OUTPUT_DIR
        self.status = tk.StringVar(value="Ready")
        self.preview_path = APP_DIR / "detected_circles_preview_ui.png"
        self.exclude_multiple_cell_regions = tk.BooleanVar(value=True)
        self.allow_edge_clipping = tk.BooleanVar(value=True)
        self.preview_roi_numbers = tk.BooleanVar(value=False)

        self.params: dict[str, tk.StringVar] = {
            "circle_diameter": tk.StringVar(value="1515"),
            "diameter_tolerance": tk.StringVar(value="0.10"),
            "min_radius": tk.StringVar(value="10"),
            "max_radius": tk.StringVar(value="0"),
            "min_dist": tk.StringVar(value="100"),
            "param1": tk.StringVar(value="100"),
            "param2": tk.StringVar(value="30"),
            "dp": tk.StringVar(value="1.2"),
            "overlap_merge_center_tolerance": tk.StringVar(value="0.25"),
            "min_cell_threshold": tk.StringVar(value="2000"),
            "max_cell_threshold": tk.StringVar(value="33000"),
            "min_cell_area": tk.StringVar(value="5000"),
            "max_cell_area": tk.StringVar(value="300000"),
            "cell_search_circle_inset": tk.StringVar(value="400"),
            "segment_diagonal_padding": tk.StringVar(value="300"),
        }

        self._build_style()
        self._build_layout()
        self.after(100, self._drain_log_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.configure("TFrame", padding=0)
        style.configure("Panel.TFrame", padding=12)
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Status.TLabel", foreground="#315a85")
        style.configure("Run.TButton", padding=(12, 7))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0, minsize=360)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(left, text="Input", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        file_row = ttk.Frame(left)
        file_row.grid(row=1, column=0, sticky="ew", pady=(8, 16))
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.input_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(file_row, text="Browse", command=self._browse_file).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Output", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=3, column=0, sticky="ew", pady=(8, 16))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._browse_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Circle Detection", style="Title.TLabel").grid(row=4, column=0, sticky="w")
        form = ttk.Frame(left)
        form.grid(row=5, column=0, sticky="ew", pady=(8, 16))
        form.columnconfigure(1, weight=1)

        fields = [
            ("circle diameter", "circle_diameter"),
            ("diameter tolerance", "diameter_tolerance"),
            ("min radius", "min_radius"),
            ("max radius", "max_radius"),
            ("min dist", "min_dist"),
            ("param1", "param1"),
            ("param2", "param2"),
            ("dp", "dp"),
            ("overlap merge tolerance", "overlap_merge_center_tolerance"),
            ("min cell threshold", "min_cell_threshold"),
            ("max cell threshold", "max_cell_threshold"),
            ("min cell region area", "min_cell_area"),
            ("max cell region area", "max_cell_area"),
            ("cell search circle inset", "cell_search_circle_inset"),
            ("segment diagonal padding", "segment_diagonal_padding"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=self.params[key], width=18).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(
            form,
            text="exclude multiple cell regions",
            variable=self.exclude_multiple_cell_regions,
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 4))
        ttk.Checkbutton(
            form,
            text="allow edge clipping",
            variable=self.allow_edge_clipping,
        ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            form,
            text="show ROI numbers in preview",
            variable=self.preview_roi_numbers,
        ).grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", pady=4)

        button_row = ttk.Frame(left)
        button_row.grid(row=6, column=0, sticky="ew", pady=(0, 16))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        self.preview_button = ttk.Button(button_row, text="Preview", style="Run.TButton", command=self._run_preview)
        self.preview_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.apply_button = ttk.Button(button_row, text="Apply", style="Run.TButton", command=self._run_apply)
        self.apply_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(left, textvariable=self.status, style="Status.TLabel", wraplength=320).grid(row=7, column=0, sticky="ew")

        ttk.Label(right, text="Preview", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.preview_label = ttk.Label(right, text="No preview yet", anchor="center")
        self.preview_label.grid(row=1, column=0, sticky="nsew", pady=(8, 12))
        self.preview_label.bind("<Configure>", self._schedule_preview_resize)

        ttk.Label(right, text="Log", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        log_frame = ttk.Frame(right)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=9, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _browse_file(self) -> None:
        current_input = Path(self.input_path.get().strip())
        if current_input.parent.exists():
            self.last_input_dir = current_input.parent
        path = filedialog.askopenfilename(
            initialdir=str(self.last_input_dir),
            title="Select multilayer TIFF",
            filetypes=[("TIFF files", "*.tif *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.input_path.set(path)
            self.last_input_dir = Path(path).parent

    def _browse_output_dir(self) -> None:
        current_output = Path(self.output_dir.get().strip())
        if current_output.exists():
            self.last_output_dir = current_output
        elif current_output.parent.exists():
            self.last_output_dir = current_output.parent
        path = filedialog.askdirectory(
            initialdir=str(self.last_output_dir),
            title="Select output folder for segment TIFFs",
        )
        if path:
            self.output_dir.set(path)
            self.last_output_dir = Path(path)

    def _validate_params(self) -> list[str] | None:
        path = Path(self.input_path.get().strip())
        if not path.exists():
            messagebox.showerror("Missing file", "Select an existing TIFF file.")
            return None

        specs: list[tuple[str, str, type]] = [
            ("circle diameter", "circle_diameter", float),
            ("diameter tolerance", "diameter_tolerance", float),
            ("min radius", "min_radius", int),
            ("max radius", "max_radius", int),
            ("min dist", "min_dist", float),
            ("param1", "param1", float),
            ("param2", "param2", float),
            ("dp", "dp", float),
            ("overlap merge tolerance", "overlap_merge_center_tolerance", float),
            ("min cell threshold", "min_cell_threshold", int),
            ("max cell threshold", "max_cell_threshold", int),
            ("min cell region area", "min_cell_area", int),
            ("max cell region area", "max_cell_area", int),
            ("cell search circle inset", "cell_search_circle_inset", float),
            ("segment diagonal padding", "segment_diagonal_padding", float),
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
        if int(values["max_cell_threshold"]) < int(values["min_cell_threshold"]):
            messagebox.showerror("Invalid range", "max cell threshold must be greater than or equal to min cell threshold.")
            return None
        if int(values["max_cell_area"]) < int(values["min_cell_area"]):
            messagebox.showerror("Invalid range", "max cell region area must be greater than or equal to min cell region area.")
            return None
        if float(values["cell_search_circle_inset"]) < 0:
            messagebox.showerror("Invalid value", "cell search circle inset must be zero or greater.")
            return None
        if float(values["segment_diagonal_padding"]) < 0:
            messagebox.showerror("Invalid value", "segment diagonal padding must be zero or greater.")
            return None

        args = [
            str(path),
            "--min-cell-threshold",
            values["min_cell_threshold"],
            "--max-cell-threshold",
            values["max_cell_threshold"],
            "--min-cell-area",
            values["min_cell_area"],
            "--max-cell-area",
            values["max_cell_area"],
            "--cell-search-circle-inset",
            values["cell_search_circle_inset"],
            "--segment-diagonal-padding",
            values["segment_diagonal_padding"],
            "--circle-diameter",
            values["circle_diameter"],
            "--diameter-tolerance",
            values["diameter_tolerance"],
            "--min-radius",
            values["min_radius"],
            "--max-radius",
            values["max_radius"],
            "--min-dist",
            values["min_dist"],
            "--param1",
            values["param1"],
            "--param2",
            values["param2"],
            "--dp",
            values["dp"],
            "--overlap-merge-center-tolerance",
            values["overlap_merge_center_tolerance"],
            "--downsample-max-dim",
            "2048",
        ]
        if self.exclude_multiple_cell_regions.get():
            args.append("--exclude-multiple-cell-regions")
        if self.allow_edge_clipping.get():
            args.append("--allow-edge-clipping")
        if self.preview_roi_numbers.get():
            args.append("--preview-roi-numbers")
        return args

    def _run_preview(self) -> None:
        args = self._validate_params()
        if args is None:
            return
        well_prefix = extract_well_prefix(Path(self.input_path.get().strip()))
        self.preview_path = APP_DIR / prefixed_name(well_prefix, "detected_circles_preview_ui.png")
        command = [
            sys.executable,
            str(SEGMENTER),
            *args,
            "--preview-only",
            "--preview-output",
            str(self.preview_path),
            "--preview-max-dim",
            "2048",
        ]
        self._start_command(command, "Running preview...", on_success=self._load_preview)

    def _run_apply(self) -> None:
        args = self._validate_params()
        if args is None:
            return

        raw_output_dir = self.output_dir.get().strip()
        if not raw_output_dir:
            messagebox.showerror("Missing output", "Select an output folder.")
            return
        output_dir = Path(raw_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_dir = output_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        well_prefix = extract_well_prefix(Path(self.input_path.get().strip()))
        coords_csv = output_dir / prefixed_name(well_prefix, f"selected_squares_{timestamp}.csv")
        preview_png = preview_dir / prefixed_name(well_prefix, f"detected_circles_preview_{timestamp}.png")
        command = [
            sys.executable,
            str(SEGMENTER),
            *args,
            "--preview-output",
            str(preview_png),
            "--output-dir",
            str(output_dir),
            "--coords-csv",
            str(coords_csv),
            "--filename-prefix",
            well_prefix,
            "--overwrite",
        ]
        self._start_command(command, f"Applying. Output: {output_dir}", on_success=lambda: self._apply_done(output_dir, preview_png))

    def _start_command(self, command: list[str], status: str, on_success: object) -> None:
        if self.running_process is not None:
            messagebox.showinfo("Busy", "A command is already running.")
            return

        self._set_running(True)
        self.status.set(status)
        self._append_log("\n$ " + " ".join(command) + "\n")

        thread = threading.Thread(target=self._run_command_thread, args=(command, on_success), daemon=True)
        thread.start()

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
            self.log_queue.put(("__DONE__", return_code, on_success))  # type: ignore[arg-type]

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    return_code = int(item[1])
                    on_success = item[2]
                    self._set_running(False)
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

    def _load_preview(self) -> None:
        self.preview_source_path = self.preview_path
        if not self.preview_source_path.exists():
            self.status.set("Preview finished, but no PNG was created.")
            return

        if self._refresh_preview_image():
            self.status.set(f"Preview saved: {self.preview_source_path}")

    def _schedule_preview_resize(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        if self.preview_source_path is None:
            return
        if self.preview_resize_job is not None:
            self.after_cancel(self.preview_resize_job)
        self.preview_resize_job = self.after(120, self._refresh_preview_image)

    def _refresh_preview_image(self) -> bool:
        self.preview_resize_job = None
        if self.preview_source_path is None or not self.preview_source_path.exists():
            return False

        source = cv2.imread(str(self.preview_source_path), cv2.IMREAD_COLOR)
        if source is None:
            self.status.set(f"Could not read preview: {self.preview_source_path}")
            return False

        source_height, source_width = source.shape[:2]
        max_width = max(1, self.preview_label.winfo_width() - 20)
        max_height = max(1, self.preview_label.winfo_height() - 20)
        scale = min(max_width / source_width, max_height / source_height)
        target_width = max(1, int(round(source_width * scale)))
        target_height = max(1, int(round(source_height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        display = cv2.resize(source, (target_width, target_height), interpolation=interpolation)
        if not cv2.imwrite(str(self.preview_display_path), display):
            self.status.set(f"Could not write display preview: {self.preview_display_path}")
            return False

        self.preview_image = tk.PhotoImage(file=str(self.preview_display_path))
        self.preview_label.configure(image=self.preview_image, text="")
        return True

    def _apply_done(self, output_dir: Path, preview: Path) -> None:
        self.status.set(f"Segments saved: {output_dir}")
        if preview.exists():
            self.preview_path = preview
            self._load_preview()


if __name__ == "__main__":
    SegmenterUi().mainloop()
