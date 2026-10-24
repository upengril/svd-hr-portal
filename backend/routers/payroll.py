import os
import io
import calendar
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from ..db import get_db
from ..services.payslip_service import PayslipGenerator
from ..config import COMPANY_INFO

router = APIRouter(prefix="/api/payroll", tags=["Payroll & Payslips"])

class PayrollRunRequestSchema(BaseModel):
    month: int
    year: int

@router.post("/run")
def process_payroll_run(data: PayrollRunRequestSchema):
    month = data.month
    year = data.year
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{days_in_month:02d}"

    company_id = COMPANY_INFO["id"]

    with get_db() as cur:
        # 1. Create or get payroll run
        cur.execute("""
            INSERT INTO hr_payroll_runs (company_id, month, year, status)
            VALUES (%s, %s, %s, 'PROCESSING')
            ON CONFLICT (company_id, month, year) DO UPDATE SET
                status = 'PROCESSING',
                processed_at = CURRENT_TIMESTAMP
            RETURNING id;
        """, (company_id, month, year))
        payroll_run_id = cur.fetchone()["id"]

        # 2. Get active employees with salary structure and bank details
        cur.execute("""
            SELECT 
                e.id,
                e.employee_code,
                e.display_name,
                e.department,
                e.designation,
                e.date_of_joining,
                e.pan_number,
                e.aadhar_number,
                e.uan_number,
                e.esic_number,
                b.bank_name,
                b.account_number,
                b.ifsc_code,
                s.wage_type,
                COALESCE(s.monthly_gross, 25000.00) as monthly_gross,
                COALESCE(s.daily_rate, 850.00) as daily_rate,
                COALESCE(s.basic_pay, 12500.00) as basic_pay,
                COALESCE(s.hra, 5000.00) as hra,
                COALESCE(s.conveyance, 2500.00) as conveyance,
                COALESCE(s.special_allowance, 5000.00) as special_allowance,
                COALESCE(s.pf_applicable, TRUE) as pf_applicable,
                COALESCE(s.esic_applicable, TRUE) as esic_applicable,
                COALESCE(s.pt_applicable, TRUE) as pt_applicable
            FROM hr_employees e
            LEFT JOIN hr_bank_details b ON e.id = b.employee_id
            LEFT JOIN hr_salary_structures s ON e.id = s.employee_id
            WHERE e.status = 'ACTIVE'
            ORDER BY e.employee_code ASC;
        """)
        employees = cur.fetchall()

        total_employees = len(employees)
        batch_gross = 0.0
        batch_deductions = 0.0
        batch_net = 0.0

        for emp in employees:
            emp_id = emp["id"]

            # Attendance stats for this month
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'PRESENT') as present_cnt,
                    COUNT(*) FILTER (WHERE status = 'HALF_DAY') as half_day_cnt,
                    COUNT(*) FILTER (WHERE status = 'LATE') as late_cnt,
                    SUM(COALESCE(overtime_minutes, 0)) as total_ot_mins
                FROM hr_attendance_daily
                WHERE employee_id = %s AND attendance_date >= %s AND attendance_date <= %s;
            """, (emp_id, start_date, end_date))
            att_stat = cur.fetchone()

            p_cnt = (att_stat["present_cnt"] or 0) + (att_stat["late_cnt"] or 0)
            hd_cnt = att_stat["half_day_cnt"] or 0
            ot_mins = att_stat["total_ot_mins"] or 0
            ot_hours = round(ot_mins / 60.0, 2)

            # Approved leaves
            cur.execute("""
                SELECT COALESCE(SUM(days_count), 0) as leave_days
                FROM hr_leaves
                WHERE employee_id = %s AND status = 'APPROVED'
                  AND from_date >= %s AND to_date <= %s;
            """, (emp_id, start_date, end_date))
            leave_days = float(cur.fetchone()["leave_days"] or 0)

            # Paid Holidays in this month
            cur.execute("""
                SELECT COUNT(*) as hol_cnt
                FROM hr_holidays
                WHERE holiday_date >= %s AND holiday_date <= %s;
            """, (start_date, end_date))
            holiday_days = float(cur.fetchone()["hol_cnt"] or 0)

            # Week-offs (standard 4 Sundays)
            sundays = len([d for d in range(1, days_in_month + 1) if datetime(year, month, d).weekday() == 6])

            # Effective paid days
            actual_worked = p_cnt + (hd_cnt * 0.5)
            # If no punches in system yet for earlier dates, treat default active staff as standard active for baseline
            if actual_worked == 0:
                paid_days = float(days_in_month - sundays)
                present_days = paid_days
                absent_days = 0.0
            else:
                paid_days = min(float(days_in_month), actual_worked + leave_days + holiday_days + sundays)
                present_days = actual_worked
                absent_days = max(0.0, float(days_in_month) - paid_days)

            # Pro-rata calculation
            ratio = paid_days / float(days_in_month)
            basic_earned = round(float(emp["basic_pay"]) * ratio, 2)
            hra_earned = round(float(emp["hra"]) * ratio, 2)
            conveyance_earned = round(float(emp["conveyance"]) * ratio, 2)
            special_allowance_earned = round(float(emp["special_allowance"]) * ratio, 2)
            
            # Overtime pay (approx hourly rate = monthly_gross / (30 * 8))
            hourly_rate = float(emp["monthly_gross"]) / 240.0
            ot_pay = round(ot_hours * hourly_rate * 1.5, 2)

            gross_earned = round(basic_earned + hra_earned + conveyance_earned + special_allowance_earned + ot_pay, 2)

            # Deductions
            pf_deduction = round(basic_earned * 0.12, 2) if emp["pf_applicable"] else 0.0
            esic_deduction = round(gross_earned * 0.0075, 2) if (emp["esic_applicable"] and gross_earned <= 21000) else 0.0
            pt_deduction = 200.0 if (emp["pt_applicable"] and gross_earned > 15000) else 0.0
            tds_deduction = 0.0
            other_deductions = 0.0
            total_deductions = round(pf_deduction + esic_deduction + pt_deduction + tds_deduction + other_deductions, 2)
            net_pay = max(0.0, round(gross_earned - total_deductions, 2))

            # Insert/Update payslip record
            cur.execute("""
                INSERT INTO hr_payslips (
                    payroll_run_id, employee_id, month, year, days_in_month,
                    paid_days, present_days, absent_days, leave_days, holiday_days, overtime_hours,
                    basic_earned, hra_earned, conveyance_earned, special_allowance_earned, overtime_pay,
                    gross_earned, pf_deduction, esic_deduction, pt_deduction, tds_deduction,
                    other_deductions, total_deductions, net_pay, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'GENERATED'
                )
                ON CONFLICT (employee_id, month, year) DO UPDATE SET
                    days_in_month = EXCLUDED.days_in_month,
                    paid_days = EXCLUDED.paid_days,
                    present_days = EXCLUDED.present_days,
                    absent_days = EXCLUDED.absent_days,
                    basic_earned = EXCLUDED.basic_earned,
                    hra_earned = EXCLUDED.hra_earned,
                    gross_earned = EXCLUDED.gross_earned,
                    total_deductions = EXCLUDED.total_deductions,
                    net_pay = EXCLUDED.net_pay,
                    status = 'GENERATED'
                RETURNING id;
            """, (
                payroll_run_id, emp_id, month, year, days_in_month,
                paid_days, present_days, absent_days, leave_days, holiday_days, ot_hours,
                basic_earned, hra_earned, conveyance_earned, special_allowance_earned, ot_pay,
                gross_earned, pf_deduction, esic_deduction, pt_deduction, tds_deduction,
                other_deductions, total_deductions, net_pay
            ))
            slip_id = cur.fetchone()["id"]

            # Generate PDF payslip
            payslip_dict = {
                "employee_code": emp["employee_code"],
                "employee_name": emp["display_name"],
                "department": emp["department"],
                "designation": emp["designation"],
                "date_of_joining": emp["date_of_joining"],
                "pan_number": emp["pan_number"],
                "aadhar_number": emp["aadhar_number"],
                "uan_number": emp["uan_number"],
                "bank_name": emp["bank_name"],
                "account_number": emp["account_number"],
                "ifsc_code": emp["ifsc_code"],
                "month": month,
                "year": year,
                "paid_days": paid_days,
                "present_days": present_days,
                "absent_days": absent_days,
                "leave_days": leave_days,
                "holiday_days": holiday_days,
                "overtime_hours": ot_hours,
                "basic_earned": basic_earned,
                "hra_earned": hra_earned,
                "conveyance_earned": conveyance_earned,
                "special_allowance_earned": special_allowance_earned,
                "overtime_pay": ot_pay,
                "gross_earned": gross_earned,
                "pf_deduction": pf_deduction,
                "esic_deduction": esic_deduction,
                "pt_deduction": pt_deduction,
                "tds_deduction": tds_deduction,
                "other_deductions": other_deductions,
                "total_deductions": total_deductions,
                "net_pay": net_pay
            }
            pdf_path = PayslipGenerator.generate_pdf(payslip_dict)

            cur.execute("UPDATE hr_payslips SET pdf_path = %s WHERE id = %s;", (pdf_path, slip_id))

            batch_gross += gross_earned
            batch_deductions += total_deductions
            batch_net += net_pay

        # Update payroll run summary
        cur.execute("""
            UPDATE hr_payroll_runs SET
                total_employees = %s,
                total_gross_payout = %s,
                total_deductions = %s,
                total_net_payout = %s,
                status = 'PROCESSED',
                processed_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (total_employees, batch_gross, batch_deductions, batch_net, payroll_run_id))

    return {
        "success": True,
        "payroll_run_id": payroll_run_id,
        "month": month,
        "year": year,
        "total_employees": total_employees,
        "total_gross_payout": batch_gross,
        "total_deductions": batch_deductions,
        "total_net_payout": batch_net,
        "message": f"Processed payroll for {total_employees} staff members and generated PDF payslips successfully!"
    }

