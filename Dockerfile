# OMS360: one container that builds the React UI and serves it plus /api from FastAPI.
#   docker build -t oms360 .
#   docker run -p 8000:8000 -v oms360-data:/data oms360

# --- Stage 1: build the frontend ---
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# --- Stage 2: run the backend ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMS360_DB=/data/oms360.sqlite \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
# main.py looks for the UI at <repo>/frontend/dist
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN mkdir -p /data
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
