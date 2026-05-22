import argparse
import shutil
from pathlib import Path

import numpy as np

try:
    from ultralytics import YOLO
except Exception as exc:
    raise SystemExit(
        "Ultralytics is required to train models. Install backend/requirements-yolo.txt first."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
CURATED_ACCIDENT_ROOT = ROOT / "datasets" / "accident_curated"
TRAINING_DATA_ROOT = ROOT / "training_data"
VALIDATION_SPLIT = 0.2
ACCIDENT_MAX_IMAGES_PER_CLASS = 1200
SEVERITY_MAX_IMAGES_PER_CLASS = 900
DEFAULT_EPOCHS = 12
DEFAULT_IMAGE_SIZE = 224
HARD_NEGATIVE_PATTERNS = [
    "*street*.jpg",
    "*road*.jpg",
    "*traffic*.jpg",
    "*camera*.jpg",
    "*cctv*.jpg",
    "*parking*.jpg",
    "*parked*.jpg",
    "*vehicle*.jpg",
    "*car*.jpg",
]


def train_accident_classifier(epochs: int, imgsz: int, max_images: int) -> None:
    dataset_dir = ROOT / "datasets" / "accident_cls"
    build_accident_dataset(dataset_dir, max_images)
    model = YOLO("yolov8n-cls.pt")
    result = model.train(data=str(dataset_dir), epochs=epochs, imgsz=imgsz, project=str(MODELS_DIR), name="accident_cls_run")
    export_best_weights(Path(result.save_dir) / "weights" / "best.pt", MODELS_DIR / "accident_cls.pt")


def train_severity_classifier(epochs: int, imgsz: int, max_images: int) -> None:
    dataset_dir = ROOT / "datasets" / "severity_cls"
    build_severity_dataset(dataset_dir, max_images)
    model = YOLO("yolov8n-cls.pt")
    result = model.train(data=str(dataset_dir), epochs=epochs, imgsz=imgsz, project=str(MODELS_DIR), name="severity_cls_run")
    export_best_weights(Path(result.save_dir) / "weights" / "best.pt", MODELS_DIR / "severity_cls.pt")


def build_accident_dataset(destination: Path, max_images: int) -> None:
    rebuild_dataset_root(destination)
    curated_train = CURATED_ACCIDENT_ROOT / "train"
    curated_val = CURATED_ACCIDENT_ROOT / "val"
    if curated_train.exists() and curated_val.exists():
        shutil.copytree(curated_train, destination / "train")
        shutil.copytree(curated_val, destination / "val")
        return

    split_copy_tree(TRAINING_DATA_ROOT / "Accident", destination, "Accident", max_images)
    split_copy_tree(TRAINING_DATA_ROOT / "NonAccident", destination, "NonAccident", max_images, prioritize_hard_negatives=True)


def build_severity_dataset(destination: Path, max_images: int) -> None:
    rebuild_dataset_root(destination)
    severity_root = TRAINING_DATA_ROOT / "Severity Score Dataset with Labels"
    for label in ["1", "2", "3"]:
        split_copy_tree(severity_root / label, destination, label, max_images)


def rebuild_dataset_root(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    cache_file = destination.with_suffix(".cache")
    if cache_file.exists():
        cache_file.unlink()


def split_copy_tree(
    source: Path,
    dataset_root: Path,
    class_name: str,
    max_images: int,
    prioritize_hard_negatives: bool = False,
) -> None:
    image_paths = list_image_paths(source)
    if not image_paths:
        return
    image_paths = sample_paths(image_paths, max_images, prioritize_hard_negatives)

    split_index = max(1, int(len(image_paths) * (1.0 - VALIDATION_SPLIT)))
    if split_index >= len(image_paths):
        split_index = len(image_paths) - 1

    train_paths = image_paths[:split_index]
    val_paths = image_paths[split_index:]
    if not val_paths:
        val_paths = image_paths[-1:]
        train_paths = image_paths[:-1]

    copy_paths(train_paths, dataset_root / "train" / class_name)
    copy_paths(val_paths, dataset_root / "val" / class_name)


def copy_paths(paths: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for file_path in paths:
        target = destination / file_path.name
        target.write_bytes(file_path.read_bytes())


def list_image_paths(source: Path) -> list[Path]:
    image_paths: list[Path] = []
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        image_paths.extend(source.glob(pattern))
    return sorted(set(image_paths))


def sample_paths(paths: list[Path], max_images: int, prioritize_hard_negatives: bool = False) -> list[Path]:
    if len(paths) <= max_images:
        return paths

    if prioritize_hard_negatives:
        preferred = collect_pattern_matches(paths, HARD_NEGATIVE_PATTERNS)
        if preferred:
            preferred = unique_in_order(preferred)
            if len(preferred) >= max_images:
                return evenly_sample(preferred, max_images)

            remaining = [path for path in paths if path not in set(preferred)]
            needed = max_images - len(preferred)
            return preferred + evenly_sample(remaining, needed)

    return evenly_sample(paths, max_images)


def collect_pattern_matches(paths: list[Path], patterns: list[str]) -> list[Path]:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend([path for path in paths if path.match(pattern)])
    return matches


def unique_in_order(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def evenly_sample(paths: list[Path], max_images: int) -> list[Path]:
    if len(paths) <= max_images:
        return paths
    indices = np.linspace(0, len(paths) - 1, max_images, dtype=int)
    return [paths[index] for index in indices]


def export_best_weights(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train compact YOLOv8 classifiers for AcciSense.")
    parser.add_argument("--mode", choices=["accident", "severity", "both"], default="accident")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--accident-max", type=int, default=ACCIDENT_MAX_IMAGES_PER_CLASS)
    parser.add_argument("--severity-max", type=int, default=SEVERITY_MAX_IMAGES_PER_CLASS)
    args = parser.parse_args()

    if args.mode in {"accident", "both"}:
        train_accident_classifier(args.epochs, args.imgsz, args.accident_max)
    if args.mode in {"severity", "both"}:
        train_severity_classifier(args.epochs, args.imgsz, args.severity_max)