@router.get("/runs")
def list_payroll_runs():
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_payroll_runs ORDER BY year DESC, month DESC;")
        runs = cur.fetchall()
    return {"runs": runs}

@router.get("/runs/{run_id}")
def get_payroll_run_details(run_id: str):
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_payroll_runs WHERE id = %s;", (run_id,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found")

        cur.execute("""
            SELECT 
                p.*,
                e.employee_code,
                e.display_name as employee_name,
                e.department,
                e.designation,
                b.bank_name,
                b.account_number,
                b.ifsc_code
            FROM hr_payslips p
            JOIN hr_employees e ON p.employee_id = e.id
            LEFT JOIN hr_bank_details b ON e.id = b.employee_id
            WHERE p.payroll_run_id = %s
            ORDER BY e.employee_code ASC;
        """, (run_id,))
        payslips = cur.fetchall()

    return {
        "run": run,
        "payslips": payslips
    }

@router.get("/payslip/{payslip_id}/pdf")
def download_payslip_pdf(payslip_id: str):
    with get_db() as cur:
        cur.execute("""
            SELECT p.*, e.employee_code, e.display_name, e.department, e.designation, e.date_of_joining,
                   e.pan_number, e.aadhar_number, e.uan_number, b.bank_name, b.account_number, b.ifsc_code
            FROM hr_payslips p
            JOIN hr_employees e ON p.employee_id = e.id
            LEFT JOIN hr_bank_details b ON e.id = b.employee_id
            WHERE p.id = %s;
        """, (payslip_id,))
        slip = cur.fetchone()
        if not slip:
            raise HTTPException(status_code=404, detail="Payslip not found")

    pdf_path = slip["pdf_path"]
    if not pdf_path or not os.path.exists(pdf_path):
        # Regenerate on the fly if needed
        slip_dict = {
            "employee_code": slip["employee_code"],
            "employee_name": slip["display_name"],
            "department": slip["department"],
            "designation": slip["designation"],
            "date_of_joining": slip["date_of_joining"],
            "pan_number": slip["pan_number"],
            "aadhar_number": slip["aadhar_number"],
            "uan_number": slip["uan_number"],
            "bank_name": slip["bank_name"],
            "account_number": slip["account_number"],
            "ifsc_code": slip["ifsc_code"],
            "month": slip["month"],
            "year": slip["year"],
            "paid_days": float(slip["paid_days"]),
            "present_days": float(slip["present_days"]),
            "absent_days": float(slip["absent_days"]),
            "leave_days": float(slip["leave_days"]),
            "holiday_days": float(slip["holiday_days"]),
            "overtime_hours": float(slip["overtime_hours"]),
            "basic_earned": float(slip["basic_earned"]),
            "hra_earned": float(slip["hra_earned"]),
            "conveyance_earned": float(slip["conveyance_earned"]),
            "special_allowance_earned": float(slip["special_allowance_earned"]),
            "overtime_pay": float(slip["overtime_pay"]),
            "gross_earned": float(slip["gross_earned"]),
            "pf_deduction": float(slip["pf_deduction"]),
            "esic_deduction": float(slip["esic_deduction"]),
            "pt_deduction": float(slip["pt_deduction"]),
            "tds_deduction": float(slip["tds_deduction"]),
            "other_deductions": float(slip["other_deductions"]),
            "total_deductions": float(slip["total_deductions"]),
            "net_pay": float(slip["net_pay"])
        }
        pdf_path = PayslipGenerator.generate_pdf(slip_dict)

    filename = f"Payslip_{slip['employee_code']}_{slip['year']}_{slip['month']:02d}.pdf"
    return FileResponse(path=pdf_path, filename=filename, media_type="application/pdf")

