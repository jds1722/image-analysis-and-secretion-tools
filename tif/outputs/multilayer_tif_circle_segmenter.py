from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import tifffile


DEFAULT_EXPORT_LAYERS = (0, 4, 5, 7)


@dataclass(frozen=True)
class Circle:
    index: int
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class Square:
    circle_index: int
    roi_number: int | None
    center_x: float
    center_y: float
    circle_radius: float
    diameter: float
    x0: int
    y0: int
    x1: int
    y1: int
    cell_region_area: int | None = None
    cell_region_circularity: float | None = None
    matching_cell_region_count: int | None = None
    cell_search_radius: float | None = None

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def vertices(self) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
        return (
            (self.x0, self.y0),
            (self.x1, self.y0),
            (self.x1, self.y1),
            (self.x0, self.y1),
        )


def parse_layers(raw: str) -> tuple[int, ...]:
    layers = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not layers:
        raise argparse.ArgumentTypeError("At least one layer index is required.")
    if any(layer < 0 for layer in layers):
        raise argparse.ArgumentTypeError("Layer indexes must be zero or greater.")
    return layers


def open_layer(tif: tifffile.TiffFile, layer_index: int) -> np.ndarray:
    """Read a single layer from common multipage or stacked TIFF layouts."""
    if len(tif.pages) > layer_index and len(tif.pages[layer_index].shape) == 2:
        return tif.pages[layer_index].asarray()

    arr = tif.asarray()
    if arr.ndim < 3:
        raise ValueError(f"TIFF does not contain layer {layer_index}; shape={arr.shape!r}")

    axes = tif.series[0].axes
    if "Y" in axes and "X" in axes:
        y_axis = axes.index("Y")
        x_axis = axes.index("X")
        layer_axes = [axis for axis in range(arr.ndim) if axis not in (y_axis, x_axis)]
        if not layer_axes:
            raise ValueError(f"TIFF has no non-spatial layer axis; axes={axes!r}")
        layer_axis = layer_axes[0]
    else:
        layer_axis = 0

    if layer_index >= arr.shape[layer_axis]:
        raise ValueError(f"TIFF does not contain layer {layer_index}; shape={arr.shape!r}, axes={axes!r}")

    return np.take(arr, layer_index, axis=layer_axis)


def normalize_to_uint8(
    image: np.ndarray,
    low_percentile: float,
    high_percentile: float,
    invert: bool,
) -> np.ndarray:
    low, high = np.percentile(image, (low_percentile, high_percentile))
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        low = float(np.min(image))
        high = float(np.max(image))
    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)

    scaled = np.clip((image.astype(np.float32) - low) * (255.0 / (high - low)), 0, 255)
    out = scaled.astype(np.uint8)
    if invert:
        out = 255 - out
    return out


def resize_for_detection(image: np.ndarray, max_dim: int) -> tuple[np.ndarray, float]:
    if max_dim <= 0:
        return image, 1.0

    height, width = image.shape
    scale = min(1.0, max_dim / float(max(height, width)))
    if scale == 1.0:
        return image, 1.0

    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    resized = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    return resized, scale


def radius_bounds_from_diameter(
    circle_diameter: float,
    diameter_tolerance: float,
    min_radius: int,
    max_radius: int,
) -> tuple[int, int]:
    if circle_diameter <= 0:
        return min_radius, max_radius
    if diameter_tolerance < 0:
        raise ValueError("--diameter-tolerance must be zero or greater.")

    if diameter_tolerance <= 1:
        min_diameter = circle_diameter * (1.0 - diameter_tolerance)
        max_diameter = circle_diameter * (1.0 + diameter_tolerance)
    else:
        min_diameter = circle_diameter - diameter_tolerance
        max_diameter = circle_diameter + diameter_tolerance

    min_radius_from_diameter = max(1, int(math.floor(min_diameter / 2.0)))
    max_radius_from_diameter = max(1, int(math.ceil(max_diameter / 2.0)))
    if max_radius_from_diameter < min_radius_from_diameter:
        raise ValueError("Circle diameter and tolerance produce an invalid radius range.")
    return min_radius_from_diameter, max_radius_from_diameter


