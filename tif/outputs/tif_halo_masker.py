from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import tifffile


def read_stack(path: Path) -> np.ndarray:
    with tifffile.TiffFile(path) as tif:
        pages = [page.asarray() for page in tif.pages if len(page.shape) == 2]
    if not pages:
        arr = tifffile.imread(path)
        if arr.ndim == 2:
            return arr[np.newaxis, ...]
        if arr.ndim == 3:
            return arr
        raise ValueError(f"Unsupported TIFF shape for {path}: {arr.shape!r}")
    return np.stack(pages, axis=0)


def write_stack(path: Path, stack: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path, stack, photometric="minisblack")


def normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    low, high = np.percentile(image, (0.5, 99.7))
    if high <= low:
        low = float(np.min(image))
        high = float(np.max(image))
    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)
    scaled = np.clip((image.astype(np.float32) - low) * (255.0 / (high - low)), 0, 255)
    return scaled.astype(np.uint8)


def remove_small_components(mask: np.ndarray, min_size: int) -> np.ndarray:
    if min_size <= 1:
        return mask.astype(bool)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(mask.shape, dtype=bool)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= min_size:
            keep[labels == label] = True
    return keep


def disk_kernel(radius: int) -> np.ndarray:
    if radius <= 0:
        return np.ones((1, 1), dtype=np.uint8)
    size = radius * 2 + 1
    kernel = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(kernel, (radius, radius), radius, 1, thickness=-1)
    return kernel


def fill_holes(mask: np.ndarray) -> np.ndarray:
    mask_u8 = mask.astype(np.uint8)
    padded = np.pad(mask_u8, 1, mode="constant", constant_values=0)
    flood = padded.copy()
    flood_mask = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 1)
    holes = flood == 0
    filled = padded.astype(bool) | holes
    return filled[1:-1, 1:-1]


def watershed_seed_labels(
    layer: np.ndarray,
    seed: np.ndarray,
    distance_ratio: float,
    min_marker_size: int,
) -> np.ndarray:
    seed_u8 = seed.astype(np.uint8)
    distance = cv2.distanceTransform(seed_u8, cv2.DIST_L2, 5)
    if distance.max() <= 0:
        return np.zeros(seed.shape, dtype=np.int32)

    sure_fg = distance >= (distance.max() * distance_ratio)
    sure_fg = remove_small_components(sure_fg, min_marker_size)
    marker_count, markers = cv2.connectedComponents(sure_fg.astype(np.uint8), connectivity=8)
    if marker_count <= 1:
        _, markers = cv2.connectedComponents(seed_u8, connectivity=8)
        return markers.astype(np.int32)

    markers = markers.astype(np.int32) + 1
    dilated_seed = cv2.dilate(seed_u8, disk_kernel(3), iterations=1).astype(bool)
    unknown = dilated_seed & ~sure_fg
    markers[unknown] = 0

    gradient_image = 255 - normalize_to_uint8(layer)
    watershed_input = cv2.cvtColor(gradient_image, cv2.COLOR_GRAY2BGR)
    cv2.watershed(watershed_input, markers)
    labels = markers.copy()
    labels[labels <= 1] = 0
    labels -= 1
    labels[labels < 0] = 0
    return labels


def make_halo_mask(
    layer: np.ndarray,
    *,
    seed_threshold: int,
    min_seed_size: int,
    use_watershed: bool,
    watershed_distance_ratio: float,
    min_marker_size: int,
    gaussian_sigma: float,
    halo_threshold_ratio: float,
    max_halo_radius: float,
    core_dilation_radius: int,
    closing_radius: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if seed_threshold < 0:
        raise ValueError("--seed-threshold must be zero or greater.")
    if not 0 < watershed_distance_ratio <= 1:
        raise ValueError("--watershed-distance-ratio must be > 0 and <= 1.")
    if not 0 <= halo_threshold_ratio <= 1:
        raise ValueError("--halo-threshold-ratio must be between 0 and 1.")

    seed = layer >= seed_threshold
    seed = remove_small_components(seed, min_seed_size)
    labels = watershed_seed_labels(layer, seed, watershed_distance_ratio, min_marker_size) if use_watershed else np.zeros(seed.shape, dtype=np.int32)

    seed_u8 = seed.astype(np.uint8)
    distance_to_seed = cv2.distanceTransform(1 - seed_u8, cv2.DIST_L2, 5)

    halo_from_distance = distance_to_seed <= max_halo_radius
    core_mask = cv2.dilate(seed_u8, disk_kernel(core_dilation_radius), iterations=1).astype(bool)

    if gaussian_sigma > 0 and seed.any():
        blur = cv2.GaussianBlur(seed.astype(np.float32), (0, 0), sigmaX=gaussian_sigma, sigmaY=gaussian_sigma)
        blur_threshold = blur.max() * halo_threshold_ratio
        halo_from_blur = blur >= blur_threshold
    else:
        halo_from_blur = np.zeros(seed.shape, dtype=bool)

    mask = core_mask | (halo_from_distance & halo_from_blur)
    if closing_radius > 0:
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, disk_kernel(closing_radius)).astype(bool)
    mask = fill_holes(mask)
    return mask, seed, labels


