# Multi-stage Docker build for LSR_SKUD with ANPR integration
FROM python:3.12-slim AS base

# Proxy support (pass via --build-arg from host; used by apt-get and pip during build)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Core system tools
    curl \
    wget \
    git \
    # Video processing
    ffmpeg \
    mediainfo \
    # OpenCV dependencies
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # OpenGL for OpenCV/ML (libgl1-mesa-glx obsoleted in Debian Trixie; use libgl1)
    libgl1 \
    libglib2.0-0 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


# Development stage
FROM base AS development

# Install development tools
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
RUN pip install uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (including dev dependencies)
RUN uv sync --all-extras --frozen

# Copy source code
COPY . .

# Create necessary directories
RUN mkdir -p data/snapshots \
    models \
    batch_processing/logs \
    tests/outputs

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]


# Production stage
FROM base AS production

# Unset proxy so runtime uses it only where explicitly set (e.g. Telegram bot); build used proxy in base.
ENV http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

# Create non-root user for security (home and .cache so uv can write)
RUN groupadd -r lsrskud && useradd -r -g lsrskud -d /home/lsrskud lsrskud \
    && mkdir -p /home/lsrskud/.cache \
    && chmod 777 /home/lsrskud/.cache \
    && chown -R lsrskud:lsrskud /home/lsrskud
ENV HOME=/home/lsrskud

# Install UV
RUN pip install uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install only production dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY --chown=lsrskud:lsrskud . .

# Create necessary directories; .cache world-writable so any user (e.g. host UID) can run uv
RUN mkdir -p data/snapshots \
    models \
    batch_processing/logs \
    /app/.cache \
    && chown -R lsrskud:lsrskud /app \
    && chmod 777 /app/.cache

# Switch to non-root user
USER lsrskud

ENV UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command
CMD [".venv/bin/python", "main.py"]


# GPU-enabled production stage
FROM production AS gpu-production

# Switch back to root for GPU driver installation
USER root

# Install NVIDIA container toolkit dependencies (software-properties-common removed in Debian Trixie)
RUN apt-get update && apt-get install -y \
    gnupg2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install CUDA runtime (if needed)
# Note: This would require NVIDIA base image in real deployment
# FROM nvidia/cuda:11.8-runtime-ubuntu20.04 as gpu-base

# Switch back to app user
USER lsrskud

# Set GPU-specific environment variables
ENV GPU_ENABLED=true \
    CUDA_VISIBLE_DEVICES=all

# Labels for image metadata
LABEL maintainer="LSR_SKUD Team" \
      version="1.0.0" \
      description="LSR_SKUD with ANPR batch processing integration" \
      gpu.enabled="true"


# Batch processing worker stage
FROM production AS batch-worker

# This stage is optimized for batch processing workloads
USER root

# Install additional tools for batch processing
RUN apt-get update && apt-get install -y \
    htop \
    iotop \
    && rm -rf /var/lib/apt/lists/*

USER lsrskud

# Set batch processing environment
ENV ANPR_CPU_WORKERS=4 \
    ANPR_GPU_WORKERS=2 \
    ANPR_FFMPEG_GPU_WORKERS=1 \
    TORCHSCRIPT_ENABLED=true \
    HALF_PRECISION=true

# Override CMD for batch processing
CMD ["uv", "run", "python", "-m", "batch_processing.batch_processor", "start"]