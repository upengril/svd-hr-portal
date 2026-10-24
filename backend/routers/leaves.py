import os
import io
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from ..db import get_db
from ..config import COMPANY_INFO, PAYSLIP_DIR

router = APIRouter(prefix="/api/leaves", tags=["Leaves & Holidays"])

class LeaveApplySchema(BaseModel):
    employee_id: str
    leave_type: str
    from_date: date
    to_date: date
    days_count: float
    reason: Optional[str] = ""

class LeaveStatusSchema(BaseModel):
    status: str
    approved_by: Optional[str] = "HR Admin"

class HolidaySchema(BaseModel):
    holiday_name: str
    holiday_date: date
    holiday_type: Optional[str] = "PUBLIC"

@router.get("")
def list_leaves(status: Optional[str] = None):
    where = "WHERE 1=1"
    params = []
    if status:
        where += " AND l.status = %s"
        params.append(status)

    with get_db() as cur:
        query = f"""
            SELECT 
                l.*,
                e.employee_code,
                e.display_name as employee_name,
                e.department
            FROM hr_leaves l
            JOIN hr_employees e ON l.employee_id = e.id
            {where}
            ORDER BY l.created_at DESC;
        """
        cur.execute(query, params)
        leaves = cur.fetchall()

    return {"leaves": leaves}

@router.post("")
def apply_leave(data: LeaveApplySchema):
    with get_db() as cur:
        cur.execute("""
            INSERT INTO hr_leaves (
                employee_id, leave_type, from_date, to_date, days_count, reason, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 'PENDING'
            ) RETURNING id;
        """, (
            data.employee_id, data.leave_type.upper(), data.from_date, data.to_date,
            data.days_count, data.reason
        ))
        lid = cur.fetchone()["id"]
    return {"success": True, "id": lid, "message": "Leave application submitted successfully"}

