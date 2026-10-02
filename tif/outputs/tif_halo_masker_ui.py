from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parent
MASKER = APP_DIR / "tif_halo_masker.py"
DEFAULT_INPUT = APP_DIR / "segments"
DEFAULT_OUTPUT = APP_DIR / "halo_masked"


class HaloMaskerUi(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bright Object Halo Masker")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.resizable(True, True)

        self.log_queue: queue.Queue[object] = queue.Queue()
        self.running_process: subprocess.Popen[str] | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.preview_source_path: Path | None = None
        self.preview_display_path = APP_DIR / ".halo_preview_display.png"
        self.preview_resize_job: str | None = None

        self.input_path = tk.StringVar(value=str(DEFAULT_INPUT))
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT))
        self.status = tk.StringVar(value="Ready")
        self.use_watershed = tk.BooleanVar(value=True)
        self.output_mode = tk.StringVar(value="masked-zero")
        self.preview_dir = APP_DIR / "halo_previews"

        self.params: dict[str, tk.StringVar] = {
            "layer_index": tk.StringVar(value="2"),
            "seed_threshold": tk.StringVar(value="30000"),
            "min_seed_size": tk.StringVar(value="5"),
            "watershed_distance_ratio": tk.StringVar(value="0.35"),
            "min_marker_size": tk.StringVar(value="3"),
            "gaussian_sigma": tk.StringVar(value="35"),
            "halo_threshold_ratio": tk.StringVar(value="0.02"),
            "max_halo_radius": tk.StringVar(value="160"),
            "core_dilation_radius": tk.StringVar(value="20"),
            "closing_radius": tk.StringVar(value="7"),
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
        self.columnconfigure(0, weight=0, minsize=380)
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
        input_row = ttk.Frame(left)
        input_row.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.input_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="File", command=self._browse_input_file).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(input_row, text="Folder", command=self._browse_input_folder).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(left, text="Output", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=3, column=0, sticky="ew", pady=(8, 12))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._browse_output_folder).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Mask Parameters", style="Title.TLabel").grid(row=4, column=0, sticky="w")
        form = ttk.Frame(left)
        form.grid(row=5, column=0, sticky="ew", pady=(8, 12))
        form.columnconfigure(1, weight=1)

        fields = [
            ("layer index", "layer_index"),
            ("seed threshold", "seed_threshold"),
            ("min seed size", "min_seed_size"),
            ("watershed distance ratio", "watershed_distance_ratio"),
            ("min marker size", "min_marker_size"),
            ("gaussian sigma", "gaussian_sigma"),
            ("halo threshold ratio", "halo_threshold_ratio"),
            ("max halo radius", "max_halo_radius"),
            ("core dilation radius", "core_dilation_radius"),
            ("closing radius", "closing_radius"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(form, textvariable=self.params[key], width=18).grid(row=row, column=1, sticky="ew", pady=3)

        options = ttk.Frame(left)
        options.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        ttk.Checkbutton(options, text="Use watershed", variable=self.use_watershed).grid(row=0, column=0, sticky="w")
        ttk.Label(options, text="Output mode").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            options,
            textvariable=self.output_mode,
            values=("add-mask-layer", "masked-zero", "both"),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        buttons = ttk.Frame(left)
        buttons.grid(row=7, column=0, sticky="ew", pady=(0, 12))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.preview_button = ttk.Button(buttons, text="Preview", style="Run.TButton", command=self._run_preview)
        self.preview_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.apply_button = ttk.Button(buttons, text="Apply", style="Run.TButton", command=self._run_apply)
        self.apply_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(left, textvariable=self.status, style="Status.TLabel", wraplength=340).grid(row=8, column=0, sticky="ew")

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

    def _browse_input_file(self) -> None:
        path = filedialog.askopenfilename(title="Select segment TIFF", filetypes=[("TIFF files", "*.tif *.tiff"), ("All files", "*.*")])
        if path:
            self.input_path.set(path)

    def _browse_input_folder(self) -> None:
        path = filedialog.askdirectory(title="Select folder containing segment TIFFs")
        if path:
            self.input_path.set(path)

    def _browse_output_folder(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir.set(path)

    def _preview_input_path(self) -> Path | None:
        path = Path(self.input_path.get().strip())
        if path.is_file():
            return path
        if path.is_dir():
            files = sorted([*path.glob("*.tif"), *path.glob("*.tiff")])
            if files:
                return files[0]
        return None

    def _base_args(self, preview_input: Path | None = None) -> list[str] | None:
        input_path = preview_input or Path(self.input_path.get().strip())
        if not input_path.exists():
            messagebox.showerror("Missing input", "Select an existing TIFF file or folder.")
            return None

        specs: list[tuple[str, str, type]] = [
            ("layer index", "layer_index", int),
            ("seed threshold", "seed_threshold", int),
            ("min seed size", "min_seed_size", int),
            ("watershed distance ratio", "watershed_distance_ratio", float),
            ("min marker size", "min_marker_size", int),
            ("gaussian sigma", "gaussian_sigma", float),
            ("halo threshold ratio", "halo_threshold_ratio", float),
            ("max halo radius", "max_halo_radius", float),
            ("core dilation radius", "core_dilation_radius", int),
            ("closing radius", "closing_radius", int),
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

        args = [
            str(input_path),
            "--layer-index",
            values["layer_index"],
            "--seed-threshold",
            values["seed_threshold"],
            "--min-seed-size",
            values["min_seed_size"],
            "--watershed-distance-ratio",
            values["watershed_distance_ratio"],
            "--min-marker-size",
            values["min_marker_size"],
            "--gaussian-sigma",
            values["gaussian_sigma"],
            "--halo-threshold-ratio",
            values["halo_threshold_ratio"],
            "--max-halo-radius",
            values["max_halo_radius"],
            "--core-dilation-radius",
            values["core_dilation_radius"],
            "--closing-radius",
            values["closing_radius"],
            "--output-mode",
            self.output_mode.get(),
        ]
        if not self.use_watershed.get():
            args.append("--disable-watershed")
        return args

    def _run_preview(self) -> None:
        preview_input = self._preview_input_path()
        if preview_input is None:
            messagebox.showerror("Missing input", "Select a TIFF file or a folder containing TIFF files.")
            return
        args = self._base_args(preview_input)
        if args is None:
            return

        self.preview_dir.mkdir(parents=True, exist_ok=True)
        temp_output = APP_DIR / ".halo_preview_output"
        temp_output.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(MASKER),
            *args,
            "--output-dir",
            str(temp_output),
            "--preview-dir",
            str(self.preview_dir),
            "--preview-only",
        ]
        self.preview_source_path = self.preview_dir / f"{preview_input.stem}_halo_preview.png"
        self._start_command(command, "Running preview...", on_success=self._load_preview)

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
        preview_dir = output_dir / "previews"
        command = [
            sys.executable,
            str(MASKER),
            *args,
            "--output-dir",
            str(output_dir),
            "--preview-dir",
            str(preview_dir),
        ]
        self._start_command(command, f"Applying. Output: {output_dir}", on_success=lambda: self.status.set(f"Saved: {output_dir}"))

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

    def _load_preview(self) -> None:
        if self.preview_source_path is None or not self.preview_source_path.exists():
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
        height, width = source.shape[:2]
        max_width = max(1, self.preview_label.winfo_width() - 20)
        max_height = max(1, self.preview_label.winfo_height() - 20)
        scale = min(max_width / width, max_height / height)
        target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        resized = cv2.resize(source, target, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        if not cv2.imwrite(str(self.preview_display_path), resized):
            return False
        self.preview_image = tk.PhotoImage(file=str(self.preview_display_path))
        self.preview_label.configure(image=self.preview_image, text="")
        return True


if __name__ == "__main__":
    HaloMaskerUi().mainloop()
