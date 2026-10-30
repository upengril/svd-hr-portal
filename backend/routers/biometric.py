from fastapi import APIRouter, Query
from ..services.biometric_service import biometric_service
from typing import Optional

router = APIRouter(prefix="/api/biometric", tags=["Biometric Device"])

@router.get("/status")
def get_biometric_device_status():
    """Check connectivity and details of Device 2 (192.168.31.111:4370)"""
    return biometric_service.get_status()

@router.post("/sync")
def trigger_biometric_sync(
    deep: bool = Query(False, description="Perform deep sync from Device 2"),
    recent_bytes: Optional[int] = Query(None, description="Explicit byte buffer to pull")
):
    """Trigger adaptive biometric attendance sync from Device 2"""
    acquired = biometric_service.lock.acquire(timeout=6)
    if not acquired:
        return {"success": False, "error": "Device sync is currently in progress, please retry in 5 seconds."}
    try:
        return biometric_service.sync_punches(recent_bytes=recent_bytes, deep=deep)
    finally:
        biometric_service.lock.release()
