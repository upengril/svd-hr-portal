import os
import csv
import time
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime

DB_URL = "postgresql://postgres:admin@localhost:5432/svd_erp_dev"
ALL_PUNCHES_CSV = r"C:\Users\LENOVO\.gemini\antigravity-cli\brain\9d15478f-3f35-4b85-aedf-5650e1f52d8a\scratch\extracted_data\device_2_all_attendance.csv"

def import_all_history():
    print(f"[*] Starting full historical import from {ALL_PUNCHES_CSV}...", flush=True)
    t0 = time.time()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # 1. Map biometric_id to employee_id
    cur.execute("SELECT biometric_id, id FROM hr_employees WHERE biometric_id IS NOT NULL;")
    emp_map = {row[0]: row[1] for row in cur.fetchall()}
    print(f"[*] Loaded {len(emp_map)} employee mappings.", flush=True)

    # 2. Read all rows from CSV
    batch = []
    with open(ALL_PUNCHES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bio_id = int(row["user_id"])
            ts_str = row["timestamp"]
            p_state = int(row.get("punch", 0))
            v_type = int(row.get("status", 1))
            emp_id = emp_map.get(bio_id)

            batch.append(('192.168.31.111', bio_id, emp_id, ts_str, p_state, v_type))

    print(f"[*] Read {len(batch)} punches from CSV. Bulk inserting into hr_biometric_punches...", flush=True)

    # Bulk insert with ON CONFLICT DO NOTHING
    insert_sql = """
        INSERT INTO hr_biometric_punches (
            device_ip, biometric_id, employee_id, punch_time, punch_state, verify_type
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_ip, biometric_id, punch_time) DO NOTHING;
    """
    execute_batch(cur, insert_sql, batch, page_size=2000)
    conn.commit()
    t1 = time.time()
    print(f"[+] Inserted {len(batch)} punches in {t1 - t0:.2f} seconds!", flush=True)

    # 3. Compute daily attendance for ALL historical dates in single high-speed SQL
    print("[*] Computing daily attendance (First-In, Last-Out, Total Hours, Status) for all historical dates...", flush=True)
    cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
    shift_row = cur.fetchone()
    shift_id = shift_row[0] if shift_row else None

    compute_sql = """
        INSERT INTO hr_attendance_daily (
            employee_id,
            attendance_date,
            shift_id,
            punch_in,
            punch_out,
            total_work_minutes,
            overtime_minutes,
            late_minutes,
            status
        )
        SELECT 
            p.employee_id,
            DATE(p.punch_time) as att_date,
            %s as shift_id,
            MIN(p.punch_time) as punch_in,
            MAX(p.punch_time) as punch_out,
            ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer as total_work_minutes,
            GREATEST(0, ROUND(EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) / 60)::integer - 480) as overtime_minutes,
            CASE 
                WHEN MIN(p.punch_time)::time > '09:15:00'::time 
                THEN ROUND(EXTRACT(EPOCH FROM (MIN(p.punch_time)::time - '09:00:00'::time)) / 60)::integer
                ELSE 0
            END as late_minutes,
            CASE 
                WHEN MIN(p.punch_time) = MAX(p.punch_time) THEN 'PRESENT'
                WHEN EXTRACT(EPOCH FROM (MAX(p.punch_time) - MIN(p.punch_time))) < 14400 THEN 'HALF_DAY'
                ELSE 'PRESENT'
            END as status
        FROM hr_biometric_punches p
        WHERE p.employee_id IS NOT NULL
        GROUP BY p.employee_id, DATE(p.punch_time)
        ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
            punch_in = EXCLUDED.punch_in,
            punch_out = EXCLUDED.punch_out,
            total_work_minutes = EXCLUDED.total_work_minutes,
            overtime_minutes = EXCLUDED.overtime_minutes,
            late_minutes = EXCLUDED.late_minutes,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP;
    """
    cur.execute(compute_sql, (shift_id,))
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM hr_attendance_daily;")
    total_daily_records = cur.fetchone()[0]

    cur.execute("SELECT MIN(attendance_date), MAX(attendance_date) FROM hr_attendance_daily;")
    min_date, max_date = cur.fetchone()

    t2 = time.time()
    print(f"[+] SUCCESS! Processed and recorded {total_daily_records} daily attendance records from {min_date} to {max_date}!", flush=True)
    print(f"[+] Total execution time: {t2 - t0:.2f} seconds.", flush=True)

    conn.close()

if __name__ == "__main__":
    import_all_history()
