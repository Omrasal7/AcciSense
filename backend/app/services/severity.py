from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


@dataclass
class SeverityOutput:
    label: str
    score: int
    confidence: float
    model_used: str
    rationale: list[str]


class SeverityAgent:
    LABEL_MAP = {
        "1": ("low", 1),
        "2": ("moderate", 2),
        "3": ("high", 3),
        "4": ("critical", 4),
    }

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self._model = None
        if YOLO is not None and self.model_path.exists():
            self._model = YOLO(str(self.model_path))

    def analyze(self, image_bytes: bytes, accident_confidence: float) -> SeverityOutput:
        image = self._decode_image(image_bytes)
        if self._model is not None:
            output = self._analyze_with_yolo(image)
        else:
            output = self._analyze_with_opencv(image, accident_confidence)
        output = self._apply_fire_override(image, output, accident_confidence)
        output = self._apply_low_detail_night_cap(image, output)
        return self._apply_severity_policy(image, output)

    def _analyze_with_yolo(self, image: np.ndarray) -> SeverityOutput:
        result = self._model.predict(source=image, verbose=False)[0]
        probs = result.probs
        top_index = int(probs.top1)
        class_name = str(result.names[top_index])
        confidence = float(probs.top1conf.item())
        label, score = self.LABEL_MAP.get(class_name, ("moderate", 2))
        return SeverityOutput(
            label=label,
            score=score,
            confidence=confidence,
            model_used=f"yolov8-cls:{self.model_path.name}",
            rationale=[f"Predicted severity class: {class_name}", f"Confidence: {confidence:.2f}"],
        )

    def _analyze_with_opencv(self, image: np.ndarray, accident_confidence: float) -> SeverityOutput:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        saturation = float(np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1]) / 255.0)
        damaged_area = float(np.mean(gray < 70))
        raw_score = accident_confidence + (damaged_area * 0.9) + (saturation * 0.3) + min(laplacian_var / 700.0, 0.7)

        if raw_score < 0.9:
            label, score = "low", 1
        elif raw_score < 1.3:
            label, score = "moderate", 2
        elif raw_score < 1.8:
            label, score = "high", 3
        else:
            label, score = "critical", 4

        confidence = min(0.95, raw_score / 2.0)
        return SeverityOutput(
            label=label,
            score=score,
            confidence=confidence,
            model_used="opencv-fallback",
            rationale=[
                f"Estimated damaged area: {damaged_area:.2f}",
                f"Image chaos score: {laplacian_var:.2f}",
                f"Detector prior confidence: {accident_confidence:.2f}",
            ],
        )

    def _apply_fire_override(
        self,
        image: np.ndarray,
        output: SeverityOutput,
        accident_confidence: float,
    ) -> SeverityOutput:
        fire_signal, fire_ratio, hotspot_ratio = self._estimate_fire_signal(image)
        if fire_signal < 0.06 and fire_ratio < 0.008 and hotspot_ratio < 0.003:
            return output

        upgraded_label, upgraded_score = output.label, output.score
        upgraded_confidence = max(output.confidence, min(0.99, 0.65 + fire_signal))

        if fire_signal >= 0.18 or hotspot_ratio >= 0.008:
            upgraded_label, upgraded_score = "critical", 4
        elif (
            fire_signal >= 0.06
            or fire_ratio >= 0.008
            or hotspot_ratio >= 0.002
            or (accident_confidence >= 0.95 and (warm_ratio := self._estimate_warm_ratio(image)) >= 0.012)
        ):
            upgraded_label, upgraded_score = "high", max(output.score, 3)
        else:
            upgraded_label, upgraded_score = "moderate", max(output.score, 2)

        if upgraded_score <= output.score:
            return output

        rationale = list(output.rationale)
        rationale.append(
            f"Fire-risk override applied: fire signal {fire_signal:.2f}, flame area {fire_ratio:.3f}, hotspot area {hotspot_ratio:.3f}"
        )
        return SeverityOutput(
            label=upgraded_label,
            score=upgraded_score,
            confidence=upgraded_confidence,
            model_used=f"{output.model_used}+fire-override",
            rationale=rationale,
        )

    def _estimate_fire_signal(self, image: np.ndarray) -> tuple[float, float, float]:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        value = hsv[:, :, 2]
        saturation = hsv[:, :, 1]

        flame_mask = cv2.inRange(hsv, np.array([5, 110, 150]), np.array([45, 255, 255]))
        hotspot_mask = cv2.inRange(hsv, np.array([0, 0, 220]), np.array([180, 80, 255]))
        warm_mask = cv2.inRange(hsv, np.array([0, 70, 140]), np.array([55, 255, 255]))

        kernel = np.ones((3, 3), dtype=np.uint8)
        flame_mask = cv2.morphologyEx(flame_mask, cv2.MORPH_OPEN, kernel)
        hotspot_mask = cv2.morphologyEx(hotspot_mask, cv2.MORPH_OPEN, kernel)
        warm_mask = cv2.morphologyEx(warm_mask, cv2.MORPH_OPEN, kernel)

        flame_ratio = float(np.count_nonzero(flame_mask) / flame_mask.size)
        hotspot_ratio = float(np.count_nonzero(hotspot_mask) / hotspot_mask.size)
        warm_ratio = float(np.count_nonzero(warm_mask) / warm_mask.size)
        brightest_ratio = float(np.mean(value > 245))
        saturated_bright_ratio = float(np.mean((value > 200) & (saturation > 150)))

        contours, _ = cv2.findContours(flame_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        largest_blob = 0.0
        if contours:
            largest_blob = max(cv2.contourArea(contour) for contour in contours) / float(image.shape[0] * image.shape[1])

        fire_signal = (
            (flame_ratio * 5.0)
            + (hotspot_ratio * 4.0)
            + (warm_ratio * 2.5)
            + (brightest_ratio * 1.5)
            + (saturated_bright_ratio * 2.0)
            + (largest_blob * 6.0)
        )
        return fire_signal, flame_ratio, hotspot_ratio

    def _estimate_warm_ratio(self, image: np.ndarray) -> float:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        warm_mask = cv2.inRange(hsv, np.array([0, 70, 140]), np.array([55, 255, 255]))
        kernel = np.ones((3, 3), dtype=np.uint8)
        warm_mask = cv2.morphologyEx(warm_mask, cv2.MORPH_OPEN, kernel)
        return float(np.count_nonzero(warm_mask) / warm_mask.size)

    def _apply_low_detail_night_cap(self, image: np.ndarray, output: SeverityOutput) -> SeverityOutput:
        if output.score < 4:
            return output

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        brightness = float(np.mean(gray))
        detail = float(min(cv2.Laplacian(gray, cv2.CV_64F).var() / 700.0, 1.0))
        dark_ratio = float(np.mean(gray < 70))
        warm_ratio = self._estimate_warm_ratio(image)
        saturation = float(np.mean(hsv[:, :, 1]) / 255.0)

        low_detail_night_scene = (
            brightness < 105
            and detail < 0.32
            and dark_ratio > 0.34
            and warm_ratio < 0.01
            and saturation < 0.28
        )

        if not low_detail_night_scene:
            return output

        rationale = list(output.rationale)
        rationale.append(
            f"Low-detail night cap applied: brightness {brightness:.1f}, detail {detail:.2f}, dark ratio {dark_ratio:.2f}, warm ratio {warm_ratio:.3f}"
        )
        return SeverityOutput(
            label="moderate",
            score=2,
            confidence=min(output.confidence, 0.78),
            model_used=f"{output.model_used}+night-cap",
            rationale=rationale,
        )

    def _apply_severity_policy(self, image: np.ndarray, output: SeverityOutput) -> SeverityOutput:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        warm_ratio = self._estimate_warm_ratio(image)
        brightness = float(np.mean(gray))
        detail = float(min(cv2.Laplacian(gray, cv2.CV_64F).var() / 700.0, 1.0))
        dark_ratio = float(np.mean(gray < 70))
        edge_density = float(np.mean(cv2.Canny(gray, 50, 150) > 0))
        saturation = float(np.mean(hsv[:, :, 1]) / 255.0)

        extreme_emergency_scene = (
            warm_ratio >= 0.012
            or (detail >= 0.68 and edge_density >= 0.13 and dark_ratio >= 0.30)
            or (detail >= 0.55 and saturation >= 0.34 and edge_density >= 0.15)
        )

        rationale = list(output.rationale)

        if output.score >= 4 and not extreme_emergency_scene:
            rationale.append(
                f"Policy cap applied: critical reserved for fire/extreme destruction scenes. brightness {brightness:.1f}, detail {detail:.2f}, edge {edge_density:.2f}, warm {warm_ratio:.3f}"
            )
            return SeverityOutput(
                label="high",
                score=3,
                confidence=min(output.confidence, 0.84),
                model_used=f"{output.model_used}+policy-cap",
                rationale=rationale,
            )

        high_but_not_extreme = (
            output.score == 3
            and warm_ratio < 0.008
            and detail < 0.52
            and edge_density < 0.14
            and saturation < 0.34
        )
        if high_but_not_extreme:
            rationale.append(
                f"Policy moderation applied: strong crash label softened without fire/extreme aftermath. detail {detail:.2f}, edge {edge_density:.2f}, warm {warm_ratio:.3f}"
            )
            return SeverityOutput(
                label="moderate",
                score=2,
                confidence=min(output.confidence, 0.76),
                model_used=f"{output.model_used}+policy-moderation",
                rationale=rationale,
            )

        return output

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image.")
        return image
