import os
import csv
import json
import psycopg2
from datetime import date

DB_URL = "postgresql://postgres:admin@localhost:5432/svd_erp_dev"
COMPANY_ID = "673eeb08-7278-435e-8a10-f706c46afe64"
USERS_CSV = r"C:\Users\LENOVO\.gemini\antigravity-cli\brain\9d15478f-3f35-4b85-aedf-5650e1f52d8a\scratch\extracted_data\device_2_users.csv"

def seed_database():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("1. Seeding Company Settings...")
    directors = [
        {"name": "Nitin Chawla", "designation": "Director"},
        {"name": "Ashok Vashdew Jagtiani", "designation": "Director"},
        {"name": "Snehlata", "designation": "Director"},
        {"name": "Mohammad Ubaidullah Faizi", "designation": "Director"},
        {"name": "Rakesh Ashok Jagtiani", "designation": "Director"},
        {"name": "Kamal Singh", "designation": "Director"}
    ]
    
    cur.execute("""
        INSERT INTO hr_company_settings (
            company_id, corporate_name, cin, registered_address, industry,
            incorporation_date, authorized_capital, paid_up_capital, directors
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT DO NOTHING;
    """, (
        COMPANY_ID,
        "SV DREEAMPLANNERS PRIVATE LIMITED",
        "U45100UP2013PTC056525",
        "C-3/87, 88, 89, First Floor, Vibhuti Khand, Gomti Nagar, Lucknow, Uttar Pradesh, India - 226010",
        "Site preparation and construction (NIC Code 4510)",
        "2013-04-26",
        35500000.00,
        1039270.00,
        json.dumps(directors)
    ))

    print("2. Seeding Shifts...")
    cur.execute("""
        INSERT INTO hr_shifts (company_id, name, code, start_time, end_time, grace_period_mins, half_day_hours, full_day_hours, is_default)
        VALUES 
            (%s, 'General Office Shift', 'GEN', '09:00:00', '18:00:00', 15, 4.50, 8.00, TRUE),
            (%s, 'Morning Site Shift', 'SITE_M', '08:00:00', '17:00:00', 15, 4.50, 8.00, FALSE),
            (%s, 'Night Shift', 'NIGHT', '20:00:00', '05:00:00', 15, 4.50, 8.00, FALSE)
        ON CONFLICT (code) DO NOTHING;
    """, (COMPANY_ID, COMPANY_ID, COMPANY_ID))

    cur.execute("SELECT id FROM hr_shifts WHERE code = 'GEN' LIMIT 1")
    default_shift_id = cur.fetchone()[0]

    print("3. Seeding Public Holidays (2026)...")
    holidays_2026 = [
        ("Republic Day", "2026-01-26", "NATIONAL"),
        ("Maha Shivratri", "2026-02-15", "PUBLIC"),
        ("Holi", "2026-03-04", "PUBLIC"),
        ("Id-ul-Fitr", "2026-03-21", "PUBLIC"),
        ("Dr. B.R. Ambedkar Jayanti", "2026-04-14", "PUBLIC"),
        ("Labour Day", "2026-05-01", "PUBLIC"),
        ("Independence Day", "2026-08-15", "NATIONAL"),
        ("Raksha Bandhan", "2026-08-28", "PUBLIC"),
        ("Janmashtami", "2026-09-04", "PUBLIC"),
        ("Mahatma Gandhi Jayanti", "2026-10-02", "NATIONAL"),
        ("Dussehra (Vijay Dashami)", "2026-10-20", "PUBLIC"),
        ("Diwali (Deepavali)", "2026-11-08", "PUBLIC"),
        ("Govardhan Puja", "2026-11-09", "PUBLIC"),
        ("Guru Nanak Jayanti", "2026-11-24", "PUBLIC"),
        ("Christmas", "2026-12-25", "PUBLIC")
    ]
    for hname, hdate, htype in holidays_2026:
        cur.execute("""
            INSERT INTO hr_holidays (company_id, holiday_name, holiday_date, holiday_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (holiday_date) DO NOTHING;
        """, (COMPANY_ID, hname, hdate, htype))

    print("4. Seeding 329 Employees from Device 2...")
    if not os.path.exists(USERS_CSV):
        print(f"Warning: {USERS_CSV} not found")
        return

    inserted_count = 0
    with open(USERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bio_id = int(row["user_id"])
            raw_name = row["name"].strip()
            if not raw_name:
                raw_name = f"Staff-{bio_id}"
            
            # Format clean first & last name
            name_parts = raw_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            emp_code = f"SVD-{bio_id:04d}"
            card = row.get("card", "0")

            cur.execute("""
                INSERT INTO hr_employees (
                    company_id, employee_code, biometric_id, card_number,
                    first_name, last_name, display_name, shift_id, department, designation,
                    date_of_joining, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, 'Site Operations', 'Field Executive',
                    '2026-01-01', 'ACTIVE'
                )
                ON CONFLICT (employee_code) DO UPDATE SET
                    biometric_id = EXCLUDED.biometric_id,
                    display_name = EXCLUDED.display_name
                RETURNING id;
            """, (
                COMPANY_ID, emp_code, bio_id, card,
                first_name, last_name, raw_name, default_shift_id
            ))
            emp_uuid = cur.fetchone()[0]

            # Bank details record placeholder
            cur.execute("""
                INSERT INTO hr_bank_details (employee_id, account_holder_name, is_primary)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (employee_id) DO NOTHING;
            """, (emp_uuid, raw_name))

            # Leave balances for current year (2026)
            cur.execute("""
                INSERT INTO hr_leave_balances (employee_id, year, casual_leave, sick_leave, earned_leave)
                VALUES (%s, 2026, 12, 10, 15)
                ON CONFLICT (employee_id, year) DO NOTHING;
            """, (emp_uuid,))

            # Salary structure default: Monthly gross ₹25,000 or Daily ₹850
            cur.execute("""
                INSERT INTO hr_salary_structures (
                    employee_id, wage_type, monthly_gross, basic_pay, hra, conveyance, special_allowance
                ) VALUES (
                    %s, 'MONTHLY', 25000.00, 12500.00, 5000.00, 2500.00, 5000.00
                )
                ON CONFLICT (employee_id) DO NOTHING;
            """, (emp_uuid,))

            inserted_count += 1

    conn.commit()
    print(f"Successfully seeded {inserted_count} employees from Device 2!")
    conn.close()

if __name__ == "__main__":
    seed_database()
