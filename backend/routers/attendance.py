import os
import io
import calendar
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from ..db import get_db
from ..config import COMPANY_INFO, PAYSLIP_DIR

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

class ManualAttendanceSchema(BaseModel):
    employee_id: str
    attendance_date: date
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    status: str
    override_reason: str

@router.get("/daily")
def get_daily_attendance(
    attendance_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    target_date = attendance_date or datetime.now().strftime("%Y-%m-%d")

    where_clauses = ["e.status = 'ACTIVE'"]
    params = [target_date]

    if department:
        where_clauses.append("e.department = %s")
        params.append(department)

    if search:
        search_term = f"%{search.strip()}%"
        where_clauses.append("(e.display_name ILIKE %s OR e.employee_code ILIKE %s OR e.biometric_id::text ILIKE %s)")
        params.extend([search_term, search_term, search_term])

    where_sql = " AND ".join(where_clauses)

    with get_db() as cur:
        query = f"""
            SELECT 
                e.id as employee_id,
                e.employee_code,
                e.biometric_id,
                e.display_name,
                e.department,
                e.designation,
                s.name as shift_name,
                s.start_time as shift_start,
                s.end_time as shift_end,
                a.id as attendance_id,
                a.attendance_date,
                a.punch_in,
                a.punch_out,
                COALESCE(a.total_work_minutes, 0) as total_work_minutes,
                COALESCE(a.overtime_minutes, 0) as overtime_minutes,
                COALESCE(a.late_minutes, 0) as late_minutes,
                COALESCE(a.status, 'ABSENT') as status,
                a.is_manual_override,
                a.override_reason
            FROM hr_employees e
            LEFT JOIN hr_shifts s ON e.shift_id = s.id
            LEFT JOIN hr_attendance_daily a ON e.id = a.employee_id AND a.attendance_date = %s
            WHERE {where_sql}
            ORDER BY 
                CASE WHEN a.punch_in IS NOT NULL THEN 0 ELSE 1 END,
                a.punch_in ASC,
                e.biometric_id ASC;
        """
        cur.execute(query, params)
        records = cur.fetchall()

        formatted = []
        counts = {"PRESENT": 0, "ABSENT": 0, "HALF_DAY": 0, "LATE": 0, "OVERTIME": 0}

        for r in records:
            st = r["status"]
            if st in counts:
                counts[st] += 1
            if r["overtime_minutes"] > 0:
                counts["OVERTIME"] += 1
            if r["late_minutes"] > 0:
                counts["LATE"] += 1

            work_hrs = round(r["total_work_minutes"] / 60.0, 1)
            ot_hrs = round(r["overtime_minutes"] / 60.0, 1)

            formatted.append({
                **r,
                "work_hours": work_hrs,
                "overtime_hours": ot_hrs,
                "punch_in_time": r["punch_in"].strftime("%H:%M:%S") if r["punch_in"] else "--:--",
                "punch_out_time": r["punch_out"].strftime("%H:%M:%S") if r["punch_out"] else "--:--"
            })

    return {
        "date": target_date,
        "summary": counts,
        "total_records": len(formatted),
        "attendance": formatted
    }

@router.get("/monthly")
def get_monthly_attendance(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None)
):
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{days_in_month:02d}"

    where_dept = "AND e.department = %s" if department else ""
    params = [start_date, end_date]
    if department:
        params.append(department)

    with get_db() as cur:
        # Fetch holidays for this month
        cur.execute("""
            SELECT holiday_name, holiday_date, holiday_type
            FROM hr_holidays
            WHERE holiday_date >= %s AND holiday_date <= %s
            ORDER BY holiday_date ASC;
        """, (start_date, end_date))
        holidays_raw = cur.fetchall()
        holidays_map = {h["holiday_date"].day: h["holiday_name"] for h in holidays_raw}

        # Fetch daily attendance for this month
        query = f"""
            SELECT 
                e.id as employee_id,
                e.employee_code,
                e.biometric_id,
                e.display_name,
                e.department,
                a.attendance_date,
                a.status,
                a.total_work_minutes,
                a.overtime_minutes
            FROM hr_employees e
            LEFT JOIN hr_attendance_daily a ON e.id = a.employee_id 
                AND a.attendance_date >= %s AND a.attendance_date <= %s
            WHERE e.status = 'ACTIVE' {where_dept}
            ORDER BY e.biometric_id ASC NULLS LAST, e.employee_code ASC, a.attendance_date ASC;
        """
        cur.execute(query, params)
        rows = cur.fetchall()

        emp_matrix = {}
        for row in rows:
            emp_id = str(row["employee_id"])
            if emp_id not in emp_matrix:
                emp_matrix[emp_id] = {
                    "employee_id": emp_id,
                    "employee_code": row["employee_code"],
                    "biometric_id": row["biometric_id"],
                    "display_name": row["display_name"],
                    "department": row["department"],
                    "days": {},
                    "present_count": 0,
                    "absent_count": 0,
                    "half_day_count": 0,
                    "total_ot_hours": 0.0
                }
            if row["attendance_date"]:
                day_num = row["attendance_date"].day
                status_short = "P" if row["status"] in ["PRESENT", "LATE"] else ("HD" if row["status"] == "HALF_DAY" else "A")
                emp_matrix[emp_id]["days"][day_num] = status_short
                if status_short == "P":
                    emp_matrix[emp_id]["present_count"] += 1
                elif status_short == "HD":
                    emp_matrix[emp_id]["half_day_count"] += 1
                    emp_matrix[emp_id]["present_count"] += 0.5
                else:
                    emp_matrix[emp_id]["absent_count"] += 1
                
                ot_hrs = (row["overtime_minutes"] or 0) / 60.0
                emp_matrix[emp_id]["total_ot_hours"] += ot_hrs

    return {
        "month": month,
        "year": year,
        "days_in_month": days_in_month,
        "holidays": [{"day": day, "name": name} for day, name in holidays_map.items()],
        "employees": list(emp_matrix.values())
    }

