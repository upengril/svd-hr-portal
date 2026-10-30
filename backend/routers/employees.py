from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import json
import urllib.request
import urllib.error
from ..db import get_db
from ..config import COMPANY_INFO

router = APIRouter(prefix="/api/employees", tags=["Employees"])

class EmployeeCreateSchema(BaseModel):
    employee_code: str
    biometric_id: Optional[int] = None
    first_name: str
    last_name: Optional[str] = ""
    display_name: Optional[str] = ""
    gender: Optional[str] = "MALE"
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = "SINGLE"
    phone: Optional[str] = None
    email: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    present_address: Optional[str] = None
    permanent_address: Optional[str] = None
    department: Optional[str] = "Site Operations"
    designation: Optional[str] = "Staff"
    employment_type: Optional[str] = "REGULAR"
    date_of_joining: Optional[date] = None
    pan_number: Optional[str] = None
    aadhar_number: Optional[str] = None
    uan_number: Optional[str] = None
    esic_number: Optional[str] = None
    is_overtime_eligible: Optional[bool] = True

class EmployeeUpdateSchema(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    display_name: Optional[str] = ""
    gender: Optional[str] = "MALE"
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = "SINGLE"
    phone: Optional[str] = None
    email: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    present_address: Optional[str] = None
    permanent_address: Optional[str] = None
    department: Optional[str] = "Site Operations"
    designation: Optional[str] = "Staff"
    employment_type: Optional[str] = "REGULAR"
    date_of_joining: Optional[date] = None
    pan_number: Optional[str] = None
    aadhar_number: Optional[str] = None
    uan_number: Optional[str] = None
    esic_number: Optional[str] = None
    is_overtime_eligible: Optional[bool] = True
    status: Optional[str] = "ACTIVE"

class BankDetailsSchema(BaseModel):
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    branch_name: Optional[str] = None
    account_type: Optional[str] = "SAVINGS"

class QualificationSchema(BaseModel):
    qualification_type: str
    degree_name: Optional[str] = None
    institution: Optional[str] = None
    board_university: Optional[str] = None
    passing_year: Optional[int] = None
    percentage_or_cgpa: Optional[str] = None
    prior_experience_years: Optional[float] = 0.0
    previous_company: Optional[str] = None
    previous_designation: Optional[str] = None

class SalaryStructureSchema(BaseModel):
    wage_type: Optional[str] = "MONTHLY"
    monthly_gross: Optional[float] = 0.0
    daily_rate: Optional[float] = 0.0
    basic_pay: Optional[float] = 0.0
    hra: Optional[float] = 0.0
    conveyance: Optional[float] = 0.0
    special_allowance: Optional[float] = 0.0
    other_allowances: Optional[float] = 0.0
    pf_applicable: Optional[bool] = True
    esic_applicable: Optional[bool] = True
    pt_applicable: Optional[bool] = True

@router.get("")
def list_employees(
    search: Optional[str] = Query(None, description="Search by name, code, phone, biometric ID"),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500)
):
    offset = (page - 1) * limit
    where_clauses = ["1=1"]
    params = []

    if search:
        search_term = f"%{search.strip()}%"
        where_clauses.append("""
            (e.display_name ILIKE %s OR e.employee_code ILIKE %s 
             OR e.phone ILIKE %s OR e.biometric_id::text ILIKE %s 
             OR e.pan_number ILIKE %s OR e.aadhar_number ILIKE %s)
        """)
        params.extend([search_term, search_term, search_term, search_term, search_term, search_term])

    if department:
        where_clauses.append("e.department = %s")
        params.append(department)

    if status:
        where_clauses.append("e.status = %s")
        params.append(status)

    where_sql = " AND ".join(where_clauses)

    with get_db() as cur:
        # Total count
        cur.execute(f"SELECT COUNT(*) as total FROM hr_employees e WHERE {where_sql};", params)
        total_count = cur.fetchone()["total"]

        # Employees list
        query = f"""
            SELECT 
                e.id,
                e.employee_code,
                e.biometric_id,
                e.card_number,
                e.first_name,
                e.last_name,
                e.display_name,
                e.gender,
                e.date_of_birth,
                e.phone,
                e.email,
                e.department,
                e.designation,
                e.employment_type,
                e.date_of_joining,
                e.status,
                e.pan_number,
                e.aadhar_number,
                b.bank_name,
                b.account_number,
                s.monthly_gross,
                s.wage_type
            FROM hr_employees e
            LEFT JOIN hr_bank_details b ON e.id = b.employee_id
            LEFT JOIN hr_salary_structures s ON e.id = s.employee_id
            WHERE {where_sql}
            ORDER BY e.biometric_id ASC NULLS LAST, e.employee_code ASC
            LIMIT %s OFFSET %s;
        """
        cur.execute(query, params + [limit, offset])
        employees = cur.fetchall()

    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "employees": employees
    }

