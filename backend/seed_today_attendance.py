import os
import csv
import psycopg2
from datetime import datetime

DB_URL = "postgresql://postgres:admin@localhost:5432/svd_erp_dev"
PUNCHES_CSV = r"C:\Users\LENOVO\.gemini\antigravity-cli\brain\9d15478f-3f35-4b85-aedf-5650e1f52d8a\scratch\extracted_data\device_2_today_attendance.csv"

def import_today_punches():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    if not os.path.exists(PUNCHES_CSV):
        print(f"File {PUNCHES_CSV} not found.")
        return

    # Map biometric_id to employee_id
    cur.execute("SELECT biometric_id, id FROM hr_employees WHERE biometric_id IS NOT NULL")
    emp_map = {row[0]: row[1] for row in cur.fetchall()}

    inserted_punches = 0
    with open(PUNCHES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bio_id = int(row["user_id"])
            ts_str = row["timestamp"]
            punch_type = int(row.get("punch", 0))
            status_val = int(row.get("status", 1))
            emp_uuid = emp_map.get(bio_id)

            cur.execute("""
                INSERT INTO hr_biometric_punches (
                    device_ip, biometric_id, employee_id, punch_time, punch_state, verify_type
                ) VALUES (
                    '192.168.31.111', %s, %s, %s, %s, %s
                )
                ON CONFLICT (device_ip, biometric_id, punch_time) DO NOTHING;
            """, (bio_id, emp_uuid, ts_str, punch_type, status_val))
            inserted_punches += 1

    print(f"Imported {inserted_punches} raw punches for today!")

    # Now calculate daily attendance for today (2026-10-22)
    cur.execute("""
        SELECT 
            p.employee_id,
            DATE(p.punch_time) as att_date,
            MIN(p.punch_time) as first_in,
            MAX(p.punch_time) as last_out,
            COUNT(*) as punch_count
        FROM hr_biometric_punches p
        WHERE p.employee_id IS NOT NULL AND DATE(p.punch_time) = '2026-10-22'
        GROUP BY p.employee_id, DATE(p.punch_time);
    """)
    daily_records = cur.fetchall()

    cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1")
    shift_id = cur.fetchone()[0]

    updated_attendance = 0
    for emp_id, att_date, first_in, last_out, punch_cnt in daily_records:
        # Calculate working minutes
        total_mins = int((last_out - first_in).total_seconds() / 60)
        
        # Determine status
        # If punch_in is after 09:15 AM -> LATE
        shift_start = datetime.strptime(f"{att_date} 09:15:00", "%Y-%m-%d %H:%M:%S")
        is_late = first_in > shift_start
        late_mins = max(0, int((first_in - datetime.strptime(f"{att_date} 09:00:00", "%Y-%m-%d %H:%M:%S")).total_seconds() / 60)) if is_late else 0
        
        # Overtime calculation: if work hours > 8 hours (480 mins)
        ot_mins = max(0, total_mins - 480)

        if total_mins < 240 and first_in == last_out:
            # Single punch so far (checked in, still at work)
            status = 'PRESENT'
        elif total_mins < 240:
            status = 'HALF_DAY'
        else:
            status = 'PRESENT'

        cur.execute("""
            INSERT INTO hr_attendance_daily (
                employee_id, attendance_date, shift_id, punch_in, punch_out,
                total_work_minutes, overtime_minutes, late_minutes, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
                punch_in = EXCLUDED.punch_in,
                punch_out = EXCLUDED.punch_out,
                total_work_minutes = EXCLUDED.total_work_minutes,
                overtime_minutes = EXCLUDED.overtime_minutes,
                late_minutes = EXCLUDED.late_minutes,
                status = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP;
        """, (
            emp_id, att_date, shift_id, first_in, last_out,
            total_mins, ot_mins, late_mins, status
        ))
        updated_attendance += 1

    conn.commit()
    print(f"Calculated and recorded daily attendance for {updated_attendance} active staff today!")
    conn.close()

if __name__ == "__main__":
    import_today_punches()
