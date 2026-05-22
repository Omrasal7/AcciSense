import csv
from pathlib import Path


class CameraRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = Path(registry_path)

    def lookup(self, source_id: str | None) -> dict | None:
        if not source_id or not self.registry_path.exists():
            return None

        normalized = source_id.strip().lower()
        with self.registry_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("source_id", "").strip().lower() == normalized:
                    return self._parse_row(row)
        return None

    def list_sources(self) -> list[dict]:
        if not self.registry_path.exists():
            return []

        results: list[dict] = []
        with self.registry_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                parsed = self._parse_row(row)
                if parsed is not None:
                    results.append(parsed)
        return results

    def lookup_from_filename(self, filename: str | None) -> dict | None:
        if not filename or not self.registry_path.exists():
            return None

        normalized_filename = filename.strip().lower().replace(" ", "")
        stem = Path(filename).stem.strip().lower().replace(" ", "")
        with self.registry_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                source_id = row.get("source_id", "").strip().lower().replace(" ", "")
                source_name = row.get("source_name", "").strip().lower().replace(" ", "")
                if source_id and (source_id in normalized_filename or source_id == stem):
                    return self._parse_row(row)
                if source_name and source_name in normalized_filename:
                    return self._parse_row(row)
        return None

    def _parse_row(self, row: dict) -> dict | None:
        try:
            return {
                "source_id": row["source_id"],
                "source_name": row.get("source_name") or row["source_id"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "address": row.get("address") or None,
                "notes": row.get("notes") or None,
            }
        except (KeyError, TypeError, ValueError):
            return None
