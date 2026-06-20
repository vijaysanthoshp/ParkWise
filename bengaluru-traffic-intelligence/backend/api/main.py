"""
FastAPI Backend — BTP Parking Intelligence Module API
======================================================
Serves all pre-computed pipeline outputs and live LightGBM
Enforcement Demand Forecast predictions.

Start with:
    uvicorn api.main:app --reload --port 8000
    (run from the backend/ directory)

API docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api.data_store as ds
from api.routes import router

app = FastAPI(
    title="BTP Parking Intelligence API",
    description=(
        "AI-driven parking enforcement intelligence for "
        "Bengaluru Traffic Police — Flipkart Grid PS1"
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    ds.load_all_data()

app.include_router(router)
