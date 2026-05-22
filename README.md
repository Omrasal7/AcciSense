# 🚨 AcciSense — AI Emergency Response & Accident Detection Platform

<div align="center">

### Intelligent AI-powered accident detection and emergency response system for CCTV, roadside cameras, and uploaded media

Built using **FastAPI**, **React**, **YOLOv8**, **OpenCV**, and **Leaflet Maps**

</div>

---

## 📌 Overview

**AcciSense** is a full-stack AI-powered emergency response platform designed for smart city surveillance and traffic monitoring systems.

The platform detects accidents from:

- CCTV feeds
- Roadside cameras
- Uploaded images
- Uploaded videos

It then:

- Estimates accident severity
- Resolves location using EXIF or camera registry mapping
- Finds nearby hospitals and police stations
- Sends emergency alerts through SMS and Email
- Displays incidents inside a live operational dashboard

---

# ✨ Features

## 🚗 AI Accident Detection

- Detects accidents from images and videos
- Supports CCTV-style surveillance footage
- False-positive reduction for calm road scenes
- Optional YOLOv8 classification support

---

## 🎥 Intelligent Video Analysis

- Scans the full uploaded video
- Selects the most meaningful accident frame
- Handles low-detail CCTV clips
- Supports representative incident extraction

---

## ⚠️ Severity Classification

The system classifies incidents into:

- Low
- Moderate
- High
- Critical

Severity logic includes:

- Fire detection influence
- Dark-scene moderation
- Extreme crash policy rules
- Rule-based severity correction

---

## 📍 Smart Location Resolution

Location is resolved using:

1. Manual coordinates
2. Image EXIF GPS
3. Camera registry mapping
4. Reverse geocoding

---

## 🏥 Nearby Emergency Services

Automatically finds nearby:

- Hospitals
- Police stations

Using:

- OpenStreetMap
- Nominatim
- Overpass API
- Local Mumbai fallback datasets

---

## 📲 Emergency Alert System

Supports:

### SMS Alerts

Using:

- Twilio SMS API

### Email Alerts

Using:

- SMTP Email
- HTML formatted emergency notifications

---

## 🖥️ Live Operations Dashboard

Includes:

- Dashboard overview
- Incident review panel
- Camera monitoring
- Live map visualization
- Admin contact management

---

# 🧠 System Architecture

```text
User Upload
     │
     ▼
AI Accident Detection
     │
     ▼
Severity Classification
     │
     ▼
Location Resolution
     │
     ▼
Nearby Service Lookup
     │
     ▼
SMS / Email Alerts
     │
     ▼
Live Dashboard Monitoring
```

---

# 🛠️ Tech Stack

## Backend

- Python
- FastAPI
- OpenCV
- NumPy
- SQLite
- Pillow
- EXIF Helpers
- YOLOv8 (Optional)

---

## Frontend

- React
- Vite
- Tailwind CSS
- Leaflet Maps
- Lucide React Icons

---

## Notifications

- Twilio SMS
- SMTP Email Alerts

---

## Maps & Geolocation

- OpenStreetMap
- Nominatim Reverse Geocoding
- Overpass API
- Google Maps Share Links

---

# 📂 Project Structure

```text
AcciSense-ai based accident detection/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── services/
│   │
│   ├── data/
│   ├── requirements.txt
│   └── requirements-yolo.txt
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── ml/
│   ├── train_classifiers.py
│   └── prepare_accident_dataset.py
│
├── models/
│   ├── accident_cls.pt
│   └── severity_cls.pt
│
├── runtime/
│   ├── accisense_live.db
│   ├── accisense_live_store.json
│   └── uploads/
│
├── datasets/
├── training_data/
├── tools/
├── .env
├── .env.example
└── README.md
```

---

# ⚙️ Installation & Setup

## 1️⃣ Clone Repository

```bash
git clone https://github.com/Omrasal7/your-repo-name.git

cd "AcciSense-ai based accident detection"
```

---

## 2️⃣ Backend Setup

```bash
cd backend

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

Run backend:

```bash
python -m uvicorn app.main:app --reload --port 8001
```

Backend docs:

```text
http://localhost:8001/docs
```

---

## 3️⃣ Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

# 🔐 Environment Variables

Copy:

```bash
.env.example
```

to:

```bash
.env
```

Example:

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

ENABLE_TWILIO=false
ENABLE_EMAIL=false
```

---

# 🤖 YOLOv8 Support (Optional)

Install YOLO dependencies:

```bash
cd backend

pip install -r requirements-yolo.txt
```

---

# 🧪 Model Training

## Prepare Dataset

```bash
cd ml

python prepare_accident_dataset.py --max-per-class 1400
```

---

## Train Accident Classifier

```bash
python train_classifiers.py --mode accident --epochs 12 --imgsz 224
```

---

## Train Severity Classifier

```bash
python train_classifiers.py --mode severity --epochs 12 --imgsz 224
```

---

## Train Both Models

```bash
python train_classifiers.py --mode both --epochs 12 --imgsz 224
```

---

# 📍 Camera Registry System

Example:

```csv
source_id,source_name,latitude,longitude,address
CAM-001,Highway Pole Camera 1,28.6139,77.2090,Connaught Place
```

Location priority:

1. Manual coordinates
2. EXIF GPS
3. Camera registry lookup
4. Reverse geocoding

---

# 📲 Twilio SMS Setup

```env
ENABLE_TWILIO=true

TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
DEFAULT_ALERT_PHONES=+91...
```

---

# 📧 Email Alert Setup

```env
ENABLE_EMAIL=true

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
```

---

# 🌐 ngrok Support

```bash
tools\ngrok\ngrok.exe http 8001
```

Then set:

```env
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.dev
```

---

# 🎬 Recommended Demo Flow

1. Start backend
2. Start frontend
3. Configure admin contact
4. Upload accident image/video
5. Review:
   - Accident detection
   - Severity
   - Location mapping
   - Nearby hospitals
   - Nearby police
   - SMS/email alerts

---

# 🔮 Future Improvements

- Real-time CCTV stream ingestion
- Multi-camera incident correlation
- AI object tracking
- Emergency dispatch automation
- Cloud deployment support
- Mobile responder application

---

# 📸 Screenshots


## Dashboard
<img width="1505" height="856" alt="image" src="https://github.com/user-attachments/assets/329d9bb9-9761-43e9-98ff-ab35e3387e99" />

---

## Location/maps
<img width="1532" height="839" alt="image" src="https://github.com/user-attachments/assets/f59140e4-6d55-44f6-9259-2c6690876947" />

---

## input/nearest hospitals and policestation
<img width="1665" height="830" alt="image" src="https://github.com/user-attachments/assets/460c647b-4b62-427d-9286-76c172bca1c0" />
<img width="1474" height="851" alt="image" src="https://github.com/user-attachments/assets/3b9f99c0-a372-4dae-90b8-4621ab3628f4" />


---

## Incident Review

<img width="1881" height="850" alt="image" src="https://github.com/user-attachments/assets/66e52ea0-a966-4522-bf42-ceb074909b72" />
<img width="1522" height="855" alt="image" src="https://github.com/user-attachments/assets/1a07c4f1-9e75-4274-97e8-556b0416ce1b" />


---

# 👨‍💻 Author

## Om Rasal

- MCA Student
- AI/ML Enthusiast
- Full Stack Developer
- Data & Computer Vision Explorer

---

# ⭐ Support

If you like this project:

- Star the repository
- Fork the project
- Share feedback
- Contribute improvements

---

<div align="center">

### 🚨 AcciSense — AI-Assisted Emergency Intelligence Platform

</div>
