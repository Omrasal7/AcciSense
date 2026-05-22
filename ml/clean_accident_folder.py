import argparse
import csv
import shutil
from pathlib import Path

try:
    from ultralytics import YOLO
except Exception as exc:
    raise SystemExit(
        "Ultralytics is required to clean the accident folder. Install backend/requirements-yolo.txt first."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "Accident"
DEFAULT_MODEL = ROOT / "models" / "accident_cls.pt"
DEFAULT_KEEP_DIR = ROOT / "Accident_cleaned_auto"
DEFAULT_REVIEW_DIR = ROOT / "Accident_review_auto"
IMAGE_PATTERNS = ("*.jpg", "*.jpeg", "*.png", "*.webp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean the raw Accident folder by keeping only strong accident predictions."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--keep-dir", type=Path, default=DEFAULT_KEEP_DIR)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument(
        "--keep-class",
        type=str,
        default="accident",
        help="Normalized class name to keep, for example 'accident' or 'nonaccident'.",
    )
    parser.add_argument(
        "--keep-threshold",
        type=float,
        default=0.85,
        help="Minimum confidence required to keep an image in the cleaned accident set.",
    )
    parser.add_argument(
        "--reset-output",
        action="store_true",
        help="Delete previous keep/review output folders before writing fresh results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    keep_dir = args.keep_dir.resolve()
    review_dir = args.review_dir.resolve()
    model_path = args.model.resolve()
    keep_class = normalize_class_name(args.keep_class)

    if not source.exists():
        raise SystemExit(f"Source folder not found: {source}")
    if not model_path.exists():
        raise SystemExit(f"Model weights not found: {model_path}")
    if keep_class not in {"accident", "nonaccident"}:
        raise SystemExit(f"Unsupported keep class: {args.keep_class}")

    if args.reset_output:
        reset_dir(keep_dir)
        reset_dir(review_dir)

    keep_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_path))
    image_paths = list_image_paths(source)
    if not image_paths:
        raise SystemExit(f"No images found in: {source}")

    report_rows: list[dict[str, str | float]] = []
    kept_count = 0
    review_count = 0

    for index, image_path in enumerate(image_paths, start=1):
        result = model.predict(source=str(image_path), verbose=False)[0]
        probs = result.probs
        top_index = int(probs.top1)
        top_confidence = float(probs.top1conf.item())
        class_name = normalize_class_name(str(result.names[top_index]))

        keep_image = class_name == keep_class and top_confidence >= args.keep_threshold
        destination_root = keep_dir if keep_image else review_dir
        destination = destination_root / image_path.name
        shutil.copy2(image_path, destination)

        report_rows.append(
            {
                "filename": image_path.name,
                "predicted_class": class_name,
                "confidence": round(top_confidence, 6),
                "decision": "keep" if keep_image else "review",
            }
        )

        if keep_image:
            kept_count += 1
        else:
            review_count += 1

        if index % 250 == 0 or index == len(image_paths):
            print(
                f"Processed {index}/{len(image_paths)} | keep={kept_count} review={review_count}",
                flush=True,
            )

    write_report(ROOT / "datasets" / "accident_cleaning_report.csv", report_rows)
    print(f"Completed. Kept: {kept_count} | Review: {review_count}")
    print(f"Keep folder: {keep_dir}")
    print(f"Review folder: {review_dir}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def list_image_paths(source: Path) -> list[Path]:
    image_paths: list[Path] = []
    for pattern in IMAGE_PATTERNS:
        image_paths.extend(source.glob(pattern))
    return sorted(set(image_paths))


def normalize_class_name(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def write_report(path: Path, rows: list[dict[str, str | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "predicted_class", "confidence", "decision"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
