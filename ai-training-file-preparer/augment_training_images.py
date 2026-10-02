from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import tifffile


IMAGE_EXTENSIONS = {".tif", ".tiff"}


@dataclass(frozen=True)
class Augmentation:
    suffix: str
    rotations: int
    flip_lr: bool


AUGMENTATIONS = [
    Augmentation("orig", 0, False),
    Augmentation("rot90", 1, False),
    Augmentation("rot180", 2, False),
    Augmentation("rot270", 3, False),
    Augmentation("orig_flip_lr", 0, True),
    Augmentation("rot90_flip_lr", 1, True),
    Augmentation("rot180_flip_lr", 2, True),
    Augmentation("rot270_flip_lr", 3, True),
]


@dataclass(frozen=True)
class AugmentResult:
    source_path: str
    augmentation: str
    destination_path: str
    status: str
    note: str = ""


def iter_tiff_files(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Input file is not a TIF/TIFF image: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    # When a folder is provided, include all files in the folder (recursive if requested).
    # Reading/writing will be attempted for each file; unsupported formats will be
    # skipped later when reading fails.
    pattern = "**/*" if recursive else "*"
    # Only include files with TIFF extensions to avoid attempting to read
    # unsupported file types later. This ensures folder-mode processes all
    # TIFF files in the directory tree.
    return sorted(
        path
        for path in input_path.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def apply_augmentation(image: np.ndarray, augmentation: Augmentation) -> np.ndarray:
    transformed = image
    if augmentation.rotations:
        transformed = np.rot90(transformed, k=augmentation.rotations, axes=(-2, -1))
    if augmentation.flip_lr:
        transformed = np.flip(transformed, axis=-1)
    return np.ascontiguousarray(transformed)


def destination_for(source_path: Path, output_dir: Path, augmentation: Augmentation) -> Path:
    return output_dir / f"{source_path.stem}_{augmentation.suffix}{source_path.suffix}"


def augment_file(source_path: Path, output_dir: Path, overwrite: bool) -> list[AugmentResult]:
    try:
        image = tifffile.imread(source_path)
    except Exception as exc:
        return [
            AugmentResult(
                source_path=str(source_path),
                augmentation="unsupported",
                destination_path="",
                status="skipped",
                note=f"Failed to read file: {exc}",
            )
        ]

    results: list[AugmentResult] = []

    for augmentation in AUGMENTATIONS:
        destination_path = destination_for(source_path, output_dir, augmentation)
        if destination_path.exists() and not overwrite:
            results.append(
                AugmentResult(
                    source_path=str(source_path),
                    augmentation=augmentation.suffix,
                    destination_path=str(destination_path),
                    status="skipped",
                    note="Destination already exists. Use --overwrite to replace it.",
                )
            )
            continue

        transformed = apply_augmentation(image, augmentation)
        tifffile.imwrite(destination_path, transformed)
        results.append(
            AugmentResult(
                source_path=str(source_path),
                augmentation=augmentation.suffix,
                destination_path=str(destination_path),
                status="written",
            )
        )

    return results


def write_report(output_dir: Path, results: list[AugmentResult]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"augmentation_report_{timestamp}.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_path", "augmentation", "destination_path", "status", "note"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)
    return report_path


def augment_images(input_path: Path, output_dir: Path, recursive: bool, overwrite: bool) -> tuple[list[AugmentResult], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = iter_tiff_files(input_path, recursive)
    if not source_paths:
        raise FileNotFoundError(f"No TIF/TIFF files found in: {input_path}")

    results: list[AugmentResult] = []
    for source_path in source_paths:
        results.extend(augment_file(source_path, output_dir, overwrite))

    report_path = write_report(output_dir, results)
    return results, report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create 8x TIF training data by saving original, 90/180/270 rotations, and LR flips of each.",
    )
    parser.add_argument("input_path", type=Path, help="Source TIF/TIFF file or folder containing TIF/TIFF files.")
    parser.add_argument("output_dir", type=Path, help="Folder where augmented copies will be written.")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When input_path is a folder, search subfolders too.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace augmented files when the destination filenames already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results, report_path = augment_images(args.input_path, args.output_dir, args.recursive, args.overwrite)
    written = sum(1 for result in results if result.status == "written")
    skipped = sum(1 for result in results if result.status == "skipped")
    print(f"Done. Written: {written}, skipped: {skipped}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