@router.get("/lookup-ifsc/{ifsc_code}")
def lookup_ifsc(ifsc_code: str):
    """
    Online IFSC lookup: fetches Bank Name, Branch, City, State, Address, and payment modes.
    Uses Razorpay public API with headers and error handling.
    """
    clean_code = ifsc_code.strip().upper()
    if len(clean_code) != 11:
        raise HTTPException(status_code=400, detail="Invalid IFSC code format (must be 11 characters).")

    try:
        url = f"https://ifsc.razorpay.com/{clean_code}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CivMasterPro-HR-Portal/2.4"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                raw_data = json.loads(response.read().decode('utf-8'))
                return {
                    "success": True,
                    "ifsc": clean_code,
                    "bank_name": raw_data.get("BANK", ""),
                    "branch_name": raw_data.get("BRANCH", ""),
                    "bank_code": raw_data.get("BANKCODE", ""),
                    "micr": raw_data.get("MICR", ""),
                    "city": raw_data.get("CITY", ""),
                    "district": raw_data.get("DISTRICT", ""),
                    "state": raw_data.get("STATE", ""),
                    "address": raw_data.get("ADDRESS", ""),
                    "contact": raw_data.get("CONTACT", ""),
                    "upi": raw_data.get("UPI", False),
                    "neft": raw_data.get("NEFT", False),
                    "rtgs": raw_data.get("RTGS", False),
                    "imps": raw_data.get("IMPS", False)
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(status_code=404, detail="IFSC code not found.")
        raise HTTPException(status_code=502, detail=f"IFSC lookup service error: {e.code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to lookup IFSC: {str(e)}")

@router.get("/{employee_id}")
def get_employee_detail(employee_id: str):
    with get_db() as cur:
        # Basic & Personal Details
        cur.execute("""
            SELECT e.*, s.name as shift_name, s.start_time as shift_start, s.end_time as shift_end
            FROM hr_employees e
            LEFT JOIN hr_shifts s ON e.shift_id = s.id
            WHERE e.id = %s;
        """, (employee_id,))
        emp = cur.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Bank Details
        cur.execute("SELECT * FROM hr_bank_details WHERE employee_id = %s;", (employee_id,))
        bank = cur.fetchone()

        # Qualifications & Experience
        cur.execute("SELECT * FROM hr_qualifications WHERE employee_id = %s ORDER BY passing_year DESC;", (employee_id,))
        qualifications = cur.fetchall()

        # Uploaded Documents
        cur.execute("SELECT * FROM hr_documents WHERE employee_id = %s ORDER BY created_at DESC;", (employee_id,))
        documents = cur.fetchall()

        # Salary Structure
        cur.execute("SELECT * FROM hr_salary_structures WHERE employee_id = %s;", (employee_id,))
        salary = cur.fetchone()

        # Leave Balances
        cur.execute("SELECT * FROM hr_leave_balances WHERE employee_id = %s AND year = 2026;", (employee_id,))
        leave_balance = cur.fetchone()

        # Recent 7 Attendance Records
        cur.execute("""
            SELECT * FROM hr_attendance_daily 
            WHERE employee_id = %s 
            ORDER BY attendance_date DESC 
            LIMIT 7;
        """, (employee_id,))
        recent_attendance = cur.fetchall()

    return {
        "employee": emp,
        "bank_details": bank,
        "qualifications": qualifications,
        "documents": documents,
        "salary_structure": salary,
        "leave_balance": leave_balance,
        "recent_attendance": recent_attendance
    }

@router.post("")
def create_employee(data: EmployeeCreateSchema):
    display_name = data.display_name or f"{data.first_name} {data.last_name or ''}".strip()
    with get_db() as cur:
        cur.execute("SELECT id FROM hr_shifts WHERE is_default = TRUE LIMIT 1")
        shift_row = cur.fetchone()
        shift_id = shift_row["id"] if shift_row else None

        cur.execute("""
            INSERT INTO hr_employees (
                company_id, employee_code, biometric_id, first_name, last_name, display_name,
                gender, date_of_birth, blood_group, marital_status, phone, email,
                emergency_contact_name, emergency_contact_phone, present_address, permanent_address,
                department, designation, employment_type, date_of_joining, shift_id,
                pan_number, aadhar_number, uan_number, esic_number, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE'
            ) RETURNING id;
        """, (
            COMPANY_INFO["id"], data.employee_code, data.biometric_id, data.first_name, data.last_name, display_name,
            data.gender, data.date_of_birth, data.blood_group, data.marital_status, data.phone, data.email,
            data.emergency_contact_name, data.emergency_contact_phone, data.present_address, data.permanent_address,
            data.department, data.designation, data.employment_type, data.date_of_joining or date.today(), shift_id,
            data.pan_number, data.aadhar_number, data.uan_number, data.esic_number
        ))
        emp_id = cur.fetchone()["id"]

        # Default bank row
        cur.execute("INSERT INTO hr_bank_details (employee_id, account_holder_name) VALUES (%s, %s);", (emp_id, display_name))
        
        # Default leave balance
        cur.execute("INSERT INTO hr_leave_balances (employee_id, year) VALUES (%s, 2026);", (emp_id,))
        
        # Default salary structure
        cur.execute("""
            INSERT INTO hr_salary_structures (
                employee_id, wage_type, monthly_gross, basic_pay, hra, conveyance, special_allowance
            ) VALUES (%s, 'MONTHLY', 25000, 12500, 5000, 2500, 5000);
        """, (emp_id,))

    return {"success": True, "id": emp_id, "message": "Employee created successfully"}

@router.put("/{employee_id}")
def update_employee(employee_id: str, data: EmployeeUpdateSchema):
    display_name = data.display_name or f"{data.first_name} {data.last_name or ''}".strip()
    with get_db() as cur:
        cur.execute("""
            UPDATE hr_employees SET
                first_name = %s,
                last_name = %s,
                display_name = %s,
                gender = %s,
                date_of_birth = %s,
                blood_group = %s,
                marital_status = %s,
                phone = %s,
                email = %s,
                emergency_contact_name = %s,
                emergency_contact_phone = %s,
                present_address = %s,
                permanent_address = %s,
                department = %s,
                designation = %s,
                employment_type = %s,
                date_of_joining = %s,
                pan_number = %s,
                aadhar_number = %s,
                uan_number = %s,
                esic_number = %s,
                is_overtime_eligible = %s,
                status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (
            data.first_name, data.last_name, display_name, data.gender, data.date_of_birth,
            data.blood_group, data.marital_status, data.phone, data.email, data.emergency_contact_name,
            data.emergency_contact_phone, data.present_address, data.permanent_address,
            data.department, data.designation, data.employment_type, data.date_of_joining,
            data.pan_number, data.aadhar_number, data.uan_number, data.esic_number,
            data.is_overtime_eligible if data.is_overtime_eligible is not None else True,
            data.status, employee_id
        ))
    return {"success": True, "message": "Employee updated successfully"}

@router.put("/{employee_id}/bank")
def update_bank_details(employee_id: str, data: BankDetailsSchema):
    with get_db() as cur:
        cur.execute("""
            INSERT INTO hr_bank_details (
                employee_id, account_holder_name, bank_name, account_number, ifsc_code, branch_name, account_type
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (employee_id) DO UPDATE SET
                account_holder_name = EXCLUDED.account_holder_name,
                bank_name = EXCLUDED.bank_name,
                account_number = EXCLUDED.account_number,
                ifsc_code = EXCLUDED.ifsc_code,
                branch_name = EXCLUDED.branch_name,
                account_type = EXCLUDED.account_type,
                updated_at = CURRENT_TIMESTAMP;
        """, (
            employee_id, data.account_holder_name, data.bank_name, data.account_number,
            data.ifsc_code, data.branch_name, data.account_type
        ))
    return {"success": True, "message": "Bank details updated successfully"}

@router.post("/{employee_id}/qualifications")
def add_qualification(employee_id: str, data: QualificationSchema):
    with get_db() as cur:
        cur.execute("""
            INSERT INTO hr_qualifications (
                employee_id, qualification_type, degree_name, institution, board_university,
                passing_year, percentage_or_cgpa, prior_experience_years, previous_company, previous_designation
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id;
        """, (
            employee_id, data.qualification_type, data.degree_name, data.institution, data.board_university,
            data.passing_year, data.percentage_or_cgpa, data.prior_experience_years,
            data.previous_company, data.previous_designation
        ))
        qid = cur.fetchone()["id"]
    return {"success": True, "id": qid, "message": "Qualification added successfully"}

@router.delete("/qualifications/{qualification_id}")
def delete_qualification(qualification_id: str):
    with get_db() as cur:
        cur.execute("DELETE FROM hr_qualifications WHERE id = %s;", (qualification_id,))
    return {"success": True, "message": "Qualification deleted"}

@router.put("/{employee_id}/salary")
def update_salary_structure(employee_id: str, data: SalaryStructureSchema):
    with get_db() as cur:
        cur.execute("""
            INSERT INTO hr_salary_structures (
                employee_id, wage_type, monthly_gross, daily_rate, basic_pay, hra, conveyance,
                special_allowance, other_allowances, pf_applicable, esic_applicable, pt_applicable
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (employee_id) DO UPDATE SET
                wage_type = EXCLUDED.wage_type,
                monthly_gross = EXCLUDED.monthly_gross,
                daily_rate = EXCLUDED.daily_rate,
                basic_pay = EXCLUDED.basic_pay,
                hra = EXCLUDED.hra,
                conveyance = EXCLUDED.conveyance,
                special_allowance = EXCLUDED.special_allowance,
                other_allowances = EXCLUDED.other_allowances,
                pf_applicable = EXCLUDED.pf_applicable,
                esic_applicable = EXCLUDED.esic_applicable,
                pt_applicable = EXCLUDED.pt_applicable;
        """, (
            employee_id, data.wage_type, data.monthly_gross, data.daily_rate, data.basic_pay,
            data.hra, data.conveyance, data.special_allowance, data.other_allowances,
            data.pf_applicable, data.esic_applicable, data.pt_applicable
        ))
    return {"success": True, "message": "Salary structure updated successfully"}
