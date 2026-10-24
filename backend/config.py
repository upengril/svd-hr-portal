import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
DOCUMENT_DIR = UPLOAD_DIR / "documents"
PHOTO_DIR = UPLOAD_DIR / "photos"
PAYSLIP_DIR = BASE_DIR / "generated_payslips"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
for d in [UPLOAD_DIR, DOCUMENT_DIR, PHOTO_DIR, PAYSLIP_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Remote Update Secret Token
UPDATE_SECRET_KEY = os.getenv("UPDATE_SECRET_KEY", "svd_update_secret_key_2026")

# Database Configuration (Shared with SVD ERP)
DB_CONFIG = {
    "dbname": "svd_erp_dev",
    "user": "postgres",
    "password": "admin",
    "host": "localhost",
    "port": 5432
}
DB_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"

# Biometric Device 2 Configuration (Physical ZKTeco x 2008)
BIOMETRIC_CONFIG = {
    "ip": "192.168.31.111",
    "port": 4370,
    "timeout": 30,
    "force_udp": False,
    "auto_sync_interval_mins": 5
}

# Company Official Identity
COMPANY_INFO = {
    "id": "673eeb08-7278-435e-8a10-f706c46afe64",
    "corporate_name": "SV DREEAMPLANNERS PRIVATE LIMITED",
    "cin": "U45100UP2013PTC056525",
    "incorporation_date": "April 26, 2013",
    "industry": "Site preparation and construction (NIC Code 4510)",
    "registered_address": "C-3/87, 88, 89, First Floor, Vibhuti Khand, Gomti Nagar, Lucknow, Uttar Pradesh, India - 226010",
    "authorized_capital": 35500000.00,
    "paid_up_capital": 1039270.00,
    "directors": [
        "Nitin Chawla",
        "Ashok Vashdew Jagtiani",
        "Snehlata",
        "Mohammad Ubaidullah Faizi",
        "Rakesh Ashok Jagtiani",
        "Kamal Singh"
    ]
}
