from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from augment_training_images import augment_images


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_DIR / "input_files"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "augmented_files"


class AugmentTrainingImagesUi(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Training Image Augmenter")
        self.geometry("980x640")
        self.minsize(820, 520)
        self.resizable(True, True)

        default_input = DEFAULT_INPUT_DIR if DEFAULT_INPUT_DIR.exists() else PROJECT_DIR
        self.input_path = tk.StringVar(value=str(default_input))
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.status = tk.StringVar(value="Ready")
        self.recursive = tk.BooleanVar(value=True)
        self.overwrite = tk.BooleanVar(value=False)
        self.log_queue: queue.Queue[object] = queue.Queue()
        self.worker: threading.Thread | None = None

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
        self.columnconfigure(0, weight=0, minsize=370)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(left, text="Input", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        input_row = ttk.Frame(left)
        input_row.grid(row=1, column=0, sticky="ew", pady=(8, 16))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.input_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="File", command=self._browse_input_file).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(input_row, text="Folder", command=self._browse_input_folder).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(left, text="Output Folder", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=3, column=0, sticky="ew", pady=(8, 16))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._browse_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Options", style="Title.TLabel").grid(row=4, column=0, sticky="w")
        options = ttk.Frame(left)
        options.grid(row=5, column=0, sticky="ew", pady=(8, 16))
        ttk.Checkbutton(options, text="Search subfolders when input is a folder", variable=self.recursive).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(options, text="Overwrite existing augmented files", variable=self.overwrite).grid(row=1, column=0, sticky="w", pady=2)

        button_row = ttk.Frame(left)
        button_row.grid(row=6, column=0, sticky="ew", pady=(0, 16))
        button_row.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(button_row, text="Create 8x Augmented Images", style="Run.TButton", command=self._start_augmentation)
        self.run_button.grid(row=0, column=0, sticky="ew")

        ttk.Label(left, textvariable=self.status, style="Status.TLabel", wraplength=340).grid(row=7, column=0, sticky="ew")

        ttk.Label(right, text="Log", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        log_frame = ttk.Frame(right)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=18, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

    def _browse_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select source TIF/TIFF image",
            filetypes=[("TIFF files", "*.tif *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.input_path.set(path)

    def _browse_input_folder(self) -> None:
        path = filedialog.askdirectory(title="Select source folder")
        if path:
            self.input_path.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir.set(path)

    def _start_augmentation(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Already running", "Augmentation is already in progress.")
            return

        input_path = Path(self.input_path.get().strip())
        output_dir = Path(self.output_dir.get().strip())
        if not input_path.exists():
            messagebox.showerror("Missing input", "Select an existing TIF/TIFF file or source folder.")
            return
        if input_path.is_dir() and input_path.resolve() == output_dir.resolve():
            messagebox.showerror("Invalid output", "Input and output folders must be different.")
            return

        self._clear_log()
        self.run_button.configure(state="disabled")
        self.status.set("Running augmentation...")
        self.worker = threading.Thread(
            target=self._augmentation_worker,
            args=(input_path, output_dir, self.recursive.get(), self.overwrite.get()),
            daemon=True,
        )
        self.worker.start()

    def _augmentation_worker(self, input_path: Path, output_dir: Path, recursive: bool, overwrite: bool) -> None:
        try:
            self.log_queue.put(f"Input: {input_path}\n")
            self.log_queue.put(f"Output: {output_dir}\n")
            self.log_queue.put("Creating original, rotations, and left-right flipped copies...\n\n")
            results, report_path = augment_images(input_path, output_dir, recursive, overwrite)
            written = sum(1 for result in results if result.status == "written")
            skipped = sum(1 for result in results if result.status == "skipped")
            for result in results:
                label = "WRITTEN" if result.status == "written" else "SKIPPED"
                self.log_queue.put(f"[{label}] {result.destination_path}\n")

            summary = f"Done. Written: {written}, skipped: {skipped}. Report: {report_path}"
            self.log_queue.put(f"\n{summary}\n")
            self.log_queue.put(("done", summary))
        except Exception as exc:
            self.log_queue.put(("error", str(exc)))

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple):
                    kind, message = item
                    self.run_button.configure(state="normal")
                    if kind == "error":
                        self.status.set("Error")
                        messagebox.showerror("Augmentation failed", message)
                    else:
                        self.status.set(message)
                        messagebox.showinfo("Augmentation complete", message)
                else:
                    self._append_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)


if __name__ == "__main__":
    AugmentTrainingImagesUi().mainloop()
