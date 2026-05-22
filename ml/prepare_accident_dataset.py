import argparse
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TRAINING_DATA_ROOT = ROOT / "training_data"
RAW_ACCIDENT_DIR = TRAINING_DATA_ROOT / "Accident"
RAW_NON_ACCIDENT_DIR = TRAINING_DATA_ROOT / "NonAccident"
CURATED_ROOT = ROOT / "datasets" / "accident_curated"
VALIDATION_SPLIT = 0.2
DEFAULT_MAX_PER_CLASS = 1400
MIN_DIMENSION = 96
MIN_LAPLACIAN = 18.0
MAX_BRIGHTNESS = 248.0
MIN_BRIGHTNESS = 12.0
PHASH_SIZE = 8
HARD_NEGATIVE_PATTERNS = [
    "street",
    "road",
    "traffic",
    "camera",
    "cctv",
    "parking",
    "parked",
    "vehicle",
    "car",
    "crossing",
    "junction",
]


@dataclass
class ImageMetrics:
    path: Path
    width: int
    height: int
    brightness: float
    blur: float
    edge_density: float
    saturation: float
    phash: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a cleaner accident/non-accident dataset.")
    parser.add_argument("--max-per-class", type=int, default=DEFAULT_MAX_PER_CLASS)
    parser.add_argument("--val-split", type=float, default=VALIDATION_SPLIT)
    parser.add_argument("--output", type=Path, default=CURATED_ROOT)
    args = parser.parse_args()

    output_root = args.output
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    report_rows: list[dict[str, str | float | int]] = []

    accident_images = curate_class(
        RAW_ACCIDENT_DIR,
        class_name="Accident",
        max_per_class=args.max_per_class,
        prioritize_hard_negatives=False,
        report_rows=report_rows,
    )
    non_accident_images = curate_class(
        RAW_NON_ACCIDENT_DIR,
        class_name="NonAccident",
        max_per_class=args.max_per_class,
        prioritize_hard_negatives=True,
        report_rows=report_rows,
    )

    write_split(accident_images, output_root, "Accident", args.val_split)
    write_split(non_accident_images, output_root, "NonAccident", args.val_split)
    write_report(output_root / "curation_report.csv", report_rows)

    print(f"Curated dataset saved to: {output_root}")
    print(f"Accident kept: {len(accident_images)}")
    print(f"NonAccident kept: {len(non_accident_images)}")
    print(f"Report: {output_root / 'curation_report.csv'}")


def curate_class(
    source_dir: Path,
    class_name: str,
    max_per_class: int,
    prioritize_hard_negatives: bool,
    report_rows: list[dict[str, str | float | int]],
) -> list[ImageMetrics]:
    image_paths = list_image_paths(source_dir)
    kept: list[ImageMetrics] = []
    seen_hashes: set[str] = set()

    for path in image_paths:
        metrics = inspect_image(path)
        if metrics is None:
            report_rows.append(make_report_row(path, class_name, "skipped", "unreadable"))
            continue

        skip_reason = quality_skip_reason(metrics)
        if skip_reason:
            report_rows.append(make_report_row(path, class_name, "skipped", skip_reason, metrics))
            continue

        if metrics.phash in seen_hashes:
            report_rows.append(make_report_row(path, class_name, "skipped", "duplicate", metrics))
            continue

        seen_hashes.add(metrics.phash)
        kept.append(metrics)
        report_rows.append(make_report_row(path, class_name, "kept", "ok", metrics))

    selected = select_balanced_subset(kept, max_per_class, prioritize_hard_negatives)
    selected_paths = {item.path for item in selected}
    for item in kept:
        if item.path not in selected_paths:
            report_rows.append(make_report_row(item.path, class_name, "skipped", "downsampled", item))

    return selected


def list_image_paths(source: Path) -> list[Path]:
    image_paths: list[Path] = []
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        image_paths.extend(source.rglob(pattern))
    return sorted(set(image_paths))


def inspect_image(path: Path) -> ImageMetrics | None:
    image = cv2.imread(str(path))
    if image is None:
        return None

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.mean(edges > 0))
    saturation = float(np.mean(hsv[:, :, 1]) / 255.0)

    return ImageMetrics(
        path=path,
        width=width,
        height=height,
        brightness=brightness,
        blur=blur,
        edge_density=edge_density,
        saturation=saturation,
        phash=compute_phash(gray),
    )


def quality_skip_reason(metrics: ImageMetrics) -> str | None:
    if metrics.width < MIN_DIMENSION or metrics.height < MIN_DIMENSION:
        return "too_small"
    if metrics.blur < MIN_LAPLACIAN:
        return "too_blurry"
    if metrics.brightness <= MIN_BRIGHTNESS:
        return "too_dark"
    if metrics.brightness >= MAX_BRIGHTNESS:
        return "too_bright"
    return None


def compute_phash(gray: np.ndarray) -> str:
    resized = cv2.resize(gray, (32, 32)).astype(np.float32)
    dct = cv2.dct(resized)
    low_freq = dct[:PHASH_SIZE, :PHASH_SIZE]
    median_value = np.median(low_freq[1:, 1:])
    bits = (low_freq > median_value).astype(np.uint8).flatten()
    return "".join(str(int(bit)) for bit in bits)


def select_balanced_subset(
    items: list[ImageMetrics],
    max_per_class: int,
    prioritize_hard_negatives: bool,
) -> list[ImageMetrics]:
    if len(items) <= max_per_class:
        return items

    if not prioritize_hard_negatives:
        return evenly_sample(items, max_per_class)

    preferred = [item for item in items if any(token in item.path.name.lower() for token in HARD_NEGATIVE_PATTERNS)]
    remainder = [item for item in items if item not in preferred]

    if len(preferred) >= max_per_class:
        return evenly_sample(preferred, max_per_class)

    chosen = list(preferred)
    needed = max_per_class - len(chosen)
    chosen.extend(evenly_sample(remainder, needed))
    return chosen


def evenly_sample(items: list[ImageMetrics], count: int) -> list[ImageMetrics]:
    if len(items) <= count:
        return items
    indices = np.linspace(0, len(items) - 1, count, dtype=int)
    return [items[index] for index in indices]


def write_split(items: list[ImageMetrics], output_root: Path, class_name: str, val_split: float) -> None:
    split_index = max(1, int(len(items) * (1.0 - val_split)))
    if split_index >= len(items):
        split_index = len(items) - 1

    train_items = items[:split_index]
    val_items = items[split_index:]
    if not val_items:
        val_items = items[-1:]
        train_items = items[:-1]

    copy_items(train_items, output_root / "train" / class_name)
    copy_items(val_items, output_root / "val" / class_name)


def copy_items(items: list[ImageMetrics], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in items:
        shutil.copy2(item.path, destination / item.path.name)


def make_report_row(
    path: Path,
    class_name: str,
    status: str,
    reason: str,
    metrics: ImageMetrics | None = None,
) -> dict[str, str | float | int]:
    row: dict[str, str | float | int] = {
        "class": class_name,
        "filename": path.name,
        "status": status,
        "reason": reason,
    }
    if metrics is not None:
        row.update(
            {
                "width": metrics.width,
                "height": metrics.height,
                "brightness": round(metrics.brightness, 2),
                "blur": round(metrics.blur, 2),
                "edge_density": round(metrics.edge_density, 4),
                "saturation": round(metrics.saturation, 4),
            }
        )
    return row


def write_report(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
