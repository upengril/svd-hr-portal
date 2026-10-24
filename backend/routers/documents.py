import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..db import get_db
from ..config import DOCUMENT_DIR

router = APIRouter(prefix="/api/documents", tags=["Document Control"])

class VerifyDocumentSchema(BaseModel):
    verification_status: str # VERIFIED, REJECTED
    verification_remarks: Optional[str] = ""

@router.post("/upload/{employee_id}")
async def upload_employee_document(
    employee_id: str,
    document_type: str = Form(...),
    document_title: str = Form(...),
    file: UploadFile = File(...)
):
    with get_db() as cur:
        cur.execute("SELECT id, employee_code FROM hr_employees WHERE id = %s;", (employee_id,))
        emp = cur.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Sanitize filename & save
        ext = Path(file.filename).suffix
        safe_name = f"{emp['employee_code']}_{document_type}_{int(datetime.now().timestamp())}{ext}"
        target_path = os.path.join(DOCUMENT_DIR, safe_name)

        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(target_path)
        mime_type = file.content_type or "application/octet-stream"

        cur.execute("""
            INSERT INTO hr_documents (
                employee_id, document_type, document_title, file_path, file_name, file_size, mime_type, verification_status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'PENDING'
            ) RETURNING id;
        """, (employee_id, document_type, document_title, target_path, safe_name, file_size, mime_type))
        doc_id = cur.fetchone()["id"]

    return {
        "success": True,
        "id": doc_id,
        "file_name": safe_name,
        "message": f"Document '{document_title}' uploaded successfully"
    }

@router.get("/{document_id}/download")
def download_document(document_id: str):
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_documents WHERE id = %s;", (document_id,))
        doc = cur.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File on disk missing")

    return FileResponse(
        path=file_path,
        filename=doc["file_name"],
        media_type=doc["mime_type"] or "application/octet-stream"
    )

@router.put("/{document_id}/verify")
def verify_document(document_id: str, data: VerifyDocumentSchema):
    with get_db() as cur:
        cur.execute("""
            UPDATE hr_documents SET
                verification_status = %s,
                verification_remarks = %s,
                verified_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """, (data.verification_status.upper(), data.verification_remarks, document_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

    return {
        "success": True,
        "message": f"Document status updated to {data.verification_status.upper()}"
    }

@router.delete("/{document_id}")
def delete_document(document_id: str):
    with get_db() as cur:
        cur.execute("SELECT file_path FROM hr_documents WHERE id = %s;", (document_id,))
        doc = cur.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        cur.execute("DELETE FROM hr_documents WHERE id = %s;", (document_id,))

    # Remove file from disk
    if os.path.exists(doc["file_path"]):
        try:
            os.remove(doc["file_path"])
        except Exception:
            pass

    return {"success": True, "message": "Document deleted"}
