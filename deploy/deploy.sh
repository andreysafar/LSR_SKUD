#!/bin/bash

# LSR_SKUD Deployment Script
# This script handles deployment to various environments

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_ENV="${1:-production}"
NAMESPACE="lsr-skud"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "Environments:"
    echo "  production    Deploy to production (default)"
    echo "  staging       Deploy to staging"
    echo "  development   Deploy to development"
    echo ""
    echo "Options:"
    echo "  --gpu         Enable GPU deployment"
    echo "  --monitoring  Enable monitoring stack"
    echo "  --batch-only  Deploy batch processing only"
    echo "  --web-only    Deploy web interface only"
    echo "  --dry-run     Show what would be deployed without actually deploying"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 production --gpu --monitoring"
    echo "  $0 staging --batch-only"
    echo "  $0 development --dry-run"
}

# Parse arguments
GPU_ENABLED=false
MONITORING_ENABLED=false
BATCH_ONLY=false
WEB_ONLY=false
DRY_RUN=false

while [[ $# -gt 1 ]]; do
    case $2 in
        --gpu)
            GPU_ENABLED=true
            shift
            ;;
        --monitoring)
            MONITORING_ENABLED=true
            shift
            ;;
        --batch-only)
            BATCH_ONLY=true
            shift
            ;;
        --web-only)
            WEB_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $2"
            show_help
            exit 1
            ;;
    esac
done

# Check for help
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_help
    exit 0
fi

# Validation
if [[ "$BATCH_ONLY" == "true" && "$WEB_ONLY" == "true" ]]; then
    log_error "Cannot use --batch-only and --web-only together"
    exit 1
fi

log_info "Starting LSR_SKUD deployment to $DEPLOYMENT_ENV environment"

# Check if running in Docker deployment or Kubernetes
DEPLOYMENT_TYPE="docker"
if command -v kubectl &> /dev/null; then
    if kubectl cluster-info &> /dev/null; then
        DEPLOYMENT_TYPE="kubernetes"
        log_info "Detected Kubernetes environment"
    else
        log_warning "kubectl found but not connected to cluster, using Docker deployment"
    fi
else
    log_info "Using Docker Compose deployment"
fi

# Pre-deployment checks
check_prerequisites() {
    log_info "Checking deployment prerequisites..."
    
    # Check if environment file exists
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
            log_warning "No .env file found. Creating from .env.example"
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            log_warning "Please edit .env file with your configuration before continuing"
            exit 1
        else
            log_error ".env file not found and no .env.example to copy from"
            exit 1
        fi
    fi
    
    # Check required directories
    mkdir -p "$PROJECT_ROOT/data/snapshots"
    mkdir -p "$PROJECT_ROOT/models"
    mkdir -p "$PROJECT_ROOT/batch_processing/logs"
    
    # Check if models exist
    if [[ ! -f "$PROJECT_ROOT/models/yolov8n.pt" ]]; then
        log_warning "YOLO model not found at models/yolov8n.pt"
        log_info "Models will be downloaded on first run"
    fi
    
    if [[ ! -f "$PROJECT_ROOT/models/license_plate_detector.pt" ]]; then
        log_warning "License plate detector model not found"
        log_info "Please ensure models are available before starting processing"
    fi
    
    log_success "Prerequisites check completed"
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_ROOT"
    
    if [[ "$GPU_ENABLED" == "true" ]]; then
        log_info "Building GPU-enabled image..."
        if [[ "$DRY_RUN" == "false" ]]; then
            docker build --target gpu-production -t lsr-skud:gpu-latest .
        fi
    else
        log_info "Building CPU-only image..."
        if [[ "$DRY_RUN" == "false" ]]; then
            docker build --target production -t lsr-skud:latest .
        fi
    fi
    
    # Build batch worker image
    log_info "Building batch worker image..."
    if [[ "$DRY_RUN" == "false" ]]; then
        docker build --target batch-worker -t lsr-skud:batch-worker .
    fi
    
    log_success "Docker images built successfully"
}

