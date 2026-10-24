import os
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from ..config import COMPANY_INFO, PAYSLIP_DIR

def number_to_words(n):
    """Convert number to Indian Rupee Words"""
    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
    teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def convert_below_thousand(num):
        res = ""
        if num >= 100:
            res += units[num // 100] + " Hundred "
            num %= 100
        if num >= 20:
            res += tens[num // 10] + " "
            num %= 10
        elif num >= 10:
            res += teens[num - 10] + " "
            return res
        if num > 0:
            res += units[num] + " "
        return res

    n = int(round(n))
    if n == 0:
        return "Zero Rupees Only"

    crore = n // 10000000
    n %= 10000000
    lakh = n // 100000
    n %= 100000
    thousand = n // 1000
    n %= 1000
    remainder = n

    parts = []
    if crore > 0:
        parts.append(convert_below_thousand(crore).strip() + " Crore")
    if lakh > 0:
        parts.append(convert_below_thousand(lakh).strip() + " Lakh")
    if thousand > 0:
        parts.append(convert_below_thousand(thousand).strip() + " Thousand")
    if remainder > 0:
        parts.append(convert_below_thousand(remainder).strip())

    return "Rupees " + " ".join(parts).strip() + " Only"

class PayslipGenerator:
    @staticmethod
    def generate_pdf(payslip_data):
        """
        Generate a professional PDF payslip
        """
        emp_code = payslip_data["employee_code"]
        month = payslip_data["month"]
        year = payslip_data["year"]
        month_name = datetime(year, month, 1).strftime("%B %Y")
        
        filename = f"Payslip_{emp_code}_{year}_{month:02d}.pdf"
        filepath = os.path.join(PAYSLIP_DIR, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        normal = styles['Normal']

        company_style = ParagraphStyle(
            'CompanyTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=18,
            alignment=1, # Center
            textColor=colors.HexColor('#1E293B')
        )
        
        sub_style = ParagraphStyle(
            'CompanySub',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            alignment=1,
            textColor=colors.HexColor('#64748B')
        )

        title_style = ParagraphStyle(
            'PayslipTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=15,
            alignment=1,
            textColor=colors.HexColor('#0F766E')
        )

        cell_style = ParagraphStyle('Cell', parent=normal, fontSize=8, leading=10, textColor=colors.HexColor('#1E293B'))
        cell_bold = ParagraphStyle('CellBold', parent=normal, fontSize=8, leading=10, fontName='Helvetica-Bold', textColor=colors.HexColor('#0F172A'))
        right_style = ParagraphStyle('CellRight', parent=normal, fontSize=8, leading=10, alignment=2, textColor=colors.HexColor('#1E293B'))
        right_bold = ParagraphStyle('CellRightBold', parent=normal, fontSize=8, leading=10, fontName='Helvetica-Bold', alignment=2, textColor=colors.HexColor('#0F172A'))

        story = []

        # 1. Header Banner
        story.append(Paragraph(COMPANY_INFO["corporate_name"], company_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"CIN: {COMPANY_INFO['cin']} | {COMPANY_INFO['industry']}", sub_style))
        story.append(Paragraph(COMPANY_INFO["registered_address"], sub_style))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0F766E'), spaceBefore=2, spaceAfter=8))
        story.append(Paragraph(f"<b>PAYSLIP FOR THE MONTH OF {month_name.upper()}</b>", title_style))
        story.append(Spacer(1, 10))

        # 2. Employee Info & Attendance Table
        # Mask Aadhaar
        raw_aadhaar = payslip_data.get("aadhar_number") or ""
        masked_aadhaar = f"XXXX-XXXX-{raw_aadhaar[-4:]}" if len(raw_aadhaar) >= 4 else "N/A"

        emp_info_data = [
            [
                Paragraph("<b>Employee Code:</b>", cell_style), Paragraph(payslip_data["employee_code"], cell_bold),
                Paragraph("<b>Paid Days:</b>", cell_style), Paragraph(str(payslip_data["paid_days"]), cell_bold)
            ],
            [
                Paragraph("<b>Employee Name:</b>", cell_style), Paragraph(payslip_data["employee_name"], cell_bold),
                Paragraph("<b>Present Days:</b>", cell_style), Paragraph(str(payslip_data["present_days"]), cell_style)
            ],
            [
                Paragraph("<b>Designation:</b>", cell_style), Paragraph(payslip_data.get("designation", "Staff"), cell_style),
                Paragraph("<b>Absent Days:</b>", cell_style), Paragraph(str(payslip_data.get("absent_days", 0)), cell_style)
            ],
            [
                Paragraph("<b>Department:</b>", cell_style), Paragraph(payslip_data.get("department", "Site Operations"), cell_style),
                Paragraph("<b>Leave / Holidays:</b>", cell_style), Paragraph(f"{payslip_data.get('leave_days', 0)} / {payslip_data.get('holiday_days', 0)}", cell_style)
            ],
            [
                Paragraph("<b>Date of Joining:</b>", cell_style), Paragraph(str(payslip_data.get("date_of_joining", "01/01/2026")), cell_style),
                Paragraph("<b>Overtime Hours:</b>", cell_style), Paragraph(f"{payslip_data.get('overtime_hours', 0)} hrs", cell_style)
            ],
            [
                Paragraph("<b>PAN:</b>", cell_style), Paragraph(payslip_data.get("pan_number") or "N/A", cell_style),
                Paragraph("<b>Bank Name:</b>", cell_style), Paragraph(payslip_data.get("bank_name") or "N/A", cell_style)
            ],
            [
                Paragraph("<b>Aadhaar (Masked):</b>", cell_style), Paragraph(masked_aadhaar, cell_style),
                Paragraph("<b>Account No:</b>", cell_style), Paragraph(payslip_data.get("account_number") or "N/A", cell_style)
            ],
            [
                Paragraph("<b>UAN / PF No:</b>", cell_style), Paragraph(payslip_data.get("uan_number") or "N/A", cell_style),
                Paragraph("<b>IFSC Code:</b>", cell_style), Paragraph(payslip_data.get("ifsc_code") or "N/A", cell_style)
            ]
        ]

        emp_table = Table(emp_info_data, colWidths=[110, 150, 110, 150])
        emp_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(emp_table)
        story.append(Spacer(1, 12))

        # 3. Earnings & Deductions Table
        earning_rows = [
            ("Basic Salary", payslip_data.get("basic_earned", 0)),
            ("House Rent Allowance (HRA)", payslip_data.get("hra_earned", 0)),
            ("Conveyance Allowance", payslip_data.get("conveyance_earned", 0)),
            ("Special Allowance", payslip_data.get("special_allowance_earned", 0)),
            ("Overtime Pay", payslip_data.get("overtime_pay", 0)),
        ]

        deduction_rows = [
            ("Provident Fund (PF)", payslip_data.get("pf_deduction", 0)),
            ("ESIC", payslip_data.get("esic_deduction", 0)),
            ("Professional Tax (PT)", payslip_data.get("pt_deduction", 0)),
            ("TDS / Income Tax", payslip_data.get("tds_deduction", 0)),
            ("Other Deductions / Advances", payslip_data.get("other_deductions", 0)),
        ]

        salary_table_data = [
            [
                Paragraph("<b>EARNINGS</b>", cell_bold), Paragraph("<b>AMOUNT (₹)</b>", right_bold),
                Paragraph("<b>DEDUCTIONS</b>", cell_bold), Paragraph("<b>AMOUNT (₹)</b>", right_bold)
            ]
        ]

        for i in range(max(len(earning_rows), len(deduction_rows))):
            e_lbl, e_val = earning_rows[i] if i < len(earning_rows) else ("", 0)
            d_lbl, d_val = deduction_rows[i] if i < len(deduction_rows) else ("", 0)

            salary_table_data.append([
                Paragraph(e_lbl, cell_style),
                Paragraph(f"₹ {float(e_val):,.2f}" if e_lbl else "", right_style),
                Paragraph(d_lbl, cell_style),
                Paragraph(f"₹ {float(d_val):,.2f}" if d_lbl else "", right_style)
            ])

        gross = float(payslip_data.get("gross_earned", 0))
        total_ded = float(payslip_data.get("total_deductions", 0))
        net = float(payslip_data.get("net_pay", 0))

        # Total Rows
        salary_table_data.append([
            Paragraph("<b>Total Gross Earnings</b>", cell_bold),
            Paragraph(f"<b>₹ {gross:,.2f}</b>", right_bold),
            Paragraph("<b>Total Deductions</b>", cell_bold),
            Paragraph(f"<b>₹ {total_ded:,.2f}</b>", right_bold)
        ])

        salary_table = Table(salary_table_data, colWidths=[150, 110, 150, 110])
        salary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#F1F5F9')),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(salary_table)
        story.append(Spacer(1, 12))

        # 4. Net Pay Summary Highlight Box
        net_words = number_to_words(net)
        net_box_data = [
            [
                Paragraph("<b>NET PAYABLE AMOUNT:</b>", ParagraphStyle('NetLbl', parent=normal, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#0F766E'))),
                Paragraph(f"<b>₹ {net:,.2f}</b>", ParagraphStyle('NetVal', parent=normal, fontName='Helvetica-Bold', fontSize=13, alignment=2, textColor=colors.HexColor('#0F766E')))
            ],
            [
                Paragraph(f"<b>In Words:</b> {net_words}", ParagraphStyle('NetW', parent=normal, fontSize=8, fontName='Helvetica-Oblique', textColor=colors.HexColor('#334155'))),
                Paragraph("", normal)
            ]
        ]
        net_table = Table(net_box_data, colWidths=[360, 160])
        net_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#CCFBF1')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#0D9488')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('SPAN', (0,1), (1,1))
        ]))
        story.append(net_table)
        story.append(Spacer(1, 30))

        # 5. Signature Section
        sig_data = [
            [
                Paragraph("<b>Employer Signature:</b><br/><br/><br/>________________________<br/>Authorized Signatory", cell_style),
                Paragraph("<b>Employee Signature:</b><br/><br/><br/>________________________<br/>I hereby confirm receipt of pay", cell_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[260, 260])
        sig_table.setStyle(TableStyle([
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 15))
        story.append(Paragraph("<i>Note: This document is a computer-generated payslip issued by SV Dreeamplanners Private Limited.</i>", ParagraphStyle('Foot', parent=normal, fontSize=7, alignment=1, textColor=colors.HexColor('#94A3B8'))))

        doc.build(story)
        return filepath
