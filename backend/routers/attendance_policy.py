from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from ..db import get_db

router = APIRouter(prefix="/api/attendance/policy", tags=["Attendance & Overtime Policy"])

class PolicyUpdateSchema(BaseModel):
    policy_name: Optional[str] = "Standard Attendance Policy"
    is_overtime_enabled: bool = True
    overtime_threshold_hours: float = 8.00
    overtime_min_minutes: int = 30
    single_punch_treatment: str = "PRESENT"  # "PRESENT", "HALF_DAY", "ABSENT"
    single_punch_default_hours: float = 8.00
    is_half_day_enabled: bool = True
    half_day_threshold_hours: float = 4.00
    full_day_threshold_hours: float = 7.50
    grace_period_mins: int = 15
    late_penalty_enabled: bool = False
    recalculate_after_save: bool = True
    recalculate_scope: Optional[str] = "MONTH"  # "MONTH", "YEAR", "NONE"

class RecalculateRequest(BaseModel):
    start_date: str
    end_date: str

class RegularizeRequest(BaseModel):
    attendance_date: str
    action: str  # "SET_OUT_TIME", "MARK_FULL_DAY", "MARK_HALF_DAY"
    out_time: Optional[str] = "18:00:00"
    employee_ids: Optional[List[str]] = None

def execute_recalculate_query(cur, start_date: str, end_date: str, policy: dict):
    cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
    sh_row = cur.fetchone()
    shift_id = sh_row["id"] if sh_row else None

    ot_enabled = policy.get("is_overtime_enabled", True)
    ot_thresh_mins = int(float(policy.get("overtime_threshold_hours", 8.0)) * 60)
    ot_min_mins = int(policy.get("overtime_min_minutes", 30))
    single_treatment = policy.get("single_punch_treatment", "PRESENT")
    single_work_mins = int(float(policy.get("single_punch_default_hours", 8.0)) * 60)
    hd_enabled = policy.get("is_half_day_enabled", True)
    hd_thresh_mins = int(float(policy.get("half_day_threshold_hours", 4.0)) * 60)
    fd_thresh_mins = int(float(policy.get("full_day_threshold_hours", 7.5)) * 60)
    grace_mins = int(policy.get("grace_period_mins", 15))

    recalc_sql = """
        INSERT INTO hr_attendance_daily (
            employee_id, attendance_date, shift_id, punch_in, punch_out,
            total_work_minutes, overtime_minutes, late_minutes, status
        )
        SELECT 
            p.employee_id,
            DATE(p.punch_time) as att_date,
            %s as shift_id,
            MIN(p.punch_time) as punch_in,
            MAX(p.punch_time) as punch_out,
            -- Total work minutes
            CASE 
                WHEN MIN(p.punch_time) = MAX(p.punch_time) THEN 
                    CASE WHEN %s = 'ABSENT' THEN 0 ELSE %s END
                ELSE ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer
            END as total_work_minutes,
            -- Overtime minutes
            CASE 
                WHEN %s IS TRUE AND COALESCE(e.is_overtime_eligible, TRUE) IS TRUE AND MIN(p.punch_time) < MAX(p.punch_time) THEN
                    CASE 
                        WHEN ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer - %s >= %s
                        THEN ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer - %s
                        ELSE 0
                    END
                ELSE 0
            END as overtime_minutes,
            -- Late minutes
            CASE 
                WHEN MIN(p.punch_time)::time > ('09:00:00'::time + (%s || ' minutes')::interval)
                THEN ROUND(EXTRACT(EPOCH FROM (MIN(p.punch_time)::time - '09:00:00'::time)) / 60)::integer
                ELSE 0
            END as late_minutes,
            -- Status
            CASE 
                WHEN MIN(p.punch_time) = MAX(p.punch_time) THEN %s
                WHEN %s IS TRUE THEN
                    CASE 
                        WHEN ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer >= %s THEN 'PRESENT'
                        WHEN ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer >= %s THEN 'HALF_DAY'
                        ELSE 'ABSENT'
                    END
                ELSE
                    CASE 
                        WHEN ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer >= %s THEN 'PRESENT'
                        ELSE 'ABSENT'
                    END
            END as status
        FROM hr_biometric_punches p
        JOIN hr_employees e ON p.employee_id = e.id
        WHERE p.employee_id IS NOT NULL AND DATE(p.punch_time) >= %s AND DATE(p.punch_time) <= %s
        GROUP BY p.employee_id, DATE(p.punch_time), e.is_overtime_eligible
        ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
            punch_in = EXCLUDED.punch_in,
            punch_out = EXCLUDED.punch_out,
            total_work_minutes = EXCLUDED.total_work_minutes,
            overtime_minutes = EXCLUDED.overtime_minutes,
            late_minutes = EXCLUDED.late_minutes,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP
        WHERE hr_attendance_daily.is_manual_override IS NOT TRUE;
    """

    cur.execute(recalc_sql, (
        shift_id,
        single_treatment, single_work_mins,
        ot_enabled, ot_thresh_mins, ot_min_mins, ot_thresh_mins,
        grace_mins,
        single_treatment,
        hd_enabled, fd_thresh_mins, hd_thresh_mins,
        hd_thresh_mins,
        start_date, end_date
    ))

