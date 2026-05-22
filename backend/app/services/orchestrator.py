from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app.core.config import Settings
from app.repositories.incident_repository import IncidentRepository
from app.services.detection import DetectionAgent
from app.services.detection import DetectionOutput
from app.services.location import LocationResolverAgent
from app.services.media import MediaProcessor
from app.services.notification import NotificationAgent
from app.services.severity import SeverityAgent


class AccidentPipeline:
    def __init__(self, settings: Settings, repository: IncidentRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.detector = DetectionAgent(settings.accident_model_path, settings.enable_opencv_fallback)
        self.severity = SeverityAgent(settings.severity_model_path)
        self.location = LocationResolverAgent(settings.camera_registry_path)
        self.media = MediaProcessor()
        self.notifier = NotificationAgent(settings)

    def analyze(
        self,
        image_bytes: bytes,
        filename: str,
        latitude: float | None = None,
        longitude: float | None = None,
        source_id: str | None = None,
    ) -> dict:
        incident_id = str(uuid4())
        media_type = self.media.classify_media_type(filename)
        original_media_url = self._save_media(incident_id, filename, image_bytes)
        candidate_frames = self.media.extract_analysis_candidates(image_bytes, filename)
        analysis_image_bytes, detection = self._select_best_analysis_frame(candidate_frames)
        severity = self.severity.analyze(analysis_image_bytes, detection.confidence)
        location = self.location.resolve(
            analysis_image_bytes,
            latitude,
            longitude,
            source_id,
            filename,
        )
        if not detection.accident_detected:
            severity.label = "low"
            severity.score = 1
            severity.confidence = min(severity.confidence, 0.35)
            severity.rationale = [
                "Final incident decision: no accident detected in the analyzed video window.",
                *severity.rationale,
            ]
            location.nearest_hospitals = []
            location.nearest_police_stations = []
        analysis_image_bytes = self.media.add_alert_overlay(
            analysis_image_bytes,
            media_type,
            detection.accident_detected,
        )
        saved_image_url = self._save_media(
            f"{incident_id}_snapshot",
            self.media.default_snapshot_name(filename),
            analysis_image_bytes,
        )

        incident = {
            "id": incident_id,
            "created_at": datetime.now(timezone.utc),
            "media_type": media_type,
            "original_media_url": original_media_url,
            "image_url": saved_image_url,
            "detection": detection.__dict__,
            "severity": severity.__dict__,
            "location": location.__dict__,
            "notifications": {
                "sms_sent_to": [],
                "sms_results": [],
                "email_sent_to": [],
                "dashboard_logged": True,
                "errors": [],
            },
        }

        if detection.accident_detected:
            contacts = self.repository.list_contacts()
            incident["notifications"] = self.notifier.notify(incident, contacts)
        self.repository.create_incident(incident)
        return incident

    def _select_best_analysis_frame(self, candidate_frames: list[tuple[int, bytes]]) -> tuple[bytes, DetectionOutput]:
        analyzed_frames: list[tuple[int, bytes, DetectionOutput]] = []
        for frame_index, frame_bytes in candidate_frames:
            analyzed_frames.append((frame_index, frame_bytes, self.detector.analyze(frame_bytes)))

        if len(analyzed_frames) > 6:
            full_video_candidate = self._select_best_video_event_frame(analyzed_frames)
            if full_video_candidate is not None:
                return full_video_candidate[1], full_video_candidate[2]

        best_cluster = self._find_best_positive_cluster(analyzed_frames)
        if best_cluster is not None:
            return best_cluster[1], best_cluster[2]

        motion_event = self._find_motion_event_candidate(analyzed_frames)
        if motion_event is not None:
            return motion_event[1], motion_event[2]

        positive_frames = [item for item in analyzed_frames if item[2].accident_detected]
        if (
            len(positive_frames) == 1
            and positive_frames[0][2].confidence >= 0.985
            and self._compute_local_motion_signal(analyzed_frames, positive_frames[0][0]) >= 0.12
        ):
            return positive_frames[0][1], positive_frames[0][2]

        negative_frames = [item for item in analyzed_frames if not item[2].accident_detected]
        if negative_frames:
            best_negative = self._select_best_negative_event_frame(analyzed_frames, negative_frames)
            return best_negative[1], best_negative[2]

        frame_bytes = candidate_frames[0][1]
        return frame_bytes, self.detector.analyze(frame_bytes)

    def _select_best_video_event_frame(
        self, analyzed_frames: list[tuple[int, bytes, DetectionOutput]]
    ) -> tuple[int, bytes, DetectionOutput] | None:
        motions = self._build_motion_timeline(analyzed_frames)
        if not motions:
            return None

        global_peak_motion = max(motions)
        if global_peak_motion <= 0.0:
            return None

        window_radius = max(6, min(20, len(analyzed_frames) // 14 or 6))
        best_window: tuple[int, int] | None = None
        best_window_score = float("-inf")
        min_late_start = int(len(analyzed_frames) * 0.14)

        for center in range(len(analyzed_frames)):
            start = max(0, center - window_radius)
            end = min(len(analyzed_frames), center + window_radius + 1)
            window = analyzed_frames[start:end]
            window_motions = motions[start:end]
            if not window or not window_motions:
                continue

            confidences = [frame[2].confidence for frame in window]
            peak_motion = max(window_motions)
            if peak_motion < max(0.035, global_peak_motion * 0.30) and max(confidences) < 0.72:
                continue

            top_motion_count = min(4, len(window_motions))
            top_conf_count = min(4, len(confidences))
            mean_top_motion = float(np.mean(sorted(window_motions, reverse=True)[:top_motion_count]))
            mean_top_confidence = float(np.mean(sorted(confidences, reverse=True)[:top_conf_count]))
            average_confidence = float(np.mean(confidences))
            detected_count = sum(1 for frame in window if frame[2].accident_detected)
            support_count = sum(1 for confidence in confidences if confidence >= 0.46)
            position_ratio = center / max(1, len(analyzed_frames) - 1)

            early_penalty = 0.0
            if center < min_late_start and detected_count == 0 and max(confidences) < 0.84:
                early_penalty = 0.45

            window_score = (
                (peak_motion * 2.8)
                + (mean_top_motion * 1.6)
                + (mean_top_confidence * 1.1)
                + (average_confidence * 0.55)
                + (detected_count * 0.25)
                + (support_count * 0.06)
                + (position_ratio * 0.35)
                - early_penalty
            )

            if window_score > best_window_score:
                best_window_score = window_score
                best_window = (start, end)

        if best_window is None:
            return None

        start, end = best_window
        window = analyzed_frames[start:end]
        window_motions = motions[start:end]
        confidences = [frame[2].confidence for frame in window]
        peak_motion = max(window_motions)
        average_confidence = float(np.mean(confidences))
        max_confidence = max(confidences)
        support_count = sum(1 for confidence in confidences if confidence >= 0.46)
        detected_count = sum(1 for frame in window if frame[2].accident_detected)

        representative_index = self._select_window_representative(window, window_motions, peak_motion)
        representative_frame = window[representative_index]
        representative_motion = window_motions[representative_index]

        should_promote = (
            detected_count > 0
            or max_confidence >= 0.76
            or (
                peak_motion >= max(0.065, global_peak_motion * 0.55)
                and support_count >= 2
                and average_confidence >= 0.43
            )
        )

        if not should_promote:
            return representative_frame

        if representative_frame[2].accident_detected:
            return representative_frame

        promoted_confidence = min(
            0.88,
            max(
                representative_frame[2].confidence,
                max_confidence,
                average_confidence + min(0.12, peak_motion),
            ),
        )
        promoted = DetectionOutput(
            accident_detected=True,
            confidence=promoted_confidence,
            model_used=f"{representative_frame[2].model_used}+full-video-window",
            evidence=[
                *representative_frame[2].evidence,
                f"Full-video event window: frames {window[0][0]}-{window[-1][0]}, peak motion {peak_motion:.2f}, avg confidence {average_confidence:.2f}, max confidence {max_confidence:.2f}",
            ],
        )
        return representative_frame[0], representative_frame[1], promoted

    def _build_motion_timeline(self, analyzed_frames: list[tuple[int, bytes, DetectionOutput]]) -> list[float]:
        grayscale_frames = [self._decode_grayscale(frame_bytes) for _, frame_bytes, _ in analyzed_frames]
        motions: list[float] = []

        for index, current_frame in enumerate(grayscale_frames):
            if current_frame is None:
                motions.append(0.0)
                continue

            motion_scores: list[float] = []
            for neighbor_offset in (-1, 1):
                neighbor_index = index + neighbor_offset
                if 0 <= neighbor_index < len(grayscale_frames):
                    neighbor_frame = grayscale_frames[neighbor_index]
                    if neighbor_frame is None:
                        continue
                    difference = cv2.absdiff(current_frame, neighbor_frame)
                    motion_scores.append(float(np.mean(difference) / 255.0))

            motions.append(max(motion_scores) if motion_scores else 0.0)

        return motions

    def _select_window_representative(
        self,
        window: list[tuple[int, bytes, DetectionOutput]],
        window_motions: list[float],
        peak_motion: float,
    ) -> int:
        onset_threshold = peak_motion * 0.72
        for index, (_, _, detection) in enumerate(window):
            if window_motions[index] >= onset_threshold and detection.confidence >= 0.40:
                return index

        best_index = 0
        best_score = float("-inf")
        for index, (_, _, detection) in enumerate(window):
            frame_score = (window_motions[index] * 2.2) + detection.confidence
            if frame_score > best_score:
                best_score = frame_score
                best_index = index
        return best_index

    def _find_best_positive_cluster(
        self, analyzed_frames: list[tuple[int, bytes, DetectionOutput]]
    ) -> tuple[int, bytes, DetectionOutput] | None:
        clusters: list[list[tuple[int, bytes, DetectionOutput]]] = []
        current_cluster: list[tuple[int, bytes, DetectionOutput]] = []

        for item in analyzed_frames:
            if self._supports_accident_cluster(item[2]):
                current_cluster.append(item)
            elif current_cluster:
                clusters.append(current_cluster)
                current_cluster = []

        if current_cluster:
            clusters.append(current_cluster)

        best_cluster: list[tuple[int, bytes, DetectionOutput]] | None = None
        best_score = 0.0

        for cluster in clusters:
            confidences = [frame[2].confidence for frame in cluster]
            average_confidence = sum(confidences) / len(confidences)
            max_confidence = max(confidences)
            onset_motion = self._compute_local_motion_signal(analyzed_frames, cluster[0][0])
            peak_motion = max(self._compute_local_motion_signal(analyzed_frames, frame[0]) for frame in cluster)

            if len(cluster) < 2 and max_confidence < 0.985:
                continue
            if len(cluster) >= 2 and average_confidence < 0.78 and max_confidence < 0.88:
                continue
            if len(cluster) >= 2 and onset_motion < 0.06 and peak_motion < 0.09:
                continue

            score = (
                average_confidence
                + (len(cluster) * 0.08)
                + (max_confidence * 0.2)
                + (onset_motion * 1.2)
                + (peak_motion * 0.8)
            )
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is None:
            return None

        for index, frame in enumerate(best_cluster):
            confidence = frame[2].confidence
            motion = self._compute_local_motion_signal(analyzed_frames, frame[0])
            if confidence >= 0.82 and motion >= 0.06:
                return self._promote_temporal_detection(frame, best_cluster, analyzed_frames)
            if (
                index + 1 < len(best_cluster)
                and best_cluster[index + 1][2].confidence >= 0.88
                and self._compute_local_motion_signal(analyzed_frames, best_cluster[index + 1][0]) >= 0.08
            ):
                return self._promote_temporal_detection(frame, best_cluster, analyzed_frames)

        strongest_frame = max(
            best_cluster,
            key=lambda frame: (frame[2].confidence, self._compute_local_motion_signal(analyzed_frames, frame[0])),
        )
        if self._compute_local_motion_signal(analyzed_frames, strongest_frame[0]) >= 0.08:
            return self._promote_temporal_detection(strongest_frame, best_cluster, analyzed_frames)

        return None

    def _supports_accident_cluster(self, detection: DetectionOutput) -> bool:
        return detection.accident_detected or detection.confidence >= 0.52

    def _promote_temporal_detection(
        self,
        frame: tuple[int, bytes, DetectionOutput],
        cluster: list[tuple[int, bytes, DetectionOutput]],
        analyzed_frames: list[tuple[int, bytes, DetectionOutput]],
    ) -> tuple[int, bytes, DetectionOutput]:
        frame_index, frame_bytes, detection = frame
        if detection.accident_detected:
            return frame

        average_confidence = sum(item[2].confidence for item in cluster) / len(cluster)
        peak_motion = max(self._compute_local_motion_signal(analyzed_frames, item[0]) for item in cluster)
        frame_motion = self._compute_local_motion_signal(analyzed_frames, frame_index)

        if average_confidence >= 0.58 and peak_motion >= 0.08 and frame_motion >= 0.05:
            promoted_confidence = min(0.89, max(detection.confidence, average_confidence))
            promoted = DetectionOutput(
                accident_detected=True,
                confidence=promoted_confidence,
                model_used=f"{detection.model_used}+video-temporal",
                evidence=[
                    *detection.evidence,
                    f"Video temporal override: cluster avg {average_confidence:.2f}, peak motion {peak_motion:.2f}, frame motion {frame_motion:.2f}",
                ],
            )
            return frame_index, frame_bytes, promoted

        return frame

    def _compute_local_motion_signal(
        self, analyzed_frames: list[tuple[int, bytes, DetectionOutput]], frame_index: int
    ) -> float:
        current_position = None
        for position, item in enumerate(analyzed_frames):
            if item[0] == frame_index:
                current_position = position
                break

        if current_position is None:
            return 0.0

        current_frame = self._decode_grayscale(analyzed_frames[current_position][1])
        if current_frame is None:
            return 0.0

        motion_scores: list[float] = []
        for neighbor_offset in (-1, 1):
            neighbor_position = current_position + neighbor_offset
            if 0 <= neighbor_position < len(analyzed_frames):
                neighbor_frame = self._decode_grayscale(analyzed_frames[neighbor_position][1])
                if neighbor_frame is None:
                    continue
                difference = cv2.absdiff(current_frame, neighbor_frame)
                motion_scores.append(float(np.mean(difference) / 255.0))

        if not motion_scores:
            return 0.0
        return max(motion_scores)

    def _decode_grayscale(self, frame_bytes: bytes) -> np.ndarray | None:
        buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return None
        return cv2.GaussianBlur(frame, (5, 5), 0)

    def _find_motion_event_candidate(
        self, analyzed_frames: list[tuple[int, bytes, DetectionOutput]]
    ) -> tuple[int, bytes, DetectionOutput] | None:
        if len(analyzed_frames) < 6:
            return None

        motion_ranked = sorted(
            (
                (position, self._compute_local_motion_signal(analyzed_frames, frame[0]))
                for position, frame in enumerate(analyzed_frames)
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        best_candidate: tuple[int, bytes, DetectionOutput] | None = None
        best_score = 0.0
        min_position_bias = max(1, int(len(analyzed_frames) * 0.22))

        for position, motion in motion_ranked[:12]:
            if motion < 0.06:
                continue

            candidate_position = position
            if candidate_position < min_position_bias and len(analyzed_frames) > min_position_bias:
                candidate_position = min_position_bias

            window_start = max(candidate_position - 5, 0)
            window_end = min(candidate_position + 6, len(analyzed_frames))
            window = analyzed_frames[window_start:window_end]
            if not window:
                continue

            confidences = [frame[2].confidence for frame in window]
            average_confidence = sum(confidences) / len(confidences)
            max_confidence = max(confidences)
            average_motion = sum(self._compute_local_motion_signal(analyzed_frames, frame[0]) for frame in window) / len(window)

            if average_confidence < 0.40 and max_confidence < 0.52:
                continue
            if average_motion < 0.055:
                continue

            candidate_score = (
                (average_confidence * 0.9)
                + (max_confidence * 0.8)
                + (average_motion * 1.4)
                + ((candidate_position / max(len(analyzed_frames), 1)) * 0.35)
            )
            if candidate_score <= best_score:
                continue

            onset_frame = None
            for frame in window:
                frame_confidence = frame[2].confidence
                frame_motion = self._compute_local_motion_signal(analyzed_frames, frame[0])
                if frame_confidence >= 0.44 and frame_motion >= 0.055:
                    onset_frame = frame
                    break

            if onset_frame is None:
                onset_frame = max(
                    window,
                    key=lambda frame: (
                        self._compute_local_motion_signal(analyzed_frames, frame[0]),
                        frame[2].confidence,
                    ),
                )

            promoted_detection = DetectionOutput(
                accident_detected=True,
                confidence=min(0.87, max(onset_frame[2].confidence, average_confidence)),
                model_used=f"{onset_frame[2].model_used}+motion-window",
                evidence=[
                    *onset_frame[2].evidence,
                    f"Motion-window override: avg confidence {average_confidence:.2f}, max confidence {max_confidence:.2f}, avg motion {average_motion:.2f}",
                ],
            )
            best_candidate = (onset_frame[0], onset_frame[1], promoted_detection)
            best_score = candidate_score

        return best_candidate

    def _select_best_negative_event_frame(
        self,
        analyzed_frames: list[tuple[int, bytes, DetectionOutput]],
        negative_frames: list[tuple[int, bytes, DetectionOutput]],
    ) -> tuple[int, bytes, DetectionOutput]:
        ranked = sorted(
            negative_frames,
            key=lambda item: (
                self._compute_local_motion_signal(analyzed_frames, item[0]),
                item[2].confidence,
                item[0],
            ),
            reverse=True,
        )

        for frame in ranked:
            motion = self._compute_local_motion_signal(analyzed_frames, frame[0])
            if motion >= 0.05:
                return frame

        return min(negative_frames, key=lambda item: (item[2].confidence, abs(item[0])))

    def _save_media(self, incident_id: str, filename: str, image_bytes: bytes) -> str:
        suffix = Path(filename).suffix or ".jpg"
        image_name = f"{incident_id}{suffix}"
        destination = self.settings.upload_dir / image_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(image_bytes)
        return f"/uploads/{image_name}"