def preview_overlay(layer: np.ndarray, mask: np.ndarray, seed: np.ndarray, output_path: Path) -> None:
    gray = normalize_to_uint8(layer)
    preview = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    overlay = preview.copy()
    overlay[mask] = (0, 0, 255)
    overlay[seed] = (0, 255, 255)
    preview = cv2.addWeighted(overlay, 0.35, preview, 0.65, 0)

    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(preview, contours, -1, (0, 0, 255), 2, lineType=cv2.LINE_8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), preview):
        raise RuntimeError(f"Failed to write preview: {output_path}")


def apply_mask_to_stack(stack: np.ndarray, mask: np.ndarray, mode: str) -> np.ndarray:
    mask_layer = (mask.astype(np.uint16) * np.iinfo(np.uint16).max).astype(np.uint16)
    if stack.dtype != np.uint16:
        mask_layer = mask_layer.astype(stack.dtype, copy=False)

    if mode == "add-mask-layer":
        return np.concatenate([stack, mask_layer[np.newaxis, ...]], axis=0)

    masked = stack.copy()
    masked[:, mask] = 0
    if mode == "masked-zero":
        return masked
    if mode == "both":
        return np.concatenate([masked, mask_layer[np.newaxis, ...]], axis=0)
    raise ValueError(f"Unsupported output mode: {mode}")


def iter_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted([*input_path.glob("*.tif"), *input_path.glob("*.tiff")])
    raise FileNotFoundError(input_path)


def process_file(path: Path, args: argparse.Namespace) -> Path:
    stack = read_stack(path)
    if args.layer_index < 0 or args.layer_index >= stack.shape[0]:
        raise ValueError(f"{path.name}: layer index {args.layer_index} is outside stack with {stack.shape[0]} layers.")

    layer = stack[args.layer_index]
    mask, seed, _labels = make_halo_mask(
        layer,
        seed_threshold=args.seed_threshold,
        min_seed_size=args.min_seed_size,
        use_watershed=not args.disable_watershed,
        watershed_distance_ratio=args.watershed_distance_ratio,
        min_marker_size=args.min_marker_size,
        gaussian_sigma=args.gaussian_sigma,
        halo_threshold_ratio=args.halo_threshold_ratio,
        max_halo_radius=args.max_halo_radius,
        core_dilation_radius=args.core_dilation_radius,
        closing_radius=args.closing_radius,
    )

    if args.preview_dir:
        preview_overlay(layer, mask, seed, args.preview_dir / f"{path.stem}_halo_preview.png")

    if args.preview_only:
        print(f"{path.name}: seed_px={int(seed.sum())}, mask_px={int(mask.sum())}, preview-only")
        return args.preview_dir / f"{path.stem}_halo_preview.png" if args.preview_dir else path

    output_path = args.output_dir / f"{path.stem}_halo_masked.tif"
    result = apply_mask_to_stack(stack, mask, args.output_mode)
    write_stack(output_path, result)

    print(f"{path.name}: seed_px={int(seed.sum())}, mask_px={int(mask.sum())}, output={output_path}")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mask conservative bright-bead halo/background regions in multilayer segment TIFFs.")
    parser.add_argument("input_path", type=Path, help="Input segment TIFF file or directory containing segment TIFFs.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for processed TIFFs.")
    parser.add_argument("--preview-dir", type=Path, default=None, help="Optional directory for preview PNG overlays.")
    parser.add_argument("--preview-only", action="store_true", help="Create preview overlays without writing processed TIFF files.")
    parser.add_argument("--layer-index", type=int, default=2, help="Layer containing bright fluorescent objects. Default: 2.")
    parser.add_argument("--seed-threshold", type=int, default=30000, help="Direct threshold for bright object seeds. Default: 30000.")
    parser.add_argument("--min-seed-size", type=int, default=5, help="Remove seed components smaller than this many pixels. Default: 5.")
    parser.add_argument("--disable-watershed", action="store_true", help="Disable watershed-based seed separation.")
    parser.add_argument("--watershed-distance-ratio", type=float, default=0.35, help="Distance-transform ratio for watershed markers. Default: 0.35.")
    parser.add_argument("--min-marker-size", type=int, default=3, help="Remove watershed markers smaller than this many pixels. Default: 3.")
    parser.add_argument("--gaussian-sigma", type=float, default=35.0, help="Gaussian sigma for broad halo field. Default: 35.")
    parser.add_argument("--halo-threshold-ratio", type=float, default=0.02, help="Threshold fraction of blurred seed max. Lower is more conservative. Default: 0.02.")
    parser.add_argument("--max-halo-radius", type=float, default=160.0, help="Maximum halo radius from any seed pixel. Default: 160.")
    parser.add_argument("--core-dilation-radius", type=int, default=20, help="Always mask this radius around seeds. Default: 20.")
    parser.add_argument("--closing-radius", type=int, default=7, help="Morphological closing radius for the final mask. Default: 7.")
    parser.add_argument(
        "--output-mode",
        choices=("add-mask-layer", "masked-zero", "both"),
        default="masked-zero",
        help="masked-zero zeros mask pixels in every original layer; add-mask-layer preserves layers and appends mask; both does both. Default: masked-zero.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)

    files = iter_input_files(args.input_path)
    if not files:
        raise FileNotFoundError(f"No TIFF files found in {args.input_path}")
    for path in files:
        process_file(path, args)


if __name__ == "__main__":
    main()