def detect_circles(
    layer0: np.ndarray,
    *,
    downsample_max_dim: int,
    low_percentile: float,
    high_percentile: float,
    invert: bool,
    dp: float,
    min_dist: float,
    param1: float,
    param2: float,
    min_radius: int,
    max_radius: int,
    blur_kernel: int,
) -> list[Circle]:
    detection_source, scale = resize_for_detection(layer0, downsample_max_dim)
    detection_image = normalize_to_uint8(detection_source, low_percentile, high_percentile, invert)

    if blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        detection_image = cv2.medianBlur(detection_image, blur_kernel)

    circles = cv2.HoughCircles(
        detection_image,
        cv2.HOUGH_GRADIENT,
        dp=dp,
        minDist=max(1.0, min_dist * scale),
        param1=param1,
        param2=param2,
        minRadius=max(1, int(round(min_radius * scale))),
        maxRadius=0 if max_radius <= 0 else max(1, int(round(max_radius * scale))),
    )
    if circles is None:
        return []

    detected = circles[0]
    order = np.lexsort((detected[:, 0], detected[:, 1]))
    result: list[Circle] = []
    for output_index, circle_index in enumerate(order):
        x, y, radius = detected[circle_index]
        result.append(Circle(output_index, float(x / scale), float(y / scale), float(radius / scale)))
    return result


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            self.parent[left_root] = right_root
        elif self.rank[left_root] > self.rank[right_root]:
            self.parent[right_root] = left_root
        else:
            self.parent[right_root] = left_root
            self.rank[left_root] += 1


def merge_overlapping_circles(
    circles: list[Circle],
    center_tolerance: float,
    max_iterations: int = 10,
) -> list[Circle]:
    merged = circles
    for _ in range(max_iterations):
        next_merged, merge_count = merge_overlapping_circles_once(merged, center_tolerance)
        merged = next_merged
        if merge_count == 0:
            break
    return [Circle(index, circle.x, circle.y, circle.radius) for index, circle in enumerate(merged)]


def merge_overlapping_circles_once(circles: list[Circle], center_tolerance: float) -> tuple[list[Circle], int]:
    if len(circles) < 2:
        return circles, 0
    if center_tolerance < 0:
        raise ValueError("--overlap-merge-center-tolerance must be zero or greater.")

    union_find = UnionFind(len(circles))
    ordered_indexes = sorted(range(len(circles)), key=lambda index: circles[index].x)
    max_radius = max(circle.radius for circle in circles)
    merge_count = 0

    for ordered_pos, left_index in enumerate(ordered_indexes):
        left = circles[left_index]
        for right_index in ordered_indexes[ordered_pos + 1 :]:
            right = circles[right_index]
            dx = right.x - left.x
            if dx > left.radius + max_radius:
                break

            radius_sum = left.radius + right.radius
            dy = right.y - left.y
            if abs(dy) > radius_sum:
                continue

            distance_squared = dx * dx + dy * dy
            if distance_squared > radius_sum * radius_sum:
                continue

            center_limit = center_tolerance
            if center_tolerance <= 1:
                center_limit = min(left.radius, right.radius) * center_tolerance
            if distance_squared <= center_limit * center_limit:
                union_find.union(left_index, right_index)

    groups: dict[int, list[Circle]] = {}
    for index, circle in enumerate(circles):
        groups.setdefault(union_find.find(index), []).append(circle)

    result: list[Circle] = []
    for group in groups.values():
        if len(group) > 1:
            merge_count += len(group) - 1
        result.append(
            Circle(
                index=len(result),
                x=sum(circle.x for circle in group) / len(group),
                y=sum(circle.y for circle in group) / len(group),
                radius=sum(circle.radius for circle in group) / len(group),
            )
        )

    result.sort(key=lambda circle: (circle.y, circle.x))
    return [Circle(index, circle.x, circle.y, circle.radius) for index, circle in enumerate(result)], merge_count


