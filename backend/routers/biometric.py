from fastapi import APIRouter
from ..services.biometric_service import biometric_service
import threading

sync_route_lock = threading.Lock()

router = APIRouter(prefix="/api/biometric", tags=["Biometric Device"])

@router.get("/status")
def get_biometric_device_status():
    """Check connectivity and details of Device 2 (192.168.31.111:4370)"""
    return biometric_service.get_status()

@router.post("/sync")
def trigger_biometric_sync():
    """Trigger high-speed attendance sync from Device 2"""
    acquired = sync_route_lock.acquire(timeout=5)
    if not acquired:
        return {"success": False, "error": "Device sync is currently in progress, please retry in 5 seconds."}
    try:
        return biometric_service.sync_punches(recent_bytes=40000)
    finally:
        sync_route_lock.release()
