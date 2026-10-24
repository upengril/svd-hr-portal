-- SVD HR & Payroll Portal Schema
-- Compatible with PostgreSQL and SVD ERP database (svd_erp_dev)

CREATE TABLE IF NOT EXISTS hr_company_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    corporate_name VARCHAR(255) NOT NULL,
    cin VARCHAR(50) NOT NULL,
    registered_address TEXT NOT NULL,
    industry VARCHAR(255),
    incorporation_date DATE,
    authorized_capital NUMERIC(15,2),
    paid_up_capital NUMERIC(15,2),
    directors JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_shifts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    grace_period_mins INTEGER DEFAULT 15,
    half_day_hours NUMERIC(4,2) DEFAULT 4.50,
    full_day_hours NUMERIC(4,2) DEFAULT 8.00,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    employee_code VARCHAR(50) NOT NULL UNIQUE,
    biometric_id INTEGER UNIQUE,
    card_number VARCHAR(50),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    display_name VARCHAR(255) NOT NULL,
    gender VARCHAR(20) DEFAULT 'MALE',
    date_of_birth DATE,
    blood_group VARCHAR(10),
    marital_status VARCHAR(20) DEFAULT 'SINGLE',
    phone VARCHAR(30),
    email VARCHAR(150),
    emergency_contact_name VARCHAR(100),
    emergency_contact_phone VARCHAR(30),
    present_address TEXT,
    permanent_address TEXT,
    department VARCHAR(100) DEFAULT 'Site Operations',
    designation VARCHAR(100) DEFAULT 'Staff',
    employment_type VARCHAR(50) DEFAULT 'REGULAR',
    date_of_joining DATE DEFAULT CURRENT_DATE,
    shift_id UUID REFERENCES hr_shifts(id) ON DELETE SET NULL,
    photo_url TEXT,
    status VARCHAR(30) DEFAULT 'ACTIVE',
    pan_number VARCHAR(20),
    aadhar_number VARCHAR(20),
    uan_number VARCHAR(30),
    esic_number VARCHAR(30),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_bank_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE UNIQUE,
    account_holder_name VARCHAR(200),
    bank_name VARCHAR(150),
    account_number VARCHAR(50),
    ifsc_code VARCHAR(30),
    branch_name VARCHAR(150),
    account_type VARCHAR(30) DEFAULT 'SAVINGS',
    is_primary BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_qualifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE,
    qualification_type VARCHAR(50) NOT NULL,
    degree_name VARCHAR(150),
    institution VARCHAR(200),
    board_university VARCHAR(200),
    passing_year INTEGER,
    percentage_or_cgpa VARCHAR(30),
    prior_experience_years NUMERIC(4,1) DEFAULT 0,
    previous_company VARCHAR(200),
    previous_designation VARCHAR(150),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    document_title VARCHAR(200) NOT NULL,
    file_path TEXT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),
    verification_status VARCHAR(30) DEFAULT 'PENDING',
    verification_remarks TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_biometric_punches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_ip VARCHAR(50) DEFAULT '192.168.31.111',
    biometric_id INTEGER NOT NULL,
    employee_id UUID REFERENCES hr_employees(id) ON DELETE SET NULL,
    punch_time TIMESTAMP NOT NULL,
    punch_state INTEGER DEFAULT 0,
    verify_type INTEGER DEFAULT 1,
    raw_data TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_biometric_punch UNIQUE (device_ip, biometric_id, punch_time)
);

CREATE TABLE IF NOT EXISTS hr_attendance_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE,
    attendance_date DATE NOT NULL,
    shift_id UUID REFERENCES hr_shifts(id) ON DELETE SET NULL,
    punch_in TIMESTAMP,
    punch_out TIMESTAMP,
    total_work_minutes INTEGER DEFAULT 0,
    overtime_minutes INTEGER DEFAULT 0,
    late_minutes INTEGER DEFAULT 0,
    early_exit_minutes INTEGER DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'PRESENT',
    is_manual_override BOOLEAN DEFAULT FALSE,
    override_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_employee_daily_attendance UNIQUE (employee_id, attendance_date)
);