@router.get("")
def get_attendance_policy():
    """Retrieve active Attendance & Overtime Rules Policy"""
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_attendance_policy LIMIT 1;")
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Attendance policy not initialized.")
        return dict(row)

@router.post("")
def update_attendance_policy(data: PolicyUpdateSchema):
    """Save policy changes and optionally trigger instant recalculation"""
    with get_db() as cur:
        cur.execute("""
            UPDATE hr_attendance_policy SET
                policy_name = %s,
                is_overtime_enabled = %s,
                overtime_threshold_hours = %s,
                overtime_min_minutes = %s,
                single_punch_treatment = %s,
                single_punch_default_hours = %s,
                is_half_day_enabled = %s,
                half_day_threshold_hours = %s,
                full_day_threshold_hours = %s,
                grace_period_mins = %s,
                late_penalty_enabled = %s,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *;
        """, (
            data.policy_name,
            data.is_overtime_enabled,
            data.overtime_threshold_hours,
            data.overtime_min_minutes,
            data.single_punch_treatment,
            data.single_punch_default_hours,
            data.is_half_day_enabled,
            data.half_day_threshold_hours,
            data.full_day_threshold_hours,
            data.grace_period_mins,
            data.late_penalty_enabled
        ))
        updated_policy = dict(cur.fetchone())

        recalculated_message = "Settings saved successfully."
        if data.recalculate_after_save:
            now = datetime.now()
            if data.recalculate_scope == "YEAR":
                start_d = f"{now.year}-01-01"
                end_d = f"{now.year}-12-31"
                execute_recalculate_query(cur, start_d, end_d, updated_policy)
                recalculated_message = f"Settings saved and full year {now.year} attendance recalculated!"
            elif data.recalculate_scope == "MONTH":
                start_d = f"{now.year}-{now.month:02d}-01"
                # Last day of current month
                import calendar
                _, last_day = calendar.monthrange(now.year, now.month)
                end_d = f"{now.year}-{now.month:02d}-{last_day:02d}"
                execute_recalculate_query(cur, start_d, end_d, updated_policy)
                recalculated_message = f"Settings saved and {now.strftime('%B %Y')} attendance recalculated!"

        return {
            "success": True,
            "message": recalculated_message,
            "policy": updated_policy
        }

@router.post("/recalculate")
def recalculate_attendance_custom(req: RecalculateRequest):
    """Trigger attendance recalculation across a custom date range using active policy"""
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_attendance_policy LIMIT 1;")
        policy = dict(cur.fetchone())
        execute_recalculate_query(cur, req.start_date, req.end_date, policy)
        return {
            "success": True,
            "message": f"Successfully recalculated attendance from {req.start_date} to {req.end_date}."
        }

