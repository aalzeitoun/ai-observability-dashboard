# AI Observability & MLOps Dashboard

A minimal full-stack dashboard for monitoring deployed machine learning models.

The project will eventually include:

- FastAPI backend for collecting and analyzing inference logs
- PostgreSQL storage
- Statistical data drift detection using the Kolmogorov–Smirnov test
- WebSocket-based real-time monitoring
- Vue.js dashboard with Chart.js visualizations
- Simulated production data drift scenarios

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- Vue.js
- Docker
- Docker Compose

## Current Status

Store reference training data in PostgreSQL
Step 8 implements: 

- FastAPI backend
- PostgreSQL service
- Health endpoint
- Inference log storage API
- Persistent inference profile tracking: manual, normal, and drift
- Stored Iris training reference data in PostgreSQL
- Reference feature summary endpoint
- scikit-learn Iris model simulator
- Normal and drifted inference simulation
- Backend metrics endpoints for latency, confidence, and prediction counts
- WebSocket endpoint for real-time dashboard updates
- Vue dashboard with Chart.js visualizations
- UI controls for simulating normal and drifted inference
- Docker Compose workflow

## Run Locally

Copy the example environment file:

```bash
cp .env.example .env
```