CREATE TABLE IF NOT EXISTS hr_leaves (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE,
    leave_type VARCHAR(30) NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    days_count NUMERIC(4,1) NOT NULL,
    reason TEXT,
    status VARCHAR(30) DEFAULT 'PENDING',
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_leave_balances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    casual_leave NUMERIC(4,1) DEFAULT 12.0,
    sick_leave NUMERIC(4,1) DEFAULT 10.0,
    earned_leave NUMERIC(4,1) DEFAULT 15.0,
    used_casual_leave NUMERIC(4,1) DEFAULT 0.0,
    used_sick_leave NUMERIC(4,1) DEFAULT 0.0,
    used_earned_leave NUMERIC(4,1) DEFAULT 0.0,
    CONSTRAINT uq_employee_leave_balance UNIQUE (employee_id, year)
);

CREATE TABLE IF NOT EXISTS hr_holidays (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    holiday_name VARCHAR(150) NOT NULL,
    holiday_date DATE NOT NULL UNIQUE,
    holiday_type VARCHAR(50) DEFAULT 'PUBLIC',
    is_optional BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_salary_structures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES hr_employees(id) ON DELETE CASCADE UNIQUE,
    wage_type VARCHAR(30) DEFAULT 'MONTHLY',
    monthly_gross NUMERIC(12,2) DEFAULT 0.00,
    daily_rate NUMERIC(10,2) DEFAULT 0.00,
    basic_pay NUMERIC(12,2) DEFAULT 0.00,
    hra NUMERIC(12,2) DEFAULT 0.00,
    conveyance NUMERIC(12,2) DEFAULT 0.00,
    special_allowance NUMERIC(12,2) DEFAULT 0.00,
    other_allowances NUMERIC(12,2) DEFAULT 0.00,
    pf_applicable BOOLEAN DEFAULT TRUE,
    esic_applicable BOOLEAN DEFAULT TRUE,
    pt_applicable BOOLEAN DEFAULT TRUE,
    effective_from DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hr_payroll_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    status VARCHAR(30) DEFAULT 'DRAFT',
    total_employees INTEGER DEFAULT 0,
    total_gross_payout NUMERIC(15,2) DEFAULT 0.00,
    total_deductions NUMERIC(15,2) DEFAULT 0.00,
    total_net_payout NUMERIC(15,2) DEFAULT 0.00,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payroll_month_year UNIQUE (company_id, month, year)
);

CREATE TABLE IF NOT EXISTS hr_payslips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payroll_run_id UUID REFERENCES hr_payroll_runs(id) ON DELETE CASCADE,
    employee_id UUID REFERENCES hr_employees(id) ON DELETE RESTRICT,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    days_in_month INTEGER NOT NULL,
    paid_days NUMERIC(4,1) NOT NULL,
    present_days NUMERIC(4,1) NOT NULL,
    absent_days NUMERIC(4,1) NOT NULL,
    leave_days NUMERIC(4,1) DEFAULT 0.0,
    holiday_days NUMERIC(4,1) DEFAULT 0.0,
    overtime_hours NUMERIC(5,2) DEFAULT 0.00,
    basic_earned NUMERIC(10,2) DEFAULT 0.00,
    hra_earned NUMERIC(10,2) DEFAULT 0.00,
    conveyance_earned NUMERIC(10,2) DEFAULT 0.00,
    special_allowance_earned NUMERIC(10,2) DEFAULT 0.00,
    overtime_pay NUMERIC(10,2) DEFAULT 0.00,
    gross_earned NUMERIC(12,2) NOT NULL,
    pf_deduction NUMERIC(10,2) DEFAULT 0.00,
    esic_deduction NUMERIC(10,2) DEFAULT 0.00,
    pt_deduction NUMERIC(10,2) DEFAULT 0.00,
    tds_deduction NUMERIC(10,2) DEFAULT 0.00,
    other_deductions NUMERIC(10,2) DEFAULT 0.00,
    total_deductions NUMERIC(12,2) NOT NULL,
    net_pay NUMERIC(12,2) NOT NULL,
    pdf_path TEXT,
    status VARCHAR(30) DEFAULT 'GENERATED',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_employee_month_payslip UNIQUE (employee_id, month, year)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_hr_biometric_punches_time ON hr_biometric_punches(punch_time);
CREATE INDEX IF NOT EXISTS idx_hr_biometric_punches_id ON hr_biometric_punches(biometric_id);
CREATE INDEX IF NOT EXISTS idx_hr_attendance_daily_date ON hr_attendance_daily(attendance_date);
CREATE INDEX IF NOT EXISTS idx_hr_employees_code ON hr_employees(employee_code);
CREATE INDEX IF NOT EXISTS idx_hr_employees_biometric ON hr_employees(biometric_id);
