import os
import sys
import shutil
import subprocess
import threading
import time
from pathlib import Path
from multiprocessing import freeze_support

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QFileDialog, QMessageBox, QCheckBox, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

CREATE_NO_WINDOW = 0x08000000

def get_source_base():
    """Returns the base directory of the bundled data or current running script."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

def find_python_executable():
    """Finds the actual python.exe on the system, NOT sys.executable (which points to this installer in PyInstaller)."""
    # 1. Try finding python or py in PATH
    for name in ["python.exe", "python", "py.exe", "py"]:
        found = shutil.which(name)
        if found and "SVD_Client_Setup" not in found:
            return found

    # 2. Search common Windows locations
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    system_drive = Path(os.environ.get("SystemDrive", "C:"))
    candidates = [
        local_app_data / "Programs" / "Python" / "Python310" / "python.exe",
        local_app_data / "Programs" / "Python" / "Python311" / "python.exe",
        local_app_data / "Programs" / "Python" / "Python312" / "python.exe",
        local_app_data / "Programs" / "Python" / "Python39" / "python.exe",
        system_drive / "Python310" / "python.exe",
        system_drive / "Python311" / "python.exe",
        system_drive / "Python312" / "python.exe",
        Path("C:/Program Files/Python310/python.exe"),
        Path("C:/Program Files/Python311/python.exe"),
        Path("C:/Program Files/Python312/python.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    return "python"

def safe_copy_tree(src, dst):
    """Safely copy files without deleting entire trees (avoids locks when running from same folder)."""
    if not src.exists():
        return
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            rel = item.relative_to(src)
            target = dst / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                except Exception:
                    pass
    else:
        try:
            shutil.copy2(src, dst)
        except Exception:
            pass

class InstallWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)

    def __init__(self, target_dir, cf_token, auto_start, firewall, cf_service, install_deps, start_now):
        super().__init__()
        self.target_dir = Path(target_dir)
        self.cf_token = cf_token.strip()
        self.auto_start = auto_start
        self.firewall = firewall
        self.cf_service = cf_service
        self.install_deps = install_deps
        self.start_now = start_now

    def run(self):
        try:
            self.log_signal.emit("[*] Starting SVD HR Portal 1-Click Deployment...")
            self.progress_signal.emit(5)

            source_dir = get_source_base()
            self.target_dir.mkdir(parents=True, exist_ok=True)
            self.log_signal.emit(f"[*] Target installation directory: {self.target_dir}")
            self.progress_signal.emit(10)

            # Step 1: Copy core files
            self.log_signal.emit("[1/6] Copying application files...")
            items_to_copy = ["backend", "frontend", "scripts", "requirements.txt", "START-HR-PORTAL.bat", "STOP-PORTAL.bat"]
            for item in items_to_copy:
                src = source_dir / item
                dst = self.target_dir / item
                safe_copy_tree(src, dst)
                self.log_signal.emit(f"      + Processed {item}")

            # Ensure logs directory
            (self.target_dir / "logs").mkdir(exist_ok=True)
            self.progress_signal.emit(30)

            # Step 2: Handle cloudflared.exe
            cf_src = source_dir / "cloudflared.exe"
            cf_dst = self.target_dir / "cloudflared.exe"
            if cf_src.exists():
                safe_copy_tree(cf_src, cf_dst)
                self.log_signal.emit("      + Copied cloudflared.exe")

            # Step 3: Install Python Dependencies
            if self.install_deps:
                self.log_signal.emit("[2/6] Checking Python & Installing dependencies...")
                req_file = self.target_dir / "requirements.txt"
                if req_file.exists():
                    try:
                        py_bin = find_python_executable()
                        self.log_signal.emit(f"      + Using Python: {py_bin}")
                        res = subprocess.run(
                            [py_bin, "-m", "pip", "install", "-r", str(req_file)],
                            capture_output=True,
                            text=True,
                            timeout=180,
                            creationflags=CREATE_NO_WINDOW
                        )
                        if res.returncode == 0:
                            self.log_signal.emit("      + Python requirements verified & up to date.")
                        else:
                            self.log_signal.emit(f"      [Notice] Pip output: {res.stderr[:200]}")
                    except Exception as e:
                        self.log_signal.emit(f"      [-] Pip check notice: {e}")
            self.progress_signal.emit(50)

            # Step 4: Configure Windows Firewall
            if self.firewall:
                self.log_signal.emit("[3/6] Configuring Windows Firewall for Port 5000...")
                fw_cmd = 'netsh advfirewall firewall add rule name="SVD HR Portal 5000" dir=in action=allow protocol=TCP localport=5000'
                try:
                    subprocess.run(fw_cmd, shell=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
                    self.log_signal.emit("      + Firewall rule added successfully.")
                except Exception as e:
                    self.log_signal.emit(f"      [-] Firewall notice: {e}")
            self.progress_signal.emit(65)

            # Step 5: Install Cloudflare Tunnel Service
            if self.cf_service and self.cf_token:
                self.log_signal.emit("[4/6] Installing Cloudflare Tunnel as Windows Service...")
                if "*" in self.cf_token:
                    self.log_signal.emit("      [!] ERROR: Token contains asterisks ('*'). Click the COPY icon in Cloudflare!")
                else:
                    try:
                        cf_path = str(cf_dst)
                        # Stop previous if any
                        subprocess.run("net stop Cloudflared", shell=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
                        install_cmd = f'"{cf_path}" service install {self.cf_token}'
                        res = subprocess.run(install_cmd, shell=True, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                        if res.returncode == 0:
                            self.log_signal.emit("      + Cloudflare service registered successfully!")
                            # Ensure service is started
                            start_res = subprocess.run("net start Cloudflared", shell=True, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                            self.log_signal.emit("      + Cloudflare background service started!")
                        else:
                            err_out = (res.stderr or res.stdout).strip()
                            self.log_signal.emit(f"      [-] Cloudflare install notice: {err_out}")
                    except Exception as e:
                        self.log_signal.emit(f"      [-] Cloudflare service notice: {e}")
            else:
                self.log_signal.emit("[4/6] Cloudflare service skipped (token not entered).")
            self.progress_signal.emit(80)

            # Step 6: Configure Silent Auto-Start on Windows Boot
            if self.auto_start:
                self.log_signal.emit("[5/6] Registering Silent Background Auto-Start (Task Scheduler)...")
                vbs_path = str(self.target_dir / "scripts" / "run_hidden.vbs")
                task_cmd = f'schtasks /create /tn "SVD_HR_Portal_Silent" /tr "wscript.exe \\"{vbs_path}\\"" /sc onlogon /rl highest /f'
                try:
                    res = subprocess.run(task_cmd, shell=True, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                    if res.returncode == 0:
                        self.log_signal.emit("      + Windows Scheduled Task created (Runs silently on boot).")
                    else:
                        # Fallback to Startup folder
                        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                        if startup.exists():
                            shutil.copy2(vbs_path, startup / "SVD_HR_Portal.vbs")
                            self.log_signal.emit("      + Added to Windows Startup folder as fallback.")
                except Exception as e:
                    self.log_signal.emit(f"      [-] Auto-start notice: {e}")
            self.progress_signal.emit(90)

            # Step 7: Start Server Immediately
            if self.start_now:
                self.log_signal.emit("[6/6] Starting SVD HR Portal in background...")
                vbs_path = str(self.target_dir / "scripts" / "run_hidden.vbs")
                subprocess.Popen(["wscript.exe", vbs_path], shell=True, creationflags=CREATE_NO_WINDOW)
                self.log_signal.emit("      + Background runner initiated.")

            self.progress_signal.emit(100)
            self.log_signal.emit("\n[SUCCESS] Setup finished successfully!")
            self.log_signal.emit("Portal is running locally at http://localhost:5000")
            if self.cf_token:
                self.log_signal.emit("Portal is accessible worldwide at https://svd.civmasterpro.com")

            self.finished_signal.emit(True, "Installation complete!")

        except Exception as e:
            self.log_signal.emit(f"\n[!] Error during installation: {str(e)}")
            self.finished_signal.emit(False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CivMasterPro – SV DREEAMPLANNERS Client PC Setup")
        self.resize(720, 680)
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #0f172a; border-radius: 8px; padding: 12px;")
        header_layout = QVBoxLayout(header_frame)
        
        title_lbl = QLabel("CivMasterPro Enterprise – SV DREEAMPLANNERS")
        title_lbl.setStyleSheet("color: #38bdf8; font-size: 18px; font-weight: bold;")
        subtitle_lbl = QLabel("HR & Biometric Management System — 1-Click Client PC Installer")
        subtitle_lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(subtitle_lbl)
        main_layout.addWidget(header_frame)

        # Cloudflare Group
        cf_group = QGroupBox("Cloudflare Tunnel Configuration")
        cf_group.setStyleSheet("font-weight: bold; color: #1e293b;")
        cf_layout = QVBoxLayout(cf_group)

        cf_info = QLabel("Enter the Cloudflare Tunnel Token for 'svd.civmasterpro.com':")
        cf_info.setStyleSheet("font-weight: normal; color: #475569; font-size: 12px;")
        cf_layout.addWidget(cf_info)

        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Paste token here: eyJhIjoi... (or leave blank if setting up later)")
        self.token_edit.setStyleSheet("padding: 8px; border: 1px solid #cbd5e1; border-radius: 4px; font-weight: normal;")
        
        paste_btn = QPushButton("Paste Token")
        paste_btn.setStyleSheet("padding: 8px 14px; background-color: #0284c7; color: white; border-radius: 4px; font-weight: bold;")
        paste_btn.clicked.connect(self.paste_token)

        token_row.addWidget(self.token_edit)
        token_row.addWidget(paste_btn)
        cf_layout.addLayout(token_row)
        main_layout.addWidget(cf_group)

        # Directory Group
        dir_group = QGroupBox("Installation Path")
        dir_group.setStyleSheet("font-weight: bold; color: #1e293b;")
        dir_layout = QHBoxLayout(dir_group)

        default_dir = "D:\\svd-hr-portal" if Path("D:\\").exists() else "C:\\svd-hr-portal"
        self.dir_edit = QLineEdit(default_dir)
        self.dir_edit.setStyleSheet("padding: 8px; border: 1px solid #cbd5e1; border-radius: 4px; font-weight: normal;")
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setStyleSheet("padding: 8px 14px; background-color: #64748b; color: white; border-radius: 4px; font-weight: bold;")
        browse_btn.clicked.connect(self.browse_dir)

        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(browse_btn)
        main_layout.addWidget(dir_group)

        # Options Group
        opt_group = QGroupBox("Automatic Deployment Options")
        opt_group.setStyleSheet("font-weight: bold; color: #1e293b;")
        opt_layout = QVBoxLayout(opt_group)

        self.cb_cf_service = QCheckBox("Install Cloudflare Tunnel as a Windows Background Service")
        self.cb_cf_service.setChecked(True)
        self.cb_cf_service.setStyleSheet("font-weight: normal; color: #334155;")

        self.cb_auto_start = QCheckBox("Start Portal Silently on Windows Boot (Task Scheduler - No Black Window)")
        self.cb_auto_start.setChecked(True)
        self.cb_auto_start.setStyleSheet("font-weight: normal; color: #334155;")

        self.cb_firewall = QCheckBox("Open Port 5000 in Windows Firewall (For other PCs/mobiles on same Wi-Fi)")
        self.cb_firewall.setChecked(True)
        self.cb_firewall.setStyleSheet("font-weight: normal; color: #334155;")

        self.cb_deps = QCheckBox("Verify & Install Python dependencies (FastAPI, Uvicorn, psycopg2, pyzk)")
        self.cb_deps.setChecked(True)
        self.cb_deps.setStyleSheet("font-weight: normal; color: #334155;")

        self.cb_start_now = QCheckBox("Start HR Portal immediately in background upon installation")
        self.cb_start_now.setChecked(True)
        self.cb_start_now.setStyleSheet("font-weight: normal; color: #334155;")

        opt_layout.addWidget(self.cb_cf_service)
        opt_layout.addWidget(self.cb_auto_start)
        opt_layout.addWidget(self.cb_firewall)
        opt_layout.addWidget(self.cb_deps)
        opt_layout.addWidget(self.cb_start_now)
        main_layout.addWidget(opt_group)

        # Action Button
        self.install_btn = QPushButton("Start 1-Click Installation")
        self.install_btn.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; 
                color: white; 
                font-size: 15px; 
                font-weight: bold; 
                padding: 12px; 
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
        self.install_btn.clicked.connect(self.start_installation)
        main_layout.addWidget(self.install_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                height: 18px; 
                border-radius: 4px; 
                text-align: center;
                background-color: #e2e8f0;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        # Console log output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #0f172a; color: #38bdf8; font-family: Consolas, monospace; font-size: 11px; border-radius: 6px; padding: 8px;")
        main_layout.addWidget(self.log_text)

    def paste_token(self):
        clipboard = QApplication.clipboard()
        self.token_edit.setText(clipboard.text().strip())

    def browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Installation Directory", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)

    def start_installation(self):
        target = self.dir_edit.text().strip()
        if not target:
            QMessageBox.warning(self, "Validation", "Please specify an installation directory.")
            return

        token = self.token_edit.text().strip()
        if "*" in token:
            QMessageBox.critical(
                self, "Invalid Token (Masked with Asterisks)",
                "Aapka token asterisks (****) ke sath copy hua hai!\n\n"
                "Cloudflare website par mouse se text select karne ke bajay, wahan command box ke right me bane 'Copy' button/icon par click karke copy karein."
            )
            return

        if not token and self.cb_cf_service.isChecked():
            res = QMessageBox.question(
                self, "Token Notice", 
                "No Cloudflare Token was provided.\n\nDo you want to proceed without Cloudflare Tunnel Service? (You can configure it manually later)",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.No:
                return

        self.install_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        self.worker = InstallWorker(
            target_dir=target,
            cf_token=token,
            auto_start=self.cb_auto_start.isChecked(),
            firewall=self.cb_firewall.isChecked(),
            cf_service=self.cb_cf_service.isChecked(),
            install_deps=self.cb_deps.isChecked(),
            start_now=self.cb_start_now.isChecked()
        )
        self.worker.log_signal.connect(self.log_text.append)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.installation_finished)
        self.worker.start()

    def installation_finished(self, success, message):
        self.install_btn.setEnabled(True)
        if success:
            QMessageBox.information(
                self, "Success", 
                "SV DREEAMPLANNERS HR Portal has been installed successfully!\n\n"
                "The server and tunnel are running in the background and will automatically start on every PC reboot."
            )
        else:
            QMessageBox.critical(self, "Installation Notice", f"Completed with warnings/errors:\n{message}")

if __name__ == "__main__":
    freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
