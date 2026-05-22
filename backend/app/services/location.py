import json
import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.camera_registry import CameraRegistry
from app.services.metadata import MetadataExtractor


@dataclass
class LocationOutput:
    latitude: float | None
    longitude: float | None
    source: str
    address: str | None
    google_maps_url: str | None
    osm_url: str | None
    nearest_hospitals: list[dict]
    nearest_police_stations: list[dict]


class LocationResolverAgent:
    def __init__(self, camera_registry_path: Path | None = None) -> None:
        self.metadata_extractor = MetadataExtractor()
        self.camera_registry = CameraRegistry(camera_registry_path) if camera_registry_path else None
        self.local_hospitals = self._load_local_hospitals(camera_registry_path)
        self.local_police = self._load_local_police(camera_registry_path)

    def resolve(
        self,
        image_bytes: bytes,
        latitude: float | None = None,
        longitude: float | None = None,
        source_id: str | None = None,
        filename: str | None = None,
    ) -> LocationOutput:
        source = "request"
        if latitude is None or longitude is None:
            latitude, longitude = self.metadata_extractor.extract_gps(image_bytes)
            source = "image-metadata" if latitude is not None and longitude is not None else "unavailable"

        if (latitude is None or longitude is None) and self.camera_registry is not None:
            camera_record = self.camera_registry.lookup(source_id)
            if camera_record is not None:
                latitude = camera_record["latitude"]
                longitude = camera_record["longitude"]
                source = f"camera-registry:{camera_record['source_id']}"

        if (latitude is None or longitude is None) and self.camera_registry is not None:
            camera_record = self.camera_registry.lookup_from_filename(filename)
            if camera_record is not None:
                latitude = camera_record["latitude"]
                longitude = camera_record["longitude"]
                source = f"camera-registry-filename:{camera_record['source_id']}"

        if latitude is None or longitude is None:
            return LocationOutput(
                latitude=None,
                longitude=None,
                source=source,
                address=None,
                google_maps_url=None,
                osm_url=None,
                nearest_hospitals=[],
                nearest_police_stations=[],
            )

        address = self._reverse_geocode(latitude, longitude)
        hospitals = self._search_nearby(latitude, longitude, "hospital")
        if not hospitals:
            hospitals = self._search_local_hospitals(latitude, longitude)
        police = self._search_nearby(latitude, longitude, "police")
        if not police:
            police = self._search_local_police(latitude, longitude)

        return LocationOutput(
            latitude=latitude,
            longitude=longitude,
            source=source,
            address=address,
            google_maps_url=f"https://www.google.com/maps?q={latitude},{longitude}",
            osm_url=f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=17/{latitude}/{longitude}",
            nearest_hospitals=hospitals,
            nearest_police_stations=police,
        )

    def _reverse_geocode(self, latitude: float, longitude: float) -> str | None:
        try:
            url = (
                "https://nominatim.openstreetmap.org/reverse"
                f"?lat={latitude}&lon={longitude}&format=jsonv2"
            )
            request = Request(url, headers={"User-Agent": "AcciSense/1.0"})
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("display_name")
        except Exception:
            return None

    def _search_nearby(self, latitude: float, longitude: float, amenity: str) -> list[dict]:
        try:
            query = self._build_overpass_query(latitude, longitude, amenity)
            request = Request(
                "https://overpass-api.de/api/interpreter",
                data=f"data={quote(query)}".encode("utf-8"),
                headers={"User-Agent": "AcciSense/1.0", "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            results = []
            for item in payload.get("elements", [])[:5]:
                lat = item.get("lat") or item.get("center", {}).get("lat")
                lon = item.get("lon") or item.get("center", {}).get("lon")
                tags = item.get("tags", {})
                address = self._build_place_address(tags)
                if not address and lat is not None and lon is not None:
                    address = self._reverse_geocode(lat, lon)
                results.append(
                    {
                        "name": tags.get("name", amenity.title()),
                        "latitude": lat,
                        "longitude": lon,
                        "address": address,
                        "maps_url": f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else None,
                    }
                )
            return results
        except Exception:
            return []

    def _build_overpass_query(self, latitude: float, longitude: float, amenity: str) -> str:
        radius = 5000
        if amenity == "hospital":
            selectors = [
                f'node["amenity"="hospital"](around:{radius},{latitude},{longitude});',
                f'way["amenity"="hospital"](around:{radius},{latitude},{longitude});',
                f'relation["amenity"="hospital"](around:{radius},{latitude},{longitude});',
                f'node["healthcare"="hospital"](around:{radius},{latitude},{longitude});',
                f'way["healthcare"="hospital"](around:{radius},{latitude},{longitude});',
                f'relation["healthcare"="hospital"](around:{radius},{latitude},{longitude});',
                f'node["amenity"="clinic"](around:{radius},{latitude},{longitude});',
                f'way["amenity"="clinic"](around:{radius},{latitude},{longitude});',
                f'relation["amenity"="clinic"](around:{radius},{latitude},{longitude});',
                f'node["emergency"="ambulance_station"](around:{radius},{latitude},{longitude});',
                f'way["emergency"="ambulance_station"](around:{radius},{latitude},{longitude});',
                f'relation["emergency"="ambulance_station"](around:{radius},{latitude},{longitude});',
            ]
        else:
            selectors = [
                f'node["amenity"="{amenity}"](around:{radius},{latitude},{longitude});',
                f'way["amenity"="{amenity}"](around:{radius},{latitude},{longitude});',
                f'relation["amenity"="{amenity}"](around:{radius},{latitude},{longitude});',
            ]

        joined_selectors = "\n              ".join(selectors)
        return f"""
            [out:json];
            (
              {joined_selectors}
            );
            out center 8;
            """

    def _build_place_address(self, tags: dict) -> str | None:
        direct_address = tags.get("addr:full")
        if direct_address:
            return direct_address

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:neighbourhood"),
            tags.get("addr:city"),
        ]
        compact = ", ".join(part.strip() for part in address_parts if part and part.strip())
        return compact or None

    def _load_local_hospitals(self, camera_registry_path: Path | None) -> list[dict]:
        base_dir = camera_registry_path.parent if camera_registry_path else Path(__file__).resolve().parents[2] / "data"
        hospitals_path = base_dir / "mumbai_hospitals.csv"
        if not hospitals_path.exists():
            return []

        hospitals: list[dict] = []
        try:
            with hospitals_path.open("r", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    try:
                        hospitals.append(
                            {
                                "name": row["name"],
                                "latitude": float(row["latitude"]),
                                "longitude": float(row["longitude"]),
                                "address": row["address"],
                            }
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
        except Exception:
            return []
        return hospitals

    def _load_local_police(self, camera_registry_path: Path | None) -> list[dict]:
        base_dir = camera_registry_path.parent if camera_registry_path else Path(__file__).resolve().parents[2] / "data"
        police_path = base_dir / "mumbai_police_stations.csv"
        if not police_path.exists():
            return []

        police: list[dict] = []
        try:
            with police_path.open("r", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    try:
                        police.append(
                            {
                                "name": row["name"],
                                "latitude": float(row["latitude"]),
                                "longitude": float(row["longitude"]),
                                "address": row["address"],
                            }
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
        except Exception:
            return []
        return police

    def _search_local_hospitals(self, latitude: float, longitude: float) -> list[dict]:
        if not self.local_hospitals:
            return []

        ranked = sorted(
            self.local_hospitals,
            key=lambda item: self._haversine_distance_km(latitude, longitude, item["latitude"], item["longitude"]),
        )

        results: list[dict] = []
        for item in ranked[:3]:
            results.append(
                {
                    "name": item["name"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "address": item["address"],
                    "maps_url": f'https://www.google.com/maps?q={item["latitude"]},{item["longitude"]}',
                }
            )
        return results

    def _search_local_police(self, latitude: float, longitude: float) -> list[dict]:
        if not self.local_police:
            return []

        ranked = sorted(
            self.local_police,
            key=lambda item: self._haversine_distance_km(latitude, longitude, item["latitude"], item["longitude"]),
        )

        results: list[dict] = []
        for item in ranked[:3]:
            results.append(
                {
                    "name": item["name"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "address": item["address"],
                    "maps_url": f'https://www.google.com/maps?q={item["latitude"]},{item["longitude"]}',
                }
            )
        return results

    def _haversine_distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import asin, cos, radians, sin, sqrt

        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)

        a = sin(d_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(d_lon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return 6371 * c