def write_or_show_circle_preview(
    layer0: np.ndarray,
    circles: Iterable[Circle],
    selected_squares: Iterable[Square] = (),
    *,
    output_path: Path | None,
    show_window: bool,
    preview_max_dim: int,
    low_percentile: float,
    high_percentile: float,
    invert: bool,
    show_roi_numbers: bool,
    roi_numbers: dict[int, int] | None = None,
) -> None:
    if output_path is None and not show_window:
        return

    preview_source, scale = resize_for_detection(layer0, preview_max_dim)
    preview_gray = normalize_to_uint8(preview_source, low_percentile, high_percentile, invert)
    preview = cv2.cvtColor(preview_gray, cv2.COLOR_GRAY2BGR)

    for circle in circles:
        center = (int(round(circle.x * scale)), int(round(circle.y * scale)))
        radius = max(1, int(round(circle.radius * scale)))
        cv2.circle(preview, center, radius, (0, 255, 0), 2, lineType=cv2.LINE_8)
        cv2.circle(preview, center, 3, (0, 0, 255), -1, lineType=cv2.LINE_8)
        if show_roi_numbers and roi_numbers is not None and circle.index in roi_numbers:
            label = str(roi_numbers[circle.index])
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.45, min(1.2, radius / 35.0))
            thickness = max(1, int(round(font_scale * 2.0)))
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            padding = max(3, int(round(font_scale * 5.0)))
            text_origin = (
                int(round(center[0] - text_width / 2.0)),
                int(round(center[1] + (text_height - baseline) / 2.0)),
            )
            box_top_left = (
                text_origin[0] - padding,
                text_origin[1] - text_height - padding,
            )
            box_bottom_right = (
                text_origin[0] + text_width + padding,
                text_origin[1] + baseline + padding,
            )
            cv2.rectangle(preview, box_top_left, box_bottom_right, (255, 255, 255), -1, lineType=cv2.LINE_8)
            cv2.rectangle(preview, box_top_left, box_bottom_right, (0, 0, 0), 1, lineType=cv2.LINE_8)
            cv2.putText(preview, label, text_origin, font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)

    for square in selected_squares:
        top_left = (int(round(square.x0 * scale)), int(round(square.y0 * scale)))
        bottom_right = (int(round(square.x1 * scale)), int(round(square.y1 * scale)))
        cv2.rectangle(preview, top_left, bottom_right, (0, 255, 255), 2, lineType=cv2.LINE_8)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), preview):
            raise RuntimeError(f"Failed to write preview image: {output_path}")
        print(f"Wrote circle preview: {output_path}")

    if show_window:
        window_name = "Detected circles preview - press any key to continue"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.imshow(window_name, preview)
        print("Showing circle preview window. Press any key in the preview window to continue.")
        cv2.waitKey(0)
        cv2.destroyWindow(window_name)


def circle_to_square(
    circle: Circle,
    image_shape: tuple[int, int],
    allow_edge_clipping: bool,
    segment_diagonal_padding: float,
) -> Square | None:
    if segment_diagonal_padding < 0:
        raise ValueError("--segment-diagonal-padding must be zero or greater.")

    height, width = image_shape
    half_side = circle.radius + (segment_diagonal_padding / (2.0 * math.sqrt(2.0)))
    x0 = int(math.floor(circle.x - half_side))
    y0 = int(math.floor(circle.y - half_side))
    x1 = int(math.ceil(circle.x + half_side))
    y1 = int(math.ceil(circle.y + half_side))

    if allow_edge_clipping:
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(width, x1)
        y1 = min(height, y1)
    elif x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        return None

    if x1 <= x0 or y1 <= y0:
        return None

    return Square(
        circle_index=circle.index,
        roi_number=None,
        center_x=circle.x,
        center_y=circle.y,
        circle_radius=circle.radius,
        diameter=2.0 * half_side,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
    )