@router.put("/{leave_id}/status")
def update_leave_status(leave_id: str, data: LeaveStatusSchema):
    with get_db() as cur:
        cur.execute("""
            UPDATE hr_leaves SET
                status = %s,
                approved_by = %s,
                approved_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING employee_id, leave_type, days_count;
        """, (data.status.upper(), data.approved_by, leave_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")

        if data.status.upper() == "APPROVED":
            emp_id = row["employee_id"]
            l_type = row["leave_type"]
            days = row["days_count"]

            col = "used_casual_leave" if l_type == "CASUAL" else ("used_sick_leave" if l_type == "SICK" else "used_earned_leave")
            cur.execute(f"""
                UPDATE hr_leave_balances SET
                    {col} = {col} + %s
                WHERE employee_id = %s AND year = 2026;
            """, (days, emp_id))

    return {"success": True, "message": f"Leave application {data.status.upper()}"}

@router.get("/balances/{employee_id}")
def get_leave_balances(employee_id: str):
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_leave_balances WHERE employee_id = %s AND year = 2026;", (employee_id,))
        bal = cur.fetchone()
        if not bal:
            return {
                "casual_leave": 12.0, "used_casual_leave": 0.0, "remaining_casual": 12.0,
                "sick_leave": 10.0, "used_sick_leave": 0.0, "remaining_sick": 10.0,
                "earned_leave": 15.0, "used_earned_leave": 0.0, "remaining_earned": 15.0
            }

        return {
            "casual_leave": float(bal["casual_leave"]),
            "used_casual_leave": float(bal["used_casual_leave"]),
            "remaining_casual": float(bal["casual_leave"] - bal["used_casual_leave"]),
            "sick_leave": float(bal["sick_leave"]),
            "used_sick_leave": float(bal["used_sick_leave"]),
            "remaining_sick": float(bal["sick_leave"] - bal["used_sick_leave"]),
            "earned_leave": float(bal["earned_leave"]),
            "used_earned_leave": float(bal["used_earned_leave"]),
            "remaining_earned": float(bal["earned_leave"] - bal["used_earned_leave"])
        }

@router.get("/holidays")
def list_holidays():
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_holidays ORDER BY holiday_date ASC;")
        holidays = cur.fetchall()
    return {"holidays": holidays}

@router.post("/holidays")
def add_holiday(data: HolidaySchema):
    with get_db() as cur:
        cur.execute("SELECT id FROM companies LIMIT 1")
        cid = cur.fetchone()["id"]
        cur.execute("""
            INSERT INTO hr_holidays (company_id, holiday_name, holiday_date, holiday_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (holiday_date) DO UPDATE SET holiday_name = EXCLUDED.holiday_name
            RETURNING id;
        """, (cid, data.holiday_name, data.holiday_date, data.holiday_type))
        hid = cur.fetchone()["id"]
    return {"success": True, "id": hid, "message": "Holiday added"}

@router.get("/holidays/export-excel")
def export_holidays_excel(year: int = 2026):
    """Export formatted Company Holiday Calendar to Excel"""
    with get_db() as cur:
        cur.execute("SELECT * FROM hr_holidays ORDER BY holiday_date ASC;")
        holidays = cur.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = f"Holidays {year}"
    ws.views.sheetView[0].showGridLines = True

    navy_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    sub_fill = PatternFill(start_color="115E59", end_color="115E59", fill_type="solid")
    hdr_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    ws.merge_cells("A1:E1")
    ws["A1"] = COMPANY_INFO["corporate_name"]
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = navy_fill
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 25

    ws.merge_cells("A2:E2")
    ws["A2"] = f"CIN: {COMPANY_INFO['cin']} | OFFICIAL COMPANY HOLIDAY CALENDAR – {year}"
    ws["A2"].font = Font(name="Calibri", size=10, bold=True, color="E0F2FE")
    ws["A2"].fill = sub_fill
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    headers = ["S.No", "Holiday Name", "Date", "Day of Week", "Holiday Classification"]
    ws.append(headers)

    for cell in ws[3]:
        cell.fill = hdr_fill
        cell.font = Font(name="Calibri", size=11, bold=True, color="1E293B")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for idx, h in enumerate(holidays, 1):
        dt = h["holiday_date"]
        row = [
            idx,
            h["holiday_name"],
            dt.strftime("%d-%B-%Y"),
            dt.strftime("%A"),
            h["holiday_type"]
        ]
        ws.append(row)
        curr_row = ws.max_row
        ws.cell(row=curr_row, column=1).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=2).alignment = Alignment(horizontal="left")
        ws.cell(row=curr_row, column=3).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=4).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=5).alignment = Alignment(horizontal="center")

        for c in range(1, 6):
            ws.cell(row=curr_row, column=c).border = thin_border
            ws.cell(row=curr_row, column=c).font = Font(name="Calibri", size=10)

    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 24

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"SV_DREEAMPLANNERS_Holiday_Calendar_{year}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/holidays/export-pdf")
def export_holidays_pdf(year: int = 2026):
    """Export formatted Company Holiday Calendar to PDF"""
    filename = f"Holiday_Calendar_{year}.pdf"
    filepath = os.path.join(PAYSLIP_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    normal = styles['Normal']

    title_style = ParagraphStyle('HTitle', parent=normal, fontName='Helvetica-Bold', fontSize=15, leading=18, alignment=1, textColor=colors.HexColor('#0F766E'))
    sub_style = ParagraphStyle('HSub', parent=normal, fontName='Helvetica', fontSize=8, leading=11, alignment=1, textColor=colors.HexColor('#64748B'))
    hdr_style = ParagraphStyle('HHdr', parent=normal, fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=1, textColor=colors.HexColor('#FFFFFF'))
    cell_style = ParagraphStyle('HCell', parent=normal, fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#1E293B'))
    cell_bold = ParagraphStyle('HCellB', parent=normal, fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=1, textColor=colors.HexColor('#0F172A'))

    with get_db() as cur:
        cur.execute("SELECT * FROM hr_holidays ORDER BY holiday_date ASC;")
        holidays = cur.fetchall()

    story = []
    story.append(Paragraph(COMPANY_INFO["corporate_name"], title_style))
    story.append(Paragraph(f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['registered_address']}", sub_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0F766E'), spaceBefore=2, spaceAfter=8))
    story.append(Paragraph(f"<b>OFFICIAL COMPANY HOLIDAY LIST – CALENDAR YEAR {year}</b>", ParagraphStyle('HolTitle', parent=normal, fontName='Helvetica-Bold', fontSize=11, alignment=1, textColor=colors.HexColor('#1E293B'))))
    story.append(Spacer(1, 10))

    table_data = [
        [
            Paragraph("<b>S.No</b>", hdr_style),
            Paragraph("<b>Holiday Name</b>", hdr_style),
            Paragraph("<b>Date</b>", hdr_style),
            Paragraph("<b>Day</b>", hdr_style),
            Paragraph("<b>Category</b>", hdr_style)
        ]
    ]

    for idx, h in enumerate(holidays, 1):
        dt = h["holiday_date"]
        table_data.append([
            Paragraph(str(idx), cell_bold),
            Paragraph(f"<b>{h['holiday_name']}</b>", cell_style),
            Paragraph(dt.strftime("%d-%B-%Y"), cell_bold),
            Paragraph(dt.strftime("%A"), cell_style),
            Paragraph(h["holiday_type"], cell_bold)
        ])

    table = Table(table_data, colWidths=[35, 190, 100, 95, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F766E')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 30))

    # Signatures
    sig_data = [
        [
            Paragraph("<b>Issued By:</b><br/>Human Resources Department<br/><br/>______________________", cell_style),
            Paragraph("<b>Approved By:</b><br/>Director / Authorized Signatory<br/><br/>______________________", cell_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260])
    story.append(sig_table)

    doc.build(story)
    return FileResponse(filepath, filename=filename, media_type="application/pdf")
