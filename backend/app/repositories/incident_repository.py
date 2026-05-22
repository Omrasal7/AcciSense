import json
import sqlite3
from datetime import datetime
from pathlib import Path


class IncidentRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path = self.db_path.with_name(f"{self.db_path.stem}_store.json")
        self.use_json_store = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incidents (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        media_type TEXT NOT NULL DEFAULT 'image',
                        original_media_url TEXT NOT NULL DEFAULT '',
                        image_url TEXT NOT NULL,
                        detection_json TEXT NOT NULL,
                        severity_json TEXT NOT NULL,
                        location_json TEXT NOT NULL,
                        notifications_json TEXT NOT NULL
                    )
                    """
                )
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(incidents)").fetchall()}
                if "media_type" not in columns:
                    conn.execute("ALTER TABLE incidents ADD COLUMN media_type TEXT NOT NULL DEFAULT 'image'")
                if "original_media_url" not in columns:
                    conn.execute("ALTER TABLE incidents ADD COLUMN original_media_url TEXT NOT NULL DEFAULT ''")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        phone TEXT,
                        email TEXT,
                        relation TEXT
                    )
                    """
                )
                conn.commit()
        except sqlite3.OperationalError:
            self.use_json_store = True
            self._ensure_json_store()

    def create_incident(self, incident: dict) -> None:
        if self.use_json_store:
            store = self._load_json_store()
            payload = self._serialize_incident_for_store(incident)
            store["incidents"].insert(0, payload)
            self._write_json_store(store)
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    id, created_at, media_type, original_media_url, image_url, detection_json,
                    severity_json, location_json, notifications_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident["id"],
                    incident["created_at"].isoformat(),
                    incident["media_type"],
                    incident["original_media_url"],
                    incident["image_url"],
                    json.dumps(incident["detection"]),
                    json.dumps(incident["severity"]),
                    json.dumps(incident["location"]),
                    json.dumps(incident["notifications"]),
                ),
            )
            conn.commit()

    def list_incidents(self) -> list[dict]:
        if self.use_json_store:
            store = self._load_json_store()
            incidents = [self._deserialize_incident_from_store(item) for item in store["incidents"]]
            return sorted(incidents, key=lambda item: item["created_at"], reverse=True)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM incidents ORDER BY datetime(created_at) DESC"
            ).fetchall()
        return [self._incident_from_row(row) for row in rows]

    def get_incident(self, incident_id: str) -> dict | None:
        if self.use_json_store:
            store = self._load_json_store()
            for incident in store["incidents"]:
                if incident["id"] == incident_id:
                    return self._deserialize_incident_from_store(incident)
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?",
                (incident_id,),
            ).fetchone()
        if row is None:
            return None
        return self._incident_from_row(row)

    def delete_incident(self, incident_id: str) -> dict | None:
        incident = self.get_incident(incident_id)
        if incident is None:
            return None
        with self._connect() as conn:
            conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
            conn.commit()
        return incident

    def list_contacts(self) -> list[dict]:
        if self.use_json_store:
            store = self._load_json_store()
            contacts = sorted(store["contacts"], key=lambda item: item["id"], reverse=True)
            return contacts[:1]
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM contacts ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows[:1]]

    def create_contact(self, contact: dict) -> dict:
        if self.use_json_store:
            store = self._load_json_store()
            new_id = max((item["id"] for item in store["contacts"]), default=0) + 1
            payload = {"id": new_id, **contact}
            store["contacts"] = [payload]
            self._write_json_store(store)
            return payload
        with self._connect() as conn:
            conn.execute("DELETE FROM contacts")
            cursor = conn.execute(
                """
                INSERT INTO contacts (name, phone, email, relation)
                VALUES (?, ?, ?, ?)
                """,
                (
                    contact["name"],
                    contact.get("phone"),
                    contact.get("email"),
                    contact.get("relation"),
                ),
            )
            conn.commit()
            new_id = cursor.lastrowid
        return {
            "id": new_id,
            **contact,
        }

    def delete_contact(self, contact_id: int) -> dict | None:
        if self.use_json_store:
            store = self._load_json_store()
            existing = next((item for item in store["contacts"] if item["id"] == contact_id), None)
            if existing is None:
                return None
            store["contacts"] = [item for item in store["contacts"] if item["id"] != contact_id]
            self._write_json_store(store)
            return existing
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
        return dict(row)

    def _incident_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "media_type": row["media_type"],
            "original_media_url": row["original_media_url"],
            "image_url": row["image_url"],
            "detection": json.loads(row["detection_json"]),
            "severity": json.loads(row["severity_json"]),
            "location": json.loads(row["location_json"]),
            "notifications": json.loads(row["notifications_json"]),
        }

    def _ensure_json_store(self) -> None:
        if self.store_path.exists():
            return
        self._write_json_store({"incidents": [], "contacts": []})

    def _load_json_store(self) -> dict:
        self._ensure_json_store()
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _write_json_store(self, payload: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _serialize_incident_for_store(self, incident: dict) -> dict:
        payload = dict(incident)
        created_at = payload.get("created_at")
        if isinstance(created_at, datetime):
            payload["created_at"] = created_at.isoformat()
        return payload

    def _deserialize_incident_from_store(self, incident: dict) -> dict:
        payload = dict(incident)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return payload
