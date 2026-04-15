# Prescription Recognition & Safety Verification System

An AI-powered web application that digitizes handwritten medical prescriptions, verifies medicine names, and locates nearby pharmacies.

## Features

- **Prescription Upload & Camera Scan** — Upload images or capture prescriptions via in-browser camera
- **AI-Powered Extraction** — Groq API (LLaMA-4-Scout-17B) reads handwritten text and extracts medicines, dosages, and frequencies
- **CRNN Validation** — Custom-trained CNN + BiLSTM + CTC model validates extracted medicine names
- **Multi-Algorithm Matching** — 4-algorithm weighted ensemble (RapidFuzz, Jaro-Winkler, Levenshtein, Partial Ratio) matches against 800+ Indian medicines
- **Hallucination Filtering** — Rule-based filter removes non-medicine words from LLM output
- **Pharmacy Locator** — Geo-based search with Haversine distance, interactive Leaflet.js map, and stock estimation
- **Feedback System** — Users can confirm/correct recognized medicines for future improvement

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3 (glassmorphism), Vanilla JS, Leaflet.js |
| Backend | Python 3, Flask, Flask-SQLAlchemy |
| Database | PostgreSQL |
| AI/Vision | Groq API (LLaMA-4-Scout-17B) |
| AI/Local | Custom CRNN (PyTorch, ~8.2M params, CPU inference) |
| Matching | RapidFuzz, Jellyfish |
| Maps | OpenStreetMap + Leaflet.js |

## Project Structure

```
PrescriptionWebApp/
├── app.py                     # Flask entry point
├── db.py                      # Database instance
├── model.py                   # SQLAlchemy ORM models
├── crnn_engine.py             # CRNN validator engine
├── pharmacy_finder.py         # Geo-based pharmacy search
├── medicine_availability.py   # Stock estimation
│
├── config/                    # Configuration
│   └── .env                   #   Environment variables
├── data/                      # Data files
│   └── medicine_database.json #   800+ Indian medicines
├── scripts/                   # Utility & migration scripts
│   ├── run_once.py            #   Create DB tables
│   ├── migrate_medicines.py   #   Seed medicine data
│   ├── seed_pharmacies.py     #   Generate mock pharmacies
│   └── fetch_pharmacies.py    #   Fetch from OpenStreetMap
├── models/                    # AI model artifacts
│   ├── checkpoints/           #   Trained CRNN weights
│   └── dataset/               #   Training data & metadata
├── notebooks/                 # Jupyter training notebooks
├── templates/                 # Flask HTML templates
├── static/                    # CSS & static assets
├── uploads/                   # User uploaded prescriptions
└── docs/                      # Screenshots & graphs
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   # Edit config/.env with your database URL and Groq API key
   DATABASE_URL=postgresql://user:pass@localhost:5433/medical_prescription
   ```

3. **Initialize database:**
   ```bash
   python scripts/run_once.py
   python scripts/migrate_medicines.py
   python scripts/seed_pharmacies.py
   ```

4. **Run the application:**
   ```bash
   python app.py
   ```
   Open http://localhost:5000

## Model Details

- **Architecture:** CNN (7 conv layers) → BiLSTM (2 layers, 256 hidden) → CTC Decoder
- **Parameters:** 8,218,822 (~32.9 MB)
- **Input:** Grayscale 32×128 pixel images
- **Output:** 70 character classes (69 chars + CTC blank)
- **Training:** 39,160 word crops, 50 epochs on Google Colab (T4 GPU)
