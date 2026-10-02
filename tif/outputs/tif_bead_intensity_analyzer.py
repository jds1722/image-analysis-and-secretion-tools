from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import tifffile


UINT16_MAX = 65535


@dataclass(frozen=True)
class Bead:
    index: int
    x: float
    y: float
    radius: float
    mean_brightness: float
    min_brightness: int
    max_brightness: int
    pixel_count: int


def read_stack(path: Path) -> np.ndarray:
    with tifffile.TiffFile(path) as tif:
        pages = [page.asarray() for page in tif.pages if len(page.shape) == 2]
    if pages:
        return np.stack(pages, axis=0)
    arr = tifffile.imread(path)
    if arr.ndim == 2:
        return arr[np.newaxis, ...]
    if arr.ndim == 3:
        return arr
    raise ValueError(f"Unsupported TIFF shape for {path}: {arr.shape!r}")


def normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    low, high = np.percentile(image, (0.5, 99.7))
    if high <= low:
        low = float(np.min(image))
        high = float(np.max(image))
    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)
    return np.clip((image.astype(np.float32) - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)


def bead_radius_bounds(diameter: float, tolerance: float) -> tuple[int, int]:
    if diameter <= 0:
        raise ValueError("Bead diameter must be greater than zero.")
    if tolerance < 0:
        raise ValueError("Diameter tolerance must be zero or greater.")
    if tolerance <= 1:
        min_diameter = diameter * (1.0 - tolerance)
        max_diameter = diameter * (1.0 + tolerance)
    else:
        min_diameter = diameter - tolerance
        max_diameter = diameter + tolerance
    return max(1, int(math.floor(min_diameter / 2.0))), max(1, int(math.ceil(max_diameter / 2.0)))


def circle_mask(shape: tuple[int, int], x: float, y: float, radius: float) -> np.ndarray:
    height, width = shape
    x0 = max(0, int(math.floor(x - radius)))
    y0 = max(0, int(math.floor(y - radius)))
    x1 = min(width, int(math.ceil(x + radius)) + 1)
    y1 = min(height, int(math.ceil(y + radius)) + 1)
    mask = np.zeros(shape, dtype=bool)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    local = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
    mask[y0:y1, x0:x1] = local
    return mask


def prepare_detection_image(layer: np.ndarray, brightness_min: int, brightness_max: int, blur_kernel: int) -> np.ndarray:
    in_range = (layer >= brightness_min) & (layer <= brightness_max)
    clipped = np.where(in_range, layer, 0)
    image = normalize_to_uint8(clipped)
    if blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        image = cv2.medianBlur(image, blur_kernel)
    return image


def detect_beads(
    layer: np.ndarray,
    *,
    bead_diameter: float,
    diameter_tolerance: float,
    brightness_min: int,
    brightness_max: int,
    dp: float,
    min_dist: float,
    param1: float,
    param2: float,
    blur_kernel: int,
    min_roi_fraction: float,
) -> list[Bead]:
    min_radius, max_radius = bead_radius_bounds(bead_diameter, diameter_tolerance)
    detection_image = prepare_detection_image(layer, brightness_min, brightness_max, blur_kernel)
    circles = cv2.HoughCircles(
        detection_image,
        cv2.HOUGH_GRADIENT,
        dp=dp,
        minDist=max(1.0, min_dist),
        param1=param1,
        param2=param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []

    detected = circles[0]
    order = np.lexsort((detected[:, 0], detected[:, 1]))
    beads: list[Bead] = []
    for circle_index in order:
        x, y, radius = detected[circle_index]
        mask = circle_mask(layer.shape, float(x), float(y), float(radius))
        values = layer[mask]
        if values.size == 0:
            continue
        in_range = (values >= brightness_min) & (values <= brightness_max)
        if float(np.count_nonzero(in_range)) / float(values.size) < min_roi_fraction:
            continue
        measured_values = values[in_range]
        if measured_values.size == 0:
            continue
        beads.append(
            Bead(
                index=len(beads),
                x=float(x),
                y=float(y),
                radius=float(radius),
                mean_brightness=float(np.mean(measured_values)),
                min_brightness=int(np.min(measured_values)),
                max_brightness=int(np.max(measured_values)),
                pixel_count=int(measured_values.size),
            )
        )
    return beads


def draw_bead_preview(layer: np.ndarray, beads: list[Bead], output_path: Path, color: tuple[int, int, int]) -> None:
    preview = cv2.cvtColor(normalize_to_uint8(layer), cv2.COLOR_GRAY2BGR)
    for bead in beads:
        center = (int(round(bead.x)), int(round(bead.y)))
        cv2.drawMarker(preview, center, (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=9, thickness=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), preview):
        raise RuntimeError(f"Failed to write preview: {output_path}")


def iter_tif_files(input_dir: Path) -> list[Path]:
    if input_dir.is_file():
        return [input_dir]
    if input_dir.is_dir():
        return sorted([*input_dir.glob("*.tif"), *input_dir.glob("*.tiff")])
    raise FileNotFoundError(input_dir)


def write_csv_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "file",
                "measurement_group",
                "layer_index",
                "bead_count",
                "mean_of_bead_mean_brightness",
                "median_of_bead_mean_brightness",
                "q1_of_bead_mean_brightness",
                "q3_of_bead_mean_brightness",
                "iqr_of_bead_mean_brightness",
                "min_of_bead_mean_brightness",
                "max_of_bead_mean_brightness",
            ]
        )


