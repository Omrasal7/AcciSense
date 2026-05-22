# AcciSense AI Emergency Response Platform

AcciSense is a full-stack AI accident detection and emergency response platform for CCTV, roadside cameras, and uploaded media. It detects accidents, estimates severity, resolves location from camera metadata or EXIF, finds nearby hospitals and police stations, and sends alerts through SMS and email.

The project is designed as a city-monitoring operations system with:

- AI-assisted accident detection
- Severity scoring
- Camera-to-location mapping
- Nearby emergency service lookup
- Alert routing to an admin contact
- A live web dashboard for operations review

## Features

- Accident detection for images and videos
- Severity classification with policy-based moderation
- Video analysis that scans the full clip and selects a representative event frame
- Camera registry-based geolocation fallback
- Reverse geocoding and map links
- Nearby hospitals and police stations
- Twilio SMS alerts
- SMTP email alerts with HTML formatting
- Live dashboard for:
  - dashboard overview
  - incident review
  - camera monitoring
  - map view
  - admin contact management

## Tech Stack

### Backend

- Python
- FastAPI
- OpenCV
- NumPy
- SQLite / JSON runtime store
- Pillow / EXIF helpers
- Optional Ultralytics YOLOv8 classification models

### Frontend

- React
- Vite
- Tailwind CSS
- Leaflet
- Lucide React icons

### Notifications

- Twilio SMS
- SMTP email

### Maps and location

- OpenStreetMap
- Nominatim reverse geocoding
- Overpass nearby place lookup
- Google Maps share links

## Project Structure

```text
AcciSense-ai based accident detection/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ repositories/
│  │  ├─ schemas/
│  │  └─ services/
│  ├─ data/
│  ├─ requirements.txt
│  └─ requirements-yolo.txt
├─ frontend/
│  ├─ src/
│  ├─ package.json
│  └─ vite.config.js
├─ ml/
│  ├─ train_classifiers.py
│  └─ prepare_accident_dataset.py
├─ models/
│  ├─ accident_cls.pt
│  └─ severity_cls.pt
├─ runtime/
│  ├─ accisense_live.db
│  ├─ accisense_live_store.json
│  └─ uploads/
├─ datasets/
├─ training_data/
│  ├─ Accident/
│  ├─ NonAccident/
│  └─ Severity Score Dataset with Labels/
├─ tools/
├─ .env
├─ .env.example
└─ README.md
```

## How the System Works

### 1. Media intake

The user uploads an image or video and selects a camera source.

### 2. Accident detection

The backend:

- runs the accident classifier
- applies conservative false-positive veto logic for calm road scenes
- for videos, scans the full clip and tries to select a meaningful accident frame

### 3. Severity estimation

The backend:

- runs the severity classifier when available
- adjusts the raw severity based on rules such as:
  - visible fire
  - dark low-detail night scenes
  - extreme vs moderate crash policy

### 4. Location resolution

The backend resolves location in this order:

1. request coordinates if provided
2. EXIF GPS from image
3. camera source registry lookup
4. reverse geocoding to a readable address

### 5. Nearby services

The backend finds:

- nearest hospitals
- nearest police stations

It uses live OpenStreetMap data first and local Mumbai fallback datasets if needed.

### 6. Notifications

The system can send:

- SMS via Twilio
- email via SMTP

Alerts are routed to the configured admin contact.

## Prerequisites

Before running the project, make sure you have:

- Python 3.11+ recommended
- Node.js 18+ recommended
- npm
- Git (optional but useful)

Optional:

- ngrok for public media links in SMS/email
- Twilio account for SMS
- Gmail App Password or SMTP credentials for email

## Environment Setup

Copy:

```bash
.env.example
```

to:

```bash
.env
```

Then configure the values you need.

### Example `.env`

```env
APP_NAME=AcciSense API
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8001
FRONTEND_ORIGIN=http://localhost:5173
PUBLIC_BASE_URL=http://localhost:8001

ACCIDENT_MODEL_PATH=../models/accident_cls.pt
SEVERITY_MODEL_PATH=../models/severity_cls.pt
UPLOAD_DIR=../runtime/uploads
DATABASE_PATH=../runtime/accisense_live.db
CAMERA_REGISTRY_PATH=./data/camera_registry.csv

ENABLE_OPENCV_FALLBACK=false
ENABLE_TWILIO=false
ENABLE_EMAIL=false

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
DEFAULT_ALERT_PHONES=
DEFAULT_ALERT_EMAILS=

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true

GOOGLE_MAPS_API_KEY=
```

## Backend Setup

From the project root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the backend:

```bash
python -m uvicorn app.main:app --reload --port 8001
```

Backend API docs:

