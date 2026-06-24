import os

files_to_create = {
    ".env.example": """# Database configuration
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mldashboard
DATABASE_URL=postgresql://postgres:postgres@db:5432/mldashboard
""",
    ".gitignore": """# Python
__pycache__/
*.pyc
.env
venv/

# Node
node_modules/
dist/
.DS_Store
""",
    "README.md": """# AI Observability & MLOps Dashboard

A full-stack monitoring platform for deployed machine learning models, focusing on data drift detection (using Kolmogorov–Smirnov test) and inference latency monitoring.

## Tech Stack
- **Backend:** Python, FastAPI, PostgreSQL, scikit-learn, SciPy
- **Frontend:** Vue.js, Vite, Chart.js
- **Infrastructure:** Docker, Docker Compose
""",
    "docker-compose.yml": """version: '3.8'

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: mldashboard
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/mldashboard
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend

volumes:
  postgres_data:
""",
    "backend/requirements.txt": """fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
scikit-learn==1.3.2
scipy==1.11.4
""",
    "backend/Dockerfile": """FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
""",
    "backend/main.py": """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MLOps Dashboard API")

# Configure CORS so the Vue frontend can communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend is up and running!"}
""",
    "frontend/package.json": """{
  "name": "mlops-dashboard-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "vue": "^3.3.4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.2.3",
    "vite": "^4.4.5"
  }
}
""",
    "frontend/vite.config.js": """import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0', // Required for Docker
    port: 5173
  }
})
""",
    "frontend/Dockerfile": """FROM node:18-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
""",
    "frontend/index.html": """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MLOps Dashboard</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
""",
    "frontend/src/main.js": """import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
""",
    "frontend/src/App.vue": """<template>
  <div class="container">
    <h1>AI Observability & MLOps Dashboard</h1>
    <p>Backend Status: <span :class="statusClass">{{ backendStatus }}</span></p>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'

const backendStatus = ref('Checking...')

const statusClass = computed(() => {
  if (backendStatus.value === 'Checking...') return 'checking'
  if (backendStatus.value === 'Connected!') return 'connected'
  return 'error'
})

onMounted(async () => {
  try {
    const response = await fetch('http://localhost:8000/health')
    const data = await response.json()
    if (data.status === 'ok') {
      backendStatus.value = 'Connected!'
    }
  } catch (error) {
    backendStatus.value = 'Failed to connect'
    console.error(error)
  }
})
</script>

<style>
.container { 
  font-family: system-ui, sans-serif; 
  padding: 2rem; 
  max-width: 800px;
  margin: 0 auto;
}
.checking { color: #888; }
.connected { color: #10b981; font-weight: bold; }
.error { color: #ef4444; font-weight: bold; }
</style>
"""
}

def create_project_structure():
    for filepath, content in files_to_create.items():
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        # Write the file content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Created: {filepath}")

if __name__ == "__main__":
    print("Generating Step 1 project skeleton...")
    create_project_structure()
    print("Done! You can now delete this script if you wish.")