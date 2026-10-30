import os
import sys
import subprocess
import threading
import time
import zipfile
import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File
from ..config import BASE_DIR, UPDATE_SECRET_KEY

router = APIRouter(prefix="/api/system", tags=["CivMasterPro System Maintenance & Remote Updates"])

SYSTEM_VERSION = "2.4.0-CivMasterPro"
BRAND_NAME = "CivMasterPro"
CLIENT_NAME = "SV DREEAMPLANNERS PRIVATE LIMITED"

def delayed_restart(delay_seconds: int = 2):
    """Wait brief interval so HTTP response finishes sending, then restart runner loop."""
    time.sleep(delay_seconds)
    os._exit(0)

def get_git_status():
    """Retrieve git metadata if available."""
    git_info = {}
    try:
        commit_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5
        )
        if commit_res.returncode == 0:
            git_info["commit"] = commit_res.stdout.strip()

        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5
        )
        if branch_res.returncode == 0:
            git_info["branch"] = branch_res.stdout.strip()

        msg_res = subprocess.run(
            ["git", "log", "-1", "--format=%s (%cd)", "--date=relative"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5
        )
        if msg_res.returncode == 0:
            git_info["last_commit"] = msg_res.stdout.strip()

        remote_res = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5
        )
        if remote_res.returncode == 0 and remote_res.stdout.strip():
            git_info["remotes"] = remote_res.stdout.strip().splitlines()
        else:
            git_info["remotes"] = None
    except Exception as e:
        git_info["git_error"] = str(e)
    return git_info

@router.get("/status")
def get_system_status():
    """Return platform branding, system version, git info, and operational status."""
    git_info = get_git_status()
    return {
        "status": "online",
        "brand": BRAND_NAME,
        "platform": f"{BRAND_NAME} Enterprise Management Platform",
        "client": CLIENT_NAME,
        "service": f"{BRAND_NAME} HR & Biometric Management System",
        "version": SYSTEM_VERSION,
        "python_version": sys.version.split()[0],
        "domain": "https://svd.civmasterpro.com",
        "git": git_info if git_info else "No git repository initialized",
        "capabilities": {
            "remote_git_update": True,
            "direct_push_update_zip": True,
            "hot_restart": True
        }
    }

@router.post("/update")
def trigger_remote_update(
    token: str = Query(None),
    x_update_token: str = Header(None),
    install_deps: bool = Query(False),
    force_restart: bool = Query(False)
):
    """
    Pulls latest changes from Git remote and restarts server.
    If no remote origin is configured, reports instructions without crashing.
    """
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    git_info = get_git_status()
    has_remote = bool(git_info.get("remotes"))

    if not has_remote and not force_restart:
        return {
            "success": False,
            "brand": BRAND_NAME,
            "version": SYSTEM_VERSION,
            "message": "Git remote is not configured yet on this installation.",
            "hint": "Use POST /api/system/push-update with a ZIP payload, or configure git remote origin using /api/system/git-remote.",
            "git_status": git_info
        }

    try:
        output = ""
        pip_output = ""
        if has_remote:
            pull = subprocess.run(
                ["git", "pull"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=60
            )
            output = pull.stdout + pull.stderr

            if install_deps or "requirements.txt" in output:
                req_file = BASE_DIR / "requirements.txt"
                if req_file.exists():
                    pip_run = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                        cwd=str(BASE_DIR),
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    pip_output = pip_run.stdout

        # Restart runner
        threading.Thread(target=delayed_restart, daemon=True).start()

        return {
            "success": True,
            "brand": BRAND_NAME,
            "version": SYSTEM_VERSION,
            "message": "CivMasterPro update processed. Server is restarting in 2 seconds...",
            "git_output": output if output else "Forced restart executed",
            "pip_output": pip_output if pip_output else None
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git pull timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@router.post("/push-update")
async def push_system_update(
    file: UploadFile = File(...),
    token: str = Query(None),
    x_update_token: str = Header(None),
    install_deps: bool = Query(False)
):
    """
    Direct Push Update: Uploads and applies an update ZIP package to CivMasterPro.
    Automatically unpacks updated code, installs requirements if updated, and restarts.
    """
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip update archives are supported.")

    temp_zip = BASE_DIR / "temp_update.zip"
    try:
        with open(temp_zip, "wb") as f:
            content = await file.read()
            f.write(content)

        updated_files = []
        protected_prefixes = ("uploads/", "uploads\\", "logs/", "logs\\", ".git/", ".git\\", "generated_payslips/")

        with zipfile.ZipFile(temp_zip, "r") as z:
            for member in z.infolist():
                # Prevent path traversal
                target_path = (BASE_DIR / member.filename).resolve()
                if not str(target_path).startswith(str(BASE_DIR.resolve())):
                    continue
                # Skip protected user data paths
                if any(member.filename.replace("\\", "/").startswith(p) for p in protected_prefixes):
                    continue

                z.extract(member, BASE_DIR)
                if not member.is_dir():
                    updated_files.append(member.filename)

        if temp_zip.exists():
            temp_zip.unlink()

        pip_output = ""
        if install_deps or any("requirements.txt" in f for f in updated_files):
            req_file = BASE_DIR / "requirements.txt"
            if req_file.exists():
                pip_run = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                pip_output = pip_run.stdout

        # Trigger clean restart
        threading.Thread(target=delayed_restart, daemon=True).start()

        return {
            "success": True,
            "brand": BRAND_NAME,
            "version": SYSTEM_VERSION,
            "message": f"Successfully applied CivMasterPro push update ({len(updated_files)} files updated). Server restarting in 2 seconds...",
            "files_updated_count": len(updated_files),
            "pip_output": pip_output if pip_output else None
        }

    except Exception as e:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Push update failed: {str(e)}")

@router.post("/git-remote")
def configure_git_remote(
    remote_url: str = Query(...),
    remote_name: str = Query("origin"),
    token: str = Query(None),
    x_update_token: str = Header(None)
):
    """Configure or change the git remote repository URL for remote updates."""
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    try:
        # Check if remote already exists
        check = subprocess.run(["git", "remote"], cwd=str(BASE_DIR), capture_output=True, text=True)
        remotes = check.stdout.split()
        if remote_name in remotes:
            cmd = ["git", "remote", "set-url", remote_name, remote_url]
        else:
            cmd = ["git", "remote", "add", remote_name, remote_url]

        run = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10)
        if run.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Git remote error: {run.stderr}")

        return {
            "success": True,
            "brand": BRAND_NAME,
            "message": f"Git remote '{remote_name}' set to '{remote_url}' successfully.",
            "remotes": get_git_status().get("remotes")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure git remote: {str(e)}")

@router.post("/restart")
def trigger_remote_restart(
    token: str = Query(None),
    x_update_token: str = Header(None)
):
    """Cleanly restart the background server process."""
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    threading.Thread(target=delayed_restart, daemon=True).start()
    return {
        "success": True,
        "brand": BRAND_NAME,
        "message": "Restart signal accepted. CivMasterPro server restarting in 2 seconds..."
    }
