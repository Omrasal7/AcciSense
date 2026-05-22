from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np


class MediaProcessor:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

    def classify_media_type(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in self.VIDEO_EXTENSIONS:
            return "video"
        return "image"

    def extract_analysis_image(self, media_bytes: bytes, filename: str) -> bytes:
        media_type = self.classify_media_type(filename)
        if media_type == "video":
            return self._extract_video_frame(media_bytes, filename)
        return media_bytes

    def extract_analysis_candidates(self, media_bytes: bytes, filename: str) -> list[tuple[int, bytes]]:
        media_type = self.classify_media_type(filename)
        if media_type == "video":
            return self._extract_video_frames(media_bytes, filename)
        return [(0, media_bytes)]

    def add_alert_overlay(self, image_bytes: bytes, media_type: str, accident_detected: bool) -> bytes:
        if media_type != "video" or not accident_detected:
            return image_bytes

        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            return image_bytes

        height, width = image.shape[:2]
        top_left, bottom_right = self._estimate_event_region(image)

        overlay = image.copy()
        accent = (66, 184, 131)
        box_width = max(bottom_right[0] - top_left[0], 1)
        box_height = max(bottom_right[1] - top_left[1], 1)
        corner = max(min(box_width, box_height) // 6, 22)
        thickness = 3

        self._draw_corner_brackets(overlay, top_left, bottom_right, accent, corner, thickness)
        label_top = max(top_left[1] - 34, 10)
        label_right = min(top_left[0] + 164, width - 10)
        cv2.rectangle(overlay, (top_left[0], label_top), (label_right, top_left[1] - 4), (20, 28, 40), -1)
        cv2.putText(overlay, "Accident Detected", (top_left[0] + 10, top_left[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        image = cv2.addWeighted(overlay, 0.92, image, 0.08, 0)

        success, encoded = cv2.imencode(".jpg", image)
        if not success:
            return image_bytes
        return encoded.tobytes()

    def _estimate_event_region(self, image: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
        height, width = image.shape[:2]
        default_width = max(int(width * 0.36), 90)
        default_height = max(int(height * 0.36), 90)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 160)
        grad_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        gradient = cv2.magnitude(grad_x, grad_y)
        gradient = cv2.normalize(gradient, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        local_contrast = cv2.absdiff(gray, cv2.GaussianBlur(gray, (17, 17), 0))

        heat = cv2.addWeighted(gradient, 0.52, edges, 0.34, 0)
        heat = cv2.addWeighted(heat, 0.82, local_contrast, 0.38, 0)

        # Ignore static UI overlays and near-camera foreground edges that often dominate the frame.
        heat[: int(height * 0.05), :] = 0
        heat[int(height * 0.90) :, :] = 0
        heat[:, : int(width * 0.03)] = 0
        heat[:, int(width * 0.97) :] = 0

        threshold = max(int(np.percentile(heat, 85)), 42)
        _, mask = cv2.threshold(heat, threshold, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_rect: tuple[int, int, int, int] | None = None
        best_score = 0.0

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < max((width * height) * 0.0035, 2200):
                continue

            region = heat[y : y + h, x : x + w]
            if region.size == 0:
                continue

            mean_heat = float(np.mean(region) / 255.0)
            center_x = x + (w / 2)
            center_y = y + (h / 2)
            center_distance_penalty = abs((center_x / width) - 0.52) * 0.45
            lower_frame_penalty = 0.22 if center_y > height * 0.82 else 0.0
            top_banner_penalty = 0.18 if y < height * 0.10 else 0.0

            score = (
                (area / max(width * height, 1)) * 2.2
                + mean_heat * 1.8
                - center_distance_penalty
                - lower_frame_penalty
                - top_banner_penalty
            )
            if score > best_score:
                best_score = score
                best_rect = (x, y, w, h)

        if best_rect is None:
            center_x = width // 2
            center_y = height // 2
            half_w = default_width // 2
            half_h = default_height // 2
            return (
                (max(center_x - half_w, 0), max(center_y - half_h, 0)),
                (min(center_x + half_w, width - 1), min(center_y + half_h, height - 1)),
            )

        x, y, w, h = best_rect
        pad_x = max(int(w * 0.18), 18)
        pad_y = max(int(h * 0.18), 18)
        x1 = max(x - pad_x, 0)
        y1 = max(y - pad_y, 0)
        x2 = min(x + w + pad_x, width - 1)
        y2 = min(y + h + pad_y, height - 1)
        return (x1, y1), (x2, y2)

    def _extract_video_frame(self, media_bytes: bytes, filename: str) -> bytes:
        frames = self._extract_video_frames(media_bytes, filename)
        if not frames:
            raise ValueError("Unable to extract frame from uploaded video.")
        return frames[len(frames) // 2][1]

    def _extract_video_frames(self, media_bytes: bytes, filename: str) -> list[tuple[int, bytes]]:
        suffix = Path(filename).suffix or ".mp4"
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(media_bytes)
            temp_path = Path(temp_file.name)

        capture = cv2.VideoCapture(str(temp_path))
        try:
            extracted: list[tuple[int, bytes]] = []
            frame_index = 0
            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                success, encoded = cv2.imencode(".jpg", frame)
                if success:
                    extracted.append((frame_index, encoded.tobytes()))
                frame_index += 1
            return extracted
        finally:
            capture.release()
            if temp_path.exists():
                temp_path.unlink()

    def _draw_corner_brackets(
        self,
        image: np.ndarray,
        top_left: tuple[int, int],
        bottom_right: tuple[int, int],
        color: tuple[int, int, int],
        corner: int,
        thickness: int,
    ) -> None:
        x1, y1 = top_left
        x2, y2 = bottom_right

        cv2.line(image, (x1, y1), (x1 + corner, y1), color, thickness)
        cv2.line(image, (x1, y1), (x1, y1 + corner), color, thickness)

        cv2.line(image, (x2, y1), (x2 - corner, y1), color, thickness)
        cv2.line(image, (x2, y1), (x2, y1 + corner), color, thickness)

        cv2.line(image, (x1, y2), (x1 + corner, y2), color, thickness)
        cv2.line(image, (x1, y2), (x1, y2 - corner), color, thickness)

        cv2.line(image, (x2, y2), (x2 - corner, y2), color, thickness)
        cv2.line(image, (x2, y2), (x2, y2 - corner), color, thickness)

    def default_snapshot_name(self, filename: str) -> str:
        stem = Path(filename).stem or "incident"
        return f"{stem}.jpg"
