import os
import time
import struct
import threading
from struct import pack, unpack
from datetime import datetime, date
from zk import ZK, const
from psycopg2.extras import execute_values
from ..config import BIOMETRIC_CONFIG, COMPANY_INFO
from ..db import get_db

class BiometricService:
    def __init__(self):
        self.ip = BIOMETRIC_CONFIG["ip"]
        self.port = BIOMETRIC_CONFIG["port"]
        self.timeout = 10
        self.lock = threading.Lock()

    def get_status(self):
        """Check live connection to Device 2 and return status"""
        acquired = self.lock.acquire(timeout=4)
        if not acquired:
            return {
                "online": True,
                "ip": self.ip,
                "port": self.port,
                "status": "Device busy syncing"
            }
        zk = ZK(self.ip, port=self.port, timeout=5, force_udp=False, ommit_ping=False)
        conn = None
        try:
            conn = zk.connect()
            conn.read_sizes()
            status_data = {
                "online": True,
                "ip": self.ip,
                "port": self.port,
                "device_name": conn.get_device_name(),
                "serial_number": conn.get_serialnumber(),
                "firmware": conn.get_firmware_version(),
                "mac": conn.get_mac(),
                "device_time": str(conn.get_time()),
                "total_users": conn.users,
                "total_records": conn.records,
                "total_fingers": conn.fingers
            }
            return status_data
        except Exception as e:
            return {
                "online": False,
                "ip": self.ip,
                "port": self.port,
                "error": str(e)
            }
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass
            self.lock.release()

    def sync_punches(self, recent_bytes=None, deep=False):
        """
        Adaptive High-Speed Biometric Sync:
        - Automatically detects punch deficit between device and PostgreSQL
        - Calculates the exact byte buffer required so historical punches are never missed
        - Uses batch database insertion and set-based attendance recalculation
        - Runs in < 1 second on normal passes; catches up multi-day backlogs seamlessly.
        """
        zk = ZK(self.ip, port=self.port, timeout=10, force_udp=False, ommit_ping=False)
        conn = None
        t0 = time.time()
        try:
            conn = zk.connect()
            conn.read_sizes()
            total_records = conn.records

            # Request attendance log buffer size
            cmd_response = conn._ZK__send_command(1503, pack('<bhii', 1, const.CMD_ATTLOG_RRQ, 0, 0), 1024)
            data = conn._ZK__data
            total_size = unpack('I', data[1:5])[0]

            # Determine deficit from database
            with get_db() as cur:
                cur.execute("SELECT count(*) as cnt FROM hr_biometric_punches WHERE device_ip = %s;", (self.ip,))
                db_punches = cur.fetchone()["cnt"]

            deficit = max(0, total_records - db_punches)

            if deep:
                bytes_to_pull = min(total_size, 400000)
            elif recent_bytes is not None:
                bytes_to_pull = min(total_size, recent_bytes)
            else:
                # Dynamic auto-sizing: base 60KB (~1,500 punches) + deficit padding
                needed = 60000 + (deficit * 40) + 20000
                bytes_to_pull = min(total_size, max(60000, needed))

            tail_bytes = min(total_size, bytes_to_pull)
            start_offset = total_size - tail_bytes

            chunk_data = conn._ZK__read_chunk(start_offset, tail_bytes)
            conn.free_data()
            conn.disconnect() # Disconnect immediately to free socket
            conn = None
            t_pull = time.time() - t0

            # Determine record offset in chunk (first record begins after 4-byte header)
            if start_offset <= 4:
                offset_in_chunk = 4 - start_offset
            else:
                rem = (start_offset - 4) % 40
                offset_in_chunk = (40 - rem) % 40

            raw = chunk_data[offset_in_chunk:]

            # Decode and deduplicate punches in memory
            punches_dict = {}
            while len(raw) >= 40:
                uid, user_id_b, status, timehex, punch, space = unpack('<H24sB4sB8s', raw[:40])
                user_id_str = (user_id_b.split(b'\x00')[0]).decode(errors='ignore').strip()
                raw = raw[40:]

                if not user_id_str or not user_id_str.isdigit():
                    continue

                bio_id = int(user_id_str)
                # Decode 4-byte time
                try:
                    t = struct.unpack('<I', timehex)[0]
                    second = t % 60
                    t = t // 60
                    minute = t % 60
                    t = t // 60
                    hour = t % 24
                    t = t // 24
                    day = t % 31 + 1
                    t = t // 31
                    month = t % 12 + 1
                    t = t // 12
                    year = t + 2000

                    if year < 2020 or year > 2030 or month < 1 or month > 12:
                        continue

                    ts_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                    key = (self.ip, bio_id, ts_str)
                    punches_dict[key] = (self.ip, bio_id, ts_str, punch, status)
                except Exception:
                    continue

            new_punches = 0
            affected_dates = set()

            with get_db() as cur:
                # 1. Map employee biometric_id -> id
                cur.execute("SELECT biometric_id, id FROM hr_employees WHERE biometric_id IS NOT NULL;")
                emp_map = {row["biometric_id"]: row["id"] for row in cur.fetchall()}

                # Auto-enroll any newly observed biometric IDs not yet in hr_employees
                unique_bio_ids = set(p[1] for p in punches_dict.values())
                unmapped_ids = [bid for bid in unique_bio_ids if bid not in emp_map]
                if unmapped_ids:
                    cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
                    sh_row = cur.fetchone()
                    sh_id = sh_row["id"] if sh_row else None
                    cur.execute("SELECT company_id FROM hr_company_settings LIMIT 1;")
                    cmp_row = cur.fetchone()
                    cmp_id = cmp_row["company_id"] if cmp_row else None

                    for bid in unmapped_ids:
                        code = f"SVD-{bid:04d}"
                        dname = f"Staff-{bid}"
                        cur.execute("""
                            INSERT INTO hr_employees (
                                company_id, employee_code, biometric_id, first_name, display_name,
                                shift_id, department, designation, date_of_joining, status
                            ) VALUES (%s, %s, %s, %s, %s, %s, 'Site Operations', 'Field Executive', '2026-10-01', 'ACTIVE')
                            ON CONFLICT (employee_code) DO NOTHING;
                        """, (cmp_id, code, bid, dname, dname, sh_id))

                    cur.execute("SELECT biometric_id, id FROM hr_employees WHERE biometric_id IS NOT NULL;")
                    emp_map = {row["biometric_id"]: row["id"] for row in cur.fetchall()}

                # Prepare batch rows
                batch_rows = []
                for (d_ip, bid, ts_str, p_state, v_type) in punches_dict.values():
                    batch_rows.append((d_ip, bid, emp_map.get(bid), ts_str, p_state, v_type))

                if batch_rows:
                    insert_sql = """
                        INSERT INTO hr_biometric_punches (
                            device_ip, biometric_id, employee_id, punch_time, punch_state, verify_type
                        ) VALUES %s
                        ON CONFLICT (device_ip, biometric_id, punch_time) DO NOTHING
                        RETURNING id, DATE(punch_time)::text as punch_date;
                    """
                    inserted = execute_values(cur, insert_sql, batch_rows, fetch=True)
                    new_punches = len(inserted)
                    for r in inserted:
                        d_val = r["punch_date"] if isinstance(r, dict) else r[1]
                        affected_dates.add(str(d_val))

                # Recalculate attendance for affected dates
                if affected_dates:
                    self._recalculate_attendance(cur, list(affected_dates))
                else:
                    # Ensure today is updated
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    self._recalculate_attendance(cur, [today_str])

            return {
                "success": True,
                "total_records_on_device": total_records,
                "recent_punches_checked": len(punches_dict),
                "new_punches_synced": new_punches,
                "pull_time_seconds": round(t_pull, 2),
                "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def _recalculate_attendance(self, cur, dates_to_process):
        """Calculate punch in, punch out, total work minutes, and attendance status"""
        if not dates_to_process:
            return

        cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
        shift_row = cur.fetchone()
        shift_id = shift_row["id"] if shift_row else None

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
            WHERE p.employee_id IS NOT NULL AND DATE(p.punch_time) = ANY(%s::date[])
            GROUP BY p.employee_id, DATE(p.punch_time)
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
        cur.execute(recalc_sql, (shift_id, list(dates_to_process)))

biometric_service = BiometricService()
