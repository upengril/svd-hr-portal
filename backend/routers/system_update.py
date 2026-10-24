import os
import sys
import subprocess
import threading
import time
from fastapi import APIRouter, HTTPException, Query, Header
from ..config import BASE_DIR, UPDATE_SECRET_KEY

router = APIRouter(prefix="/api/system", tags=["System Maintenance & Remote Updates"])

def delayed_restart():
    """Wait 2 seconds so the HTTP response is delivered to the client, then cleanly exit."""
    time.sleep(2)
    # Process exit triggers the auto-restarting runner loop in run_server.bat
    os._exit(0)

@router.get("/status")
def get_system_status():
    """Return system version, branch, and current commit info."""
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
    except Exception as e:
        git_info["git_error"] = str(e)

    return {
        "status": "online",
        "service": "SV DREEAMPLANNERS HR Portal",
        "python_version": sys.version.split()[0],
        "git": git_info if git_info else "No git repository initialized yet"
    }

@router.post("/update")
def trigger_remote_update(
    token: str = Query(None),
    x_update_token: str = Header(None),
    install_deps: bool = Query(False)
):
    """
    Pulls latest changes from Git remote and restarts the background server process.
    Requires the secret UPDATE_SECRET_KEY.
    """
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    try:
        # Run git pull
        pull = subprocess.run(
            ["git", "pull"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=60
        )
        output = pull.stdout + pull.stderr

        # If pip install requested or requirements file changed
        pip_output = ""
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

        # Trigger background restart
        threading.Thread(target=delayed_restart, daemon=True).start()

        return {
            "success": True,
            "message": "Update pulled successfully. Portal is restarting in 2 seconds...",
            "git_output": output,
            "pip_output": pip_output if pip_output else None
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git pull timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@router.post("/restart")
def trigger_remote_restart(
    token: str = Query(None),
    x_update_token: str = Header(None)
):
    """Cleanly restart the background server process without pulling git changes."""
    provided = token or x_update_token
    if not provided or provided != UPDATE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing update token.")

    threading.Thread(target=delayed_restart, daemon=True).start()
    return {
        "success": True,
        "message": "Restart signal received. Server restarting in 2 seconds..."
    }