def filter_squares_by_layer0_cell_region(
    layer0: np.ndarray,
    squares: Iterable[Square],
    min_cell_threshold: int,
    max_cell_threshold: int,
    min_cell_area: int,
    max_cell_area: int,
    cell_search_circle_inset: float,
    exclude_multiple_cell_regions: bool,
) -> list[Square]:
    if cell_search_circle_inset < 0:
        raise ValueError("--cell-search-circle-inset must be zero or greater.")

    selected: list[Square] = []
    for square in squares:
        cell_search_radius = square.circle_radius - cell_search_circle_inset
        if cell_search_radius <= 0:
            continue

        roi = layer0[square.y0 : square.y1, square.x0 : square.x1]
        y_coords, x_coords = np.ogrid[square.y0 : square.y1, square.x0 : square.x1]
        circle_mask = (
            (x_coords - square.center_x) * (x_coords - square.center_x)
            + (y_coords - square.center_y) * (y_coords - square.center_y)
        ) <= cell_search_radius * cell_search_radius
        cell_mask = ((roi >= min_cell_threshold) & (roi <= max_cell_threshold) & circle_mask).astype(np.uint8)
        component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(cell_mask, connectivity=8)
        if component_count <= 1:
            continue

        component_areas = stats[1:, cv2.CC_STAT_AREA]
        matching_cell_region_count = int(np.count_nonzero((component_areas >= min_cell_area) & (component_areas <= max_cell_area)))
        if exclude_multiple_cell_regions and matching_cell_region_count >= 2:
            continue

        largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        largest_area = int(stats[largest_label, cv2.CC_STAT_AREA])
        largest_component = (labels == largest_label).astype(np.uint8)
        contours, _hierarchy = cv2.findContours(largest_component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
        circularity = 0.0 if perimeter <= 0 else float((4.0 * math.pi * largest_area) / (perimeter * perimeter))

        if min_cell_area <= largest_area <= max_cell_area:
            selected.append(
                Square(
                    circle_index=square.circle_index,
                    roi_number=square.roi_number,
                    center_x=square.center_x,
                    center_y=square.center_y,
                    circle_radius=square.circle_radius,
                    diameter=square.diameter,
                    x0=square.x0,
                    y0=square.y0,
                    x1=square.x1,
                    y1=square.y1,
                    cell_region_area=largest_area,
                    cell_region_circularity=circularity,
                    matching_cell_region_count=matching_cell_region_count,
                    cell_search_radius=cell_search_radius,
                )
            )
    return selected


def write_coordinates_csv(path: Path, squares: Iterable[Square], total_roi_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "segment_index",
                "roi_number",
                "total_roi_count",
                "circle_index",
                "center_x",
                "center_y",
                "circle_radius",
                "diameter",
                "x0",
                "y0",
                "x1",
                "y1",
                "top_left",
                "top_right",
                "bottom_right",
                "bottom_left",
                "cell_region_area",
                "cell_region_circularity",
                "matching_cell_region_count",
                "cell_search_radius",
            ]
        )
        for segment_index, square in enumerate(squares):
            top_left, top_right, bottom_right, bottom_left = square.vertices()
            writer.writerow(
                [
                    segment_index,
                    square.roi_number,
                    total_roi_count,
                    square.circle_index,
                    f"{square.center_x:.3f}",
                    f"{square.center_y:.3f}",
                    f"{square.circle_radius:.3f}",
                    f"{square.diameter:.3f}",
                    square.x0,
                    square.y0,
                    square.x1,
                    square.y1,
                    f"{top_left[0]}:{top_left[1]}",
                    f"{top_right[0]}:{top_right[1]}",
                    f"{bottom_right[0]}:{bottom_right[1]}",
                    f"{bottom_left[0]}:{bottom_left[1]}",
                    square.cell_region_area,
                    "" if square.cell_region_circularity is None else f"{square.cell_region_circularity:.4f}",
                    square.matching_cell_region_count,
                    "" if square.cell_search_radius is None else f"{square.cell_search_radius:.3f}",
                ]
            )


def extract_well_prefix(input_tif_path: Path) -> str:
    match = re.match(r"^(Well[A-Za-z]+[0-9]+)", input_tif_path.stem)
    return match.group(1) if match else ""