# Docker Compose deployment
deploy_docker() {
    log_info "Deploying with Docker Compose..."
    
    cd "$PROJECT_ROOT"
    
    # Prepare compose command
    COMPOSE_CMD="docker-compose"
    COMPOSE_FILE="docker-compose.yml"
    
    # Add profiles based on options
    PROFILES=""
    if [[ "$MONITORING_ENABLED" == "true" ]]; then
        PROFILES="--profile monitoring"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Dry run - would execute: $COMPOSE_CMD -f $COMPOSE_FILE $PROFILES up -d"
        return
    fi
    
    # Stop existing containers
    log_info "Stopping existing containers..."
    $COMPOSE_CMD down
    
    # Start services based on deployment type
    if [[ "$WEB_ONLY" == "true" ]]; then
        log_info "Starting web interface only..."
        if [[ "$GPU_ENABLED" == "true" ]]; then
            $COMPOSE_CMD up -d lsr-skud-gpu
        else
            $COMPOSE_CMD up -d lsr-skud
        fi
    elif [[ "$BATCH_ONLY" == "true" ]]; then
        log_info "Starting batch processor only..."
        $COMPOSE_CMD up -d batch-worker
    else
        log_info "Starting all services..."
        $COMPOSE_CMD $PROFILES up -d
    fi
    
    # Wait for services to be healthy
    log_info "Waiting for services to become healthy..."
    sleep 30
    
    # Check service status
    if [[ "$WEB_ONLY" != "true" && "$BATCH_ONLY" != "true" ]]; then
        check_service_health
    fi
    
    log_success "Docker deployment completed"
}

# Kubernetes deployment
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Dry run - would apply Kubernetes manifests"
        kubectl apply -f "$SCRIPT_DIR/production.yaml" --dry-run=client
        return
    fi
    
    # Create namespace if it doesn't exist
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply base configuration
    kubectl apply -f "$SCRIPT_DIR/production.yaml"
    
    # Wait for deployment to be ready
    log_info "Waiting for deployment to be ready..."
    kubectl rollout status deployment/lsr-skud-app -n "$NAMESPACE" --timeout=300s
    
    # Start batch processing job if not web-only
    if [[ "$WEB_ONLY" != "true" ]]; then
        log_info "Creating batch processing job..."
        kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: lsr-skud-batch-$(date +%s)
  namespace: $NAMESPACE
  labels:
    app: lsr-skud
    component: batch-processor
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: batch-processor
        image: lsr-skud:batch-worker
        envFrom:
        - configMapRef:
            name: lsr-skud-config
EOF
    fi
    
    log_success "Kubernetes deployment completed"
    
    # Show access information
    show_access_info_k8s
}

# Check service health
check_service_health() {
    log_info "Checking service health..."
    
    # Check web interface
    if command -v curl &> /dev/null; then
        if curl -f http://localhost:8501/_stcore/health &> /dev/null; then
            log_success "Web interface is healthy"
        else
            log_warning "Web interface health check failed"
        fi
    else
        log_info "curl not available, skipping health check"
    fi
    
    # Check if containers are running
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "lsr-skud"; then
        log_success "LSR_SKUD containers are running"
    else
        log_error "LSR_SKUD containers not found"
    fi
}

# Show access information for Docker deployment
show_access_info_docker() {
    log_success "Deployment completed successfully!"
    echo ""
    echo "Access Information:"
    echo "  Web Interface: http://localhost:8501"
    echo "  Logs: docker-compose logs -f lsr-skud"
    echo "  Status: docker-compose ps"
    echo ""
    echo "Management Commands:"
    echo "  Stop services: docker-compose down"
    echo "  View logs: docker-compose logs -f"
    echo "  Restart: docker-compose restart"
    
    if [[ "$MONITORING_ENABLED" == "true" ]]; then
        echo ""
        echo "Monitoring:"
        echo "  Prometheus: http://localhost:9090"
        echo "  Grafana: http://localhost:3000 (admin/admin)"
    fi
}

# Show access information for Kubernetes deployment  
show_access_info_k8s() {
    log_success "Deployment completed successfully!"
    echo ""
    echo "Access Information:"
    echo "  External URL: https://lsr-skud.example.com"
    echo "  Port Forward: kubectl port-forward -n $NAMESPACE svc/lsr-skud-service 8501:8501"
    echo ""
    echo "Management Commands:"
    echo "  View pods: kubectl get pods -n $NAMESPACE"
    echo "  View logs: kubectl logs -n $NAMESPACE -l app=lsr-skud -f"
    echo "  Scale: kubectl scale -n $NAMESPACE deployment/lsr-skud-app --replicas=3"
}

# Main deployment function
main() {
    log_info "LSR_SKUD Deployment Script"
    log_info "Environment: $DEPLOYMENT_ENV"
    log_info "GPU Enabled: $GPU_ENABLED"
    log_info "Monitoring: $MONITORING_ENABLED"
    log_info "Batch Only: $BATCH_ONLY"
    log_info "Web Only: $WEB_ONLY"
    log_info "Dry Run: $DRY_RUN"
    echo ""
    
    # Run pre-deployment checks
    check_prerequisites
    
    # Build images
    build_images
    
    # Deploy based on environment
    if [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        deploy_kubernetes
    else
        deploy_docker
        show_access_info_docker
    fi
    
    log_success "LSR_SKUD deployment to $DEPLOYMENT_ENV completed successfully!"
}

# Run main function
main "$@"