def append_bead_summary_to_csv(path: Path, file_path: Path, group: str, layer_index: int, beads: list[Bead]) -> None:
    bead_means = np.array([bead.mean_brightness for bead in beads], dtype=np.float64)
    if bead_means.size:
        q1, median, q3 = np.percentile(bead_means, (25, 50, 75))
        mean_value = float(np.mean(bead_means))
        min_value = float(np.min(bead_means))
        max_value = float(np.max(bead_means))
        iqr = float(q3 - q1)
        summary_values = [
            f"{mean_value:.3f}",
            f"{median:.3f}",
            f"{q1:.3f}",
            f"{q3:.3f}",
            f"{iqr:.3f}",
            f"{min_value:.3f}",
            f"{max_value:.3f}",
        ]
    else:
        summary_values = [""] * 7

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                file_path.name,
                group,
                layer_index,
                len(beads),
                *summary_values,
            ]
        )


def process_file(path: Path, args: argparse.Namespace, csv_path: Path) -> None:
    stack = read_stack(path)
    for layer_index in (args.layer1, args.layer2):
        if layer_index < 0 or layer_index >= stack.shape[0]:
            raise ValueError(f"{path.name}: layer {layer_index} is outside stack with {stack.shape[0]} layers.")

    layer1 = stack[args.layer1]
    layer2 = stack[args.layer2]
    beads1 = detect_beads(
        layer1,
        bead_diameter=args.diameter1,
        diameter_tolerance=args.diameter_tolerance,
        brightness_min=args.brightness_min1,
        brightness_max=args.brightness_max1,
        dp=args.dp,
        min_dist=args.min_dist,
        param1=args.param1,
        param2=args.param2,
        blur_kernel=args.blur_kernel,
        min_roi_fraction=args.min_roi_fraction,
    )
    beads2 = detect_beads(
        layer2,
        bead_diameter=args.diameter2,
        diameter_tolerance=args.diameter_tolerance,
        brightness_min=args.brightness_min2,
        brightness_max=args.brightness_max2,
        dp=args.dp,
        min_dist=args.min_dist,
        param1=args.param1,
        param2=args.param2,
        blur_kernel=args.blur_kernel,
        min_roi_fraction=args.min_roi_fraction,
    )

    append_bead_summary_to_csv(csv_path, path, "layer1", args.layer1, beads1)
    append_bead_summary_to_csv(csv_path, path, "layer2", args.layer2, beads2)

    if args.preview_dir:
        draw_bead_preview(layer1, beads1, args.preview_dir / f"{path.stem}_layer{args.layer1}_beads.png", (0, 255, 0))
        draw_bead_preview(layer2, beads2, args.preview_dir / f"{path.stem}_layer{args.layer2}_beads.png", (255, 0, 255))

    print(f"{path.name}: layer {args.layer1} beads={len(beads1)}, layer {args.layer2} beads={len(beads2)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect small circular beads in two layers of masked segment TIFFs and measure mean brightness.")
    parser.add_argument("input_path", type=Path, help="Input TIFF file or folder containing masked segment TIFFs.")
    parser.add_argument("--output-csv", type=Path, required=True, help="CSV path for bead measurements.")
    parser.add_argument("--preview-dir", type=Path, default=None, help="Optional preview PNG output directory.")
    parser.add_argument("--layer1", type=int, default=1, help="Input #1: first layer index. Default: 1.")
    parser.add_argument("--diameter1", type=float, default=9.0, help="Input #2: first bead diameter in pixels. Default: 9.")
    parser.add_argument("--brightness-min1", type=int, default=10000, help="First layer bead brightness minimum. Default: 10000.")
    parser.add_argument("--brightness-max1", type=int, default=UINT16_MAX, help="First layer bead brightness maximum. Default: 65535.")
    parser.add_argument("--layer2", type=int, default=3, help="Input #3: second layer index. Default: 3.")
    parser.add_argument("--diameter2", type=float, default=9.0, help="Input #4: second bead diameter in pixels. Default: 9.")
    parser.add_argument("--brightness-min2", type=int, default=30000, help="Second layer bead brightness minimum. Default: 30000.")
    parser.add_argument("--brightness-max2", type=int, default=UINT16_MAX, help="Second layer bead brightness maximum. Default: 65535.")
    parser.add_argument("--diameter-tolerance", type=float, default=0.35, help="Diameter tolerance. <=1 is fraction, >1 is pixels. Default: 0.35.")
    parser.add_argument("--min-dist", type=float, default=6.0, help="Minimum distance between bead centers. Default: 6.")
    parser.add_argument("--dp", type=float, default=1.2, help="OpenCV HoughCircles dp. Default: 1.2.")
    parser.add_argument("--param1", type=float, default=80.0, help="OpenCV HoughCircles upper Canny threshold. Default: 80.")
    parser.add_argument("--param2", type=float, default=10.0, help="OpenCV HoughCircles accumulator threshold. Lower finds more beads. Default: 10.")
    parser.add_argument("--blur-kernel", type=int, default=3, help="Median blur kernel before detection. Default: 3.")
    parser.add_argument("--min-roi-fraction", type=float, default=0.20, help="Minimum fraction of circle ROI pixels within brightness range. Default: 0.20.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    files = iter_tif_files(args.input_path)
    if not files:
        raise FileNotFoundError(f"No TIFF files found: {args.input_path}")
    write_csv_header(args.output_csv)
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        process_file(path, args, args.output_csv)
    print(f"Wrote measurements: {args.output_csv}")


if __name__ == "__main__":
    main()
