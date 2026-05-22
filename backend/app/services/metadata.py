from io import BytesIO

from PIL import Image, ExifTags


class MetadataExtractor:
    def extract_gps(self, image_bytes: bytes) -> tuple[float | None, float | None]:
        try:
            image = Image.open(BytesIO(image_bytes))
            exif = image.getexif()
            if not exif:
                return None, None

            gps_tag = None
            for key, value in ExifTags.TAGS.items():
                if value == "GPSInfo":
                    gps_tag = key
                    break

            if gps_tag is None or gps_tag not in exif:
                return None, None

            gps_info = exif[gps_tag]
            latitude = self._convert_to_degrees(gps_info.get(2))
            longitude = self._convert_to_degrees(gps_info.get(4))
            if latitude is None or longitude is None:
                return None, None

            if gps_info.get(1) == "S":
                latitude *= -1
            if gps_info.get(3) == "W":
                longitude *= -1
            return latitude, longitude
        except Exception:
            return None, None

    def _convert_to_degrees(self, values) -> float | None:
        if not values or len(values) != 3:
            return None
        degrees = float(values[0])
        minutes = float(values[1])
        seconds = float(values[2])
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
