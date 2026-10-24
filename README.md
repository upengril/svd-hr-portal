# SV DREEAMPLANNERS PRIVATE LIMITED – HR & Biometric Management Portal

## Corporate Identity
* **Corporate Name**: SV DREEAMPLANNERS PRIVATE LIMITED
* **CIN**: U45100UP2013PTC056525
* **Date of Incorporation**: April 26, 2013
* **Industry / Activity**: Site preparation and construction (NIC Code 4510)
* **Registered Office**: C-3/87, 88, 89, First Floor, Vibhuti Khand, Gomti Nagar, Lucknow, Uttar Pradesh, India - 226010
* **Authorized Capital**: ₹ 3,55,00,000
* **Paid-up Capital**: ₹ 10,39,270
* **Board of Directors**:
  1. Nitin Chawla (Director)
  2. Ashok Vashdew Jagtiani (Director)
  3. Snehlata (Director)
  4. Mohammad Ubaidullah Faizi (Director)
  5. Rakesh Ashok Jagtiani (Director)
  6. Kamal Singh (Director)

---

## System Overview
The **SVD HR & Biometric Portal** is a full-featured web-based enterprise application that connects directly to the company's **ZKTeco Biometric Terminal (Device 2)** and shares all data with the existing **SVD ERP** PostgreSQL database (`svd_erp_dev`).

### Hardware Integration
* **Target Hardware**: ZKTeco `x 2008` Terminal (Device 2)
* **IP Address & Port**: `192.168.31.111:4370` (TCP/UDP)
* **Serial Number**: `TFDB244500349`
* **Pre-Loaded Staff**: 329 Employees directly synced from device

---

## Core Features

1. **Live Dashboard & Hardware Monitor**
   - Real-time online/offline status for Device 2 (`192.168.31.111:4370`).
   - Today's attendance KPI cards (Present, Absent, Late Arrivals, Half Day, Overtime).
   - Real-time punch feed ticker.
   - One-click **"Sync Biometric"** button.

2. **Employee 360° Directory (329 Enrolled Staff)**
   - Pre-seeded with all 329 employees from the biometric terminal.
   - Comprehensive profile management:
     - **Personal & Contact Details**: First name, last name, phone, email, date of birth, blood group, gender, marital status, emergency contact, present & permanent address.
     - **Statutory Identifiers (KYC)**: PAN Card, Aadhaar Number (with masked view), UAN/PF Number, ESIC Number.
     - **Bank Account**: Account holder name, Bank name, Account number, IFSC Code, Branch name.
     - **Qualifications & Experience**: Degrees, diplomas, ITI certificates, passing years, prior work experience, past company names.
     - **Salary Structure**: Monthly gross, basic pay, HRA, conveyance, special allowances, and statutory PF/ESIC/PT flags.

3. **Document Control & Management (DMS)**
   - Secure upload and viewing of Aadhaar cards, PAN cards, degree certificates, resumes, offer letters, and experience certificates.
   - Verification workflow with **"Verified"** or **"Rejected"** HR status tags.

4. **Daily Attendance Management**
   - Date picker to view attendance for any working day.
   - Automated First-In, Last-Out, Total Work Hours, Late Arrivals, and Overtime computation.
   - Status indicators (`PRESENT`, `HALF DAY`, `ABSENT`).
   - Manual punch adjustment / override modal with audit note.
   - One-click CSV export.

5. **Monthly Timesheet Matrix**
   - Visual monthly calendar grid showing attendance (P, HD, A) for all 329 employees across the entire month.

6. **Leave Management & Holiday Calendar**
   - Leave applications for Casual Leave (CL), Sick Leave (SL), Earned Leave (EL), Loss of Pay (LOP).
   - Approval/Rejection workflow with automated leave balance deduction.
   - Official 2026 Company Holiday Calendar pre-configured.

7. **Payroll Engine & Automated PDF Payslips**
   - Automated monthly salary calculation based on actual attendance days, worked hours, OT, leaves, and paid holidays.
   - Statutory deductions computed (PF 12%, ESIC 0.75%, PT ₹200).
   - **One-click PDF Payslip Generation**: Formatted with company header, CIN, employee KYC, earnings, deductions, and Net Pay in words and figures.
   - **One-click Excel Export**: Exports bank salary disbursement sheet (`.xlsx`) with employee bank accounts, IFSC, and net payout.

---

## How to Start the Application

Double-click the startup script:
```bat
D:\svd-hr-portal\START-HR-PORTAL.bat
```
Or start manually via terminal:
```bash
cd D:\svd-hr-portal
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000
```
Then open your browser at:
👉 **http://localhost:5000**
API Documentation (Swagger):
👉 **http://localhost:5000/docs**
