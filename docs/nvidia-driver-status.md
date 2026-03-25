# NVIDIA driver status and root cause (2026-03-04)

## Current state after reboot

- **nvidia-smi**: "No devices were found"
- **GPU**: NVIDIA RTX A5000 (GA102GL), visible in `lspci`
- **Driver**: proprietary `nvidia-driver-570` (570.211.01), packages installed
- **Kernel**: 6.8.0-101-generic
- **Config**: `nvidia-drm.modeset=0` (was set to fix earlier KMS error)

## What actually broke (root cause)

After reboot, `dmesg` shows the real error:

```text
NVRM: GPU 0000:0b:00.0: RmInitAdapter failed! (0x62:0x65:2522)
NVRM: GPU 0000:0b:00.0: rm_init_adapter failed, device minor number 0
```

So the failure is **RmInitAdapter**: the driver loads, but the GPU adapter (and GSP firmware path) never finishes initialising. Error code `0x65` is usually a timeout. Because of that, the GPU is never registered with the Resource Manager, and **nvidia-smi** correctly reports "No devices were found".

## Timeline of issues

1. **With `nvidia-drm.modeset=1` (default)**  
   - `[drm] *ERROR* Failed to allocate NvKmsKapiDevice`  
   - `[drm] *ERROR* Failed to register device`  
   - So with KMS on, nvidia-drm failed during load and the device was not registered.

2. **After setting `nvidia-drm.modeset=0` and rebooting**  
   - Those DRM errors are gone; `nvidia-drm` initialises.  
   - But **RmInitAdapter** still fails (see above).  
   - So the problem is not only KMS, but adapter/GSP init (and possibly kernel/driver/firmware interaction).

## APT proxy

- File **`/etc/apt/apt.conf.d/80proxy`** created with proxy `http://10.10.1.122:3128/` (same as in `.env`).  
- Existing `00proxy` / `proxy.conf` also set a proxy; having one consolidated file in `80proxy` is enough for apt to use the proxy.

## Recommended next steps

1. **Try open kernel modules (recommended first)**  
   - Install: `sudo apt install nvidia-driver-570-open`  
   - Remove proprietary meta: `sudo apt remove nvidia-driver-570` (leave libs like `libnvidia-compute-570` if pulled by -open).  
   - Reboot and check `nvidia-smi` and `dmesg` for RmInitAdapter.

2. **If still failing, try older kernel**  
   - In GRUB choose **6.8.0-85-generic** (already present).  
   - Some reports mention "RmInitAdapter failed since kernel > 6.4"; older kernel may avoid the failure.

3. **If open driver is not desired**  
   - Ensure latest 570 updates: `sudo apt update && sudo apt install --only-upgrade nvidia-driver-570 nvidia-dkms-570`  
   - Check for newer driver/firmware in Ubuntu updates or NVIDIA repo.

## Commands used for diagnostics

```bash
nvidia-smi
lspci | grep -i nvidia
sudo dmesg | grep -i nvidia
ls -la /dev/nvidia*
cat /proc/driver/nvidia/version
dpkg -l | grep nvidia
```
