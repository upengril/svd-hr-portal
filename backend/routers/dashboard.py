from fastapi import APIRouter
from datetime import datetime, date
from ..db import get_db
from ..services.biometric_service import biometric_service
from ..config import COMPANY_INFO

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary")
def get_dashboard_summary():
    today_str = datetime.now().strftime("%Y-%m-%d")

    with get_db() as cur:
        # Total Staff Count
        cur.execute("SELECT COUNT(*) as total FROM hr_employees WHERE status = 'ACTIVE';")
        total_employees = cur.fetchone()["total"]

        # Today's Attendance Breakdown
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('PRESENT', 'HALF_DAY', 'LATE')) as present_count,
                COUNT(*) FILTER (WHERE status = 'LATE') as late_count,
                COUNT(*) FILTER (WHERE status = 'HALF_DAY') as half_day_count,
                COUNT(*) FILTER (WHERE overtime_minutes > 0) as overtime_count
            FROM hr_attendance_daily
            WHERE attendance_date = %s;
        """, (today_str,))
        att_stats = cur.fetchone()

        present_count = att_stats["present_count"] or 0
        late_count = att_stats["late_count"] or 0
        half_day_count = att_stats["half_day_count"] or 0
        overtime_count = att_stats["overtime_count"] or 0
        absent_count = max(0, total_employees - present_count)

        # Recent Punches Feed (Last 15 punches today)
        cur.execute("""
            SELECT 
                p.id,
                p.biometric_id,
                p.punch_time,
                p.punch_state,
                p.verify_type,
                COALESCE(e.display_name, 'Staff-' || p.biometric_id) as employee_name,
                COALESCE(e.employee_code, 'SVD-' || LPAD(p.biometric_id::text, 4, '0')) as employee_code,
                e.department,
                e.designation
            FROM hr_biometric_punches p
            LEFT JOIN hr_employees e ON p.employee_id = e.id
            ORDER BY p.punch_time DESC
            LIMIT 15;
        """)
        recent_punches = cur.fetchall()

        # Department Distribution
        cur.execute("""
            SELECT department, COUNT(*) as count
            FROM hr_employees
            WHERE status = 'ACTIVE'
            GROUP BY department
            ORDER BY count DESC;
        """)
        departments = cur.fetchall()

    return {
        "company": COMPANY_INFO,
        "date": today_str,
        "metrics": {
            "total_employees": total_employees,
            "present_today": present_count,
            "absent_today": absent_count,
            "late_today": late_count,
            "half_day_today": half_day_count,
            "overtime_today": overtime_count
        },
        "device": {
            "ip": "192.168.31.111",
            "port": 4370,
            "model": "x 2008 (ZKTeco)",
            "serial": "TFDB244500349",
            "status": "ONLINE"
        },
        "recent_punches": recent_punches,
        "departments": departments
    }
