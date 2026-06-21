# 🚓 ParkWise: Parking Intelligence Module

**Flipkart Grid 6.0 | Problem Statement 1:** Karnataka State Police - Smart Traffic Management & Enforcement Prioritisation

---

## 🚀 Live Demo

You can view the live deployment of ParkWise here: **[https://park-wise-seven.vercel.app/](https://park-wise-seven.vercel.app/)**

> **Evaluator Note:** The backend API is hosted on a free tier. When you first open the link, the top right corner may show "API Offline" or say "Loading incident data...". Please wait **30 to 90 seconds** for the server to wake up, then refresh the page. Once awake, everything will load instantly!

---

## 🎥 Full Video Demo

Watch the complete walkthrough of the ParkWise module here: **`[INSERT YOUR YOUTUBE/DRIVE VIDEO LINK HERE]`**

---

## 📖 The Problem
Bengaluru Traffic Police handles massive amounts of incident data. The hidden problem is that a huge percentage of severe congestion is caused by unregulated, illegal parking. ParkWise shifts the police force from reactive dispatching to proactive, data-driven patrol deployment.

## 💡 Our Methodology (Steps Used)
1. **NLP Data Extraction:** We process raw unstructured traffic logs and mathematically identify incidents caused specifically by illegal parking.
2. **DBSCAN Spatial Clustering:** The live map dynamically clusters these parking violations to highlight high-priority gridlock zones.
3. **Predictive Forecasting (LightGBM):** Using historical data and H3 hex grids, our AI predicts exactly how many patrol officers will be needed at specific junctions in the future.
4. **Explainable AI (SHAP):** We use SHAP values to explain *why* the AI made its prediction, ensuring total transparency for police commanders.
5. **ASTraM Copilot (Groq LLM):** A generative AI assistant reads the live data and translates complex charts into plain-English deployment orders.
6. **High-Speed Analytics (DuckDB):** The backend queries the entire 136,000+ record dataset in milliseconds without crashing standard hardware.

---

## 📂 Project Structure

```text
ParkWise/
└── bengaluru-traffic-intelligence/
    ├── backend/                  # Python FastAPI Backend
    │   ├── api/                  # API routing, DuckDB queries, & endpoints
    │   ├── data/                 # Raw and processed Parquet data files
    │   ├── models/               # Saved LightGBM & SHAP explainer models
    │   ├── pipeline.py           # ML training & NLP data processing pipeline
    │   └── requirements.txt      # Python dependencies
    └── frontend/                 # React.js Frontend
        ├── src/
        │   ├── components/       # UI Components (Smart Map, Risk Scorecard, Forecast)
        │   ├── App.jsx           # Main routing and layout
        │   └── index.css         # Styling and design system
        ├── package.json          # Node dependencies
        └── vite.config.js        # Vite bundler configuration
```

---

## 💻 How to Run Locally

Follow these steps to run the complete ParkWise pipeline from scratch.

### 1. Clone the Repository
```bash
git clone https://github.com/vijaysanthoshp/ParkWise.git
cd ParkWise/bengaluru-traffic-intelligence
```

### 2. Backend Setup
Open a terminal and navigate to the backend:
```bash
cd backend

# Create a virtual environment:
python -m venv .venv

# Activate the virtual environment:
# On Windows: .venv\Scripts\activate
# On Mac/Linux: source .venv/bin/activate

# Install dependencies:
pip install -r requirements.txt

# Run the data processing and ML pipeline (Ensure raw .csv is in backend/data/raw):
python pipeline.py

# Start the FastAPI Server:
uvicorn api.main:app --reload --port 8000
```

### 3. Frontend Setup
Open a **new** terminal window and navigate to the frontend:
```bash
cd ParkWise/bengaluru-traffic-intelligence/frontend

# Install dependencies:
npm install

# Create a .env file inside the frontend folder and add:
# VITE_API_URL=http://127.0.0.1:8000

# Start the React Development Server:
npm run dev
```

The application will now be running at `http://localhost:5173`. Open this in your browser to view the ParkWise dashboard!
# 🚓 ParkWise: Parking Intelligence Module

**Flipkart Grid 6.0 | Problem Statement 1:** Karnataka State Police - Smart Traffic Management & Enforcement Prioritisation

---

## 🚀 Live Demo

You can view the live deployment of ParkWise here: **[https://park-wise-seven.vercel.app/](https://park-wise-seven.vercel.app/)**

> **Evaluator Note:** The backend API is hosted on a free tier. When you first open the link, the top right corner may show "API Offline" or say "Loading incident data...". Please wait **30 to 90 seconds** for the server to wake up, then refresh the page. Once awake, everything will load instantly!

---

## 🎥 Full Video Demo

Watch the complete walkthrough of the ParkWise module here: **`[INSERT YOUR YOUTUBE/DRIVE VIDEO LINK HERE]`**

---

## 📖 The Problem
Bengaluru Traffic Police handles massive amounts of incident data. The hidden problem is that a huge percentage of severe congestion is caused by unregulated, illegal parking. ParkWise shifts the police force from reactive dispatching to proactive, data-driven patrol deployment.

## 💡 Our Methodology (Steps Used)
1. **NLP Data Extraction:** We process raw unstructured traffic logs and mathematically identify incidents caused specifically by illegal parking.
2. **DBSCAN Spatial Clustering:** The live map dynamically clusters these parking violations to highlight high-priority gridlock zones.
3. **Predictive Forecasting (LightGBM):** Using historical data and H3 hex grids, our AI predicts exactly how many patrol officers will be needed at specific junctions in the future.
4. **Explainable AI (SHAP):** We use SHAP values to explain *why* the AI made its prediction, ensuring total transparency for police commanders.
5. **ASTraM Copilot (Groq LLM):** A generative AI assistant reads the live data and translates complex charts into plain-English deployment orders.
6. **High-Speed Analytics (DuckDB):** The backend queries the entire 136,000+ record dataset in milliseconds without crashing standard hardware.

---

## 📂 Project Structure

```text
ParkWise/
└── bengaluru-traffic-intelligence/
    ├── backend/                  # Python FastAPI Backend
    │   ├── api/                  # API routing, DuckDB queries, & endpoints
    │   ├── data/                 # Raw and processed Parquet data files
    │   ├── models/               # Saved LightGBM & SHAP explainer models
    │   ├── pipeline.py           # ML training & NLP data processing pipeline
    │   └── requirements.txt      # Python dependencies
    └── frontend/                 # React.js Frontend
        ├── src/
        │   ├── components/       # UI Components (Smart Map, Risk Scorecard, Forecast)
        │   ├── App.jsx           # Main routing and layout
        │   └── index.css         # Styling and design system
        ├── package.json          # Node dependencies
        └── vite.config.js        # Vite bundler configuration
```

---

## 💻 How to Run Locally

Follow these steps to run the complete ParkWise pipeline from scratch.

### 1. Clone the Repository
```bash
git clone https://github.com/vijaysanthoshp/ParkWise.git
cd ParkWise/bengaluru-traffic-intelligence
```

### 2. Backend Setup
Open a terminal and navigate to the backend:
```bash
cd backend

# Create a virtual environment:
python -m venv .venv

# Activate the virtual environment:
# On Windows: .venv\Scripts\activate
# On Mac/Linux: source .venv/bin/activate

# Install dependencies:
pip install -r requirements.txt

# Run the data processing and ML pipeline (Ensure raw .csv is in backend/data/raw):
python pipeline.py

# Start the FastAPI Server:
uvicorn api.main:app --reload --port 8000
```

### 3. Frontend Setup
Open a **new** terminal window and navigate to the frontend:
```bash
cd ParkWise/bengaluru-traffic-intelligence/frontend

# Install dependencies:
npm install

# Create a .env file inside the frontend folder and add:
# VITE_API_URL=http://127.0.0.1:8000

# Start the React Development Server:
npm run dev
```

The application will now be running at `http://localhost:5173`. Open this in your browser to view the ParkWise dashboard!
