from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


@dataclass
class DetectionOutput:
    accident_detected: bool
    confidence: float
    model_used: str
    evidence: list[str]


class DetectionAgent:
    def __init__(self, model_path: Path, enable_fallback: bool = True) -> None:
        self.model_path = Path(model_path)
        self.enable_fallback = enable_fallback
        self._model = None
        self._fallback_centroids: dict[str, np.ndarray] | None = None
        self._fallback_sample_count = 300
        if YOLO is not None and self.model_path.exists():
            self._model = YOLO(str(self.model_path))

    def analyze(self, image_bytes: bytes) -> DetectionOutput:
        if self._model is not None:
            return self._apply_static_scene_veto(image_bytes, self._analyze_with_yolo(image_bytes))
        if self.enable_fallback:
            return self._apply_static_scene_veto(image_bytes, self._analyze_with_dataset_fallback(image_bytes))
        if YOLO is None:
            raise RuntimeError(
                "YOLO accident model is unavailable because the 'ultralytics' package is not installed "
                "in the active backend environment. Run: pip install -r requirements-yolo.txt"
            )
        if not self.model_path.exists():
            raise RuntimeError(
                f"YOLO accident model weights are missing. Expected weights at: {self.model_path}. "
                f"Train or place accident_cls.pt there."
            )
        raise RuntimeError(
            f"YOLO accident model is required but could not be initialized from: {self.model_path}"
        )

    def _apply_static_scene_veto(self, image_bytes: bytes, output: DetectionOutput) -> DetectionOutput:
        if not output.accident_detected:
            return output

        image = self._decode_image(image_bytes)
        metrics = self._estimate_scene_metrics(image)
        incident_signal = (
            (metrics["edge_density"] * 2.8)
            + (metrics["gray_std"] * 1.6)
            + (metrics["dark_ratio"] * 1.2)
            + (metrics["saturation_mean"] * 0.4)
            + (metrics["warm_ratio"] * 3.0)
            + (metrics["laplacian_var"] * 0.35)
        )

        static_scene = (
            metrics["edge_density"] < 0.085
            and metrics["gray_std"] < 0.22
            and metrics["dark_ratio"] < 0.24
            and metrics["warm_ratio"] < 0.004
            and metrics["saturation_mean"] < 0.30
            and metrics["laplacian_var"] < 0.45
        )

        if static_scene and incident_signal < 0.92 and output.confidence < 0.995:
            evidence = list(output.evidence)
            evidence.append(
                "Static-scene veto applied: calm roadway visual profile with insufficient crash evidence."
            )
            evidence.append(
                f"Scene metrics edge={metrics['edge_density']:.3f}, std={metrics['gray_std']:.3f}, dark={metrics['dark_ratio']:.3f}, warm={metrics['warm_ratio']:.3f}"
            )
            return DetectionOutput(
                accident_detected=False,
                confidence=min(output.confidence, 0.58),
                model_used=f"{output.model_used}+static-scene-veto",
                evidence=evidence,
            )

        if (
            output.accident_detected
            and output.confidence < 0.82
            and incident_signal < 1.02
            and metrics["warm_ratio"] < 0.006
            and metrics["edge_density"] < 0.11
            and metrics["laplacian_var"] < 0.55
        ):
            evidence = list(output.evidence)
            evidence.append(
                "Medium-confidence roadway veto applied: confidence and scene evidence are too weak for a confirmed accident."
            )
            evidence.append(
                f"Incident signal={incident_signal:.3f}, edge={metrics['edge_density']:.3f}, warm={metrics['warm_ratio']:.3f}, laplacian={metrics['laplacian_var']:.3f}"
            )
            return DetectionOutput(
                accident_detected=False,
                confidence=min(output.confidence, 0.60),
                model_used=f"{output.model_used}+roadway-veto",
                evidence=evidence,
            )

        return output

    def _analyze_with_yolo(self, image_bytes: bytes) -> DetectionOutput:
        image = self._decode_image(image_bytes)
        result = self._model.predict(source=image, verbose=False)[0]
        probs = result.probs
        top_index = int(probs.top1)
        class_name = str(result.names[top_index]).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        confidence = float(probs.top1conf.item())
        accident_aliases = {"accident", "crash", "collision"}
        non_accident_aliases = {"nonaccident", "noaccident", "normal", "safe"}
        if class_name in non_accident_aliases:
            detected = False
        elif class_name in accident_aliases:
            detected = confidence >= 0.60
        else:
            detected = ("non" not in class_name) and ("accident" in class_name) and confidence >= 0.60
        return DetectionOutput(
            accident_detected=detected,
            confidence=confidence,
            model_used=f"yolov8-cls:{self.model_path.name}",
            evidence=[f"Top class: {class_name}", f"Confidence: {confidence:.2f}", f"Threshold: 0.60"],
        )

    def _analyze_with_dataset_fallback(self, image_bytes: bytes) -> DetectionOutput:
        image = self._decode_image(image_bytes)
        centroids = self._load_fallback_centroids()
        if centroids is None:
            return self._analyze_with_opencv_heuristic(image)

        feature = self._extract_feature_vector(image)
        accident_distance = self._cosine_distance(feature, centroids["accident"])
        non_accident_distance = self._cosine_distance(feature, centroids["non_accident"])
        detected = accident_distance <= non_accident_distance
        distance_gap = abs(non_accident_distance - accident_distance)
        confidence = max(0.5, min(0.99, 0.5 + (distance_gap * 2.0)))

        return DetectionOutput(
            accident_detected=detected,
            confidence=confidence,
            model_used="dataset-centroid-fallback",
            evidence=[
                f"Accident distance: {accident_distance:.3f}",
                f"Non-accident distance: {non_accident_distance:.3f}",
                f"Decision margin: {distance_gap:.3f}",
            ],
        )

    def _analyze_with_opencv_heuristic(self, image: np.ndarray) -> DetectionOutput:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        edge_density = float(np.mean(edges > 0))
        dark_ratio = float(np.mean(gray < 55))
        red_ratio = float(np.mean(image[:, :, 2] > 160))

        score = min(0.98, (edge_density * 2.5) + (dark_ratio * 0.7) + (red_ratio * 0.4))
        detected = score >= 0.45

        return DetectionOutput(
            accident_detected=detected,
            confidence=score,
            model_used="opencv-fallback",
            evidence=[
                f"Edge density: {edge_density:.2f}",
                f"Dark region ratio: {dark_ratio:.2f}",
                f"High red ratio: {red_ratio:.2f}",
            ],
        )

    def _load_fallback_centroids(self) -> dict[str, np.ndarray] | None:
        if self._fallback_centroids is not None:
            return self._fallback_centroids

        project_root = Path(__file__).resolve().parents[3]
        training_data_root = project_root / "training_data"
        accident_dir = training_data_root / "Accident"
        non_accident_dir = training_data_root / "NonAccident"
        if not accident_dir.exists() or not non_accident_dir.exists():
            return None

        accident_features = self._build_feature_matrix(accident_dir)
        non_accident_features = self._build_feature_matrix(non_accident_dir)
        if accident_features.size == 0 or non_accident_features.size == 0:
            return None

        self._fallback_centroids = {
            "accident": accident_features.mean(axis=0),
            "non_accident": non_accident_features.mean(axis=0),
        }
        return self._fallback_centroids

    def _build_feature_matrix(self, directory: Path) -> np.ndarray:
        image_paths: list[Path] = []
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            image_paths.extend(directory.rglob(pattern))
        image_paths = sorted(set(image_paths))
        if not image_paths:
            return np.array([])

        if len(image_paths) > self._fallback_sample_count:
            indices = np.linspace(0, len(image_paths) - 1, self._fallback_sample_count, dtype=int)
            selected_paths = [image_paths[index] for index in indices]
        else:
            selected_paths = image_paths

        vectors: list[np.ndarray] = []
        for path in selected_paths:
            image = cv2.imread(str(path))
            if image is None:
                continue
            vectors.append(self._extract_feature_vector(image))

        if not vectors:
            return np.array([])
        return np.vstack(vectors)

    def _extract_feature_vector(self, image: np.ndarray) -> np.ndarray:
        resized_gray = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (32, 32)).astype(np.float32) / 255.0
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [16], [0, 256]).flatten()
        hist_v = cv2.calcHist([hsv], [2], None, [16], [0, 256]).flatten()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        texture = np.array(
            [
                float(np.mean(edges > 0)),
                float(np.mean(gray) / 255.0),
                float(np.std(gray) / 255.0),
                float(np.mean(hsv[:, :, 1]) / 255.0),
            ],
            dtype=np.float32,
        )
        feature = np.concatenate(
            [
                resized_gray.flatten(),
                self._normalize_hist(hist_h),
                self._normalize_hist(hist_s),
                self._normalize_hist(hist_v),
                texture,
            ]
        ).astype(np.float32)
        norm = np.linalg.norm(feature)
        if norm == 0:
            return feature
        return feature / norm

    def _normalize_hist(self, histogram: np.ndarray) -> np.ndarray:
        histogram = histogram.astype(np.float32)
        total = float(histogram.sum())
        if total == 0:
            return histogram
        return histogram / total

    def _estimate_scene_metrics(self, image: np.ndarray) -> dict[str, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        warm_mask = cv2.inRange(hsv, np.array([0, 70, 140]), np.array([55, 255, 255]))
        kernel = np.ones((3, 3), dtype=np.uint8)
        warm_mask = cv2.morphologyEx(warm_mask, cv2.MORPH_OPEN, kernel)

        return {
            "edge_density": float(np.mean(edges > 0)),
            "gray_std": float(np.std(gray) / 255.0),
            "dark_ratio": float(np.mean(gray < 55)),
            "saturation_mean": float(np.mean(hsv[:, :, 1]) / 255.0),
            "warm_ratio": float(np.count_nonzero(warm_mask) / warm_mask.size),
            "laplacian_var": float(min(cv2.Laplacian(blur, cv2.CV_64F).var() / 700.0, 1.0)),
        }

    def _cosine_distance(self, left: np.ndarray, right: np.ndarray) -> float:
        return float(1.0 - np.dot(left, right))

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image.")
        return image