@router.get("/monthly/export-excel")
def export_monthly_attendance_excel(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None)
):
    """Generate and download publication-quality Excel Monthly Attendance Register"""
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{days_in_month:02d}"
    month_name = datetime(year, month, 1).strftime("%B %Y")

    with get_db() as cur:
        # Holidays
        cur.execute("SELECT holiday_date, holiday_name FROM hr_holidays WHERE holiday_date BETWEEN %s AND %s;", (start_date, end_date))
        holiday_days = {h["holiday_date"].day: h["holiday_name"] for h in cur.fetchall()}

        # Employees & Attendance
        where_dept = "AND e.department = %s" if department else ""
        params = [start_date, end_date]
        if department:
            params.append(department)

        cur.execute(f"""
            SELECT 
                e.id, e.employee_code, e.biometric_id, e.display_name, e.department,
                a.attendance_date, a.status, a.overtime_minutes
            FROM hr_employees e
            LEFT JOIN hr_attendance_daily a ON e.id = a.employee_id AND a.attendance_date BETWEEN %s AND %s
            WHERE e.status = 'ACTIVE' {where_dept}
            ORDER BY e.biometric_id ASC NULLS LAST, e.employee_code ASC;
        """, params)
        rows = cur.fetchall()

    emp_data = {}
    for r in rows:
        eid = str(r["id"])
        if eid not in emp_data:
            emp_data[eid] = {
                "code": r["employee_code"],
                "bio_id": r["biometric_id"] or "",
                "name": r["display_name"],
                "dept": r["department"],
                "days": {},
                "ot_hours": 0.0
            }
        if r["attendance_date"]:
            d_num = r["attendance_date"].day
            st = "P" if r["status"] in ["PRESENT", "LATE"] else ("HD" if r["status"] == "HALF_DAY" else "A")
            emp_data[eid]["days"][d_num] = st
            emp_data[eid]["ot_hours"] += (r["overtime_minutes"] or 0) / 60.0

    # Build Excel Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = f"Attendance {month_name}"
    ws.views.sheetView[0].showGridLines = True

    # Styles
    navy_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    teal_sub_fill = PatternFill(start_color="115E59", end_color="115E59", fill_type="solid")
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    sunday_header_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    holiday_header_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    p_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid") # Soft green
    hd_fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid") # Soft purple
    wo_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Soft gray
    h_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid") # Soft gold
    a_fill = PatternFill(start_color="FFE4E6", end_color="FFE4E6", fill_type="solid") # Soft rose

    title_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    sub_font = Font(name="Calibri", size=9, bold=False, color="E0F2FE")
    bold_10 = Font(name="Calibri", size=10, bold=True, color="1E293B")
    reg_9 = Font(name="Calibri", size=9)
    bold_9 = Font(name="Calibri", size=9, bold=True)

    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    right = Alignment(horizontal="right", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # 1. Company Header Rows
    total_cols = 4 + days_in_month + 3
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.cell(row=1, column=1, value=COMPANY_INFO["corporate_name"])
    ws.cell(row=1, column=1).font = title_font
    ws.cell(row=1, column=1).fill = navy_fill
    ws.cell(row=1, column=1).alignment = center
    ws.row_dimensions[1].height = 25

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws.cell(row=2, column=1, value=f"CIN: {COMPANY_INFO['cin']} | Registered Office: {COMPANY_INFO['registered_address']}")
    ws.cell(row=2, column=1).font = sub_font
    ws.cell(row=2, column=1).fill = teal_sub_fill
    ws.cell(row=2, column=1).alignment = center
    ws.row_dimensions[2].height = 18

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=total_cols)
    ws.cell(row=3, column=1, value=f"MONTHLY BIOMETRIC ATTENDANCE REGISTER – {month_name.upper()} (DEVICE 2: 192.168.31.111)")
    ws.cell(row=3, column=1).font = Font(name="Calibri", size=11, bold=True, color="0F766E")
    ws.cell(row=3, column=1).alignment = center
    ws.row_dimensions[3].height = 20

    # 2. Table Column Headers
    headers_row_1 = ["S.No", "Bio ID", "Code", "Employee Name"]
    for d in range(1, days_in_month + 1):
        headers_row_1.append(d)
    headers_row_1.extend(["Total Present", "Total Absent", "OT (Hours)"])

    headers_row_2 = ["", "", "", ""]
    for d in range(1, days_in_month + 1):
        dt = datetime(year, month, d)
        day_str = dt.strftime("%a")[:2] # Mo, Tu, We, Th, Fr, Sa, Su
        headers_row_2.append(day_str)
    headers_row_2.extend(["", "", ""])

    ws.append(headers_row_1)
    ws.append(headers_row_2)

    # Style header rows (Row 4 & 5)
    for col_idx in range(1, total_cols + 1):
        c1 = ws.cell(row=4, column=col_idx)
        c2 = ws.cell(row=5, column=col_idx)

        c1.alignment = center
        c2.alignment = center
        c1.font = bold_10
        c2.font = bold_9
        c1.border = thin_border
        c2.border = thin_border

        # Check if day column
        if 5 <= col_idx <= 4 + days_in_month:
            d_val = col_idx - 4
            is_sun = datetime(year, month, d_val).weekday() == 6
            is_hol = d_val in holiday_days
            if is_hol:
                c1.fill = holiday_header_fill
                c2.fill = holiday_header_fill
            elif is_sun:
                c1.fill = sunday_header_fill
                c2.fill = sunday_header_fill
            else:
                c1.fill = header_fill
                c2.fill = header_fill
        else:
            c1.fill = header_fill
            c2.fill = header_fill

    # Merge static headers across row 4 & 5
    for c in [1, 2, 3, 4, total_cols - 2, total_cols - 1, total_cols]:
        ws.merge_cells(start_row=4, start_column=c, end_row=5, end_column=c)

    # 3. Employee Data Rows
    today_dt = date.today()
    is_curr_m = (today_dt.year == year and today_dt.month == month)
    today_d = today_dt.day if is_curr_m else (days_in_month if today_dt > date(year, month, days_in_month) else 0)

    row_num = 6
    for idx, (eid, emp) in enumerate(emp_data.items(), 1):
        row_cells = [idx, emp["bio_id"], emp["code"], emp["name"]]
        p_cnt = 0.0
        a_cnt = 0.0

        for d in range(1, days_in_month + 1):
            is_sun = datetime(year, month, d).weekday() == 6
            is_hol = d in holiday_days
            p_val = emp["days"].get(d)

            if p_val == "P":
                badge = "P"
                p_cnt += 1.0
            elif p_val == "HD":
                badge = "HD"
                p_cnt += 0.5
                a_cnt += 0.5
            elif d <= today_d:
                if is_hol:
                    badge = "H"
                    p_cnt += 1.0 # Paid holiday
                elif is_sun:
                    badge = "WO"
                    p_cnt += 1.0 # Paid week off
                else:
                    badge = "A"
                    a_cnt += 1.0
            else:
                badge = "-"

            row_cells.append(badge)

        row_cells.extend([p_cnt, a_cnt, round(emp["ot_hours"], 1)])
        ws.append(row_cells)

        # Style data cells
        ws.cell(row=row_num, column=1).alignment = center
        ws.cell(row=row_num, column=2).alignment = center
        ws.cell(row=row_num, column=3).alignment = center
        ws.cell(row=row_num, column=4).alignment = left

        for c in range(1, total_cols + 1):
            cell = ws.cell(row=row_num, column=c)
            cell.border = thin_border
            cell.font = reg_9

            if 5 <= c <= 4 + days_in_month:
                cell.alignment = center
                val = str(cell.value)
                if val == "P":
                    cell.fill = p_fill
                    cell.font = bold_9
                elif val == "HD":
                    cell.fill = hd_fill
                    cell.font = bold_9
                elif val == "H":
                    cell.fill = h_fill
                    cell.font = bold_9
                elif val == "WO":
                    cell.fill = wo_fill
                elif val == "A":
                    cell.fill = a_fill
            elif c > 4 + days_in_month:
                cell.alignment = center
                cell.font = bold_9

        row_num += 1

    # Freeze panes on Employee Name
    ws.freeze_panes = "E6"

    # Set Column Widths
    ws.column_dimensions['A'].width = 6   # S.No
    ws.column_dimensions['B'].width = 8   # Bio ID
    ws.column_dimensions['C'].width = 11  # Code
    ws.column_dimensions['D'].width = 24  # Name
    for d in range(1, days_in_month + 1):
        col_letter = get_column_letter(4 + d)
        ws.column_dimensions[col_letter].width = 4.5
    ws.column_dimensions[get_column_letter(total_cols - 2)].width = 13
    ws.column_dimensions[get_column_letter(total_cols - 1)].width = 13
    ws.column_dimensions[get_column_letter(total_cols)].width = 12

    # Save to buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"SV_DREEAMPLANNERS_Attendance_{year}_{month:02d}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/monthly/export-pdf")
