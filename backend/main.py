import os
import threading
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import UPLOAD_DIR, PAYSLIP_DIR, BASE_DIR
from .db import init_db_pool
from .services.biometric_service import biometric_service
from .routers import (
    dashboard, employees, attendance, documents, leaves, payroll, biometric, system_update, attendance_policy
)

app = FastAPI(
    title="CivMasterPro – HR & Biometric Management System",
    description="Enterprise Web HR Portal with Biometric Device 2 Integration, Document Control, Attendance, and Payroll for SV DREEAMPLANNERS PVT LTD (CivMasterPro Platform)",
    version="2.4.0"
)

# Enable CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sync_worker_running = True

def continuous_biometric_sync_worker():
    """Background worker that pulls latest punches from Device 2 every 30 seconds"""
    print("[*] High-Speed Biometric Sync Worker started (runs every 30s in < 1 second).", flush=True)
    time.sleep(5)
    while sync_worker_running:
        try:
            if biometric_service.lock.acquire(blocking=False):
                try:
                    res = biometric_service.sync_punches()
                    if res.get("success") and res.get("new_punches_synced", 0) > 0:
                        print(f"[{time.strftime('%H:%M:%S')}] [+] Synced {res.get('new_punches_synced')} new punches in {res.get('pull_time_seconds')}s!", flush=True)
                finally:
                    biometric_service.lock.release()
        except Exception as e:
            print(f"[-] Auto-sync worker notice: {e}", flush=True)

        for _ in range(30):
            if not sync_worker_running:
                break
            time.sleep(1)

@app.on_event("startup")
def on_startup():
    init_db_pool()
    print("SVD HR Portal Backend initialized with PostgreSQL connection pool.")
    
    # Start the continuous background sync thread
    t = threading.Thread(target=continuous_biometric_sync_worker, daemon=True)
    t.start()

@app.on_event("shutdown")
def on_shutdown():
    global sync_worker_running
    sync_worker_running = False

# Include API Routers
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(documents.router)
app.include_router(leaves.router)
app.include_router(payroll.router)
app.include_router(biometric.router)
app.include_router(attendance_policy.router)
app.include_router(system_update.router)

# Mount static folders
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/payslips", StaticFiles(directory=str(PAYSLIP_DIR)), name="payslips")

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "CivMasterPro HR Portal API is running. Visit /docs for Swagger API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=5000, reload=True)