- [http://localhost:8001/docs](http://localhost:8001/docs)

## Optional YOLO Support

If you want model training and YOLO-based classification:

```bash
cd backend
pip install -r requirements-yolo.txt
```

If YOLO is not installed:

- training will not work
- model-based accident detection will not initialize

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- [http://localhost:5173](http://localhost:5173)

## Running the Full App

Use this order:

1. Start backend
2. Start frontend
3. Open the frontend in browser
4. Upload an image or video
5. Select a camera source
6. Review the result

## Camera Registry

The camera registry lets the system map camera IDs to fixed coordinates and addresses.

File:

- [C:\Accisense-ai based accident detection\backend\data\camera_registry.csv](C:/Accisense-ai based accident detection/backend/data/camera_registry.csv)

Example:

```csv
source_id,source_name,latitude,longitude,address,notes
CAM-001,Highway Pole Camera 1,28.6139,77.2090,Connaught Place New Delhi,Northbound traffic feed
NH44-CAM-07,NH44 Junction Camera,28.6448,77.2167,Near NH44 Junction,Crash-prone segment
DRONE-12,Traffic Drone Patrol 12,28.5355,77.3910,Noida Sector 18,Aerial patrol zone
```

Location resolution order:

1. manual coordinates from request
2. EXIF GPS
3. camera registry source ID
4. reverse geocoding

## Model Training

### Raw training data

The raw folders are organized under:

- `training_data/Accident/`
- `training_data/NonAccident/`
- `training_data/Severity Score Dataset with Labels/1`
- `training_data/Severity Score Dataset with Labels/2`
- `training_data/Severity Score Dataset with Labels/3`

### Prepare a cleaner accident dataset

This filters duplicates and weak-quality images and builds a curated training set:

```bash
cd ml
python prepare_accident_dataset.py --max-per-class 1400
```

Output:

- `datasets/accident_curated/`
- `datasets/accident_curated/curation_report.csv`

### Train accident classifier only

Recommended first:

```bash
cd ml
python train_classifiers.py --mode accident --epochs 12 --imgsz 224 --accident-max 1200
```

### Train severity classifier only

```bash
cd ml
python train_classifiers.py --mode severity --epochs 12 --imgsz 224 --severity-max 900
```

### Train both

```bash
cd ml
python train_classifiers.py --mode both --epochs 12 --imgsz 224 --accident-max 1200 --severity-max 900
```

### Output models

The backend expects:

- `models/accident_cls.pt`
- `models/severity_cls.pt`

After training, restart the backend to use the updated models.

## Alerts Setup

### Twilio SMS

To enable SMS:

```env
ENABLE_TWILIO=true
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
DEFAULT_ALERT_PHONES=+91...
```

Notes:

- Twilio trial accounts can only send to verified numbers
- Twilio trial accounts have daily message limits
- public snapshot links require a public `PUBLIC_BASE_URL`

### Email

To enable email:

```env
ENABLE_EMAIL=true
DEFAULT_ALERT_EMAILS=you@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=you@example.com
SMTP_USE_TLS=true
```

If using Gmail:

- enable 2-Step Verification
- generate an App Password
- use the App Password, not your normal Gmail password

## ngrok for Public Snapshot URLs

If you want image links inside SMS or email to open on another device, expose the backend publicly.

Example:

```bash
tools\ngrok\ngrok.exe http 8001
```

Then set:

```env
PUBLIC_BASE_URL=https://your-real-ngrok-url.ngrok-free.dev
```

Restart the backend after changing it.

## Current Operational Rules

### Notification routing

- alerts go to the configured admin contact
- only one admin contact is active at a time

### Severity policy

- `critical` is reserved for extreme scenes such as fire or strong destruction evidence
- normal crashes should trend toward `moderate` or `high`
- dark low-detail CCTV scenes are prevented from jumping too aggressively to `critical`

### Static-scene false positive reduction

The detector uses extra scene analysis to suppress false positives for:

- calm road scenes
- parked vehicles
- ordinary street CCTV frames

## Troubleshooting

### Frontend shows runtime error

- restart the frontend:

```bash
cd frontend
npm run dev
```

- hard refresh browser with `Ctrl + F5`

### Backend not loading changes

- stop old backend windows
- start a fresh backend instance:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8001
```

### SMS not sending

Check:

- Twilio credentials
- trial limits
- verified number requirement
- public `PUBLIC_BASE_URL`
- Twilio logs for final message status

### Email not sending

Check:

- SMTP credentials
- Gmail App Password
- `ENABLE_EMAIL=true`

### Hospitals or police missing

The app first tries live OSM lookup and falls back to local Mumbai datasets. If an old incident card is missing these, upload a fresh incident because old saved results do not auto-refresh.

## Recommended Demo Flow

1. Start backend on `8001`
2. Start frontend on `5173`
3. Configure one admin contact
4. Upload a known accident image
5. Verify:
   - accident detection
   - severity
   - map resolution
   - nearby hospitals
   - nearby police
   - email/SMS alert behavior

## Notes

- This project is best treated as an AI-assisted emergency response demo / prototype platform
- For production-grade deployment, you would still want:
  - stronger datasets
  - more reliable video event modeling
  - better model calibration
  - hardened alerting and observability

## License / usage

Add your preferred license here if you plan to publish the repository.
#   A c c i S e n s e  
 