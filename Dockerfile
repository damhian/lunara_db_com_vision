# Stage 1: Builder for dependencies
FROM python:3.12.8-slim AS builder

# Install system dependencies including FFmpeg and build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-extra \
    curl \
    iputils-ping \
    netcat-openbsd \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12.8-slim

# Install runtime dependencies (FFmpeg with full codec support)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-extra \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy from builder
COPY --from=builder /opt/venv /opt/venv
COPY . .

# Environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:5001/hello || exit 1

EXPOSE 5001

# Run with Gunicorn for production
# CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--threads", "2", "--timeout", "120", "run:app"]