def prefixed_name(prefix: str, name: str) -> str:
    return f"{prefix}_{name}" if prefix else name


def number_circles_top_left(circles: Iterable[Circle]) -> dict[int, int]:
    circle_list = list(circles)
    if not circle_list:
        return {}

    sorted_radii = sorted(circle.radius for circle in circle_list)
    median_radius = sorted_radii[len(sorted_radii) // 2]
    row_tolerance = max(1.0, median_radius * 0.85)

    rows: list[list[Circle]] = []
    row_centers: list[float] = []
    for circle in sorted(circle_list, key=lambda item: (item.y, item.x)):
        if rows and abs(circle.y - row_centers[-1]) <= row_tolerance:
            rows[-1].append(circle)
            row_centers[-1] = sum(item.y for item in rows[-1]) / len(rows[-1])
        else:
            rows.append([circle])
            row_centers.append(circle.y)

    result: dict[int, int] = {}
    roi_number = 1
    for _row_center, row in sorted(zip(row_centers, rows, strict=True), key=lambda item: item[0]):
        for circle in sorted(row, key=lambda item: (item.x - item.radius, item.x)):
            result[circle.index] = roi_number
            roi_number += 1
    return result


def format_roi_part(roi_number: int | None, total_roi_count: int) -> str:
    if roi_number is None:
        return f"roi_unknown_of{total_roi_count}"
    width = max(1, len(str(max(1, total_roi_count))))
    return f"roi_{roi_number:0{width}d}_of{total_roi_count}"


def prepare_segment_paths(
    output_dir: Path,
    squares: list[Square],
    overwrite: bool,
    filename_prefix: str,
    total_roi_count: int,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for segment_index, square in enumerate(squares):
        roi_part = format_roi_part(square.roi_number, total_roi_count)
        path = output_dir / (
            f"{prefixed_name(filename_prefix, roi_part)}"
            f"_segment_{segment_index:06d}"
            f"_circle_{square.circle_index:06d}"
            f"_x{square.x0}_y{square.y0}_w{square.width}_h{square.height}.tif"
        )
        if path.exists():
            if not overwrite:
                raise FileExistsError(f"{path} already exists. Use --overwrite to replace existing segments.")
            path.unlink()
        paths.append(path)
    return paths


def write_segment_pages(
    input_tif_path: Path,
    selected_squares: list[Square],
    segment_paths: list[Path],
    export_layers: tuple[int, ...],
) -> None:
    with tifffile.TiffFile(input_tif_path) as tif:
        for exported_position, layer_index in enumerate(export_layers):
            layer = open_layer(tif, layer_index)
            for square, path in zip(selected_squares, segment_paths, strict=True):
                crop = layer[square.y0 : square.y1, square.x0 : square.x1]
                tifffile.imwrite(
                    path,
                    crop,
                    append=exported_position > 0,
                    photometric="minisblack",
                    metadata={"source_layer": layer_index, "export_order": exported_position},
                )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect circles on layer 0 of a multilayer 16-bit TIFF, filter circles by the largest "
            "layer 0 threshold component inside each circle, and export selected square ROIs as multilayer TIFF files."
        )
    )
    parser.add_argument("input_tif", type=Path, help="Input multilayer TIFF path.")
    parser.add_argument(
        "--min-cell-threshold",
        "--min-dark-threshold",
        dest="min_cell_threshold",
        type=int,
        default=0,
        help="Input #1: layer 0 cell mask minimum threshold. Pixels >= this value are included. Default: 0.",
    )
    parser.add_argument(
        "--max-cell-threshold",
        "--max-dark-threshold",
        dest="max_cell_threshold",
        type=int,
        default=30000,
        help="Input #2: layer 0 cell mask maximum threshold. Pixels <= this value are included. Default: 30000.",
    )
    parser.add_argument(
        "--min-cell-area",
        "--min-dark-pixels",
        dest="min_cell_area",
        type=int,
        default=20000,
        help="Input #3: selected when the largest threshold component inside the circle is this area or greater. Default: 20000.",
    )
    parser.add_argument(
        "--max-cell-area",
        "--max-dark-pixels",
        dest="max_cell_area",
        type=int,
        default=300000,
        help="Input #4: selected when the largest threshold component inside the circle is this area or smaller. Default: 300000.",
    )
    parser.add_argument(
        "--cell-search-circle-inset",
        type=float,
        default=0.0,
        help="Shrink the circle mask inward by this many original pixels before finding the largest cell component. Default: 0.",
    )
    parser.add_argument(
        "--exclude-multiple-cell-regions",
        action="store_true",
        help="Exclude an ROI when two or more threshold components inside the circle satisfy the cell area range.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("segments"), help="Directory for exported segment TIFFs.")
    parser.add_argument("--coords-csv", type=Path, default=Path("selected_squares.csv"), help="CSV path for selected square vertices.")
    parser.add_argument("--filename-prefix", default="", help="Prefix to prepend to exported segment TIFF filenames.")
    parser.add_argument("--export-layers", type=parse_layers, default=DEFAULT_EXPORT_LAYERS, help="Comma-separated layer indexes to export.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing segment TIFF files.")
    parser.add_argument("--allow-edge-clipping", action="store_true", help="Clamp squares that extend beyond image bounds.")
    parser.add_argument(
        "--segment-diagonal-padding",
        type=float,
        default=200.0,
        help="Increase each segment square diagonal by this many original pixels while preserving the square center. Default: 200.",
    )

    parser.add_argument("--downsample-max-dim", type=int, default=4096, help="Max dimension used for circle detection.")
    parser.add_argument("--low-percentile", type=float, default=0.5, help="Lower percentile for 16-bit to 8-bit normalization.")
    parser.add_argument("--high-percentile", type=float, default=99.5, help="Upper percentile for 16-bit to 8-bit normalization.")
    parser.add_argument("--invert", action="store_true", help="Invert normalized layer 0 before circle detection.")
    parser.add_argument("--blur-kernel", type=int, default=5, help="Median blur kernel size before Hough circle detection.")

    parser.add_argument(
        "--circle-diameter",
        type=float,
        default=1515.0,
        help="Expected circle diameter in original pixels. 0 disables diameter-based radius bounds. Default: 1515.",
    )
    parser.add_argument(
        "--diameter-tolerance",
        type=float,
        default=0.10,
        help="Diameter tolerance. Values <= 1 are treated as a fraction; values > 1 are treated as pixels. Default: 0.10.",
    )
    parser.add_argument("--preview", action="store_true", help="Show detected circles in an OpenCV preview window.")
    parser.add_argument("--preview-only", action="store_true", help="Stop after showing/saving detected circle preview.")
    parser.add_argument("--preview-roi-numbers", action="store_true", help="Draw circle-based ROI numbers at circle centers in the preview image.")
    parser.add_argument(
        "--preview-output",
        default="outputs/detected_circles_preview.png",
        help="Path to save a PNG preview of detected circles. Use an empty string to skip saving.",
    )
    parser.add_argument("--preview-max-dim", type=int, default=2048, help="Max dimension for circle preview image.")
    parser.add_argument(
        "--overlap-merge-center-tolerance",
        type=float,
        default=0.25,
        help=(
            "Merge overlapping circles only when their centers are close enough. "
            "Values <= 1 are treated as a fraction of the smaller radius; values > 1 are pixels. Default: 0.25."
        ),
    )

    parser.add_argument("--dp", type=float, default=1.2, help="OpenCV HoughCircles dp parameter.")
    parser.add_argument("--min-dist", type=float, default=100.0, help="Minimum distance between circle centers in original pixels.")
    parser.add_argument("--param1", type=float, default=100.0, help="OpenCV HoughCircles upper Canny threshold.")
    parser.add_argument("--param2", type=float, default=30.0, help="OpenCV HoughCircles accumulator threshold.")
    parser.add_argument("--min-radius", type=int, default=10, help="Minimum circle radius in original pixels.")
    parser.add_argument("--max-radius", type=int, default=0, help="Maximum circle radius in original pixels. 0 means no maximum.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    input_tif_path = args.input_tif.resolve()
    filename_prefix = args.filename_prefix or extract_well_prefix(input_tif_path)
    if args.max_cell_threshold < args.min_cell_threshold:
        raise ValueError("--max-cell-threshold must be greater than or equal to --min-cell-threshold.")
    if args.max_cell_area < args.min_cell_area:
        raise ValueError("--max-cell-area must be greater than or equal to --min-cell-area.")
    if args.cell_search_circle_inset < 0:
        raise ValueError("--cell-search-circle-inset must be zero or greater.")
    min_radius, max_radius = radius_bounds_from_diameter(
        args.circle_diameter,
        args.diameter_tolerance,
        args.min_radius,
        args.max_radius,
    )
    preview_output = Path(args.preview_output) if args.preview_output else None

    with tifffile.TiffFile(input_tif_path) as tif:
        layer0 = open_layer(tif, 0)
        if layer0.ndim != 2:
            raise ValueError(f"Layer 0 must be 2D, got shape={layer0.shape!r}")

        print(f"Loaded layer 0: shape={layer0.shape}, dtype={layer0.dtype}")
        circles = detect_circles(
            layer0,
            downsample_max_dim=args.downsample_max_dim,
            low_percentile=args.low_percentile,
            high_percentile=args.high_percentile,
            invert=args.invert,
            dp=args.dp,
            min_dist=args.min_dist,
            param1=args.param1,
            param2=args.param2,
            min_radius=min_radius,
            max_radius=max_radius,
            blur_kernel=args.blur_kernel,
        )
        detected_circle_count = len(circles)
        circles = merge_overlapping_circles(circles, args.overlap_merge_center_tolerance)
        print(f"Detected circles: {detected_circle_count}")
        print(f"Circles after overlap merge: {len(circles)}")
        print(f"Circle radius bounds used: min={min_radius}, max={max_radius if max_radius > 0 else 'none'}")

        circle_roi_numbers = number_circles_top_left(circles)
        total_roi_count = len(circles)
        candidate_squares: list[Square] = []
        for circle in circles:
            square = circle_to_square(
                circle,
                layer0.shape,
                args.allow_edge_clipping,
                args.segment_diagonal_padding,
            )
            if square is not None:
                candidate_squares.append(replace(square, roi_number=circle_roi_numbers[circle.index]))
        candidate_squares.sort(key=lambda square: square.roi_number or 0)
        print(f"Circle-based ROI count: {total_roi_count}")
        print(f"Candidate squares available for segmentation: {len(candidate_squares)}")

        selected_squares = filter_squares_by_layer0_cell_region(
            layer0,
            candidate_squares,
            args.min_cell_threshold,
            args.max_cell_threshold,
            args.min_cell_area,
            args.max_cell_area,
            args.cell_search_circle_inset,
            args.exclude_multiple_cell_regions,
        )
        print(f"Selected squares after layer 0 largest cell-region filter: {len(selected_squares)}")

        write_or_show_circle_preview(
            layer0,
            circles,
            selected_squares,
            output_path=preview_output,
            show_window=args.preview,
            preview_max_dim=args.preview_max_dim,
            low_percentile=args.low_percentile,
            high_percentile=args.high_percentile,
            invert=args.invert,
            show_roi_numbers=args.preview_roi_numbers,
            roi_numbers=circle_roi_numbers,
        )
        if args.preview_only:
            print("Preview-only mode enabled. Skipping segment export.")
            return

    write_coordinates_csv(args.coords_csv, selected_squares, total_roi_count)
    print(f"Wrote coordinates CSV: {args.coords_csv}")

    if not selected_squares:
        print("No segments exported because no squares passed the filter.")
        return

    segment_paths = prepare_segment_paths(args.output_dir, selected_squares, args.overwrite, filename_prefix, total_roi_count)
    write_segment_pages(input_tif_path, selected_squares, segment_paths, args.export_layers)
    print(f"Wrote segment TIFFs: {len(segment_paths)} files in {args.output_dir}")


if __name__ == "__main__":
    main()
