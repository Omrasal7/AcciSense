import base64
import json
import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import Settings


class NotificationAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def notify(self, incident: dict, contacts: list[dict]) -> dict:
        sms_sent_to: list[str] = []
        sms_results: list[dict] = []
        email_sent_to: list[str] = []
        errors: list[str] = []

        admin_contacts = contacts[:1]
        phones = [self._normalize_phone(contact["phone"]) for contact in admin_contacts if contact.get("phone")]
        phones = [phone for phone in phones if phone]
        emails = [contact["email"] for contact in admin_contacts if contact.get("email")]

        if not phones and self.settings.default_alert_phones:
            phones = [self._normalize_phone(item.strip()) for item in self.settings.default_alert_phones.split(",") if item.strip()]
            phones = [phone for phone in phones if phone]
        if not emails and self.settings.default_alert_emails:
            emails = [item.strip() for item in self.settings.default_alert_emails.split(",") if item.strip()]

        for phone in phones:
            try:
                if not self.settings.enable_twilio:
                    errors.append(f"SMS not sent to {phone}: Twilio is disabled in backend configuration.")
                    continue
                if not self.settings.twilio_account_sid or not self.settings.twilio_auth_token or not self.settings.twilio_from_number:
                    errors.append(f"SMS not sent to {phone}: Twilio credentials or sender number are missing.")
                    continue
                sms_result = self._send_sms(phone, incident)
                sms_sent_to.append(phone)
                sms_results.append(sms_result)
            except Exception as exc:
                errors.append(f"SMS failed for {phone}: {exc}")

        for email in emails:
            try:
                if not self.settings.enable_email:
                    errors.append(f"Email not sent to {email}: Email delivery is disabled in backend configuration.")
                    continue
                self._send_email(email, incident)
                email_sent_to.append(email)
            except Exception as exc:
                errors.append(f"Email failed for {email}: {exc}")

        return {
            "sms_sent_to": sms_sent_to,
            "sms_results": sms_results,
            "email_sent_to": email_sent_to,
            "dashboard_logged": True,
            "errors": errors,
        }

    def _send_sms(self, phone: str, incident: dict) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json"
        body = (
            f"Accident detected. Severity: {incident['severity']['label']}. "
            f"Confidence: {round(incident['detection']['confidence'] * 100)}%. "
            f"Location: {incident['location'].get('google_maps_url') or 'Unavailable'}. "
            f"Snapshot: {self._public_url(incident['image_url']) or 'Unavailable'}"
        )
        params = {
            "To": phone,
            "From": self.settings.twilio_from_number,
            "Body": body,
        }
        media_url = self._public_url(incident["image_url"])
        if media_url and self._is_public_media_url(media_url):
            params["MediaUrl"] = media_url
        payload = urlencode(params).encode("utf-8")
        credentials = f"{self.settings.twilio_account_sid}:{self.settings.twilio_auth_token}".encode("utf-8")
        headers = {
            "Authorization": f"Basic {base64.b64encode(credentials).decode('utf-8')}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        request = Request(url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {
                "phone": phone,
                "sid": payload.get("sid"),
                "status": payload.get("status"),
                "error_code": payload.get("error_code"),
                "error_message": payload.get("error_message"),
            }
        except HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8")) from exc

    def _send_email(self, recipient: str, incident: dict) -> None:
        missing_fields = []
        if not self.settings.smtp_host:
            missing_fields.append("SMTP_HOST")
        if not self.settings.smtp_username:
            missing_fields.append("SMTP_USERNAME")
        if not self.settings.smtp_password:
            missing_fields.append("SMTP_PASSWORD")
        if not self.settings.smtp_from_email:
            missing_fields.append("SMTP_FROM_EMAIL")
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise RuntimeError(
                f"SMTP configuration is incomplete. Set {missing} in the project .env file."
            )

        message = EmailMessage()
        message["Subject"] = f"Emergency Alert: {incident['severity']['label'].title()} accident"
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message.set_content(self._build_email_body(incident))

        inline_cid = "incident-snapshot"
        message.add_alternative(self._build_email_html(incident, inline_cid), subtype="html")

        local_snapshot_path = self._resolve_local_media_path(incident.get("image_url"))
        if local_snapshot_path is not None and local_snapshot_path.exists():
            mime_type, _ = mimetypes.guess_type(local_snapshot_path.name)
            maintype, subtype = (mime_type or "image/jpeg").split("/", 1)
            html_part = message.get_payload()[-1]
            html_part.add_related(
                local_snapshot_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                cid=f"<{inline_cid}>",
                filename=local_snapshot_path.name,
            )

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if self.settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)

    def _build_email_body(self, incident: dict) -> str:
        detection = incident["detection"]
        severity = incident["severity"]
        location = incident["location"]
        snapshot_url = self._public_url(incident["image_url"]) or "Unavailable"
        media_url = self._public_url(incident["original_media_url"]) or "Unavailable"
        hospital_lines = self._format_places(location.get("nearest_hospitals", []))
        police_lines = self._format_places(location.get("nearest_police_stations", []))

        sections = [
            "Emergency Alert",
            "",
            f"Incident ID: {incident['id']}",
            f"Detected accident: {'Yes' if detection.get('accident_detected') else 'No'}",
            f"Severity: {severity.get('label', 'unknown').title()} (score {severity.get('score', 'n/a')})",
            f"Confidence: {round(float(detection.get('confidence', 0)) * 100)}%",
            f"Source: {location.get('source') or 'Unavailable'}",
            f"Address: {location.get('address') or 'Unavailable'}",
            f"Google Maps: {location.get('google_maps_url') or 'Unavailable'}",
            f"OpenStreetMap: {location.get('osm_url') or 'Unavailable'}",
            f"Snapshot: {snapshot_url}",
            f"Original media: {media_url}",
            "",
            "Nearest hospitals:",
            *hospital_lines,
            "",
            "Nearest police stations:",
            *police_lines,
        ]
        return "\n".join(sections)

    def _build_email_html(self, incident: dict, inline_cid: str) -> str:
        detection = incident["detection"]
        severity = incident["severity"]
        location = incident["location"]
        severity_label = severity.get("label", "unknown").title()
        severity_tone = {
            "Low": "#FBBF24",
            "Moderate": "#F97316",
            "High": "#DC2626",
            "Critical": "#991B1B",
        }.get(severity_label, "#1E3A8A")
        snapshot_url = self._public_url(incident["image_url"]) or "Unavailable"
        maps_url = location.get("google_maps_url") or location.get("osm_url") or "#"
        hospitals = self._format_places_html(location.get("nearest_hospitals", []))
        police = self._format_places_html(location.get("nearest_police_stations", []))

        return f"""
<html>
  <body style="margin:0;padding:24px;background:#f5f7fa;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <div style="max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:24px;overflow:hidden;">
      <div style="padding:24px 28px;background:linear-gradient(135deg,#ffffff 0%,#eff6ff 100%);border-bottom:1px solid #e2e8f0;">
        <div style="font-size:12px;letter-spacing:0.12em;color:#64748b;font-weight:700;text-transform:uppercase;">AcciSense Emergency Alert</div>
        <h1 style="margin:12px 0 8px;font-size:30px;line-height:1.15;color:#0f172a;">Accident response summary</h1>
        <p style="margin:0;font-size:15px;line-height:1.7;color:#475569;">
          A verified incident has been processed by the AcciSense pipeline. Review the snapshot, location, and nearby response resources below.
        </p>
      </div>

      <div style="padding:28px;">
        <div style="display:inline-block;padding:8px 14px;border-radius:999px;background:{severity_tone};color:#ffffff;font-size:13px;font-weight:700;">
          Severity: {severity_label}
        </div>

        <div style="margin-top:20px;border:1px solid #e2e8f0;border-radius:20px;overflow:hidden;background:#f8fafc;">
          <img src="cid:{inline_cid}" alt="Incident snapshot" style="display:block;width:100%;max-height:360px;object-fit:cover;background:#0f172a;" />
        </div>

        <div style="margin-top:22px;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;">
          <div style="padding:16px;border:1px solid #e2e8f0;border-radius:18px;background:#ffffff;">
            <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Detection</div>
            <div style="margin-top:8px;font-size:24px;font-weight:700;color:#0f172a;">{"Yes" if detection.get("accident_detected") else "No"}</div>
          </div>
          <div style="padding:16px;border:1px solid #e2e8f0;border-radius:18px;background:#ffffff;">
            <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Confidence</div>
            <div style="margin-top:8px;font-size:24px;font-weight:700;color:#0f172a;">{round(float(detection.get("confidence", 0)) * 100)}%</div>
          </div>
          <div style="padding:16px;border:1px solid #e2e8f0;border-radius:18px;background:#ffffff;">
            <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Location source</div>
            <div style="margin-top:8px;font-size:16px;font-weight:700;color:#0f172a;">{location.get("source") or "Unavailable"}</div>
          </div>
        </div>

        <div style="margin-top:22px;padding:18px;border:1px solid #e2e8f0;border-radius:20px;background:#ffffff;">
          <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Resolved address</div>
          <div style="margin-top:10px;font-size:15px;line-height:1.7;color:#334155;">{location.get("address") or "Unavailable"}</div>
          <div style="margin-top:14px;">
            <a href="{maps_url}" style="display:inline-block;padding:10px 16px;border-radius:999px;background:#0f172a;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">Open location</a>
            <a href="{snapshot_url}" style="display:inline-block;margin-left:10px;padding:10px 16px;border-radius:999px;border:1px solid #cbd5e1;color:#0f172a;text-decoration:none;font-size:14px;font-weight:600;">Open snapshot</a>
          </div>
        </div>

        <div style="margin-top:22px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;">
          <div style="padding:18px;border:1px solid #e2e8f0;border-radius:20px;background:#ffffff;">
            <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Nearest hospitals</div>
            <div style="margin-top:12px;">{hospitals}</div>
          </div>
          <div style="padding:18px;border:1px solid #e2e8f0;border-radius:20px;background:#ffffff;">
            <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Nearest police stations</div>
            <div style="margin-top:12px;">{police}</div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
        """.strip()

    def _format_places(self, places: list[dict]) -> list[str]:
        if not places:
            return ["- No nearby places found."]

        lines: list[str] = []
        for place in places[:3]:
            name = place.get("name") or "Unknown"
            address = place.get("address") or "Address unavailable"
            maps_url = place.get("maps_url") or "No map link"
            lines.append(f"- {name}")
            lines.append(f"  Address: {address}")
            lines.append(f"  Maps: {maps_url}")
        return lines

    def _format_places_html(self, places: list[dict]) -> str:
        if not places:
            return '<div style="font-size:14px;color:#64748b;">No nearby places found.</div>'

        rendered: list[str] = []
        for place in places[:3]:
            name = place.get("name") or "Unknown"
            address = place.get("address") or "Address unavailable"
            rendered.append(
                f"""
<div style="margin-bottom:14px;">
  <div style="font-size:15px;font-weight:700;color:#0f172a;">{name}</div>
  <div style="margin-top:4px;font-size:14px;line-height:1.6;color:#64748b;">{address}</div>
</div>
                """.strip()
            )
        return "".join(rendered)

    def _public_url(self, relative_path: str) -> str | None:
        if not relative_path:
            return None
        base = self.settings.public_base_url.rstrip("/")
        return f"{base}{relative_path}"

    def _resolve_local_media_path(self, relative_path: str | None) -> Path | None:
        if not relative_path:
            return None
        file_name = Path(relative_path).name
        path = self.settings.upload_dir / file_name
        return path if path.exists() else None

    def _is_public_media_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0"}
        if host in blocked_hosts:
            return False
        if "your-ngrok-url" in host or host.endswith(".example.com") or host == "example.com":
            return False
        if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.16."):
            return False
        return True

    def _normalize_phone(self, raw_phone: str | None) -> str | None:
        if not raw_phone:
            return None

        cleaned = "".join(ch for ch in raw_phone if ch.isdigit() or ch == "+").strip()
        if not cleaned:
            return None

        if cleaned.startswith("+"):
            return cleaned

        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if len(digits) == 10:
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        return f"+{digits}" if digits else None
