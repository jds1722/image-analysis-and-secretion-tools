from __future__ import annotations

import csv
import queue
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_DIR / "input_files"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "prepared_files"


@dataclass(frozen=True)
class CopyResult:
    requested_name: str
    status: str
    source_path: str = ""
    destination_path: str = ""
    note: str = ""


def parse_file_names(raw_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        for part in line.split(","):
            name = part.strip().strip('"').strip("'")
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)
    return names


def build_file_index(input_dir: Path, recursive: bool, case_sensitive: bool) -> dict[str, list[Path]]:
    pattern = "**/*" if recursive else "*"
    index: dict[str, list[Path]] = {}
    for path in input_dir.glob(pattern):
        if not path.is_file():
            continue
        key = path.name if case_sensitive else path.name.lower()
        index.setdefault(key, []).append(path)
    return index


def unique_destination(destination_dir: Path, source_name: str) -> Path:
    candidate = destination_dir / source_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        next_candidate = destination_dir / f"{stem}_copy{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


class TrainingFilePreparerUi(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Training File Preparer")
        self.geometry("980x680")
        self.minsize(820, 560)
        self.resizable(True, True)

        default_input = DEFAULT_INPUT_DIR if DEFAULT_INPUT_DIR.exists() else PROJECT_DIR
        self.input_dir = tk.StringVar(value=str(default_input))
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.status = tk.StringVar(value="Ready")
        self.recursive = tk.BooleanVar(value=True)
        self.case_sensitive = tk.BooleanVar(value=False)
        self.copy_all_matches = tk.BooleanVar(value=False)
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

        ttk.Label(left, text="Source Folder", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        input_row = ttk.Frame(left)
        input_row.grid(row=1, column=0, sticky="ew", pady=(8, 16))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.input_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="Browse", command=self._browse_input_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Destination Folder", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=3, column=0, sticky="ew", pady=(8, 16))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._browse_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="Options", style="Title.TLabel").grid(row=4, column=0, sticky="w")
        options = ttk.Frame(left)
        options.grid(row=5, column=0, sticky="ew", pady=(8, 16))
        ttk.Checkbutton(options, text="Search subfolders", variable=self.recursive).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(options, text="Case-sensitive filename match", variable=self.case_sensitive).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Checkbutton(options, text="Copy every match when duplicates exist", variable=self.copy_all_matches).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Checkbutton(options, text="Overwrite existing destination files", variable=self.overwrite).grid(row=3, column=0, sticky="w", pady=2)

        button_row = ttk.Frame(left)
        button_row.grid(row=6, column=0, sticky="ew", pady=(0, 16))
        button_row.columnconfigure(0, weight=1)
        self.copy_button = ttk.Button(button_row, text="Find and Copy", style="Run.TButton", command=self._start_copy)
        self.copy_button.grid(row=0, column=0, sticky="ew")

        ttk.Label(left, textvariable=self.status, style="Status.TLabel", wraplength=330).grid(row=7, column=0, sticky="ew")

        ttk.Label(right, text="File Names", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        names_frame = ttk.Frame(right)
        names_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 16))
        names_frame.columnconfigure(0, weight=1)
        names_frame.rowconfigure(0, weight=1)
        self.names_text = tk.Text(names_frame, height=14, wrap="none", undo=True)
        self.names_text.grid(row=0, column=0, sticky="nsew")
        names_scroll = ttk.Scrollbar(names_frame, orient="vertical", command=self.names_text.yview)
        names_scroll.grid(row=0, column=1, sticky="ns")
        self.names_text.configure(yscrollcommand=names_scroll.set)
        self.names_text.insert("1.0", "example.tif\nanother_file.csv")

        ttk.Label(right, text="Log", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        log_frame = ttk.Frame(right)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

    def _browse_input_dir(self) -> None:
        path = filedialog.askdirectory(title="Select source folder")
        if path:
            self.input_dir.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select destination folder")
        if path:
            self.output_dir.set(path)

    def _start_copy(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Already running", "Copy is already in progress.")
            return

        input_dir = Path(self.input_dir.get().strip())
        output_dir = Path(self.output_dir.get().strip())
        names = parse_file_names(self.names_text.get("1.0", "end"))

        if not input_dir.is_dir():
            messagebox.showerror("Missing source folder", "Select an existing source folder.")
            return
        if not names:
            messagebox.showerror("Missing file names", "Enter at least one filename.")
            return
        if input_dir.resolve() == output_dir.resolve():
            messagebox.showerror("Invalid destination", "Source and destination folders must be different.")
            return

        self._clear_log()
        self.copy_button.configure(state="disabled")
        self.status.set("Searching...")
        settings = {
            "recursive": self.recursive.get(),
            "case_sensitive": self.case_sensitive.get(),
            "copy_all_matches": self.copy_all_matches.get(),
            "overwrite": self.overwrite.get(),
        }
        self.worker = threading.Thread(
            target=self._copy_worker,
            args=(input_dir, output_dir, names, settings),
            daemon=True,
        )
        self.worker.start()

    def _copy_worker(self, input_dir: Path, output_dir: Path, names: list[str], settings: dict[str, bool]) -> None:
        results: list[CopyResult] = []
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            self.log_queue.put(f"Indexing files in: {input_dir}\n")
            index = build_file_index(input_dir, settings["recursive"], settings["case_sensitive"])

            copied_count = 0
            missing_count = 0
            for requested_name in names:
                key = requested_name if settings["case_sensitive"] else requested_name.lower()
                matches = sorted(index.get(key, []))
                if not matches:
                    missing_count += 1
                    results.append(CopyResult(requested_name, "missing", note="No matching file found."))
                    self.log_queue.put(f"[MISSING] {requested_name}\n")
                    continue

                selected_matches = matches if settings["copy_all_matches"] else matches[:1]
                if len(matches) > 1 and not settings["copy_all_matches"]:
                    self.log_queue.put(f"[DUPLICATE] {requested_name}: copied first of {len(matches)} matches.\n")

                for source_path in selected_matches:
                    destination_path = output_dir / source_path.name
                    if destination_path.exists() and not settings["overwrite"]:
                        destination_path = unique_destination(output_dir, source_path.name)
                    shutil.copy2(source_path, destination_path)
                    copied_count += 1
                    results.append(
                        CopyResult(
                            requested_name=requested_name,
                            status="copied",
                            source_path=str(source_path),
                            destination_path=str(destination_path),
                        )
                    )
                    self.log_queue.put(f"[COPIED] {source_path} -> {destination_path}\n")

            report_path = self._write_report(output_dir, results)
            summary = f"Done. Copied {copied_count} file(s), missing {missing_count}. Report: {report_path}"
            self.log_queue.put(f"\n{summary}\n")
            self.log_queue.put(("done", summary))
        except Exception as exc:
            self.log_queue.put(("error", str(exc)))

    def _write_report(self, output_dir: Path, results: list[CopyResult]) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"file_copy_report_{timestamp}.csv"
        with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["requested_name", "status", "source_path", "destination_path", "note"],
            )
            writer.writeheader()
            for result in results:
                writer.writerow(result.__dict__)
        return report_path

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
                    self.copy_button.configure(state="normal")
                    if kind == "error":
                        self.status.set("Error")
                        messagebox.showerror("Copy failed", message)
                    else:
                        self.status.set(message)
                        messagebox.showinfo("Copy complete", message)
                else:
                    self._append_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)


if __name__ == "__main__":
    TrainingFilePreparerUi().mainloop()
