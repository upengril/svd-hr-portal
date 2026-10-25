// SV DREEAMPLANNERS – HR & Biometric Web Portal Controller

let currentTab = 'dashboard';
let employeesList = [];
let allEmployeesMap = {};
let currentPayrollRunId = null;

// Clock
function updateClock() {
  const now = new Date();
  const timeEl = document.getElementById('header-clock');
  const dateEl = document.getElementById('header-date');
  if (timeEl) timeEl.textContent = now.toLocaleTimeString('en-IN');
  if (dateEl) dateEl.textContent = now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}
setInterval(updateClock, 1000);
updateClock();

// Toast Notifications
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-600 text-white',
    error: 'bg-rose-600 text-white',
    info: 'bg-slate-900 text-white',
    warning: 'bg-amber-600 text-white'
  };
  toast.className = `${colors[type] || colors.info} px-4 py-2.5 rounded-lg shadow-lg text-xs font-medium flex items-center space-x-2 pointer-events-auto transition-all duration-300 transform translate-y-2 opacity-0`;
  toast.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle')}"></i><span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.classList.remove('translate-y-2', 'opacity-0'), 10);
  setTimeout(() => {
    toast.classList.add('opacity-0');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Tab Switching
function switchTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  const target = document.getElementById(`tab-${tabId}`);
  if (target) target.classList.remove('hidden');

  document.querySelectorAll('.nav-tab').forEach(el => {
    if (el.dataset.tab === tabId) {
      el.classList.add('active', 'bg-slate-900', 'text-white', 'border-b-2', 'border-teal-400');
      el.classList.remove('text-slate-300');
    } else {
      el.classList.remove('active', 'bg-slate-900', 'text-white', 'border-b-2', 'border-teal-400');
      el.classList.add('text-slate-300');
    }
  });

  if (tabId === 'dashboard') loadDashboard();
  if (tabId === 'employees') loadEmployees();
  if (tabId === 'attendance') loadDailyAttendance();
  if (tabId === 'timesheet') loadMonthlyTimesheet();
  if (tabId === 'monthly-report') loadMonthlyDetailReport();
  if (tabId === 'leaves') loadLeaves();
  if (tabId === 'payroll') loadPayroll();
  if (tabId === 'documents') loadDocuments();
  if (tabId === 'system-updates') checkSystemStatusUI();
}

// 1. DASHBOARD LOGIC
async function loadDashboard() {
  try {
    const res = await fetch('/api/dashboard/summary');
    const data = await res.json();

    document.getElementById('dash-total').textContent = data.metrics.total_employees;
    document.getElementById('dash-present').textContent = data.metrics.present_today;
    document.getElementById('dash-late').textContent = data.metrics.late_today;
    document.getElementById('dash-halfday').textContent = data.metrics.half_day_today;
    document.getElementById('dash-absent').textContent = data.metrics.absent_today;
    document.getElementById('dash-ot').textContent = data.metrics.overtime_today;

    const tbody = document.getElementById('dash-punches-table');
    tbody.innerHTML = '';
    if (data.recent_punches.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-slate-400">No punches recorded yet today.</td></tr>';
      return;
    }

    data.recent_punches.forEach(p => {
      const tr = document.createElement('tr');
      const isOut = p.punch_state === 1;
      const timeStr = p.punch_time.replace('T', ' ');
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono text-[11px]">${timeStr}</td>
        <td class="py-2.5 px-3 font-semibold text-slate-800">${p.employee_name}</td>
        <td class="py-2.5 px-3 font-mono text-teal-700 font-medium">${p.employee_code}</td>
        <td class="py-2.5 px-3 text-slate-500">${p.department || 'Site Operations'}</td>
        <td class="py-2.5 px-3 text-right">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${isOut ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
            ${isOut ? 'OUT' : 'IN'}
          </span>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to load dashboard:', err);
  }
}

// 2. BIOMETRIC SYNC
async function triggerBiometricSync() {
  const icon = document.getElementById('sync-icon');
  icon.classList.add('fa-spin');
  showToast('Connecting to Device 2 (192.168.31.111:4370) to pull latest punches...', 'info');

  try {
    const res = await fetch('/api/biometric/sync', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`Sync complete! ${data.new_punches_synced} new punches downloaded.`, 'success');
      loadDashboard();
      if (currentTab === 'attendance') loadDailyAttendance();
    } else {
      showToast(`Device sync error: ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Failed to reach backend service', 'error');
  } finally {
    icon.classList.remove('fa-spin');
  }
}

// 3. EMPLOYEES LOGIC
async function loadEmployees() {
  const tbody = document.getElementById('employees-table-body');
  tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-400">Loading 329 employees...</td></tr>';

  try {
    const res = await fetch('/api/employees?limit=500');
    const data = await res.json();
    employeesList = data.employees;

    // Populate lookup map
    employeesList.forEach(e => {
      allEmployeesMap[e.id] = e;
    });

    renderEmployeesTable(employeesList);
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-rose-500">Failed to load employees.</td></tr>';
  }
}

function renderEmployeesTable(list) {
  const tbody = document.getElementById('employees-table-body');
  tbody.innerHTML = '';

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-400">No employees match criteria.</td></tr>';
    return;
  }

  list.forEach(e => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50 transition';
    
    // Mask Aadhaar
    const rawAadhaar = e.aadhar_number || '';
    const maskedAadhaar = rawAadhaar.length >= 4 ? `XXXX-XXXX-${rawAadhaar.slice(-4)}` : (rawAadhaar || '<span class="text-slate-300">Pending</span>');
    const panDisplay = e.pan_number || '<span class="text-slate-300">Pending</span>';
    const bankDisplay = e.bank_name ? `${e.bank_name} (${e.account_number ? e.account_number.slice(-4) : ''})` : '<span class="text-slate-300">Pending</span>';

    tr.innerHTML = `
      <td class="py-2.5 px-4 font-mono font-bold text-slate-700">${e.biometric_id || '-'}</td>
      <td class="py-2.5 px-4 font-mono text-teal-700 font-medium">${e.employee_code}</td>
      <td class="py-2.5 px-4">
        <div class="font-bold text-slate-800">${e.display_name}</div>
        <div class="text-[10px] text-slate-400">${e.employment_type || 'REGULAR'}</div>
      </td>
      <td class="py-2.5 px-4">
        <div class="font-medium text-slate-700">${e.department || 'Site Operations'}</div>
        <div class="text-[10px] text-slate-400">${e.designation || 'Staff'}</div>
      </td>
      <td class="py-2.5 px-4 text-slate-600">${e.phone || '<span class="text-slate-300">--</span>'}</td>
      <td class="py-2.5 px-4 text-[11px]">
        <div>PAN: <span class="font-mono font-medium">${panDisplay}</span></div>
        <div>Aadhaar: <span class="font-mono">${maskedAadhaar}</span></div>
      </td>
      <td class="py-2.5 px-4 text-[11px] text-slate-600">${bankDisplay}</td>
      <td class="py-2.5 px-4 text-center">
        <button onclick="viewEmployeeProfile('${e.id}')" class="bg-teal-50 hover:bg-teal-100 text-teal-700 px-2.5 py-1 rounded text-[11px] font-semibold transition">
          <i class="fas fa-id-card mr-1"></i> Profile 360°
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterEmployees() {
  const query = document.getElementById('emp-search-input').value.toLowerCase().trim();
  const dept = document.getElementById('emp-dept-filter').value;

  const filtered = employeesList.filter(e => {
    const matchQuery = !query || 
      (e.display_name && e.display_name.toLowerCase().includes(query)) ||
      (e.employee_code && e.employee_code.toLowerCase().includes(query)) ||
      (e.biometric_id && e.biometric_id.toString().includes(query)) ||
      (e.pan_number && e.pan_number.toLowerCase().includes(query)) ||
      (e.aadhar_number && e.aadhar_number.toLowerCase().includes(query)) ||
      (e.phone && e.phone.includes(query));

    const matchDept = !dept || e.department === dept;
    return matchQuery && matchDept;
  });

  renderEmployeesTable(filtered);
}

// 4. VIEW EMPLOYEE 360° PROFILE MODAL
async function viewEmployeeProfile(employeeId) {
  try {
    const res = await fetch(`/api/employees/${employeeId}`);
    const data = await res.json();
    const emp = data.employee;
    const bank = data.bank_details || {};
    const salary = data.salary_structure || {};

    const container = document.getElementById('modal-container');
    container.innerHTML = `
      <div class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
          
          <!-- Modal Header -->
          <div class="bg-slate-900 text-white px-6 py-4 flex items-center justify-between border-b border-slate-800">
            <div class="flex items-center space-x-3">
              <div class="w-10 h-10 rounded-full bg-teal-600 flex items-center justify-center font-bold text-white text-base">
                ${emp.display_name.charAt(0).toUpperCase()}
              </div>
              <div>
                <h3 class="text-base font-bold">${emp.display_name}</h3>
                <p class="text-xs text-teal-400 font-mono">${emp.employee_code} • Biometric Terminal ID: ${emp.biometric_id || 'N/A'}</p>
              </div>
            </div>
            <button onclick="closeModal()" class="text-slate-400 hover:text-white text-lg"><i class="fas fa-times"></i></button>
          </div>

          <!-- Modal Tabs -->
          <div class="bg-slate-100 border-b border-slate-200 px-6 flex space-x-4 text-xs font-semibold">
            <button onclick="switchProfileSubTab('personal')" class="prof-sub-tab active py-3 border-b-2 border-teal-600 text-teal-800" data-subtab="personal">Personal & KYC</button>
            <button onclick="switchProfileSubTab('bank')" class="prof-sub-tab py-3 text-slate-500 hover:text-slate-800" data-subtab="bank">Bank Account</button>
            <button onclick="switchProfileSubTab('qualifications')" class="prof-sub-tab py-3 text-slate-500 hover:text-slate-800" data-subtab="qualifications">Qualifications & Exp</button>
            <button onclick="switchProfileSubTab('salary')" class="prof-sub-tab py-3 text-slate-500 hover:text-slate-800" data-subtab="salary">Salary Structure</button>
            <button onclick="switchProfileSubTab('docs')" class="prof-sub-tab py-3 text-slate-500 hover:text-slate-800" data-subtab="docs">Documents (${data.documents.length})</button>
          </div>

          <!-- Modal Body -->
          <div class="flex-1 overflow-y-auto p-6 text-xs custom-scrollbar">
            
            <!-- SUBTAB 1: PERSONAL & KYC -->
            <div id="subtab-personal" class="prof-sub-content space-y-4">
              <form id="profile-edit-form" onsubmit="saveEmployeePersonal(event, '${emp.id}')">
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">First Name *</label>
                    <input type="text" id="prof-fname" value="${emp.first_name || ''}" required class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Last Name</label>
                    <input type="text" id="prof-lname" value="${emp.last_name || ''}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Gender</label>
                    <select id="prof-gender" class="w-full p-2 border border-slate-300 rounded-lg">
                      <option value="MALE" ${emp.gender === 'MALE' ? 'selected' : ''}>Male</option>
                      <option value="FEMALE" ${emp.gender === 'FEMALE' ? 'selected' : ''}>Female</option>
                      <option value="OTHER" ${emp.gender === 'OTHER' ? 'selected' : ''}>Other</option>
                    </select>
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Phone Number</label>
                    <input type="text" id="prof-phone" value="${emp.phone || ''}" placeholder="e.g. 9876543210" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Email</label>
                    <input type="email" id="prof-email" value="${emp.email || ''}" placeholder="name@svderp.local" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Date of Birth</label>
                    <input type="date" id="prof-dob" value="${emp.date_of_birth || ''}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Blood Group</label>
                    <input type="text" id="prof-blood" value="${emp.blood_group || ''}" placeholder="e.g. O+, B+" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Department</label>
                    <input type="text" id="prof-dept" value="${emp.department || 'Site Operations'}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Designation</label>
                    <input type="text" id="prof-desig" value="${emp.designation || 'Staff'}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                </div>

                <div class="border-t border-slate-200 pt-3 mt-4">
                  <h4 class="font-bold text-slate-700 uppercase tracking-wider text-[11px] mb-2">Statutory Identifiers (KYC)</h4>
                  <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">PAN Card Number</label>
                      <input type="text" id="prof-pan" value="${emp.pan_number || ''}" placeholder="ABCDE1234F" class="w-full p-2 border border-slate-300 rounded-lg uppercase">
                    </div>
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">Aadhaar Number</label>
                      <input type="text" id="prof-aadhar" value="${emp.aadhar_number || ''}" placeholder="12-digit Aadhaar" class="w-full p-2 border border-slate-300 rounded-lg">
                    </div>
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">UAN / PF Number</label>
                      <input type="text" id="prof-uan" value="${emp.uan_number || ''}" placeholder="UAN / PF No" class="w-full p-2 border border-slate-300 rounded-lg">
                    </div>
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">ESIC Number</label>
                      <input type="text" id="prof-esic" value="${emp.esic_number || ''}" placeholder="ESIC Insurance No" class="w-full p-2 border border-slate-300 rounded-lg">
                    </div>
                  </div>
                </div>

                <div class="border-t border-slate-200 pt-3 mt-4">
                  <h4 class="font-bold text-slate-700 uppercase tracking-wider text-[11px] mb-2">Address & Emergency Contact</h4>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">Present Address</label>
                      <textarea id="prof-present-addr" rows="2" class="w-full p-2 border border-slate-300 rounded-lg">${emp.present_address || ''}</textarea>
                    </div>
                    <div>
                      <label class="block text-slate-500 font-medium mb-1">Emergency Contact (Name & Phone)</label>
                      <input type="text" id="prof-emer-name" value="${emp.emergency_contact_name || ''}" placeholder="Contact Person" class="w-full p-2 border border-slate-300 rounded-lg mb-1">
                      <input type="text" id="prof-emer-phone" value="${emp.emergency_contact_phone || ''}" placeholder="Contact Phone" class="w-full p-2 border border-slate-300 rounded-lg">
                    </div>
                  </div>
                </div>

                <div class="flex justify-end pt-4">
                  <button type="submit" class="bg-teal-600 hover:bg-teal-500 text-white px-5 py-2 rounded-lg font-semibold shadow transition">Save Personal & KYC Details</button>
                </div>
              </form>
            </div>

            <!-- SUBTAB 2: BANK ACCOUNT -->
            <div id="subtab-bank" class="prof-sub-content hidden space-y-4">
              <form onsubmit="saveEmployeeBank(event, '${emp.id}')">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Account Holder Name *</label>
                    <input type="text" id="bank-holder" value="${bank.account_holder_name || emp.display_name}" required class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Bank Account Number</label>
                    <input type="text" id="bank-acc" value="${bank.account_number || ''}" placeholder="Account Number" class="w-full p-2 border border-slate-300 rounded-lg font-mono">
                  </div>

                  <!-- Online IFSC Auto-Fetch Box -->
                  <div class="sm:col-span-2 bg-gradient-to-r from-teal-50/70 via-cyan-50/50 to-slate-50 p-3.5 rounded-xl border border-teal-200">
                    <div class="flex items-center justify-between mb-1.5">
                      <label class="text-xs font-bold text-teal-900 flex items-center gap-1.5">
                        <i class="fas fa-building-columns text-teal-600"></i>
                        <span>IFSC Code (Online Auto-Fetch Bank & Branch)</span>
                      </label>
                      <span id="ifsc-status-pill" class="text-[11px] font-semibold text-slate-500">
                        ${bank.ifsc_code ? '<span class="text-emerald-700 font-bold flex items-center gap-1"><i class="fas fa-circle-check"></i> ' + (bank.bank_name || 'Bank Linked') + '</span>' : 'Type 11-digit IFSC'}
                      </span>
                    </div>

                    <div class="flex items-center gap-2">
                      <div class="relative flex-1">
                        <input type="text" id="bank-ifsc" value="${bank.ifsc_code || ''}" placeholder="e.g. SBIN0001234, HDFC0000001, PUNB0000100" maxlength="11" oninput="handleIfscAutoFetch(this.value)" class="w-full p-2.5 pr-8 border border-slate-300 rounded-lg font-mono font-bold text-slate-800 uppercase tracking-wider bg-white focus:ring-2 focus:ring-teal-500 focus:outline-none">
                        <div id="ifsc-loading-spinner" class="absolute right-3 top-3 hidden text-teal-600 text-xs">
                          <i class="fas fa-spinner fa-spin"></i>
                        </div>
                      </div>
                      <button type="button" onclick="fetchIfscManual()" class="px-3.5 py-2.5 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-xs font-bold shadow-xs transition flex items-center gap-1.5 cursor-pointer">
                        <i class="fas fa-magnifying-glass"></i>
                        <span>Fetch</span>
                      </button>
                    </div>

                    <div id="ifsc-info-box" class="mt-2.5 text-[11px] text-teal-900 ${bank.branch_name ? '' : 'hidden'} bg-white p-2.5 rounded-lg border border-teal-200 shadow-xs">
                      ${bank.bank_name ? `
                        <div class="flex items-start justify-between">
                          <div>
                            <div class="font-bold text-slate-800 text-xs">${bank.bank_name} – ${bank.branch_name || ''}</div>
                            <div class="text-slate-500 text-[10px] mt-0.5">IFSC: <span class="font-mono font-bold text-teal-700">${bank.ifsc_code || ''}</span></div>
                          </div>
                          <span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[10px]">VERIFIED</span>
                        </div>
                      ` : ''}
                    </div>
                  </div>

                  <div>
                    <label class="block text-slate-500 font-medium mb-1 flex items-center justify-between">
                      <span>Bank Name</span>
                      <span class="text-[10px] text-teal-600 font-normal">Auto-filled</span>
                    </label>
                    <input type="text" id="bank-name" value="${bank.bank_name || ''}" placeholder="Auto-selected on IFSC fetch" class="w-full p-2 border border-slate-300 rounded-lg font-medium text-slate-800 bg-slate-50">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1 flex items-center justify-between">
                      <span>Branch Name</span>
                      <span class="text-[10px] text-teal-600 font-normal">Auto-filled</span>
                    </label>
                    <input type="text" id="bank-branch" value="${bank.branch_name || ''}" placeholder="Auto-selected on IFSC fetch" class="w-full p-2 border border-slate-300 rounded-lg font-medium text-slate-800 bg-slate-50">
                  </div>
                  <div class="sm:col-span-2">
                    <label class="block text-slate-500 font-medium mb-1">Account Type</label>
                    <select id="bank-type" class="w-full p-2 border border-slate-300 rounded-lg">
                      <option value="SAVINGS" ${bank.account_type === 'SAVINGS' ? 'selected' : ''}>Savings Account</option>
                      <option value="CURRENT" ${bank.account_type === 'CURRENT' ? 'selected' : ''}>Current Account</option>
                      <option value="SALARY" ${bank.account_type === 'SALARY' ? 'selected' : ''}>Salary Account</option>
                    </select>
                  </div>
                </div>
                <div class="flex justify-end pt-4">
                  <button type="submit" class="bg-teal-600 hover:bg-teal-500 text-white px-5 py-2 rounded-lg font-semibold shadow transition cursor-pointer">Save Bank Details</button>
                </div>
              </form>
            </div>

            <!-- SUBTAB 3: QUALIFICATIONS -->
            <div id="subtab-qualifications" class="prof-sub-content hidden space-y-4">
              <div class="flex justify-between items-center border-b pb-2">
                <h4 class="font-bold text-slate-700">Educational Background & Past Work Experience</h4>
              </div>

              <!-- List -->
              <div class="space-y-2">
                ${data.qualifications.length === 0 ? '<p class="text-slate-400 py-2">No educational records or work experience added yet.</p>' : ''}
                ${data.qualifications.map(q => `
                  <div class="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div>
                      <div class="font-bold text-slate-800">${q.qualification_type}: ${q.degree_name || ''}</div>
                      <div class="text-slate-500">${q.institution || q.board_university || ''} (${q.passing_year || 'Year N/A'})</div>
                      ${q.previous_company ? `<div class="text-teal-700 text-[11px] font-medium mt-0.5">Prior Experience: ${q.prior_experience_years || 0} yrs at ${q.previous_company} (${q.previous_designation || ''})</div>` : ''}
                    </div>
                    <button onclick="deleteQualification('${q.id}', '${emp.id}')" class="text-rose-500 hover:text-rose-700 text-sm p-1"><i class="fas fa-trash"></i></button>
                  </div>
                `).join('')}
              </div>

              <!-- Add Form -->
              <form onsubmit="addEmployeeQualification(event, '${emp.id}')" class="bg-slate-50 p-4 border border-slate-200 rounded-lg space-y-3">
                <h5 class="font-bold text-slate-700">Add Degree / Experience Record</h5>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <select id="qual-type" required class="p-2 border border-slate-300 rounded-lg">
                    <option value="GRADUATION">Graduation (B.Tech / B.Sc / B.Com)</option>
                    <option value="DIPLOMA">Polytechnic / Diploma</option>
                    <option value="ITI">ITI Technical</option>
                    <option value="12TH">12th Standard</option>
                    <option value="10TH">10th Standard</option>
                    <option value="POST_GRADUATION">Post Graduation (M.Tech / MBA)</option>
                  </select>
                  <input type="text" id="qual-degree" placeholder="Degree / Course Name" required class="p-2 border border-slate-300 rounded-lg">
                  <input type="text" id="qual-inst" placeholder="College / University" class="p-2 border border-slate-300 rounded-lg">
                  <input type="number" id="qual-year" placeholder="Passing Year" min="1980" max="2026" class="p-2 border border-slate-300 rounded-lg">
                  <input type="text" id="qual-prev-comp" placeholder="Previous Company (if any)" class="p-2 border border-slate-300 rounded-lg">
                  <input type="number" step="0.5" id="qual-exp-yrs" placeholder="Experience Years" class="p-2 border border-slate-300 rounded-lg">
                </div>
                <button type="submit" class="bg-slate-900 hover:bg-slate-800 text-white px-4 py-1.5 rounded-lg font-semibold">Add Record</button>
              </form>
            </div>

            <!-- SUBTAB 4: SALARY STRUCTURE -->
            <div id="subtab-salary" class="prof-sub-content hidden space-y-4">
              <form onsubmit="saveEmployeeSalary(event, '${emp.id}')">
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Wage / Compensation Type</label>
                    <select id="sal-wage-type" class="w-full p-2 border border-slate-300 rounded-lg">
                      <option value="MONTHLY" ${salary.wage_type === 'MONTHLY' ? 'selected' : ''}>Monthly Fixed Salary</option>
                      <option value="DAILY_WAGE" ${salary.wage_type === 'DAILY_WAGE' ? 'selected' : ''}>Daily Wage Rate</option>
                    </select>
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Monthly Gross (₹)</label>
                    <input type="number" id="sal-gross" value="${salary.monthly_gross || 25000}" onkeyup="calculateSalaryComponents()" class="w-full p-2 border border-slate-300 rounded-lg font-bold text-teal-700">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Daily Wage Rate (₹)</label>
                    <input type="number" id="sal-daily-rate" value="${salary.daily_rate || 850}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Basic Pay (50%)</label>
                    <input type="number" id="sal-basic" value="${salary.basic_pay || 12500}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">HRA (20%)</label>
                    <input type="number" id="sal-hra" value="${salary.hra || 5000}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Conveyance Allowance</label>
                    <input type="number" id="sal-conveyance" value="${salary.conveyance || 2500}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                  <div>
                    <label class="block text-slate-500 font-medium mb-1">Special Allowance</label>
                    <input type="number" id="sal-special" value="${salary.special_allowance || 5000}" class="w-full p-2 border border-slate-300 rounded-lg">
                  </div>
                </div>

                <div class="border-t border-slate-200 pt-3 mt-4 space-y-2">
                  <h4 class="font-bold text-slate-700 text-[11px] uppercase tracking-wider">Statutory Deductions Applicability</h4>
                  <div class="flex items-center space-x-6">
                    <label class="flex items-center space-x-2">
                      <input type="checkbox" id="sal-pf" ${salary.pf_applicable !== false ? 'checked' : ''} class="rounded text-teal-600">
                      <span>Provident Fund (PF - 12%)</span>
                    </label>
                    <label class="flex items-center space-x-2">
                      <input type="checkbox" id="sal-esic" ${salary.esic_applicable !== false ? 'checked' : ''} class="rounded text-teal-600">
                      <span>ESIC (0.75%)</span>
                    </label>
                    <label class="flex items-center space-x-2">
                      <input type="checkbox" id="sal-pt" ${salary.pt_applicable !== false ? 'checked' : ''} class="rounded text-teal-600">
                      <span>Professional Tax (PT - ₹200)</span>
                    </label>
                  </div>
                </div>

                <div class="flex justify-end pt-4">
                  <button type="submit" class="bg-teal-600 hover:bg-teal-500 text-white px-5 py-2 rounded-lg font-semibold shadow transition">Save Salary Structure</button>
                </div>
              </form>
            </div>

            <!-- SUBTAB 5: DOCUMENTS -->
            <div id="subtab-docs" class="prof-sub-content hidden space-y-4">
              <div class="flex justify-between items-center border-b pb-2">
                <h4 class="font-bold text-slate-700">Uploaded KYC & Educational Files</h4>
                <button onclick="openUploadDocModal('${emp.id}')" class="bg-teal-600 hover:bg-teal-500 text-white px-3 py-1 rounded text-xs font-semibold">Upload New</button>
              </div>

              <div class="space-y-2">
                ${data.documents.length === 0 ? '<p class="text-slate-400 py-3">No documents uploaded for this employee yet.</p>' : ''}
                ${data.documents.map(d => `
                  <div class="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div class="flex items-center space-x-3">
                      <i class="fas fa-file-pdf text-rose-500 text-xl"></i>
                      <div>
                        <div class="font-bold text-slate-800">${d.document_title} <span class="text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded ml-1">${d.document_type}</span></div>
                        <div class="text-[10px] text-slate-400 font-mono">${d.file_name} • ${(d.file_size / 1024).toFixed(1)} KB</div>
                      </div>
                    </div>
                    <div class="flex items-center space-x-2">
                      <span class="px-2 py-0.5 rounded text-[10px] font-bold ${d.verification_status === 'VERIFIED' ? 'bg-emerald-100 text-emerald-800' : (d.verification_status === 'REJECTED' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800')}">
                        ${d.verification_status}
                      </span>
                      <a href="/api/documents/${d.id}/download" target="_blank" class="bg-slate-200 hover:bg-slate-300 text-slate-800 px-2 py-1 rounded text-xs">
                        <i class="fas fa-download"></i>
                      </a>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>

          </div>

          <!-- Modal Footer -->
          <div class="bg-slate-100 px-6 py-3 border-t border-slate-200 flex justify-end">
            <button onclick="closeModal()" class="bg-slate-300 hover:bg-slate-400 text-slate-800 px-4 py-1.5 rounded-lg font-semibold text-xs transition">Close</button>
          </div>

        </div>
      </div>
    `;
  } catch (err) {
    showToast('Failed to load employee details', 'error');
  }
}

function switchProfileSubTab(subTabId) {
  document.querySelectorAll('.prof-sub-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.prof-sub-tab').forEach(el => {
    el.classList.remove('active', 'border-b-2', 'border-teal-600', 'text-teal-800');
    el.classList.add('text-slate-500');
  });

  const target = document.getElementById(`subtab-${subTabId}`);
  if (target) target.classList.remove('hidden');

  const btn = document.querySelector(`.prof-sub-tab[data-subtab="${subTabId}"]`);
  if (btn) {
    btn.classList.add('active', 'border-b-2', 'border-teal-600', 'text-teal-800');
    btn.classList.remove('text-slate-500');
  }
}

function closeModal() {
  const container = document.getElementById('modal-container');
  container.innerHTML = '';
}

// Save Personal & KYC
async function saveEmployeePersonal(e, empId) {
  e.preventDefault();
  const payload = {
    first_name: document.getElementById('prof-fname').value,
    last_name: document.getElementById('prof-lname').value,
    gender: document.getElementById('prof-gender').value,
    phone: document.getElementById('prof-phone').value,
    email: document.getElementById('prof-email').value,
    date_of_birth: document.getElementById('prof-dob').value || null,
    blood_group: document.getElementById('prof-blood').value,
    department: document.getElementById('prof-dept').value,
    designation: document.getElementById('prof-desig').value,
    pan_number: document.getElementById('prof-pan').value.toUpperCase(),
    aadhar_number: document.getElementById('prof-aadhar').value,
    uan_number: document.getElementById('prof-uan').value,
    esic_number: document.getElementById('prof-esic').value,
    present_address: document.getElementById('prof-present-addr').value,
    emergency_contact_name: document.getElementById('prof-emer-name').value,
    emergency_contact_phone: document.getElementById('prof-emer-phone').value,
    status: 'ACTIVE'
  };

  try {
    const res = await fetch(`/api/employees/${empId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Personal and KYC details saved successfully!', 'success');
      loadEmployees();
    }
  } catch (err) {
    showToast('Failed to save personal details', 'error');
  }
}

// Save Bank Details
async function saveEmployeeBank(e, empId) {
  e.preventDefault();
  const payload = {
    account_holder_name: document.getElementById('bank-holder').value,
    bank_name: document.getElementById('bank-name').value,
    account_number: document.getElementById('bank-acc').value,
    ifsc_code: document.getElementById('bank-ifsc').value.toUpperCase(),
    branch_name: document.getElementById('bank-branch').value,
    account_type: document.getElementById('bank-type').value
  };

  try {
    const res = await fetch(`/api/employees/${empId}/bank`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Bank details updated successfully!', 'success');
      loadEmployees();
    }
  } catch (err) {
    showToast('Failed to save bank details', 'error');
  }
}

// -------------------------------------------------------------
// ONLINE IFSC LOOKUP & AUTO-SELECT BANK AND BRANCH
// -------------------------------------------------------------
let ifscLookupTimeout = null;

function handleIfscAutoFetch(rawVal) {
  const code = (rawVal || '').trim().toUpperCase();
  const inputEl = document.getElementById('bank-ifsc');
  if (inputEl && inputEl.value !== code) inputEl.value = code;

  const statusPill = document.getElementById('ifsc-status-pill');
  const infoBox = document.getElementById('ifsc-info-box');

  if (ifscLookupTimeout) clearTimeout(ifscLookupTimeout);

  if (code.length < 11) {
    if (statusPill) statusPill.innerHTML = `<span class="text-slate-400 font-normal">${code.length}/11 chars</span>`;
    if (infoBox) infoBox.classList.add('hidden');
    return;
  }

  if (statusPill) statusPill.innerHTML = `<span class="text-teal-600 font-semibold"><i class="fas fa-spinner fa-spin mr-1"></i>Checking online...</span>`;
  ifscLookupTimeout = setTimeout(() => {
    executeIfscLookup(code);
  }, 350);
}

function fetchIfscManual() {
  const inputEl = document.getElementById('bank-ifsc');
  const code = inputEl ? inputEl.value.trim().toUpperCase() : '';
  if (!code) {
    showToast('Please enter an IFSC code.', 'info');
    return;
  }
  executeIfscLookup(code);
}

async function executeIfscLookup(code) {
  const spinner = document.getElementById('ifsc-loading-spinner');
  const statusPill = document.getElementById('ifsc-status-pill');
  const infoBox = document.getElementById('ifsc-info-box');
  const bankNameInput = document.getElementById('bank-name');
  const branchNameInput = document.getElementById('bank-branch');

  if (spinner) spinner.classList.remove('hidden');
  if (statusPill) statusPill.innerHTML = `<span class="text-teal-600 font-semibold"><i class="fas fa-spinner fa-spin mr-1"></i>Fetching details...</span>`;

  try {
    let data = null;

    // 1. Try local backend proxy first
    try {
      const res = await fetch(`/api/employees/lookup-ifsc/${encodeURIComponent(code)}`);
      if (res.ok) {
        data = await res.json();
      }
    } catch (e) {
      // Fallback to direct Razorpay API if proxy has network glitch
    }

    // 2. Direct browser fallback
    if (!data) {
      const directRes = await fetch(`https://ifsc.razorpay.com/${encodeURIComponent(code)}`);
      if (directRes.ok) {
        const raw = await directRes.json();
        data = {
          success: true,
          bank_name: raw.BANK,
          branch_name: raw.BRANCH,
          city: raw.CITY,
          district: raw.DISTRICT,
          state: raw.STATE,
          address: raw.ADDRESS,
          upi: raw.UPI,
          neft: raw.NEFT,
          rtgs: raw.RTGS,
          imps: raw.IMPS
        };
      }
    }

    if (data && data.bank_name) {
      // Auto-populate Bank Name and Branch Name
      if (bankNameInput) {
        bankNameInput.value = data.bank_name;
        bankNameInput.classList.add('ring-2', 'ring-teal-400');
        setTimeout(() => bankNameInput.classList.remove('ring-2', 'ring-teal-400'), 1500);
      }
      if (branchNameInput) {
        branchNameInput.value = data.branch_name;
        branchNameInput.classList.add('ring-2', 'ring-teal-400');
        setTimeout(() => branchNameInput.classList.remove('ring-2', 'ring-teal-400'), 1500);
      }

      if (statusPill) {
        statusPill.innerHTML = `<span class="text-emerald-700 font-bold flex items-center gap-1"><i class="fas fa-circle-check"></i> Verified Bank</span>`;
      }

      if (infoBox) {
        infoBox.classList.remove('hidden');
        infoBox.innerHTML = `
          <div class="flex items-start justify-between">
            <div>
              <div class="font-bold text-slate-800 text-xs">${data.bank_name} – ${data.branch_name}</div>
              <div class="text-slate-500 text-[10px] mt-0.5">${data.address || (data.city + ', ' + data.state)}</div>
            </div>
            <div class="flex items-center gap-1 text-[9px] font-bold text-emerald-700">
              ${data.upi ? '<span class="bg-emerald-100 px-1 py-0.5 rounded">UPI</span>' : ''}
              ${data.neft ? '<span class="bg-blue-100 text-blue-800 px-1 py-0.5 rounded">NEFT</span>' : ''}
              ${data.rtgs ? '<span class="bg-purple-100 text-purple-800 px-1 py-0.5 rounded">RTGS</span>' : ''}
              ${data.imps ? '<span class="bg-amber-100 text-amber-800 px-1 py-0.5 rounded">IMPS</span>' : ''}
            </div>
          </div>
        `;
      }
      showToast(`Verified: ${data.bank_name} (${data.branch_name})`, 'success');
    } else {
      if (statusPill) {
        statusPill.innerHTML = `<span class="text-rose-600 font-semibold flex items-center gap-1"><i class="fas fa-circle-xmark"></i> Invalid IFSC</span>`;
      }
      if (infoBox) {
        infoBox.classList.add('hidden');
      }
      showToast('IFSC Code not found. Please verify the code.', 'error');
    }
  } catch (err) {
    if (statusPill) {
      statusPill.innerHTML = `<span class="text-amber-600 font-semibold"><i class="fas fa-triangle-exclamation"></i> Lookup error</span>`;
    }
  } finally {
    if (spinner) spinner.classList.add('hidden');
  }
}

// Add Qualification
async function addEmployeeQualification(e, empId) {
  e.preventDefault();
  const payload = {
    qualification_type: document.getElementById('qual-type').value,
    degree_name: document.getElementById('qual-degree').value,
    institution: document.getElementById('qual-inst').value,
    passing_year: parseInt(document.getElementById('qual-year').value) || null,
    previous_company: document.getElementById('qual-prev-comp').value,
    prior_experience_years: parseFloat(document.getElementById('qual-exp-yrs').value) || 0.0
  };

  try {
    const res = await fetch(`/api/employees/${empId}/qualifications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Qualification record added!', 'success');
      viewEmployeeProfile(empId);
    }
  } catch (err) {
    showToast('Failed to add qualification', 'error');
  }
}

async function deleteQualification(qId, empId) {
  if (!confirm('Are you sure you want to delete this qualification record?')) return;
  try {
    await fetch(`/api/employees/qualifications/${qId}`, { method: 'DELETE' });
    showToast('Qualification deleted', 'info');
    viewEmployeeProfile(empId);
  } catch (err) {
    showToast('Error deleting record', 'error');
  }
}

// Calculate Auto Breakdown
function calculateSalaryComponents() {
  const gross = parseFloat(document.getElementById('sal-gross').value) || 0;
  document.getElementById('sal-basic').value = Math.round(gross * 0.50);
  document.getElementById('sal-hra').value = Math.round(gross * 0.20);
  document.getElementById('sal-conveyance').value = Math.round(gross * 0.10);
  document.getElementById('sal-special').value = Math.round(gross * 0.20);
}

// Save Salary Structure
async function saveEmployeeSalary(e, empId) {
  e.preventDefault();
  const payload = {
    wage_type: document.getElementById('sal-wage-type').value,
    monthly_gross: parseFloat(document.getElementById('sal-gross').value) || 0,
    daily_rate: parseFloat(document.getElementById('sal-daily-rate').value) || 0,
    basic_pay: parseFloat(document.getElementById('sal-basic').value) || 0,
    hra: parseFloat(document.getElementById('sal-hra').value) || 0,
    conveyance: parseFloat(document.getElementById('sal-conveyance').value) || 0,
    special_allowance: parseFloat(document.getElementById('sal-special').value) || 0,
    pf_applicable: document.getElementById('sal-pf').checked,
    esic_applicable: document.getElementById('sal-esic').checked,
    pt_applicable: document.getElementById('sal-pt').checked
  };

  try {
    const res = await fetch(`/api/employees/${empId}/salary`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Salary structure updated successfully!', 'success');
    }
  } catch (err) {
    showToast('Failed to save salary structure', 'error');
  }
}

// 5. DAILY ATTENDANCE
function setAttendanceToday() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('attendance-date-picker').value = today;
  loadDailyAttendance();
}

async function loadDailyAttendance() {
  const picker = document.getElementById('attendance-date-picker');
  if (!picker.value) {
    picker.value = new Date().toISOString().split('T')[0];
  }
  const dateStr = picker.value;
  const tbody = document.getElementById('attendance-table-body');
  tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-400">Loading daily attendance for ' + dateStr + '...</td></tr>';

  try {
    const res = await fetch(`/api/attendance/daily?attendance_date=${dateStr}`);
    const data = await res.json();

    tbody.innerHTML = '';
    if (data.attendance.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-400">No attendance records found for this date.</td></tr>';
      return;
    }

    data.attendance.forEach(a => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition';

      const statusBadge = a.status === 'PRESENT' 
        ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">PRESENT</span>'
        : (a.status === 'HALF_DAY'
          ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800">HALF DAY</span>'
          : '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">ABSENT</span>');

      tr.innerHTML = `
        <td class="py-2.5 px-4">
          <div class="font-bold text-slate-800">${a.display_name}</div>
          <div class="text-[10px] font-mono text-slate-400">${a.employee_code} (Bio ID: ${a.biometric_id || '-'})</div>
        </td>
        <td class="py-2.5 px-4 text-slate-600">${a.shift_name || 'General (09:00 - 18:00)'}</td>
        <td class="py-2.5 px-4 font-mono font-bold text-slate-700">${a.punch_in_time}</td>
        <td class="py-2.5 px-4 font-mono font-bold text-slate-700">${a.punch_out_time}</td>
        <td class="py-2.5 px-4 text-center font-semibold text-slate-800">${a.work_hours} hrs</td>
        <td class="py-2.5 px-4 text-center font-medium ${a.late_minutes > 0 ? 'text-amber-600 font-bold' : 'text-slate-400'}">${a.late_minutes}</td>
        <td class="py-2.5 px-4 text-center font-medium ${a.overtime_hours > 0 ? 'text-teal-600 font-bold' : 'text-slate-400'}">${a.overtime_hours}</td>
        <td class="py-2.5 px-4 text-center">${statusBadge}</td>
        <td class="py-2.5 px-4 text-right">
          <button onclick="openManualPunchModal('${a.employee_id}', '${a.display_name}', '${dateStr}')" class="text-teal-600 hover:text-teal-800 p-1 text-xs">
            <i class="fas fa-edit mr-1"></i> Adjust
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-rose-500">Failed to load attendance.</td></tr>';
  }
}

function exportDailyAttendanceCSV() {
  const dateStr = document.getElementById('attendance-date-picker').value || '2026-10-22';
  window.open(`/api/attendance/daily?attendance_date=${dateStr}`, '_blank');
}

// 6. MONTHLY TIMESHEET
async function loadMonthlyTimesheet() {
  const month = parseInt(document.getElementById('timesheet-month').value);
  const year = parseInt(document.getElementById('timesheet-year').value);
  const container = document.getElementById('timesheet-container');
  container.innerHTML = '<div class="text-center py-8 text-slate-400"><i class="fas fa-spinner fa-spin mr-2"></i>Loading monthly attendance matrix...</div>';

  try {
    const res = await fetch(`/api/attendance/monthly?month=${month}&year=${year}`);
    const data = await res.json();

    const today = new Date();
    const isCurrentMonth = (today.getFullYear() === year && (today.getMonth() + 1) === month);
    const todayDay = isCurrentMonth ? today.getDate() : (today > new Date(year, month - 1, data.days_in_month) ? data.days_in_month : 0);

    const holidayDaysMap = {};
    if (data.holidays) {
      data.holidays.forEach(h => {
        holidayDaysMap[h.day] = h.name;
      });
    }

    let html = `
      <table class="w-full text-center text-[10px] border-collapse">
        <thead>
          <tr class="bg-slate-100 text-slate-700 font-bold">
            <th class="py-2.5 px-3 text-left sticky left-0 bg-slate-100 z-10 w-48 shadow-sm">Staff Name & Code</th>
    `;
    for (let d = 1; d <= data.days_in_month; d++) {
      const dayDate = new Date(year, month - 1, d);
      const isSunday = (dayDate.getDay() === 0);
      const isHoliday = !!holidayDaysMap[d];
      const isToday = (isCurrentMonth && d === todayDay);
      
      let thClass = isHoliday 
        ? 'bg-amber-100 text-amber-800 font-extrabold border-amber-300' 
        : (isSunday ? 'bg-slate-200/60 text-slate-500' : (isToday ? 'bg-teal-100 text-teal-800 font-extrabold' : ''));

      html += `<th title="${holidayDaysMap[d] || (isSunday ? 'Sunday' : '')}" class="py-2 px-1 w-6 border-l border-slate-200 ${thClass}">${d}</th>`;
    }
    html += `
            <th class="py-2.5 px-2 border-l border-slate-300 text-emerald-700 bg-emerald-50">Present</th>
            <th class="py-2.5 px-2 border-l border-slate-200 text-rose-700 bg-rose-50">Absent</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
    `;

    data.employees.forEach(emp => {
      let presentCount = 0;
      let absentCount = 0;

      let rowHtml = `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-2 px-3 text-left font-semibold text-slate-800 sticky left-0 bg-white shadow-sm truncate max-w-[190px]">
            <div>${emp.display_name}</div>
            <div class="text-[9px] font-mono text-slate-400 font-normal">${emp.employee_code}</div>
          </td>
      `;

      for (let d = 1; d <= data.days_in_month; d++) {
        const dayDate = new Date(year, month - 1, d);
        const isSunday = (dayDate.getDay() === 0);
        const isHoliday = !!holidayDaysMap[d];
        const punchedVal = emp.days[d];

        let badge = '-';
        let badgeClass = 'text-slate-300';

        if (punchedVal === 'P') {
          badge = 'P';
          badgeClass = 'bg-emerald-100 text-emerald-800 font-bold';
          presentCount += 1;
        } else if (punchedVal === 'HD') {
          badge = 'HD';
          badgeClass = 'bg-purple-100 text-purple-800 font-bold';
          presentCount += 0.5;
          absentCount += 0.5;
        } else if (d <= todayDay) {
          if (isHoliday) {
            badge = 'H';
            badgeClass = 'bg-amber-100 text-amber-800 font-bold border border-amber-300';
            presentCount += 1; // Paid holiday
          } else if (isSunday) {
            badge = 'WO';
            badgeClass = 'bg-slate-100 text-slate-500 font-medium';
          } else {
            badge = 'A';
            badgeClass = 'bg-rose-100 text-rose-800 font-medium';
            absentCount += 1;
          }
        } else {
          // Future day
          badge = isHoliday ? 'H' : (isSunday ? 'WO' : '-');
          badgeClass = isHoliday ? 'bg-amber-50 text-amber-700' : 'text-slate-300';
        }

        rowHtml += `<td class="py-1.5 px-1 border-l border-slate-100 ${badgeClass}">${badge}</td>`;
      }

      rowHtml += `
          <td class="py-1.5 px-2 border-l border-slate-300 font-bold text-emerald-700 bg-emerald-50/50">${presentCount}</td>
          <td class="py-1.5 px-2 border-l border-slate-200 font-bold text-rose-700 bg-rose-50/50">${absentCount}</td>
        </tr>
      `;

      html += rowHtml;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = '<div class="text-center py-8 text-rose-500">Failed to load monthly timesheet.</div>';
  }
}

function downloadTimesheetExcel() {
  const month = document.getElementById('timesheet-month').value;
  const year = document.getElementById('timesheet-year').value;
  window.open(`/api/attendance/monthly/export-excel?month=${month}&year=${year}`, '_blank');
}

function downloadTimesheetPDF() {
  const month = document.getElementById('timesheet-month').value;
  const year = document.getElementById('timesheet-year').value;
  window.open(`/api/attendance/monthly/export-pdf?month=${month}&year=${year}`, '_blank');
}

function downloadHolidaysExcel() {
  window.open('/api/leaves/holidays/export-excel?year=2026', '_blank');
}

function downloadHolidaysPDF() {
  window.open('/api/leaves/holidays/export-pdf?year=2026', '_blank');
}

// ======================================================================
// 6B. MONTHLY DETAIL REPORT (PUNCH IN / OUT & ABSENT PERCENTAGE)
// ======================================================================

let monthlyReportData = null;
let currentReportSubView = 'threerow'; // 'threerow', 'summary' or 'punches'

async function loadMonthlyDetailReport() {
  const monthEl = document.getElementById('report-month');
  const yearEl = document.getElementById('report-year');
  if (!monthEl || !yearEl) return;

  const month = monthEl.value;
  const year = yearEl.value;
  const deptEl = document.getElementById('report-dept');
  const dept = deptEl ? deptEl.value : 'ALL';
  const empSelect = document.getElementById('report-employee');
  const empId = empSelect ? empSelect.value : 'ALL';

  const tbody = document.getElementById('report-summary-tbody');
  const threeRowTbody = document.getElementById('report-threerow-tbody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="14" class="text-center py-8 text-slate-400"><i class="fas fa-spinner fa-spin mr-2"></i>Loading monthly attendance detail & percentages...</td></tr>';
  }
  if (threeRowTbody) {
    threeRowTbody.innerHTML = '<tr><td colspan="45" class="text-center py-12 text-slate-400"><i class="fas fa-spinner fa-spin text-teal-600 mr-2 text-base"></i><span class="font-semibold">Loading 3-Row Attendance Register for all employees...</span></td></tr>';
  }

  try {
    let url = `/api/attendance/monthly-detail?month=${month}&year=${year}`;
    if (dept && dept !== 'ALL') url += `&department=${encodeURIComponent(dept)}`;
    if (empId && empId !== 'ALL') url += `&employee_id=${encodeURIComponent(empId)}`;

    const res = await fetch(url);
    monthlyReportData = await res.json();

    populateReportDepartments(monthlyReportData.employees);
    populateReportEmployeeDropdown(monthlyReportData.employees);
    renderReportKPIs(monthlyReportData);

    if (currentReportSubView === 'threerow') {
      renderReportThreeRowTable(monthlyReportData);
    } else if (currentReportSubView === 'summary') {
      renderReportSummaryTable(monthlyReportData.employees);
    } else {
      const selectedId = (empId && empId !== 'ALL') ? empId : (monthlyReportData.employees[0] ? monthlyReportData.employees[0].employee_id : null);
      renderReportEmployeePunches(selectedId);
    }
  } catch (err) {
    console.error('Failed to load monthly detail report:', err);
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="14" class="text-center py-8 text-rose-500"><i class="fas fa-exclamation-triangle mr-2"></i>Failed to load monthly attendance detail.</td></tr>';
    }
    if (threeRowTbody) {
      threeRowTbody.innerHTML = '<tr><td colspan="45" class="text-center py-8 text-rose-500"><i class="fas fa-exclamation-triangle mr-2"></i>Failed to load 3-Row Attendance Register.</td></tr>';
    }
  }
}

function populateReportDepartments(employees) {
  const deptSelect = document.getElementById('report-dept');
  if (!deptSelect) return;
  const currentVal = deptSelect.value || 'ALL';

  const depts = new Set();
  employees.forEach(e => {
    if (e.department) depts.add(e.department);
  });

  let optionsHtml = '<option value="ALL">All Departments</option>';
  Array.from(depts).sort().forEach(d => {
    optionsHtml += `<option value="${d}" ${d === currentVal ? 'selected' : ''}>${d}</option>`;
  });
  deptSelect.innerHTML = optionsHtml;
}

function populateReportEmployeeDropdown(employees) {
  const empSelect = document.getElementById('report-employee');
  if (!empSelect) return;
  const currentVal = empSelect.value || 'ALL';

  let optionsHtml = '<option value="ALL">-- All Staff Summary & Percentage View --</option>';
  employees.forEach(e => {
    const isSel = (e.employee_id === currentVal);
    optionsHtml += `<option value="${e.employee_id}" ${isSel ? 'selected' : ''}>[${e.employee_code}] ${e.display_name} (Bio: ${e.biometric_id || '-'})</option>`;
  });
  empSelect.innerHTML = optionsHtml;
}

function renderReportKPIs(data) {
  const container = document.getElementById('report-kpi-container');
  if (!container) return;

  const s = data.summary_stats;
  container.innerHTML = `
    <div class="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex flex-col justify-between">
      <div class="flex items-center justify-between text-slate-500">
        <span class="text-xs font-semibold uppercase tracking-wider">Total Staff</span>
        <div class="w-7 h-7 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center text-xs">
          <i class="fas fa-users"></i>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-2xl font-bold text-slate-900">${s.total_employees}</div>
        <span class="text-[11px] text-slate-400">Enrolled on Device</span>
      </div>
    </div>

    <div class="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex flex-col justify-between">
      <div class="flex items-center justify-between text-slate-500">
        <span class="text-xs font-semibold uppercase tracking-wider">Working Days</span>
        <div class="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center text-xs">
          <i class="fas fa-calendar-day"></i>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-2xl font-bold text-slate-900">${data.working_days} <span class="text-xs font-normal text-slate-500">/ ${data.days_in_month}d</span></div>
        <span class="text-[11px] text-slate-400">${data.total_sundays} Sun • ${data.total_holidays} Holidays</span>
      </div>
    </div>

    <div class="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex flex-col justify-between">
      <div class="flex items-center justify-between text-slate-500">
        <span class="text-xs font-semibold uppercase tracking-wider">Present %</span>
        <div class="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center text-xs">
          <i class="fas fa-user-check"></i>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-2xl font-bold text-emerald-700">${s.avg_present_percent}%</div>
        <div class="w-full bg-slate-100 rounded-full h-1.5 mt-1 overflow-hidden">
          <div class="bg-emerald-500 h-1.5 rounded-full" style="width: ${Math.min(100, s.avg_present_percent)}%"></div>
        </div>
      </div>
    </div>

    <div class="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex flex-col justify-between">
      <div class="flex items-center justify-between text-slate-500">
        <span class="text-xs font-semibold uppercase tracking-wider">Absent %</span>
        <div class="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center text-xs">
          <i class="fas fa-user-times"></i>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-2xl font-bold text-rose-700">${s.avg_absent_percent}%</div>
        <div class="w-full bg-slate-100 rounded-full h-1.5 mt-1 overflow-hidden">
          <div class="bg-rose-500 h-1.5 rounded-full" style="width: ${Math.min(100, s.avg_absent_percent)}%"></div>
        </div>
      </div>
    </div>

    <div class="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex flex-col justify-between sm:col-span-2 lg:col-span-1">
      <div class="flex items-center justify-between text-slate-500">
        <span class="text-xs font-semibold uppercase tracking-wider">Total Man-Hours</span>
        <div class="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center text-xs">
          <i class="fas fa-business-time"></i>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-2xl font-bold text-slate-900">${Math.round(s.total_work_hours)} <span class="text-xs font-normal text-slate-500">hrs</span></div>
        <span class="text-[11px] text-amber-600 font-medium">+${Math.round(s.total_ot_hours)} hrs OT</span>
      </div>
    </div>
  `;
}

function renderReportSummaryTable(employees) {
  const tbody = document.getElementById('report-summary-tbody');
  if (!tbody) return;

  if (!employees || employees.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" class="text-center py-8 text-slate-400">No employee attendance records match the selected filters.</td></tr>';
    return;
  }

  let html = '';
  employees.forEach((emp, idx) => {
    // Style percentages
    const presClass = emp.present_percent >= 80 ? 'bg-emerald-100 text-emerald-800' : (emp.present_percent >= 50 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600');
    const absClass = emp.absent_percent > 30 ? 'bg-rose-100 text-rose-800 font-bold' : (emp.absent_percent > 15 ? 'bg-amber-100 text-amber-800' : 'bg-emerald-50 text-emerald-700');

    html += `
      <tr class="hover:bg-slate-50/80 transition rep-summary-row" data-search="${(emp.display_name + ' ' + emp.employee_code + ' ' + (emp.biometric_id || '') + ' ' + emp.department).toLowerCase()}">
        <td class="py-2.5 px-3 text-center text-slate-400 font-mono">${idx + 1}</td>
        <td class="py-2.5 px-3 text-center font-mono font-bold text-teal-700">${emp.biometric_id || '-'}</td>
        <td class="py-2.5 px-3 font-mono text-slate-600 font-medium">${emp.employee_code}</td>
        <td class="py-2.5 px-4 font-semibold text-slate-900">
          <button onclick="showEmployeeDailyDetail('${emp.employee_id}')" class="hover:text-teal-600 text-left">
            ${emp.display_name}
          </button>
        </td>
        <td class="py-2.5 px-3 text-slate-500">${emp.department || 'Operations'}</td>
        <td class="py-2.5 px-3 text-center font-medium text-slate-600">${emp.working_days}</td>
        <td class="py-2.5 px-3 text-center font-bold text-emerald-700">${emp.present_days}</td>
        <td class="py-2.5 px-3 text-center font-bold text-rose-700">${emp.absent_days}</td>
        <td class="py-2.5 px-3 text-center text-purple-700 font-medium">${emp.half_days}</td>
        <td class="py-2.5 px-4 text-center bg-emerald-50/30">
          <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${presClass}">
            ${emp.present_percent}%
          </span>
        </td>
        <td class="py-2.5 px-4 text-center bg-rose-50/30">
          <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${absClass}">
            ${emp.absent_percent}%
          </span>
        </td>
        <td class="py-2.5 px-3 text-right font-medium text-slate-700">${emp.total_work_hours}h</td>
        <td class="py-2.5 px-3 text-right font-semibold text-amber-600">${emp.total_ot_hours > 0 ? emp.total_ot_hours + 'h' : '-'}</td>
        <td class="py-2.5 px-4 text-center">
          <button onclick="showEmployeeDailyDetail('${emp.employee_id}')" class="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-teal-50 hover:bg-teal-600 text-teal-700 hover:text-white text-[11px] font-semibold border border-teal-200 hover:border-transparent transition shadow-xs">
            <i class="fas fa-clock"></i>
            <span>Punch Times</span>
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function renderReportEmployeePunches(empId) {
  if (!monthlyReportData || !monthlyReportData.employees) return;
  const emp = monthlyReportData.employees.find(e => e.employee_id === empId) || monthlyReportData.employees[0];
  if (!emp) return;

  // 1. Render Profile Card
  const profCard = document.getElementById('report-emp-profile-card');
  if (profCard) {
    profCard.innerHTML = `
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div class="flex items-center space-x-4">
          <div class="w-14 h-14 rounded-xl bg-teal-600/30 border border-teal-400/40 flex items-center justify-center text-teal-300 font-mono text-xl font-bold shadow-inner">
            ${emp.biometric_id || 'ID'}
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <h2 class="text-lg font-bold text-white tracking-tight">${emp.display_name}</h2>
              <span class="px-2 py-0.5 rounded bg-teal-500/20 text-teal-300 text-xs font-mono border border-teal-500/40">${emp.employee_code}</span>
            </div>
            <p class="text-xs text-slate-300 mt-0.5">
              ${emp.designation || 'Staff'} • ${emp.department || 'Operations'} • Shift: <span class="font-mono text-teal-300">${emp.shift_name} (${emp.shift_start ? emp.shift_start.slice(0, 5) : '09:00'} - ${emp.shift_end ? emp.shift_end.slice(0, 5) : '18:00'})</span>
            </p>
          </div>
        </div>

        <!-- Quick Employee Action Buttons -->
        <div class="flex items-center space-x-2">
          <button onclick="switchReportSubView('summary')" class="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-700 transition">
            <i class="fas fa-arrow-left"></i>
            <span>Back to All Staff</span>
          </button>
          <button onclick="downloadReportExcel('${emp.employee_id}')" class="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold shadow transition">
            <i class="fas fa-file-excel"></i>
            <span>Export Card (.xlsx)</span>
          </button>
          <button onclick="downloadReportPDF('${emp.employee_id}')" class="flex items-center space-x-1.5 bg-rose-600 hover:bg-rose-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold shadow transition">
            <i class="fas fa-file-pdf"></i>
            <span>Export Card (.pdf)</span>
          </button>
        </div>
      </div>

      <!-- Stat Badges Row -->
      <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mt-5 pt-4 border-t border-slate-800/80 text-center">
        <div class="bg-slate-800/60 p-2.5 rounded-lg border border-slate-700/60">
          <div class="text-[10px] text-slate-400 uppercase font-semibold">Working Days</div>
          <div class="text-lg font-bold text-white mt-0.5">${emp.working_days}</div>
        </div>
        <div class="bg-emerald-950/40 p-2.5 rounded-lg border border-emerald-800/40">
          <div class="text-[10px] text-emerald-400 uppercase font-semibold">Present Days</div>
          <div class="text-lg font-bold text-emerald-300 mt-0.5">${emp.present_days}</div>
        </div>
        <div class="bg-rose-950/40 p-2.5 rounded-lg border border-rose-800/40">
          <div class="text-[10px] text-rose-400 uppercase font-semibold">Absent Days</div>
          <div class="text-lg font-bold text-rose-300 mt-0.5">${emp.absent_days}</div>
        </div>
        <div class="bg-purple-950/40 p-2.5 rounded-lg border border-purple-800/40">
          <div class="text-[10px] text-purple-400 uppercase font-semibold">Half Days</div>
          <div class="text-lg font-bold text-purple-300 mt-0.5">${emp.half_days}</div>
        </div>
        <div class="bg-teal-900/40 p-2.5 rounded-lg border border-teal-600/40">
          <div class="text-[10px] text-teal-300 uppercase font-bold">Present %</div>
          <div class="text-lg font-extrabold text-teal-200 mt-0.5">${emp.present_percent}%</div>
        </div>
        <div class="bg-rose-900/40 p-2.5 rounded-lg border border-rose-600/40">
          <div class="text-[10px] text-rose-300 uppercase font-bold">Absent %</div>
          <div class="text-lg font-extrabold text-rose-200 mt-0.5">${emp.absent_percent}%</div>
        </div>
        <div class="bg-slate-800/60 p-2.5 rounded-lg border border-slate-700/60 col-span-2 sm:col-span-1">
          <div class="text-[10px] text-amber-400 uppercase font-semibold">Total Hours</div>
          <div class="text-lg font-bold text-amber-300 mt-0.5">${emp.total_work_hours}h <span class="text-xs text-slate-400">(+${emp.total_ot_hours}h OT)</span></div>
        </div>
      </div>
    `;
  }

  // 2. Render Daily Punches Table
  const tbody = document.getElementById('report-punches-tbody');
  if (!tbody) return;

  let html = '';
  emp.daily_records.forEach(d => {
    // Badge styles
    let statusClass = 'bg-slate-100 text-slate-600';
    if (d.status === 'PRESENT') statusClass = 'bg-emerald-100 text-emerald-800 font-bold';
    else if (d.status === 'LATE') statusClass = 'bg-amber-100 text-amber-800 font-bold';
    else if (d.status === 'HALF_DAY') statusClass = 'bg-purple-100 text-purple-800 font-bold';
    else if (d.status === 'ABSENT') statusClass = 'bg-rose-100 text-rose-800 font-bold';
    else if (d.status === 'SUNDAY') statusClass = 'bg-slate-200/80 text-slate-600 font-medium';
    else if (d.status === 'HOLIDAY') statusClass = 'bg-amber-200 text-amber-900 font-bold';

    const inBadge = d.punch_in !== '--:--'
      ? `<span class="inline-flex items-center space-x-1.5 px-3 py-1 rounded-md font-mono font-bold text-xs bg-emerald-100 text-emerald-900 border border-emerald-300/80 shadow-xs"><i class="fas fa-sign-in-alt text-emerald-600"></i><span>${d.punch_in}</span></span>`
      : `<span class="text-slate-300 font-mono font-medium">--:--</span>`;

    const outBadge = d.punch_out !== '--:--'
      ? `<span class="inline-flex items-center space-x-1.5 px-3 py-1 rounded-md font-mono font-bold text-xs bg-blue-100 text-blue-900 border border-blue-300/80 shadow-xs"><i class="fas fa-sign-out-alt text-blue-600"></i><span>${d.punch_out}</span></span>`
      : `<span class="text-slate-300 font-mono font-medium">--:--</span>`;

    const isWeekendOrHol = d.is_sunday || d.is_holiday;
    const rowBg = isWeekendOrHol ? 'bg-slate-50/60' : 'hover:bg-slate-50/80';

    html += `
      <tr class="${rowBg} transition">
        <td class="py-2 px-3 text-center font-bold text-slate-500">${d.day}</td>
        <td class="py-2 px-3 font-mono text-slate-700">${d.date}</td>
        <td class="py-2 px-3 font-semibold ${d.is_sunday ? 'text-slate-400' : 'text-slate-700'}">${d.day_name}</td>
        <td class="py-2 px-3 text-slate-500 font-mono text-[10px]">${d.shift}</td>
        <td class="py-2 px-4 text-center bg-emerald-50/30 border-x border-emerald-100">${inBadge}</td>
        <td class="py-2 px-4 text-center bg-blue-50/30 border-r border-blue-100">${outBadge}</td>
        <td class="py-2 px-3 text-center font-semibold text-slate-800">${d.work_time_str}</td>
        <td class="py-2 px-3 text-center font-medium ${d.overtime_minutes > 0 ? 'text-amber-700 font-bold' : 'text-slate-400'}">${d.ot_time_str}</td>
        <td class="py-2 px-3 text-center ${d.late_minutes > 0 ? 'text-rose-600 font-bold' : 'text-slate-400'}">${d.late_minutes > 0 ? d.late_minutes + ' min' : '-'}</td>
        <td class="py-2 px-4 text-center">
          <span class="inline-block px-2.5 py-0.5 rounded text-[10px] ${statusClass}">
            ${d.status}${d.holiday_name ? ': ' + d.holiday_name : ''}
          </span>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function showEmployeeDailyDetail(empId) {
  const empSelect = document.getElementById('report-employee');
  if (empSelect) empSelect.value = empId;

  switchReportSubView('punches');
  renderReportEmployeePunches(empId);

  const container = document.getElementById('tab-monthly-report');
  if (container) container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function switchReportSubView(viewMode) {
  currentReportSubView = viewMode;
  const btnThreeRow = document.getElementById('btn-rep-threerow');
  const btnSummary = document.getElementById('btn-rep-summary');
  const btnPunches = document.getElementById('btn-rep-punches');
  
  const threeRowView = document.getElementById('report-threerow-view');
  const summaryView = document.getElementById('report-summary-view');
  const punchesView = document.getElementById('report-punches-view');
  const searchBar = document.getElementById('report-search-bar');

  // Reset button styles
  [btnThreeRow, btnSummary, btnPunches].forEach(b => {
    if (b) {
      b.classList.remove('bg-white', 'text-teal-800', 'shadow-sm', 'font-bold');
      b.classList.add('text-slate-600', 'font-medium');
    }
  });

  if (viewMode === 'threerow') {
    if (btnThreeRow) {
      btnThreeRow.classList.add('bg-white', 'text-teal-800', 'shadow-sm', 'font-bold');
      btnThreeRow.classList.remove('text-slate-600', 'font-medium');
    }
    if (threeRowView) threeRowView.classList.remove('hidden');
    if (summaryView) summaryView.classList.add('hidden');
    if (punchesView) punchesView.classList.add('hidden');
    if (searchBar) searchBar.classList.remove('hidden');

    if (monthlyReportData) {
      renderReportThreeRowTable(monthlyReportData);
    }
  } else if (viewMode === 'summary') {
    if (btnSummary) {
      btnSummary.classList.add('bg-white', 'text-teal-800', 'shadow-sm', 'font-bold');
      btnSummary.classList.remove('text-slate-600', 'font-medium');
    }
    if (threeRowView) threeRowView.classList.add('hidden');
    if (summaryView) summaryView.classList.remove('hidden');
    if (punchesView) punchesView.classList.add('hidden');
    if (searchBar) searchBar.classList.remove('hidden');

    if (monthlyReportData && monthlyReportData.employees) {
      renderReportSummaryTable(monthlyReportData.employees);
    }
  } else {
    if (btnPunches) {
      btnPunches.classList.add('bg-white', 'text-teal-800', 'shadow-sm', 'font-bold');
      btnPunches.classList.remove('text-slate-600', 'font-medium');
    }
    if (threeRowView) threeRowView.classList.add('hidden');
    if (summaryView) summaryView.classList.add('hidden');
    if (punchesView) punchesView.classList.remove('hidden');
    if (searchBar) searchBar.classList.add('hidden');

    const empSelect = document.getElementById('report-employee');
    const selectedId = (empSelect && empSelect.value !== 'ALL') ? empSelect.value : (monthlyReportData && monthlyReportData.employees[0] ? monthlyReportData.employees[0].employee_id : null);
    if (selectedId) {
      renderReportEmployeePunches(selectedId);
    }
  }
}

function renderReportThreeRowTable(data) {
  const thead = document.getElementById('report-threerow-thead');
  const tbody = document.getElementById('report-threerow-tbody');
  if (!thead || !tbody || !data || !data.employees) return;

  const daysInMonth = data.days_in_month;
  const holidaysMap = {};
  if (data.holidays) {
    data.holidays.forEach(h => {
      const parts = h.date.split('-');
      const d = parseInt(parts[2]);
      holidaysMap[d] = h.name;
    });
  }

  const today = new Date();
  const isCurrentMonth = (today.getFullYear() === data.year && (today.getMonth() + 1) === data.month);
  const todayDay = isCurrentMonth ? today.getDate() : 0;

  // 1. Build Header
  let thHtml = `
    <tr class="bg-slate-100 text-slate-700 font-bold border-b border-slate-300">
      <th class="py-2.5 px-2 text-center sticky left-0 bg-slate-100 z-20 w-10 shadow-xs border-r border-slate-200">#</th>
      <th class="py-2.5 px-3 text-left sticky left-10 bg-slate-100 z-20 w-60 shadow-xs border-r border-slate-300">Staff Details (Name / Code / Dept)</th>
      <th class="py-2.5 px-2 text-center sticky left-70 bg-slate-200 z-20 w-24 shadow-xs border-r border-slate-300">Metric</th>
  `;

  for (let d = 1; d <= daysInMonth; d++) {
    const dObj = new Date(data.year, data.month - 1, d);
    const dayName = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'][dObj.getDay()];
    const isSunday = (dObj.getDay() === 0);
    const isHoliday = !!holidaysMap[d];
    const isToday = (d === todayDay);

    let dayClass = 'bg-slate-50 text-slate-700';
    if (isHoliday) dayClass = 'bg-amber-100 text-amber-900 font-bold';
    else if (isSunday) dayClass = 'bg-slate-200 text-slate-600 font-semibold';
    else if (isToday) dayClass = 'bg-teal-100 text-teal-900 font-extrabold ring-1 ring-teal-400';

    thHtml += `
      <th class="py-1 px-1 min-w-[44px] max-w-[50px] border-r border-slate-200 ${dayClass}" title="Day ${d} (${dayName})${isHoliday ? ' - ' + holidaysMap[d] : ''}">
        <div class="text-[11px] font-bold">${d}</div>
        <div class="text-[9px] uppercase">${dayName}</div>
      </th>
    `;
  }

  thHtml += `
      <th class="py-2 px-2 text-center text-emerald-800 bg-emerald-50 font-bold border-l border-slate-300 min-w-[50px]" title="Total Present Days">P</th>
      <th class="py-2 px-2 text-center text-rose-800 bg-rose-50 font-bold min-w-[50px]" title="Total Absent Days">A</th>
      <th class="py-2 px-2 text-center text-purple-800 bg-purple-50 font-bold min-w-[50px]" title="Total Half Days">HD</th>
      <th class="py-2 px-2 text-center text-emerald-900 bg-emerald-100 font-extrabold min-w-[65px]">P %</th>
      <th class="py-2 px-2 text-center text-rose-900 bg-rose-100 font-extrabold min-w-[65px]">A %</th>
      <th class="py-2 px-2 text-center text-slate-800 bg-slate-100 font-bold min-w-[65px]">Work Hrs</th>
      <th class="py-2 px-2 text-center text-amber-800 bg-amber-50 font-bold min-w-[60px]">OT Hrs</th>
    </tr>
  `;
  thead.innerHTML = thHtml;

  // 2. Build 3-Row Body per Employee
  let bodyHtml = '';
  data.employees.forEach((emp, idx) => {
    const bgRow = (idx % 2 === 0) ? 'bg-white' : 'bg-slate-50/70';
    const stickyBg = (idx % 2 === 0) ? 'bg-white' : 'bg-slate-50';
    const searchKey = `${emp.display_name} ${emp.employee_code} ${emp.biometric_id || ''} ${emp.department}`.toLowerCase();

    // Map daily records by day
    const dayMap = {};
    if (emp.daily_records) {
      emp.daily_records.forEach(r => {
        dayMap[r.day] = r;
      });
    }

    // Row 1: Status (Present / Absent)
    bodyHtml += `
      <tr class="threerow-emp-group border-t-2 border-slate-300 hover:bg-teal-50/30 transition ${bgRow}" data-search="${searchKey}" data-empid="${emp.employee_id}">
        <td rowspan="3" class="py-2 px-2 text-center text-slate-400 font-mono sticky left-0 ${stickyBg} z-10 border-r border-slate-200">${idx + 1}</td>
        <td rowspan="3" class="py-2 px-3 font-semibold text-slate-900 text-left sticky left-10 ${stickyBg} z-10 border-r border-slate-300">
          <div class="flex items-center space-x-1.5">
            <button onclick="showEmployeeDailyDetail('${emp.employee_id}')" class="font-bold text-slate-900 hover:text-teal-600 text-left truncate max-w-[190px]" title="${emp.display_name}">
              ${emp.display_name}
            </button>
            <span class="font-mono text-[10px] text-teal-700 font-bold bg-teal-50 px-1 py-0.5 rounded border border-teal-200">#${emp.biometric_id || '-'}</span>
          </div>
          <div class="text-[10px] text-slate-500 flex items-center space-x-2 mt-0.5">
            <span class="font-mono font-medium text-slate-600">${emp.employee_code}</span>
            <span>•</span>
            <span class="truncate max-w-[120px]">${emp.department || 'Operations'}</span>
          </div>
        </td>
        <td class="py-1 px-1.5 text-center font-bold text-[10px] bg-teal-50 text-teal-800 sticky left-70 ${stickyBg} z-10 border-r border-slate-300">
          <span class="px-2 py-0.5 rounded bg-teal-100 font-extrabold text-teal-900 text-[10px]">Status</span>
        </td>
    `;

    // Status Day cells
    for (let d = 1; d <= daysInMonth; d++) {
      const rec = dayMap[d];
      let cellContent = '<span class="text-slate-300">-</span>';
      if (rec) {
        if (rec.status === 'PRESENT') {
          cellContent = '<span class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[10px]" title="Present">P</span>';
        } else if (rec.status === 'LATE') {
          cellContent = '<span class="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-bold text-[10px]" title="Late Entry">L</span>';
        } else if (rec.status === 'HALF_DAY') {
          cellContent = '<span class="px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-bold text-[10px]" title="Half Day">HD</span>';
        } else if (rec.status === 'ABSENT') {
          cellContent = '<span class="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 font-bold text-[10px]" title="Absent">A</span>';
        } else if (rec.status === 'SUNDAY') {
          cellContent = '<span class="px-1 py-0.5 rounded bg-slate-100 text-slate-500 font-medium text-[9px]" title="Sunday (Week Off)">WO</span>';
        } else if (rec.status === 'HOLIDAY') {
          cellContent = `<span class="px-1 py-0.5 rounded bg-amber-100 text-amber-800 font-bold text-[9px]" title="${rec.holiday_name || 'Holiday'}">H</span>`;
        }
      }
      bodyHtml += `<td class="py-1 px-0.5 border-r border-slate-100">${cellContent}</td>`;
    }

    // Totals columns (rowspan=3)
    const presClass = emp.present_percent >= 80 ? 'text-emerald-800 bg-emerald-100/60' : (emp.present_percent >= 50 ? 'text-amber-800 bg-amber-100/60' : 'text-slate-700 bg-slate-100');
    const absClass = emp.absent_percent > 30 ? 'text-rose-800 bg-rose-100/70' : (emp.absent_percent > 15 ? 'text-amber-800 bg-amber-100/60' : 'text-emerald-800 bg-emerald-50/50');

    bodyHtml += `
        <td rowspan="3" class="py-2 px-2 text-center font-bold text-emerald-700 bg-emerald-50/30 border-l border-slate-200 border-r">${emp.present_days}</td>
        <td rowspan="3" class="py-2 px-2 text-center font-bold text-rose-700 bg-rose-50/30 border-r border-slate-200">${emp.absent_days}</td>
        <td rowspan="3" class="py-2 px-2 text-center font-medium text-purple-700 border-r border-slate-200">${emp.half_days}</td>
        <td rowspan="3" class="py-2 px-2 text-center font-extrabold ${presClass} border-r border-slate-200">${emp.present_percent}%</td>
        <td rowspan="3" class="py-2 px-2 text-center font-extrabold ${absClass} border-r border-slate-200">${emp.absent_percent}%</td>
        <td rowspan="3" class="py-2 px-2 text-center font-medium text-slate-800 border-r border-slate-200">${emp.total_work_hours}h</td>
        <td rowspan="3" class="py-2 px-2 text-center font-semibold text-amber-600">${emp.total_ot_hours > 0 ? emp.total_ot_hours + 'h' : '-'}</td>
      </tr>
    `;

    // Row 2: Punch In
    bodyHtml += `
      <tr class="threerow-emp-group hover:bg-teal-50/30 transition ${bgRow}" data-search="${searchKey}" data-empid="${emp.employee_id}">
        <td class="py-1 px-1.5 text-center font-bold text-[10px] bg-emerald-50 text-emerald-800 sticky left-70 ${stickyBg} z-10 border-r border-slate-300">
          <span class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[10px]">Punch In</span>
        </td>
    `;
    for (let d = 1; d <= daysInMonth; d++) {
      const rec = dayMap[d];
      let inStr = '--:--';
      let inColor = 'text-slate-300';
      if (rec && rec.punch_in && rec.punch_in !== '--:--') {
        inStr = rec.punch_in.slice(0, 5);
        inColor = rec.late_minutes > 0 ? 'text-amber-700 font-bold bg-amber-50 rounded px-0.5' : 'text-emerald-700 font-semibold';
      }
      bodyHtml += `<td class="py-1 px-0.5 border-r border-slate-100 font-mono text-[10px] ${inColor}">${inStr}</td>`;
    }
    bodyHtml += `</tr>`;

    // Row 3: Punch Out
    bodyHtml += `
      <tr class="threerow-emp-group hover:bg-teal-50/30 transition ${bgRow} border-b border-slate-300" data-search="${searchKey}" data-empid="${emp.employee_id}">
        <td class="py-1 px-1.5 text-center font-bold text-[10px] bg-blue-50 text-blue-800 sticky left-70 ${stickyBg} z-10 border-r border-slate-300">
          <span class="px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-bold text-[10px]">Punch Out</span>
        </td>
    `;
    for (let d = 1; d <= daysInMonth; d++) {
      const rec = dayMap[d];
      let outStr = '--:--';
      let outColor = 'text-slate-300';
      if (rec && rec.punch_out && rec.punch_out !== '--:--') {
        outStr = rec.punch_out.slice(0, 5);
        outColor = 'text-blue-700 font-semibold';
      }
      bodyHtml += `<td class="py-1 px-0.5 border-r border-slate-100 font-mono text-[10px] ${outColor}">${outStr}</td>`;
    }
    bodyHtml += `</tr>`;
  });

  tbody.innerHTML = bodyHtml;
  const countBadge = document.getElementById('threerow-count-badge');
  if (countBadge) countBadge.textContent = `${data.employees.length} Staff`;
}

function handleReportFilterChange() {
  loadMonthlyDetailReport();
}

function handleReportStaffChange() {
  const empSelect = document.getElementById('report-employee');
  if (!empSelect) return;
  const selectedVal = empSelect.value;
  if (selectedVal === 'ALL') {
    switchReportSubView('threerow');
  } else {
    switchReportSubView('punches');
    renderReportEmployeePunches(selectedVal);
  }
}

function filterReportTable() {
  const query = (document.getElementById('report-search-input').value || '').trim().toLowerCase();
  
  // Filter summary table rows
  const sumRows = document.querySelectorAll('.rep-summary-row');
  sumRows.forEach(r => {
    const text = r.dataset.search || '';
    r.style.display = (!query || text.includes(query)) ? '' : 'none';
  });

  // Filter 3-row muster groups
  const threeRows = document.querySelectorAll('.threerow-emp-group');
  threeRows.forEach(r => {
    const text = r.dataset.search || '';
    r.style.display = (!query || text.includes(query)) ? '' : 'none';
  });
}

function downloadReportExcel(specificEmpId) {
  const month = document.getElementById('report-month').value;
  const year = document.getElementById('report-year').value;
  const dept = document.getElementById('report-dept') ? document.getElementById('report-dept').value : 'ALL';
  const empSelect = document.getElementById('report-employee');
  const empId = specificEmpId || (empSelect ? empSelect.value : 'ALL');

  let url = `/api/attendance/monthly-detail/export-excel?month=${month}&year=${year}`;
  if (dept && dept !== 'ALL') url += `&department=${encodeURIComponent(dept)}`;
  if (empId && empId !== 'ALL') url += `&employee_id=${encodeURIComponent(empId)}`;

  window.open(url, '_blank');
}

function downloadReportPDF(specificEmpId) {
  const month = document.getElementById('report-month').value;
  const year = document.getElementById('report-year').value;
  const dept = document.getElementById('report-dept') ? document.getElementById('report-dept').value : 'ALL';
  const empSelect = document.getElementById('report-employee');
  const empId = specificEmpId || (empSelect ? empSelect.value : 'ALL');

  let url = `/api/attendance/monthly-detail/export-pdf?month=${month}&year=${year}`;
  if (dept && dept !== 'ALL') url += `&department=${encodeURIComponent(dept)}`;
  if (empId && empId !== 'ALL') url += `&employee_id=${encodeURIComponent(empId)}`;

  window.open(url, '_blank');
}

// 7. PAYROLL & PAYSLIPS
async function runMonthlyPayroll() {
  const month = document.getElementById('payroll-run-month').value;
  const year = document.getElementById('payroll-run-year').value;
  const btn = document.getElementById('btn-process-payroll');
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing 329 Staff...';

  try {
    const res = await fetch('/api/payroll/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ month: parseInt(month), year: parseInt(year) })
    });
    const data = await res.json();
    if (data.success) {
      currentPayrollRunId = data.payroll_run_id;
      showToast(data.message, 'success');
      loadPayrollRunDetails(currentPayrollRunId);
    } else {
      showToast('Error processing payroll', 'error');
    }
  } catch (err) {
    showToast('Failed to execute payroll run', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-calculator"></i> Run Monthly Payroll';
  }
}

async function loadPayroll() {
  try {
    const res = await fetch('/api/payroll/runs');
    const data = await res.json();
    if (data.runs && data.runs.length > 0) {
      currentPayrollRunId = data.runs[0].id;
      loadPayrollRunDetails(currentPayrollRunId);
    }
  } catch (err) {
    console.error(err);
  }
}

async function loadPayrollRunDetails(runId) {
  try {
    const res = await fetch(`/api/payroll/runs/${runId}`);
    const data = await res.json();
    document.getElementById('btn-export-excel').classList.remove('hidden');

    const tbody = document.getElementById('payroll-slips-body');
    tbody.innerHTML = '';

    data.payslips.forEach(slip => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition';
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-medium text-teal-700">${slip.employee_code}</td>
        <td class="py-2.5 px-3 font-bold text-slate-800">${slip.employee_name}</td>
        <td class="py-2.5 px-3 text-slate-600">${slip.paid_days} days</td>
        <td class="py-2.5 px-3 font-semibold text-slate-800">₹ ${parseFloat(slip.gross_earned).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
        <td class="py-2.5 px-3 text-slate-600">₹ ${(parseFloat(slip.pf_deduction) + parseFloat(slip.esic_deduction)).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
        <td class="py-2.5 px-3 text-rose-600 font-medium">₹ ${parseFloat(slip.total_deductions).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
        <td class="py-2.5 px-3 font-bold text-teal-700">₹ ${parseFloat(slip.net_pay).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
        <td class="py-2.5 px-3 text-right">
          <a href="/api/payroll/payslip/${slip.id}/pdf" target="_blank" class="bg-rose-50 hover:bg-rose-100 text-rose-700 px-2.5 py-1 rounded text-xs font-semibold inline-flex items-center space-x-1 transition">
            <i class="fas fa-file-pdf"></i>
            <span>PDF</span>
          </a>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

function exportPayrollExcel() {
  if (!currentPayrollRunId) {
    showToast('Please run payroll first to export salary sheet.', 'warning');
    return;
  }
  window.open(`/api/payroll/runs/${currentPayrollRunId}/export-excel`, '_blank');
}

// 8. LEAVES & HOLIDAYS
async function loadLeaves() {
  // Populate employee select
  const select = document.getElementById('leave-emp-select');
  select.innerHTML = employeesList.map(e => `<option value="${e.id}">${e.display_name} (${e.employee_code})</option>`).join('');

  // Fetch leaves
  try {
    const res = await fetch('/api/leaves');
    const data = await res.json();
    const tbody = document.getElementById('leaves-table-body');
    tbody.innerHTML = '';
    if (data.leaves.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">No leave applications submitted.</td></tr>';
    } else {
      data.leaves.forEach(l => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="py-2 px-3 font-semibold text-slate-800">${l.employee_name}</td>
          <td class="py-2 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">${l.leave_type}</span></td>
          <td class="py-2 px-3 text-slate-500 font-mono text-[11px]">${l.from_date} to ${l.to_date}</td>
          <td class="py-2 px-3 font-bold">${l.days_count}</td>
          <td class="py-2 px-3">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${l.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' : (l.status === 'REJECTED' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800')}">
              ${l.status}
            </span>
          </td>
          <td class="py-2 px-3 text-right">
            ${l.status === 'PENDING' ? `
              <button onclick="updateLeaveStatus('${l.id}', 'APPROVED')" class="text-emerald-600 hover:text-emerald-800 mr-2"><i class="fas fa-check"></i></button>
              <button onclick="updateLeaveStatus('${l.id}', 'REJECTED')" class="text-rose-600 hover:text-rose-800"><i class="fas fa-times"></i></button>
            ` : '<span class="text-slate-400">Completed</span>'}
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Fetch holidays
    const holRes = await fetch('/api/leaves/holidays');
    const holData = await holRes.json();
    const holGrid = document.getElementById('holidays-grid');
    holGrid.innerHTML = holData.holidays.map(h => `
      <div class="p-3 bg-slate-50 border border-slate-200 rounded-lg">
        <div class="font-bold text-slate-800 truncate">${h.holiday_name}</div>
        <div class="text-[11px] text-teal-700 font-mono font-medium">${h.holiday_date}</div>
        <div class="text-[10px] text-slate-400 uppercase mt-1">${h.holiday_type}</div>
      </div>
    `).join('');

  } catch (err) {
    console.error(err);
  }
}

async function submitLeave(e) {
  e.preventDefault();
  const payload = {
    employee_id: document.getElementById('leave-emp-select').value,
    leave_type: document.getElementById('leave-type-select').value,
    from_date: document.getElementById('leave-from-date').value,
    to_date: document.getElementById('leave-to-date').value,
    days_count: parseFloat(document.getElementById('leave-days-count').value) || 1.0,
    reason: document.getElementById('leave-reason').value
  };

  try {
    const res = await fetch('/api/leaves', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Leave request submitted!', 'success');
      loadLeaves();
      document.getElementById('leave-form').reset();
    }
  } catch (err) {
    showToast('Failed to apply leave', 'error');
  }
}

async function updateLeaveStatus(leaveId, status) {
  try {
    const res = await fetch(`/api/leaves/${leaveId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Leave application ${status}`, 'success');
      loadLeaves();
    }
  } catch (err) {
    showToast('Failed to update leave', 'error');
  }
}

// 9. DOCUMENT CONTROL
async function loadDocuments() {
  const tbody = document.getElementById('dms-table-body');
  tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">Loading document vault...</td></tr>';

  try {
    const res = await fetch('/api/employees?limit=500');
    const data = await res.json();
    let allDocs = [];

    for (let emp of data.employees.slice(0, 30)) {
      const dRes = await fetch(`/api/employees/${emp.id}`);
      const dData = await dRes.json();
      if (dData.documents && dData.documents.length > 0) {
        dData.documents.forEach(doc => {
          allDocs.push({ ...doc, employee_name: emp.display_name, employee_code: emp.employee_code });
        });
      }
    }

    tbody.innerHTML = '';
    if (allDocs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">No documents uploaded yet. Click "Upload Document" to add Aadhaar, PAN, degrees, etc.</td></tr>';
      return;
    }

    allDocs.forEach(d => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition';
      tr.innerHTML = `
        <td class="py-2.5 px-4 font-bold text-slate-800">${d.employee_name} <span class="text-slate-400 font-mono text-[10px]">(${d.employee_code})</span></td>
        <td class="py-2.5 px-4"><span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">${d.document_type}</span></td>
        <td class="py-2.5 px-4 font-semibold text-slate-800">${d.document_title}</td>
        <td class="py-2.5 px-4 font-mono text-slate-500">${d.file_name}</td>
        <td class="py-2.5 px-4">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${d.verification_status === 'VERIFIED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">
            ${d.verification_status}
          </span>
        </td>
        <td class="py-2.5 px-4 text-right space-x-2">
          <a href="/api/documents/${d.id}/download" target="_blank" class="text-teal-600 hover:text-teal-800 text-xs"><i class="fas fa-download"></i></a>
          <button onclick="verifyDoc('${d.id}', 'VERIFIED')" class="text-emerald-600 hover:text-emerald-800 text-xs"><i class="fas fa-check-circle"></i></button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-rose-500">Failed to load documents.</td></tr>';
  }
}

function openUploadDocModal(preSelectedEmpId = '') {
  const container = document.getElementById('modal-container');
  container.innerHTML = `
    <div class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <div class="flex items-center justify-between border-b pb-2">
          <h3 class="font-bold text-slate-800 text-sm">Upload Employee Document</h3>
          <button onclick="closeModal()" class="text-slate-400 hover:text-slate-700"><i class="fas fa-times"></i></button>
        </div>
        <form onsubmit="handleUploadDoc(event)" class="space-y-3 text-xs">
          <div>
            <label class="block text-slate-600 font-medium mb-1">Select Employee</label>
            <select id="doc-emp-select" required class="w-full p-2 border border-slate-300 rounded-lg">
              ${employeesList.map(e => `<option value="${e.id}" ${e.id === preSelectedEmpId ? 'selected' : ''}>${e.display_name} (${e.employee_code})</option>`).join('')}
            </select>
          </div>
          <div>
            <label class="block text-slate-600 font-medium mb-1">Document Category</label>
            <select id="doc-type-select" required class="w-full p-2 border border-slate-300 rounded-lg">
              <option value="AADHAAR">Aadhaar Card</option>
              <option value="PAN">PAN Card</option>
              <option value="DEGREE">Degree / Certificate</option>
              <option value="RESUME">Resume / CV</option>
              <option value="OFFER_LETTER">Offer / Appointment Letter</option>
              <option value="EXP_CERTIFICATE">Experience Letter</option>
              <option value="OTHER">Other Document</option>
            </select>
          </div>
          <div>
            <label class="block text-slate-600 font-medium mb-1">Document Title</label>
            <input type="text" id="doc-title-input" placeholder="e.g. Aadhaar Card Copy" required class="w-full p-2 border border-slate-300 rounded-lg">
          </div>
          <div>
            <label class="block text-slate-600 font-medium mb-1">Choose File (PDF, PNG, JPG)</label>
            <input type="file" id="doc-file-input" required class="w-full p-1.5 border border-slate-300 rounded-lg">
          </div>
          <div class="flex justify-end space-x-2 pt-3">
            <button type="button" onclick="closeModal()" class="px-4 py-1.5 bg-slate-200 text-slate-700 rounded-lg">Cancel</button>
            <button type="submit" class="px-4 py-1.5 bg-teal-600 hover:bg-teal-500 text-white rounded-lg font-semibold">Upload File</button>
          </div>
        </form>
      </div>
    </div>
  `;
}

async function handleUploadDoc(e) {
  e.preventDefault();
  const empId = document.getElementById('doc-emp-select').value;
  const docType = document.getElementById('doc-type-select').value;
  const docTitle = document.getElementById('doc-title-input').value;
  const fileInput = document.getElementById('doc-file-input');

  if (!fileInput.files || fileInput.files.length === 0) {
    showToast('Please select a file', 'warning');
    return;
  }

  const formData = new FormData();
  formData.append('document_type', docType);
  formData.append('document_title', docTitle);
  formData.append('file', fileInput.files[0]);

  try {
    const res = await fetch(`/api/documents/upload/${empId}`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      showToast('Document uploaded successfully!', 'success');
      closeModal();
      loadDocuments();
    }
  } catch (err) {
    showToast('Failed to upload document', 'error');
  }
}

async function verifyDoc(docId, status) {
  try {
    await fetch(`/api/documents/${docId}/verify`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verification_status: status, verification_remarks: 'Verified by HR Admin' })
    });
    showToast(`Document ${status}`, 'success');
    loadDocuments();
  } catch (err) {
    showToast('Failed to verify document', 'error');
  }
}

// Initial Load & Auto-Refresh
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  loadEmployees();
  
  // Auto-refresh Dashboard and Live Punches every 10 seconds
  setInterval(() => {
    if (currentTab === 'dashboard') {
      loadDashboard();
    }
  }, 10000);
});

// ==========================================
// CIVMASTERPRO SYSTEM UPGRADE & PUSH UPDATE
// ==========================================

function appendSystemLog(message) {
  const logBox = document.getElementById('sys-console-output');
  if (!logBox) return;
  const time = new Date().toLocaleTimeString();
  logBox.textContent += `\n[${time}] ${message}`;
  logBox.scrollTop = logBox.scrollHeight;
}

function clearSystemLog() {
  const logBox = document.getElementById('sys-console-output');
  if (logBox) logBox.textContent = `[CivMasterPro Console Cleared]`;
}

function copyUpdateCommand() {
  const text = document.getElementById('cmd-curl-text').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    showToast('Curl command copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy. Please copy manually.', 'info');
  });
}

async function checkSystemStatusUI() {
  appendSystemLog('Fetching real-time CivMasterPro system status...');
  try {
    const res = await fetch('/api/system/status');
    const data = await res.json();
    
    if (document.getElementById('sys-platform')) {
      document.getElementById('sys-platform').textContent = data.brand ? `${data.brand} Enterprise` : 'CivMasterPro Enterprise';
    }
    if (document.getElementById('sys-version')) {
      document.getElementById('sys-version').textContent = data.version || 'v2.4.0-CivMasterPro';
    }
    if (document.getElementById('sys-git-branch')) {
      const branch = (data.git && data.git.branch) ? data.git.branch : 'master';
      document.getElementById('sys-git-branch').textContent = branch;
    }
    if (document.getElementById('sys-git-commit')) {
      const commit = (data.git && data.git.commit) ? `Commit: ${data.git.commit}` : 'Git: Clean';
      document.getElementById('sys-git-commit').textContent = commit;
    }

    appendSystemLog(`[STATUS OK] Service: ${data.service} | Version: ${data.version} | Python: ${data.python_version}`);
    if (data.git && data.git.last_commit) {
      appendSystemLog(`[GIT] Latest commit: ${data.git.last_commit}`);
    }
  } catch (err) {
    appendSystemLog(`[ERROR] Failed to query system status: ${err.message}`);
    showToast('Error checking system status', 'error');
  }
}

async function triggerHotRestartUI() {
  if (!confirm('Are you sure you want to restart the CivMasterPro server process? (It will be back up in ~2 seconds)')) {
    return;
  }
  const token = document.getElementById('update-zip-token')?.value || 'svd_update_secret_key_2026';
  appendSystemLog('Sending restart command to server runner...');
  try {
    const res = await fetch(`/api/system/restart?token=${encodeURIComponent(token)}`, { method: 'POST' });
    const data = await res.json();
    appendSystemLog(`[SERVER] ${data.message}`);
    showToast('Server restart triggered. Reconnecting...', 'info');
    setTimeout(() => {
      checkSystemStatusUI();
    }, 4000);
  } catch (err) {
    appendSystemLog(`[NOTICE] Server connection reset (server is restarting): ${err.message}`);
    showToast('Server is restarting...', 'success');
  }
}

async function triggerRemoteGitUpdate() {
  const btn = document.getElementById('btn-trigger-git-update');
  const token = document.getElementById('update-zip-token')?.value || 'svd_update_secret_key_2026';
  
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Triggering Remote Update...</span>';
  appendSystemLog('Invoking POST /api/system/update webhook...');

  try {
    const res = await fetch(`/api/system/update?token=${encodeURIComponent(token)}`, { method: 'POST' });
    const data = await res.json();
    appendSystemLog(`[UPDATE RESULT] Success: ${data.success}`);
    appendSystemLog(`[MESSAGE] ${data.message}`);
    if (data.git_output) appendSystemLog(`[OUTPUT]\n${data.git_output}`);
    if (data.hint) appendSystemLog(`[HINT] ${data.hint}`);
    
    showToast(data.message, data.success ? 'success' : 'info');
  } catch (err) {
    appendSystemLog(`[ERROR] Remote update failed: ${err.message}`);
    showToast('Remote update request failed', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-arrows-rotate"></i><span>Execute Remote Update via Webhook</span>';
  }
}

async function handleZipPushUpdate(event) {
  event.preventDefault();
  const fileInput = document.getElementById('update-zip-file');
  const tokenInput = document.getElementById('update-zip-token');
  const installDeps = document.getElementById('update-install-deps').checked;
  const btn = document.getElementById('btn-submit-zip-update');

  if (!fileInput.files || fileInput.files.length === 0) {
    showToast('Please select a .zip update package.', 'error');
    return;
  }

  const file = fileInput.files[0];
  if (!file.name.toLowerCase().endsWith('.zip')) {
    showToast('Only .zip files are allowed for system updates.', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Uploading & Applying Update Package...</span>';
  appendSystemLog(`Uploading update package "${file.name}" (${(file.size / 1024).toFixed(1)} KB)...`);

  try {
    const res = await fetch(`/api/system/push-update?token=${encodeURIComponent(tokenInput.value)}&install_deps=${installDeps}`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Push update failed.');
    }

    appendSystemLog(`[SUCCESS] ${data.message}`);
    if (data.files_updated_count) {
      appendSystemLog(`[FILES] ${data.files_updated_count} files extracted & replaced cleanly.`);
    }
    showToast('Push update applied! Server restarting...', 'success');
    fileInput.value = '';

    setTimeout(() => {
      appendSystemLog('Reconnecting to updated CivMasterPro portal...');
      checkSystemStatusUI();
    }, 4000);

  } catch (err) {
    appendSystemLog(`[ERROR] Push update error: ${err.message}`);
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-cloud-arrow-up"></i><span>Push & Deploy Update Package</span>';
  }
}
