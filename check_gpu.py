#!/usr/bin/env python3
"""
GPU and system diagnostics script.
Run with: python3 check_gpu.py
"""
import sys
import os
import platform

def check_system():
    """Check system information."""
    print("=" * 60)
    print("System Information")
    print("=" * 60)
    print(f"OS: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Machine: {platform.machine()}")
    print()

def check_torch():
    """Check PyTorch and CUDA."""
    print("=" * 60)
    print("PyTorch & CUDA Check")
    print("=" * 60)
    try:
        import torch
        print(f"✓ PyTorch version: {torch.__version__}")
        print(f"✓ CUDA available: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"✓ CUDA version: {torch.version.cuda}")
            print(f"✓ GPU count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  - GPU {i}: {torch.cuda.get_device_name(i)}")
            print(f"✓ Current GPU: {torch.cuda.current_device()}")
            print(f"✓ GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        else:
            print("⚠ CUDA is NOT available")
        print()
        return torch.cuda.is_available()
    except Exception as e:
        print(f"✗ Error checking PyTorch: {e}")
        return False

def check_nvidia_smi():
    """Check nvidia-smi if available."""
    print("=" * 60)
    print("NVIDIA GPU Status (nvidia-smi)")
    print("=" * 60)
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                print(f"✓ {line}")
            print()
            return True
        else:
            print("⚠ nvidia-smi not available or failed")
            print()
            return False
    except Exception as e:
        print(f"⚠ Cannot run nvidia-smi: {e}")
        print()
        return False

def check_opencv():
    """Check OpenCV."""
    print("=" * 60)
    print("OpenCV Check")
    print("=" * 60)
    try:
        import cv2
        print(f"✓ OpenCV version: {cv2.__version__}")
        print(f"✓ CUDA support: {cv2.cuda.getCudaEnabledDeviceCount() > 0 if hasattr(cv2, 'cuda') else 'Unknown'}")
        print()
    except Exception as e:
        print(f"✗ Error: {e}")
        print()

def check_ultralytics():
    """Check YOLOv8."""
    print("=" * 60)
    print("Ultralytics (YOLO) Check")
    print("=" * 60)
    try:
        from ultralytics import __version__ as yolo_version
        print(f"✓ Ultralytics version: {yolo_version}")
        print()
    except Exception as e:
        print(f"✗ Error: {e}")
        print()

def check_easyocr():
    """Check EasyOCR."""
    print("=" * 60)
    print("EasyOCR Check")
    print("=" * 60)
    try:
        import easyocr
        print(f"✓ EasyOCR available")
        print()
    except Exception as e:
        print(f"✗ Error: {e}")
        print()

def check_env_vars():
    """Check environment variables."""
    print("=" * 60)
    print("Environment Variables")
    print("=" * 60)
    vars_to_check = [
        'GPU_ENABLED',
        'DEVICE',
        'CUDA_VISIBLE_DEVICES',
        'NVIDIA_VISIBLE_DEVICES',
        'NVIDIA_DRIVER_CAPABILITIES',
        'PYTHONUNBUFFERED',
    ]
    for var in vars_to_check:
        val = os.environ.get(var, "NOT SET")
        print(f"{var}: {val}")
    print()

def test_gpu_compute(cuda_available):
    """Test basic GPU computation."""
    print("=" * 60)
    print("GPU Compute Test")
    print("=" * 60)
    
    if not cuda_available:
        print("⚠ GPU not available, skipping compute test")
        print()
        return
    
    try:
        import torch
        
        # Create tensors
        x = torch.randn(1000, 1000).cuda()
        y = torch.randn(1000, 1000).cuda()
        
        # Matrix multiplication
        import time
        start = time.time()
        for _ in range(10):
            z = torch.mm(x, y)
        elapsed = time.time() - start
        
        print(f"✓ Matrix multiplication test passed")
        print(f"  10x (1000x1000) matrix mult: {elapsed:.3f}s")
        print()
    except Exception as e:
        print(f"✗ Compute test failed: {e}")
        print()

def main():
    """Run all checks."""
    print("\n" + "=" * 60)
    print("LSR_SKUD GPU & System Diagnostics")
    print("=" * 60 + "\n")
    
    check_system()
    cuda_available = check_torch()
    check_nvidia_smi()
    check_opencv()
    check_ultralytics()
    check_easyocr()
    check_env_vars()
    test_gpu_compute(cuda_available)
    
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    if cuda_available:
        print("✓ System ready for GPU acceleration")
    else:
        print("⚠ GPU not available - system will run on CPU")
    print()

if __name__ == "__main__":
    main()
