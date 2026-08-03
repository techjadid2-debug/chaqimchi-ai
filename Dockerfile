# Multi-stage build for efficiency
FROM python:3.12-slim AS builder

WORKDIR /app

# System dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# System dependencies for OpenCV.
# Diqqat: libgl1-mesa-glx Debian 12 (bookworm) da yo'q — o'rnini libgl1 egallagan.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CHAQIMCHI_CONFIG=/app/config/config.yaml

# Expose port
EXPOSE 8742

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8742/health', timeout=4).status == 200 else 1)"

# Start command (using uvicorn as production server).
# --workers 1 majburiy: metrics, WebSocket ro'yxati va rate limiter jarayon ichida saqlanadi.
CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8742", "--workers", "1"]
