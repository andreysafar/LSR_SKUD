# LSR_SKUD Deployment Guide

This guide covers deployment of LSR_SKUD with integrated ANPR batch processing capabilities.

## Overview

LSR_SKUD can be deployed in multiple configurations:
- **Web Interface**: Streamlit dashboard for monitoring and control
- **Batch Processor**: High-performance video processing worker  
- **Combined**: Both web interface and batch processing

## Prerequisites

### System Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8GB
- Storage: 50GB free space
- OS: Linux (Ubuntu 20.04+ recommended)

**Recommended for Production:**
- CPU: 8+ cores  
- RAM: 16GB+
- GPU: NVIDIA GPU with 8GB+ VRAM (for batch processing)
- Storage: 100GB+ SSD
- Docker 20.10+
- Docker Compose 2.0+

### Software Dependencies

```bash
# Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# For Kubernetes deployment (optional)
kubectl
helm (optional)
```

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd LSR_SKUD
cp .env.example .env
```

### 2. Edit Configuration

Edit `.env` file with your settings:

```bash
# Required settings
ANPR_INPUT_DIRECTORIES=/mnt/iss_media/CAM_14,/mnt/iss_media/CAM_16
GPU_ENABLED=true
ANPR_CPU_WORKERS=8
ANPR_GPU_WORKERS=4
```

### 3. Deploy

```bash
# Quick deployment (CPU-only)
./deploy/deploy.sh production

# GPU-enabled deployment  
./deploy/deploy.sh production --gpu

# With monitoring stack
./deploy/deploy.sh production --gpu --monitoring
```

## Deployment Methods

### Docker Compose (Recommended for Single Server)

#### Basic Deployment
```bash
# Web interface only
./deploy/deploy.sh production --web-only

# Batch processing only
./deploy/deploy.sh production --batch-only --gpu

# Complete stack
./deploy/deploy.sh production --gpu --monitoring
```

#### Manual Docker Compose
```bash
# Build and start
docker-compose up -d

# With monitoring
docker-compose --profile monitoring up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Kubernetes (For Cluster Deployment)

#### Prerequisites
```bash
# Ensure kubectl is configured
kubectl cluster-info

# Create namespace
kubectl create namespace lsr-skud
```

#### Deploy
```bash
# Automatic deployment
./deploy/deploy.sh production

# Manual deployment
kubectl apply -f deploy/production.yaml

# Check status
kubectl get pods -n lsr-skud
kubectl logs -n lsr-skud -l app=lsr-skud -f
```

## Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
DB_PATH=data/gate_control.db

# ANPR Processing
ANPR_INPUT_DIRECTORIES=/path/to/video/directories
ANPR_CPU_WORKERS=8
ANPR_GPU_WORKERS=4
ANPR_FFMPEG_GPU_WORKERS=2
ANPR_VIDEO_EXTENSION=.issvd

# Performance
TORCHSCRIPT_ENABLED=true
HALF_PRECISION=true
GPU_ENABLED=true

# Output
ANPR_OUTPUT_CSV_PATH=data/plates.csv
ANPR_OUTPUT_IMAGES_DIR=data/snapshots
```

### Volume Mounts

Required volume mounts:

```yaml
volumes:
  # Persistent data
  - ./data:/app/data
  - ./models:/app/models
  
  # Video archive (read-only)
  - /mnt/video_archive:/mnt/video_archive:ro
  
  # Logs
  - ./batch_processing/logs:/app/batch_processing/logs
```

## Production Considerations

### Security

1. **Use non-root user in containers** (already configured)
2. **Set proper file permissions**:
   ```bash
   chmod 600 .env
   chown -R 1000:1000 data/
   ```

3. **Configure firewall**:
   ```bash
   # Only expose necessary ports
   ufw allow 8501  # Streamlit
   ufw enable
   ```

### Performance Optimization

#### GPU Configuration
```bash
# Install NVIDIA Docker runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list

apt-get update && apt-get install -y nvidia-docker2
systemctl restart docker
```

#### Storage Optimization
```bash
# Use SSD for models and database
mkdir -p /fast-storage/lsr-skud/{data,models}
ln -s /fast-storage/lsr-skud/data ./data
ln -s /fast-storage/lsr-skud/models ./models
```

### Monitoring

#### Built-in Monitoring
Access at `http://localhost:8501` → Analytics page

#### External Monitoring (Optional)
```bash
# Deploy with monitoring stack
./deploy/deploy.sh production --monitoring

# Access:
# Prometheus: http://localhost:9090  
# Grafana: http://localhost:3000 (admin/admin)
```

#### Log Management
```bash
# Container log rotation is configured
# View logs:
docker-compose logs -f lsr-skud

# Kubernetes logs:
kubectl logs -n lsr-skud -l app=lsr-skud -f
```

## Maintenance

### Updates

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
./deploy/deploy.sh production --gpu

# Or manual rebuild:
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Backup

```bash
# Backup data and models
tar -czf backup-$(date +%Y%m%d).tar.gz data/ models/

# Database backup
sqlite3 data/gate_control.db ".backup backup.db"
```

### Cleanup

```bash
# Clean old containers and images
docker system prune -a

# Clean application data (careful!)
rm -rf data/snapshots/*.jpg
rm -f data/plates.csv
```

## Troubleshooting

### Common Issues

#### GPU Not Detected
```bash
# Check GPU availability
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# Verify GPU in container
docker-compose exec lsr-skud python -c "import torch; print(torch.cuda.is_available())"
```

#### Out of Memory
```bash
# Reduce worker counts in .env
ANPR_CPU_WORKERS=4
ANPR_GPU_WORKERS=2

# Check memory usage
docker stats
```

#### Permission Issues
```bash
# Fix data directory permissions
sudo chown -R 1000:1000 data/
sudo chmod -R 755 data/
```

#### Model Loading Errors
```bash
# Download models manually
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt -P models/
```

### Logs

```bash
# Application logs
docker-compose logs -f lsr-skud

# Batch processing logs  
tail -f batch_processing/logs/process_videos.log

# System logs
journalctl -u docker -f
```

### Health Checks

```bash
# Check service health
curl http://localhost:8501/_stcore/health

# Check container status
docker-compose ps

# Check resource usage
docker stats
```

## Scaling

### Horizontal Scaling (Kubernetes)
```bash
# Scale web interface
kubectl scale deployment lsr-skud-app --replicas=3 -n lsr-skud

# Enable autoscaling (already configured)
kubectl get hpa -n lsr-skud
```

### Vertical Scaling
Update resource limits in configuration:

```yaml
resources:
  requests:
    memory: "4Gi"
    cpu: "2000m"
  limits:
    memory: "8Gi"
    cpu: "4000m"
```

## Support

For issues and questions:
1. Check logs for error messages
2. Review configuration in `.env`
3. Verify system requirements
4. Check GPU/CUDA installation (if using GPU)

## Security Notes

- Never commit `.env` file to version control
- Use secrets management in production
- Regular security updates for base images
- Monitor access logs
- Use HTTPS in production (configure reverse proxy)