@router.get("/runs/{run_id}/export-excel")
def export_payroll_excel(run_id: str):
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_payroll_runs WHERE id = %s;", (run_id,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found")

        cur.execute("""
            SELECT 
                p.*,
                e.employee_code,
                e.display_name,
                e.department,
                e.designation,
                e.pan_number,
                b.bank_name,
                b.account_number,
                b.ifsc_code
            FROM hr_payslips p
            JOIN hr_employees e ON p.employee_id = e.id
            LEFT JOIN hr_bank_details b ON e.id = b.employee_id
            WHERE p.payroll_run_id = %s
            ORDER BY e.employee_code ASC;
        """, (run_id,))
        slips = cur.fetchall()

    wb = Workbook()
    ws = wb.active
    month_name = datetime(run["year"], run["month"], 1).strftime("%B %Y")
    ws.title = f"Payroll {month_name}"

    # Header Styling
    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True)
    center_align = Alignment(horizontal="center", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")

    headers = [
        "S.No", "Employee Code", "Employee Name", "Department", "Designation",
        "Bank Name", "Account Number", "IFSC Code", "PAN Number",
        "Paid Days", "Gross Salary (₹)", "PF (₹)", "ESIC (₹)", "PT (₹)",
        "Total Deductions (₹)", "Net Pay (₹)"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    for idx, s in enumerate(slips, 1):
        row = [
            idx,
            s["employee_code"],
            s["display_name"],
            s["department"],
            s["designation"],
            s["bank_name"] or "N/A",
            s["account_number"] or "N/A",
            s["ifsc_code"] or "N/A",
            s["pan_number"] or "N/A",
            float(s["paid_days"]),
            float(s["gross_earned"]),
            float(s["pf_deduction"]),
            float(s["esic_deduction"]),
            float(s["pt_deduction"]),
            float(s["total_deductions"]),
            float(s["net_pay"])
        ]
        ws.append(row)

    # Summary Row
    total_gross = sum(float(s["gross_earned"]) for s in slips)
    total_ded = sum(float(s["total_deductions"]) for s in slips)
    total_net = sum(float(s["net_pay"]) for s in slips)
    sum_row = ["", "", "TOTAL", "", "", "", "", "", "", "", total_gross, "", "", "", total_ded, total_net]
    ws.append(sum_row)
    for cell in ws[ws.max_row]:
        cell.font = bold_font

    # Column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"SV_DREEAMPLANNERS_Salary_Sheet_{run['year']}_{run['month']:02d}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
