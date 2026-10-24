import os
import time
import struct
from struct import pack, unpack
from datetime import datetime, date
from zk import ZK, const
from ..config import BIOMETRIC_CONFIG, COMPANY_INFO
from ..db import get_db

class BiometricService:
    def __init__(self):
        self.ip = BIOMETRIC_CONFIG["ip"]
        self.port = BIOMETRIC_CONFIG["port"]
        self.timeout = 10

    def get_status(self):
        """Check live connection to Device 2 and return status"""
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

    def sync_punches(self, recent_bytes=40000):
        """
        High-Speed Instant Sync:
        Fetches the latest ~1,000 punches directly from the tail of the device buffer in < 1 second.
        Avoids downloading 90,000+ records and prevents socket collisions.
        """
        zk = ZK(self.ip, port=self.port, timeout=8, force_udp=False, ommit_ping=False)
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

            # Read only the last recent_bytes (last 1,000 punches = ~40,000 bytes)
            tail_bytes = min(total_size, recent_bytes)
            start_offset = total_size - tail_bytes

            chunk_data = conn._ZK__read_chunk(start_offset, tail_bytes)
            conn.free_data()
            conn.disconnect() # Disconnect immediately to free socket
            conn = None
            t_pull = time.time() - t0

            # Parse records
            record_size = 40
            offset_in_chunk = 4 if start_offset == 0 else (tail_bytes % record_size)
            raw = chunk_data[offset_in_chunk:]

            parsed_punches = []
            while len(raw) >= 40:
                uid, user_id_b, status, timehex, punch, space = unpack('<H24sB4sB8s', raw[:40])
                user_id_str = (user_id_b.split(b'\x00')[0]).decode(errors='ignore').strip()
                raw = raw[40:]

                if not user_id_str:
                    continue

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
                    parsed_punches.append({
                        "user_id": int(user_id_str),
                        "timestamp": ts_str,
                        "status": status,
                        "punch": punch
                    })
                except Exception:
                    continue

            # Save parsed punches into PostgreSQL
            new_punches = 0
            affected_dates = set()

            with get_db() as cur:
                cur.execute("SELECT biometric_id, id FROM hr_employees WHERE biometric_id IS NOT NULL;")
                emp_map = {row["biometric_id"]: row["id"] for row in cur.fetchall()}

                for p in parsed_punches:
                    bio_id = p["user_id"]
                    emp_uuid = emp_map.get(bio_id)
                    ts_str = p["timestamp"]
                    p_state = p["punch"]
                    v_type = p["status"]

                    cur.execute("""
                        INSERT INTO hr_biometric_punches (
                            device_ip, biometric_id, employee_id, punch_time, punch_state, verify_type
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (device_ip, biometric_id, punch_time) DO NOTHING
                        RETURNING id;
                    """, (self.ip, bio_id, emp_uuid, ts_str, p_state, v_type))

                    row = cur.fetchone()
                    if row:
                        new_punches += 1
                        affected_dates.add(ts_str.split(" ")[0])

                # Recalculate attendance for affected dates
                if affected_dates:
                    self._recalculate_attendance(cur, affected_dates)
                else:
                    # Ensure today is updated
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    self._recalculate_attendance(cur, [today_str])

            return {
                "success": True,
                "total_records_on_device": total_records,
                "recent_punches_checked": len(parsed_punches),
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
        cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1;")
        shift_row = cur.fetchone()
        shift_id = shift_row["id"] if shift_row else None

        for d_str in dates_to_process:
            cur.execute("""
                SELECT 
                    p.employee_id,
                    DATE(p.punch_time) as att_date,
                    MIN(p.punch_time) as first_in,
                    MAX(p.punch_time) as last_out
                FROM hr_biometric_punches p
                WHERE p.employee_id IS NOT NULL AND DATE(p.punch_time) = %s
                GROUP BY p.employee_id, DATE(p.punch_time);
            """, (d_str,))
            records = cur.fetchall()

            for rec in records:
                emp_id = rec["employee_id"]
                att_date = rec["att_date"]
                first_in = rec["first_in"]
                last_out = rec["last_out"]

                total_mins = int((last_out - first_in).total_seconds() / 60)
                shift_start = datetime.strptime(f"{att_date} 09:15:00", "%Y-%m-%d %H:%M:%S")
                is_late = first_in > shift_start
                late_mins = max(0, int((first_in - datetime.strptime(f"{att_date} 09:00:00", "%Y-%m-%d %H:%M:%S")).total_seconds() / 60)) if is_late else 0
                ot_mins = max(0, total_mins - 480)

                if total_mins < 240 and first_in == last_out:
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
                """, (emp_id, att_date, shift_id, first_in, last_out, total_mins, ot_mins, late_mins, status))

biometric_service = BiometricService()