@router.get("/single-punches")
def get_single_punches(attendance_date: str = Query(...)):
    """Fetch all employees with a single punch (missing in or out) on a specific date"""
    with get_db() as cur:
        query = """
            SELECT 
                e.id as employee_id,
                e.employee_code,
                e.display_name,
                e.department,
                e.designation,
                p_in.punch_time as single_punch_time,
                p_in.punch_state,
                a.status as current_status,
                a.total_work_minutes
            FROM hr_employees e
            JOIN (
                SELECT employee_id, MIN(punch_time) as punch_time, punch_state
                FROM hr_biometric_punches
                WHERE DATE(punch_time) = %s AND employee_id IS NOT NULL
                GROUP BY employee_id, punch_state
                HAVING COUNT(*) = 1
            ) p_in ON e.id = p_in.employee_id
            LEFT JOIN hr_attendance_daily a ON e.id = a.employee_id AND a.attendance_date = %s
            WHERE (
                SELECT COUNT(*) FROM hr_biometric_punches p2 
                WHERE p2.employee_id = e.id AND DATE(p2.punch_time) = %s
            ) = 1
            ORDER BY e.biometric_id ASC;
        """
        cur.execute(query, (attendance_date, attendance_date, attendance_date))
        rows = cur.fetchall()
        return {
            "date": attendance_date,
            "count": len(rows),
            "records": [dict(r) for r in rows]
        }

@router.post("/regularize-single-punches")
def regularize_single_punches(req: RegularizeRequest):
    """Bulk regularize single punches on a specific date"""
    with get_db() as cur:
        cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
        sh_row = cur.fetchone()
        shift_id = sh_row["id"] if sh_row else None

        # Fetch affected single punch employees
        emp_filter = "AND e.id = ANY(%s::uuid[])" if req.employee_ids else ""
        params = [req.attendance_date, req.attendance_date]
        if req.employee_ids:
            params.append(req.employee_ids)

        cur.execute(f"""
            SELECT e.id, MIN(p.punch_time) as first_in
            FROM hr_employees e
            JOIN hr_biometric_punches p ON e.id = p.employee_id
            WHERE DATE(p.punch_time) = %s {emp_filter}
            GROUP BY e.id
            HAVING MIN(p.punch_time) = MAX(p.punch_time);
        """, params)
        targets = cur.fetchall()

        updated_count = 0
        for t in targets:
            emp_id = t["id"]
            first_in = t["first_in"]

            if req.action == "SET_OUT_TIME":
                out_ts_str = f"{req.attendance_date} {req.out_time}"
                last_out = datetime.strptime(out_ts_str, "%Y-%m-%d %H:%M:%S")
                total_mins = max(0, int((last_out - first_in).total_seconds() / 60))
                ot_mins = max(0, total_mins - 480)
                status = "PRESENT" if total_mins >= 240 else "HALF_DAY"
                reason = f"Regularized missing exit punch to {req.out_time}"
            elif req.action == "MARK_FULL_DAY":
                last_out = first_in
                total_mins = 480
                ot_mins = 0
                status = "PRESENT"
                reason = "Regularized single punch as Full Day Present"
            else:  # MARK_HALF_DAY
                last_out = first_in
                total_mins = 240
                ot_mins = 0
                status = "HALF_DAY"
                reason = "Regularized single punch as Half Day"

            cur.execute("""
                INSERT INTO hr_attendance_daily (
                    employee_id, attendance_date, shift_id, punch_in, punch_out,
                    total_work_minutes, overtime_minutes, status, is_manual_override, override_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
                    punch_out = EXCLUDED.punch_out,
                    total_work_minutes = EXCLUDED.total_work_minutes,
                    overtime_minutes = EXCLUDED.overtime_minutes,
                    status = EXCLUDED.status,
                    is_manual_override = TRUE,
                    override_reason = EXCLUDED.override_reason,
                    updated_at = CURRENT_TIMESTAMP;
            """, (emp_id, req.attendance_date, shift_id, first_in, last_out, total_mins, ot_mins, status, reason))
            updated_count += 1

        return {
            "success": True,
            "message": f"Successfully regularized {updated_count} staff single punches for {req.attendance_date}!",
            "updated_count": updated_count
        }