def export_monthly_attendance_pdf(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None)
):
    """Generate and download landscape PDF Monthly Attendance Register"""
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{days_in_month:02d}"
    month_name = datetime(year, month, 1).strftime("%B %Y")

    filename = f"Attendance_Register_{year}_{month:02d}.pdf"
    filepath = os.path.join(PAYSLIP_DIR, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24
    )

    styles = getSampleStyleSheet()
    normal = styles['Normal']

    title_style = ParagraphStyle('Title', parent=normal, fontName='Helvetica-Bold', fontSize=14, leading=16, alignment=1, textColor=colors.HexColor('#0F766E'))
    sub_style = ParagraphStyle('Sub', parent=normal, fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#64748B'))
    hdr_style = ParagraphStyle('Hdr', parent=normal, fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#FFFFFF'))
    cell_style = ParagraphStyle('Cell', parent=normal, fontName='Helvetica', fontSize=7.5, leading=9, textColor=colors.HexColor('#1E293B'))
    cell_bold = ParagraphStyle('CellB', parent=normal, fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor('#0F172A'))

    with get_db() as cur:
        # Holidays
        cur.execute("SELECT holiday_date, holiday_name FROM hr_holidays WHERE holiday_date BETWEEN %s AND %s;", (start_date, end_date))
        holidays_list = cur.fetchall()

        # Employees summary
        where_dept = "AND e.department = %s" if department else ""
        params = [start_date, end_date]
        if department:
            params.append(department)

        cur.execute(f"""
            SELECT 
                e.employee_code,
                e.biometric_id,
                e.display_name,
                e.department,
                COUNT(a.id) FILTER (WHERE a.status = 'PRESENT') as present_days,
                COUNT(a.id) FILTER (WHERE a.status = 'HALF_DAY') as half_days,
                COUNT(a.id) FILTER (WHERE a.status = 'LATE') as late_days,
                COALESCE(SUM(a.overtime_minutes), 0) as total_ot_mins
            FROM hr_employees e
            LEFT JOIN hr_attendance_daily a ON e.id = a.employee_id AND a.attendance_date BETWEEN %s AND %s
            WHERE e.status = 'ACTIVE' {where_dept}
            GROUP BY e.id, e.employee_code, e.biometric_id, e.display_name, e.department
            ORDER BY e.biometric_id ASC NULLS LAST, e.employee_code ASC;
        """, params)
        staff_summary = cur.fetchall()

    story = []

    # Title Banner
    story.append(Paragraph(COMPANY_INFO["corporate_name"], title_style))
    story.append(Paragraph(f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}", sub_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0F766E'), spaceBefore=2, spaceAfter=6))
    story.append(Paragraph(f"<b>MONTHLY ATTENDANCE REGISTER SUMMARY – {month_name.upper()} (DEVICE 2: 192.168.31.111)</b>", ParagraphStyle('RptTitle', parent=normal, fontName='Helvetica-Bold', fontSize=10, alignment=1, textColor=colors.HexColor('#1E293B'))))
    story.append(Spacer(1, 6))

    # Holiday info note
    hol_text = ", ".join([f"{h['holiday_date'].strftime('%d-%b')}: {h['holiday_name']}" for h in holidays_list])
    if hol_text:
        story.append(Paragraph(f"<b>Public Holidays this month:</b> {hol_text}", ParagraphStyle('HolTxt', parent=normal, fontName='Helvetica-Oblique', fontSize=7.5, textColor=colors.HexColor('#B45309'))))
        story.append(Spacer(1, 6))

    # Summary Table
    table_data = [
        [
            Paragraph("<b>S.No</b>", hdr_style),
            Paragraph("<b>Bio ID</b>", hdr_style),
            Paragraph("<b>Emp Code</b>", hdr_style),
            Paragraph("<b>Employee Name</b>", hdr_style),
            Paragraph("<b>Department</b>", hdr_style),
            Paragraph("<b>Present Days</b>", hdr_style),
            Paragraph("<b>Half Days</b>", hdr_style),
            Paragraph("<b>Late Days</b>", hdr_style),
            Paragraph("<b>Absent Days</b>", hdr_style),
            Paragraph("<b>Overtime (Hrs)</b>", hdr_style)
        ]
    ]

    for idx, s in enumerate(staff_summary, 1):
        p = s["present_days"] + s["late_days"]
        hd = s["half_days"]
        ot_hrs = round((s["total_ot_mins"] or 0) / 60.0, 1)
        # Approximate absent for current period
        curr_days = min(datetime.now().day if datetime.now().month == month else days_in_month, days_in_month)
        sundays = len([d for d in range(1, curr_days + 1) if datetime(year, month, d).weekday() == 6])
        absent = max(0, curr_days - p - (hd * 0.5) - sundays)

        table_data.append([
            Paragraph(str(idx), cell_bold),
            Paragraph(str(s["biometric_id"] or '-'), cell_bold),
            Paragraph(s["employee_code"], cell_bold),
            Paragraph(s["display_name"], cell_style),
            Paragraph(s["department"] or "Operations", cell_style),
            Paragraph(str(p), cell_bold),
            Paragraph(str(hd), cell_bold),
            Paragraph(str(s["late_days"]), cell_bold),
            Paragraph(str(absent), cell_bold),
            Paragraph(f"{ot_hrs} hrs", cell_bold)
        ])

    summary_table = Table(table_data, colWidths=[30, 45, 60, 190, 120, 65, 55, 55, 65, 75])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F766E')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 15))

    # Signatures
    sig_data = [
        [
            Paragraph("<b>Prepared By:</b> HR Department<br/><br/>______________________", cell_style),
            Paragraph("<b>Verified By:</b> Head of Operations<br/><br/>______________________", cell_style),
            Paragraph("<b>Approved By:</b> Director / Managing Director<br/><br/>______________________", cell_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260, 260])
    story.append(sig_table)

    doc.build(story)
    return FileResponse(filepath, filename=filename, media_type="application/pdf")

@router.post("/manual")
def manual_attendance_override(data: ManualAttendanceSchema):
    with get_db() as cur:
        total_mins = 0
        if data.punch_in and data.punch_out:
            total_mins = max(0, int((data.punch_out - data.punch_in).total_seconds() / 60))

        cur.execute("""
            INSERT INTO hr_attendance_daily (
                employee_id, attendance_date, punch_in, punch_out,
                total_work_minutes, status, is_manual_override, override_reason
            ) VALUES (
                %s, %s, %s, %s, %s, %s, TRUE, %s
            )
            ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
                punch_in = EXCLUDED.punch_in,
                punch_out = EXCLUDED.punch_out,
                total_work_minutes = EXCLUDED.total_work_minutes,
                status = EXCLUDED.status,
                is_manual_override = TRUE,
                override_reason = EXCLUDED.override_reason,
                updated_at = CURRENT_TIMESTAMP;
        """, (
            data.employee_id, data.attendance_date, data.punch_in, data.punch_out,
            total_mins, data.status, data.override_reason
        ))

    return {"success": True, "message": "Attendance record updated manually"}

@router.get("/live-punches")
def get_live_punches(limit: int = 25):
    with get_db() as cur:
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
            LIMIT %s;
        """, (limit,))
        punches = cur.fetchall()

    return {"punches": punches}


# ======================================================================
# MONTHLY DETAIL REPORT (PUNCH IN / OUT & ABSENT/PRESENT PERCENTAGE)
# ======================================================================

def _calculate_monthly_detail_data(cur, month: int, year: int, department: Optional[str] = None, employee_id: Optional[str] = None, search: Optional[str] = None):
    """
    Computes accurate monthly attendance detail with:
    - Daily punch in and punch out times
    - Total work hours and overtime hours
    - Standard working days (excluding Sundays and official holidays)
    - Elapsed working days (up to current date for current month)
    - Present percentage & Absent percentage
    """
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{days_in_month:02d}"
    month_name = datetime(year, month, 1).strftime("%B %Y")

    today = date.today()
    if year == today.year and month == today.month:
        elapsed_days = min(today.day, days_in_month)
    elif date(year, month, days_in_month) < today:
        elapsed_days = days_in_month
    else:
        elapsed_days = 0

    # 1. Holidays
    cur.execute("SELECT holiday_date, holiday_name FROM hr_holidays WHERE holiday_date BETWEEN %s AND %s;", (start_date, end_date))
    holiday_map = {h["holiday_date"]: h["holiday_name"] for h in cur.fetchall()}

    # 2. Calendar metrics
    total_sundays = 0
    total_holidays = 0
    total_working_days = 0
    elapsed_working_days = 0

    for d in range(1, days_in_month + 1):
        dt = date(year, month, d)
        is_sun = (dt.weekday() == 6)
        is_hol = (dt in holiday_map)
        if is_sun:
            total_sundays += 1
        elif is_hol:
            total_holidays += 1
        else:
            total_working_days += 1
            if d <= elapsed_days:
                elapsed_working_days += 1

    working_baseline = elapsed_working_days if elapsed_working_days > 0 else total_working_days

    # 3. Filter employees
    where_clauses = ["e.status = 'ACTIVE'"]
    params = []

    if isinstance(department, str) and department.strip() and department.upper() != 'ALL':
        where_clauses.append("e.department = %s")
        params.append(department.strip())

    if isinstance(employee_id, str) and employee_id.strip() and employee_id.upper() != 'ALL':
        where_clauses.append("e.id = %s::uuid")
        params.append(employee_id.strip())

    if isinstance(search, str) and search.strip():
        s_term = f"%{search.strip()}%"
        where_clauses.append("(e.display_name ILIKE %s OR e.employee_code ILIKE %s OR e.biometric_id::text ILIKE %s)")
        params.extend([s_term, s_term, s_term])

    where_sql = " AND ".join(where_clauses)
    query = f"""
        SELECT 
            e.id,
            e.employee_code,
            e.biometric_id,
            e.display_name,
            e.department,
            e.designation,
            COALESCE(s.name, 'General Shift') as shift_name,
            COALESCE(s.start_time::text, '09:00:00') as shift_start,
            COALESCE(s.end_time::text, '18:00:00') as shift_end
        FROM hr_employees e
        LEFT JOIN hr_shifts s ON e.shift_id = s.id
        WHERE {where_sql}
        ORDER BY e.biometric_id ASC NULLS LAST, e.employee_code ASC;
    """
    cur.execute(query, params)
    employees = cur.fetchall()

    if not employees:
        return {
            "month": month,
            "year": year,
            "month_name": month_name,
            "days_in_month": days_in_month,
            "elapsed_days": elapsed_days,
            "working_days": working_baseline,
            "total_working_days": total_working_days,
            "total_sundays": total_sundays,
            "total_holidays": total_holidays,
            "holidays": [{"date": dt.strftime("%Y-%m-%d"), "name": name} for dt, name in holiday_map.items()],
            "summary_stats": {
                "total_employees": 0,
                "total_present_days": 0.0,
                "total_absent_days": 0.0,
                "avg_present_percent": 0.0,
                "avg_absent_percent": 0.0,
                "total_work_hours": 0.0,
                "total_ot_hours": 0.0
            },
            "employees": []
        }

    emp_ids = [e["id"] for e in employees]

    # 4. Fetch Attendance records
    cur.execute("""
        SELECT 
            employee_id,
            attendance_date,
            punch_in,
            punch_out,
            COALESCE(total_work_minutes, 0) as total_work_minutes,
            COALESCE(overtime_minutes, 0) as overtime_minutes,
            COALESCE(late_minutes, 0) as late_minutes,
            status
        FROM hr_attendance_daily
        WHERE employee_id = ANY(%s::uuid[]) AND attendance_date BETWEEN %s AND %s;
    """, (emp_ids, start_date, end_date))
    att_rows = cur.fetchall()

    att_map = {}
    for r in att_rows:
        eid = str(r["employee_id"])
        if eid not in att_map:
            att_map[eid] = {}
        att_map[eid][r["attendance_date"]] = r

    # 5. Build Employee Records
    emp_results = []
    tot_pres_all = 0.0
    tot_abs_all = 0.0
    tot_hrs_all = 0.0
    tot_ot_all = 0.0

    for emp in employees:
        eid = str(emp["id"])
        emp_atts = att_map.get(eid, {})

        pres_days = 0.0
        abs_days = 0.0
        half_days = 0
        late_days = 0
        sun_worked = 0
        hol_worked = 0
        tot_work_mins = 0
        tot_ot_mins = 0
        daily_records = []

        for d in range(1, days_in_month + 1):
            dt = date(year, month, d)
            is_sun = (dt.weekday() == 6)
            is_hol = (dt in holiday_map)
            hol_name = holiday_map.get(dt)
            is_future = (d > elapsed_days)

            rec = emp_atts.get(dt)
            if rec and rec["punch_in"]:
                p_in = rec["punch_in"]
                p_out = rec["punch_out"]
                w_mins = rec["total_work_minutes"] or 0
                ot_mins = rec["overtime_minutes"] or 0
                l_mins = rec["late_minutes"] or 0
                status_raw = rec["status"]

                p_in_str = p_in.strftime("%H:%M:%S")
                p_out_str = p_out.strftime("%H:%M:%S") if (p_out and p_out != p_in) else "--:--"

                if status_raw == "HALF_DAY":
                    status_badge = "HALF_DAY"
                    pres_days += 0.5
                    abs_days += 0.5
                    half_days += 1
                else:
                    if l_mins > 0:
                        status_badge = "LATE"
                        late_days += 1
                    else:
                        status_badge = "PRESENT"
                    pres_days += 1.0

                if is_sun:
                    sun_worked += 1
                if is_hol:
                    hol_worked += 1

                tot_work_mins += w_mins
                tot_ot_mins += ot_mins
            else:
                p_in_str = "--:--"
                p_out_str = "--:--"
                w_mins = 0
                ot_mins = 0
                l_mins = 0

                if is_future:
                    status_badge = "UPCOMING"
                elif is_hol:
                    status_badge = "HOLIDAY"
                elif is_sun:
                    status_badge = "SUNDAY"
                else:
                    status_badge = "ABSENT"
                    abs_days += 1.0

            w_hrs = round(w_mins / 60.0, 1)
            ot_hrs = round(ot_mins / 60.0, 1)

            daily_records.append({
                "day": d,
                "date": dt.strftime("%Y-%m-%d"),
                "day_name": dt.strftime("%a"),
                "shift": f"{emp['shift_start'][:5]} - {emp['shift_end'][:5]}",
                "punch_in": p_in_str,
                "punch_out": p_out_str,
                "work_minutes": w_mins,
                "work_hours": w_hrs,
                "work_time_str": f"{w_mins // 60}h {w_mins % 60}m" if w_mins > 0 else "--",
                "overtime_minutes": ot_mins,
                "ot_hours": ot_hrs,
                "ot_time_str": f"{ot_mins // 60}h {ot_mins % 60}m" if ot_mins > 0 else "--",
                "late_minutes": l_mins,
                "status": status_badge,
                "is_sunday": is_sun,
                "is_holiday": is_hol,
                "holiday_name": hol_name,
                "is_future": is_future
            })

        # Absent & Present Percentages calculated on Working Days baseline
        if working_baseline > 0:
            abs_pct = round((abs_days / working_baseline) * 100.0, 1)
            abs_pct = max(0.0, min(100.0, abs_pct))
            pres_pct = round(100.0 - abs_pct, 1)
        else:
            abs_pct = 0.0
            pres_pct = 0.0

        emp_work_hrs = round(tot_work_mins / 60.0, 1)
        emp_ot_hrs = round(tot_ot_mins / 60.0, 1)

        tot_pres_all += pres_days
        tot_abs_all += abs_days
        tot_hrs_all += emp_work_hrs
        tot_ot_all += emp_ot_hrs

        emp_results.append({
            "employee_id": eid,
            "employee_code": emp["employee_code"],
            "biometric_id": emp["biometric_id"],
            "display_name": emp["display_name"],
            "department": emp["department"],
            "designation": emp["designation"],
            "shift_name": emp["shift_name"],
            "shift_start": emp["shift_start"],
            "shift_end": emp["shift_end"],
            "working_days": working_baseline,
            "present_days": pres_days,
            "absent_days": abs_days,
            "half_days": half_days,
            "late_days": late_days,
            "sundays_worked": sun_worked,
            "holidays_worked": hol_worked,
            "present_percent": pres_pct,
            "absent_percent": abs_pct,
            "total_work_minutes": tot_work_mins,
            "total_work_hours": emp_work_hrs,
            "total_ot_minutes": tot_ot_mins,
            "total_ot_hours": emp_ot_hrs,
            "daily_records": daily_records
        })

    total_emps = len(emp_results)
    avg_pres_pct = round(sum(e["present_percent"] for e in emp_results) / total_emps, 1) if total_emps > 0 else 0.0
    avg_abs_pct = round(sum(e["absent_percent"] for e in emp_results) / total_emps, 1) if total_emps > 0 else 0.0

    return {
        "month": month,
        "year": year,
        "month_name": month_name,
        "days_in_month": days_in_month,
        "elapsed_days": elapsed_days,
        "working_days": working_baseline,
        "total_working_days": total_working_days,
        "total_sundays": total_sundays,
        "total_holidays": total_holidays,
        "holidays": [{"date": dt.strftime("%Y-%m-%d"), "name": name} for dt, name in holiday_map.items()],
        "summary_stats": {
            "total_employees": total_emps,
            "total_present_days": round(tot_pres_all, 1),
            "total_absent_days": round(tot_abs_all, 1),
            "avg_present_percent": avg_pres_pct,
            "avg_absent_percent": avg_abs_pct,
            "total_work_hours": round(tot_hrs_all, 1),
            "total_ot_hours": round(tot_ot_all, 1)
        },
        "employees": emp_results
    }


@router.get("/monthly-detail")
def get_monthly_detail_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    with get_db() as cur:
        return _calculate_monthly_detail_data(cur, month, year, department, employee_id, search)


@router.get("/monthly-detail/export-excel")
def export_monthly_detail_excel(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None)
):
    """
    Exports a publication-grade Excel workbook:
    - If employee_id is specified: Detailed single employee monthly punch card with daily in/out times and Absent %
    - If employee_id is None / ALL: Master monthly report with Staff Summary (Absent %) and full Daily Punch In/Out Log
    """
    with get_db() as cur:
        data = _calculate_monthly_detail_data(cur, month, year, department, employee_id)

    wb = Workbook()
    
    # Styles
    navy_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    teal_sub_fill = PatternFill(start_color="115E59", end_color="115E59", fill_type="solid")
    hdr_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    p_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    a_fill = PatternFill(start_color="FFE4E6", end_color="FFE4E6", fill_type="solid")
    hd_fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")
    h_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    wo_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    title_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    sub_font = Font(name="Calibri", size=9, color="E0F2FE")
    bold_10 = Font(name="Calibri", size=10, bold=True, color="0F172A")
    bold_9 = Font(name="Calibri", size=9, bold=True)
    reg_9 = Font(name="Calibri", size=9)

    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    is_single_emp = bool(isinstance(employee_id, str) and employee_id.upper() != 'ALL' and len(data["employees"]) == 1)

    if is_single_emp:
        emp = data["employees"][0]
        ws = wb.active
        ws.title = f"{emp['employee_code']} Punch Card"
        ws.views.sheetView[0].showGridLines = True

        # Header
        ws.merge_cells("A1:J1")
        ws["A1"] = COMPANY_INFO["corporate_name"]
        ws["A1"].font = title_font
        ws["A1"].fill = navy_fill
        ws["A1"].alignment = center
        ws.row_dimensions[1].height = 24

        ws.merge_cells("A2:J2")
        ws["A2"] = f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}"
        ws["A2"].font = sub_font
        ws["A2"].fill = teal_sub_fill
        ws["A2"].alignment = center
        ws.row_dimensions[2].height = 18

        ws.merge_cells("A3:J3")
        ws["A3"] = f"MONTHLY BIOMETRIC TIME CARD WITH PUNCH IN / OUT – {data['month_name'].upper()}"
        ws["A3"].font = Font(name="Calibri", size=11, bold=True, color="0F766E")
        ws["A3"].alignment = center
        ws.row_dimensions[3].height = 20

        # Profile Box
        ws.merge_cells("A5:B5"); ws["A5"] = "Staff Name:"; ws["A5"].font = bold_10
        ws.merge_cells("C5:E5"); ws["C5"] = emp["display_name"]; ws["C5"].font = bold_10
        ws["F5"] = "Emp Code:"; ws["F5"].font = bold_10
        ws["G5"] = emp["employee_code"]
        ws["H5"] = "Biometric ID:"; ws["H5"].font = bold_10
        ws["I5"] = emp["biometric_id"]

        ws.merge_cells("A6:B6"); ws["A6"] = "Department:"; ws["A6"].font = bold_9
        ws.merge_cells("C6:E6"); ws["C6"] = emp["department"]
        ws["F6"] = "Designation:"; ws["F6"].font = bold_9
        ws["G6"] = emp["designation"]
        ws["H6"] = "Shift:"; ws["H6"].font = bold_9
        ws["I6"] = f"{emp['shift_name']} ({emp['shift_start'][:5]} - {emp['shift_end'][:5]})"

        # KPI Summary Box
        ws.merge_cells("A8:B8"); ws["A8"] = "Working Days"; ws["A8"].font = bold_9; ws["A8"].alignment = center; ws["A8"].fill = hdr_fill
        ws.merge_cells("C8:D8"); ws["C8"] = "Present Days"; ws["C8"].font = bold_9; ws["C8"].alignment = center; ws["C8"].fill = p_fill
        ws.merge_cells("E8:F8"); ws["E8"] = "Absent Days"; ws["E8"].font = bold_9; ws["E8"].alignment = center; ws["E8"].fill = a_fill
        ws.merge_cells("G8:H8"); ws["G8"] = "Present %"; ws["G8"].font = bold_10; ws["G8"].alignment = center; ws["G8"].fill = p_fill
        ws.merge_cells("I8:J8"); ws["I8"] = "Absent %"; ws["I8"].font = bold_10; ws["I8"].alignment = center; ws["I8"].fill = a_fill

        ws.merge_cells("A9:B9"); ws["A9"] = emp["working_days"]; ws["A9"].font = bold_10; ws["A9"].alignment = center
        ws.merge_cells("C9:D9"); ws["C9"] = emp["present_days"]; ws["C9"].font = bold_10; ws["C9"].alignment = center
        ws.merge_cells("E9:F9"); ws["E9"] = emp["absent_days"]; ws["E9"].font = bold_10; ws["E9"].alignment = center
        ws.merge_cells("G9:H9"); ws["G9"] = f"{emp['present_percent']}%"; ws["G9"].font = bold_10; ws["G9"].alignment = center
        ws.merge_cells("I9:J9"); ws["I9"] = f"{emp['absent_percent']}%"; ws["I9"].font = bold_10; ws["I9"].alignment = center

        for r_k in range(8, 10):
            for c_k in range(1, 11):
                ws.cell(row=r_k, column=c_k).border = thin_border

        daily_hdrs = ["Day", "Date", "Weekday", "Shift", "Punch In Time", "Punch Out Time", "Total Hours", "Overtime", "Late (Mins)", "Status"]
        d_row_start = 11
        for col_i, h in enumerate(daily_hdrs, 1):
            c = ws.cell(row=d_row_start, column=col_i, value=h)
            c.fill = hdr_fill
            c.font = bold_10
            c.alignment = center
            c.border = thin_border

        ws.row_dimensions[d_row_start].height = 20

        for idx, day_rec in enumerate(emp["daily_records"], start=d_row_start + 1):
            ws.append([
                day_rec["day"],
                day_rec["date"],
                day_rec["day_name"],
                day_rec["shift"],
                day_rec["punch_in"],
                day_rec["punch_out"],
                day_rec["work_time_str"],
                day_rec["ot_time_str"],
                day_rec["late_minutes"] if day_rec["late_minutes"] > 0 else "-",
                day_rec["status"]
            ])
            for col_i in range(1, len(daily_hdrs) + 1):
                cell = ws.cell(row=idx, column=col_i)
                cell.border = thin_border
                cell.alignment = center
                cell.font = reg_9

                if col_i == 5 and day_rec["punch_in"] != "--:--":
                    cell.font = bold_9
                elif col_i == 6 and day_rec["punch_out"] != "--:--":
                    cell.font = bold_9
                elif col_i == 10:
                    st = day_rec["status"]
                    cell.font = bold_9
                    if st in ["PRESENT", "LATE"]:
                        cell.fill = p_fill
                    elif st == "HALF_DAY":
                        cell.fill = hd_fill
                    elif st == "ABSENT":
                        cell.fill = a_fill
                    elif st == "SUNDAY":
                        cell.fill = wo_fill
                    elif st == "HOLIDAY":
                        cell.fill = h_fill

        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 10
        ws.column_dimensions['D'].width = 14
        ws.column_dimensions['E'].width = 16
        ws.column_dimensions['F'].width = 16
        ws.column_dimensions['G'].width = 13
        ws.column_dimensions['H'].width = 13
        ws.column_dimensions['I'].width = 12
        ws.column_dimensions['J'].width = 14

        filename = f"SVD_PunchDetail_{emp['employee_code']}_{year}_{month:02d}.xlsx"

    else:
        # All-Staff Master Workbook
        # Sheet 1: 3-Row Muster Register (Status P/A, Punch In, Punch Out)
        ws_3row = wb.active
        ws_3row.title = "3-Row Attendance Register"
        ws_3row.views.sheetView[0].showGridLines = True

        days_count = data["days_in_month"]
        total_3row_cols = 6 + days_count + 7
        max_col_letter = get_column_letter(total_3row_cols)

        # Title Rows
        ws_3row.merge_cells(f"A1:{max_col_letter}1")
        ws_3row["A1"] = f"CIVMASTERPRO – {COMPANY_INFO['corporate_name']}"
        ws_3row["A1"].font = title_font
        ws_3row["A1"].fill = navy_fill
        ws_3row["A1"].alignment = center
        ws_3row.row_dimensions[1].height = 24

        ws_3row.merge_cells(f"A2:{max_col_letter}2")
        ws_3row["A2"] = f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}"
        ws_3row["A2"].font = sub_font
        ws_3row["A2"].fill = teal_sub_fill
        ws_3row["A2"].alignment = center
        ws_3row.row_dimensions[2].height = 18

        ws_3row.merge_cells(f"A3:{max_col_letter}3")
        ws_3row["A3"] = f"MONTHLY 3-ROW ATTENDANCE REGISTER (STATUS P/A, PUNCH IN, PUNCH OUT) – {data['month_name'].upper()} {data['year']}"
        ws_3row["A3"].font = Font(name="Calibri", size=11, bold=True, color="0F766E")
        ws_3row["A3"].alignment = center
        ws_3row.row_dimensions[3].height = 20

        # Headers Row 4
        base_hdrs = ["S.No", "Bio ID", "Emp Code", "Staff Name", "Department", "Metric"]
        for col_idx, h in enumerate(base_hdrs, 1):
            c = ws_3row.cell(row=4, column=col_idx, value=h)
            c.fill = hdr_fill
            c.font = bold_10
            c.border = thin_border
            c.alignment = center

        for d in range(1, days_count + 1):
            dt = date(year, month, d)
            day_name = dt.strftime("%a")
            c = ws_3row.cell(row=4, column=6 + d, value=f"{d}\n{day_name[:2]}")
            c.fill = PatternFill(start_color="FEF3C7" if dt in holiday_map else ("E2E8F0" if dt.weekday() == 6 else "F1F5F9"), fill_type="solid")
            c.font = Font(name="Calibri", size=8.5, bold=True)
            c.border = thin_border
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        end_hdrs = ["Present Days", "Absent Days", "Half Days", "Present %", "Absent %", "Work Hours", "OT Hours"]
        for idx_h, eh in enumerate(end_hdrs):
            c = ws_3row.cell(row=4, column=6 + days_count + 1 + idx_h, value=eh)
            c.fill = hdr_fill
            c.font = bold_9
            c.border = thin_border
            c.alignment = center

        ws_3row.row_dimensions[4].height = 26

        # Fill 3 Rows per employee
        cur_r = 5
        for idx, emp in enumerate(data["employees"], 1):
            r1 = cur_r
            r2 = cur_r + 1
            r3 = cur_r + 2

            day_map = {rec["day"]: rec for rec in emp.get("daily_records", [])}

            # Left Columns
            ws_3row.cell(row=r1, column=1, value=idx)
            ws_3row.cell(row=r1, column=2, value=emp["biometric_id"] or "")
            ws_3row.cell(row=r1, column=3, value=emp["employee_code"])
            ws_3row.cell(row=r1, column=4, value=emp["display_name"])
            ws_3row.cell(row=r1, column=5, value=emp["department"])

            ws_3row.cell(row=r1, column=6, value="STATUS")
            ws_3row.cell(row=r2, column=6, value="PUNCH IN")
            ws_3row.cell(row=r3, column=6, value="PUNCH OUT")

            ws_3row.cell(row=r1, column=6).font = bold_9
            ws_3row.cell(row=r2, column=6).font = Font(name="Calibri", size=8.5, color="047857", bold=True)
            ws_3row.cell(row=r3, column=6).font = Font(name="Calibri", size=8.5, color="1D4ED8", bold=True)

            # Day columns for this employee
            for d in range(1, days_count + 1):
                col_i = 6 + d
                rec = day_map.get(d)

                c1 = ws_3row.cell(row=r1, column=col_i)
                c1.alignment = center
                c1.font = bold_9
                c1.border = thin_border

                c2 = ws_3row.cell(row=r2, column=col_i)
                c2.alignment = center
                c2.font = Font(name="Consolas", size=8)
                c2.border = thin_border

                c3 = ws_3row.cell(row=r3, column=col_i)
                c3.alignment = center
                c3.font = Font(name="Consolas", size=8)
                c3.border = thin_border

                if rec:
                    st = rec.get("status")
                    if st == "PRESENT":
                        c1.value = "P"; c1.fill = p_fill
                    elif st == "LATE":
                        c1.value = "L"; c1.fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
                    elif st == "HALF_DAY":
                        c1.value = "HD"; c1.fill = hd_fill
                    elif st == "ABSENT":
                        c1.value = "A"; c1.fill = a_fill
                    elif st == "SUNDAY":
                        c1.value = "WO"; c1.fill = wo_fill
                    elif st == "HOLIDAY":
                        c1.value = "H"; c1.fill = h_fill
                    else:
                        c1.value = "-"

                    p_in = rec.get("punch_in")
                    c2.value = p_in[:5] if p_in and p_in != "--:--" else "--"

                    p_out = rec.get("punch_out")
                    c3.value = p_out[:5] if p_out and p_out != "--:--" else "--"
                else:
                    c1.value = "-"
                    c2.value = "--"
                    c3.value = "--"

            # Summary values in Row 1
            ws_3row.cell(row=r1, column=7 + days_count, value=emp["present_days"])
            ws_3row.cell(row=r1, column=8 + days_count, value=emp["absent_days"])
            ws_3row.cell(row=r1, column=9 + days_count, value=emp["half_days"])
            ws_3row.cell(row=r1, column=10 + days_count, value=f"{emp['present_percent']}%")
            ws_3row.cell(row=r1, column=11 + days_count, value=f"{emp['absent_percent']}%")
            ws_3row.cell(row=r1, column=12 + days_count, value=emp["total_work_hours"])
            ws_3row.cell(row=r1, column=13 + days_count, value=emp["total_ot_hours"])

            # Merge left cells across r1:r3
            for col_i in range(1, 6):
                ws_3row.merge_cells(start_row=r1, start_column=col_i, end_row=r3, end_column=col_i)
                top_c = ws_3row.cell(row=r1, column=col_i)
                top_c.alignment = left if col_i in [4, 5] else center
                top_c.font = bold_9 if col_i in [2, 3, 4] else reg_9

            # Merge summary cells across r1:r3
            for col_i in range(7 + days_count, 14 + days_count):
                ws_3row.merge_cells(start_row=r1, start_column=col_i, end_row=r3, end_column=col_i)
                top_c = ws_3row.cell(row=r1, column=col_i)
                top_c.alignment = center
                top_c.font = bold_9
                if col_i == 10 + days_count and emp["present_percent"] >= 80:
                    top_c.fill = p_fill
                elif col_i == 11 + days_count and emp["absent_percent"] > 20:
                    top_c.fill = a_fill

            for r_idx in range(r1, r3 + 1):
                for col_i in range(1, total_3row_cols + 1):
                    ws_3row.cell(row=r_idx, column=col_i).border = thin_border

            cur_r += 3

        ws_3row.column_dimensions['A'].width = 6
        ws_3row.column_dimensions['B'].width = 8
        ws_3row.column_dimensions['C'].width = 12
        ws_3row.column_dimensions['D'].width = 24
        ws_3row.column_dimensions['E'].width = 18
        ws_3row.column_dimensions['F'].width = 13
        for d in range(1, days_count + 1):
            ws_3row.column_dimensions[get_column_letter(6 + d)].width = 7.5
        for col_i in range(7 + days_count, 14 + days_count):
            ws_3row.column_dimensions[get_column_letter(col_i)].width = 12

        ws_3row.freeze_panes = "G5"

        # Sheet 2: Summary Table
        ws_sum = wb.create_sheet(title="Staff Summary & %")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.merge_cells("A1:N1")
        ws_sum["A1"] = f"CIVMASTERPRO – {COMPANY_INFO['corporate_name']}"
        ws_sum["A1"].font = title_font
        ws_sum["A1"].fill = navy_fill
        ws_sum["A1"].alignment = center
        ws_sum.row_dimensions[1].height = 24

        ws_sum.merge_cells("A2:N2")
        ws_sum["A2"] = f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}"
        ws_sum["A2"].font = sub_font
        ws_sum["A2"].fill = teal_sub_fill
        ws_sum["A2"].alignment = center
        ws_sum.row_dimensions[2].height = 18

        ws_sum.merge_cells("A3:N3")
        ws_sum["A3"] = f"MONTHLY ATTENDANCE DETAIL & ABSENT/PRESENT PERCENTAGE REGISTER – {data['month_name'].upper()}"
        ws_sum["A3"].font = Font(name="Calibri", size=11, bold=True, color="0F766E")
        ws_sum["A3"].alignment = center
        ws_sum.row_dimensions[3].height = 20

        sum_headers = [
            "S.No", "Bio ID", "Emp Code", "Employee Name", "Department", "Designation",
            "Working Days", "Present Days", "Absent Days", "Half Days",
            "Present %", "Absent %", "Total Work (Hrs)", "Overtime (Hrs)"
        ]
        ws_sum.append(sum_headers)
        for col_idx in range(1, len(sum_headers) + 1):
            c = ws_sum.cell(row=4, column=col_idx)
            c.fill = hdr_fill
            c.font = bold_10
            c.border = thin_border
            c.alignment = center

        ws_sum.row_dimensions[4].height = 20

        for idx, emp in enumerate(data["employees"], 1):
            r_num = 4 + idx
            ws_sum.append([
                idx,
                emp["biometric_id"] or "",
                emp["employee_code"],
                emp["display_name"],
                emp["department"],
                emp["designation"],
                emp["working_days"],
                emp["present_days"],
                emp["absent_days"],
                emp["half_days"],
                f"{emp['present_percent']}%",
                f"{emp['absent_percent']}%",
                emp["total_work_hours"],
                emp["total_ot_hours"]
            ])
            for c in range(1, len(sum_headers) + 1):
                cell = ws_sum.cell(row=r_num, column=c)
                cell.border = thin_border
                cell.font = reg_9
                cell.alignment = left if c in [4, 5, 6] else center
                if c == 11:
                    cell.font = bold_9
                    if emp["present_percent"] >= 80:
                        cell.fill = p_fill
                elif c == 12:
                    cell.font = bold_9
                    if emp["absent_percent"] > 20:
                        cell.fill = a_fill

        ws_sum.column_dimensions['A'].width = 6
        ws_sum.column_dimensions['B'].width = 8
        ws_sum.column_dimensions['C'].width = 12
        ws_sum.column_dimensions['D'].width = 24
        ws_sum.column_dimensions['E'].width = 18
        ws_sum.column_dimensions['F'].width = 18
        ws_sum.column_dimensions['G'].width = 13
        ws_sum.column_dimensions['H'].width = 13
        ws_sum.column_dimensions['I'].width = 13
        ws_sum.column_dimensions['J'].width = 10
        ws_sum.column_dimensions['K'].width = 12
        ws_sum.column_dimensions['L'].width = 12
        ws_sum.column_dimensions['M'].width = 15
        ws_sum.column_dimensions['N'].width = 14

        # Sheet 2: Daily Punch In/Out Logs
        ws_log = wb.create_sheet(title="Daily Punch In-Out Log")
        ws_log.views.sheetView[0].showGridLines = True

        log_headers = [
            "Date", "Day", "Bio ID", "Emp Code", "Employee Name", "Department",
            "Shift", "Punch In Time", "Punch Out Time", "Work Hours", "OT Hours", "Status"
        ]
        ws_log.append(log_headers)
        for col_idx in range(1, len(log_headers) + 1):
            c = ws_log.cell(row=1, column=col_idx)
            c.fill = navy_fill
            c.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
            c.alignment = center
            c.border = thin_border

        log_row = 2
        for emp in data["employees"]:
            for d in emp["daily_records"]:
                ws_log.append([
                    d["date"],
                    d["day_name"],
                    emp["biometric_id"] or "",
                    emp["employee_code"],
                    emp["display_name"],
                    emp["department"],
                    d["shift"],
                    d["punch_in"],
                    d["punch_out"],
                    d["work_time_str"],
                    d["ot_time_str"],
                    d["status"]
                ])

        ws_log.column_dimensions['A'].width = 12
        ws_log.column_dimensions['B'].width = 7
        ws_log.column_dimensions['C'].width = 8
        ws_log.column_dimensions['D'].width = 12
        ws_log.column_dimensions['E'].width = 22
        ws_log.column_dimensions['F'].width = 18
        ws_log.column_dimensions['G'].width = 14
        ws_log.column_dimensions['H'].width = 15
        ws_log.column_dimensions['I'].width = 15
        ws_log.column_dimensions['J'].width = 12
        ws_log.column_dimensions['K'].width = 12
        ws_log.column_dimensions['L'].width = 13

        filename = f"SVD_MonthlyAttendanceDetail_{year}_{month:02d}.xlsx"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/monthly-detail/export-pdf")
def export_monthly_detail_pdf(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    department: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None)
):
    """
    Generates and downloads publication-grade PDF:
    - If employee_id is specified: Single Employee Biometric Time Card with In/Out Times and Absent %
    - If employee_id is None / ALL: All Staff Attendance & Percentage Summary Register
    """
    with get_db() as cur:
        data = _calculate_monthly_detail_data(cur, month, year, department, employee_id)

    is_single_emp = bool(isinstance(employee_id, str) and employee_id.upper() != 'ALL' and len(data["employees"]) == 1)

    styles = getSampleStyleSheet()
    normal = styles['Normal']

    title_style = ParagraphStyle('T', parent=normal, fontName='Helvetica-Bold', fontSize=13, alignment=1, textColor=colors.HexColor('#0F766E'))
    sub_style = ParagraphStyle('S', parent=normal, fontName='Helvetica', fontSize=7.5, alignment=1, textColor=colors.HexColor('#64748B'))
    hdr_s = ParagraphStyle('H', parent=normal, fontName='Helvetica-Bold', fontSize=7.5, alignment=1, textColor=colors.HexColor('#FFFFFF'))
    c_bold = ParagraphStyle('CB', parent=normal, fontName='Helvetica-Bold', fontSize=7, alignment=1, textColor=colors.HexColor('#0F172A'))
    c_norm = ParagraphStyle('CN', parent=normal, fontName='Helvetica', fontSize=7, alignment=1, textColor=colors.HexColor('#334155'))
    c_left = ParagraphStyle('CL', parent=normal, fontName='Helvetica', fontSize=7, alignment=0, textColor=colors.HexColor('#334155'))

    if is_single_emp:
        emp = data["employees"][0]
        filename = f"PunchCard_{emp['employee_code']}_{year}_{month:02d}.pdf"
        filepath = os.path.join(PAYSLIP_DIR, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=24,
            rightMargin=24,
            topMargin=20,
            bottomMargin=20
        )

        story = [
            Paragraph(COMPANY_INFO["corporate_name"], title_style),
            Paragraph(f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}", sub_style),
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0F766E'), spaceBefore=2, spaceAfter=4),
            Paragraph(f"<b>MONTHLY BIOMETRIC TIME CARD & ATTENDANCE DETAIL – {data['month_name'].upper()}</b>", ParagraphStyle('RT', parent=normal, fontName='Helvetica-Bold', fontSize=9, alignment=1, textColor=colors.HexColor('#1E293B'))),
            Spacer(1, 4)
        ]

        # Profile & Summary Table
        kpi_table_data = [
            [
                Paragraph(f"<b>Employee:</b> {emp['display_name']}", c_left),
                Paragraph(f"<b>Code:</b> {emp['employee_code']}", c_norm),
                Paragraph(f"<b>Bio ID:</b> {emp['biometric_id'] or '-'}", c_norm),
                Paragraph(f"<b>Department:</b> {emp['department']}", c_left)
            ],
            [
                Paragraph(f"<b>Working Days:</b> {emp['working_days']}", c_bold),
                Paragraph(f"<b>Present Days:</b> {emp['present_days']}", c_bold),
                Paragraph(f"<b>Absent Days:</b> {emp['absent_days']}", c_bold),
                Paragraph(f"<b>Present %:</b> <font color='#0D9488'>{emp['present_percent']}%</font> | <b>Absent %:</b> <font color='#E11D48'>{emp['absent_percent']}%</font>", c_bold)
            ]
        ]
        kpi_t = Table(kpi_table_data, colWidths=[140, 120, 110, 175])
        kpi_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(kpi_t)
        story.append(Spacer(1, 6))

        # Daily table
        d_table_data = [[
            Paragraph("<b>Day</b>", hdr_s),
            Paragraph("<b>Date</b>", hdr_s),
            Paragraph("<b>Weekday</b>", hdr_s),
            Paragraph("<b>Punch In Time</b>", hdr_s),
            Paragraph("<b>Punch Out Time</b>", hdr_s),
            Paragraph("<b>Work Time</b>", hdr_s),
            Paragraph("<b>OT</b>", hdr_s),
            Paragraph("<b>Status</b>", hdr_s)
        ]]

        for d in emp["daily_records"]:
            st_color = '#0F766E' if d["status"] in ["PRESENT", "LATE"] else ('#E11D48' if d["status"] == "ABSENT" else '#475569')
            d_table_data.append([
                Paragraph(str(d["day"]), c_bold),
                Paragraph(d["date"][5:], c_norm),
                Paragraph(d["day_name"], c_norm),
                Paragraph(f"<b>{d['punch_in']}</b>" if d["punch_in"] != "--:--" else "--:--", c_norm),
                Paragraph(f"<b>{d['punch_out']}</b>" if d["punch_out"] != "--:--" else "--:--", c_norm),
                Paragraph(d["work_time_str"], c_norm),
                Paragraph(d["ot_time_str"], c_norm),
                Paragraph(f"<b><font color='{st_color}'>{d['status']}</font></b>", c_bold)
            ])

        dt_table = Table(d_table_data, colWidths=[35, 55, 55, 95, 95, 75, 65, 70])
        dt_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F766E')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
            ('TOPPADDING', (0,0), (-1,-1), 1.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ]))
        story.append(dt_table)
        story.append(Spacer(1, 8))

        # Signatures
        sig_data = [[
            Paragraph("<b>Prepared By:</b> HR Executive<br/><br/>______________________", c_norm),
            Paragraph("<b>Verified By:</b> Plant / Site In-charge<br/><br/>______________________", c_norm),
            Paragraph("<b>Employee Signature:</b><br/><br/>______________________", c_norm)
        ]]
        sig_table = Table(sig_data, colWidths=[180, 180, 185])
        story.append(sig_table)

        doc.build(story)
        return FileResponse(filepath, filename=filename, media_type="application/pdf")

    else:
        # All-Staff Landscape Summary PDF
        filename = f"Attendance_Percentage_Summary_{year}_{month:02d}.pdf"
        filepath = os.path.join(PAYSLIP_DIR, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            leftMargin=24,
            rightMargin=24,
            topMargin=20,
            bottomMargin=20
        )

        story = [
            Paragraph(COMPANY_INFO["corporate_name"], title_style),
            Paragraph(f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}", sub_style),
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0F766E'), spaceBefore=2, spaceAfter=4),
            Paragraph(f"<b>MONTHLY ATTENDANCE REGISTER & ABSENT/PRESENT PERCENTAGE SUMMARY – {data['month_name'].upper()}</b>", ParagraphStyle('RT', parent=normal, fontName='Helvetica-Bold', fontSize=10, alignment=1, textColor=colors.HexColor('#1E293B'))),
            Spacer(1, 6)
        ]

        table_data = [[
            Paragraph("<b>S.No</b>", hdr_s),
            Paragraph("<b>Bio ID</b>", hdr_s),
            Paragraph("<b>Emp Code</b>", hdr_s),
            Paragraph("<b>Employee Name</b>", hdr_s),
            Paragraph("<b>Department</b>", hdr_s),
            Paragraph("<b>Work Days</b>", hdr_s),
            Paragraph("<b>Present</b>", hdr_s),
            Paragraph("<b>Absent</b>", hdr_s),
            Paragraph("<b>Half Days</b>", hdr_s),
            Paragraph("<b>Present %</b>", hdr_s),
            Paragraph("<b>Absent %</b>", hdr_s),
            Paragraph("<b>Total Hours</b>", hdr_s),
            Paragraph("<b>OT Hours</b>", hdr_s)
        ]]

        for idx, s in enumerate(data["employees"], 1):
            table_data.append([
                Paragraph(str(idx), c_bold),
                Paragraph(str(s["biometric_id"] or '-'), c_norm),
                Paragraph(s["employee_code"], c_bold),
                Paragraph(s["display_name"], c_left),
                Paragraph(s["department"] or "Operations", c_left),
                Paragraph(str(s["working_days"]), c_norm),
                Paragraph(str(s["present_days"]), c_bold),
                Paragraph(str(s["absent_days"]), c_bold),
                Paragraph(str(s["half_days"]), c_norm),
                Paragraph(f"<font color='#0D9488'><b>{s['present_percent']}%</b></font>", c_bold),
                Paragraph(f"<font color='#E11D48'><b>{s['absent_percent']}%</b></font>", c_bold),
                Paragraph(f"{s['total_work_hours']}h", c_norm),
                Paragraph(f"{s['total_ot_hours']}h", c_norm)
            ])

        sum_table = Table(table_data, colWidths=[28, 38, 55, 140, 110, 50, 48, 48, 48, 55, 55, 60, 55])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F766E')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(sum_table)
        story.append(Spacer(1, 10))

        # Signatures
        sig_data = [
            [
                Paragraph("<b>Prepared By:</b> HR Department<br/><br/>______________________", c_norm),
                Paragraph("<b>Verified By:</b> Head of Operations<br/><br/>______________________", c_norm),
                Paragraph("<b>Approved By:</b> Managing Director<br/><br/>______________________", c_norm)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[260, 260, 260])
        story.append(sig_table)

        doc.build(story)
        return FileResponse(filepath, filename=filename, media_type="application/pdf")

