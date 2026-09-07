const app = document.querySelector('#app');
let token = sessionStorage.token || '';
let me = null;
let lookups = null;

const api = async (path, options = {}) => {
  const cleanPath = String(path || '').replace(/^(?:\/?api)?\/+/, '');
  const opts = { ...options };
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch('/api/' + cleanPath, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(opts.headers || {}) },
  });
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    let msg = errData.detail || 'The request could not be completed.';
    if (Array.isArray(msg)) {
      msg = msg.map(m => m.msg || JSON.stringify(m)).join(', ');
    } else if (typeof msg === 'object') {
      msg = JSON.stringify(msg);
    }
    throw new Error(msg);
  }
  return response.status === 204 ? null : response.json();
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const money = value => Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const humanTime = value => {
  const match = String(value ?? '').match(/(?:T|\s)(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (!match) return value || '';
  const hour = Number(match[1]);
  return `${((hour + 11) % 12) + 1}:${match[2]} ${hour >= 12 ? 'PM' : 'AM'}`;
};
const has = permission => {
  if (!me) return false;
  if (me.role === 'super_admin' || me.role === 'admin') return true;
  if (me.permissions?.includes(permission)) return true;
  if (permission === 'payroll.manage' && me.permissions?.includes('finance.manage')) return true;
  return false;
};

function showError(error) { alert(error?.message || String(error)); }

const navIcons = {
  dashboard: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`,
  attendance: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  calendar: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
  tasks: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>`,
  assistant: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  reports: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  students: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>`,
  enrollments: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>`,
  bills: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>`,
  'student-transactions': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>`,
  certificates: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>`,
  routines: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>`,
  grades: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  courses: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>`,
  schools: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-3"/></svg>`,
  staff: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>`,
  advances: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/></svg>`,
  salary: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 100 4h4a2 2 0 110 4H8"/><line x1="12" y1="6" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="18"/></svg>`,
  finance: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 118 2.83"/><path d="M22 12A10 10 0 0012 2v10z"/></svg>`,
  transfers: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>`,
  'student-profile': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  users: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a5 5 0 00-5 5v3a5 5 0 0010 0V7a5 5 0 00-5-5z"/><path d="M17 14v1a5 5 0 01-10 0v-1M4 22a8 8 0 0116 0"/></svg>`,
  company: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M9 8h1M9 12h1M9 16h1M14 8h1M14 12h1M14 16h1M5 21V5a2 2 0 012-2h10a2 2 0 012 2v16"/></svg>`,
  proxy: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>`,
  'teacher-proxy': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>`,
  settings: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>`,
  print: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>`,
  edit: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  backup: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>`,
  audit: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>`,
  lock: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>`,
  check: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  close: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  arrowRight: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`,
  arrowLeft: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>`,
  plus: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  chevronDown: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`,
  chevronLeft: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>`,
  chevronRight: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`,
  chevronDoubleLeft: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>`,
  chevronDoubleRight: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>`,
  'teacher-classes': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>`,
  'teacher-attendance': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  'teacher-payments': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/><circle cx="7" cy="15" r="1"/></svg>`,
  'user-check': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>`,
  'user-x': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/></svg>`,
  'alert-triangle': `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  cms: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>`,
  inquiries: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`
};

function uiIcon(name, size = 16, style = '') {
  const raw = navIcons[name] || '';
  if (!raw) return '';
  return raw
    .replace(/width="\d+"/, `width="${size}"`)
    .replace(/height="\d+"/, `height="${size}"`)
    .replace(/<svg /, `<svg ${style ? `style="${style}" ` : ''}`);
}

/* ==========================================================================
   Advanced DataTable Engine (DataTables+ Enterprise)
   ========================================================================== */

function parseNumeric(val) {
  if (typeof val === 'number') return isNaN(val) ? null : val;
  if (!val || typeof val !== 'string') return null;
  const cleaned = val.replace(/[^0-9.-]/g, '');
  if (!cleaned || isNaN(Number(cleaned))) return null;
  return parseFloat(cleaned);
}

function parseTimeMinutes(val) {
  if (typeof val !== 'string') return null;
  const match = val.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return null;
  let hour = parseInt(match[1], 10);
  const min = parseInt(match[2], 10);
  const ampm = match[3].toUpperCase();
  if (ampm === 'PM' && hour < 12) hour += 12;
  if (ampm === 'AM' && hour === 12) hour = 0;
  return hour * 60 + min;
}

function showDtToast(message) {
  let toast = document.querySelector('.dt-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.className = 'dt-toast';
    document.body.append(toast);
  }
  toast.innerHTML = `<span class="dt-toast-icon">${uiIcon('check', 12)}</span><span>${esc(message)}</span>`;
  toast.classList.add('show');
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {
    toast.classList.remove('show');
  }, 2500);
}

class AdvancedDataTable {
  constructor(id, rows, columns, options = {}) {
    this.id = id;
    this.rawRows = Array.isArray(rows) ? rows : [];
    this.columns = Array.isArray(columns) ? columns : [];
    this.options = {
      pageSize: options.pageSize !== undefined ? options.pageSize : (this.rawRows.length > 25 ? 25 : 10),
      sortable: options.sortable !== false,
      searchable: options.searchable !== false,
      exportable: options.exportable !== false,
      colvis: options.colvis !== false,
      pagination: options.pagination !== false,
      density: options.density || 'comfortable',
      title: options.title || '',
      ...options
    };
    this.pageSize = this.options.pageSize;
    this.currentPage = 1;
    this.searchQuery = '';
    this.sortColIndex = options.defaultSortCol !== undefined ? options.defaultSortCol : null;
    this.sortDir = options.defaultSortDir || 'asc';
    this.hiddenColumns = new Set(options.hiddenColumns || []);
    this.density = this.options.density;
    this.searchIndex = [];
    this.cacheSearchData();
  }

  cacheSearchData() {
    this.searchIndex = this.rawRows.map(row => {
      const tokens = [];
      for (const col of this.columns) {
        if (col.key === 'actions' || col.key === 'select_bill' || col.isCheckbox || (!col.label && !col.key)) continue;
        let val = '';
        if (col.render) {
          try {
            const rendered = String(col.render(row) ?? '');
            val = rendered.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
          } catch (e) {
            val = '';
          }
        } else if (row[col.key] !== undefined && row[col.key] !== null) {
          val = String(row[col.key]);
        }
        if (val) tokens.push(val.toLowerCase());
      }
      return tokens.join(' ');
    });
  }

  getFilteredRowIndices() {
    if (!this.searchQuery.trim()) {
      return this.rawRows.map((_, i) => i);
    }
    const terms = this.searchQuery.toLowerCase().trim().split(/\s+/).filter(Boolean);
    const matched = [];
    for (let i = 0; i < this.rawRows.length; i++) {
      const text = this.searchIndex[i] || '';
      if (terms.every(t => text.includes(t))) {
        matched.push(i);
      }
    }
    return matched;
  }

  getProcessedRowIndices() {
    const indices = this.getFilteredRowIndices();
    if (this.sortColIndex === null || !this.columns[this.sortColIndex]) {
      return indices;
    }
    const col = this.columns[this.sortColIndex];
    const dir = this.sortDir === 'desc' ? -1 : 1;

    const sortValues = new Map();
    for (const idx of indices) {
      const row = this.rawRows[idx];
      let val;
      if (col.key && row[col.key] !== undefined && row[col.key] !== null && typeof row[col.key] === 'number') {
        val = row[col.key];
      } else if (col.render) {
        try {
          const rendered = String(col.render(row) ?? '');
          val = rendered.replace(/<[^>]*>/g, '').replace(/,/g, '').trim();
        } catch (e) {
          val = '';
        }
      } else {
        val = row[col.key] ?? '';
      }
      sortValues.set(idx, val);
    }

    indices.sort((a, b) => {
      const valA = sortValues.get(a);
      const valB = sortValues.get(b);

      const emptyA = valA === '' || valA === null || valA === undefined;
      const emptyB = valB === '' || valB === null || valB === undefined;
      if (emptyA && emptyB) return 0;
      if (emptyA) return 1;
      if (emptyB) return -1;

      // Numeric comparison
      const numA = typeof valA === 'number' ? valA : parseNumeric(valA);
      const numB = typeof valB === 'number' ? valB : parseNumeric(valB);
      if (numA !== null && numB !== null) {
        return (numA - numB) * dir;
      }

      // Time comparison (e.g. 10:30 AM vs 2:00 PM)
      const timeA = parseTimeMinutes(valA);
      const timeB = parseTimeMinutes(valB);
      if (timeA !== null && timeB !== null) {
        return (timeA - timeB) * dir;
      }

      // String natural comparison (handles dates YYYY/MM/DD and alphanumeric)
      if (typeof valA === 'string' && typeof valB === 'string') {
        return valA.localeCompare(valB, undefined, { numeric: true, sensitivity: 'base' }) * dir;
      }

      return (valA < valB ? -1 : valA > valB ? 1 : 0) * dir;
    });

    return indices;
  }

  getVisibleColumnCount() {
    let count = 0;
    for (let i = 0; i < this.columns.length; i++) {
      if (!this.hiddenColumns.has(i)) count++;
    }
    return Math.max(1, count);
  }

  renderToolbar(processedIndices) {
    const total = this.rawRows.length;
    const filtered = processedIndices.length;
    const isFiltered = this.searchQuery.trim().length > 0;

    const lengths = [10, 25, 50, 100, -1];
    const lengthOptions = lengths.map(len => {
      const text = len === -1 ? 'All' : len;
      const sel = this.pageSize === len ? 'selected' : '';
      return `<option value="${len}" ${sel}>${text}</option>`;
    }).join('');

    const colvisItems = this.columns.map((col, idx) => {
      if ((!col.label && col.key === 'actions') || col.key === 'select_bill' || col.isCheckbox) return '';
      const checked = !this.hiddenColumns.has(idx) ? 'checked' : '';
      return `
        <label class="dt-colvis-item">
          <input type="checkbox" class="dt-col-checkbox" data-col-idx="${idx}" ${checked}>
          <span>${esc(col.label || `Column ${idx + 1}`)}</span>
        </label>
      `;
    }).filter(Boolean).join('');

    return `
      <div class="dt-toolbar">
        <div class="dt-toolbar-left">
          <div class="dt-length">
            <label>
              <span>Show</span>
              <select class="dt-length-select" aria-label="Entries per page">${lengthOptions}</select>
              <span>entries</span>
            </label>
          </div>
          <div class="dt-buttons">
            <button type="button" class="dt-action-btn dt-btn-copy" data-action="copy" title="Copy to clipboard">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              <span>Copy</span>
            </button>
            <button type="button" class="dt-action-btn dt-btn-csv" data-action="csv" title="Export table data to CSV">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              <span>CSV</span>
            </button>
            <button type="button" class="dt-action-btn dt-btn-print" data-action="print" title="Print formatted table">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
              <span>Print</span>
            </button>
            <div class="dt-colvis-dropdown">
              <button type="button" class="dt-action-btn dt-btn-colvis" data-action="toggle-colvis" title="Toggle column visibility">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                <span style="display:inline-flex;align-items:center;gap:3px;">Columns ${uiIcon('chevronDown', 12)}</span>
              </button>
              <div class="dt-colvis-menu">
                <div class="dt-colvis-header">
                  <b>Visible Columns</b>
                  <button type="button" class="dt-colvis-reset-btn" data-action="reset-columns">Show All</button>
                </div>
                <div class="dt-colvis-list">${colvisItems}</div>
              </div>
            </div>
            <button type="button" class="dt-action-btn dt-btn-density ${this.density === 'compact' ? 'active' : ''}" data-action="toggle-density" title="Toggle compact density">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="12" x2="3" y2="12"/><line x1="21" y1="18" x2="3" y2="18"/></svg>
              <span>${this.density === 'compact' ? 'Comfortable' : 'Compact'}</span>
            </button>
          </div>
        </div>
        <div class="dt-toolbar-right">
          <div class="dt-search">
            <svg class="dt-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="search" class="dt-search-input" placeholder="Search table..." value="${esc(this.searchQuery)}" aria-label="Search records">
            ${isFiltered ? `<button type="button" class="dt-search-clear-btn" data-action="clear-search" title="Clear search" aria-label="Clear search" style="display:inline-flex;align-items:center;justify-content:center;">${uiIcon('close', 12)}</button>` : ''}
            ${isFiltered ? `<span class="dt-match-badge">${filtered}/${total}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  renderHeader() {
    const ths = this.columns.map((col, colIdx) => {
      if (this.hiddenColumns.has(colIdx)) return '';
      const isCheckboxCol = col.key === 'select_bill' || col.isCheckbox;
      const isSortable = !isCheckboxCol && this.options.sortable && col.sortable !== false && col.label && col.key !== 'actions';
      const isSorted = this.sortColIndex === colIdx;
      const sortClass = isSorted ? (this.sortDir === 'asc' ? 'dt-sorted-asc' : 'dt-sorted-desc') : '';
      const sortIcon = isSortable
        ? (isSorted
            ? (this.sortDir === 'asc'
                ? `<svg class="dt-sort-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>`
                : `<svg class="dt-sort-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`)
            : `<svg class="dt-sort-neutral" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 9 12 5 16 9"/><polyline points="16 15 12 19 8 15"/></svg>`)
        : '';

      const thTitle = isSortable ? `role="button" tabindex="0" title="Click to sort by ${esc(col.title || col.label)}"` : '';
      const labelHtml = (isCheckboxCol || col.rawHeader) ? (col.headerHtml || col.label) : esc(col.label);
      const thStyle = isCheckboxCol ? 'style="width:38px;text-align:center;padding:6px 8px;"' : '';

      return `<th class="${isSortable ? 'dt-sortable' : ''} ${sortClass}" data-col-idx="${colIdx}" ${thTitle} ${thStyle}>
        <div class="dt-th-content" style="${isCheckboxCol ? 'justify-content:center;' : ''}">
          <span class="dt-th-label">${labelHtml}</span>
          ${sortIcon}
        </div>
      </th>`;
    }).join('');
    return `<thead><tr>${ths}</tr></thead>`;
  }

  renderBodyRows(processedIndices) {
    if (!processedIndices.length) {
      const visibleCount = this.getVisibleColumnCount();
      const message = this.searchQuery
        ? `<div class="dt-empty-state">
             <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
             <p>No matching records found for "<b>${esc(this.searchQuery)}</b>"</p>
             <button type="button" class="dt-btn-clear-search" data-action="clear-search">Clear filter</button>
           </div>`
        : `<div class="dt-empty-state">
             <p>No records found.</p>
           </div>`;
      return `<tr><td class="empty dt-empty-cell" colspan="${visibleCount}">${message}</td></tr>`;
    }

    const pageSize = this.pageSize === -1 ? processedIndices.length : this.pageSize;
    const start = (this.currentPage - 1) * pageSize;
    const pageIndices = processedIndices.slice(start, start + pageSize);

    return pageIndices.map(idx => {
      const row = this.rawRows[idx];
      const cells = this.columns.map((col, colIdx) => {
        if (this.hiddenColumns.has(colIdx)) return '';
        let content = '';
        try {
          content = col.render ? col.render(row) : esc(row[col.key]);
        } catch (err) {
          content = esc(row[col.key] ?? '');
        }
        const isCheckboxCol = col.key === 'select_bill' || col.isCheckbox;
        const tdStyle = isCheckboxCol ? 'style="width:38px;text-align:center;padding:6px 8px;"' : '';
        return `<td ${tdStyle}>${content}</td>`;
      }).join('');
      const rowStyle = this.options.rowStyle ? (typeof this.options.rowStyle === 'function' ? this.options.rowStyle(row) : this.options.rowStyle) : '';
      const rowClass = this.options.rowClass ? (typeof this.options.rowClass === 'function' ? this.options.rowClass(row) : this.options.rowClass) : '';
      return `<tr ${rowClass ? `class="${rowClass}"` : ''} ${rowStyle ? `style="${rowStyle}"` : ''}>${cells}</tr>`;
    }).join('');
  }

  renderFooter(processedIndices) {
    const total = this.rawRows.length;
    const filtered = processedIndices.length;
    const pageSize = this.pageSize === -1 ? filtered : this.pageSize;
    const totalPages = Math.max(1, Math.ceil(filtered / (pageSize || 1)));

    if (this.currentPage > totalPages) this.currentPage = totalPages;
    if (this.currentPage < 1) this.currentPage = 1;

    const start = filtered === 0 ? 0 : (this.currentPage - 1) * pageSize + 1;
    const end = this.pageSize === -1 ? filtered : Math.min(filtered, this.currentPage * pageSize);

    const infoText = filtered === total
      ? `Showing <b>${start}</b> to <b>${end}</b> of <b>${total}</b> entries`
      : `Showing <b>${start}</b> to <b>${end}</b> of <b>${filtered}</b> entries <span class="dt-filtered-hint">(filtered from ${total} total)</span>`;

    let pageButtons = '';
    if (totalPages > 1) {
      const isFirst = this.currentPage === 1;
      const isLast = this.currentPage === totalPages;

      pageButtons += `<button type="button" class="dt-page-btn" data-page="1" ${isFirst ? 'disabled' : ''} title="First page" aria-label="First page" style="display:inline-flex;align-items:center;justify-content:center;">${uiIcon('chevronDoubleLeft', 12)}</button>`;
      pageButtons += `<button type="button" class="dt-page-btn" data-page="${this.currentPage - 1}" ${isFirst ? 'disabled' : ''} title="Previous page" aria-label="Previous page" style="display:inline-flex;align-items:center;justify-content:center;">${uiIcon('chevronLeft', 12)}</button>`;

      const pagesToShow = this.getPageNumbers(this.currentPage, totalPages);
      for (const p of pagesToShow) {
        if (p === '...') {
          pageButtons += `<span class="dt-page-ellipsis">…</span>`;
        } else {
          const isActive = p === this.currentPage;
          pageButtons += `<button type="button" class="dt-page-btn ${isActive ? 'active' : ''}" data-page="${p}">${p}</button>`;
        }
      }

      pageButtons += `<button type="button" class="dt-page-btn" data-page="${this.currentPage + 1}" ${isLast ? 'disabled' : ''} title="Next page" aria-label="Next page" style="display:inline-flex;align-items:center;justify-content:center;">${uiIcon('chevronRight', 12)}</button>`;
      pageButtons += `<button type="button" class="dt-page-btn" data-page="${totalPages}" ${isLast ? 'disabled' : ''} title="Last page" aria-label="Last page" style="display:inline-flex;align-items:center;justify-content:center;">${uiIcon('chevronDoubleRight', 12)}</button>`;
    }

    return `
      <div class="dt-footer">
        <div class="dt-info">${infoText}</div>
        <div class="dt-pagination">${pageButtons}</div>
      </div>
    `;
  }

  getPageNumbers(curr, total) {
    if (total <= 7) {
      return Array.from({ length: total }, (_, i) => i + 1);
    }
    if (curr <= 4) {
      return [1, 2, 3, 4, 5, '...', total];
    }
    if (curr >= total - 3) {
      return [1, '...', total - 4, total - 3, total - 2, total - 1, total];
    }
    return [1, '...', curr - 1, curr, curr + 1, '...', total];
  }

  updateView() {
    const container = document.getElementById(this.id);
    if (!container) return;
    const processed = this.getProcessedRowIndices();

    container.classList.toggle('dt-compact', this.density === 'compact');

    const thead = container.querySelector('.dt-table thead');
    if (thead) thead.outerHTML = this.renderHeader();

    const tbody = container.querySelector('.dt-table tbody');
    if (tbody) tbody.innerHTML = this.renderBodyRows(processed);

    const footer = container.querySelector('.dt-footer');
    if (footer) footer.outerHTML = this.renderFooter(processed);

    const searchWrap = container.querySelector('.dt-search');
    if (searchWrap) {
      let clearBtn = searchWrap.querySelector('.dt-search-clear-btn');
      let badge = searchWrap.querySelector('.dt-match-badge');
      if (this.searchQuery.trim()) {
        if (!clearBtn) {
          clearBtn = document.createElement('button');
          clearBtn.type = 'button';
          clearBtn.className = 'dt-search-clear-btn';
          clearBtn.dataset.action = 'clear-search';
          clearBtn.title = 'Clear search';
          clearBtn.setAttribute('aria-label', 'Clear search');
          clearBtn.style.display = 'inline-flex';
          clearBtn.style.alignItems = 'center';
          clearBtn.style.justifyContent = 'center';
          clearBtn.innerHTML = uiIcon('close', 12);
          searchWrap.append(clearBtn);
        }
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'dt-match-badge';
          searchWrap.append(badge);
        }
        badge.textContent = `${processed.length}/${this.rawRows.length}`;
      } else {
        if (clearBtn) clearBtn.remove();
        if (badge) badge.remove();
      }
    }

    container.querySelectorAll('.dt-col-checkbox').forEach(cb => {
      const idx = Number(cb.dataset.colIdx);
      cb.checked = !this.hiddenColumns.has(idx);
    });

    const densityBtn = container.querySelector('.dt-btn-density');
    if (densityBtn) {
      densityBtn.classList.toggle('active', this.density === 'compact');
      const span = densityBtn.querySelector('span');
      if (span) span.textContent = this.density === 'compact' ? 'Comfortable' : 'Compact';
    }

    if (typeof updateSelectedBillsUI === 'function') {
      try { updateSelectedBillsUI(); } catch (e) {}
    }
  }

  copyToClipboard() {
    const processed = this.getProcessedRowIndices();
    if (!processed.length) {
      showDtToast('No records to copy');
      return;
    }
    const visibleCols = this.columns.filter((c, idx) => !this.hiddenColumns.has(idx) && (c.label || c.key !== 'actions') && c.key !== 'select_bill' && !c.isCheckbox);
    if (!visibleCols.length) return;

    const headerLine = visibleCols.map(c => c.label).join('\t');
    const rowsLines = processed.map(idx => {
      const row = this.rawRows[idx];
      return visibleCols.map(c => {
        if (c.csv) return String(c.csv(row) ?? '').replace(/[\t\n\r]/g, ' ');
        if (c.render) {
          return String(c.render(row) ?? '').replace(/<[^>]*>/g, '').trim().replace(/[\t\n\r]/g, ' ');
        }
        return String(row[c.key] ?? '').replace(/[\t\n\r]/g, ' ');
      }).join('\t');
    });

    const fullText = [headerLine, ...rowsLines].join('\n');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(fullText).then(() => {
        showDtToast(`Copied ${processed.length} row${processed.length === 1 ? '' : 's'} to clipboard`);
      }).catch(() => {
        this.fallbackCopy(fullText, processed.length);
      });
    } else {
      this.fallbackCopy(fullText, processed.length);
    }
  }

  fallbackCopy(text, count) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.append(ta);
    ta.select();
    try {
      document.execCommand('copy');
      showDtToast(`Copied ${count} row${count === 1 ? '' : 's'} to clipboard`);
    } catch (e) {
      showError(new Error('Failed to copy to clipboard'));
    }
    ta.remove();
  }

  exportCsv() {
    const processed = this.getProcessedRowIndices();
    if (!processed.length) {
      showDtToast('No records to export');
      return;
    }
    const visibleCols = this.columns.filter((c, idx) => !this.hiddenColumns.has(idx) && (c.label || c.key !== 'actions') && c.key !== 'select_bill' && !c.isCheckbox);
    if (!visibleCols.length) return;

    const headerLine = visibleCols.map(c => `"${String(c.label ?? '').replaceAll('"', '""')}"`).join(',');
    const rowLines = processed.map(idx => {
      const row = this.rawRows[idx];
      return visibleCols.map(c => {
        let val = '';
        if (c.csv) {
          val = String(c.csv(row) ?? '');
        } else if (c.render) {
          val = String(c.render(row) ?? '').replace(/<[^>]*>/g, '').trim();
        } else {
          val = String(row[c.key] ?? '');
        }
        return `"${val.replaceAll('"', '""')}"`;
      }).join(',');
    });

    const pageTitle = (location.hash.slice(1).split('?')[0]) || 'table_export';
    const filename = `${pageTitle}_${new Date().toISOString().slice(0, 10)}.csv`;
    const csvContent = '\uFEFF' + [headerLine, ...rowLines].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    showDtToast(`Exported ${processed.length} rows to ${filename}`);
  }

  printTable() {
    const processed = this.getProcessedRowIndices();
    if (!processed.length) {
      showDtToast('No records to print');
      return;
    }
    const visibleCols = this.columns.filter((c, idx) => !this.hiddenColumns.has(idx) && (c.label || c.key !== 'actions') && c.key !== 'select_bill' && !c.isCheckbox);
    if (!visibleCols.length) return;

    const pageTitle = document.querySelector('.top h1')?.innerText || document.title || 'Table Report';
    const tableHeaders = visibleCols.map(c => `<th>${esc(c.label)}</th>`).join('');
    const tableRows = processed.map(idx => {
      const row = this.rawRows[idx];
      const cells = visibleCols.map(c => {
        let val = '';
        if (c.render) {
          val = String(c.render(row) ?? '');
        } else {
          val = esc(row[c.key] ?? '');
        }
        return `<td>${val}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    const printWindow = window.open('', '_blank', 'width=900,height=700');
    if (!printWindow) {
      alert('Please allow popups to print table records.');
      return;
    }

    printWindow.document.open();
    printWindow.document.write(`
      <!doctype html>
      <html>
        <head>
          <meta charset="utf-8">
          <title>${esc(pageTitle)} - Print</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; color: #111; }
            .header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #222; padding-bottom: 8px; margin-bottom: 16px; }
            .header h1 { margin: 0; font-size: 20px; }
            .header .meta { font-size: 12px; color: #555; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
            th, td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; }
            th { background: #f2f2f2; font-weight: 700; text-transform: uppercase; font-size: 11px; }
            tr:nth-child(even) td { background: #fafafa; }
            @media print {
              body { margin: 0; }
              th { background-color: #eee !important; -webkit-print-color-adjust: exact; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>${esc(pageTitle)}</h1>
            <div class="meta">Printed: ${new Date().toLocaleString()} · Total: ${processed.length} records</div>
          </div>
          <table>
            <thead><tr>${tableHeaders}</tr></thead>
            <tbody>${tableRows}</tbody>
          </table>
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
    }, 250);
  }
}

// Global Delegated Event Listeners for all Advanced DataTables
document.addEventListener('click', e => {
  // Sort header click
  const th = e.target.closest('th.dt-sortable');
  if (th) {
    const container = th.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        const colIdx = Number(th.dataset.colIdx);
        if (!isNaN(colIdx)) {
          if (instance.sortColIndex === colIdx) {
            if (instance.sortDir === 'asc') {
              instance.sortDir = 'desc';
            } else if (instance.sortDir === 'desc') {
              instance.sortColIndex = null;
              instance.sortDir = 'asc';
            }
          } else {
            instance.sortColIndex = colIdx;
            instance.sortDir = 'asc';
          }
          instance.currentPage = 1;
          instance.updateView();
          return;
        }
      }
    }
  }

  // Clear search
  const clearBtn = e.target.closest('[data-action="clear-search"]');
  if (clearBtn) {
    const container = clearBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.searchQuery = '';
        instance.currentPage = 1;
        const input = container.querySelector('.dt-search-input');
        if (input) {
          input.value = '';
          input.focus();
        }
        instance.updateView();
        return;
      }
    }
  }

  // Pagination button click
  const pageBtn = e.target.closest('.dt-page-btn');
  if (pageBtn && !pageBtn.disabled) {
    const container = pageBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        const page = Number(pageBtn.dataset.page);
        if (!isNaN(page)) {
          instance.currentPage = page;
          instance.updateView();
          return;
        }
      }
    }
  }

  // Copy button
  const copyBtn = e.target.closest('[data-action="copy"]');
  if (copyBtn) {
    const container = copyBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.copyToClipboard();
        return;
      }
    }
  }

  // CSV button
  const csvBtn = e.target.closest('[data-action="csv"]');
  if (csvBtn) {
    const container = csvBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.exportCsv();
        return;
      }
    }
  }

  // Print button
  const printBtn = e.target.closest('[data-action="print"]');
  if (printBtn) {
    const container = printBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.printTable();
        return;
      }
    }
  }

  // Density button
  const densityBtn = e.target.closest('[data-action="toggle-density"]');
  if (densityBtn) {
    const container = densityBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.density = instance.density === 'compact' ? 'comfortable' : 'compact';
        instance.updateView();
        return;
      }
    }
  }

  // Columns visibility toggle & dropdown click outside
  const colvisToggle = e.target.closest('[data-action="toggle-colvis"]');
  const openMenus = document.querySelectorAll('.dt-colvis-dropdown.open');
  if (colvisToggle) {
    const dropdown = colvisToggle.closest('.dt-colvis-dropdown');
    const wasOpen = dropdown.classList.contains('open');
    openMenus.forEach(m => m.classList.remove('open'));
    if (!wasOpen) dropdown.classList.add('open');
    e.stopPropagation();
    return;
  }
  if (!e.target.closest('.dt-colvis-menu')) {
    openMenus.forEach(m => m.classList.remove('open'));
  }

  // Reset columns
  const resetBtn = e.target.closest('[data-action="reset-columns"]');
  if (resetBtn) {
    const container = resetBtn.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.hiddenColumns.clear();
        instance.updateView();
        return;
      }
    }
  }
});

// Search input listener
document.addEventListener('input', e => {
  const input = e.target.closest('.dt-search-input');
  if (!input) return;
  const container = input.closest('.advanced-datatable-container');
  if (!container) return;
  const instance = window._activeDataTables?.get(container.dataset.dtId);
  if (!instance) return;
  instance.searchQuery = input.value;
  instance.currentPage = 1;
  instance.updateView();
});

// Length select change & column checkbox change
document.addEventListener('change', e => {
  const select = e.target.closest('.dt-length-select');
  if (select) {
    const container = select.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        instance.pageSize = Number(select.value);
        instance.currentPage = 1;
        instance.updateView();
        return;
      }
    }
  }

  const cb = e.target.closest('.dt-col-checkbox');
  if (cb) {
    const container = cb.closest('.advanced-datatable-container');
    if (container) {
      const instance = window._activeDataTables?.get(container.dataset.dtId);
      if (instance) {
        const colIdx = Number(cb.dataset.colIdx);
        if (cb.checked) {
          instance.hiddenColumns.delete(colIdx);
        } else {
          if (instance.columns.length - instance.hiddenColumns.size <= 1) {
            cb.checked = true;
            showDtToast('At least one column must remain visible');
            return;
          }
          instance.hiddenColumns.add(colIdx);
        }
        instance.updateView();
        return;
      }
    }
  }
});

// Keyboard accessibility for sortable headers
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') {
    const th = e.target.closest('th.dt-sortable');
    if (th && e.target === th) {
      e.preventDefault();
      th.click();
    }
  }
});

function table(rows, columns, options = {}) {
  if (!window._activeDataTables) window._activeDataTables = new Map();
  if (window._activeDataTables.size > 200) {
    for (const [key] of window._activeDataTables) {
      if (!document.getElementById(key)) window._activeDataTables.delete(key);
    }
  }

  const id = 'dt_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now().toString(36);
  const instance = new AdvancedDataTable(id, rows, columns, options);
  window._activeDataTables.set(id, instance);

  const processed = instance.getProcessedRowIndices();
  return `
    <div class="advanced-datatable-container ${instance.density === 'compact' ? 'dt-compact' : ''}" id="${id}" data-dt-id="${id}">
      ${instance.renderToolbar(processed)}
      <div class="table-wrap dt-table-wrap">
        <table class="dt-table">
          ${instance.renderHeader()}
          <tbody>
            ${instance.renderBodyRows(processed)}
          </tbody>
        </table>
      </div>
      ${instance.renderFooter(processed)}
    </div>
  `;
}
function toolbar(actions = [], hint = '') { return `<div class="toolbar">${actions.join('')} ${hint ? `<span class="muted">${hint}</span>` : ''}</div>`; }
function action(label, onclick, primary = false) { return `<button class="${primary ? 'primary' : ''}" onclick="${onclick}">${esc(label)}</button>`; }
function modal(title, content) {
  const host = document.createElement('div'); host.className = 'modal';
  host.innerHTML = `<section class="panel modal-panel"><div class="modal-title"><h2>${esc(title)}</h2><button class="icon-btn" aria-label="Close">${uiIcon('close', 16)}</button></div>${content}</section>`;
  host.onclick = event => { if (event.target === host) host.remove(); };
  host.querySelector('.icon-btn').onclick = () => host.remove();
  document.body.append(host); return host;
}
function formData(form) { return Object.fromEntries(new FormData(form)); }
function selectOptions(rows, valueKey, label) { return rows.map(row => `<option value="${esc(row[valueKey])}">${esc(label(row))}</option>`).join(''); }
async function getLookups() { if (!lookups) lookups = await api('/lookups'); return lookups; }

const navGroups = [
  ['Operations', [
    ['dashboard', 'Dashboard', 'dashboard.view'],
    ['attendance', 'Attendance', 'devices.manage'],
    ['calendar', 'Academic Calendar', 'devices.manage'],
    ['proxy', 'Proxy Classes', 'staff.manage'],
    ['tasks', 'Tasks & Bugs', 'dashboard.view'],
    ['assistant', 'AI Assistant', 'assistant.view'],
    ['reports', 'Reports', 'reports.view']
  ]],
  ['Academic', [
    ['students', 'Students', 'students.manage'],
    ['enrollments', 'Enrollments', 'enrollments.manage'],
    ['bills', 'Due Bills & Payments', 'billing.manage'],
    ['student-transactions', 'Student Accounts', 'billing.manage'],
    ['certificates', 'Certificates', 'certificates.manage'],
    ['routines', 'Class Routines', 'master_data.manage'],
    ['grades', 'Grades & Levels', 'master_data.manage'],
    ['courses', 'Courses', 'master_data.manage'],
    ['schools', 'Schools', 'master_data.manage']
  ]],
  ['People & Finance', [
    ['staff', 'Staff', 'staff.manage'],
    ['advances', 'Staff Advances', 'payroll.manage'],
    ['salary', 'Salary Payouts', 'payroll.manage'],
    ['finance', 'Finance', 'finance.manage'],
    ['transfers', 'Account Transfers', 'finance.manage']
  ]],
  ['Student Portal', [
    ['dashboard', 'Dashboard', 'portal.student'],
    ['student-profile', 'My Profile & Attendance', 'portal.student'],
    ['routines', 'Class Timetable', 'portal.student'],
    ['bills', 'My Fees & Bills', 'portal.student'],
    ['certificates', 'My Certificates', 'portal.student']
  ]],
  ['Teacher Portal', [
    ['dashboard', 'Dashboard', 'portal.staff'],
    ['teacher-proxy', 'Leave & Proxy', 'portal.staff'],
    ['teacher-classes', 'My Classes & Students', 'portal.staff'],
    ['teacher-attendance', 'My Attendance', 'portal.staff'],
    ['teacher-payments', 'Salary & Payments', 'portal.staff'],
    ['routines', 'Weekly Timetable', 'portal.staff']
  ]],
  ['Website CMS', [
    ['cms', 'Website CMS', 'cms.manage'],
    ['inquiries', 'Admission Leads', 'cms.manage']
  ]],
  ['Administration', [
    ['users', 'User Management', 'administration.manage'],
    ['company', 'Company Details', 'administration.manage'],
    ['settings', 'System & Automation', 'administration.manage']
  ]],
];

let isDarkMode = localStorage.getItem('tailadmin_dark') === 'true';

function toggleDarkMode() {
  isDarkMode = !isDarkMode;
  localStorage.setItem('tailadmin_dark', isDarkMode);
  applyTheme();
}

function applyTheme() {
  document.body.classList.toggle('dark', isDarkMode);
  document.documentElement.classList.toggle('dark', isDarkMode);
  const btn = document.querySelector('#themeToggleBtn');
  if (btn) {
    btn.innerHTML = isDarkMode
      ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
      : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`;
    btn.title = isDarkMode ? 'Switch to light mode' : 'Switch to dark mode';
  }
}

function toggleSidebar() {
  document.querySelector('.shell')?.classList.toggle('sidebar-open');
}

let collapsedGroups = new Set(JSON.parse(localStorage.getItem('tailadmin_collapsed_groups') || '[]'));

function toggleNavGroup(groupName) {
  if (collapsedGroups.has(groupName)) {
    collapsedGroups.delete(groupName);
  } else {
    collapsedGroups.add(groupName);
  }
  localStorage.setItem('tailadmin_collapsed_groups', JSON.stringify(Array.from(collapsedGroups)));
  const groupEl = document.querySelector(`.nav-group[data-group="${CSS.escape(groupName)}"]`);
  if (groupEl) {
    groupEl.classList.toggle('collapsed', collapsedGroups.has(groupName));
  }
}

function toggleUserDropdown(event) {
  if (event) {
    event.stopPropagation();
  }
  const pill = document.querySelector('#userPill');
  const menu = document.querySelector('#userDropdownMenu');
  if (!menu) return;
  const isOpen = menu.classList.contains('show');
  if (isOpen) {
    closeUserDropdown();
  } else {
    menu.classList.add('show');
    pill?.classList.add('open');
    pill?.setAttribute('aria-expanded', 'true');
  }
}

function closeUserDropdown() {
  const pill = document.querySelector('#userPill');
  const menu = document.querySelector('#userDropdownMenu');
  menu?.classList.remove('show');
  pill?.classList.remove('open');
  pill?.setAttribute('aria-expanded', 'false');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#userMenuWrapper')) {
    closeUserDropdown();
  }
});

function shell(title, subtitle, body) {
  applyTheme();
  const active = (location.hash.slice(1).split('?')[0]) || 'dashboard';
  const isTeacher = (me?.role === 'staff' || me?.role === 'teacher' || (me?.teacher_id && !has('administration.manage') && !has('students.manage')));
  const isStudent = me?.role === 'student';
  const navActive = active === 'student-profile' ? (isStudent ? 'student-profile' : 'students') : active;
  const navigation = navGroups.map(([group, pages]) => {
    if (isStudent && group !== 'Student Portal') return '';
    if (!isStudent && group === 'Student Portal') return '';
    if (isTeacher && group !== 'Teacher Portal') return '';
    if (!isTeacher && group === 'Teacher Portal') return '';
    const visible = pages.filter(([page, , permission]) => {
      if (page === 'assistant' && me?.role !== 'super_admin' && me?.role !== 'admin') return false;
      return has(permission);
    });
    if (!visible.length) return '';
    const containsActive = visible.some(([page]) => navActive === page);
    const isCollapsed = !containsActive && collapsedGroups.has(group);
    return `
      <div class="nav-group ${isCollapsed ? 'collapsed' : ''}" data-group="${esc(group)}">
        <div class="nav-group-title" onclick="toggleNavGroup('${esc(group)}')">
          <span>${esc(group)}</span>
          <svg class="group-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="nav-group-items">
          ${visible.map(([page, label]) => `
            <button class="nav ${navActive === page ? 'active' : ''}" onclick="go('${page}')">
              ${navIcons[page] || '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="8"/></svg>'}
              <span>${esc(label)}</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }).join('');

  const initials = (me?.display_name || me?.username || 'U')
    .split(/\s+/)
    .slice(0, 2)
    .map(p => p[0].toUpperCase())
    .join('');

  app.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="brand" onclick="go('dashboard')">
            <div class="brand-icon">E</div>
            <div class="brand-text">
              <b>ELH</b><span>Admin</span>
            </div>
          </div>
          <button class="sidebar-close-btn" onclick="toggleSidebar()" aria-label="Close sidebar">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div style="flex:1;overflow-y:auto;">
          ${navigation}
        </div>
        <div class="sidebar-bottom">
          <button class="nav" onclick="go('website')" style="color:var(--brand);font-weight:600;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span>Public Website</span>
          </button>
          <button class="nav" onclick="changePasswordModal()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
            <span>Change password</span>
          </button>
          <button class="nav" onclick="logout()" style="color:var(--danger);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            <span>Sign out</span>
          </button>
        </div>
      </aside>
      <main class="content">
        <header class="top">
          <div class="top-left">
            <button class="menu-toggle-btn" onclick="toggleSidebar()" aria-label="Open menu">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            </button>
            <div>
              <h1>${esc(title)}</h1>
              <p class="muted">${esc(subtitle)}</p>
            </div>
          </div>
          <div class="top-actions">
            <button class="btn" onclick="go('website')" style="font-size:12px;padding:6px 12px;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);" title="View Public Institute Website">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              <span>Website</span>
            </button>
            <button id="themeToggleBtn" class="theme-toggle-btn" onclick="toggleDarkMode()" aria-label="Toggle theme">
              ${isDarkMode
                ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
                : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`}
            </button>
            <div class="user-menu-wrapper" id="userMenuWrapper">
              <div class="user-pill" id="userPill" onclick="toggleUserDropdown(event)" tabindex="0" role="button" aria-haspopup="true" aria-expanded="false">
                <div class="user-avatar">${esc(initials)}</div>
                <div class="user-details">
                  <span class="user-name">${esc(me?.display_name || me?.username || 'User')}</span>
                  <span class="user-role">${esc((me?.role || '').replace('_', ' '))}</span>
                </div>
                <svg class="user-pill-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="user-dropdown-menu" id="userDropdownMenu">
                <div class="user-dropdown-header">
                  <b>${esc(me?.display_name || me?.username || 'User')}</b>
                  <span>@${esc(me?.username || '')}</span>
                  <span class="badge active">${esc((me?.role || '').replace('_', ' ').toUpperCase())}</span>
                </div>
                ${me?.student_id ? `
                  <button class="user-dropdown-item" onclick="closeUserDropdown();go('student-profile?id=${me.student_id}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    <span>My Student Profile</span>
                  </button>
                ` : ''}
                ${me?.teacher_id ? `
                  <button class="user-dropdown-item" onclick="closeUserDropdown();go('teacher-classes')">
                    ${uiIcon('teacher-classes', 16)}
                    <span>My Classes & Students</span>
                  </button>
                  <button class="user-dropdown-item" onclick="closeUserDropdown();go('teacher-attendance')">
                    ${uiIcon('teacher-attendance', 16)}
                    <span>My Attendance History</span>
                  </button>
                  <button class="user-dropdown-item" onclick="closeUserDropdown();go('teacher-payments')">
                    ${uiIcon('teacher-payments', 16)}
                    <span>Salary & Payments</span>
                  </button>
                ` : ''}
                ${has('administration.manage') ? `
                  <button class="user-dropdown-item" onclick="closeUserDropdown();go('users')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a5 5 0 00-5 5v3a5 5 0 0010 0V7a5 5 0 00-5-5z"/><path d="M17 14v1a5 5 0 01-10 0v-1M4 22a8 8 0 0116 0"/></svg>
                    <span>User Management</span>
                  </button>
                ` : ''}
                <button class="user-dropdown-item" onclick="closeUserDropdown();changePasswordModal()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  <span>Change Password</span>
                </button>
                <div class="user-dropdown-divider"></div>
                <button class="user-dropdown-item danger-item" onclick="closeUserDropdown();logout()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                  <span>Sign out</span>
                </button>
              </div>
            </div>
          </div>
        </header>
        ${body}
      </main>
    </div>
  `;
}

function csvDownload(filename, rows, columns) {
  const output = [columns.map(c => c.label), ...rows.map(row => columns.map(c => c.csv ? c.csv(row) : (c.render ? '' : row[c.key] ?? '')))];
  const text = output.map(row => row.map(value => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\n');
  const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' })); link.download = filename; link.click(); URL.revokeObjectURL(link.href);
}

async function openBillPaymentQrModal(billId) {
  try {
    const data = await api(`/bills/${billId}/qr`);
    if (!data.enabled) {
      alert('Digital QR payment is not configured yet. Please pay tuition fees at the counter.');
      return;
    }
    const content = `
      <div style="text-align:center;padding:8px 0;">
        <div style="display:inline-flex;padding:14px;background:#fff;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.1);margin-bottom:14px;justify-content:center;align-items:center;min-width:200px;min-height:200px;">
          ${data.qr_svg ? data.qr_svg : `<div style="padding:16px;background:#f8fafc;border-radius:8px;font-family:monospace;word-break:break-all;font-size:12px;max-width:280px;">${esc(data.payload)}</div>`}
        </div>
        <h3 style="margin:4px 0 2px;font-size:18px;color:var(--text);">${esc(data.merchant_name || 'Expert Learning Hub')}</h3>
        <p style="color:var(--brand);font-size:24px;font-weight:700;margin:6px 0;">Rs. ${money(data.amount)}</p>
        <div style="display:flex;justify-content:center;gap:16px;font-size:13px;color:var(--text-muted);margin-bottom:12px;">
          <span>Bill #: <b>${esc(data.bill_number)}</b></span>
          <span>Student: <b>${esc(data.student_name)}</b></span>
          <span>Gateway: <b>${esc(data.provider)}</b></span>
        </div>
        <p style="font-size:13px;color:var(--text-muted);max-width:380px;margin:0 auto 16px;">
          ${esc(data.instructions || 'Scan using Fonepay, eSewa, Khalti, or your Mobile Banking App.')}
        </p>
        <div class="form-actions" style="justify-content:center;">
          <button class="primary" onclick="this.closest('.modal').remove()">Done</button>
        </div>
      </div>
    `;
    modal(`Payment QR — ${esc(data.bill_number)}`, content);
  } catch (err) {
    showError(err);
  }
}

function renderStudentDashboard(data) {
  const student = data.student || {};
  const metrics = data.metrics || {};
  const enrollments = data.enrollments || [];
  const dueBills = data.due_bills || [];
  const rawTodayRoutine = data.today_routine || [];
  const sClass = String(student.class_name || '').trim().toLowerCase();
  const enrolledCids = new Set(enrollments.map(e => Number(e.course_id)).filter(Boolean));
  const todayRoutine = rawTodayRoutine.filter(r => {
    if (sClass) {
      const rClass = String(r.class_name || '').trim().toLowerCase();
      const isGeneral = !rClass || rClass === 'all';
      const isMatch = isGeneral || rClass === sClass || rClass === `grade ${sClass}` || sClass === `grade ${rClass}`;
      if (!isMatch) return false;
    }
    const rCourseId = r.course_id ? Number(r.course_id) : null;
    if (rCourseId && !enrolledCids.has(rCourseId)) return false;
    return true;
  });
  const certificates = data.certificates || [];

  const overdueAlerts = data.overdue_alerts || [];
  const overdueBillIds = new Set(overdueAlerts.map(a => a.bill_id));

  const attendanceBadge = metrics.today_present
    ? `<span class="badge active" style="font-size:12px;padding:3px 8px;">● Present</span>`
    : `<span class="badge" style="background:#fef3c7;color:#b45309;font-size:12px;padding:3px 8px;">○ Not Marked</span>`;

  const metricCards = [
    {
      label: 'Today’s Attendance',
      value: metrics.today_present ? 'Present' : 'Not Marked',
      sub: metrics.today_punches?.length ? `Punches: ${metrics.today_punches.join(', ')}` : `${metrics.attendance_month_days || 0} days present this month`,
      badge: attendanceBadge,
      icon: uiIcon('attendance', 22)
    },
    {
      label: 'Outstanding Dues',
      value: `Rs. ${money(metrics.outstanding)}`,
      sub: overdueAlerts.length ? `${overdueAlerts.length} overdue bill(s) past due date` : (metrics.outstanding > 0 ? `${dueBills.length} pending bill(s)` : 'All accounts settled'),
      subClass: (overdueAlerts.length || metrics.outstanding > 0) ? 'due-alert' : 'paid-ok',
      icon: uiIcon('bills', 22)
    },
    {
      label: 'Active Enrollments',
      value: `${metrics.enrollments ?? enrollments.length} Active`,
      sub: `Class: ${esc(student.class_name || 'Standard')}`,
      icon: uiIcon('enrollments', 22)
    },
    {
      label: 'Certificates Earned',
      value: `${metrics.certificates ?? certificates.length}`,
      sub: 'Issued completion certificates',
      icon: uiIcon('certificates', 22)
    }
  ];

  const cardsHtml = `
    <div class="cards">
      ${metricCards.map(c => `
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span>${esc(c.label)}</span>
            <div class="card-icon">
              ${c.icon}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
            <b style="font-size:22px;">${esc(c.value)}</b>
            ${c.badge || ''}
          </div>
          <small class="${c.subClass || 'muted'}">${esc(c.sub)}</small>
        </div>
      `).join('')}
    </div>
  `;

  const heroHtml = `
    <div class="panel" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;background:linear-gradient(135deg, rgba(70,95,255,0.06), rgba(70,95,255,0.02));border:1px solid rgba(70,95,255,0.18);border-radius:12px;margin-bottom:18px;">
      <div style="display:flex;align-items:center;gap:16px;">
        <div style="width:52px;height:52px;border-radius:50%;background:var(--brand);color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;">
          ${esc((student.student_name || 'ST').slice(0, 2).toUpperCase())}
        </div>
        <div>
          <h2 style="margin:0 0 4px 0;font-size:20px;">Welcome back, ${esc(student.student_name || 'Student')}</h2>
          <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:13px;color:var(--text-muted);">
            ${student.id ? `<span>Student ID: <b>#${esc(student.id)}</b></span>` : ''}
            ${student.class_name ? `<span>Class: <b>${esc(student.class_name)}</b></span>` : ''}
            ${student.school_name ? `<span>School: <b>${esc(student.school_name)}</b></span>` : ''}
            ${student.contact ? `<span>Contact: <b>${esc(student.contact)}</b></span>` : ''}
          </div>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="primary" onclick="go('student-profile')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('student-profile', 15)}My Full Profile & Attendance</button>
        ${student.id ? `<button onclick="downloadStudentProfilePdf(${student.id})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('print', 15)}Download Dossier PDF</button>` : ''}
      </div>
    </div>
  `;

  const overdueBanner = overdueAlerts.length ? `
    <div style="background:#fef2f2;border:1px solid #f87171;border-radius:10px;padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:24px;">⚠️</span>
        <div>
          <b style="color:#b91c1c;font-size:15px;">Payment Overdue Alert: You have ${overdueAlerts.length} bill(s) past the due date</b>
          <div style="font-size:13px;color:#7f1d1d;margin-top:2px;">
            Total overdue: <b>Rs. ${money(overdueAlerts.reduce((sum, a) => sum + (a.balance || 0), 0))}</b>. Please settle your fee balance or pay online via QR to avoid account holds.
          </div>
        </div>
      </div>
      <button class="primary" onclick="document.querySelector('#studentBillsSection')?.scrollIntoView({behavior:'smooth'})" style="background:#dc2626;border-color:#dc2626;">View & Pay Overdue</button>
    </div>
  ` : '';

  const routineCols = [
    { key: 'period_label', label: 'Period' },
    { key: 'time', label: 'Time', render: r => `${r.start_time || ''} - ${r.end_time || ''}` },
    { key: 'subject_name', label: 'Subject' },
    { key: 'course_name', label: 'Course' },
    { key: 'teacher_name', label: 'Teacher / Instructor' },
  ];
  const routineHtml = `
    <section class="panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <h2 style="margin:0;display:flex;align-items:center;gap:8px;">
          ${uiIcon('calendar', 18)}Today’s Class Schedule (${esc(data.today_weekday || 'Today')})
          ${student.class_name ? `<span class="badge" style="background:#e0f2fe;color:#0369a1;font-size:11px;font-weight:600;padding:2px 8px;">Class: ${esc(student.class_name)}</span>` : ''}
        </h2>
        <button onclick="go('routines')" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">Full Weekly Timetable ${uiIcon('arrowRight', 12)}</button>
      </div>
      ${todayRoutine.length
        ? table(todayRoutine, routineCols)
        : `<p class="muted" style="padding:16px 0;margin:0;">No classes scheduled for today (${esc(data.today_weekday || 'Today')}). Check the <a href="javascript:void(0)" onclick="go('routines')">weekly timetable</a> for upcoming classes.</p>`
      }
    </section>
  `;

  const billCols = [
    { key: 'bill_number', label: 'Bill #' },
    { key: 'course_name', label: 'Course' },
    { key: 'billing_period', label: 'Period' },
    { key: 'due_date', label: 'Due Date', render: r => overdueBillIds.has(r.id) ? `<b>${esc(r.due_date)}</b> <span class="badge" style="background:#fee2e2;color:#b91c1c;font-size:11px;font-weight:700;">Overdue</span>` : esc(r.due_date) },
    { key: 'total_amount', label: 'Total', render: r => `Rs. ${money(r.total_amount)}` },
    { key: 'paid_amount', label: 'Paid', render: r => `Rs. ${money(r.paid_amount)}` },
    { key: 'balance', label: 'Balance Due', render: r => `<b class="${r.balance > 0 ? 'due-alert' : 'paid-ok'}">Rs. ${money(r.balance)}</b>` },
    { key: 'status', label: 'Status', render: r => `<span class="badge ${r.status === 'Paid' ? 'active' : (r.status === 'Partial' ? 'partial' : 'inactive')}">${esc(r.status)}</span>` },
    { key: 'action', label: 'Payment', render: r => r.balance > 0 ? `<button class="primary" style="padding:4px 8px;font-size:12px;" onclick="openBillPaymentQrModal(${r.id})">Pay via QR</button>` : `<span style="color:var(--success);font-weight:600;display:inline-flex;align-items:center;gap:4px;">${uiIcon('check', 13)}Settled</span>` }
  ];
  const billsHtml = `
    <section class="panel" id="studentBillsSection">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h2 style="margin:0;display:flex;align-items:center;gap:8px;">${uiIcon('bills', 18)}Pending & Recent Due Bills</h2>
        <button onclick="go('bills')" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">View All Bills & Receipts ${uiIcon('arrowRight', 12)}</button>
      </div>
      ${dueBills.length
        ? table(dueBills, billCols)
        : `<p class="muted" style="padding:16px 0;margin:0;">No outstanding dues or pending bills found. You are all settled!</p>`
      }
    </section>
  `;

  const enrollCols = [
    { key: 'course_name', label: 'Course' },
    { key: 'level', label: 'Level' },
    { key: 'instructor_name', label: 'Instructor' },
    { key: 'start_date', label: 'Start Date' },
    { key: 'monthly_fee', label: 'Monthly Fee', render: r => `Rs. ${money(r.monthly_fee)}` },
    { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status)}</span>` },
  ];
  const enrollHtml = `
    <section class="panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h2 style="margin:0;display:flex;align-items:center;gap:8px;">${uiIcon('courses', 18)}My Enrolled Courses</h2>
        <button onclick="go('student-profile')" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">View Course Details ${uiIcon('arrowRight', 12)}</button>
      </div>
      ${enrollments.length
        ? table(enrollments, enrollCols)
        : `<p class="muted" style="padding:16px 0;margin:0;">You are not currently enrolled in any active courses.</p>`
      }
    </section>
  `;

  const proxyNotifs = data.proxy_notifications || [];
  const proxyBanner = proxyNotifs.length ? `
    <div style="background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #f59e0b;border-radius:10px;padding:14px 18px;margin-bottom:18px;">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:10px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="font-size:22px;">📢</span>
          <div>
            <b style="color:#92400e;font-size:15px;">Class Schedule Notice · Substitute / Proxy Faculty</b>
            <div style="color:#b45309;font-size:13px;margin-top:2px;">Special notice regarding substitute faculty conducting your scheduled classes</div>
          </div>
        </div>
        <span class="badge" style="background:#fef3c7;color:#92400e;font-weight:700;border:1px solid #fcd34d;">${proxyNotifs.length} Notice(s)</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        ${proxyNotifs.map(n => `
          <div style="background:#ffffff;border:1px solid #fed7aa;border-radius:8px;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
              <span class="badge active" style="font-weight:700;font-size:11px;">📅 ${esc(n.class_date)}</span>
              <b style="color:#0f172a;font-size:14px;">${esc(n.subject_name || 'Class')}</b>
              <span class="badge" style="background:#e0f2fe;color:#0369a1;font-size:11px;">${esc(n.period_label || '')} (${esc(n.start_time || '')} - ${esc(n.end_time || '')})</span>
              <span style="font-size:13px;color:#475569;">
                Substitute Teacher: <b style="color:#166534;background:#dcfce7;padding:2px 8px;border-radius:4px;">${esc(n.proxy_teacher_name)}</b>
                <span class="muted" style="font-size:12px;margin-left:4px;">(Regular: ${esc(n.original_teacher_name)})</span>
              </span>
            </div>
            ${!n.read_at ? `<button onclick="markProxyNotifRead(${n.notification_id}, this)" style="font-size:11px;padding:3px 8px;">Mark as Read</button>` : `<span class="muted" style="font-size:11px;">✓ Seen</span>`}
          </div>
        `).join('')}
      </div>
    </div>
  ` : '';

  shell('Student Dashboard', 'Personal academic overview, attendance, and fee status', `${heroHtml}${proxyBanner}${overdueBanner}${cardsHtml}${routineHtml}${billsHtml}${enrollHtml}`);
}

async function downloadPayslipPdf(salaryId) {
  try {
    const res = await fetch(`/api/salary/${salaryId}/payslip/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
    if (!res.ok) throw new Error('Failed to generate payslip PDF');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `payslip_${salaryId}.pdf`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err);
  }
}

function switchTeacherRoutineDay(dayName) {
  window._selectedTeacherDay = dayName;
  document.querySelectorAll('.teacher-day-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.day === dayName);
  });
  const container = document.querySelector('#teacherRoutineDayContent');
  if (!container || !window._teacherWeeklyRoutines) return;
  const filtered = dayName === 'all'
    ? window._teacherWeeklyRoutines
    : window._teacherWeeklyRoutines.filter(r => (r.day_of_week || '').toLowerCase() === dayName.toLowerCase());

  const cols = [
    { key: 'day_of_week', label: 'Day' },
    { key: 'period_label', label: 'Period' },
    { key: 'time', label: 'Time', render: r => `${r.start_time || ''} - ${r.end_time || ''}` },
    { key: 'display_class_name', label: 'Class / Grade', render: r => `<b>${esc(r.display_class_name || r.class_name || '-')}</b>` },
    { key: 'subject_name', label: 'Subject' },
    { key: 'teacher_name', label: 'Teacher / Faculty', render: r => esc(r.teacher_name || '-') },
    { key: 'course_name', label: 'Course' },
    { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status || 'Active')}</span>` }
  ];

  container.innerHTML = filtered.length
    ? table(filtered, cols)
    : `<p class="muted" style="padding:14px 0;margin:0;">No classes scheduled for ${esc(dayName === 'all' ? 'the week' : dayName)}.</p>`;
}

function filterTeacherAssignedStudents(className) {
  window._selectedTeacherClass = className;
  document.querySelectorAll('.teacher-class-pill').forEach(b => {
    b.classList.toggle('active', b.dataset.class === className);
  });
  renderTeacherStudentsTable();
}

function searchTeacherStudents(query) {
  window._teacherStudentQuery = (query || '').trim().toLowerCase();
  renderTeacherStudentsTable();
}

function renderTeacherStudentsTable() {
  const container = document.querySelector('#teacherStudentsTableContainer');
  if (!container || !window._teacherAssignedStudents) return;
  const selectedClass = window._selectedTeacherClass || 'all';
  const query = window._teacherStudentQuery || '';

  let filtered = window._teacherAssignedStudents;
  if (selectedClass !== 'all') {
    filtered = filtered.filter(s => (s.display_class_name || s.class_name || '').toLowerCase() === selectedClass.toLowerCase());
  }
  if (query) {
    filtered = filtered.filter(s =>
      (s.student_name || '').toLowerCase().includes(query) ||
      String(s.id || '').includes(query) ||
      (s.contact || '').toLowerCase().includes(query) ||
      (s.parent_name || '').toLowerCase().includes(query)
    );
  }

  const countBadge = document.querySelector('#teacherStudentCountBadge');
  if (countBadge) countBadge.textContent = `${filtered.length} shown`;

  const cols = [
    { key: 'id', label: 'Student ID', render: s => `<b>#${esc(s.id)}</b>` },
    { key: 'student_name', label: 'Student Name', render: s => `<b>${esc(s.student_name)}</b>` },
    { key: 'display_class_name', label: 'Class / Level', render: s => `<span class="badge" style="background:#e0f2fe;color:#0369a1;font-weight:600;">${esc(s.display_class_name || s.class_name || '-')}</span>` },
    { key: 'school_name', label: 'School' },
    { key: 'contact', label: 'Contact', render: s => s.contact ? `<a href="tel:${esc(s.contact)}">${esc(s.contact)}</a>` : '-' },
    { key: 'parent_name', label: 'Parent / Guardian' },
    { key: 'status', label: 'Status', render: s => `<span class="badge ${s.status === 'Active' ? 'active' : 'inactive'}">${esc(s.status || 'Active')}</span>` }
  ];

  container.innerHTML = filtered.length
    ? table(filtered, cols)
    : `<p class="muted" style="padding:14px 0;margin:0;">No students match the selected filter or search query.</p>`;
}

function switchTeacherPaymentTab(tabId) {
  document.querySelectorAll('.teacher-pay-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabId);
  });
  document.querySelectorAll('.teacher-pay-pane').forEach(p => {
    const isActive = p.id === `teacher-pay-${tabId}`;
    p.style.display = isActive ? 'block' : 'none';
  });
}

function renderTeacherDashboard(data) {
  const teacher = data.teacher || {};
  const metrics = data.metrics || {};
  const weeklyRoutines = data.weekly_routines || [];
  const todayRoutines = data.today_routines || [];
  const assignedStudents = data.assigned_students || [];
  const classDist = data.class_distribution || {};
  const salaryPayouts = data.salary_payouts || [];
  const advances = data.advances || [];
  const statement = data.statement || [];
  const paySummary = data.payment_summary || {};
  const attHistory = data.attendance_history || {};
  const dailyLogs = attHistory.daily_logs || [];
  const tasks = data.tasks || [];

  window._teacherWeeklyRoutines = weeklyRoutines;
  window._teacherAssignedStudents = assignedStudents;
  window._selectedTeacherDay = 'all';
  window._selectedTeacherClass = 'all';
  window._teacherStudentQuery = '';

  const initials = (teacher.teacher_name || 'TR')
    .split(/\s+/)
    .slice(0, 2)
    .map(p => p[0].toUpperCase())
    .join('') || 'TR';

  // Hero Section
  const heroHtml = `
    <div class="panel" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;background:linear-gradient(135deg, rgba(70,95,255,0.06), rgba(70,95,255,0.02));border:1px solid rgba(70,95,255,0.18);border-radius:12px;margin-bottom:18px;">
      <div style="display:flex;align-items:center;gap:16px;">
        <div style="width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg, #4f46e5, #3b82f6);color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;box-shadow:0 4px 10px rgba(79,70,229,0.25);">
          ${esc(initials)}
        </div>
        <div>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <h2 style="margin:0;font-size:20px;">Welcome back, ${esc(teacher.teacher_name || 'Teacher')}</h2>
            <span class="badge active" style="font-size:11px;padding:3px 8px;">${esc(teacher.staff_type || 'Teaching')} Staff</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--text-muted);margin-top:5px;">
            ${teacher.id ? `<span>Staff ID: <b>#${esc(teacher.id)}</b></span>` : ''}
            ${teacher.subject ? `<span>Subject: <b>${esc(teacher.subject)}</b></span>` : ''}
            ${teacher.qualification ? `<span>Qualification: <b>${esc(teacher.qualification)}</b></span>` : ''}
            ${teacher.contact ? `<span>Contact: <b>${esc(teacher.contact)}</b></span>` : ''}
            ${teacher.salary_type ? `<span>Pay Scheme: <b>${esc(teacher.salary_type)}</b></span>` : ''}
            ${teacher.joined_date ? `<span>Joined (BS): <b>${esc(teacher.joined_date)}</b></span>` : ''}
          </div>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="primary" onclick="proxyLeaveRequestModal()" style="display:inline-flex;align-items:center;gap:6px;background:#ea580c;border-color:#c2410c;">${uiIcon('plus', 14)}Request Leave / Proxy</button>
        <button onclick="document.querySelector('#teacherProxySection')?.scrollIntoView({behavior:'smooth'})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('proxy', 14)}Proxy Classes ${metrics.pending_proxy_count ? `<span class="badge" style="background:#fee2e2;color:#b91c1c;padding:1px 6px;font-weight:700;font-size:10px;">${metrics.pending_proxy_count} NEW</span>` : ''}</button>
        <button onclick="downloadRoutinePdf()" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('print', 15)}Timetable PDF</button>
        <button onclick="document.querySelector('#teacherScheduleSection')?.scrollIntoView({behavior:'smooth'})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('routines', 15)}My Schedule</button>
        <button onclick="document.querySelector('#teacherPaymentsSection')?.scrollIntoView({behavior:'smooth'})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('salary', 15)}Payments</button>
      </div>
    </div>
  `;

  const pendingProxyAlertHtml = metrics.pending_proxy_count > 0 ? `
    <div class="panel" style="background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #f59e0b;padding:14px 18px;margin-bottom:18px;border-radius:10px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:24px;">🔔</span>
        <div>
          <b style="color:#92400e;font-size:15px;">Pending Proxy Class Requests Awaiting Your Response</b>
          <div style="color:#b45309;font-size:13px;margin-top:2px;">You have <b>${metrics.pending_proxy_count}</b> substitute class assignment(s) assigned to you. Please accept or decline so students can be notified.</div>
        </div>
      </div>
      <button class="primary" onclick="document.querySelector('#teacherProxyAssignments')?.scrollIntoView({behavior:'smooth'})" style="font-size:12px;padding:6px 14px;background:#d97706;border-color:#b45309;">Review Assignments</button>
    </div>
  ` : '';

  const todayAttBadge = metrics.today_present
    ? `<span class="badge active" style="font-size:12px;padding:3px 8px;">● Present</span>`
    : `<span class="badge" style="background:#fef3c7;color:#b45309;font-size:12px;padding:3px 8px;">○ Not Marked</span>`;

  const payBadge = paySummary.current_month_paid
    ? `<span class="badge active" style="font-size:11px;padding:2px 6px;">Month Paid</span>`
    : `<span class="badge" style="background:#fef3c7;color:#b45309;font-size:11px;padding:2px 6px;">Month Due</span>`;

  const metricCards = [
    {
      label: 'Classes This Week',
      value: `${metrics.total_classes_week ?? weeklyRoutines.length} Classes`,
      sub: `${metrics.today_classes_count ?? todayRoutines.length} class(es) scheduled today (${esc(data.today_weekday || 'Today')})`,
      badge: `<span class="badge active" style="font-size:11px;padding:2px 6px;">${esc(data.today_weekday || 'Today')}</span>`,
      icon: uiIcon('routines', 22),
      onClick: "document.querySelector('#teacherScheduleSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'Assigned Students',
      value: `${metrics.total_students_assigned ?? assignedStudents.length} Students`,
      sub: `Across ${Object.keys(classDist).length} class level(s) taught`,
      badge: `<span class="badge" style="background:#e0f2fe;color:#0369a1;font-size:11px;padding:2px 6px;">${Object.keys(classDist).length} Classes</span>`,
      icon: uiIcon('students', 22),
      onClick: "document.querySelector('#teacherStudentsSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'Payments & Pending',
      value: `Rs. ${money(paySummary.pending_salary > 0 ? paySummary.pending_salary : paySummary.total_salary_paid)}`,
      sub: paySummary.pending_salary > 0
        ? `Pending: Rs. ${money(paySummary.pending_salary)} · Adv: Rs. ${money(paySummary.pending_advance)}`
        : `Total Paid: Rs. ${money(paySummary.total_salary_paid)} · Adv: Rs. ${money(paySummary.pending_advance)}`,
      subClass: (paySummary.pending_salary > 0 || paySummary.pending_advance > 0) ? 'due-alert' : 'paid-ok',
      badge: payBadge,
      icon: uiIcon('salary', 22),
      onClick: "document.querySelector('#teacherPaymentsSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'My Attendance',
      value: `${metrics.month_days_present ?? attHistory.month_days ?? 0} Days Present`,
      sub: metrics.today_present
        ? `Today: ${metrics.today_punches?.join(', ') || 'Present'} · ${metrics.month_hours_worked || 0} hrs this month`
        : `Not punched today · ${metrics.month_hours_worked || 0} hrs this month`,
      badge: todayAttBadge,
      icon: uiIcon('attendance', 22),
      onClick: "document.querySelector('#teacherAttendanceSection')?.scrollIntoView({behavior:'smooth'})"
    }
  ];

  const cardsHtml = `
    <div class="cards" style="margin-bottom:20px;">
      ${metricCards.map(c => `
        <div class="card" onclick="${c.onClick}" style="cursor:pointer;" title="Click to view section">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span>${esc(c.label)}</span>
            <div class="card-icon">${c.icon}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
            <b style="font-size:22px;">${esc(c.value)}</b>
            ${c.badge || ''}
          </div>
          <small class="${c.subClass || 'muted'}">${esc(c.sub)}</small>
        </div>
      `).join('')}
    </div>
  `;

  // SECTION 1: Total Classes in this week & Today's Schedule
  const daysOfWeek = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const todayWeekday = data.today_weekday || '';
  const dayTabsHtml = `
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
      <button type="button" class="btn teacher-day-tab active" data-day="all" onclick="switchTeacherRoutineDay('all')" style="font-size:12px;padding:4px 10px;">All Days (${weeklyRoutines.length})</button>
      ${daysOfWeek.map(d => {
        const count = weeklyRoutines.filter(r => (r.day_of_week || '').toLowerCase() === d.toLowerCase()).length;
        const isToday = todayWeekday.toLowerCase() === d.toLowerCase();
        return `
          <button type="button" class="btn teacher-day-tab" data-day="${d}" onclick="switchTeacherRoutineDay('${d}')" style="font-size:12px;padding:4px 10px;${isToday ? 'font-weight:700;border-color:var(--brand);' : ''}">
            ${d} (${count}) ${isToday ? '<span class="badge active" style="font-size:10px;padding:1px 5px;margin-left:4px;">Today</span>' : ''}
          </button>
        `;
      }).join('')}
    </div>
  `;

  const todayCardsHtml = todayRoutines.map(r => `
    <div style="background:#ffffff;border:1px solid #bbf7d0;border-left:4px solid #16a34a;border-radius:8px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
        <div style="background:#ecfdf5;color:#15803d;padding:6px 12px;border-radius:6px;font-weight:700;font-size:13px;white-space:nowrap;border:1px solid #bbf7d0;">
          ${esc(r.period_label || ('Period ' + r.period_number))}
        </div>
        <div>
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <b style="font-size:15px;color:#0f172a;">${esc(r.subject_name || 'Class')}</b>
            <span class="badge" style="background:#e0f2fe;color:#0369a1;font-weight:600;font-size:11px;">${esc(r.display_class_name || r.class_name || '-')}</span>
            ${r.course_name ? `<span class="badge" style="background:#f1f5f9;color:#475569;font-size:11px;">${esc(r.course_name)}</span>` : ''}
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;display:flex;gap:14px;flex-wrap:wrap;">
            <span>⏰ Time: <b>${esc(r.start_time || '')} - ${esc(r.end_time || '')}</b></span>
            ${r.teacher_name ? `<span>👤 Teacher: <b>${esc(r.teacher_name)}</b></span>` : ''}
          </div>
        </div>
      </div>
      <div>
        <span class="badge active" style="font-size:12px;padding:3px 8px;">Active</span>
      </div>
    </div>
  `).join('');

  const scheduleHtml = `
    <section class="panel" id="teacherScheduleSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('routines', 20)}Weekly Class Timetable & Schedule
            <span class="badge active" style="font-size:12px;font-weight:700;">${weeklyRoutines.length} Classes This Week</span>
          </h2>
          <small class="muted">Classes scheduled for this week under the active academic timetable routine (${esc(data.active_plan_name || 'Active Plan')})</small>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="primary" onclick="downloadRoutinePdf()" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">${uiIcon('print', 14)}Download Timetable PDF</button>
          <button onclick="go('routines')" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">Full Routine View ${uiIcon('arrowRight', 12)}</button>
        </div>
      </div>

      ${todayRoutines.length ? `
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 18px;margin-bottom:18px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#16a34a;"></span>
              <b style="color:#166534;font-size:15px;">Today’s Classes (${esc(todayWeekday || 'Today')} - ${todayRoutines.length} scheduled)</b>
            </div>
            <span class="badge active" style="font-size:11px;padding:3px 8px;">Running Today</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px;">
            ${todayCardsHtml}
          </div>
        </div>
      ` : `
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:16px;color:var(--text-muted);font-size:13px;display:flex;align-items:center;gap:8px;">
          <span>ℹ️</span>
          <span>No classes scheduled for you today (${esc(todayWeekday || 'Today')}). Total ${weeklyRoutines.length} class(es) scheduled throughout the week.</span>
        </div>
      `}

      <h3 style="margin:12px 0 8px 0;font-size:14px;color:var(--text-muted);">Weekly Timetable by Day:</h3>
      ${dayTabsHtml}
      <div id="teacherRoutineDayContent">
        ${weeklyRoutines.length ? table(weeklyRoutines, [
          { key: 'day_of_week', label: 'Day' },
          { key: 'period_label', label: 'Period' },
          { key: 'time', label: 'Time', render: r => `${r.start_time || ''} - ${r.end_time || ''}` },
          { key: 'display_class_name', label: 'Class / Grade', render: r => `<b>${esc(r.display_class_name || r.class_name || '-')}</b>` },
          { key: 'subject_name', label: 'Subject' },
          { key: 'teacher_name', label: 'Teacher / Faculty', render: r => esc(r.teacher_name || '-') },
          { key: 'course_name', label: 'Course' },
          { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status || 'Active')}</span>` }
        ]) : '<p class="muted">No class routine periods currently assigned to you.</p>'}
      </div>
    </section>
  `;

  // SECTION 2: Students Assigned in Class
  const classPillsHtml = `
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
      <button type="button" class="btn teacher-class-pill active" data-class="all" onclick="filterTeacherAssignedStudents('all')" style="font-size:12px;padding:4px 10px;">All Classes (${assignedStudents.length})</button>
      ${Object.entries(classDist).map(([cName, cnt]) => `
        <button type="button" class="btn teacher-class-pill" data-class="${esc(cName)}" onclick="filterTeacherAssignedStudents('${esc(cName)}')" style="font-size:12px;padding:4px 10px;">
          ${esc(cName)} (${cnt})
        </button>
      `).join('')}
    </div>
  `;

  const studentsHtml = `
    <section class="panel" id="teacherStudentsSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('students', 20)}Students Assigned in My Classes
            <span class="badge" id="teacherStudentCountBadge" style="background:#e0f2fe;color:#0369a1;font-size:12px;font-weight:700;">${assignedStudents.length} Students Total</span>
          </h2>
          <small class="muted">Active students enrolled in class levels and courses taught by you</small>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="text" placeholder="Search assigned students..." oninput="searchTeacherStudents(this.value)" style="padding:5px 10px;font-size:13px;width:220px;border-radius:6px;border:1px solid var(--border);">
        </div>
      </div>

      ${classPillsHtml}
      <div id="teacherStudentsTableContainer">
        ${assignedStudents.length ? table(assignedStudents, [
          { key: 'id', label: 'Student ID', render: s => `<b>#${esc(s.id)}</b>` },
          { key: 'student_name', label: 'Student Name', render: s => `<b>${esc(s.student_name)}</b>` },
          { key: 'display_class_name', label: 'Class / Level', render: s => `<span class="badge" style="background:#e0f2fe;color:#0369a1;font-weight:600;">${esc(s.display_class_name || s.class_name || '-')}</span>` },
          { key: 'school_name', label: 'School' },
          { key: 'contact', label: 'Contact', render: s => s.contact ? `<a href="tel:${esc(s.contact)}">${esc(s.contact)}</a>` : '-' },
          { key: 'parent_name', label: 'Parent / Guardian' },
          { key: 'status', label: 'Status', render: s => `<span class="badge ${s.status === 'Active' ? 'active' : 'inactive'}">${esc(s.status || 'Active')}</span>` }
        ]) : '<p class="muted">No students currently assigned to your classes.</p>'}
      </div>
    </section>
  `;

  // SECTION 3: Payment History, Advance and Other Payments & Pending Payment
  const paySubCardsHtml = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:12px;margin-bottom:16px;">
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;">
        <span style="font-size:12px;color:var(--text-muted);display:block;font-weight:600;">TOTAL SALARY PAID</span>
        <b style="font-size:20px;color:#0f172a;">Rs. ${money(paySummary.total_salary_paid)}</b>
        <small class="muted" style="display:block;margin-top:2px;">Net payouts received to date</small>
      </div>
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 14px;">
        <span style="font-size:12px;color:#15803d;display:block;font-weight:600;">OTHER PAYMENTS</span>
        <b style="font-size:20px;color:#166534;">Rs. ${money(paySummary.total_other_payments)}</b>
        <small style="color:#166534;display:block;margin-top:2px;">Bonus: Rs. ${money(paySummary.total_bonus)} · Allow.: Rs. ${money(paySummary.total_allowance)} · Extra: Rs. ${money(paySummary.total_extra_payment)}</small>
      </div>
      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 14px;">
        <span style="font-size:12px;color:#b45309;display:block;font-weight:600;">STAFF ADVANCES</span>
        <b style="font-size:20px;color:#92400e;">Rs. ${money(paySummary.total_advances_taken)}</b>
        <small style="color:#92400e;display:block;margin-top:2px;">Recovered: Rs. ${money(paySummary.total_advances_recovered)} | Pending: <b>Rs. ${money(paySummary.pending_advance)}</b></small>
      </div>
      <div style="background:${paySummary.pending_salary > 0 ? '#fef2f2;border:1px solid #fecaca;' : '#f0fdf4;border:1px solid #bbf7d0;'};border-radius:8px;padding:12px 14px;">
        <span style="font-size:12px;color:${paySummary.pending_salary > 0 ? '#b91c1c' : '#15803d'};display:block;font-weight:600;">PENDING PAYMENT (${esc(paySummary.current_month || 'Current')})</span>
        <b style="font-size:20px;color:${paySummary.pending_salary > 0 ? '#dc2626' : '#166534'};">
          ${paySummary.pending_salary > 0 ? `Rs. ${money(paySummary.pending_salary)}` : 'Rs. 0.00 (Settled)'}
        </b>
        <small style="color:${paySummary.pending_salary > 0 ? '#991b1b' : '#166534'};display:block;margin-top:2px;">
          ${paySummary.current_month_paid ? 'Current month salary already paid' : 'Current month salary pending payout'}
        </small>
      </div>
    </div>
  `;

  const salaryCols = [
    { key: 'salary_month', label: 'Salary Month', render: r => `<b>${esc(r.salary_month)}</b>` },
    { key: 'basic_salary', label: 'Basic Salary', render: r => `Rs. ${money(r.basic_salary)}` },
    {
      key: 'other_payments',
      label: 'Other Payments',
      render: r => {
        const extra = r.extra_payment || 0;
        const bonus = r.bonus || 0;
        const allow = r.allowance || 0;
        const sum = extra + bonus + allow;
        return sum > 0
          ? `<b>Rs. ${money(sum)}</b> <small class="muted" style="display:block;font-size:11px;">(Bonus: ${money(bonus)}, Allow: ${money(allow)}, Extra: ${money(extra)})</small>`
          : 'Rs. 0.00';
      }
    },
    { key: 'advance_deduction', label: 'Advance Ded.', render: r => r.advance_deduction > 0 ? `<span style="color:#b91c1c;">-Rs. ${money(r.advance_deduction)}</span>` : 'Rs. 0.00' },
    { key: 'net_salary', label: 'Net Paid', render: r => `<b style="color:var(--success);font-size:14px;">Rs. ${money(r.net_salary)}</b>` },
    { key: 'payment_date', label: 'Payment Date' },
    { key: 'voucher_no', label: 'Voucher / Ref', render: r => esc(r.voucher_no || '-') },
    { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status || 'Paid')}</span>` },
    {
      key: 'action',
      label: 'Payslip',
      render: r => `<button class="primary" style="padding:3px 8px;font-size:11px;" onclick="downloadPayslipPdf(${r.id})">${uiIcon('print', 12)} PDF Payslip</button>`
    }
  ];

  const advanceCols = [
    { key: 'advance_date', label: 'Advance Date', render: r => `<b>${esc(r.advance_date)}</b>` },
    { key: 'amount', label: 'Advance Amount', render: r => `<b>Rs. ${money(r.amount)}</b>` },
    { key: 'recovered_amount', label: 'Recovered', render: r => `Rs. ${money(r.recovered_amount)}` },
    { key: 'balance', label: 'Remaining / Pending', render: r => `<b class="${r.balance > 0 ? 'due-alert' : 'paid-ok'}">Rs. ${money(r.balance)}</b>` },
    { key: 'monthly_deduction', label: 'Monthly Ded.', render: r => r.monthly_deduction > 0 ? `Rs. ${money(r.monthly_deduction)}` : '-' },
    { key: 'recovery_method', label: 'Recovery Method', render: r => esc(r.recovery_method || 'Salary Deduction') },
    { key: 'status', label: 'Status', render: r => `<span class="badge ${r.status === 'Fully Recovered' ? 'active' : (r.status === 'Partially Recovered' ? 'partial' : 'inactive')}">${esc(r.status)}</span>` },
    { key: 'reference_no', label: 'Ref / Remarks', render: r => esc(r.reference_no || r.remarks || '-') }
  ];

  const statementCols = [
    { key: 'transaction_date', label: 'Date' },
    { key: 'transaction_type', label: 'Transaction Type', render: r => `<b>${esc(r.transaction_type)}</b>` },
    { key: 'amount', label: 'Amount', render: r => `<b>Rs. ${money(r.amount)}</b>` },
    { key: 'paid_from', label: 'Account', render: r => esc(r.paid_from || '-') },
    { key: 'particular', label: 'Particulars', render: r => esc(r.particular || '-') },
    { key: 'reference_no', label: 'Ref #', render: r => esc(r.reference_no || '-') }
  ];

  const paymentsHtml = `
    <section class="panel" id="teacherPaymentsSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('salary', 20)}Salary, Advances & Payment History
          </h2>
          <small class="muted">History of salary payouts, allowances, bonuses, advances, and pending balance</small>
        </div>
        <div style="display:flex;gap:6px;">
          <button type="button" class="btn teacher-pay-tab active" data-tab="salary" onclick="switchTeacherPaymentTab('salary')" style="font-size:12px;padding:4px 10px;">Salary Payouts (${salaryPayouts.length})</button>
          <button type="button" class="btn teacher-pay-tab" data-tab="advances" onclick="switchTeacherPaymentTab('advances')" style="font-size:12px;padding:4px 10px;">Advances (${advances.length})</button>
          <button type="button" class="btn teacher-pay-tab" data-tab="statement" onclick="switchTeacherPaymentTab('statement')" style="font-size:12px;padding:4px 10px;">Statement (${statement.length})</button>
        </div>
      </div>

      ${paySubCardsHtml}

      <div id="teacher-pay-salary" class="teacher-pay-pane active">
        ${salaryPayouts.length ? table(salaryPayouts, salaryCols) : '<p class="muted" style="padding:14px 0;margin:0;">No salary payouts recorded yet.</p>'}
      </div>

      <div id="teacher-pay-advances" class="teacher-pay-pane" style="display:none;">
        ${advances.length ? table(advances, advanceCols) : '<p class="muted" style="padding:14px 0;margin:0;">No advances recorded.</p>'}
      </div>

      <div id="teacher-pay-statement" class="teacher-pay-pane" style="display:none;">
        ${statement.length ? table(statement, statementCols) : '<p class="muted" style="padding:14px 0;margin:0;">No statement transaction history.</p>'}
      </div>
    </section>
  `;

  // SECTION 4: Attendance History of His/Her Own
  const attCols = [
    { key: 'date_bs', label: 'Date (BS)', render: r => `<b>${esc(r.date_bs)}</b>` },
    { key: 'date', label: 'Date (AD)', render: r => `<small class="muted">${esc(r.date)}</small>` },
    { key: 'day_of_week', label: 'Day' },
    { key: 'first_in', label: 'First In (Punch)', render: r => r.first_in ? `<span style="color:var(--success);font-weight:600;">${esc(r.first_in)}</span>` : '-' },
    { key: 'last_out', label: 'Last Out (Punch)', render: r => r.last_out ? `<span style="color:#0284c7;font-weight:600;">${esc(r.last_out)}</span>` : '-' },
    { key: 'punches', label: 'Punch Log', render: r => r.punches?.length ? r.punches.map(p => `<span class="badge" style="font-size:11px;margin-right:3px;">${esc(p)}</span>`).join('') : '-' },
    { key: 'hours', label: 'Hours', render: r => r.hours > 0 ? `${r.hours} hrs` : '-' },
    { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status || 'Present')}</span>` }
  ];

  const attendanceHtml = `
    <section class="panel" id="teacherAttendanceSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('attendance', 20)}My Attendance History
            ${todayAttBadge}
          </h2>
          <small class="muted">
            Current Month: <b>${esc(attHistory.current_month || 'This Month')}</b> · 
            Days Present: <b>${attHistory.month_days || 0}</b> · 
            Hours Worked: <b>${attHistory.month_hours || 0} hrs</b> · 
            Lifetime Days: <b>${attHistory.lifetime_days || 0}</b>
          </small>
        </div>
      </div>

      ${metrics.today_punches?.length ? `
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span style="font-size:20px;">🕒</span>
          <div>
            <b style="color:#166534;font-size:14px;">Today’s Biometric Punches (${esc(data.today_weekday || 'Today')}):</b>
            <div style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap;">
              ${metrics.today_punches.map(p => `<span class="badge active" style="font-size:12px;padding:3px 8px;">${esc(p)}</span>`).join('')}
            </div>
          </div>
        </div>
      ` : ''}

      ${dailyLogs.length ? table(dailyLogs, attCols) : '<p class="muted" style="padding:14px 0;margin:0;">No attendance records found for this period.</p>'}
    </section>
  `;

  // Tasks Section
  const tasksHtml = tasks.length ? `
    <section class="panel" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
          ${uiIcon('tasks', 20)}My Assigned Tasks & Action Items
          <span class="badge active" style="font-size:11px;">${tasks.length}</span>
        </h2>
        <button onclick="go('tasks')" style="font-size:12px;padding:4px 8px;">View All Tasks ${uiIcon('arrowRight', 12)}</button>
      </div>
      ${table(tasks, [
        { key: 'title', label: 'Task', render: t => `<b>${esc(t.title)}</b>` },
        { key: 'due_date', label: 'Due Date' },
        { key: 'priority', label: 'Priority', render: t => `<span class="badge ${t.priority === 'High' ? 'danger' : 'active'}">${esc(t.priority)}</span>` },
        { key: 'status', label: 'Status', render: t => `<span class="badge ${t.status === 'Completed' ? 'active' : 'partial'}">${esc(t.status)}</span>` },
        { key: 'details', label: 'Details' }
      ])}
    </section>
  ` : '';

  // Proxy & Leave Section
  const proxyAssignments = data.proxy_assignments || [];
  const proxyRequests = data.proxy_requests || [];

  const teacherProxyHtml = `
    <section class="panel" id="teacherProxySection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('proxy', 20)}Leave Requests & Proxy Class Management
            ${metrics.pending_proxy_count ? `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;font-size:12px;">${metrics.pending_proxy_count} Action Required</span>` : ''}
          </h2>
          <small class="muted">Manage your absence leave requests and respond to proxy substitution assignments</small>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="primary" onclick="proxyLeaveRequestModal()" style="font-size:12px;padding:5px 12px;display:inline-flex;align-items:center;gap:6px;background:#ea580c;border-color:#c2410c;">
            ${uiIcon('plus', 14)}Request Leave / Absence
          </button>
        </div>
      </div>

      <div id="teacherProxyAssignments" style="margin-bottom:20px;">
        <h3 style="font-size:15px;margin:0 0 10px 0;display:flex;align-items:center;gap:6px;color:#1e293b;">
          📥 Proxy Classes Assigned to Me
          <span class="badge active" style="font-size:11px;">${proxyAssignments.length}</span>
        </h3>
        ${proxyAssignments.length ? table(proxyAssignments, [
          { key: 'class_date', label: 'Date', render: r => `<b>${esc(r.class_date)}</b>` },
          { key: 'routine', label: 'Class / Period', render: r => `<b>${esc(r.display_class_name || r.class_name || '-')}</b><br><small class="muted">${esc(r.period_label || '')} (${esc(r.start_time || '')} - ${esc(r.end_time || '')})</small>` },
          { key: 'subject_name', label: 'Subject', render: r => `<b>${esc(r.subject_name || '-')}</b>` },
          { key: 'original_teacher_name', label: 'Regular Teacher', render: r => esc(r.original_teacher_name || '-') },
          { key: 'proxy_status', label: 'Your Response', render: r => {
            if (r.proxy_status === 'Accepted') return `<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;">● Accepted</span>`;
            if (r.proxy_status === 'Declined') return `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;">● Declined</span>`;
            return `<span class="badge" style="background:#fef3c7;color:#b45309;font-weight:700;">● Pending Response</span>`;
          }},
          { key: 'actions', label: 'Action', render: r => {
            if (r.proxy_status === 'Pending') {
              return `
                <div style="display:flex;gap:6px;">
                  <button class="primary" style="padding:4px 10px;font-size:11px;background:#16a34a;border-color:#16a34a;" onclick="respondProxy(${r.id}, 'Accept')">Accept</button>
                  <button style="padding:4px 10px;font-size:11px;color:#dc2626;border-color:#fca5a5;" onclick="respondProxy(${r.id}, 'Decline')">Decline</button>
                </div>
              `;
            }
            if (r.proxy_status === 'Accepted') {
              return `<small class="muted" style="color:#16a34a;font-weight:600;">✓ Confirmed Proxy</small>`;
            }
            return `<small class="muted">${esc(r.proxy_declined_reason || 'Declined')}</small>`;
          }}
        ]) : `<p class="muted" style="padding:10px 0;margin:0;font-size:13px;">No proxy classes assigned to you at this time.</p>`}
      </div>

      <div id="teacherLeaveRequests">
        <h3 style="font-size:15px;margin:0 0 10px 0;display:flex;align-items:center;gap:6px;color:#1e293b;">
          📤 My Absence & Leave Requests
          <span class="badge" style="font-size:11px;">${proxyRequests.length}</span>
        </h3>
        ${proxyRequests.length ? table(proxyRequests, [
          { key: 'class_date', label: 'Date', render: r => `<b>${esc(r.class_date)}</b>` },
          { key: 'routine', label: 'Class / Period', render: r => `<b>${esc(r.display_class_name || r.class_name || '-')}</b><br><small class="muted">${esc(r.period_label || '')} (${esc(r.start_time || '')} - ${esc(r.end_time || '')})</small>` },
          { key: 'subject_name', label: 'Subject', render: r => `<b>${esc(r.subject_name || '-')}</b>` },
          { key: 'leave_type', label: 'Type / Reason', render: r => `<span class="badge active">${esc(r.leave_type || 'Absent')}</span><br><small class="muted">${esc(r.reason || 'No details')}</small>` },
          { key: 'status', label: 'Leave Approval', render: r => {
            if (r.status === 'Approved') return `<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;">Approved</span>`;
            if (r.status === 'Rejected') return `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;">Rejected</span>`;
            return `<span class="badge" style="background:#fef3c7;color:#b45309;font-weight:700;">Pending</span>`;
          }},
          { key: 'proxy_teacher_name', label: 'Substitute Teacher', render: r => {
            if (!r.proxy_teacher_id) return `<span class="muted" style="font-style:italic;">Pending Admin Assignment</span>`;
            const statusLabel = r.proxy_status === 'Accepted' ? '<span style="color:#16a34a;font-weight:700;">(Accepted)</span>' : (r.proxy_status === 'Declined' ? '<span style="color:#dc2626;font-weight:700;">(Declined)</span>' : '<span style="color:#b45309;">(Pending)</span>');
            return `<b>${esc(r.proxy_teacher_name)}</b> ${statusLabel}`;
          }}
        ]) : `<p class="muted" style="padding:10px 0;margin:0;font-size:13px;">You have not submitted any leave or proxy requests.</p>`}
      </div>
    </section>
  `;

  shell(
    'Teacher Dashboard',
    'Personal teaching schedule, assigned students, payment statements, and attendance records',
    `${heroHtml}${pendingProxyAlertHtml}${cardsHtml}${teacherProxyHtml}${scheduleHtml}${studentsHtml}${paymentsHtml}${attendanceHtml}${tasksHtml}`
  );
}

// Standalone pages for direct routing
async function teacher_classes() {
  const data = await api('/dashboard');
  if (data.role === 'staff' || data.role === 'teacher') {
    renderTeacherDashboard(data);
    setTimeout(() => document.querySelector('#teacherStudentsSection')?.scrollIntoView({ behavior: 'smooth' }), 100);
  } else {
    go('dashboard');
  }
}

async function teacher_attendance() {
  const data = await api('/dashboard');
  if (data.role === 'staff' || data.role === 'teacher') {
    renderTeacherDashboard(data);
    setTimeout(() => document.querySelector('#teacherAttendanceSection')?.scrollIntoView({ behavior: 'smooth' }), 100);
  } else {
    go('attendance');
  }
}

async function teacher_payments() {
  const data = await api('/dashboard');
  if (data.role === 'staff' || data.role === 'teacher') {
    renderTeacherDashboard(data);
    setTimeout(() => document.querySelector('#teacherPaymentsSection')?.scrollIntoView({ behavior: 'smooth' }), 100);
  } else {
    go('salary');
  }
}

async function dashboard() {
  const data = await api('/dashboard');
  if (data.role === 'student') {
    renderStudentDashboard(data);
    return;
  }
  if (data.role === 'staff' || data.role === 'teacher') {
    renderTeacherDashboard(data);
    return;
  }
  const overdueCount = data.metrics.overdue_bills_count || 0;
  const overdueAmount = data.metrics.overdue_amount || 0;
  const paymentAlerts = data.payment_alerts || [];
  const todayClasses = data.today_classes || [];
  const todayWeekday = data.today_weekday || 'Today';
  const activePlanName = data.active_plan_name || 'Active Routine';
  window._paymentAlerts = paymentAlerts;

  const presentTeachersCount = data.present_teachers_count !== undefined
    ? data.present_teachers_count
    : todayClasses.filter(c => c.teacher_present === true).length;
  const absentTeachersCount = data.absent_teachers_count !== undefined
    ? data.absent_teachers_count
    : todayClasses.filter(c => c.teacher_present === false).length;

  const metricCards = [
    {
      label: "Today's Classes",
      value: `${data.today_classes_count ?? todayClasses.length} Classes`,
      sub: `${presentTeachersCount} present (green) · ${absentTeachersCount} absent (red)`,
      badge: `<span class="badge active" style="font-size:11px;padding:2px 6px;">${esc(todayWeekday)}</span>`,
      icon: uiIcon('routines', 22),
      onClick: "document.querySelector('#todayClassesSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'Total Students',
      value: data.metrics.students,
      sub: 'Enrolled student body',
      icon: uiIcon('students', 22),
      onClick: "go('students')"
    },
    {
      label: 'Active Staff',
      value: data.metrics.staff,
      sub: 'Teaching & non-teaching',
      icon: uiIcon('staff', 22),
      onClick: "go('staff')"
    },
    {
      label: 'Active Enrollments',
      value: data.metrics.enrollments,
      sub: 'Current course admissions',
      icon: uiIcon('enrollments', 22),
      onClick: "go('enrollments')"
    },
    {
      label: 'Outstanding Dues',
      value: `Rs. ${money(data.metrics.outstanding)}`,
      sub: overdueCount > 0 ? `${overdueCount} overdue bill(s) (Rs. ${money(overdueAmount)})` : 'Receivables balance',
      subClass: overdueCount > 0 ? 'due-alert' : '',
      icon: uiIcon('bills', 22),
      onClick: "document.querySelector('#paymentAlertsSection')?.scrollIntoView({behavior:'smooth'})"
    }
  ];

  const cardsHtml = `
    <div class="cards">
      ${metricCards.map(c => `
        <div class="card" ${c.onClick ? `onclick="${c.onClick}" style="cursor:pointer;" title="Click to view"` : ''}>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span>${esc(c.label)}</span>
            <div class="card-icon">
              ${c.icon}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
            <b style="font-size:22px;">${esc(c.value)}</b>
            ${c.badge || ''}
          </div>
          <small class="${c.subClass || 'muted'}">${esc(c.sub)}</small>
        </div>
      `).join('')}
    </div>
  `;

  const todayClassesHtml = `
    <section class="panel" id="todayClassesSection">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            ${uiIcon('routines', 18)}
            Today’s Scheduled Classes (${esc(todayWeekday)})
            <span class="badge active" style="font-size:12px;padding:2px 8px;font-weight:700;">${todayClasses.length} Scheduled</span>
            <span class="badge" style="font-size:12px;padding:2px 8px;font-weight:700;background:#dcfce7;color:#15803d;border:1px solid #86efac;display:inline-flex;align-items:center;gap:4px;" title="Classes whose assigned faculty have punched attendance today">
              <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#16a34a;"></span>
              ${presentTeachersCount} Present
            </span>
            <span class="badge" style="font-size:12px;padding:2px 8px;font-weight:700;background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;display:inline-flex;align-items:center;gap:4px;" title="Classes whose assigned faculty have not punched attendance today">
              <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#dc2626;"></span>
              ${absentTeachersCount} Absent
            </span>
          </h2>
          <small class="muted">Academic timetable routine running today under ${esc(activePlanName)}</small>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <button onclick="go('routines')" style="font-size:12px;padding:4px 10px;display:inline-flex;align-items:center;gap:4px;">
            ${uiIcon('routines', 14)} Master Routine Timetable
          </button>
        </div>
      </div>
      <div id="todayClassesContainer">
        ${todayClasses.length ? table(todayClasses, [
          { key: 'period_label', label: 'Period' },
          { key: 'time', label: 'Time', render: row => `${row.start_time || ''} - ${row.end_time || ''}` },
          { key: 'display_class_name', label: 'Class / Grade', render: row => `<b>${esc(row.display_class_name || row.class_name || '-')}</b>` },
          { key: 'subject_name', label: 'Subject', render: row => `<b>${esc(row.subject_name || '-')}</b>` },
          { key: 'teacher_name', label: 'Teacher / Faculty', render: row => {
            if (row.has_proxy) {
              const proxyDot = row.teacher_present === true
                ? '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#16a34a;margin-right:6px;flex-shrink:0;" title="Proxy Present"></span>'
                : '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#dc2626;margin-right:6px;flex-shrink:0;" title="Proxy Absent"></span>';
              return `<div>
                <div style="display:inline-flex;align-items:center;">
                  ${proxyDot}
                  <span class="badge" style="background:#e0e7ff;color:#3730a3;font-weight:700;border:1px solid #c7d2fe;font-size:11px;padding:2px 8px;border-radius:10px;">
                    Proxy: ${esc(row.proxy_teacher_name)}
                  </span>
                </div>
                <div style="font-size:11px;color:#64748b;margin-top:2px;">(for ${esc(row.original_teacher_name || row.teacher_name)})</div>
              </div>`;
            }
            const name = esc(row.teacher_name || 'Unassigned');
            const isBhawani = (row.teacher_name || '').toLowerCase().includes('bhawani');
            let dot = '';
            if (row.teacher_present === true) {
              dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#16a34a;margin-right:6px;flex-shrink:0;" title="Teacher is Present"></span>';
            } else if (row.teacher_present === false) {
              dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#dc2626;margin-right:6px;flex-shrink:0;" title="Teacher is Absent"></span>';
            } else {
              dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#9ca3af;margin-right:6px;flex-shrink:0;" title="Unassigned"></span>';
            }
            return `<div style="display:inline-flex;align-items:center;">
              ${dot}
              <span style="${isBhawani ? 'background:#e0f2fe;color:#0369a1;font-weight:700;padding:2px 6px;border-radius:4px;' : 'font-weight:600;'}">${name}</span>
            </div>`;
          }},
          { key: 'teacher_attendance', label: 'Teacher Status', render: row => {
            if (row.has_proxy) {
              if (row.teacher_present === true) {
                const punchTime = row.first_punch ? humanTime(row.first_punch) : '';
                return `<div style="display:inline-flex;flex-direction:column;gap:2px;">
                  <span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;border:1px solid #86efac;padding:3px 10px;border-radius:12px;display:inline-flex;align-items:center;gap:5px;font-size:12px;">
                    <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#16a34a;"></span>
                    Proxy Present
                  </span>
                  ${punchTime ? `<small class="muted" style="font-size:11px;display:inline-flex;align-items:center;gap:3px;">🕒 In: ${punchTime}</small>` : ''}
                </div>`;
              } else {
                return `<div style="display:inline-flex;flex-direction:column;gap:2px;">
                  <span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;border:1px solid #fca5a5;padding:3px 10px;border-radius:12px;display:inline-flex;align-items:center;gap:5px;font-size:12px;">
                    <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#dc2626;"></span>
                    Proxy Absent
                  </span>
                  <small class="muted" style="font-size:11px;">Not punched today</small>
                </div>`;
              }
            }
            if (row.teacher_present === true) {
              const punchTime = row.first_punch ? humanTime(row.first_punch) : '';
              return `<div style="display:inline-flex;flex-direction:column;gap:2px;">
                <span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;border:1px solid #86efac;padding:3px 10px;border-radius:12px;display:inline-flex;align-items:center;gap:5px;font-size:12px;" title="Teacher attendance logged today">
                  <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#16a34a;box-shadow:0 0 0 2px rgba(22,163,74,0.2);"></span>
                  Present
                </span>
                ${punchTime ? `<small class="muted" style="font-size:11px;display:inline-flex;align-items:center;gap:3px;">🕒 In: ${punchTime}</small>` : ''}
              </div>`;
            } else if (row.teacher_present === false) {
              return `<div style="display:inline-flex;flex-direction:column;gap:2px;">
                <span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;border:1px solid #fca5a5;padding:3px 10px;border-radius:12px;display:inline-flex;align-items:center;gap:5px;font-size:12px;" title="Teacher has no biometric attendance punch today">
                  <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#dc2626;box-shadow:0 0 0 2px rgba(220,38,38,0.2);"></span>
                  Absent
                </span>
                <small class="muted" style="font-size:11px;">Not punched today</small>
              </div>`;
            } else {
              return `<span class="muted small" style="font-style:italic;">Unassigned</span>`;
            }
          }},
          { key: 'course_name', label: 'Course' },
          { key: 'status', label: 'Class Status', render: row => `<span class="badge active">${esc(row.status || 'Active')}</span>` }
        ], {
          rowStyle: row => {
            if (row.teacher_present === true) return 'background:rgba(240,253,244,0.38);';
            if (row.teacher_present === false) return 'background:rgba(254,242,242,0.38);';
            return '';
          }
        }) : `<p class="muted" style="padding:12px 0;margin:0;">No classes scheduled for today (${esc(todayWeekday)}).</p>`}
      </div>
    </section>
  `;

  const paymentAlertsHtml = `
    <section class="panel" id="paymentAlertsSection">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <h2 style="margin:0;display:flex;align-items:center;gap:8px;">
          ${uiIcon('bills', 18)}
          Payment Alerts & Overdue Follow-ups
          ${paymentAlerts.length ? `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-size:12px;padding:2px 8px;font-weight:700;">${paymentAlerts.length} Overdue</span>` : ''}
        </h2>
        <div style="display:flex;align-items:center;gap:8px;">
          <button id="toggleSuppressedPaymentsBtn" onclick="toggleSuppressedPaymentAlerts()" style="font-size:12px;padding:4px 10px;">
            ${window._showSuppressedPayments ? 'Hide Suppressed' : 'Show Suppressed'}
          </button>
        </div>
      </div>
      <div id="paymentAlertsContainer">
        ${paymentAlerts.length
          ? table(paymentAlerts, paymentAlertColumns)
          : '<p class="muted" style="padding:12px 0;margin:0;">No overdue payment alerts. All bills are within payment terms or settled.</p>'
        }
      </div>
    </section>
  `;

  shell('Dashboard', 'Today’s operational overview & metrics', `${cardsHtml}${todayClassesHtml}${paymentAlertsHtml}<section class="panel"><h2>Students present today</h2>${table(data.present_today, [{ key: 'student_name', label: 'Student' }, { key: 'class_name', label: 'Class' }, { key: 'punches', label: 'Punches' }, { key: 'first_seen', label: 'First punch', render: row => humanTime(row.first_seen) }, { key: 'last_seen', label: 'Last punch', render: row => humanTime(row.last_seen) }])}</section><section class="panel"><h2>Attendance follow-up alerts</h2>${table(data.attendance_alerts, [{ key: 'student_name', label: 'Student' }, { key: 'class_name', label: 'Class' }, { key: 'reason', label: 'Reason' }, { key: 'review_status', label: 'Status' }])}</section>`);
}

const paymentAlertColumns = [
  { key: 'student_name', label: 'Student', render: row => `<a href="javascript:void(0)" onclick="viewStudentProfile(${row.student_id})" style="font-weight:700;color:var(--brand);text-decoration:none;">${esc(row.student_name)}</a>` },
  { key: 'class_name', label: 'Class' },
  { key: 'bill_number', label: 'Bill #' },
  { key: 'course_name', label: 'Course' },
  { key: 'due_date', label: 'Due Date' },
  { key: 'days_overdue', label: 'Overdue', render: row => `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;">${row.days_overdue} day(s)</span>` },
  { key: 'balance', label: 'Amount Due', render: row => `<b class="due-alert">Rs. ${money(row.balance)}</b>` },
  { key: 'review_status', label: 'Follow-up Status', render: row => `<span class="badge ${row.review_status === 'Suppressed' ? 'inactive' : (row.review_status === 'Suppression expired' ? 'partial' : (row.review_status === 'Not reviewed' ? 'inactive' : 'active'))}">${esc(row.review_status)}</span>` },
  { key: 'follow_up_date', label: 'Follow-up Date', render: row => row.follow_up_date ? esc(row.follow_up_date) : '<span class="muted">-</span>' },
  {
    key: 'actions',
    label: 'Actions',
    render: row => `
      <div style="display:flex;gap:4px;align-items:center;">
        <button class="primary" style="padding:4px 8px;font-size:12px;" onclick="paymentReviewForm(${row.bill_id}, '${esc(row.student_name)}', '${esc(row.bill_number)}', ${row.balance})">Follow-up / Suppress</button>
        <button style="padding:4px 8px;font-size:12px;" onclick="billPayment(${row.bill_id})">Pay</button>
      </div>
    `
  }
];

let _showSuppressedPayments = false;
async function toggleSuppressedPaymentAlerts() {
  _showSuppressedPayments = !_showSuppressedPayments;
  const rows = await api(`/billing/alerts?include_suppressed=${_showSuppressedPayments}`);
  window._paymentAlerts = rows;
  const container = document.querySelector('#paymentAlertsContainer');
  const btn = document.querySelector('#toggleSuppressedPaymentsBtn');
  if (container) {
    container.innerHTML = rows.length
      ? table(rows, paymentAlertColumns)
      : '<p class="muted" style="padding:12px 0;margin:0;">No overdue payment alerts found.</p>';
    if (btn) btn.textContent = _showSuppressedPayments ? 'Hide Suppressed' : 'Show Suppressed';
  } else {
    dashboard();
  }
}

function paymentReviewForm(billId, studentName, billNumber, amount) {
  const host = modal(`Payment Follow-up — ${billNumber}`, `
    <form class="form">
      <div style="margin-bottom:12px;padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;font-size:13px;">
        <div>Student: <b>${esc(studentName)}</b></div>
        <div>Bill: <b>${esc(billNumber)}</b> &nbsp;|&nbsp; Balance Due: <b class="due-alert">Rs. ${money(amount)}</b></div>
      </div>
      <label>Follow-up Status *
        <select name="status">
          <option value="Suppressed">Suppressed (Hide from dashboard until follow-up)</option>
          <option value="Promise to Pay">Promise to Pay</option>
          <option value="Parent Contacted">Parent Contacted</option>
          <option value="Payment Plan">Payment Plan</option>
          <option value="Dispute / Under Review">Dispute / Under Review</option>
          <option value="Monitoring">Monitoring</option>
          <option value="No Action Needed">No Action Needed</option>
        </select>
      </label>
      <label>Resume / Follow-up Date (BS)
        <input name="follow_up_date" placeholder="2083/06/01">
        <small class="muted">When status is "Suppressed", the alert is hidden until this date, then returns automatically.</small>
      </label>
      <label>Follow-up Notes / Reason
        <textarea name="note" rows="3" placeholder="e.g. Called parent; promised to pay full fees next week Monday."></textarea>
      </label>
      <div class="form-actions">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Save Follow-up</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    try {
      await api(`/billing/alerts/${billId}/review`, {
        method: 'POST',
        body: JSON.stringify(formData(event.target)),
      });
      host.remove();
      dashboard();
    } catch (error) {
      showError(error);
    }
  };
}

const studentColumns = [
  { key: 'id', label: 'ID' },
  { key: 'student_name', label: 'Student', render: row => `<a href="javascript:void(0)" onclick="viewStudentProfile(${row.id})" style="font-weight:700;color:var(--brand);text-decoration:none;">${esc(row.student_name)}</a>` },
  { key: 'class_name', label: 'Class' },
  { key: 'school_name', label: 'School' },
  { key: 'contact', label: 'Contact' },
  { key: 'enrolled', label: 'Enrolled', render: row => row.enrolled ? 'Yes' : 'No' },
  {
    key: 'actions',
    label: 'Actions',
    render: row => `
      <div style="display:flex;gap:4px;align-items:center;">
        <button class="primary" style="padding:4px 8px;font-size:12px;" onclick="viewStudentProfile(${row.id})">Profile</button>
        <button style="padding:4px 8px;font-size:12px;" onclick="editStudent(${row.id})">Edit</button>
        ${has('administration.manage') ? `<button style="padding:4px 8px;font-size:12px;background:var(--brand-light);color:var(--brand);border:1px solid var(--brand);" onclick="openCreateUserForStudent(${row.id})" title="Create or manage user account">User</button>` : ''}
      </div>
    `
  }
];
async function students() {
  const rows = await api('/students');
  shell('Students', 'Records, attendance identity, and enrollment status', `${toolbar([`<input id="studentSearch" placeholder="Search students" oninput="filterStudents()">`, `<select id="studentStatus" onchange="filterStudents()"><option>All</option><option>Active</option><option>Inactive</option></select>`, action('Add student', 'studentForm()', true), action('Export visible CSV', 'exportStudentCsv()')])}<div id="studentTable">${table(rows, studentColumns)}</div>`);
  window._students = rows;
}
async function filterStudents() { const query = document.querySelector('#studentSearch').value; const status = document.querySelector('#studentStatus').value; const rows = await api(`/students?query=${encodeURIComponent(query)}&status=${status}`); window._students = rows; document.querySelector('#studentTable').innerHTML = table(rows, studentColumns); }
function exportStudentCsv() { csvDownload('students.csv', window._students || [], studentColumns.slice(0, -1)); }
async function studentForm(existing = null) {
  const data = await getLookups(); const value = key => esc(existing?.[key] || '');
  const schoolOptions = `<option value="">Not assigned</option>${data.schools.map(s => `<option value="${s.id}" ${existing?.school_id === s.id ? 'selected' : ''}>${esc(s.school_name)}</option>`).join('')}`;
  const classOptions = `<option value="">Not assigned</option>${data.classes.map(c => `<option ${existing?.class_name === c.level_name ? 'selected' : ''}>${esc(c.level_name)}</option>`).join('')}`;
  const host = modal(existing ? 'Edit student' : 'Add student', `<form class="form two-col"><label>Name *<input name="name" required value="${value('name')}"></label><label>Class<select name="class_name">${classOptions}</select></label><label>School<select name="school_id">${schoolOptions}</select></label><label>Contact<input name="contact" value="${value('contact')}"></label><label>Gender<select name="gender"><option></option>${['Male','Female','Other'].map(v => `<option ${existing?.gender === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label>Joining date (BS) *<input name="joining_date" required placeholder="2083/05/10" value="${value('joining_date')}"></label><label>Date of birth (BS)<input name="date_of_birth" value="${value('date_of_birth')}"></label><label>Parent / Guardian<input name="parent_name" value="${value('parent_name')}"></label><label>Relationship<input name="guardian_relationship" value="${value('guardian_relationship')}"></label><label>Status<select name="status">${['Active','Inactive'].map(v => `<option ${(!existing && v === 'Active') || existing?.status === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label class="span-2">Address<input name="address" value="${value('address')}"></label><label class="span-2">Remarks<input name="remarks" value="${value('remarks')}"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">${existing ? 'Save changes' : 'Save student'}</button>${existing ? `<button type="button" class="danger" onclick="archiveStudent(${existing.id})">Archive</button>` : ''}</div></form>`);
  host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.school_id = payload.school_id ? Number(payload.school_id) : null; try { await api(existing ? `/students/${existing.id}` : '/students', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) }); lookups = null; host.remove(); if (location.hash.includes('student-profile')) { go(location.hash.slice(1)); } else { go('students'); } } catch (error) { showError(error); } };
}
async function editStudent(id) { const record = await api(`/students/${id}`); studentForm(record); }
async function archiveStudent(id) { if (!confirm('Archive this student? Existing history will be retained.')) return; try { await api(`/students/${id}/archive`, { method: 'POST' }); document.querySelector('.modal')?.remove(); go('students'); } catch (error) { showError(error); } }

function viewStudentProfile(id) {
  go(`student-profile?id=${id}`);
}

async function downloadStudentProfilePdf(studentId) {
  try {
    const res = await fetch(`/api/students/${studentId}/profile/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
    if (!res.ok) throw new Error('Failed to generate student profile PDF');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `student_profile_${studentId}.pdf`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err);
  }
}

function switchProfileTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-content').forEach(pane => {
    pane.classList.toggle('active', pane.id === `tab-${tabId}`);
  });
}

async function student_profile() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  let studentId = Number(params.get('id'));
  if (!studentId && me?.student_id) {
    studentId = Number(me.student_id);
  }
  if (!studentId) {
    go(me?.role === 'student' ? 'dashboard' : 'students');
    return;
  }

  const profile = await api(`/students/${studentId}/profile`);
  const student = profile.student;
  const financials = profile.financials;
  const attendance = profile.attendance;
  const activeEnrollments = profile.active_enrollments || [];
  const previousEnrollments = profile.previous_enrollments || [];
  const certificates = profile.certificates || [];
  const recentSms = profile.recent_sms || [];

  const initials = (student.student_name || 'ST')
    .split(/\s+/)
    .slice(0, 2)
    .map(p => p[0].toUpperCase())
    .join('') || 'ST';

  const photoHtml = student.has_photo
    ? `<img src="/api/students/${student.id}/photo?token=${encodeURIComponent(token)}" class="profile-photo" alt="${esc(student.student_name)}">`
    : `<div class="profile-avatar-fallback"><b>${esc(initials)}</b><small>No photo</small></div>`;

  const statusBadge = `<span class="badge ${student.status === 'Active' ? 'active' : 'inactive'}">● ${esc(student.status.toUpperCase())}</span>`;

  const heroHtml = `
    <div class="profile-hero">
      ${photoHtml}
      <div class="profile-body">
        <div class="profile-name-row">
          <h2>${esc(student.student_name)}</h2>
          ${statusBadge}
        </div>
        <div class="profile-meta-grid">
          <div class="profile-meta-item"><span>Student ID:</span> <b>#${esc(student.id)}</b></div>
          <div class="profile-meta-item"><span>Class / Level:</span> <b>${esc(student.class_level_name || student.class_name || 'Unassigned')}</b></div>
          <div class="profile-meta-item"><span>School:</span> <b>${esc(student.school_name || 'None')}</b></div>
          <div class="profile-meta-item"><span>Contact:</span> <b>${esc(student.contact || '-')}</b></div>
          <div class="profile-meta-item"><span>Parent / Guard.:</span> <b>${esc(student.parent_name || '-')} (${esc(student.guardian_relationship || 'Guardian')})</b></div>
          <div class="profile-meta-item"><span>DOB & Gender:</span> <b>${esc(student.date_of_birth || '-')} | ${esc(student.gender || '-')}</b></div>
          <div class="profile-meta-item"><span>Joining Date:</span> <b>${esc(student.joining_date || '-')}</b></div>
          <div class="profile-meta-item"><span>Biometric User:</span> <b>${esc(student.device_user_id ? `User #${student.device_user_id}` : 'Not mapped')} ${student.device_user_name ? `(${esc(student.device_user_name)})` : ''}</b></div>
          <div class="profile-meta-item" style="grid-column: 1 / -1;"><span>Address:</span> <b>${esc(student.address || '-')}</b></div>
        </div>
      </div>
      <div class="profile-actions">
        <button class="primary" onclick="downloadStudentProfilePdf(${student.id})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('print', 15)}Download PDF Dossier</button>
        <button onclick="window.print()" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('print', 15)}Print View</button>
        ${has('students.manage') ? `<button onclick="editStudent(${student.id})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('edit', 15)}Edit Student</button>` : ''}
        ${has('administration.manage') ? `<button onclick="openCreateUserForStudent(${student.id})" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('users', 15)}User Account</button>` : ''}
        ${has('students.manage') ? `<button onclick="go('students')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('arrowLeft', 14)}Back to Students</button>` : ''}
      </div>
    </div>
  `;

  const dueColorClass = financials.total_due > 0 ? 'due-alert' : 'paid-ok';
  const kpiCardsHtml = `
    <div class="cards" style="margin-top: 16px;">
      <div class="card">
        <span>OUTSTANDING BALANCE</span>
        <b class="${dueColorClass}">Rs. ${money(financials.total_due)}</b>
        <small class="muted">${financials.total_due > 0 ? `${financials.due_bills.length} bill(s) pending` : 'All accounts settled'}</small>
      </div>
      <div class="card">
        <span>COURSES ENROLLED</span>
        <b>${activeEnrollments.length} Active</b>
        <small class="muted">${previousEnrollments.length} previous / completed</small>
      </div>
      <div class="card">
        <span>MONTH ATTENDANCE (${esc(attendance.current_month)})</span>
        <b>${attendance.days_present_month} Days</b>
        <small class="muted">${attendance.total_punches_month} punches · ${attendance.lifetime_days} lifetime</small>
      </div>
      <div class="card">
        <span>TOTAL FEES PAID</span>
        <b>Rs. ${money(financials.total_paid)}</b>
        <small class="muted">Invoiced: Rs. ${money(financials.total_billed)}</small>
      </div>
    </div>
  `;

  const activeColumns = [
    { key: 'course_name', label: 'Course' },
    { key: 'category', label: 'Category' },
    { key: 'level', label: 'Level' },
    { key: 'start_date', label: 'Start Date' },
    { key: 'monthly_fee', label: 'Monthly Fee', render: r => `Rs. ${money(r.monthly_fee)}` },
    { key: 'admission_fee', label: 'Admission Fee', render: r => `Rs. ${money(r.admission_fee)}` },
    { key: 'discount', label: 'Discount', render: r => `Rs. ${money(r.discount)}` },
    { key: 'billing_type', label: 'Billing Type' },
    { key: 'instructor_name', label: 'Instructor' },
  ];
  const previousColumns = [
    { key: 'course_name', label: 'Course' },
    { key: 'category', label: 'Category' },
    { key: 'level', label: 'Level' },
    { key: 'start_date', label: 'Start Date' },
    { key: 'end_date', label: 'End Date' },
    { key: 'monthly_fee', label: 'Monthly Fee', render: r => `Rs. ${money(r.monthly_fee)}` },
    { key: 'status', label: 'Status', render: r => `<span class="badge ${r.status === 'Active' ? 'active' : 'inactive'}">${esc(r.status)}</span>` },
  ];

  const billColumns = [
    { key: 'bill_number', label: 'Bill #' },
    { key: 'billing_period', label: 'Period' },
    { key: 'course_name', label: 'Course' },
    { key: 'issue_date', label: 'Issue Date' },
    { key: 'due_date', label: 'Due Date' },
    { key: 'total_amount', label: 'Total', render: r => `Rs. ${money(r.total_amount)}` },
    { key: 'paid_amount', label: 'Paid', render: r => `Rs. ${money(r.paid_amount)}` },
    { key: 'balance', label: 'Balance Due', render: r => `<b class="${r.balance > 0 ? 'due-alert' : 'paid-ok'}">Rs. ${money(r.balance)}</b>` },
    { key: 'status', label: 'Status', render: r => `<span class="badge ${r.status === 'Paid' ? 'active' : (r.status === 'Partial' ? 'partial' : 'inactive')}">${esc(r.status)}</span>` },
    { key: 'pay', label: 'Action', render: r => r.balance > 0 ? `<button class="primary" style="padding:4px 8px;font-size:11px;" onclick="billPayment(${r.id})">Receive Payment</button>` : '' }
  ];
  const txnColumns = [
    { key: 'transaction_date', label: 'Date' },
    { key: 'receipt_no', label: 'Receipt #' },
    { key: 'particular', label: 'Particular', render: r => esc(r.particular || r.remarks || '-') },
    { key: 'payment_amount', label: 'Paid Amount', render: r => `Rs. ${money(r.payment_amount)}` },
    { key: 'discount_amount', label: 'Discount', render: r => `Rs. ${money(r.discount_amount)}` },
    { key: 'payment_method', label: 'Method' },
    { key: 'account_name', label: 'Account' },
  ];

  const punchColumns = [
    { key: 'date', label: 'Date (AD)' },
    { key: 'first_in', label: 'First In (Check-in)', render: r => r.first_in ? humanTime(`T${r.first_in}`) : '-' },
    { key: 'last_out', label: 'Last Out (Check-out)', render: r => r.last_out ? humanTime(`T${r.last_out}`) : '-' },
    { key: 'punch_count', label: 'Total Punches' },
    { key: 'status', label: 'Daily Status', render: () => '<span class="badge active">Present</span>' },
  ];

  const certColumns = [
    { key: 'certificate_number', label: 'Certificate #' },
    { key: 'course_name_snapshot', label: 'Course Snapshot' },
    { key: 'certify_date', label: 'Certify Date' },
    { key: 'instructor_name', label: 'Instructor' },
    { key: 'status', label: 'Status', render: r => `<span class="badge active">${esc(r.status)}</span>` },
  ];
  const smsColumns = [
    { key: 'created_at', label: 'Sent At', render: r => String(r.created_at || '').slice(0, 19) },
    { key: 'event_key', label: 'Event' },
    { key: 'recipient', label: 'Recipient' },
    { key: 'message_text', label: 'Message Text' },
    { key: 'status', label: 'Status', render: r => `<span class="badge ${r.status === 'DELIVERED' ? 'active' : 'partial'}">${esc(r.status)}</span>` },
  ];

  const tabsHtml = `
    <div class="tabs-bar">
      <button class="tab-btn active" data-tab="enrollments" onclick="switchProfileTab('enrollments')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('courses', 15)}Course Enrollments (${activeEnrollments.length + previousEnrollments.length})</button>
      <button class="tab-btn" data-tab="finance" onclick="switchProfileTab('finance')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('bills', 15)}Account & Due Bills (${financials.due_bills.length})</button>
      <button class="tab-btn" data-tab="attendance" onclick="switchProfileTab('attendance')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('attendance', 15)}Attendance Record (${attendance.days_present_month} days)</button>
      <button class="tab-btn" data-tab="other" onclick="switchProfileTab('other')" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('certificates', 15)}Certificates & Logs</button>
    </div>

    <div id="tab-enrollments" class="tab-content active">
      <section class="panel">
        <h2>Active Enrollments (${activeEnrollments.length})</h2>
        ${table(activeEnrollments, activeColumns)}
      </section>
      <section class="panel">
        <h2>Previous Enrollments History (${previousEnrollments.length})</h2>
        ${table(previousEnrollments, previousColumns)}
      </section>
    </div>

    <div id="tab-finance" class="tab-content">
      <section class="panel">
        <h2>Due Bills & Invoices (${financials.due_bills.length})</h2>
        ${table(financials.due_bills, billColumns)}
      </section>
      <section class="panel">
        <h2>Payment Receipts & Transactions (${financials.transactions.length})</h2>
        ${table(financials.transactions, txnColumns)}
      </section>
    </div>

    <div id="tab-attendance" class="tab-content">
      <section class="panel">
        <h2>Attendance Overview (${esc(attendance.current_month)})</h2>
        <div style="padding: 10px 0; font-size: 13px; color: #475569;">
          Month: <b>${esc(attendance.current_month)}</b> ·
          Days Present: <b>${attendance.days_present_month}</b> ·
          Total Punches: <b>${attendance.total_punches_month}</b> ·
          Lifetime: <b>${attendance.lifetime_days}</b> days (${attendance.lifetime_punches} punches) ·
          First Seen: <b>${attendance.first_seen ? attendance.first_seen.slice(0, 10) : '-'}</b> ·
          Last Seen: <b>${attendance.last_seen ? attendance.last_seen.slice(0, 10) : '-'}</b>
        </div>
        ${table(attendance.recent_punches, punchColumns)}
      </section>
    </div>

    <div id="tab-other" class="tab-content">
      <section class="panel">
        <h2>Earned Certificates (${certificates.length})</h2>
        ${table(certificates, certColumns)}
      </section>
      <section class="panel">
        <h2>Recent SMS Notifications (${recentSms.length})</h2>
        ${table(recentSms, smsColumns)}
      </section>
      ${student.remarks ? `
      <section class="panel">
        <h2>Institutional Notes & Remarks</h2>
        <p style="margin: 0; color: #334155;">${esc(student.remarks)}</p>
      </section>
      ` : ''}
    </div>
  `;

  shell(
    `Student Profile: ${student.student_name}`,
    `Comprehensive record for #${student.id} · ${student.class_level_name || student.class_name || 'No Class'} · ${student.school_name || 'No School'}`,
    `${heroHtml}${kpiCardsHtml}${tabsHtml}`
  );
}

async function enrollments() {
  const rows = await api('/enrollments'); const columns = [{ key: 'id', label: 'ID' }, { key: 'student_name', label: 'Student' }, { key: 'course_name', label: 'Course' }, { key: 'level', label: 'Class' }, { key: 'start_date', label: 'Start' }, { key: 'end_date', label: 'End' }, { key: 'monthly_fee', label: 'Monthly fee', render: row => money(row.monthly_fee) }, { key: 'status', label: 'Status' }];
  shell('Enrollments', 'Assign students to courses and retain course history', `${toolbar([action('Assign enrollment', 'enrollmentForm()', true), action('Export CSV', 'exportEnrollments()')])}${table(rows, columns)}`); window._enrollments = rows; window._enrollmentColumns = columns;
}
function exportEnrollments() { csvDownload('enrollments.csv', window._enrollments || [], window._enrollmentColumns || []); }
async function enrollmentForm() {
  const [studentRows, courseRows] = await Promise.all([api('/students'), api('/courses')]);
  const host = modal('Assign enrollment', `<form class="form two-col"><label>Student *<select name="student_id">${selectOptions(studentRows, 'id', row => `${row.student_name}${row.class_name ? ` - ${row.class_name}` : ''}`)}</select></label><label>Course *<select name="course_id" onchange="this.form.monthly_fee.value=this.selectedOptions[0].dataset.fee">${courseRows.map(row => `<option value="${row.id}" data-fee="${row.default_fee || 0}">${esc(row.course_name)} (${esc(row.category)})</option>`).join('')}</select></label><label>Class / level<input name="level"></label><label>Start date (BS) *<input name="start_date" required placeholder="2083/05/10"></label><label>End date (BS)<input name="end_date"></label><label>Monthly fee<input name="monthly_fee" type="number" min="0" value="${courseRows[0]?.default_fee || 0}"></label><label>Admission fee<input name="admission_fee" type="number" min="0" value="0"></label><label>Discount<input name="discount" type="number" min="0" value="0"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save enrollment</button></div></form>`);
  host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); ['student_id','course_id'].forEach(k => payload[k] = Number(payload[k])); ['monthly_fee','admission_fee','discount'].forEach(k => payload[k] = Number(payload[k])); try { await api('/enrollments', { method: 'POST', body: JSON.stringify(payload) }); host.remove(); go('enrollments'); } catch (error) { showError(error); } };
}

async function bills() {
  const rows = await api('/bills');
  const isStudent = me?.role === 'student';
  window._selectedBillIds = new Set();
  const columns = [
    ...(isStudent ? [] : [{
      key: 'select_bill',
      isCheckbox: true,
      rawHeader: true,
      sortable: false,
      label: '<input type="checkbox" id="selectAllBills" title="Select All" onchange="toggleSelectAllBills(this.checked)" style="cursor:pointer;width:16px;height:16px;accent-color:#2563eb;margin:0;vertical-align:middle;">',
      headerHtml: '<input type="checkbox" id="selectAllBills" title="Select All" onchange="toggleSelectAllBills(this.checked)" style="cursor:pointer;width:16px;height:16px;accent-color:#2563eb;margin:0;vertical-align:middle;">',
      render: row => row.balance > 0
        ? `<input type="checkbox" class="bill-select-chk" value="${row.id}" data-student-id="${row.student_id || ''}" data-student="${esc(row.student_name)}" data-balance="${row.balance}" onchange="onBillCheckboxChange(this)" ${(window._selectedBillIds && window._selectedBillIds.has(row.id)) ? 'checked' : ''} style="cursor:pointer;width:16px;height:16px;accent-color:#2563eb;margin:0;vertical-align:middle;">`
        : ''
    }]),
    { key: 'bill_number', label: 'Bill no.' },
    ...(isStudent ? [] : [{ key: 'student_name', label: 'Student' }]),
    { key: 'course_name', label: 'Course' },
    { key: 'billing_period', label: 'Period' },
    { key: 'due_date', label: 'Due date' },
    { key: 'total_amount', label: 'Total', render: row => money(row.total_amount) },
    { key: 'paid_amount', label: 'Paid', render: row => money(row.paid_amount) },
    { key: 'balance', label: 'Balance', render: row => `<b class="${row.balance > 0 ? 'due-alert' : 'paid-ok'}">Rs. ${money(row.balance)}</b>` },
    { key: 'status', label: 'Status', render: row => `<span class="badge ${row.status === 'Paid' ? 'active' : (row.status === 'Partial' ? 'partial' : 'inactive')}">${esc(row.status)}</span>` },
    { key: 'pay', label: 'Action', render: row => {
      if (isStudent) {
        return row.balance > 0 ? `<button class="primary small" onclick="openBillPaymentQrModal(${row.id})">Pay via QR</button>` : `<span style="color:var(--success);font-weight:600;display:inline-flex;align-items:center;gap:4px;">${uiIcon('check', 13)}Settled</span>`;
      }
      return row.balance > 0 ? `<button class="primary small" onclick="billPayment(${row.id})">Receive payment</button>` : '';
    } }
  ];
  const tb = isStudent
    ? [action('Export CSV', 'exportBills()')]
    : [
        action('Generate bills', 'billGenerationForm()', true),
        `<button id="paySelectedBillsBtn" class="primary" style="display:none;background:#059669;border-color:#059669;padding:6px 12px;font-size:13px;align-items:center;gap:6px;" onclick="openSelectedBillsPayment()">${uiIcon('bills', 14)} Pay Selected Bills (<span id="selectedBillsCount">0</span>)</button>`,
        action('Export CSV', 'exportBills()')
      ];
  const title = isStudent ? 'My Fees & Bills' : 'Due Bills & Payments';
  const subtitle = isStudent ? 'Your fee statements, payment records, and balances' : 'Generate bills, accept payments, and track balances';
  shell(title, subtitle, `${toolbar(tb)}${table(rows, columns)}`);
  window._bills = rows;
  window._billColumns = columns;
}

function onBillCheckboxChange(cb) {
  if (!window._selectedBillIds) window._selectedBillIds = new Set();
  const id = Number(cb.value);
  if (cb.checked) {
    window._selectedBillIds.add(id);
  } else {
    window._selectedBillIds.delete(id);
  }
  updateSelectedBillsUI();
}

function toggleSelectAllBills(checked) {
  if (!window._selectedBillIds) window._selectedBillIds = new Set();
  const pageChks = document.querySelectorAll('.bill-select-chk');
  pageChks.forEach(cb => {
    cb.checked = checked;
    const id = Number(cb.value);
    if (checked) {
      window._selectedBillIds.add(id);
    } else {
      window._selectedBillIds.delete(id);
    }
  });
  updateSelectedBillsUI();
}

function updateSelectedBillsUI() {
  if (!window._selectedBillIds) window._selectedBillIds = new Set();
  const allBills = window._bills || [];
  const selectedBills = allBills.filter(b => window._selectedBillIds.has(b.id) && Number(b.balance) > 0);

  // Sync checkboxes on current page
  const pageChks = [...document.querySelectorAll('.bill-select-chk')];
  pageChks.forEach(cb => {
    const id = Number(cb.value);
    cb.checked = window._selectedBillIds.has(id);
  });

  const selectAll = document.getElementById('selectAllBills');
  if (selectAll && pageChks.length > 0) {
    selectAll.checked = pageChks.every(cb => cb.checked);
    selectAll.indeterminate = !selectAll.checked && pageChks.some(cb => cb.checked);
  } else if (selectAll) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }

  const btn = document.getElementById('paySelectedBillsBtn');
  const countSpan = document.getElementById('selectedBillsCount');
  if (!btn) return;
  if (selectedBills.length > 0) {
    btn.style.display = 'inline-flex';
    btn.style.alignItems = 'center';
    btn.style.gap = '6px';
    const totalBal = selectedBills.reduce((sum, b) => sum + Number(b.balance || 0), 0);
    if (countSpan) countSpan.textContent = `${selectedBills.length} · Rs. ${money(totalBal)}`;
  } else {
    btn.style.display = 'none';
  }
}

function openSelectedBillsPayment() {
  const ids = Array.from(window._selectedBillIds || []);
  if (!ids.length) {
    alert('Please select at least one bill to pay.');
    return;
  }
  multiBillPaymentModal(ids);
}

async function multiBillPaymentModal(billIds) {
  const data = await getLookups();
  const allBills = window._bills || [];
  const selectedBills = allBills.filter(b => billIds.includes(b.id));
  if (!selectedBills.length) {
    alert('No bills found.');
    return;
  }
  const studentNames = [...new Set(selectedBills.map(b => b.student_name))];
  if (studentNames.length > 1) {
    alert('All selected bills must belong to the same student for a combined payment.\nSelected students: ' + studentNames.join(', '));
    return;
  }
  const studentName = studentNames[0];
  const totalBalance = selectedBills.reduce((sum, b) => sum + (Number(b.balance) || 0), 0);

  const billsSummaryHtml = selectedBills.map(b => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:4px;font-size:12px;">
      <div><b>${esc(b.bill_number)}</b> <span class="muted">(${esc(b.billing_period)})</span> — ${esc(b.course_name)}</div>
      <div>Due: <b style="color:#d97706;">Rs. ${money(b.balance)}</b></div>
    </div>
  `).join('');

  const host = modal(
    `Combined Payment — ${esc(studentName)} (${selectedBills.length} Bills)`,
    `<form class="form two-col" id="multiBillPayForm">
      <div class="span-2" style="margin-bottom:6px;">
        <label style="font-weight:600;margin-bottom:4px;">Bills to settle (${selectedBills.length}):</label>
        <div style="max-height:140px;overflow-y:auto;padding-right:4px;">
          ${billsSummaryHtml}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding:6px 10px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;font-size:13px;">
          <span>Total Combined Balance Due:</span>
          <b style="color:#1d4ed8;font-size:15px;">Rs. ${money(totalBalance)}</b>
        </div>
        <small style="display:block;color:#0284c7;margin-top:4px;">💡 Payment automatically settles older bills first. Any extra amount is credited as student advance.</small>
      </div>

      <label>Payment amount *
        <input name="amount" id="multiPayAmountInput" type="number" min="0" step="0.01" value="${totalBalance}" required>
        <small id="multiPayAdvanceNotice" style="display:none;color:#16a34a;font-weight:600;margin-top:2px;"></small>
      </label>
      <label>Discount
        <input name="discount" type="number" min="0" step="0.01" value="0">
      </label>
      <label>Payment date (BS) *
        <input name="payment_date" placeholder="2083/05/10" required>
      </label>
      <label>Account *
        <select name="account_id" required>
          <option value="">Select account</option>
          ${selectOptions(data.accounts, 'id', row => `${row.account_name} (${row.account_type})`)}
        </select>
      </label>
      <label>Method
        <select name="payment_method">
          <option>Cash</option>
          <option>Bank</option>
          <option>Wallet</option>
          <option>Other</option>
        </select>
      </label>
      <label>Receipt no.
        <input name="receipt_no">
      </label>
      <label class="span-2">Remarks
        <input name="remarks" placeholder="Optional transaction reference / notes">
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary" style="background:#059669;border-color:#059669;">Receive Payment (Rs. <span id="multiPayBtnTotal">${money(totalBalance)}</span>)</button>
      </div>
    </form>`
  );

  const amountInput = host.querySelector('#multiPayAmountInput');
  const advNotice = host.querySelector('#multiPayAdvanceNotice');
  const btnTotal = host.querySelector('#multiPayBtnTotal');

  amountInput.oninput = () => {
    const val = Number(amountInput.value || 0);
    if (btnTotal) btnTotal.textContent = money(val);
    if (val > totalBalance) {
      const extra = val - totalBalance;
      advNotice.style.display = 'block';
      advNotice.textContent = `✓ Full dues settled + Rs. ${money(extra)} surplus credited as Advance!`;
    } else {
      advNotice.style.display = 'none';
    }
  };

  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.bill_ids = billIds;
    payload.amount = Number(payload.amount);
    payload.discount = Number(payload.discount || 0);
    payload.account_id = payload.account_id ? Number(payload.account_id) : null;
    try {
      const resp = await api('/bills/pay-multiple', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      let msg = `Payment of Rs. ${money(payload.amount)} recorded successfully!\n• Settled / updated bills: ${resp.updated_bills?.length || 0}`;
      if (resp.advance_amount > 0) {
        msg += `\n• Advance surplus credited: Rs. ${money(resp.advance_amount)}`;
      }
      if (window._selectedBillIds) window._selectedBillIds.clear();
      alert(msg);
      host.remove();
      go('bills');
    } catch (error) {
      showError(error);
    }
  };
}

function exportBills() { csvDownload('due-bills.csv', window._bills || [], (window._billColumns || []).filter(c => c.key !== 'select_bill' && !c.isCheckbox && c.key !== 'pay')); }
async function billGenerationForm() {
  const enrollmentsRows = await api('/enrollments');
  const host = modal('Generate due bills', `<form class="form two-col"><label class="span-2">Enrollments *<select name="enrollment_ids" multiple size="9">${enrollmentsRows.filter(row => row.status === 'Active').map(row => `<option value="${row.id}">${esc(row.student_name)} — ${esc(row.course_name)} (${esc(row.level || '')})</option>`).join('')}</select><small>Use Ctrl or Shift to select several enrollments.</small></label><label>Start month (BS) *<input name="start_month" placeholder="2083/05" required></label><label>End month (BS) *<input name="end_month" placeholder="2083/05" required></label><label>Issue date (BS) *<input name="issue_date" placeholder="2083/05/10" required></label><label>Due date (BS) *<input name="due_date" placeholder="2083/05/15" required></label><label class="span-2">Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Generate</button></div></form>`);
  host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.enrollment_ids = [...event.target.elements.enrollment_ids.selectedOptions].map(option => Number(option.value)); try { const result = await api('/bills/generate', { method: 'POST', body: JSON.stringify(payload) }); alert(`${result.created} bill(s) generated.`); host.remove(); go('bills'); } catch (error) { showError(error); } };
}
async function billPayment(id) {
  const data = await getLookups();
  const bill = (window._bills || []).find(row => row.id === id);
  const otherUnpaid = (window._bills || []).filter(row => row.id !== id && row.student_name === bill?.student_name && row.balance > 0);

  const multiplePromptHtml = otherUnpaid.length > 0 ? `
    <div class="span-2" style="padding:8px 12px;background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;margin-bottom:8px;font-size:12px;color:#92400e;display:flex;justify-content:space-between;align-items:center;gap:8px;">
      <span>⚠️ <b>${esc(bill?.student_name)}</b> has <b>${otherUnpaid.length}</b> other unpaid bill(s) (Combined Due: <b>Rs. ${money((Number(bill?.balance) || 0) + otherUnpaid.reduce((s, r) => s + Number(r.balance || 0), 0))}</b>).</span>
      <button type="button" class="small primary" style="background:#d97706;border-color:#d97706;white-space:nowrap;" onclick="this.closest('.modal').remove(); multiBillPaymentModal([${[id, ...otherUnpaid.map(r => r.id)].join(',')}]);">Pay All Together</button>
    </div>
  ` : '';

  const host = modal(
    `Receive payment — ${bill?.bill_number || ''}`,
    `<form class="form two-col">
      ${multiplePromptHtml}
      <div class="span-2" style="padding:6px 10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:6px;">
        Student: <b>${esc(bill?.student_name || '')}</b> · Course: <b>${esc(bill?.course_name || '')}</b> · Period: <b>${esc(bill?.billing_period || '')}</b><br>
        Current Bill Balance: <b style="color:#d97706;">Rs. ${money(bill?.balance || 0)}</b>
      </div>
      <label>Payment amount *
        <input name="amount" id="singlePayAmountInput" type="number" min="0" step="0.01" value="${bill?.balance || 0}" required>
        <small id="singlePayAdvanceNotice" style="display:none;color:#16a34a;font-weight:600;margin-top:2px;"></small>
      </label>
      <label>Discount
        <input name="discount" type="number" min="0" step="0.01" value="0">
      </label>
      <label>Payment date (BS) *
        <input name="payment_date" placeholder="2083/05/10" required>
      </label>
      <label>Account *
        <select name="account_id" required>
          <option value="">Select account</option>
          ${selectOptions(data.accounts, 'id', row => `${row.account_name} (${row.account_type})`)}
        </select>
      </label>
      <label>Method
        <select name="payment_method">
          <option>Cash</option>
          <option>Bank</option>
          <option>Wallet</option>
          <option>Other</option>
        </select>
      </label>
      <label>Receipt no.
        <input name="receipt_no">
      </label>
      <label class="span-2">Remarks
        <input name="remarks" placeholder="Optional notes">
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Receive payment</button>
      </div>
    </form>`
  );

  const amountInput = host.querySelector('#singlePayAmountInput');
  const advNotice = host.querySelector('#singlePayAdvanceNotice');
  const billBal = Number(bill?.balance || 0);

  amountInput.oninput = () => {
    const val = Number(amountInput.value || 0);
    if (val > billBal) {
      advNotice.style.display = 'block';
      advNotice.textContent = `✓ Full bill settled + Rs. ${money(val - billBal)} surplus credited as Advance!`;
    } else {
      advNotice.style.display = 'none';
    }
  };

  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.amount = Number(payload.amount);
    payload.discount = Number(payload.discount || 0);
    payload.account_id = payload.account_id ? Number(payload.account_id) : null;
    try {
      const resp = await api(`/bills/${id}/payment`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      let msg = `Payment recorded successfully! Bill marked ${resp.status}.`;
      if (resp.advance_amount > 0) {
        msg += `\n• Advance surplus credited: Rs. ${money(resp.advance_amount)}`;
        alert(msg);
      }
      host.remove();
      go('bills');
    } catch (error) {
      showError(error);
    }
  };
}

async function attendance() {
  if (me?.role === 'student') {
    go('student-profile');
    setTimeout(() => switchProfileTab('attendance'), 50);
    return;
  }
  const [present, absent, alerts, punched, poller] = await Promise.all([
    api('/attendance/present-today').catch(() => []),
    api('/attendance/absent-today').catch(() => []),
    api('/attendance/alerts').catch(() => []),
    api('/attendance/punched-not-enrolled').catch(() => []),
    api('/attendance/poller/status').catch(() => null),
  ]);

  const presentList = Array.isArray(present) ? present : [];
  const absentList = Array.isArray(absent) ? absent : [];
  const alertsList = Array.isArray(alerts) ? alerts : [];
  const punchedList = Array.isArray(punched) ? punched : [];

  const presentCount = presentList.length;
  const absentCount = absentList.length;
  const totalTracked = presentCount + absentCount;
  const presentPercent = totalTracked > 0 ? Math.round((presentCount / totalTracked) * 100) : 0;
  const absentPercent = totalTracked > 0 ? Math.round((absentCount / totalTracked) * 100) : 0;

  const pollerText = poller ? `Auto-sync: ${poller.running ? `Active (${poller.interval_seconds}s)` : 'Disabled'} · Last: ${poller.last_polled_at || 'Never'} · Imported: ${poller.total_saved_count || 0}` : '';

  const metricCards = [
    {
      label: 'Students Present Today',
      value: `${presentCount}`,
      badge: `<span class="badge active" style="font-size:12px;font-weight:700;background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.25);">${presentPercent}% Present</span>`,
      sub: `${presentCount} students verified with biometric / manual punch`,
      icon: uiIcon('user-check', 22, 'color:#10b981;'),
      onClick: "document.querySelector('#presentStudentsSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'Students Absent Today',
      value: `${absentCount}`,
      badge: `<span class="badge" style="font-size:12px;font-weight:700;background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.25);">${absentPercent}% Absent</span>`,
      sub: `${absentCount} students absent without punch today`,
      icon: uiIcon('user-x', 22, 'color:#ef4444;'),
      onClick: "document.querySelector('#absentStudentsSection')?.scrollIntoView({behavior:'smooth'})"
    },
    {
      label: 'Total Expected Students',
      value: `${totalTracked}`,
      badge: `<span class="badge" style="font-size:12px;font-weight:700;background:rgba(59,130,246,0.15);color:#3b82f6;border:1px solid rgba(59,130,246,0.25);">Active Cohort</span>`,
      sub: `${presentPercent}% overall student attendance rate today`,
      icon: uiIcon('students', 22, 'color:#3b82f6;')
    },
    {
      label: 'Follow-up Alerts',
      value: `${alertsList.length}`,
      badge: alertsList.length ? `<span class="badge" style="font-size:12px;font-weight:700;background:rgba(245,158,11,0.15);color:#d97706;border:1px solid rgba(245,158,11,0.25);">Action Needed</span>` : `<span class="badge active" style="font-size:12px;font-weight:700;background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.25);">Clear</span>`,
      sub: alertsList.length ? `${alertsList.length} students with consecutive absences / irregularities` : 'All student attendance patterns normal',
      icon: uiIcon('alert-triangle', 22, 'color:#d97706;'),
      onClick: "document.querySelector('#attendanceAlertsSection')?.scrollIntoView({behavior:'smooth'})"
    }
  ];

  const cardsHtml = `
    <div class="cards" style="margin-bottom:24px;">
      ${metricCards.map(c => `
        <div class="card" ${c.onClick ? `onclick="${c.onClick}" style="cursor:pointer;" title="Click to view details"` : ''}>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span>${esc(c.label)}</span>
            <div class="card-icon">
              ${c.icon}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
            <b style="font-size:24px;">${esc(c.value)}</b>
            ${c.badge || ''}
          </div>
          <small class="muted">${esc(c.sub)}</small>
        </div>
      `).join('')}
    </div>
  `;

  const presentSectionHtml = `
    <section class="panel" id="presentStudentsSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('user-check', 20, 'color:#10b981;')}
            Students Present Today
            <span class="badge active" style="font-size:12px;font-weight:700;padding:2px 8px;">${presentCount} Present</span>
          </h2>
          <small class="muted">Students verified by biometric device or manual attendance entry for today (${presentPercent}% of enrolled)</small>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="ghost small" onclick="document.querySelector('#absentStudentsSection')?.scrollIntoView({behavior:'smooth'})" style="display:inline-flex;align-items:center;gap:6px;">
            ${uiIcon('user-x', 14, 'color:#ef4444;')} View Absent Students (${absentCount})
          </button>
        </div>
      </div>
      ${presentList.length ? table(presentList, [
        { key: 'student_name', label: 'Student' },
        { key: 'class_name', label: 'Class' },
        { key: 'punches', label: 'Punches' },
        { key: 'first_seen', label: 'First Punch', render: row => humanTime(row.first_seen) },
        { key: 'last_seen', label: 'Last Punch', render: row => humanTime(row.last_seen) }
      ]) : '<p class="muted" style="padding:14px 0;margin:0;">No students recorded as present today yet.</p>'}
    </section>
  `;

  const absentSectionHtml = `
    <section class="panel" id="absentStudentsSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('user-x', 20, 'color:#ef4444;')}
            Students Absent Today
            <span class="badge" style="background:rgba(239,68,68,0.15);color:#ef4444;font-size:12px;font-weight:700;padding:2px 8px;">${absentCount} Absent</span>
          </h2>
          <small class="muted">Active enrolled students without a presence record today (${absentPercent}% absence rate)</small>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="ghost small" onclick="document.querySelector('#presentStudentsSection')?.scrollIntoView({behavior:'smooth'})" style="display:inline-flex;align-items:center;gap:6px;">
            ${uiIcon('user-check', 14, 'color:#10b981;')} View Present Students (${presentCount})
          </button>
        </div>
      </div>
      ${absentList.length ? table(absentList, [
        { key: 'student_name', label: 'Student' },
        { key: 'class_name', label: 'Class' },
        { key: 'courses', label: 'Course(s)' },
        { key: 'last_seen', label: 'Last Attendance', render: row => humanTime(row.last_seen) },
        { key: 'device_status', label: 'Device Status' }
      ]) : '<p class="muted" style="padding:14px 0;margin:0;">No absences recorded today! Perfect attendance.</p>'}
    </section>
  `;

  const alertsSectionHtml = `
    <section class="panel" id="attendanceAlertsSection" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            ${uiIcon('alert-triangle', 20, 'color:#d97706;')}
            Attendance Follow-up Alerts
            <span class="badge" style="background:rgba(245,158,11,0.15);color:#d97706;font-size:12px;font-weight:700;padding:2px 8px;">${alertsList.length} Active</span>
          </h2>
          <small class="muted">Students triggering consecutive absence alerts or attendance irregularity reviews</small>
        </div>
      </div>
      ${table(alertsList, [
        { key: 'student_name', label: 'Student' },
        { key: 'class_name', label: 'Class' },
        { key: 'reason', label: 'Reason' },
        { key: 'review_status', label: 'Status' },
        { key: 'review', label: 'Action', render: row => `<button onclick="attendanceReviewForm(${row.student_id}, '${esc(row.student_name)}')">Review</button>` }
      ])}
    </section>
  `;

  const punchedSectionHtml = `
    <section class="panel" id="punchedStudentsSection">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div>
          <h2 style="margin:0;display:flex;align-items:center;gap:8px;font-size:18px;">
            Punched but Not Enrolled
            <span class="badge" style="font-size:12px;font-weight:700;padding:2px 8px;">${punchedList.length}</span>
          </h2>
          <small class="muted">Device punches from students without active course enrollments</small>
        </div>
      </div>
      ${punchedList.length ? table(punchedList, [
        { key: 'student_name', label: 'Student' },
        { key: 'class_name', label: 'Class' },
        { key: 'punches', label: 'Punches' },
        { key: 'last_seen', label: 'Last Punch', render: row => humanTime(row.last_seen) }
      ]) : '<p class="muted" style="padding:14px 0;margin:0;">No un-enrolled punches found.</p>'}
    </section>
  `;

  shell(
    'Attendance',
    'Daily presence, manual corrections, and follow-up review',
    `${toolbar([action('Sync device now', 'triggerAttendanceSync()', true), action('Mark manual presence', 'manualAttendanceForm()'), action('Show suppressed alerts', 'attendanceAlerts(true)')], pollerText)}${cardsHtml}${presentSectionHtml}${absentSectionHtml}${alertsSectionHtml}${punchedSectionHtml}`
  );
}
async function triggerAttendanceSync() {
  try {
    const result = await api('/attendance/poller/trigger', { method: 'POST' });
    alert(`Sync completed successfully.\nPunches received: ${result.received}\nNew punches saved: ${result.saved}\nUnmapped punches: ${result.unmapped}`);
    go('attendance');
  } catch (error) {
    showError(error);
  }
}
async function attendanceAlerts(includeSuppressed) { const rows = await api(`/attendance/alerts?include_suppressed=${includeSuppressed}`); modal('Attendance follow-up alerts', table(rows, [{ key: 'student_name', label: 'Student' }, { key: 'reason', label: 'Reason' }, { key: 'review_status', label: 'Status' }, { key: 'follow_up_date', label: 'Resume date' }, { key: 'review_note', label: 'Note' }])); }
async function manualAttendanceForm() { const people = await api('/attendance/people'); const studentsRows = people.students; const staffRows = people.staff; const host = modal('Mark manual attendance', `<form class="form two-col"><label>Person type<select name="person_type" onchange="switchManualPeople(this.value)"><option value="student">Student</option><option value="teacher">Staff</option></select></label><label>Student / staff<select name="person_id" id="manualPerson">${selectOptions(studentsRows, 'id', row => row.student_name)}</select></label><label>Attendance date (BS) *<input name="attendance_date" placeholder="2083/05/10" required></label><label>Time *<input name="attendance_time" placeholder="6:00 PM" required></label><label class="span-2">Reason *<input name="reason" required value="Device attendance missed"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Mark present</button></div></form>`); window._manualPeople = { student: studentsRows.map(row => ({ id: row.id, label: row.student_name })), teacher: staffRows.map(row => ({ id: row.id, label: row.teacher_name })) }; host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.person_id = Number(payload.person_id); try { const result = await api('/attendance/manual', { method: 'POST', body: JSON.stringify(payload) }); alert(result.created ? 'Manual presence recorded.' : 'Attendance was already recorded for this person today.'); host.remove(); go('attendance'); } catch (error) { showError(error); } }; }
function switchManualPeople(type) { const select = document.querySelector('#manualPerson'); select.innerHTML = (window._manualPeople?.[type] || []).map(row => `<option value="${row.id}">${esc(row.label)}</option>`).join(''); }
function attendanceReviewForm(studentId, name) { const host = modal(`Review follow-up — ${name}`, `<form class="form"><label>Status<select name="status"><option>Monitoring</option><option>Contacted</option><option>Approved Leave</option><option>Left Institution</option><option>No Action Needed</option><option>Suppressed</option></select></label><label>Resume / follow-up date (BS)<input name="follow_up_date" placeholder="2083/06/01"></label><label>Notes<input name="note"></label><div class="form-actions"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save review</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); try { await api(`/attendance/alerts/${studentId}/review`, { method: 'POST', body: JSON.stringify(formData(event.target)) }); host.remove(); go('attendance'); } catch (error) { showError(error); } }; }

async function courses() { const rows = await api('/courses?include_inactive=true'); const cols = [{ key: 'course_name', label: 'Course' }, { key: 'category', label: 'Category' }, { key: 'billing_type', label: 'Billing' }, { key: 'default_fee', label: 'Fee', render: row => money(row.default_fee) }, { key: 'duration_months', label: 'Months' }, { key: 'instructor_name', label: 'Instructor' }, { key: 'status', label: 'Status' }]; shell('Courses', 'Reusable course definitions and billing defaults', `${toolbar([action('Add course', 'courseForm()', true), action('Export CSV', 'exportCourses()')])}${table(rows, cols)}`); window._courses = rows; window._courseCols = cols; }
function exportCourses() { csvDownload('courses.csv', window._courses || [], window._courseCols || []); }
function courseForm() { const host = modal('Add course', `<form class="form two-col"><label>Course name *<input name="course_name" required></label><label>Category *<input name="category" required value="Tuition"></label><label>Billing type<select name="billing_type"><option>Monthly</option><option>Course Complete</option></select></label><label>Default fee<input name="default_fee" type="number" min="0" value="0"></label><label>Duration months<input name="duration_months" type="number" min="0" value="0"></label><label>Instructor name<input name="instructor_name"></label><label>Status<select name="status"><option>Active</option><option>Inactive</option></select></label><label>Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save course</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.default_fee = Number(payload.default_fee); payload.duration_months = Number(payload.duration_months); try { await api('/courses', { method: 'POST', body: JSON.stringify(payload) }); host.remove(); go('courses'); } catch (error) { showError(error); } }; }
async function schools() { const rows = await api('/schools?include_inactive=true'); const cols = [{ key: 'school_name', label: 'School' }, { key: 'emis_id', label: 'EMIS ID' }, { key: 'address', label: 'Address' }, { key: 'contact', label: 'Contact' }, { key: 'status', label: 'Status' }]; shell('Schools', 'Schools linked to student records', `${toolbar([action('Add school', 'schoolForm()', true), action('Export CSV', 'exportSchools()')])}${table(rows, cols)}`); window._schools = rows; window._schoolCols = cols; }
function exportSchools() { csvDownload('schools.csv', window._schools || [], window._schoolCols || []); }
function schoolForm() { const host = modal('Add school', `<form class="form two-col"><label>School name *<input name="school_name" required></label><label>EMIS ID<input name="emis_id"></label><label>Contact<input name="contact"></label><label>Status<select name="status"><option>Active</option><option>Inactive</option></select></label><label class="span-2">Address<input name="address"></label><label class="span-2">Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save school</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); try { await api('/schools', { method: 'POST', body: JSON.stringify(formData(event.target)) }); lookups = null; host.remove(); go('schools'); } catch (error) { showError(error); } }; }

async function staff() {
  const rows = await api('/staff');
  const cols = [
    { key: 'teacher_name', label: 'Staff' },
    { key: 'staff_type', label: 'Type' },
    { key: 'contact', label: 'Contact' },
    { key: 'subject', label: 'Subject' },
    { key: 'salary_type', label: 'Salary basis' },
    { key: 'basic_salary', label: 'Rate', render: row => money(row.basic_salary) },
    { key: 'status', label: 'Status' },
    {
      key: 'actions',
      label: 'Actions',
      render: row => `
        <div style="display:flex;gap:4px;align-items:center;">
          ${has('administration.manage') ? `<button class="primary" style="padding:3px 8px;font-size:11px;" onclick="openCreateUserForStaff(${row.id})" title="Create or manage user account">User</button>` : ''}
        </div>
      `
    }
  ];
  shell('Staff', 'Teaching and non-teaching staff with payment-account tracking', `${toolbar([action('Add staff', 'staffForm()', true), action('Export CSV', 'exportStaff()')])}${table(rows, cols)}`);
  window._staff = rows;
  window._staffCols = cols;
}
function exportStaff() { csvDownload('staff.csv', window._staff || [], window._staffCols || []); }
function staffForm() { const host = modal('Add staff', `<form class="form two-col"><label>Name *<input name="teacher_name" required></label><label>Staff type<select name="staff_type"><option>Teaching</option><option>Non Teaching</option></select></label><label>Contact<input name="contact"></label><label>Email<input name="email"></label><label>Subject / role<input name="subject"></label><label>Qualification<input name="qualification"></label><label>Joined date (BS) *<input name="joined_date" placeholder="2083/05/10" required></label><label>Salary type<select name="salary_type"><option>Monthly Salary</option><option>Per Class Payment</option></select></label><label>Basic salary / rate<input name="basic_salary" type="number" min="0" value="0"></label><label>Status<select name="status"><option>Active</option><option>Inactive</option></select></label><label class="span-2">Address<input name="address"></label><label class="span-2">Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save staff</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.basic_salary = Number(payload.basic_salary); try { await api('/staff', { method: 'POST', body: JSON.stringify(payload) }); host.remove(); go('staff'); } catch (error) { showError(error); } }; }

async function finance() { const [accounts, incomeRows, expenseRows, ledgerRows] = await Promise.all([api('/accounts'), api('/income'), api('/expenses'), api('/ledger')]); shell('Finance', 'Accounts, income, expenses, and current ledger', `${toolbar([action('Add account', 'accountForm()', true), action('Record income', 'moneyForm("income")'), action('Record expense', 'moneyForm("expenses")')])}<section class="panel"><h2>Accounts</h2>${table(accounts, [{ key: 'account_name', label: 'Account' }, { key: 'account_type', label: 'Type' }, { key: 'balance', label: 'Current balance', render: row => money(row.balance) }, { key: 'status', label: 'Status' }])}</section><section class="panel"><h2>Income</h2>${table(incomeRows, [{ key: 'income_date', label: 'Date' }, { key: 'category', label: 'Category' }, { key: 'particular', label: 'Particular' }, { key: 'amount', label: 'Amount', render: row => money(row.amount) }, { key: 'account_name', label: 'Account' }])}</section><section class="panel"><h2>Expenses</h2>${table(expenseRows, [{ key: 'expense_date', label: 'Date' }, { key: 'category', label: 'Category' }, { key: 'particular', label: 'Particular' }, { key: 'amount', label: 'Amount', render: row => money(row.amount) }, { key: 'account_name', label: 'Account' }, { key: 'payee_name', label: 'Payee' }])}</section><section class="panel"><h2>Ledger</h2>${table(ledgerRows, [{ key: 'transaction_date', label: 'Date' }, { key: 'account_name', label: 'Account' }, { key: 'direction', label: 'Direction' }, { key: 'amount', label: 'Amount', render: row => money(row.amount) }, { key: 'particular', label: 'Particular' }, { key: 'reference_no', label: 'Reference' }])}</section>`); }
function accountForm() { const host = modal('Add account', `<form class="form two-col"><label>Account name *<input name="account_name" required></label><label>Type<select name="account_type"><option>Cash Counter</option><option>Bank Account</option><option>Personal Account</option><option>Wallet</option><option>Other</option></select></label><label>Bank name<input name="bank_name"></label><label>Account no.<input name="account_number"></label><label>Account holder<input name="account_holder"></label><label>Opening balance<input name="opening_balance" type="number" value="0"></label><label>Status<select name="status"><option>Active</option><option>Inactive</option></select></label><label>Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save account</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.opening_balance = Number(payload.opening_balance); try { await api('/accounts', { method: 'POST', body: JSON.stringify(payload) }); lookups = null; host.remove(); go('finance'); } catch (error) { showError(error); } }; }
async function moneyForm(type) { const data = await getLookups(); const heading = type === 'income' ? 'Record income' : 'Record expense'; const host = modal(heading, `<form class="form two-col"><label>Date (BS) *<input name="record_date" placeholder="2083/05/10" required></label><label>Category *<input name="category" required></label><label class="span-2">Particular *<input name="particular" required></label><label>Amount *<input name="amount" type="number" min="0.01" step="0.01" required></label><label>${type === 'income' ? 'Received in account' : 'Paid from account'} *<select name="account_id">${selectOptions(data.accounts, 'id', row => row.account_name)}</select></label><label>${type === 'income' ? 'Received from' : 'Paid to'}<input name="party"></label><label>Payment method<select name="payment_method"><option>Cash</option><option>Bank</option><option>Wallet</option><option>Other</option></select></label><label>Reference no.<input name="reference_no"></label><label>Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save ${type}</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.amount = Number(payload.amount); payload.account_id = Number(payload.account_id); try { await api(`/${type}`, { method: 'POST', body: JSON.stringify(payload) }); host.remove(); go('finance'); } catch (error) { showError(error); } }; }

async function tasks() { const [taskRows, bugRows] = await Promise.all([api('/tasks'), api('/bug-reports')]); const taskCols = [{key:'title',label:'Task'}, {key:'assigned_to',label:'Assigned to'}, {key:'due_date',label:'Due date'}, {key:'priority',label:'Priority'}, {key:'status',label:'Status'}, {key:'done',label:'Action',render: row => row.status === 'Done' ? '' : `<button onclick="completeTask(${row.id})">Mark done</button>`}]; const bugCols = [{key:'title',label:'Issue'}, {key:'page_name',label:'Screen'}, {key:'severity',label:'Severity'}, {key:'status',label:'Status'}, {key:'reported_by',label:'Reported by'}, {key:'created_at',label:'Reported'}]; shell('Tasks & Bugs', 'Assign follow-ups to staff and maintain a clear issue register', `${toolbar([action('New task','taskForm()',true),action('Report a bug','bugForm()')])}<section class="panel"><h2>Tasks</h2>${table(taskRows, taskCols)}</section><section class="panel"><h2>Bug reports</h2>${table(bugRows, bugCols)}</section>`); }
async function taskForm() { const people = await api('/attendance/people'); const host = modal('New task', `<form class="form two-col"><label class="span-2">Task *<input name="title" required></label><label>Assign to staff<select name="assigned_teacher_id"><option value="">Unassigned</option>${selectOptions(people.staff,'id',row=>row.teacher_name)}</select></label><label>Due date (BS)<input name="due_date" placeholder="2083/05/10"></label><label>Priority<select name="priority"><option>Low</option><option selected>Normal</option><option>High</option></select></label><label class="span-2">Details<input name="details"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save task</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); payload.assigned_teacher_id = payload.assigned_teacher_id ? Number(payload.assigned_teacher_id) : null; try { await api('/tasks',{method:'POST',body:JSON.stringify(payload)}); host.remove(); go('tasks'); } catch(error) { showError(error); } }; }
async function completeTask(id) { try { await api(`/tasks/${id}/complete`,{method:'POST'}); go('tasks'); } catch(error) { showError(error); } }
function bugForm() { const host = modal('Report a bug', `<form class="form"><label>What happened? *<input name="title" required></label><label>Screen / page<input name="page_name" value="${esc(location.hash.slice(1) || 'dashboard')}"></label><label>Severity<select name="severity"><option>Low</option><option selected>Normal</option><option>High</option><option>Critical</option></select></label><label>Details / steps to repeat *<textarea name="details" required rows="5"></textarea></label><div class="form-actions"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Submit report</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); try { await api('/bug-reports',{method:'POST',body:JSON.stringify(formData(event.target))}); host.remove(); alert('Bug report saved for follow-up.'); go('tasks'); } catch(error) { showError(error); } }; }
async function transfers() { const rows = await api('/transfers'); const cols = [{key:'transfer_date',label:'Date'}, {key:'from_account',label:'From'}, {key:'to_account',label:'To'}, {key:'amount',label:'Amount',render:row=>money(row.amount)}, {key:'transfer_charge',label:'Charge',render:row=>money(row.transfer_charge)}, {key:'reference_no',label:'Reference'}]; shell('Account Transfers','Move money safely between institution accounts',`${toolbar([action('New transfer','transferForm()',true)])}${table(rows,cols)}`); }
async function transferForm() { const data = await getLookups(); const options = `<option value="">Select account</option>${selectOptions(data.accounts,'id',row=>`${row.account_name} (${row.account_type})`)}`; const host = modal('Transfer between accounts', `<form class="form two-col"><label>Date (BS) *<input name="transfer_date" placeholder="2083/05/10" required></label><label>Amount *<input name="amount" type="number" min="0.01" step="0.01" required></label><label>From account *<select name="from_account_id" required>${options}</select></label><label>To account *<select name="to_account_id" required>${options}</select></label><label>Transfer charge<input name="transfer_charge" type="number" min="0" step="0.01" value="0"></label><label>Reference no.<input name="reference_no"></label><label class="span-2">Remarks<input name="remarks"></label><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Transfer money</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload = formData(event.target); ['from_account_id','to_account_id'].forEach(key=>payload[key]=Number(payload[key])); ['amount','transfer_charge'].forEach(key=>payload[key]=Number(payload[key])); try { await api('/transfers',{method:'POST',body:JSON.stringify(payload)}); host.remove(); lookups=null; go('transfers'); } catch(error) { showError(error); } }; }
async function calendar() { const month = new URLSearchParams(location.hash.split('?')[1] || '').get('month') || ''; const data = await api(`/academic-calendar${month ? `?month=${encodeURIComponent(month)}` : ''}`); const weekdayIndex = {Sunday:0,Monday:1,Tuesday:2,Wednesday:3,Thursday:4,Friday:5,Saturday:6}; const leading = data.days.length ? '<div class="calendar-day empty" aria-hidden="true"></div>'.repeat(weekdayIndex[data.days[0].day_name] ?? 0) : ''; const cells = leading + data.days.map(day => { const eventText = day.events.map(event => `<span>${esc(event.event_name)}${event.course_name ? ` · ${esc(event.course_name)}` : ''}</span>`).join(''); return `<div class="calendar-day ${day.closed ? 'closed' : ''}"><b>${day.day}</b><small>${esc(day.day_name.slice(0,3))}</small>${eventText}</div>`; }).join(''); const eventCols = [{key:'event_name',label:'Event'}, {key:'course_name',label:'Course',render:row=>row.course_name || 'All courses'}, {key:'event_type',label:'Type'}, {key:'start_date',label:'Start'}, {key:'end_date',label:'End'}, {key:'status',label:'Status'}, {key:'remarks',label:'Remarks'}]; shell('Academic Calendar','Holidays and closures are excluded from attendance absence alerts',`${toolbar([`<input id="calendarMonth" value="${esc(data.month)}" placeholder="2083/05">`,action('Open month','openCalendarMonth()'),...(has('master_data.manage')?[action('Add calendar event','calendarEventForm()',true)]:[])])}<section class="panel"><h2>${esc(data.month)} calendar</h2><div class="calendar-weekdays"><b>Sun</b><b>Mon</b><b>Tue</b><b>Wed</b><b>Thu</b><b>Fri</b><b>Sat</b></div><div class="calendar-grid">${cells}</div><p class="muted small">Red dates are holidays or closures. Course-specific holidays only affect students enrolled in that course.</p></section><section class="panel"><h2>Calendar events</h2>${table(data.events,eventCols)}</section>`); }
function openCalendarMonth() { const month = document.querySelector('#calendarMonth').value.trim(); if (!/^\d{4}\/\d{2}$/.test(month)) return showError(new Error('Enter the month as YYYY/MM.')); go(`calendar?month=${month}`); }
async function calendarEventForm() { let courses=[]; try { courses=await api('/academic-calendar/courses'); } catch(error) { showError(error); return; } const current=document.querySelector('#calendarMonth')?.value || ''; const options=`<option value="">All courses (institution-wide)</option>${selectOptions(courses,'id',row=>row.course_name)}`; const host = modal('Add calendar event', `<form class="form two-col"><label class="span-2">Event name *<input name="event_name" required placeholder="Public holiday / institute closure"></label><label>Applies to course<select name="course_id">${options}</select></label><label>Type<select name="event_type"><option>Holiday</option><option>Closure</option><option>Working Day</option><option>Event</option></select></label><label>Start date (BS) *<input name="start_date" required placeholder="2083/05/10"></label><label>End date (BS)<input name="end_date" placeholder="Same day if blank"></label><label>Status<select name="status"><option>Active</option><option>Inactive</option></select></label><label class="span-2">Remarks<input name="remarks"></label><fieldset class="span-2 checkbox-row"><legend>Bulk weekend closure (optional)</legend><label>Month <input name="weekend_month" value="${esc(current)}" placeholder="2083/05"></label><label><input type="checkbox" name="weekend_days" value="Saturday"> Saturday</label><label><input type="checkbox" name="weekend_days" value="Sunday"> Sunday</label></fieldset><p class="span-2 muted small">Leave course empty for an institution-wide event. Select Saturday or Sunday above to add that weekend day throughout the selected month; the individual event dates are then ignored.</p><div class="form-actions span-2"><button type="button" onclick="this.closest('.modal').remove()">Cancel</button><button class="primary">Save event</button></div></form>`); host.querySelector('form').onsubmit = async event => { event.preventDefault(); const payload=formData(event.target); payload.course_id=payload.course_id ? Number(payload.course_id) : null; const weekend_days=[...event.target.querySelectorAll('input[name="weekend_days"]:checked')].map(input=>input.value); try { if (weekend_days.length) { const result=await api('/academic-calendar/bulk-weekends',{method:'POST',body:JSON.stringify({month:payload.weekend_month,course_id:payload.course_id,weekend_days,event_type:payload.event_type==='Closure'?'Closure':'Holiday',remarks:payload.remarks})}); host.remove(); alert(`${result.created} weekend event(s) added.`); go(`calendar?month=${encodeURIComponent(result.month)}`); return; } await api('/academic-calendar',{method:'POST',body:JSON.stringify(payload)}); host.remove(); go('calendar'); } catch(error) { showError(error); } }; }
async function reports() { shell('Reports', 'Export any operational table to CSV or print the current view from your browser', `<section class="panel"><h2>Operational reports</h2><p>Use the Export CSV action in Students, Enrollments, Due Bills, Courses, Schools, and Staff to download the current operational data. Use your browser’s Print command for a paper/PDF copy of the current view.</p>${toolbar([action('Print this page', 'window.print()', true)])}</section>`); }
async function company() { const data = await api('/company-profile'); const html = `<form id="companyForm" class="form two-col"><label>Company name *<input name="company_name" required value="${esc(data.company_name || '')}"></label><label>PAN no.<input name="pan_number" value="${esc(data.pan_number || '')}"></label><label>Registration no.<input name="registration_number" value="${esc(data.registration_number || '')}"></label><label>Principal / Director<input name="principal_name" value="${esc(data.principal_name || '')}"></label><label>Phone<input name="phone" value="${esc(data.phone || '')}"></label><label>Email<input name="email" value="${esc(data.email || '')}"></label><label class="span-2">Website<input name="website" value="${esc(data.website || '')}"></label><label class="span-2">Address<input name="address" value="${esc(data.address || '')}"></label><label class="span-2">Report footer<input name="report_footer" value="${esc(data.report_footer || '')}"></label><div class="form-actions span-2"><button class="primary">Save company details</button></div></form>`; shell('Company Details', 'Organisation information used by reports, bills, and certificates', `<section class="panel">${html}</section>`); document.querySelector('#companyForm').onsubmit = async event => { event.preventDefault(); try { await api('/company-profile', { method: 'PUT', body: JSON.stringify(formData(event.target)) }); alert('Company details saved.'); } catch (error) { showError(error); } }; }

function changePasswordModal() {
  const host = modal('Change Password', `
    <form class="form">
      <label>Current password *<input type="password" name="current_password" required></label>
      <label>New password (min 6 chars) *<input type="password" name="new_password" required minlength="6"></label>
      <label>Confirm new password *<input type="password" name="confirm_password" required minlength="6"></label>
      <div class="form-actions">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Update password</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    if (payload.new_password !== payload.confirm_password) {
      alert('New password and confirmation do not match.');
      return;
    }
    try {
      await api('/auth/change-password', { method: 'POST', body: JSON.stringify(payload) });
      host.remove();
      alert('Password updated successfully.');
    } catch (error) {
      showError(error);
    }
  };
}

let assistantHistory = [];
async function assistant() {
  if (me?.role !== 'super_admin' && me?.role !== 'admin') {
    shell(
      'Access Denied',
      'Feature restricted',
      `
        <div class="panel" style="max-width:520px;margin:40px auto;text-align:center;padding:36px 24px;">
          <div style="width:48px;height:48px;border-radius:50%;background:var(--danger-light);color:var(--danger);display:flex;align-items:center;justify-content:center;margin:0 auto 16px;">
            ${uiIcon('lock', 24)}
          </div>
          <h2 style="margin:0 0 8px;color:var(--danger);">AI Assistant Access Restricted</h2>
          <p class="muted" style="margin-bottom:24px;font-size:14px;line-height:1.5;">The AI Assistant is an administrative feature reserved exclusively for Admin and Super Admin accounts.</p>
          <button class="primary" onclick="go('dashboard')">Return to Dashboard</button>
        </div>
      `
    );
    return;
  }
  const quickActions = [
    { label: 'Overview', cmd: '/stats', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>` },
    { label: 'Absent Today', cmd: '/absent', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/></svg>` },
    { label: 'Present Today', cmd: '/present', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>` },
    { label: 'Top Fee Dues', cmd: '/dues', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>` },
    { label: 'Accounts', cmd: '/accounts', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>` },
    { label: 'Courses', cmd: '/courses', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>` },
    { label: 'Staff', cmd: '/staff', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>` },
    { label: 'Health', cmd: '/health', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>` },
    { label: 'Poller Telemetry', cmd: '/poller', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/></svg>` },
    { label: 'Help', cmd: '/help', icon: `<svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>` },
  ];
  const quickButtons = quickActions.map(action =>
    `<button class="quick-cmd-btn" onclick="runAssistantCmd('${action.cmd}')">
      ${action.icon}
      <span class="cmd-label">${esc(action.label)}</span>
    </button>`
  ).join('');

  const renderMessages = () => {
    if (!assistantHistory.length) {
      return `<div class="assistant-entry"><div class="assistant-entry-header"><span>AI Assistant</span><span class="badge active">READY</span></div><pre>Welcome to the ELH AI Assistant! Type a query, ask for student or staff records, check fees, or click any quick command on the left.</pre></div>`;
    }
    return assistantHistory.map(entry => {
      let tableHtml = '';
      if (entry.data_rows && entry.data_rows.length) {
        const keys = Object.keys(entry.data_rows[0]);
        const cols = keys.map(k => ({ key: k, label: k.replace(/_/g, ' ').toUpperCase() }));
        tableHtml = `<div style="margin-top:10px;">${table(entry.data_rows, cols)}</div>`;
      }
      let chipsHtml = '';
      if (entry.suggested_actions && entry.suggested_actions.length) {
        chipsHtml = `<div class="action-chips">${entry.suggested_actions.map(act => `<span class="action-chip" onclick="runAssistantCmd('${esc(act)}')">${esc(act)}</span>`).join('')}</div>`;
      }
      const badgeCls = entry.badge === 'ERROR' ? 'inactive' : (entry.badge === 'WARNING' ? 'partial' : 'active');
      return `<div class="assistant-entry ${entry.isUser ? 'user' : ''}">
        <div class="assistant-entry-header">
          <span>${esc(entry.title || (entry.isUser ? 'You' : 'AI Assistant'))}</span>
          ${entry.badge ? `<span class="badge ${badgeCls}">${esc(entry.badge)}</span>` : ''}
        </div>
        <pre>${esc(entry.content)}</pre>
        ${tableHtml}
        ${chipsHtml}
      </div>`;
    }).join('');
  };

  const body = `
    <div class="assistant-workspace">
      <div class="quick-commands">
        <b style="color:var(--ink);margin-bottom:4px;font-size:12px;text-transform:uppercase;">Quick Commands</b>
        ${quickButtons}
        <button class="quick-cmd-btn clear-btn" onclick="clearAssistant()">
          <svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
          <span class="cmd-label">Clear History</span>
        </button>
      </div>
      <div class="assistant-console">
        <div class="assistant-messages" id="assistantMsgs">${renderMessages()}</div>
        <form class="assistant-form" id="assistantForm" onsubmit="handleAssistantSubmit(event)">
          <input class="assistant-input" id="assistantPrompt" placeholder="Ask anything (e.g. /stats, /absent, 'due for John', 'call 98...')" autocomplete="off" autofocus>
          <button class="primary" type="submit">Ask Assistant</button>
        </form>
      </div>
    </div>
  `;
  shell('AI Assistant', 'Safe, read-only operational intelligence and instant student/staff lookups', body);
  const msgDiv = document.querySelector('#assistantMsgs');
  if (msgDiv) msgDiv.scrollTop = msgDiv.scrollHeight;
}

function clearAssistant() {
  assistantHistory = [];
  assistant();
}

async function runAssistantCmd(cmd) {
  const promptInput = document.querySelector('#assistantPrompt');
  if (promptInput) promptInput.value = cmd;
  await sendAssistantQuery(cmd);
}

async function handleAssistantSubmit(event) {
  event.preventDefault();
  const input = document.querySelector('#assistantPrompt');
  const query = input.value.trim();
  if (!query) return;
  input.value = '';
  await sendAssistantQuery(query);
}

async function sendAssistantQuery(query) {
  assistantHistory.push({ isUser: true, title: 'You', content: query });
  assistant();
  try {
    const res = await api('/assistant/query', { method: 'POST', body: JSON.stringify({ prompt: query }) });
    assistantHistory.push({ isUser: false, title: res.title, content: res.content, badge: res.badge, data_rows: res.data_rows, suggested_actions: res.suggested_actions });
  } catch (error) {
    assistantHistory.push({ isUser: false, title: 'Error', content: error.message, badge: 'ERROR' });
  }
  assistant();
}

const certificateCols = [
  { key: 'id', label: 'ID' },
  { key: 'certificate_number', label: 'Certificate No.' },
  { key: 'student_name_snapshot', label: 'Student' },
  { key: 'course_name_snapshot', label: 'Course' },
  { key: 'certify_date', label: 'Certify Date' },
  { key: 'instructor_name', label: 'Instructor' },
  { key: 'actions', label: 'Actions', render: row => `
    <a href="/api/certificates/${row.id}/pdf?token=${encodeURIComponent(token)}" target="_blank"><button class="primary" style="padding:3px 8px;font-size:12px;">PDF</button></a>
    <a href="/api/certificates/${row.id}/docx?token=${encodeURIComponent(token)}"><button style="padding:3px 8px;font-size:12px;">DOCX</button></a>
    <button style="padding:3px 8px;font-size:12px;" onclick="regenerateCertificate(${row.id})">Regenerate</button>
  ` }
];

async function certificates() {
  const rows = await api('/certificates');
  const isStudent = me?.role === 'student';
  const cols = [
    { key: 'id', label: 'ID' },
    { key: 'certificate_number', label: 'Certificate No.' },
    ...(isStudent ? [] : [{ key: 'student_name_snapshot', label: 'Student' }]),
    { key: 'course_name_snapshot', label: 'Course' },
    { key: 'certify_date', label: 'Certify Date' },
    { key: 'instructor_name', label: 'Instructor' },
    { key: 'actions', label: 'Actions', render: row => `
      <a href="/api/certificates/${row.id}/pdf?token=${encodeURIComponent(token)}" target="_blank"><button class="primary" style="padding:3px 8px;font-size:12px;">Download PDF</button></a>
      ${isStudent ? '' : `
      <a href="/api/certificates/${row.id}/docx?token=${encodeURIComponent(token)}"><button style="padding:3px 8px;font-size:12px;">DOCX</button></a>
      <button style="padding:3px 8px;font-size:12px;" onclick="regenerateCertificate(${row.id})">Regenerate</button>
      `}
    ` }
  ];
  const tb = isStudent
    ? [action('Export CSV', 'exportCertificates()')]
    : [action('Issue certificate', 'certificateForm()', true), action('Export CSV', 'exportCertificates()')];

  shell(isStudent ? 'My Certificates' : 'Course Certificates', isStudent ? 'Official course completion certificates' : 'Issue and reproduce print-ready PDF and editable DOCX certificates', `
    ${toolbar(tb)}
    <div id="certTable">${table(rows, cols)}</div>
  `);
  window._certificates = rows;
  window._certCols = cols;
}

function exportCertificates() {
  csvDownload('certificates.csv', window._certificates || [], (window._certCols || certificateCols).slice(0, -1));
}

async function regenerateCertificate(id) {
  try {
    await api(`/certificates/${id}/regenerate-pdf`, { method: 'POST' });
    await api(`/certificates/${id}/regenerate-docx`, { method: 'POST' }).catch(() => {});
    alert('Certificate regenerated.');
    certificates();
  } catch (error) {
    showError(error);
  }
}

async function certificateForm() {
  const [available, nextNum] = await Promise.all([
    api('/certificates/available-enrollments'),
    api('/certificates/next-number'),
  ]);
  if (!available.length) {
    alert('No completed enrollments are currently awaiting certificates. Make sure the student enrollment status is set to "Completed" and has an end date.');
    return;
  }
  const enrollOptions = available.map(e =>
    `<option value="${e.enrollment_id}" data-instructor="${esc(e.course_instructor || '')}" data-principal="${esc(e.company_principal || '')}" data-student="${esc(e.student_name)}" data-course="${esc(e.course_name)}">
      ${esc(e.student_name)} — ${esc(e.course_name)} (Completed: ${esc(e.end_date)})
    </option>`
  ).join('');

  const host = modal('Issue Certificate', `
    <form class="form two-col">
      <label class="span-2">Completed Enrollment *
        <select name="enrollment_id" required onchange="onCertEnrollChange(this)">
          ${enrollOptions}
        </select>
      </label>
      <label>Certificate No. *<input name="certificate_number" required value="${esc(nextNum.certificate_number || '')}"></label>
      <label>Certificate Date (BS) *<input name="certify_date" required value="${new Date().toISOString().slice(0, 10).replace(/-/g, '/')}"></label>
      <label>Instructor Name *<input name="instructor_name" id="certInstructor" required value="${esc(available[0]?.course_instructor || '')}"></label>
      <label>Director / Principal *<input name="principal_name" id="certPrincipal" required value="${esc(available[0]?.company_principal || '')}"></label>
      <label class="span-2">Remarks<input name="remarks"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Issue Certificate</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.enrollment_id = Number(payload.enrollment_id);
    try {
      const result = await api('/certificates', { method: 'POST', body: JSON.stringify(payload) });
      host.remove();
      alert(`Certificate ${result.certificate_number} issued successfully.`);
      window.open(`/api/certificates/${result.id}/pdf?token=${encodeURIComponent(token)}`, '_blank');
      go('certificates');
    } catch (error) {
      showError(error);
    }
  };
}

function onCertEnrollChange(select) {
  const opt = select.selectedOptions[0];
  if (!opt) return;
  const inst = document.querySelector('#certInstructor');
  const princ = document.querySelector('#certPrincipal');
  if (inst && opt.dataset.instructor) inst.value = opt.dataset.instructor;
  if (princ && opt.dataset.principal) princ.value = opt.dataset.principal;
}

const studentTransCols = [
  { key: 'id', label: 'ID' },
  { key: 'transaction_date', label: 'Date' },
  { key: 'student_name', label: 'Student', render: row => `<a href="javascript:void(0)" onclick="viewStudentProfile(${row.student_id})" style="font-weight:700;color:var(--brand);text-decoration:none;">${esc(row.student_name)}</a>` },
  { key: 'transaction_type', label: 'Type' },
  { key: 'particular', label: 'Particular' },
  { key: 'charge_amount', label: 'Charge', render: row => money(row.charge_amount) },
  { key: 'payment_amount', label: 'Payment', render: row => money(row.payment_amount) },
  { key: 'discount_amount', label: 'Discount', render: row => money(row.discount_amount) },
  { key: 'account_name', label: 'Account' },
  { key: 'receipt_no', label: 'Receipt No.' },
];

async function student_transactions() {
  const rows = await api('/student-transactions');
  shell('Student Accounts', 'Track charges, payments, discounts, refunds, and adjustments', `
    ${toolbar([
      action('Record transaction', 'studentTransactionForm()', true),
      action('Export CSV', 'exportStudentTransactions()')
    ])}
    <div id="studentTransTable">${table(rows, studentTransCols)}</div>
  `);
  window._studentTransactions = rows;
}

function exportStudentTransactions() {
  csvDownload('student-transactions.csv', window._studentTransactions || [], studentTransCols);
}

async function studentTransactionForm() {
  const [studentsList, data] = await Promise.all([
    api('/students'),
    getLookups(),
  ]);
  const host = modal('Record Student Transaction', `
    <form class="form two-col">
      <label class="span-2">Student *
        <select name="student_id" required>
          ${selectOptions(studentsList, 'id', s => `${s.student_name}${s.class_name ? ` (${s.class_name})` : ''}`)}
        </select>
      </label>
      <label>Date (BS) *<input name="transaction_date" placeholder="2083/05/10" required></label>
      <label>Transaction Type
        <select name="transaction_type">
          <option>Payment Received</option>
          <option>Admission Fee</option>
          <option>Monthly Fee</option>
          <option>Exam Fee</option>
          <option>Other Charge</option>
          <option>Discount</option>
          <option>Refund</option>
          <option>Adjustment</option>
        </select>
      </label>
      <label class="span-2">Particular *<input name="particular" required value="Fee payment"></label>
      <label>Charge Amount<input name="charge_amount" type="number" step="0.01" value="0"></label>
      <label>Payment Amount<input name="payment_amount" type="number" step="0.01" value="0"></label>
      <label>Discount Amount<input name="discount_amount" type="number" step="0.01" value="0"></label>
      <label>Payment Account
        <select name="account_id">
          <option value="">Select account</option>
          ${selectOptions(data.accounts, 'id', a => `${a.account_name} (${a.account_type})`)}
        </select>
      </label>
      <label>Payment Method
        <select name="payment_method">
          <option>Cash</option>
          <option>Bank</option>
          <option>Wallet</option>
          <option>Other</option>
        </select>
      </label>
      <label>Receipt No.<input name="receipt_no"></label>
      <label class="span-2">Remarks<input name="remarks"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Save Transaction</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.student_id = Number(payload.student_id);
    ['charge_amount', 'payment_amount', 'discount_amount'].forEach(k => payload[k] = Number(payload[k] || 0));
    payload.account_id = payload.account_id ? Number(payload.account_id) : null;
    try {
      await api('/student-transactions', { method: 'POST', body: JSON.stringify(payload) });
      host.remove();
      go('student-transactions');
    } catch (error) {
      showError(error);
    }
  };
}

async function grades() {
  const [gradesList, classesList] = await Promise.all([
    api('/grades'),
    api('/class-levels'),
  ]);
  const gradeCols = [
    { key: 'id', label: 'ID' },
    { key: 'short_name', label: 'Short Name' },
    { key: 'grade_name', label: 'Grade Name' },
    { key: 'status', label: 'Status' },
    { key: 'remarks', label: 'Remarks' },
    { key: 'actions', label: 'Actions', render: row => `<button style="padding:3px 8px;font-size:12px;" onclick="gradeForm(${row.id})">Edit</button>` }
  ];
  const classCols = [
    { key: 'id', label: 'ID' },
    { key: 'level_name', label: 'Class / Level Name' },
    { key: 'status', label: 'Status' },
    { key: 'remarks', label: 'Remarks' },
    { key: 'actions', label: 'Actions', render: row => `<button style="padding:3px 8px;font-size:12px;" onclick="classLevelForm(${row.id})">Edit</button>` }
  ];
  shell('Grades & Class Levels', 'Maintain grade master and standard class levels', `
    ${toolbar([
      action('Add grade', 'gradeForm()', true),
      action('Add class level', 'classLevelForm()')
    ])}
    <section class="panel">
      <h2>Grade Master</h2>
      ${table(gradesList, gradeCols)}
    </section>
    <section class="panel">
      <h2>Class Levels</h2>
      ${table(classesList, classCols)}
    </section>
  `);
  window._gradesList = gradesList;
  window._classesList = classesList;
}

function gradeForm(id = null) {
  const existing = id ? (window._gradesList || []).find(g => g.id === id) : null;
  const host = modal(existing ? 'Edit Grade' : 'Add Grade', `
    <form class="form two-col">
      <label>Short Name *<input name="short_name" required value="${esc(existing?.short_name || '')}"></label>
      <label>Grade Name *<input name="grade_name" required value="${esc(existing?.grade_name || '')}"></label>
      <label>Status
        <select name="status">
          <option ${existing?.status === 'Active' ? 'selected' : ''}>Active</option>
          <option ${existing?.status === 'Inactive' ? 'selected' : ''}>Inactive</option>
        </select>
      </label>
      <label>Remarks<input name="remarks" value="${esc(existing?.remarks || '')}"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">${existing ? 'Update Grade' : 'Save Grade'}</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    try {
      await api(existing ? `/grades/${existing.id}` : '/grades', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      lookups = null;
      host.remove();
      go('grades');
    } catch (error) {
      showError(error);
    }
  };
}

function classLevelForm(id = null) {
  const existing = id ? (window._classesList || []).find(c => c.id === id) : null;
  const host = modal(existing ? 'Edit Class Level' : 'Add Class Level', `
    <form class="form two-col">
      <label class="span-2">Level Name *<input name="level_name" required value="${esc(existing?.level_name || '')}"></label>
      <label>Status
        <select name="status">
          <option ${existing?.status === 'Active' ? 'selected' : ''}>Active</option>
          <option ${existing?.status === 'Inactive' ? 'selected' : ''}>Inactive</option>
        </select>
      </label>
      <label>Remarks<input name="remarks" value="${esc(existing?.remarks || '')}"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">${existing ? 'Update Level' : 'Save Level'}</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    try {
      await api(existing ? `/class-levels/${existing.id}` : '/class-levels', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      lookups = null;
      host.remove();
      go('grades');
    } catch (error) {
      showError(error);
    }
  };
}

async function routines() {
  const plans = await api('/routines/plans');
  const isStudent = me?.role === 'student';
  const urlParams = new URLSearchParams(location.hash.split('?')[1] || '');
  const urlPlanId = urlParams.get('plan');
  const urlCourseId = urlParams.get('course');
  const selectedPlanId = urlPlanId ? Number(urlPlanId) : (plans.find(p => p.status === 'Active')?.id || plans[0]?.id || null);
  const selectedCourseId = (urlCourseId !== null && urlCourseId !== '' && urlCourseId !== 'null') ? Number(urlCourseId) : null;

  let studentClass = '';
  let enrolledCourses = [];
  if (isStudent) {
    try {
      const dbData = await api('/dashboard');
      studentClass = dbData?.student?.class_name || '';
      enrolledCourses = (dbData?.enrollments || []).filter(e => e.status === 'Active');
    } catch (e) {
      console.error(e);
    }
  }

  let queryUrl = `/routines?routine_plan_id=${selectedPlanId || ''}`;
  if (isStudent && selectedCourseId !== null) {
    queryUrl += `&course_id=${selectedCourseId}`;
  }
  const rows = selectedPlanId ? await api(queryUrl) : [];

  let displayRows = rows;
  if (isStudent && Array.isArray(rows)) {
    const sClass = String(studentClass || '').trim().toLowerCase();
    const enrolledCourseIds = new Set(enrolledCourses.map(c => Number(c.course_id || c.id)).filter(Boolean));
    const enrolledCourseNames = new Set(enrolledCourses.map(c => String(c.course_name || '').trim().toLowerCase()).filter(Boolean));

    displayRows = rows.filter(r => {
      // 1. Class filter
      if (sClass) {
        const rClass = String(r.class_name || '').trim().toLowerCase();
        const isGeneral = !rClass || rClass === 'all';
        const isMatch = isGeneral || rClass === sClass || rClass === `grade ${sClass}` || sClass === `grade ${rClass}`;
        if (!isMatch) return false;
      }

      // 2. Course filter
      const rCourseId = r.course_id ? Number(r.course_id) : null;
      const rCourseName = String(r.course_name || '').trim().toLowerCase();
      if (selectedCourseId !== null && selectedCourseId > 0) {
        if (rCourseId !== selectedCourseId) return false;
      } else if (selectedCourseId === 0) {
        if (rCourseId) return false;
      } else {
        if (rCourseId && !enrolledCourseIds.has(rCourseId) && !enrolledCourseNames.has(rCourseName)) {
          return false;
        }
      }
      return true;
    });
  }

  const planOptions = plans.map(p =>
    `<option value="${p.id}" ${p.id === selectedPlanId ? 'selected' : ''}>${esc(p.plan_name)} (${esc(p.effective_from)}) [${esc(p.status)}]</option>`
  ).join('');

  const canManageRoutines = has('master_data.manage');
  const isTeacher = (me?.role === 'staff' || me?.role === 'teacher');

  const routineCols = [
    { key: 'class_name', label: 'Class' },
    { key: 'day_of_week', label: 'Day' },
    { key: 'period_label', label: 'Period' },
    { key: 'subject_name', label: 'Subject' },
    { key: 'teacher_name', label: 'Teacher' },
    { key: 'course_name', label: 'Course' },
    { key: 'time', label: 'Time', render: row => `${row.start_time || ''} - ${row.end_time || ''}` },
    { key: 'status', label: 'Status' },
    ...(canManageRoutines ? [{
      key: 'actions', label: 'Actions', render: row => `
        <button style="padding:3px 8px;font-size:12px;" onclick="routinePeriodForm(${row.id})">Edit</button>
        <button class="danger" style="padding:3px 8px;font-size:12px;" onclick="deleteRoutinePeriod(${row.id})">Delete</button>
      `
    }] : [])
  ];

  let tb;
  if (isStudent) {
    const courseOptions = [
      `<option value="" ${selectedCourseId === null ? 'selected' : ''}>All Enrolled (Class & Courses)</option>`,
      ...(studentClass ? [`<option value="0" ${selectedCourseId === 0 ? 'selected' : ''}>Class ${esc(studentClass)} Core Subjects Only</option>`] : []),
      ...enrolledCourses.map(c => {
        const cid = c.course_id || c.id;
        return `<option value="${cid}" ${selectedCourseId === cid ? 'selected' : ''}>${esc(c.course_name)}</option>`;
      })
    ].join('');

    tb = [
      `<label style="font-weight:700;display:flex;align-items:center;gap:6px;">Plan: <select id="routinePlanSelect" onchange="switchRoutinePlan(this.value, '${selectedCourseId !== null ? selectedCourseId : ''}')">${planOptions}</select></label>`,
      ...(studentClass ? [`<span class="badge" style="background:#e0f2fe;color:#0369a1;padding:6px 12px;font-size:12px;font-weight:700;display:inline-flex;align-items:center;gap:5px;">${uiIcon('school', 14)}Class: ${esc(studentClass)}</span>`] : []),
      ...(enrolledCourses.length > 0 ? [`<label style="font-weight:700;display:flex;align-items:center;gap:6px;">Course: <select id="routineCourseSelect" onchange="switchRoutineCourse(this.value, '${selectedPlanId || ''}')">${courseOptions}</select></label>`] : []),
      action('Download Timetable PDF', `downloadRoutinePdf(${selectedPlanId || ''}, ${selectedCourseId !== null ? selectedCourseId : 'null'})`, true)
    ];
  } else {
    tb = [
      `<label style="font-weight:700;display:flex;align-items:center;gap:6px;">Plan: <select id="routinePlanSelect" onchange="switchRoutinePlan(this.value)">${planOptions}</select></label>`,
      ...(canManageRoutines ? [
        action('Add routine period', 'routinePeriodForm()', true),
        action('New effective plan', 'newRoutinePlanForm()')
      ] : []),
      action('Download Timetable PDF', `downloadRoutinePdf(${selectedPlanId || ''})`, !canManageRoutines)
    ];
  }

  const tableHtml = displayRows.length > 0
    ? table(displayRows, routineCols)
    : `<div style="padding:32px;text-align:center;color:var(--text-muted);background:var(--card-bg, #fff);border:1px dashed var(--border, #cbd5e1);border-radius:10px;margin-top:12px;">
        <p style="font-size:15px;font-weight:600;margin:0 0 6px 0;color:var(--text-color, #1e293b);">No timetable periods found.</p>
        <p style="margin:0;font-size:13px;">${isStudent ? 'There are no active classes scheduled for your enrolled class or course in this routine plan.' : (isTeacher ? 'No routine periods found for you in this plan.' : 'No routine periods found for this plan.')}</p>
       </div>`;

  shell(
    isStudent ? 'My Class Timetable' : ((isTeacher && !canManageRoutines) ? 'My Teaching Timetable' : 'Class Routines'),
    isStudent
      ? (studentClass ? `Weekly schedule for Class ${esc(studentClass)}${enrolledCourses.length ? ' and enrolled courses' : ''}` : 'Weekly schedule of your enrolled subjects and courses')
      : ((isTeacher && !canManageRoutines) ? 'Weekly schedule of your assigned classes and teaching periods' : 'Maintain weekly class routines and timetables'),
    `
      ${toolbar(tb)}
      <div id="routineTable">${tableHtml}</div>
    `
  );
  window._routineRows = rows;
  window._routinePlanId = selectedPlanId;
  window._routinePlans = plans;
}

function switchRoutinePlan(planId, courseId = '') {
  const cParam = (courseId !== '' && courseId !== 'null' && courseId !== null) ? `&course=${encodeURIComponent(courseId)}` : '';
  go(`routines?plan=${planId}${cParam}`);
}

function switchRoutineCourse(courseId, planId = '') {
  const pParam = planId ? `plan=${encodeURIComponent(planId)}&` : '';
  const cParam = (courseId !== '' && courseId !== null && courseId !== undefined) ? `course=${encodeURIComponent(courseId)}` : '';
  go(`routines?${pParam}${cParam}`.replace(/&$/, ''));
}

function downloadRoutinePdf(planId, courseId = null) {
  let url = `/api/routines/pdf?routine_plan_id=${planId || ''}`;
  if (courseId !== null && courseId !== undefined && courseId !== 'null' && courseId !== '') {
    url += `&course_id=${encodeURIComponent(courseId)}`;
  }
  url += `&token=${encodeURIComponent(token)}`;
  window.open(url, '_blank');
}

async function deleteRoutinePeriod(id) {
  if (!confirm('Delete this routine period?')) return;
  try {
    await api(`/routines/${id}`, { method: 'DELETE' });
    go(location.hash.slice(1) || 'routines');
  } catch (error) {
    showError(error);
  }
}

async function routinePeriodForm(id = null) {
  const [data, coursesList] = await Promise.all([
    getLookups(),
    api('/courses'),
  ]);
  const existing = id ? (window._routineRows || []).find(r => r.id === id) : null;
  const currentPlanId = window._routinePlanId || window._routinePlans?.[0]?.id;
  if (!currentPlanId) {
    alert('Create a routine plan first.');
    return;
  }

  const host = modal(existing ? 'Edit Routine Period' : 'Add Routine Period', `
    <form class="form two-col">
      <label>Class / Level *
        <select name="class_level_id" required onchange="this.form.class_name.value=this.selectedOptions[0].text">
          ${selectOptions(data.classes, 'id', c => c.level_name)}
        </select>
      </label>
      <input type="hidden" name="class_name" value="${esc(existing?.class_name || data.classes[0]?.level_name || '')}">
      <label>Day of Week *
        <select name="day_of_week">
          ${['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'].map(d => `<option ${existing?.day_of_week === d ? 'selected' : ''}>${d}</option>`).join('')}
        </select>
      </label>
      <label>Period Label *<input name="period_label" required placeholder="Period 1" value="${esc(existing?.period_label || '')}"></label>
      <label>Subject Name *<input name="subject_name" required value="${esc(existing?.subject_name || '')}"></label>
      <label>Teacher / Staff
        <select name="teacher_id">
          <option value="">Unassigned</option>
          ${selectOptions(data.teachers, 'id', t => t.teacher_name)}
        </select>
      </label>
      <label>Course (optional)
        <select name="course_id">
          <option value="">None</option>
          ${selectOptions(coursesList, 'id', c => c.course_name)}
        </select>
      </label>
      <label>Start Time<input name="start_time" placeholder="07:00 AM" value="${esc(existing?.start_time || '')}"></label>
      <label>End Time<input name="end_time" placeholder="07:45 AM" value="${esc(existing?.end_time || '')}"></label>
      <label>Status
        <select name="status">
          <option ${existing?.status === 'Active' ? 'selected' : ''}>Active</option>
          <option ${existing?.status === 'Inactive' ? 'selected' : ''}>Inactive</option>
        </select>
      </label>
      <label>Remarks<input name="remarks" value="${esc(existing?.remarks || '')}"></label>
      <input type="hidden" name="routine_plan_id" value="${currentPlanId}">
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">${existing ? 'Update Period' : 'Save Period'}</button>
      </div>
    </form>
  `);
  if (existing) {
    if (existing.class_level_id) host.querySelector('select[name="class_level_id"]').value = existing.class_level_id;
    if (existing.teacher_id) host.querySelector('select[name="teacher_id"]').value = existing.teacher_id;
    if (existing.course_id) host.querySelector('select[name="course_id"]').value = existing.course_id;
  }
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.class_level_id = Number(payload.class_level_id);
    payload.routine_plan_id = Number(payload.routine_plan_id);
    payload.teacher_id = payload.teacher_id ? Number(payload.teacher_id) : null;
    payload.course_id = payload.course_id ? Number(payload.course_id) : null;
    try {
      await api(existing ? `/routines/${existing.id}` : '/routines', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      host.remove();
      go(location.hash.slice(1) || 'routines');
    } catch (error) {
      showError(error);
    }
  };
}

async function newRoutinePlanForm() {
  const plans = window._routinePlans || await api('/routines/plans');
  const host = modal('New Effective Routine Plan', `
    <form class="form two-col">
      <label class="span-2">Plan Name *<input name="plan_name" required placeholder="Academic Session 2083/84"></label>
      <label class="span-2">Effective From (BS) *<input name="effective_from" required placeholder="2083/05/10"></label>
      <label class="span-2">Copy Periods From
        <select name="copy_from_plan_id">
          <option value="">Start Empty (Do not copy)</option>
          ${selectOptions(plans, 'id', p => `${p.plan_name} (${p.effective_from})`)}
        </select>
      </label>
      <label class="span-2"><input type="checkbox" name="archive_source" checked> Archive previous plan when this plan starts</label>
      <label class="span-2">Remarks<input name="remarks"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Create Plan</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.copy_from_plan_id = payload.copy_from_plan_id ? Number(payload.copy_from_plan_id) : null;
    payload.archive_source = payload.archive_source === 'on';
    try {
      const res = await api('/routines/plans', { method: 'POST', body: JSON.stringify(payload) });
      host.remove();
      alert('Routine plan created.');
      go(`routines?plan=${res.id}`);
    } catch (error) {
      showError(error);
    }
  };
}

const advanceCols = [
  { key: 'id', label: 'ID' },
  { key: 'advance_date', label: 'Date' },
  { key: 'teacher_name', label: 'Staff Member' },
  { key: 'amount', label: 'Advance', render: row => money(row.amount) },
  { key: 'recovered_amount', label: 'Recovered', render: row => money(row.recovered_amount) },
  { key: 'remaining', label: 'Remaining', render: row => money(row.remaining) },
  { key: 'account_name', label: 'Paid From' },
  { key: 'recovery_method', label: 'Recovery' },
  { key: 'status', label: 'Status' },
];

async function advances() {
  const rows = await api('/advances');
  shell('Staff Advances', 'Track advance payouts, recovery plans, and outstanding balances', `
    ${toolbar([
      action('Pay advance', 'advanceForm()', true),
      action('Export CSV', 'exportAdvances()')
    ])}
    <div id="advanceTable">${table(rows, advanceCols)}</div>
  `);
  window._advances = rows;
}

function exportAdvances() {
  csvDownload('staff-advances.csv', window._advances || [], advanceCols);
}

async function advanceForm() {
  const data = await getLookups();
  const host = modal('Pay Staff Advance', `
    <form class="form two-col">
      <label class="span-2">Staff Member *
        <select name="teacher_id" required>
          ${selectOptions(data.teachers, 'id', t => `${t.teacher_name} (${t.staff_type})`)}
        </select>
      </label>
      <label>Advance Date (BS) *<input name="advance_date" placeholder="2083/05/10" required></label>
      <label>Advance Amount *<input name="amount" type="number" min="0.01" step="0.01" required></label>
      <label>Paid From Account *
        <select name="paid_from_account_id" required>
          ${selectOptions(data.accounts, 'id', a => `${a.account_name} (${a.account_type})`)}
        </select>
      </label>
      <label>Payment Method
        <select name="payment_method">
          <option>Cash</option>
          <option>Bank</option>
          <option>Wallet</option>
          <option>Other</option>
        </select>
      </label>
      <label>Reference No.<input name="reference_no"></label>
      <label>Recovery Method
        <select name="recovery_method">
          <option>Salary Deduction</option>
          <option>Direct Repayment</option>
          <option>Other</option>
        </select>
      </label>
      <label>Recovery Start Month (YYYY/MM)<input name="recovery_start_month" placeholder="2083/06"></label>
      <label>Monthly Deduction<input name="monthly_deduction" type="number" step="0.01" value="0"></label>
      <label class="span-2">Remarks<input name="remarks"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Pay Advance</button>
      </div>
    </form>
  `);
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.teacher_id = Number(payload.teacher_id);
    payload.paid_from_account_id = Number(payload.paid_from_account_id);
    payload.amount = Number(payload.amount);
    payload.monthly_deduction = Number(payload.monthly_deduction || 0);
    try {
      await api('/advances', { method: 'POST', body: JSON.stringify(payload) });
      lookups = null;
      host.remove();
      go('advances');
    } catch (error) {
      showError(error);
    }
  };
}

const salaryCols = [
  { key: 'id', label: 'ID' },
  { key: 'salary_month', label: 'Month' },
  { key: 'teacher_name', label: 'Staff Member' },
  { key: 'basic_salary', label: 'Basic', render: row => money(row.basic_salary) },
  { key: 'advance_deduction', label: 'Advance Ded.', render: row => money(row.advance_deduction) },
  { key: 'net_salary', label: 'Net Salary', render: row => `<b>${money(row.net_salary)}</b>` },
  { key: 'payment_date', label: 'Paid Date' },
  { key: 'account_name', label: 'Account' },
  { key: 'voucher_no', label: 'Voucher' },
  { key: 'actions', label: 'Actions', render: row => `
    <a href="/api/salary/${row.id}/payslip/pdf?token=${encodeURIComponent(token)}" target="_blank"><button class="primary" style="padding:3px 8px;font-size:12px;">Payslip PDF</button></a>
  ` }
];

async function salary() {
  const rows = await api('/salary');
  shell('Salary Payouts', 'Monthly payroll, attendance calculation, and payslip generation', `
    ${toolbar([
      action('Pay salary', 'salaryPayoutForm()', true),
      action('Export CSV', 'exportSalary()')
    ])}
    <div id="salaryTable">${table(rows, salaryCols)}</div>
  `);
  window._salaryRows = rows;
}

function exportSalary() {
  csvDownload('salary-payouts.csv', window._salaryRows || [], salaryCols.slice(0, -1));
}

async function salaryPayoutForm() {
  const data = await getLookups();
  const host = modal('Process Salary Payout', `
    <form class="form two-col" id="salaryForm">
      <label class="span-2">Staff Member *
        <select name="teacher_id" id="salaryStaff" required onchange="onSalaryStaffChange()">
          ${selectOptions(data.teachers, 'id', t => `${t.teacher_name} (${t.staff_type} - ${t.salary_type})`)}
        </select>
      </label>
      <label>Salary Month (YYYY/MM) *<input name="salary_month" id="salaryMonth" placeholder="2083/05" required onchange="onSalaryStaffChange()"></label>
      <label style="display:flex;align-items:flex-end;">
        <button type="button" class="primary" onclick="calculateSalaryData()" style="width:100%;">Calculate Attendance</button>
      </label>
      <div class="span-2" id="attendanceNotice" style="font-size:13px;color:#0369a1;background:#f0f9ff;padding:8px 12px;border-radius:4px;display:none;"></div>
      <label>Basic Salary *<input name="basic_salary" id="salaryBasic" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Extra Payment<input name="extra_payment" id="salaryExtra" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Bonus<input name="bonus" id="salaryBonus" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Allowance<input name="allowance" id="salaryAllowance" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Advance Deduction<input name="advance_deduction" id="salaryAdvance" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Other Deduction<input name="other_deduction" id="salaryOther" type="number" step="0.01" value="0" oninput="recalcSalaryNet()"></label>
      <label>Attendance Days<input name="attendance_days" id="salaryDays" type="number" value="0"></label>
      <label>Working Hours<input name="working_hours" id="salaryHours" type="number" step="0.01" value="0"></label>
      <label>Scheduled Classes<input name="class_count" id="salaryClasses" type="number" value="0"></label>
      <div style="font-size:16px;font-weight:700;display:flex;align-items:center;color:#008b78;">Net Salary: <span id="salaryNet" style="margin-left:8px;">0.00</span></div>
      <label>Payment Date (BS) *<input name="payment_date" placeholder="2083/05/10" required></label>
      <label>Paid From Account *
        <select name="paid_from_account_id" required>
          ${selectOptions(data.accounts, 'id', a => `${a.account_name} (${a.account_type})`)}
        </select>
      </label>
      <label>Payment Method
        <select name="payment_method">
          <option>Bank</option>
          <option>Cash</option>
          <option>Wallet</option>
          <option>Other</option>
        </select>
      </label>
      <label>Voucher No.<input name="voucher_no"></label>
      <label class="span-2">Remarks<input name="remarks"></label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Pay Salary</button>
      </div>
    </form>
  `);
  window._selectedTeacher = data.teachers[0];
  if (data.teachers[0]) {
    document.querySelector('#salaryBasic').value = data.teachers[0].basic_salary || 0;
    recalcSalaryNet();
  }
  host.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const payload = formData(event.target);
    payload.teacher_id = Number(payload.teacher_id);
    payload.paid_from_account_id = Number(payload.paid_from_account_id);
    ['basic_salary','extra_payment','bonus','allowance','advance_deduction','other_deduction','working_hours'].forEach(k => payload[k] = Number(payload[k] || 0));
    ['attendance_days','class_count'].forEach(k => payload[k] = Number(payload[k] || 0));
    try {
      const res = await api('/salary', { method: 'POST', body: JSON.stringify(payload) });
      lookups = null;
      host.remove();
      alert('Salary payout recorded successfully.');
      window.open(`/api/salary/${res.id}/payslip/pdf?token=${encodeURIComponent(token)}`, '_blank');
      go('salary');
    } catch (error) {
      showError(error);
    }
  };
}

async function onSalaryStaffChange() {
  const staffId = Number(document.querySelector('#salaryStaff')?.value);
  const data = await getLookups();
  const teacher = data.teachers.find(t => t.id === staffId);
  if (teacher) {
    window._selectedTeacher = teacher;
    const basicInput = document.querySelector('#salaryBasic');
    if (basicInput) basicInput.value = teacher.basic_salary || 0;
    recalcSalaryNet();
  }
}

async function calculateSalaryData() {
  const teacher_id = Number(document.querySelector('#salaryStaff')?.value);
  const salary_month = document.querySelector('#salaryMonth')?.value.trim();
  if (!teacher_id || !salary_month) {
    alert('Select a staff member and enter the salary month.');
    return;
  }
  try {
    const data = await api('/salary/calculate', { method: 'POST', body: JSON.stringify({ teacher_id, salary_month }) });
    const notice = document.querySelector('#attendanceNotice');
    if (notice) {
      notice.style.display = 'block';
      notice.textContent = `Attendance: ${data.summary.days} present days, ${data.summary.hours.toFixed(2)} hours. Scheduled classes: ${data.scheduled_classes}. Outstanding advance: Rs. ${data.outstanding_advance.toFixed(2)}`;
    }
    document.querySelector('#salaryDays').value = data.summary.days;
    document.querySelector('#salaryHours').value = data.summary.hours.toFixed(2);
    document.querySelector('#salaryClasses').value = data.scheduled_classes;
    if (data.salary_type === 'Per Class Payment' && data.scheduled_classes > 0) {
      document.querySelector('#salaryBasic').value = (data.basic_salary * data.scheduled_classes).toFixed(2);
    }
    if (data.outstanding_advance > 0) {
      document.querySelector('#salaryAdvance').value = data.outstanding_advance;
    }
    recalcSalaryNet();
  } catch (error) {
    showError(error);
  }
}

function recalcSalaryNet() {
  const getVal = id => Number(document.querySelector('#' + id)?.value || 0);
  const gross = getVal('salaryBasic') + getVal('salaryExtra') + getVal('salaryBonus') + getVal('salaryAllowance');
  const deductions = getVal('salaryAdvance') + getVal('salaryOther');
  const net = Math.max(0, gross - deductions);
  const span = document.querySelector('#salaryNet');
  if (span) span.textContent = money(net);
}

async function settings() {
  const [rows, healthData] = await Promise.all([
    api('/settings'),
    api('/system/health').catch(() => ({ status: 'unknown', message: 'Unable to query health', checks: [] })),
  ]);

  const bannerClass = healthData.status === 'ok' ? 'ok' : (healthData.status === 'warning' ? 'warning' : 'error');
  const healthCards = (healthData.checks || []).map(c => `
    <div class="health-card">
      <h4>${esc(c.name.toUpperCase())} <span class="badge ${c.status === 'ok' ? 'active' : (c.status === 'warning' ? 'partial' : 'inactive')}">${esc(c.status)}</span></h4>
      <p>${esc(c.detail)}</p>
    </div>
  `).join('');

  const categories = {};
  rows.forEach(r => {
    const cat = r.category || 'General';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(r);
  });

  const catNames = Object.keys(categories);
  const activeCat = window._activeSettingsCat || catNames[0];

  const catTabs = catNames.map(cat =>
    `<button class="settings-tab ${cat === activeCat ? 'active' : ''}" onclick="switchSettingsCategory('${esc(cat)}')">${esc(cat)}</button>`
  ).join('');

  const currentRows = categories[activeCat] || [];
  const fields = currentRows.map(r => `
    <label class="span-2" style="background:#fff;border:1px solid var(--line);border-radius:6px;padding:12px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
        <span style="font-weight:700;color:var(--ink);">${esc(r.setting_label || r.setting_key)}</span>
        <code style="font-size:11px;color:#64748b;">${esc(r.setting_key)}</code>
      </div>
      <small style="color:#64748b;margin-bottom:8px;display:block;">${esc(r.description || '')}</small>
      ${r.data_type === 'boolean'
        ? `<select name="${esc(r.setting_key)}"><option value="true" ${r.setting_value === 'true' ? 'selected' : ''}>Enabled (true)</option><option value="false" ${r.setting_value === 'false' ? 'selected' : ''}>Disabled (false)</option></select>`
        : `<input name="${esc(r.setting_key)}" value="${esc(r.setting_value || '')}">`
      }
    </label>
  `).join('');

  shell('System & Automation Settings', 'Global system configuration, daily backup automation, and health telemetry', `
    <div class="health-banner ${bannerClass}">
      <div>
        <h3 style="margin:0;">System Health: ${esc(healthData.status.toUpperCase())}</h3>
        <span style="font-size:13px;">${esc(healthData.message || '')}</span>
      </div>
      <button class="primary" onclick="triggerBackup()" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('backup', 15)}Backup Database Now</button>
    </div>
    <div class="health-grid">${healthCards}</div>

    <section class="panel">
      <div class="settings-tabs">${catTabs}</div>
      <form class="form two-col" id="settingsForm" onsubmit="saveSettings(event)">
        ${fields}
        <div class="form-actions span-2">
          <button class="primary">Save Settings</button>
        </div>
      </form>
    </section>
  `);
}

function switchSettingsCategory(cat) {
  window._activeSettingsCat = cat;
  settings();
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.target;
  const payload = { settings: formData(form) };
  try {
    await api('/settings', { method: 'PUT', body: JSON.stringify(payload) });
    alert('Settings updated successfully.');
    lookups = null;
    settings();
  } catch (error) {
    showError(error);
  }
}

async function triggerBackup() {
  if (!confirm('Take an immediate database backup snapshot?')) return;
  try {
    const res = await api('/system/backup', { method: 'POST' });
    alert(`Backup created successfully!\nFile: ${res.filename}\nSize: ${(res.size_bytes / 1024).toFixed(1)} KB`);
    settings();
  } catch (error) {
    showError(error);
  }
}

// -----------------------------------------------------------------------
// User Management & Access Control
// -----------------------------------------------------------------------
let _allUsers = [];
let _userRolesPermissions = null;

async function users() {
  const [usersList, rolesMeta] = await Promise.all([
    api('/users'),
    api('/users/roles-permissions')
  ]);
  _allUsers = usersList;
  _userRolesPermissions = rolesMeta;

  const total = usersList.length;
  const active = usersList.filter(u => u.status === 'Active').length;
  const staff = usersList.filter(u => u.teacher_id).length;
  const students = usersList.filter(u => u.student_id).length;
  const locked = usersList.filter(u => u.locked_until || (u.failed_attempts >= 5)).length;

  const kpis = `
    <div class="cards">
      <div class="card"><span>TOTAL USERS</span><b>${total}</b><small class="muted">Configured accounts</small></div>
      <div class="card"><span>ACTIVE ACCOUNTS</span><b>${active}</b><small class="muted">${total - active} disabled</small></div>
      <div class="card"><span>STAFF LOGINS</span><b>${staff}</b><small class="muted">Linked to staff members</small></div>
      <div class="card"><span>STUDENT LOGINS</span><b>${students}</b><small class="muted">Linked to students</small></div>
      <div class="card"><span>LOCKED OUT</span><b>${locked}</b><small class="muted">${locked > 0 ? 'Requires attention' : 'All clear'}</small></div>
    </div>
  `;

  const filterBar = `
    <div class="user-filter-bar">
      <input id="userSearchInput" style="flex:1;min-width:200px;" placeholder="Search by username, name, email or phone..." oninput="filterUsersList()">
      <select id="userRoleFilter" onchange="filterUsersList()">
        <option value="All">All Roles</option>
        ${rolesMeta.roles.map(r => `<option value="${esc(r)}">${esc(r.replace('_', ' ').toUpperCase())}</option>`).join('')}
      </select>
      <select id="userStatusFilter" onchange="filterUsersList()">
        <option value="All">All Statuses</option>
        <option value="Active">Active</option>
        <option value="Disabled">Disabled</option>
        <option value="Locked">Locked Out</option>
      </select>
      <button class="primary" onclick="userForm()" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('plus', 14)}Add User</button>
      <button onclick="userAuditLogModal()" style="display:inline-flex;align-items:center;gap:6px;">${uiIcon('audit', 15)}Audit Log</button>
      <button onclick="exportUsersCsv()">Export CSV</button>
    </div>
  `;

  shell('User Management', 'Manage user accounts, roles, access permissions, and linked entities', `${kpis}${filterBar}<section class="panel"><div id="usersTableContainer"></div></section>`);
  filterUsersList();
}

function filterUsersList() {
  const query = (document.querySelector('#userSearchInput')?.value || '').toLowerCase().trim();
  const role = document.querySelector('#userRoleFilter')?.value || 'All';
  const status = document.querySelector('#userStatusFilter')?.value || 'All';

  let filtered = _allUsers;
  if (role !== 'All') {
    filtered = filtered.filter(u => u.role === role);
  }
  if (status !== 'All') {
    if (status === 'Locked') {
      filtered = filtered.filter(u => u.locked_until || (u.failed_attempts >= 5));
    } else {
      filtered = filtered.filter(u => u.status === status);
    }
  }
  if (query) {
    filtered = filtered.filter(u =>
      (u.username || '').toLowerCase().includes(query) ||
      (u.display_name || '').toLowerCase().includes(query) ||
      (u.email || '').toLowerCase().includes(query) ||
      (u.phone || '').toLowerCase().includes(query) ||
      (u.student_name || '').toLowerCase().includes(query) ||
      (u.teacher_name || '').toLowerCase().includes(query)
    );
  }
  renderUsersTable(filtered);
}

function renderUsersTable(rows) {
  const container = document.querySelector('#usersTableContainer');
  if (!container) return;

  const columns = [
    { key: 'id', label: 'ID' },
    {
      key: 'username',
      label: 'User',
      render: u => `<div><b>${esc(u.username)}</b><div style="font-size:12px;color:#64748b;">${esc(u.display_name || '')}</div></div>`
    },
    {
      key: 'role',
      label: 'Role',
      render: u => `<span class="role-badge ${esc(u.role)}">${esc(u.role.replace('_', ' '))}</span>`
    },
    {
      key: 'contact',
      label: 'Contact',
      render: u => `<div><small>${esc(u.phone || '-')}</small><div style="font-size:11px;color:#64748b;">${esc(u.email || '-')}</div></div>`
    },
    {
      key: 'linked_entity',
      label: 'Linked Entity',
      render: u => {
        if (u.student_id) return `<span class="badge active" style="font-size:11px;">Student #${esc(u.student_id)}: ${esc(u.student_name || '')}</span>`;
        if (u.teacher_id) return `<span class="badge active" style="font-size:11px;background:#fef3c7;color:#92400e;border-color:#fde68a;">Staff #${esc(u.teacher_id)}: ${esc(u.teacher_name || '')}</span>`;
        return '<span class="muted" style="font-size:12px;">None</span>';
      }
    },
    {
      key: 'status',
      label: 'Status',
      render: u => {
        const isLocked = Boolean(u.locked_until || (u.failed_attempts >= 5));
        if (isLocked) return `<span class="badge inactive" style="background:#fee2e2;color:#991b1b;border:1px solid #f87171;display:inline-flex;align-items:center;gap:4px;">${uiIcon('lock', 12)}LOCKED (${u.failed_attempts || 5})</span>`;
        if (u.status === 'Active') return '<span class="badge active">● Active</span>';
        return '<span class="badge inactive">● Disabled</span>';
      }
    },
    {
      key: 'activity',
      label: 'Last Login',
      render: u => `<small style="color:#64748b;">${u.last_login_at ? esc(u.last_login_at.replace('T', ' ').slice(0, 16)) : 'Never'}</small>`
    },
    {
      key: 'actions',
      label: 'Actions',
      render: u => {
        const isLocked = Boolean(u.locked_until || (u.failed_attempts >= 5));
        const isSelf = me && Number(me.id) === Number(u.id);
        const unlockBtn = isLocked ? `<button style="padding:3px 7px;font-size:11px;background:#dcfce7;color:#166534;border:1px solid #86efac;" onclick="unlockUser(${u.id})">Unlock</button>` : '';
        const toggleBtn = !isSelf ? `<button style="padding:3px 7px;font-size:11px;" onclick="toggleUser(${u.id}, '${esc(u.status)}')">${u.status === 'Active' ? 'Disable' : 'Activate'}</button>` : '';
        return `
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            <button class="primary" style="padding:3px 7px;font-size:11px;" onclick="userForm(${u.id})">Edit</button>
            <button style="padding:3px 7px;font-size:11px;" onclick="userResetPasswordModal(${u.id}, '${esc(u.username)}')">Reset Pwd</button>
            ${unlockBtn}
            ${toggleBtn}
          </div>
        `;
      }
    }
  ];

  container.innerHTML = table(rows, columns);
}

function generateRandomPassword() {
  const charsUpper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const charsLower = 'abcdefghjkmnpqrstuvwxyz';
  const charsNum = '23456789';
  const charsSpecial = '!@#$%^&*';
  const allChars = charsUpper + charsLower + charsNum + charsSpecial;
  let pwd = [
    charsUpper[Math.floor(Math.random() * charsUpper.length)],
    charsUpper[Math.floor(Math.random() * charsUpper.length)],
    charsLower[Math.floor(Math.random() * charsLower.length)],
    charsLower[Math.floor(Math.random() * charsLower.length)],
    charsNum[Math.floor(Math.random() * charsNum.length)],
    charsNum[Math.floor(Math.random() * charsNum.length)],
    charsSpecial[Math.floor(Math.random() * charsSpecial.length)],
    charsSpecial[Math.floor(Math.random() * charsSpecial.length)],
  ];
  for (let i = 8; i < 12; i++) {
    pwd.push(allChars[Math.floor(Math.random() * allChars.length)]);
  }
  return pwd.sort(() => Math.random() - 0.5).join('');
}

function validateClientPassword(password) {
  if (!password || password.length < 10) {
    return 'Password must contain at least 10 characters.';
  }
  if (!/[a-z]/.test(password)) {
    return 'Password must contain at least one lowercase letter.';
  }
  if (!/[A-Z]/.test(password)) {
    return 'Password must contain at least one uppercase letter.';
  }
  if (!/[0-9]/.test(password)) {
    return 'Password must contain at least one number.';
  }
  if (!/[^a-zA-Z0-9]/.test(password)) {
    return 'Password must contain at least one symbol (!@#$%^&*...).';
  }
  return null;
}

async function openCreateUserForStaff(teacherId) {
  try {
    const usersList = await api('/users');
    const existing = usersList.find(u => u.teacher_id === Number(teacherId));
    if (existing) {
      userForm(existing.id);
      return;
    }
    const lookupsData = await getLookups();
    const staffMember = (lookupsData.teachers || []).find(t => t.id === Number(teacherId));
    const rawName = (staffMember?.teacher_name || 'staff').toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').slice(0, 15);
    userForm(null, {
      role: 'staff',
      teacher_id: Number(teacherId),
      display_name: staffMember?.teacher_name || '',
      email: staffMember?.email || '',
      phone: staffMember?.contact || '',
      username: `${rawName}_staff`
    });
  } catch (err) {
    showError(err);
  }
}

async function openCreateUserForStudent(studentId) {
  try {
    const usersList = await api('/users');
    const existing = usersList.find(u => u.student_id === Number(studentId));
    if (existing) {
      userForm(existing.id);
      return;
    }
    const lookupsData = await getLookups();
    const studentMember = (lookupsData.students || []).find(s => s.id === Number(studentId));
    const rawName = (studentMember?.student_name || 'student').toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').slice(0, 15);
    userForm(null, {
      role: 'student',
      student_id: Number(studentId),
      display_name: studentMember?.student_name || '',
      email: studentMember?.email || '',
      phone: studentMember?.contact || '',
      username: `${rawName}_stu`
    });
  } catch (err) {
    showError(err);
  }
}

async function userForm(userId = null, preset = null) {
  let lookupsData, rolesMeta, existingUser;
  try {
    [lookupsData, rolesMeta, existingUser] = await Promise.all([
      getLookups(),
      _userRolesPermissions ? Promise.resolve(_userRolesPermissions) : api('/users/roles-permissions'),
      userId ? api(`/users/${userId}`) : Promise.resolve(null)
    ]);
  } catch (err) {
    showError(err);
    return;
  }
  _userRolesPermissions = rolesMeta;

  const roles = rolesMeta.roles;
  const permissionsList = rolesMeta.permissions;
  const roleDefaults = rolesMeta.role_defaults;

  const currentRole = existingUser?.role || preset?.role || 'staff';
  const currentPermissions = new Set(existingUser ? existingUser.permissions : (roleDefaults[currentRole] || []));

  const selectedTeacherId = existingUser?.teacher_id ?? preset?.teacher_id;
  const selectedStudentId = existingUser?.student_id ?? preset?.student_id;

  const teacherOptions = `<option value="">-- No staff link --</option>` +
    (lookupsData.teachers || []).map(t => `<option value="${t.id}" data-name="${esc(t.teacher_name)}" data-email="${esc(t.email || '')}" data-phone="${esc(t.contact || '')}" ${selectedTeacherId === t.id ? 'selected' : ''}>${esc(t.teacher_name)} (${esc(t.staff_type)})</option>`).join('');

  const studentOptions = `<option value="">-- No student link --</option>` +
    (lookupsData.students || []).map(s => `<option value="${s.id}" data-name="${esc(s.student_name)}" data-email="${esc(s.email || '')}" data-phone="${esc(s.contact || '')}" ${selectedStudentId === s.id ? 'selected' : ''}>${esc(s.student_name)} (${esc(s.class_name || 'No Class')})</option>`).join('');

  const roleOptions = roles.map(r => `<option value="${esc(r)}" ${currentRole === r ? 'selected' : ''}>${esc(r.replace('_', ' ').toUpperCase())}</option>`).join('');

  const isSuperOrAdmin = currentRole === 'super_admin' || currentRole === 'admin';

  const permItemsHtml = permissionsList.map(p => {
    const key = p.key || p[0];
    const name = p.name || p[1] || key;
    const desc = p.description || p[2] || '';
    const isAssistant = key === 'assistant.view';
    const isChecked = isSuperOrAdmin ? true : (!isAssistant && currentPermissions.has(key));
    const isDisabled = isAssistant && !isSuperOrAdmin;
    return `
      <label class="permission-item" style="${isDisabled ? 'opacity:0.6;' : ''}">
        <input type="checkbox" name="permissions" value="${esc(key)}" ${isChecked ? 'checked' : ''} ${isDisabled ? 'disabled' : ''}>
        <div>
          <strong>${esc(name)}${isAssistant ? ' <span class="badge" style="font-size:10px;padding:1px 6px;">Admin Only</span>' : ''}</strong>
          <small>${esc(desc)}</small>
        </div>
      </label>
    `;
  }).join('');

  const formHtml = `
    <form class="form two-col" id="userAccountForm">
      <label>
        Username *
        <input name="username" required minlength="3" ${existingUser ? 'disabled' : ''} value="${esc(existingUser?.username || preset?.username || '')}" placeholder="e.g. john_staff">
      </label>
      ${!existingUser ? `
        <label>
          Initial Password *
          <div style="display:flex;gap:6px;">
            <input type="text" name="password" id="userFormPassword" required minlength="10" placeholder="Min 10 characters (upper, lower, num, symbol)" value="${generateRandomPassword()}">
            <button type="button" onclick="document.querySelector('#userFormPassword').value = generateRandomPassword()">Generate</button>
          </div>
        </label>
      ` : `
        <div>
          <label>Password</label>
          <p class="muted" style="margin:6px 0 0;font-size:12px;">Existing password retained. To reset, use the "Reset Pwd" button in table.</p>
        </div>
      `}
      <label>
        Full Display Name *
        <input name="display_name" required value="${esc(existingUser?.display_name || preset?.display_name || '')}" placeholder="e.g. John Doe">
      </label>
      <label>
        Role *
        <select name="role" id="userFormRoleSelect" onchange="onUserRoleChange(this)">
          ${roleOptions}
        </select>
      </label>
      <label>
        Email
        <input type="email" name="email" value="${esc(existingUser?.email || preset?.email || '')}" placeholder="john@example.com">
      </label>
      <label>
        Phone
        <input type="tel" name="phone" value="${esc(existingUser?.phone || preset?.phone || '')}" placeholder="98XXXXXXXX">
      </label>
      <label>
        Account Status
        <select name="status">
          <option value="Active" ${existingUser?.status === 'Active' ? 'selected' : ''}>Active</option>
          <option value="Disabled" ${existingUser?.status === 'Disabled' ? 'selected' : ''}>Disabled</option>
        </select>
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin-top:24px;">
        <input type="checkbox" name="must_change_password" ${(!existingUser || existingUser?.must_change_password) ? 'checked' : ''}>
        <span>Must change password at next login</span>
      </label>

      <div class="span-2" id="userStaffLinkGroup" style="display:${currentRole === 'staff' ? 'block' : 'none'};background:#fffbeb;padding:12px;border:1px solid #fef3c7;border-radius:6px;margin:8px 0;">
        <label style="font-weight:600;color:#92400e;">
          Linked Staff Member (Teacher / Employee)
          <select name="teacher_id" id="userTeacherSelect" onchange="onUserStaffSelect(this)">
            ${teacherOptions}
          </select>
          <small class="muted" style="display:block;margin-top:4px;">Links this user to teacher attendance, schedule, routines, and payroll records.</small>
        </label>
      </div>

      <div class="span-2" id="userStudentLinkGroup" style="display:${currentRole === 'student' ? 'block' : 'none'};background:#f0fdf4;padding:12px;border:1px solid #bbf7d0;border-radius:6px;margin:8px 0;">
        <label style="font-weight:600;color:#166534;">
          Linked Student
          <select name="student_id" id="userStudentSelect" onchange="onUserStudentSelect(this)">
            ${studentOptions}
          </select>
          <small class="muted" style="display:block;margin-top:4px;">Links this user to student portal, grades, attendance records, and personal dossier.</small>
        </label>
      </div>

      <div class="span-2" style="margin-top:8px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <h3 style="margin:0;font-size:14px;color:var(--ink);">Access Permissions Matrix</h3>
          <div style="display:flex;gap:6px;">
            <button type="button" style="padding:2px 8px;font-size:11px;" onclick="resetPermissionsToRoleDefaults()">Reset to Role Defaults</button>
            <button type="button" style="padding:2px 8px;font-size:11px;" onclick="setPermissionsAll(true)">Select All</button>
            <button type="button" style="padding:2px 8px;font-size:11px;" onclick="setPermissionsAll(false)">Deselect All</button>
          </div>
        </div>
        <div class="permissions-grid" id="userFormPermissionsGrid">
          ${permItemsHtml}
        </div>
      </div>

      <div class="form-actions span-2" style="margin-top:16px;">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">${existingUser ? 'Save Changes' : 'Create User'}</button>
      </div>
    </form>
  `;

  const host = modal(existingUser ? `Edit User: ${existingUser.username}` : (preset ? `Create User for ${preset.display_name || 'Account'}` : 'Add New User'), formHtml);
  const form = host.querySelector('#userAccountForm');

  form.onsubmit = async event => {
    event.preventDefault();
    const data = formData(form);
    const selectedPermissions = Array.from(form.querySelectorAll('input[name="permissions"]:checked')).map(cb => cb.value);

    const payload = {
      display_name: data.display_name.trim(),
      email: data.email ? data.email.trim() : '',
      phone: data.phone ? data.phone.trim() : '',
      role: data.role,
      status: data.status || 'Active',
      teacher_id: data.teacher_id ? Number(data.teacher_id) : null,
      student_id: data.student_id ? Number(data.student_id) : null,
      must_change_password: Boolean(form.querySelector('input[name="must_change_password"]').checked),
      permissions: (data.role === 'super_admin' || data.role === 'admin')
        ? selectedPermissions
        : selectedPermissions.filter(p => p !== 'assistant.view'),
    };

    if (!existingUser) {
      const pwdErr = validateClientPassword(data.password);
      if (pwdErr) {
        alert(pwdErr);
        return;
      }
    }

    try {
      if (existingUser) {
        await api(`/users/${existingUser.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
        alert('User updated successfully.');
      } else {
        payload.username = data.username.trim();
        payload.password = data.password;
        await api('/users', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        alert(`User account '${payload.username}' created successfully.`);
      }
      host.remove();
      if (location.hash.slice(1).startsWith('users')) {
        users();
      }
    } catch (err) {
      showError(err);
    }
  };
}

function onUserRoleChange(select) {
  const role = select.value;
  const staffGroup = document.querySelector('#userStaffLinkGroup');
  const studentGroup = document.querySelector('#userStudentLinkGroup');
  if (staffGroup) staffGroup.style.display = (role === 'staff') ? 'block' : 'none';
  if (studentGroup) studentGroup.style.display = (role === 'student') ? 'block' : 'none';

  resetPermissionsToRoleDefaults();
}

function onUserStaffSelect(select) {
  const opt = select.selectedOptions[0];
  if (!opt || !opt.value) return;
  const form = select.closest('form');
  const nameInput = form?.querySelector('input[name="display_name"]');
  const emailInput = form?.querySelector('input[name="email"]');
  const phoneInput = form?.querySelector('input[name="phone"]');
  if (nameInput && (!nameInput.value || nameInput.value === 'Staff')) nameInput.value = opt.dataset.name || '';
  if (emailInput && !emailInput.value) emailInput.value = opt.dataset.email || '';
  if (phoneInput && !phoneInput.value) phoneInput.value = opt.dataset.phone || '';
}

function onUserStudentSelect(select) {
  const opt = select.selectedOptions[0];
  if (!opt || !opt.value) return;
  const form = select.closest('form');
  const nameInput = form?.querySelector('input[name="display_name"]');
  const emailInput = form?.querySelector('input[name="email"]');
  const phoneInput = form?.querySelector('input[name="phone"]');
  if (nameInput && (!nameInput.value || nameInput.value === 'Student')) nameInput.value = opt.dataset.name || '';
  if (emailInput && !emailInput.value) emailInput.value = opt.dataset.email || '';
  if (phoneInput && !phoneInput.value) phoneInput.value = opt.dataset.phone || '';
}

function setPermissionsAll(checked) {
  const role = document.querySelector('#userFormRoleSelect')?.value || 'staff';
  const isSuperOrAdmin = role === 'super_admin' || role === 'admin';
  document.querySelectorAll('#userFormPermissionsGrid input[name="permissions"]').forEach(cb => {
    if (cb.value === 'assistant.view' && !isSuperOrAdmin) {
      cb.checked = false;
      return;
    }
    cb.checked = checked;
  });
}

function resetPermissionsToRoleDefaults() {
  const role = document.querySelector('#userFormRoleSelect')?.value || 'staff';
  const defaults = _userRolesPermissions?.role_defaults?.[role] || [];
  const defaultsSet = new Set(defaults);
  const isSuperOrAdmin = role === 'super_admin' || role === 'admin';

  document.querySelectorAll('#userFormPermissionsGrid input[name="permissions"]').forEach(cb => {
    const isAssistant = cb.value === 'assistant.view';
    if (isAssistant) {
      cb.checked = isSuperOrAdmin;
      cb.disabled = !isSuperOrAdmin;
      const parentLabel = cb.closest('.permission-item');
      if (parentLabel) parentLabel.style.opacity = isSuperOrAdmin ? '1' : '0.6';
      return;
    }
    cb.checked = isSuperOrAdmin || defaultsSet.has(cb.value);
  });
}

function userResetPasswordModal(userId, username) {
  const host = modal(`Reset Password: ${username}`, `
    <form class="form" id="resetPasswordForm">
      <p class="muted" style="margin-top:0;">Enter a new password for <b>${esc(username)}</b> or generate one automatically.</p>
      <label>
        New Password *
        <div style="display:flex;gap:6px;">
          <input type="text" name="new_password" id="resetNewPasswordInput" required minlength="10" placeholder="Min 10 characters (upper, lower, num, symbol)" value="${generateRandomPassword()}">
          <button type="button" onclick="document.querySelector('#resetNewPasswordInput').value = generateRandomPassword()">Generate</button>
        </div>
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:12px 0;">
        <input type="checkbox" name="must_change_password" checked>
        <span>Require password change upon next login</span>
      </label>
      <div class="form-actions" style="margin-top:16px;">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button class="primary">Reset Password</button>
      </div>
    </form>
  `);

  host.querySelector('#resetPasswordForm').onsubmit = async event => {
    event.preventDefault();
    const data = formData(event.target);
    const pwdErr = validateClientPassword(data.new_password);
    if (pwdErr) {
      alert(pwdErr);
      return;
    }
    try {
      await api(`/users/${userId}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({
          new_password: data.new_password,
          must_change_password: Boolean(event.target.querySelector('input[name="must_change_password"]').checked)
        })
      });
      alert(`Password reset successfully for ${username}.`);
      host.remove();
      if (location.hash.slice(1).startsWith('users')) {
        users();
      }
    } catch (err) {
      showError(err);
    }
  };
}

async function unlockUser(userId) {
  if (!confirm('Unlock this user account and reset failed login attempts?')) return;
  try {
    await api(`/users/${userId}/unlock`, { method: 'POST' });
    alert('User account unlocked.');
    users();
  } catch (err) {
    showError(err);
  }
}

async function toggleUser(userId, currentStatus) {
  const newStatus = currentStatus === 'Active' ? 'Disabled' : 'Active';
  if (!confirm(`Are you sure you want to set this account to ${newStatus}?`)) return;
  try {
    await api(`/users/${userId}/toggle-status`, {
      method: 'POST',
      body: JSON.stringify({ status: newStatus })
    });
    users();
  } catch (err) {
    showError(err);
  }
}

async function userAuditLogModal() {
  try {
    const logs = await api('/users/audit-log?limit=200');
    const cols = [
      { key: 'created_at', label: 'Timestamp', render: r => `<small>${esc((r.created_at || '').replace('T', ' ').slice(0, 19))}</small>` },
      { key: 'username', label: 'User', render: r => `<b>${esc(r.username || '-')}</b>` },
      { key: 'event_type', label: 'Event', render: r => `<span class="badge" style="font-size:11px;">${esc(r.event_type)}</span>` },
      { key: 'success', label: 'Status', render: r => r.success ? '<span style="color:#166534;font-weight:600;">Success</span>' : '<span style="color:#991b1b;font-weight:600;">Failed</span>' },
      { key: 'description', label: 'Details' },
      { key: 'ip_address', label: 'IP Address', render: r => `<small class="muted">${esc(r.ip_address || '-')}</small>` },
    ];
    modal('Security & Authentication Audit Log', `
      <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
        <span class="muted">Showing latest 200 security and login events.</span>
        <button onclick="csvDownload('auth_audit_log.csv', ${JSON.stringify(logs).replace(/"/g, '&quot;')}, [
          { key: 'created_at', label: 'Timestamp' },
          { key: 'username', label: 'User' },
          { key: 'event_type', label: 'Event' },
          { key: 'success', label: 'Success' },
          { key: 'description', label: 'Details' },
          { key: 'ip_address', label: 'IP' }
        ])">Export Log CSV</button>
      </div>
      <div style="max-height:65vh;overflow-y:auto;">
        ${table(logs, cols)}
      </div>
    `);
  } catch (err) {
    showError(err);
  }
}

function exportUsersCsv() {
  const cols = [
    { key: 'id', label: 'ID' },
    { key: 'username', label: 'Username' },
    { key: 'display_name', label: 'Display Name' },
    { key: 'role', label: 'Role' },
    { key: 'status', label: 'Status' },
    { key: 'phone', label: 'Phone' },
    { key: 'email', label: 'Email' },
    { key: 'student_id', label: 'Student ID' },
    { key: 'student_name', label: 'Student Name' },
    { key: 'teacher_id', label: 'Staff ID' },
    { key: 'teacher_name', label: 'Staff Name' },
    { key: 'last_login_at', label: 'Last Login' },
    { key: 'created_at', label: 'Created At' },
  ];
  csvDownload('users.csv', _allUsers || [], cols);
}

async function login(customForm = null) {
  const form = customForm || document.querySelector('#login');
  const errEl = form?.querySelector('.login-error') || document.querySelector('#error');
  try {
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    const response = await api('/auth/login', { method: 'POST', body: JSON.stringify(formData(form)) });
    token = response.token;
    sessionStorage.token = token;
    me = response.user;
    document.querySelectorAll('.modal').forEach(m => m.remove());
    go('dashboard');
  } catch (error) {
    if (errEl) {
      errEl.textContent = error.message;
      errEl.style.display = 'block';
    } else {
      showError(error);
    }
  }
}
function logout() { api('/auth/logout', { method: 'POST' }).catch(() => {}); sessionStorage.clear(); token = ''; me = null; location.hash = ''; boot(); }

/* ==========================================================================
   Expert Learning Hub - Public Frontend Website
   Matches https://expertlearninghub.edu.np with TailAdmin Aesthetic
   ========================================================================== */

const webCourseData = [
  {
    id: 'g10-see',
    title: 'Grade 10 SEE Master Class',
    category: 'school',
    categoryLabel: 'Secondary & SEE',
    icon: '📚',
    duration: 'Full Academic Year',
    level: 'Class 10 (SEE)',
    badge: 'High Board Success',
    desc: 'Intensive board examination coaching for Secondary Education Examination (SEE). Features syllabus completion, daily problem-solving, and continuous mock tests.',
    subjects: ['Compulsory Mathematics', 'Science (Physics, Chem, Bio)', 'OPT. Mathematics', 'English', 'Nepali'],
    schedule: 'Morning & Evening Batches',
  },
  {
    id: 'g8-9-tuition',
    title: 'Grade 8 & 9 Foundation Coaching',
    category: 'school',
    categoryLabel: 'Basic & Secondary',
    icon: '✏️',
    duration: 'Daily Routine',
    level: 'Classes 8 & 9',
    badge: 'Core Foundation',
    desc: 'Comprehensive concept-building for basic level examinations. Strengthens fundamentals in algebra, science experiments, grammar, and analytical thinking.',
    subjects: ['Mathematics', 'Science', 'English Grammar & Writing', 'Social Studies'],
    schedule: '6:00 PM - 8:00 PM Sessions',
  },
  {
    id: 'plus2-science',
    title: '+2 Science Bridge & Board Prep',
    category: 'plus2',
    categoryLabel: '+2 Science',
    icon: '🔬',
    duration: '3 - 12 Months',
    level: 'Grade 11 & 12 / Bridge Course',
    badge: 'Pre-Engineering / Medical',
    desc: 'Deep conceptual preparation for Grade 11 & 12 board examinations and competitive medical & engineering entrance exams across Nepal.',
    subjects: ['Physics', 'Chemistry', 'Biology', 'Higher Mathematics'],
    schedule: 'Flexible Batch Timings',
  },
  {
    id: 'plus2-mgmt',
    title: '+2 Management & Accounting Mastery',
    category: 'plus2',
    categoryLabel: '+2 Commerce',
    icon: '📊',
    duration: 'Full Term',
    level: 'Grade 11 & 12',
    badge: 'Finance & Business',
    desc: 'Practical financial accounting, modern economics, and business studies designed to prepare future chartered accountants and managers.',
    subjects: ['Financial Accounting', 'Economics', 'Business Mathematics', 'English'],
    schedule: 'Morning / Evening Batches',
  },
  {
    id: 'iot-mentorship',
    title: 'IoT & Hardware Prototyping Mentorship',
    category: 'tech',
    categoryLabel: 'Tech & IoT',
    icon: '⚡',
    duration: '8 - 12 Weeks',
    level: 'Beginner to Advanced',
    badge: 'Hands-on Lab',
    desc: 'Join our cutting-edge mentorship program. Build real-world IoT projects, interface microcontrollers (ESP32/Arduino), connect cloud telemetry, and create smart automation.',
    subjects: ['Embedded C / Python', 'Sensors & Microcontrollers', 'Cloud IoT Telemetry', 'PCB & Hardware Prototyping'],
    schedule: 'Weekend & Lab Sessions',
  },
  {
    id: 'software-dev',
    title: 'Software, Web & App Development',
    category: 'tech',
    categoryLabel: 'Software & Coding',
    icon: '💻',
    duration: '12 Weeks',
    level: 'Practical Bootcamp',
    badge: 'Industry Project',
    desc: 'Master full-stack programming, JavaScript/Python fundamentals, web interface design, database systems, and modern version control.',
    subjects: ['HTML5/CSS3/JavaScript', 'Python & APIs', 'Database Design (SQL)', 'Git & Deployment'],
    schedule: 'Practical Computer Lab',
  },
  {
    id: 'korean-lang',
    title: 'Korean Language (EPS-TOPIK)',
    category: 'language',
    categoryLabel: 'Global Languages',
    icon: '🇰🇷',
    duration: '3 - 6 Months',
    level: 'Levels 1 - 4',
    badge: 'EPS Employment Prep',
    desc: 'Specialized language coaching for EPS-TOPIK examination and South Korean employment visas. Taught by experienced language instructors with native audio materials.',
    subjects: ['Hangul Alphabet & Grammar', 'Listening & Reading Comprehension', 'Mock Exam Drills', 'Interview Orientation'],
    schedule: 'Daily Morning & Evening',
  },
  {
    id: 'japanese-lang',
    title: 'Japanese Language (NAT-TEST / JLPT)',
    category: 'language',
    categoryLabel: 'Global Languages',
    icon: '🇯🇵',
    duration: '4 - 6 Months',
    level: 'N5 & N4 Levels',
    badge: 'Study in Japan',
    desc: 'Structured curriculum preparing students for NAT-TEST and JLPT N5/N4 certifications, college admissions in Japan, and SSW visa pathways.',
    subjects: ['Hiragana, Katakana & Kanji', 'Everyday Conversation', 'Listening Practice', 'Visa Documentation Guidance'],
    schedule: 'Daily Dedicated Batches',
  },
  {
    id: 'english-fluency',
    title: 'English Fluency & IELTS/PTE Preparation',
    category: 'language',
    categoryLabel: 'Global Languages',
    icon: '🇬🇧',
    duration: '6 - 8 Weeks',
    level: 'All Proficiency Levels',
    badge: 'Official Test Prep',
    desc: 'Spoken English fluency, business communication, and targeted score improvement for IELTS and PTE Academic examinations.',
    subjects: ['Speaking & Phonetics', 'Academic Writing Task 1 & 2', 'Listening Speed Drills', 'Reading Strategies'],
    schedule: 'Intensive Batches',
  },
  {
    id: 'personality-dev',
    title: 'Personality & Leadership Development',
    category: 'language',
    categoryLabel: 'Professional Skills',
    icon: '🌟',
    duration: '4 Weeks',
    level: 'Open to All',
    badge: 'Career Boost',
    desc: 'Confidence building, public speaking, modern workplace communication, and interview skills to help you excel in professional life.',
    subjects: ['Public Speaking', 'Body Language & Etiquette', 'Interview Simulation', 'Leadership Psychology'],
      schedule: 'Special Evening Sessions',
  }
];

window._currentWebCategory = 'all';
window._websiteCmsData = null;

async function loadWebsiteCmsData(forceRefresh = false) {
  if (!forceRefresh && window._websiteCmsData) return window._websiteCmsData;
  try {
    window._websiteCmsData = await api('/public/website-data');
  } catch (e) {
    if (!window._websiteCmsData) window._websiteCmsData = {};
  }
  return window._websiteCmsData;
}

function filterWebCourses(category) {
  window._currentWebCategory = category;
  document.querySelectorAll('.elh-filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.category === category);
  });
  const container = document.querySelector('#webCourseGridContainer');
  if (!container) return;

  const rawList = window._websiteCmsData?.courses || webCourseData;
  const activeCourses = rawList.filter(c => c.status !== 'Draft');
  const filtered = category === 'all'
    ? activeCourses
    : activeCourses.filter(c => {
        const cat = (c.category || '').toLowerCase();
        return cat === category || (category === 'school' && cat === 'secondary') || cat.includes(category);
      });

  if (!filtered.length) {
    container.innerHTML = '<p class="muted" style="grid-column:1/-1;text-align:center;padding:30px 0;">No active courses in this category at the moment.</p>';
    return;
  }

  container.innerHTML = filtered.map(c => {
    const topics = c.topics || c.subjects || [];
    const catLabel = c.category_label || c.categoryLabel || c.category;
    const badge = c.badge || c.level || 'Featured';
    const desc = c.description || c.desc || '';
    const feeNote = c.fee_note ? `<div style="font-size:11px;color:var(--brand);margin-top:4px;">💳 ${esc(c.fee_note)}</div>` : '';
    const icon = c.icon || '📚';
    return `
      <div class="elh-course-card">
        <div>
          <div class="elh-course-card-top">
            <div class="elh-course-icon">${icon}</div>
            <span class="elh-course-cat">${esc(catLabel)}</span>
          </div>
          <h3 class="elh-course-title">${esc(c.title)}</h3>
          <p class="elh-course-desc">${esc(desc)}</p>
          ${feeNote}
          <div class="elh-course-tags">
            ${topics.map(s => `<span class="elh-course-tag">${esc(s)}</span>`).join('')}
          </div>
        </div>
        <div class="elh-course-footer">
          <div class="elh-course-meta">
            <small>${esc(c.duration || 'Flexible')}</small>
            <b>${esc(badge)}</b>
          </div>
          <button class="primary" style="font-size:12px;padding:6px 14px;border-radius:var(--radius-pill);" onclick="prefillInquiryCourse('${esc(c.title)}')">
            Inquire / Apply →
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function prefillInquiryCourse(courseName) {
  const selectEl = document.querySelector('#inquiryCourseSelect');
  if (selectEl) selectEl.value = courseName;
  const target = document.querySelector('#contactSection');
  if (target) target.scrollIntoView({ behavior: 'smooth' });
}

async function handleWebInquiry(event) {
  event.preventDefault();
  const form = event.target;
  const submitBtn = form.querySelector('button[type="submit"]');
  const alertEl = document.querySelector('#inquirySuccessAlert');
  const payload = formData(form);

  try {
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Submitting inquiry...'; }
    const res = await api('/public/inquiry', {
      method: 'POST',
      body: JSON.stringify({
        full_name: payload.full_name,
        phone: payload.phone,
        email: payload.email || '',
        grade: payload.grade || '',
        course_interest: payload.course_interest || '',
        message: payload.message || ''
      })
    });
    if (alertEl) {
      alertEl.innerHTML = `
        <div style="background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:14px 18px;border-radius:10px;margin-bottom:16px;">
          <b style="display:block;font-size:15px;margin-bottom:4px;">✓ Inquiry Submitted Successfully!</b>
          <span>${esc(res.message || 'Thank you! Our academic counselors will reach out to you shortly.')}</span>
        </div>
      `;
      alertEl.style.display = 'block';
    } else {
      alert(res.message || 'Inquiry submitted successfully!');
    }
    form.reset();
  } catch (err) {
    alert('Could not submit inquiry: ' + (err.message || String(err)));
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Submit Online Inquiry →'; }
  }
}

function openPortalLoginModal(defaultRole = '') {
  const host = document.createElement('div');
  host.className = 'modal';
  host.innerHTML = `
    <section class="panel modal-panel" style="max-width:440px;border-radius:18px;padding:28px 28px 24px;box-shadow:0 25px 50px -12px rgba(0,0,0,0.25);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <div style="width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg, #465fff, #7c3aed);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px;">E</div>
          <div>
            <h3 style="margin:0;font-size:18px;font-weight:800;color:var(--ink-dark);">ELH Portal Login</h3>
            <small class="muted">Access your personalized portal</small>
          </div>
        </div>
        <button class="icon-btn" aria-label="Close" onclick="this.closest('.modal').remove()" style="padding:4px;">
          ${uiIcon('close', 18)}
        </button>
      </div>

      <div style="display:flex;gap:6px;background:var(--line-subtle);padding:4px;border-radius:10px;margin-bottom:20px;">
        <button type="button" class="btn portal-role-pill ${defaultRole === 'student' ? 'active' : ''}" onclick="switchModalRole(this, 'student')" style="flex:1;font-size:12px;padding:6px 8px;border-radius:7px;${defaultRole === 'student' ? 'background:var(--brand);color:#fff;border-color:var(--brand);' : ''}">Student</button>
        <button type="button" class="btn portal-role-pill ${defaultRole === 'teacher' ? 'active' : ''}" onclick="switchModalRole(this, 'teacher')" style="flex:1;font-size:12px;padding:6px 8px;border-radius:7px;${defaultRole === 'teacher' ? 'background:var(--brand);color:#fff;border-color:var(--brand);' : ''}">Teacher / Staff</button>
        <button type="button" class="btn portal-role-pill ${(!defaultRole || defaultRole === 'admin') ? 'active' : ''}" onclick="switchModalRole(this, 'admin')" style="flex:1;font-size:12px;padding:6px 8px;border-radius:7px;${(!defaultRole || defaultRole === 'admin') ? 'background:var(--brand);color:#fff;border-color:var(--brand);' : ''}">Admin</button>
      </div>

      <div class="login-error" style="display:none;background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;"></div>

      <form class="form" onsubmit="event.preventDefault(); login(this);">
        <label>Username or Email
          <input name="username" required autofocus placeholder="Enter your username or email" autocomplete="username">
        </label>
        <label>Password
          <input type="password" name="password" required placeholder="••••••••" autocomplete="current-password">
        </label>
        <button class="primary" type="submit" style="width:100%;margin-top:12px;padding:11px;font-weight:700;font-size:14px;border-radius:10px;">
          Sign In to Portal →
        </button>
      </form>

      <div style="text-align:center;margin-top:18px;font-size:12px;color:var(--muted);">
        <span>Need credentials or forgot password? Contact the institute administration at <b>+977 9800924090</b></span>
      </div>
    </section>
  `;
  host.onclick = e => { if (e.target === host) host.remove(); };
  document.body.append(host);
  host.querySelector('input[name="username"]')?.focus();
}

function switchModalRole(btn, role) {
  btn.parentElement.querySelectorAll('.portal-role-pill').forEach(b => {
    b.style.background = '';
    b.style.color = '';
    b.style.borderColor = '';
  });
  btn.style.background = 'var(--brand)';
  btn.style.color = '#ffffff';
  btn.style.borderColor = 'var(--brand)';
  const input = btn.closest('.modal-panel')?.querySelector('input[name="username"]');
  if (input) {
    if (role === 'student') input.placeholder = 'e.g. your student username or phone';
    else if (role === 'teacher') input.placeholder = 'e.g. bhawani_timsina or teacher username';
    else input.placeholder = 'e.g. admin or staff';
    input.focus();
  }
}

/* ==========================================================================
   Website Content Management System (CMS) & Admission Leads Engine
   ========================================================================== */

function showCmsToast(message, isError = false) {
  let toast = document.querySelector('.cms-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.className = 'cms-toast';
    document.body.append(toast);
  }
  toast.innerHTML = `<span style="font-size:18px;">${isError ? '⚠️' : '✅'}</span><span>${esc(message)}</span>`;
  toast.style.borderColor = isError ? 'var(--danger)' : 'var(--brand)';
  toast.classList.add('show');
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {
    toast.classList.remove('show');
  }, 2800);
}

async function saveCmsSection(sectionKey, data, successMessage = 'Section updated successfully!') {
  try {
    const updated = await api(`/cms/sections/${sectionKey}`, {
      method: 'PUT',
      body: JSON.stringify({ data })
    });
    if (!window._cmsData) window._cmsData = {};
    window._cmsData[sectionKey] = updated;
    if (window._websiteCmsData) {
      window._websiteCmsData[sectionKey] = updated;
    }
    showCmsToast(successMessage);
    return updated;
  } catch (error) {
    showError(error);
    throw error;
  }
}

async function resetCmsDefaults() {
  if (!confirm('Are you sure you want to reset all website CMS content to default factory values? Any custom changes across all 10 sections will be restored.')) {
    return;
  }
  try {
    const result = await api('/cms/reset-defaults', { method: 'POST' });
    window._cmsData = result;
    window._websiteCmsData = result;
    showCmsToast('All website sections have been reset to factory defaults!');
    await cms();
  } catch (error) {
    showError(error);
  }
}

async function cms() {
  if (!has('cms.manage')) {
    alert('Access Denied: You do not have permission to manage website content.');
    go('dashboard');
    return;
  }

  let content = {};
  try {
    content = await api('/cms/content');
    window._cmsData = content;
  } catch (err) {
    showError(err);
    return;
  }

  const activeTab = window._activeCmsTab || 'hero';

  const tabs = [
    { id: 'hero', label: '📢 Hero & Announcement' },
    { id: 'general', label: '🏢 Institute Profile' },
    { id: 'stats', label: '📊 Live Statistics' },
    { id: 'courses', label: '🎓 Courses & Syllabi' },
    { id: 'iot', label: '🤖 Tech & IoT Lab' },
    { id: 'languages', label: '🌏 Languages Hub' },
    { id: 'pillars', label: '🏛 4 Pillars' },
    { id: 'events', label: '📅 Events & Workshops' },
    { id: 'testimonials', label: '💬 Reviews' },
    { id: 'faqs', label: '❓ FAQs' },
    { id: 'inquiries', label: '📬 Admission Leads' }
  ];

  const tabsHtml = `
    <div class="cms-nav-tabs">
      ${tabs.map(t => `
        <button class="cms-tab-btn ${t.id === activeTab ? 'active' : ''}" onclick="switchCmsTab('${t.id}')">
          ${esc(t.label)}
        </button>
      `).join('')}
    </div>
  `;

  const topActions = `
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <a href="#home" target="_blank" class="button" style="display:inline-flex;align-items:center;gap:6px;text-decoration:none;font-weight:600;">
        👁️ View Live Website
      </a>
      <button class="danger" onclick="resetCmsDefaults()">
        🔄 Reset Defaults
      </button>
    </div>
  `;

  shell(
    'Website CMS & Portal Content Manager',
    'Manage public website content, academic programs, language tracks, events, testimonials, and live student admission leads',
    `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
        ${tabsHtml}
        ${topActions}
      </div>
      <div id="cmsTabContainer">
        ${await renderCmsTabContent(activeTab)}
      </div>
    `
  );
}

async function inquiries() {
  window._activeCmsTab = 'inquiries';
  await cms();
}

async function switchCmsTab(tabId) {
  window._activeCmsTab = tabId;
  document.querySelectorAll('.cms-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('onclick')?.includes(`'${tabId}'`));
  });
  const container = document.getElementById('cmsTabContainer');
  if (container) {
    container.innerHTML = '<div style="padding:40px;text-align:center;"><p class="muted">Loading section...</p></div>';
    container.innerHTML = await renderCmsTabContent(tabId);
  }
}

async function renderCmsTabContent(tabId) {
  const data = window._cmsData || {};
  switch (tabId) {
    case 'hero':
      return renderCmsHeroTab(data.hero);
    case 'general':
      return renderCmsGeneralTab(data.general);
    case 'stats':
      return renderCmsStatsTab(data.stats);
    case 'courses':
      return renderCmsCoursesTab(data.courses || []);
    case 'iot':
      return renderCmsIotTab(data.iot_showcase || {});
    case 'languages':
      return renderCmsLanguagesTab(data.languages || []);
    case 'pillars':
      return renderCmsPillarsTab(data.pillars || []);
    case 'events':
      return renderCmsEventsTab(data.events || []);
    case 'testimonials':
      return renderCmsTestimonialsTab(data.testimonials || []);
    case 'faqs':
      return renderCmsFaqsTab(data.faqs || []);
    case 'inquiries':
      return await renderCmsInquiriesTab();
    default:
      return renderCmsHeroTab(data.hero);
  }
}

function renderCmsHeroTab(data) {
  const hero = data || {};
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Hero Banner & Announcement Strip</h3>
          <p>Configure the top banner, primary value proposition, background badge, and calls-to-action.</p>
        </div>
      </div>
      <form id="cmsHeroForm" onsubmit="event.preventDefault(); saveCmsHero(this);">
        <h4 style="margin:0 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">📢 Announcement Strip</h4>
        <div class="cms-grid-2" style="margin-bottom:20px;">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-weight:600;">
            <input type="checkbox" name="announcement_active" ${hero.announcement_active !== false ? 'checked' : ''} style="width:18px;height:18px;">
            <span>Display Announcement Bar on Website</span>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Announcement Message</span>
            <input type="text" name="announcement_text" value="${esc(hero.announcement_text || '')}" placeholder="e.g. Admissions Open 2024–25" required>
          </label>
        </div>

        <h4 style="margin:20px 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">🎯 Main Hero Pitch & Headings</h4>
        <div class="cms-grid-2">
          <label class="span-2">
            <span style="font-weight:600;font-size:13px;">Hero Badge / Top Pill</span>
            <input type="text" name="badge" value="${esc(hero.badge || '')}" placeholder="e.g. Leading Coaching & Tech Mentorship in Morang" required>
          </label>
          <label class="span-2">
            <span style="font-weight:600;font-size:13px;">Main Headline / Title</span>
            <input type="text" name="title" value="${esc(hero.title || '')}" placeholder="e.g. Empowering Future Leaders & Tech Innovators" required>
          </label>
          <label class="span-2">
            <span style="font-weight:600;font-size:13px;">Subtitle / Narrative Description</span>
            <textarea name="subtitle" rows="3" required>${esc(hero.subtitle || '')}</textarea>
          </label>
        </div>

        <h4 style="margin:20px 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">🔘 Call-To-Action (CTA) Buttons</h4>
        <div class="cms-grid-2">
          <label>
            <span style="font-weight:600;font-size:13px;">Primary CTA Button Label</span>
            <input type="text" name="cta_primary_text" value="${esc(hero.cta_primary_text || 'Explore Courses')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Primary CTA Link / Anchor</span>
            <input type="text" name="cta_primary_link" value="${esc(hero.cta_primary_link || '#coursesSection')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Secondary CTA Button Label</span>
            <input type="text" name="cta_secondary_text" value="${esc(hero.cta_secondary_text || 'IoT Mentorship')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Secondary CTA Link / Anchor</span>
            <input type="text" name="cta_secondary_link" value="${esc(hero.cta_secondary_link || '#iotSection')}" required>
          </label>
        </div>

        <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
          <button type="submit" class="primary">💾 Save Hero Section</button>
        </div>
      </form>
    </div>
  `;
}

async function saveCmsHero(form) {
  const fd = new FormData(form);
  const data = {
    announcement_active: form.querySelector('input[name="announcement_active"]')?.checked ?? true,
    announcement_text: fd.get('announcement_text') || '',
    badge: fd.get('badge') || '',
    title: fd.get('title') || '',
    subtitle: fd.get('subtitle') || '',
    cta_primary_text: fd.get('cta_primary_text') || '',
    cta_primary_link: fd.get('cta_primary_link') || '',
    cta_secondary_text: fd.get('cta_secondary_text') || '',
    cta_secondary_link: fd.get('cta_secondary_link') || ''
  };
  await saveCmsSection('hero', data, 'Hero section saved successfully!');
}

function renderCmsGeneralTab(data) {
  const gen = data || {};
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Institute Profile, Contact & Social Links</h3>
          <p>Control organization identity, phone numbers, location, working hours, and social channels displayed on the header, contact section, and footer.</p>
        </div>
      </div>
      <form id="cmsGeneralForm" onsubmit="event.preventDefault(); saveCmsGeneral(this);">
        <h4 style="margin:0 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">🏢 Identity & Tagline</h4>
        <div class="cms-grid-2">
          <label>
            <span style="font-weight:600;font-size:13px;">Institute Name</span>
            <input type="text" name="name" value="${esc(gen.name || 'Expert Learning Hub')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Tagline / Motto</span>
            <input type="text" name="tagline" value="${esc(gen.tagline || 'Redefining Education Through Excellence & Innovation')}" required>
          </label>
          <label class="span-2">
            <span style="font-weight:600;font-size:13px;">Physical Campus Address</span>
            <input type="text" name="address" value="${esc(gen.address || 'Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal')}" required>
          </label>
        </div>

        <h4 style="margin:20px 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">📞 Contact & Support</h4>
        <div class="cms-grid-3">
          <label>
            <span style="font-weight:600;font-size:13px;">Primary Phone Number</span>
            <input type="text" name="phone" value="${esc(gen.phone || '+977 9800924090')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Secondary / Mobile Phone</span>
            <input type="text" name="alt_phone" value="${esc(gen.alt_phone || '+977 9842121118')}">
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Official Email Address</span>
            <input type="email" name="email" value="${esc(gen.email || 'info@expertlearninghub.edu.np')}" required>
          </label>
          <label class="span-3">
            <span style="font-weight:600;font-size:13px;">Working Hours</span>
            <input type="text" name="working_hours" value="${esc(gen.working_hours || 'Sun - Fri: 6:00 AM - 7:00 PM')}">
          </label>
        </div>

        <h4 style="margin:20px 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">🌐 Social Media Channels</h4>
        <div class="cms-grid-2">
          <label>
            <span style="font-weight:600;font-size:13px;">Facebook Page URL</span>
            <input type="url" name="facebook_url" value="${esc(gen.facebook_url || '')}" placeholder="https://facebook.com/...">
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">YouTube Channel URL</span>
            <input type="url" name="youtube_url" value="${esc(gen.youtube_url || '')}" placeholder="https://youtube.com/@...">
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Instagram Profile URL</span>
            <input type="url" name="instagram_url" value="${esc(gen.instagram_url || '')}" placeholder="https://instagram.com/...">
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">TikTok Profile URL</span>
            <input type="url" name="tiktok_url" value="${esc(gen.tiktok_url || '')}" placeholder="https://tiktok.com/@...">
          </label>
        </div>

        <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
          <button type="submit" class="primary">💾 Save Institute Profile</button>
        </div>
      </form>
    </div>
  `;
}

async function saveCmsGeneral(form) {
  const fd = new FormData(form);
  const data = {
    name: fd.get('name') || '',
    tagline: fd.get('tagline') || '',
    address: fd.get('address') || '',
    phone: fd.get('phone') || '',
    alt_phone: fd.get('alt_phone') || '',
    email: fd.get('email') || '',
    working_hours: fd.get('working_hours') || '',
    facebook_url: fd.get('facebook_url') || '',
    youtube_url: fd.get('youtube_url') || '',
    instagram_url: fd.get('instagram_url') || '',
    tiktok_url: fd.get('tiktok_url') || '',
    map_embed_url: fd.get('map_embed_url') || ''
  };
  await saveCmsSection('general', data, 'Institute profile saved successfully!');
}

function renderCmsStatsTab(data) {
  const stats = data || {};
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Impact Numbers & Statistics</h3>
          <p>Highlight verifiable key metrics on the website to build confidence with parents and applicants.</p>
        </div>
      </div>
      <form id="cmsStatsForm" onsubmit="event.preventDefault(); saveCmsStats(this);">
        <div class="cms-grid-2">
          <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
            <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Stat Metric 1</span>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Number / Counter</span>
              <input type="text" name="students_count" value="${esc(stats.students_count || '500+')}" required>
            </label>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Description Label</span>
              <input type="text" name="students_label" value="${esc(stats.students_label || 'Students Mentored')}" required>
            </label>
          </div>
          <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
            <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Stat Metric 2</span>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Number / Counter</span>
              <input type="text" name="teachers_count" value="${esc(stats.teachers_count || '14+')}" required>
            </label>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Description Label</span>
              <input type="text" name="teachers_label" value="${esc(stats.teachers_label || 'Expert Educators')}" required>
            </label>
          </div>
          <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
            <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Stat Metric 3</span>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Number / Counter</span>
              <input type="text" name="success_rate" value="${esc(stats.success_rate || '98%')}" required>
            </label>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Description Label</span>
              <input type="text" name="success_label" value="${esc(stats.success_label || 'Academic Success Rate')}" required>
            </label>
          </div>
          <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
            <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Stat Metric 4</span>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Number / Counter</span>
              <input type="text" name="projects_count" value="${esc(stats.projects_count || '25+')}" required>
            </label>
            <label style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-muted);">Description Label</span>
              <input type="text" name="projects_label" value="${esc(stats.projects_label || 'IoT & Tech Capstones')}" required>
            </label>
          </div>
        </div>
        <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
          <button type="submit" class="primary">💾 Save Statistics</button>
        </div>
      </form>
    </div>
  `;
}

async function saveCmsStats(form) {
  const fd = new FormData(form);
  const data = {
    students_count: fd.get('students_count') || '',
    students_label: fd.get('students_label') || '',
    teachers_count: fd.get('teachers_count') || '',
    teachers_label: fd.get('teachers_label') || '',
    success_rate: fd.get('success_rate') || '',
    success_label: fd.get('success_label') || '',
    projects_count: fd.get('projects_count') || '',
    projects_label: fd.get('projects_label') || ''
  };
  await saveCmsSection('stats', data, 'Statistics saved successfully!');
}

function renderCmsCoursesTab(courses) {
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Academic Programs & Syllabi (${courses.length})</h3>
          <p>Create and edit courses, grade levels, fee notes, and detailed curriculum syllabus topics.</p>
        </div>
        <div>
          <button class="primary" onclick="cmsCourseModal()">+ Add New Course</button>
        </div>
      </div>

      <div class="cms-list-grid">
        ${courses.map(c => `
          <div class="cms-item-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
              <div>
                <span class="badge" style="font-size:11px;background:rgba(56,189,248,0.15);color:var(--brand);margin-right:6px;">${esc(c.category_label || c.category)}</span>
                <span class="badge ${c.status === 'Draft' ? '' : 'active'}" style="font-size:11px;">${esc(c.status || 'Published')}</span>
              </div>
              <span style="font-size:11px;font-weight:700;color:var(--brand);">${esc(c.badge || '')}</span>
            </div>
            <h4>${esc(c.title)}</h4>
            <p style="font-size:13px;color:var(--text-muted);margin:6px 0 10px;line-height:1.5;">${esc(c.description || '')}</p>
            <div style="font-size:12px;color:var(--text-strong);margin-bottom:8px;">
              ⏱ <b>Duration:</b> ${esc(c.duration || 'N/A')}
              ${c.fee_note ? ` • 💳 <b>Fee:</b> ${esc(c.fee_note)}` : ''}
            </div>
            ${c.topics && c.topics.length ? `
              <div style="margin:8px 0;padding-left:16px;">
                <small class="muted" style="font-weight:600;display:block;margin-bottom:4px;">Syllabus Highlights:</small>
                <ul style="margin:0;padding-left:14px;font-size:12px;color:var(--text-muted);">
                  ${c.topics.slice(0, 3).map(t => `<li>${esc(t)}</li>`).join('')}
                  ${c.topics.length > 3 ? `<li><i>+${c.topics.length - 3} more topics...</i></li>` : ''}
                </ul>
              </div>
            ` : ''}
            <div class="cms-item-actions">
              <button class="small" onclick="cmsCourseModal(${c.id})">Edit Course</button>
              <button class="small" onclick="toggleCmsCourseStatus(${c.id})">
                ${c.status === 'Draft' ? 'Publish' : 'Make Draft'}
              </button>
              <button class="small danger" onclick="deleteCmsCourse(${c.id})">Delete</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function cmsCourseModal(courseId = null) {
  const courses = window._cmsData?.courses || [];
  const existing = courseId ? courses.find(c => c.id === courseId) : null;
  const categories = [
    { value: 'secondary', label: 'Secondary (8-10)' },
    { value: 'plus2', label: '+2 Science & Commerce' },
    { value: 'tech', label: 'Tech & IoT' },
    { value: 'language', label: 'Global Languages' },
    { value: 'tuition', label: 'School Coaching' }
  ];

  const topicsText = (existing?.topics || []).join('\n');

  const host = modal(existing ? `Edit Course: ${existing.title}` : 'Add New Academic Course', `
    <form class="form two-col" id="cmsCourseForm">
      <label class="span-2">
        <span>Course Title *</span>
        <input name="title" required value="${esc(existing?.title || '')}" placeholder="e.g. Grade 10 SEE Master Class">
      </label>
      <label>
        <span>Category Track *</span>
        <select name="category" onchange="const opt = this.options[this.selectedIndex]; this.form.category_label.value = opt.text;">
          ${categories.map(cat => `
            <option value="${cat.value}" ${existing?.category === cat.value ? 'selected' : ''}>${cat.label}</option>
          `).join('')}
        </select>
      </label>
      <label>
        <span>Category Display Label *</span>
        <input name="category_label" required value="${esc(existing?.category_label || 'Secondary (8-10)')}">
      </label>
      <label>
        <span>Badge / Tag</span>
        <input name="badge" value="${esc(existing?.badge || '')}" placeholder="e.g. Flagship, Popular">
      </label>
      <label>
        <span>Duration</span>
        <input name="duration" value="${esc(existing?.duration || 'Full Academic Year')}" placeholder="e.g. Full Academic Year">
      </label>
      <label>
        <span>Fee Notes / Structure</span>
        <input name="fee_note" value="${esc(existing?.fee_note || '')}" placeholder="e.g. Monthly installment available">
      </label>
      <label>
        <span>Status *</span>
        <select name="status">
          <option value="Published" ${existing?.status !== 'Draft' ? 'selected' : ''}>Published</option>
          <option value="Draft" ${existing?.status === 'Draft' ? 'selected' : ''}>Draft (Hidden)</option>
        </select>
      </label>
      <label class="span-2">
        <span>Course Description *</span>
        <textarea name="description" rows="3" required>${esc(existing?.description || '')}</textarea>
      </label>
      <label class="span-2">
        <span>Syllabus Highlights (One topic per line)</span>
        <textarea name="topics" rows="5" placeholder="Topic 1\nTopic 2\nTopic 3">${esc(topicsText)}</textarea>
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">${existing ? 'Save Changes' : 'Create Course'}</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const topics = (fd.get('topics') || '').split('\n').map(t => t.trim()).filter(Boolean);
    const updatedCourses = [...(window._cmsData?.courses || [])];
    if (existing) {
      const idx = updatedCourses.findIndex(c => c.id === courseId);
      if (idx !== -1) {
        updatedCourses[idx] = {
          ...updatedCourses[idx],
          title: fd.get('title'),
          category: fd.get('category'),
          category_label: fd.get('category_label'),
          badge: fd.get('badge'),
          duration: fd.get('duration'),
          fee_note: fd.get('fee_note'),
          status: fd.get('status'),
          description: fd.get('description'),
          topics
        };
      }
    } else {
      const newId = Math.max(0, ...updatedCourses.map(c => c.id || 0)) + 1;
      updatedCourses.unshift({
        id: newId,
        title: fd.get('title'),
        category: fd.get('category'),
        category_label: fd.get('category_label'),
        badge: fd.get('badge'),
        duration: fd.get('duration'),
        fee_note: fd.get('fee_note'),
        status: fd.get('status'),
        description: fd.get('description'),
        topics
      });
    }
    host.remove();
    await saveCmsSection('courses', updatedCourses, existing ? 'Course updated successfully!' : 'New course added successfully!');
    switchCmsTab('courses');
  };
}

async function toggleCmsCourseStatus(courseId) {
  const updatedCourses = [...(window._cmsData?.courses || [])];
  const item = updatedCourses.find(c => c.id === courseId);
  if (!item) return;
  item.status = item.status === 'Draft' ? 'Published' : 'Draft';
  await saveCmsSection('courses', updatedCourses, `Course is now ${item.status}!`);
  switchCmsTab('courses');
}

async function deleteCmsCourse(courseId) {
  if (!confirm('Are you sure you want to delete this course from the website?')) return;
  const updatedCourses = (window._cmsData?.courses || []).filter(c => c.id !== courseId);
  await saveCmsSection('courses', updatedCourses, 'Course removed from website!');
  switchCmsTab('courses');
}

function renderCmsIotTab(data) {
  const iot = data || {};
  const highlights = iot.highlights || [
    { title: 'ESP32 & Microcontroller Architecture', desc: 'GPIO programming, I2C/SPI sensor interfaces, and embedded C++.' },
    { title: 'Sensor Integration & Robotics', desc: 'Ultrasonic, temperature, gas, motion sensors, and motor-driven automation kits.' },
    { title: 'Cloud Dashboards & MQTT', desc: 'Connecting real-world sensors to web dashboards and live mobile telemetry.' },
    { title: 'Real-World Engineering Projects', desc: 'Smart agriculture, automatic lighting, and environmental monitors.' }
  ];

  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Tech & IoT Engineering Mentorship</h3>
          <p>Highlight the cutting-edge robotics, microcontrollers, embedded systems, and capstone features of the lab.</p>
        </div>
      </div>
      <form id="cmsIotForm" onsubmit="event.preventDefault(); saveCmsIot(this);">
        <h4 style="margin:0 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">🤖 Header & Value Proposition</h4>
        <div class="cms-grid-2">
          <label>
            <span style="font-weight:600;font-size:13px;">Section Badge</span>
            <input type="text" name="badge" value="${esc(iot.badge || 'Future-Proof Technology')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">Main Title</span>
            <input type="text" name="title" value="${esc(iot.title || 'Hardware, Embedded Firmware & Cloud Telemetry')}" required>
          </label>
          <label class="span-2">
            <span style="font-weight:600;font-size:13px;">Subtitle / Narrative</span>
            <textarea name="subtitle" rows="3" required>${esc(iot.subtitle || '')}</textarea>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">CTA Button Text</span>
            <input type="text" name="cta_text" value="${esc(iot.cta_text || 'Enroll in IoT Program')}" required>
          </label>
          <label>
            <span style="font-weight:600;font-size:13px;">CTA Button Link</span>
            <input type="text" name="cta_link" value="${esc(iot.cta_link || '#inquiry')}" required>
          </label>
        </div>

        <h4 style="margin:20px 0 12px;font-size:14px;color:var(--brand);text-transform:uppercase;letter-spacing:0.5px;">⚙️ 4 Laboratory Highlights</h4>
        <div class="cms-grid-2">
          ${[0, 1, 2, 3].map(i => {
            const h = highlights[i] || {};
            return `
              <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
                <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Highlight ${i + 1}</span>
                <label style="margin-top:8px;">
                  <span style="font-size:12px;color:var(--text-muted);">Title</span>
                  <input type="text" name="hl_title_${i}" value="${esc(h.title || '')}" required>
                </label>
                <label style="margin-top:8px;">
                  <span style="font-size:12px;color:var(--text-muted);">Description</span>
                  <textarea name="hl_desc_${i}" rows="2" required>${esc(h.desc || '')}</textarea>
                </label>
              </div>
            `;
          }).join('')}
        </div>

        <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
          <button type="submit" class="primary">💾 Save IoT Showcase</button>
        </div>
      </form>
    </div>
  `;
}

async function saveCmsIot(form) {
  const fd = new FormData(form);
  const highlights = [];
  for (let i = 0; i < 4; i++) {
    const title = fd.get(`hl_title_${i}`) || '';
    const desc = fd.get(`hl_desc_${i}`) || '';
    if (title || desc) {
      highlights.push({ title, desc });
    }
  }
  const data = {
    badge: fd.get('badge') || '',
    title: fd.get('title') || '',
    subtitle: fd.get('subtitle') || '',
    cta_text: fd.get('cta_text') || '',
    cta_link: fd.get('cta_link') || '',
    highlights
  };
  await saveCmsSection('iot_showcase', data, 'IoT Showcase saved successfully!');
}

function renderCmsLanguagesTab(languages) {
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Global Languages Hub (${languages.length})</h3>
          <p>Manage international language programs (Korean EPS-TOPIK, Japanese NAT/JLPT, English IELTS).</p>
        </div>
        <div>
          <button class="primary" onclick="cmsLanguageModal()">+ Add Language Track</button>
        </div>
      </div>

      <div class="cms-list-grid">
        ${languages.map(l => `
          <div class="cms-item-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
              <span class="badge" style="font-size:12px;font-weight:700;background:rgba(124,58,237,0.15);color:#7c3aed;">
                ${esc(l.code || 'LANG')} • ${esc(l.badge || '')}
              </span>
              <span style="font-size:12px;color:var(--text-muted);">⏱ ${esc(l.duration || '')}</span>
            </div>
            <h4>${esc(l.name || l.title)}</h4>
            <div style="font-size:12px;color:var(--brand);margin-bottom:6px;">🎯 Target: <b>${esc(l.target_exam || '')}</b></div>
            <p style="font-size:13px;color:var(--text-muted);margin:6px 0 10px;line-height:1.5;">${esc(l.description || '')}</p>
            ${l.features && l.features.length ? `
              <div style="margin:8px 0;padding-left:14px;">
                <ul style="margin:0;padding-left:12px;font-size:12px;color:var(--text-muted);">
                  ${l.features.map(f => `<li>${esc(f)}</li>`).join('')}
                </ul>
              </div>
            ` : ''}
            <div class="cms-item-actions">
              <button class="small" onclick="cmsLanguageModal(${l.id})">Edit Language</button>
              <button class="small danger" onclick="deleteCmsLanguage(${l.id})">Delete</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function cmsLanguageModal(langId = null) {
  const languages = window._cmsData?.languages || [];
  const existing = langId ? languages.find(l => l.id === langId) : null;
  const featuresText = (existing?.features || []).join('\n');

  const host = modal(existing ? `Edit Language Track: ${existing.name}` : 'Add New Language Track', `
    <form class="form two-col" id="cmsLanguageForm">
      <label>
        <span>Program Name *</span>
        <input name="name" required value="${esc(existing?.name || '')}" placeholder="e.g. Korean Language (EPS-TOPIK)">
      </label>
      <label>
        <span>Language Code (2-3 letters) *</span>
        <input name="code" required value="${esc(existing?.code || 'KR')}" placeholder="e.g. KR, JP, EN">
      </label>
      <label>
        <span>Badge / Exam Accredit</span>
        <input name="badge" value="${esc(existing?.badge || '')}" placeholder="e.g. HRD Korea EPS, JLPT N5-N3">
      </label>
      <label>
        <span>Target Examination *</span>
        <input name="target_exam" required value="${esc(existing?.target_exam || '')}" placeholder="e.g. EPS-TOPIK Manufacturing & Agriculture">
      </label>
      <label class="span-2">
        <span>Course Duration</span>
        <input name="duration" value="${esc(existing?.duration || '4 - 6 Months')}" placeholder="e.g. 4 - 6 Months">
      </label>
      <label class="span-2">
        <span>Course Description *</span>
        <textarea name="description" rows="3" required>${esc(existing?.description || '')}</textarea>
      </label>
      <label class="span-2">
        <span>Key Features (One feature per line)</span>
        <textarea name="features" rows="4" placeholder="Daily CBT practice\nNative audio listening labs\nInterview guidance">${esc(featuresText)}</textarea>
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">${existing ? 'Save Changes' : 'Create Language Track'}</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const features = (fd.get('features') || '').split('\n').map(f => f.trim()).filter(Boolean);
    const updatedLanguages = [...(window._cmsData?.languages || [])];
    if (existing) {
      const idx = updatedLanguages.findIndex(l => l.id === langId);
      if (idx !== -1) {
        updatedLanguages[idx] = {
          ...updatedLanguages[idx],
          name: fd.get('name'),
          code: fd.get('code'),
          badge: fd.get('badge'),
          target_exam: fd.get('target_exam'),
          duration: fd.get('duration'),
          description: fd.get('description'),
          features
        };
      }
    } else {
      const newId = Math.max(0, ...updatedLanguages.map(l => l.id || 0)) + 1;
      updatedLanguages.push({
        id: newId,
        name: fd.get('name'),
        code: fd.get('code'),
        badge: fd.get('badge'),
        target_exam: fd.get('target_exam'),
        duration: fd.get('duration'),
        description: fd.get('description'),
        features
      });
    }
    host.remove();
    await saveCmsSection('languages', updatedLanguages, existing ? 'Language track updated!' : 'New language track added!');
    switchCmsTab('languages');
  };
}

async function deleteCmsLanguage(langId) {
  if (!confirm('Are you sure you want to delete this language program?')) return;
  const updatedLanguages = (window._cmsData?.languages || []).filter(l => l.id !== langId);
  await saveCmsSection('languages', updatedLanguages, 'Language track removed!');
  switchCmsTab('languages');
}

function renderCmsPillarsTab(pillars) {
  const pList = pillars && pillars.length ? pillars : [
    { id: 1, title: 'Concept Mastery', subtitle: 'No Rote Learning', desc: 'We build deep first-principles intuition.', icon: 'brain' },
    { id: 2, title: 'Continuous Evaluation', subtitle: 'Weekly Model Exams', desc: 'Regular mock examinations simulate board conditions.', icon: 'chart' },
    { id: 3, title: 'Hands-on Mentorship', subtitle: 'Robotics & IoT Lab', desc: 'Students gain practical engineering skills.', icon: 'cpu' },
    { id: 4, title: 'Global Pathways', subtitle: 'Language & Career Hub', desc: 'Specialized Korean, Japanese, and English training.', icon: 'globe' }
  ];

  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>4 Educational Methodology Pillars</h3>
          <p>Define the core institutional advantages and philosophies highlighted in the "Why Choose ELH" section.</p>
        </div>
      </div>
      <form id="cmsPillarsForm" onsubmit="event.preventDefault(); saveCmsPillars(this);">
        <div class="cms-grid-2">
          ${pList.map((p, i) => `
            <div style="padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);">
              <span style="font-weight:700;font-size:12px;color:var(--brand);text-transform:uppercase;">Pillar ${i + 1}</span>
              <div class="cms-grid-2" style="margin-top:8px;">
                <label>
                  <span style="font-size:12px;color:var(--text-muted);">Pillar Title</span>
                  <input type="text" name="pillar_title_${i}" value="${esc(p.title || '')}" required>
                </label>
                <label>
                  <span style="font-size:12px;color:var(--text-muted);">Subtitle / Tag</span>
                  <input type="text" name="pillar_subtitle_${i}" value="${esc(p.subtitle || '')}" required>
                </label>
                <label class="span-2">
                  <span style="font-size:12px;color:var(--text-muted);">Icon Symbol</span>
                  <select name="pillar_icon_${i}">
                    <option value="brain" ${p.icon === 'brain' ? 'selected' : ''}>🧠 Brain (Concept Mastery)</option>
                    <option value="chart" ${p.icon === 'chart' ? 'selected' : ''}>📊 Chart (Continuous Evaluation)</option>
                    <option value="cpu" ${p.icon === 'cpu' ? 'selected' : ''}>🤖 CPU / Tech (Hands-on Mentorship)</option>
                    <option value="globe" ${p.icon === 'globe' ? 'selected' : ''}>🌐 Globe (Global Pathways)</option>
                  </select>
                </label>
                <label class="span-2">
                  <span style="font-size:12px;color:var(--text-muted);">Narrative Description</span>
                  <textarea name="pillar_desc_${i}" rows="2" required>${esc(p.desc || '')}</textarea>
                </label>
              </div>
            </div>
          `).join('')}
        </div>

        <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
          <button type="submit" class="primary">💾 Save 4 Pillars</button>
        </div>
      </form>
    </div>
  `;
}

async function saveCmsPillars(form) {
  const fd = new FormData(form);
  const pillars = [];
  for (let i = 0; i < 4; i++) {
    pillars.push({
      id: i + 1,
      title: fd.get(`pillar_title_${i}`) || '',
      subtitle: fd.get(`pillar_subtitle_${i}`) || '',
      desc: fd.get(`pillar_desc_${i}`) || '',
      icon: fd.get(`pillar_icon_${i}`) || 'brain'
    });
  }
  await saveCmsSection('pillars', pillars, '4 Methodology Pillars saved successfully!');
}

function renderCmsEventsTab(events) {
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Events, Workshops & Seminars (${events.length})</h3>
          <p>Publish upcoming webinars, hackathons, academic seminars, and career workshops.</p>
        </div>
        <div>
          <button class="primary" onclick="cmsEventModal()">+ Add Event / Workshop</button>
        </div>
      </div>

      <div class="cms-list-grid">
        ${events.map(ev => `
          <div class="cms-item-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
              <span class="badge" style="font-size:11px;background:rgba(56,189,248,0.15);color:var(--brand);">${esc(ev.category)}</span>
              <span class="badge active" style="font-size:11px;">${esc(ev.status || 'Upcoming')}</span>
            </div>
            <h4>${esc(ev.title)}</h4>
            <div style="font-size:12px;color:var(--text-strong);margin:6px 0;">
              📅 <b>${esc(ev.date)}</b> • 📍 <b>${esc(ev.venue || 'ELH Campus')}</b>
            </div>
            <p style="font-size:13px;color:var(--text-muted);margin:6px 0 12px;line-height:1.5;">${esc(ev.desc || '')}</p>
            <div class="cms-item-actions">
              <button class="small" onclick="cmsEventModal(${ev.id})">Edit Event</button>
              <button class="small danger" onclick="deleteCmsEvent(${ev.id})">Delete</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function cmsEventModal(eventId = null) {
  const events = window._cmsData?.events || [];
  const existing = eventId ? events.find(ev => ev.id === eventId) : null;

  const host = modal(existing ? `Edit Event: ${existing.title}` : 'Add New Event / Workshop', `
    <form class="form two-col" id="cmsEventForm">
      <label class="span-2">
        <span>Event Title *</span>
        <input name="title" required value="${esc(existing?.title || '')}" placeholder="e.g. Hands-on IoT Prototype Hackathon">
      </label>
      <label>
        <span>Category Track *</span>
        <select name="category">
          <option ${existing?.category === 'Workshop' ? 'selected' : ''}>Workshop</option>
          <option ${existing?.category === 'Seminar' ? 'selected' : ''}>Seminar</option>
          <option ${existing?.category === 'Webinar' ? 'selected' : ''}>Webinar</option>
          <option ${existing?.category === 'Field Tour' ? 'selected' : ''}>Field Tour</option>
          <option ${existing?.category === 'Conference' ? 'selected' : ''}>Conference</option>
        </select>
      </label>
      <label>
        <span>Event Status *</span>
        <select name="status">
          <option ${existing?.status === 'Upcoming' ? 'selected' : ''}>Upcoming</option>
          <option ${existing?.status === 'Registration Open' ? 'selected' : ''}>Registration Open</option>
          <option ${existing?.status === 'Scheduled' ? 'selected' : ''}>Scheduled</option>
          <option ${existing?.status === 'Completed' ? 'selected' : ''}>Completed</option>
        </select>
      </label>
      <label>
        <span>Date / Schedule *</span>
        <input name="date" required value="${esc(existing?.date || '')}" placeholder="e.g. Every Alternate Saturday, or 2083/06/15">
      </label>
      <label>
        <span>Venue / Location *</span>
        <input name="venue" required value="${esc(existing?.venue || 'ELH Main Campus, Pathari')}" placeholder="e.g. ELH Tech Lab, Pathari">
      </label>
      <label class="span-2">
        <span>Description *</span>
        <textarea name="desc" rows="3" required>${esc(existing?.desc || '')}</textarea>
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">${existing ? 'Save Changes' : 'Publish Event'}</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const updatedEvents = [...(window._cmsData?.events || [])];
    if (existing) {
      const idx = updatedEvents.findIndex(ev => ev.id === eventId);
      if (idx !== -1) {
        updatedEvents[idx] = {
          ...updatedEvents[idx],
          title: fd.get('title'),
          category: fd.get('category'),
          status: fd.get('status'),
          date: fd.get('date'),
          venue: fd.get('venue'),
          desc: fd.get('desc')
        };
      }
    } else {
      const newId = Math.max(0, ...updatedEvents.map(e => e.id || 0)) + 1;
      updatedEvents.unshift({
        id: newId,
        title: fd.get('title'),
        category: fd.get('category'),
        status: fd.get('status'),
        date: fd.get('date'),
        venue: fd.get('venue'),
        desc: fd.get('desc')
      });
    }
    host.remove();
    await saveCmsSection('events', updatedEvents, existing ? 'Event updated!' : 'New event published!');
    switchCmsTab('events');
  };
}

async function deleteCmsEvent(eventId) {
  if (!confirm('Are you sure you want to delete this event?')) return;
  const updatedEvents = (window._cmsData?.events || []).filter(ev => ev.id !== eventId);
  await saveCmsSection('events', updatedEvents, 'Event removed from website!');
  switchCmsTab('events');
}

function renderCmsTestimonialsTab(testimonials) {
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Student Testimonials & Reviews (${testimonials.length})</h3>
          <p>Showcase real success stories, board exam scores, and student experiences.</p>
        </div>
        <div>
          <button class="primary" onclick="cmsTestimonialModal()">+ Add Testimonial</button>
        </div>
      </div>

      <div class="cms-list-grid">
        ${testimonials.map(t => `
          <div class="cms-item-card">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
              <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#465fff,#7c3aed);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;">
                ${esc(t.avatar || (t.student_name || 'EL').slice(0, 2).toUpperCase())}
              </div>
              <div>
                <h4 style="margin:0;font-size:14px;">${esc(t.student_name)}</h4>
                <small class="muted">${esc(t.course || '')}</small>
              </div>
            </div>
            <div style="margin-bottom:8px;">
              <span class="badge active" style="font-size:11px;">🏆 ${esc(t.achievement || 'Achiever')}</span>
            </div>
            <p style="font-size:13px;color:var(--text-muted);font-style:italic;line-height:1.5;margin:0 0 12px;">
              "${esc(t.quote)}"
            </p>
            <div class="cms-item-actions">
              <button class="small" onclick="cmsTestimonialModal(${t.id})">Edit Review</button>
              <button class="small danger" onclick="deleteCmsTestimonial(${t.id})">Delete</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function cmsTestimonialModal(testId = null) {
  const testimonials = window._cmsData?.testimonials || [];
  const existing = testId ? testimonials.find(t => t.id === testId) : null;

  const host = modal(existing ? `Edit Testimonial: ${existing.student_name}` : 'Add Student Testimonial', `
    <form class="form two-col" id="cmsTestimonialForm">
      <label>
        <span>Student / Alumni Name *</span>
        <input name="student_name" required value="${esc(existing?.student_name || '')}" placeholder="e.g. Aayush Khatiwada">
      </label>
      <label>
        <span>Course / Cohort *</span>
        <input name="course" required value="${esc(existing?.course || '')}" placeholder="e.g. SEE Master Class (Grade 10)">
      </label>
      <label>
        <span>Achievement / Score *</span>
        <input name="achievement" required value="${esc(existing?.achievement || '')}" placeholder="e.g. GPA 3.95 (A+) or EPS 190/200">
      </label>
      <label>
        <span>Avatar Initials (2 letters)</span>
        <input name="avatar" maxlength="3" value="${esc(existing?.avatar || '')}" placeholder="e.g. AK">
      </label>
      <label class="span-2">
        <span>Student Quote / Review *</span>
        <textarea name="quote" rows="4" required placeholder="Describe their experience and how ELH helped them...">${esc(existing?.quote || '')}</textarea>
      </label>
      <div class="form-actions span-2">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">${existing ? 'Save Changes' : 'Add Testimonial'}</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const updatedTestimonials = [...(window._cmsData?.testimonials || [])];
    if (existing) {
      const idx = updatedTestimonials.findIndex(t => t.id === testId);
      if (idx !== -1) {
        updatedTestimonials[idx] = {
          ...updatedTestimonials[idx],
          student_name: fd.get('student_name'),
          course: fd.get('course'),
          achievement: fd.get('achievement'),
          avatar: (fd.get('avatar') || fd.get('student_name').slice(0, 2)).toUpperCase(),
          quote: fd.get('quote')
        };
      }
    } else {
      const newId = Math.max(0, ...updatedTestimonials.map(t => t.id || 0)) + 1;
      updatedTestimonials.push({
        id: newId,
        student_name: fd.get('student_name'),
        course: fd.get('course'),
        achievement: fd.get('achievement'),
        avatar: (fd.get('avatar') || fd.get('student_name').slice(0, 2)).toUpperCase(),
        quote: fd.get('quote')
      });
    }
    host.remove();
    await saveCmsSection('testimonials', updatedTestimonials, existing ? 'Testimonial updated!' : 'New testimonial added!');
    switchCmsTab('testimonials');
  };
}

async function deleteCmsTestimonial(testId) {
  if (!confirm('Are you sure you want to delete this testimonial?')) return;
  const updatedTestimonials = (window._cmsData?.testimonials || []).filter(t => t.id !== testId);
  await saveCmsSection('testimonials', updatedTestimonials, 'Testimonial removed!');
  switchCmsTab('testimonials');
}

function renderCmsFaqsTab(faqs) {
  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Frequently Asked Questions (${faqs.length})</h3>
          <p>Manage common inquiries regarding admissions, scholarships, schedules, and device labs.</p>
        </div>
        <div>
          <button class="primary" onclick="cmsFaqModal()">+ Add New FAQ</button>
        </div>
      </div>

      <div class="cms-list-grid">
        ${faqs.map(f => `
          <div class="cms-item-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span class="badge" style="font-size:11px;background:rgba(56,189,248,0.15);color:var(--brand);">${esc(f.category || 'General')}</span>
            </div>
            <h4>${esc(f.question)}</h4>
            <p style="font-size:13px;color:var(--text-muted);margin:6px 0 12px;line-height:1.5;">${esc(f.answer)}</p>
            <div class="cms-item-actions">
              <button class="small" onclick="cmsFaqModal(${f.id})">Edit FAQ</button>
              <button class="small danger" onclick="deleteCmsFaq(${f.id})">Delete</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function cmsFaqModal(faqId = null) {
  const faqs = window._cmsData?.faqs || [];
  const existing = faqId ? faqs.find(f => f.id === faqId) : null;

  const host = modal(existing ? 'Edit FAQ' : 'Add New FAQ', `
    <form class="form" id="cmsFaqForm">
      <label>
        <span>Category Track *</span>
        <select name="category">
          <option ${existing?.category === 'Admissions' ? 'selected' : ''}>Admissions</option>
          <option ${existing?.category === 'Academics & SEE' ? 'selected' : ''}>Academics & SEE</option>
          <option ${existing?.category === 'Tech & Robotics' ? 'selected' : ''}>Tech & Robotics</option>
          <option ${existing?.category === 'Languages' ? 'selected' : ''}>Languages</option>
          <option ${existing?.category === 'Fees & Schedule' ? 'selected' : ''}>Fees & Schedule</option>
          <option ${existing?.category === 'General' ? 'selected' : ''}>General</option>
        </select>
      </label>
      <label>
        <span>Question *</span>
        <input name="question" required value="${esc(existing?.question || '')}" placeholder="e.g. What is the admission procedure for Grade 10?">
      </label>
      <label>
        <span>Answer *</span>
        <textarea name="answer" rows="4" required placeholder="Detailed response for prospective students...">${esc(existing?.answer || '')}</textarea>
      </label>
      <div class="form-actions">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">${existing ? 'Save Changes' : 'Add FAQ'}</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const updatedFaqs = [...(window._cmsData?.faqs || [])];
    if (existing) {
      const idx = updatedFaqs.findIndex(f => f.id === faqId);
      if (idx !== -1) {
        updatedFaqs[idx] = {
          ...updatedFaqs[idx],
          category: fd.get('category'),
          question: fd.get('question'),
          answer: fd.get('answer')
        };
      }
    } else {
      const newId = Math.max(0, ...updatedFaqs.map(f => f.id || 0)) + 1;
      updatedFaqs.push({
        id: newId,
        category: fd.get('category'),
        question: fd.get('question'),
        answer: fd.get('answer')
      });
    }
    host.remove();
    await saveCmsSection('faqs', updatedFaqs, existing ? 'FAQ updated!' : 'New FAQ added!');
    switchCmsTab('faqs');
  };
}

async function deleteCmsFaq(faqId) {
  if (!confirm('Are you sure you want to delete this FAQ?')) return;
  const updatedFaqs = (window._cmsData?.faqs || []).filter(f => f.id !== faqId);
  await saveCmsSection('faqs', updatedFaqs, 'FAQ removed!');
  switchCmsTab('faqs');
}

async function renderCmsInquiriesTab() {
  const currentFilter = window._cmsInquiryFilter || 'all';
  const searchQuery = window._cmsInquirySearch || '';
  let url = '/cms/inquiries';
  const params = [];
  if (currentFilter !== 'all') params.push(`status=${encodeURIComponent(currentFilter)}`);
  if (searchQuery) params.push(`search=${encodeURIComponent(searchQuery)}`);
  if (params.length) url += `?${params.join('&')}`;

  let inquiries = [];
  try {
    inquiries = await api(url);
    window._cmsInquiriesList = inquiries;
  } catch (err) {
    inquiries = [];
  }

  const statuses = ['all', 'New', 'Contacted', 'Counseling Scheduled', 'Enrolled', 'Closed'];

  const rows = inquiries.map(inq => {
    const statusColor = {
      'New': '#38bdf8',
      'Contacted': '#f59e0b',
      'Counseling Scheduled': '#a855f7',
      'Enrolled': '#10b981',
      'Closed': '#64748b'
    }[inq.status] || '#94a3b8';

    return `
      <tr>
        <td style="font-size:12px;color:var(--text-muted);white-space:nowrap;">${esc(inq.created_at || '').split('T')[0]}</td>
        <td>
          <strong style="font-size:14px;color:var(--text-strong);">${esc(inq.full_name)}</strong>
          <div style="font-size:12px;color:var(--text-muted);">${esc(inq.grade_level || 'General')}</div>
        </td>
        <td>
          <div>📞 <a href="tel:${esc(inq.phone)}" style="color:var(--brand);">${esc(inq.phone)}</a></div>
          ${inq.email ? `<div style="font-size:12px;color:var(--text-muted);">✉️ ${esc(inq.email)}</div>` : ''}
        </td>
        <td><span class="badge" style="background:rgba(56,189,248,0.12);color:var(--brand);">${esc(inq.course_name || 'General')}</span></td>
        <td><span class="badge" style="background:${statusColor}22;color:${statusColor};font-weight:700;">${esc(inq.status)}</span></td>
        <td style="max-width:200px;font-size:12px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(inq.staff_notes || inq.message || '')}">
          ${esc(inq.staff_notes || inq.message || '-')}
        </td>
        <td>
          <div style="display:flex;gap:6px;">
            <button class="small" onclick="cmsInquiryStatusModal(${inq.id})">Review & Note</button>
            <button class="small danger" onclick="deleteCmsInquiry(${inq.id})">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  return `
    <div class="cms-section-card">
      <div class="cms-section-header">
        <div>
          <h3>Online Admission Inquiries & Leads</h3>
          <p>Prospective student inquiries submitted through the website form. Track counseling progress and notes.</p>
        </div>
        <div>
          <span class="badge active" style="font-size:13px;padding:6px 12px;">Total Leads: ${inquiries.length}</span>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap;">
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${statuses.map(s => `
            <button class="${currentFilter === s ? 'primary' : ''} small" onclick="filterCmsInquiries('${s}')">
              ${esc(s === 'all' ? 'All Leads' : s)}
            </button>
          `).join('')}
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="text" id="cmsInquirySearchInput" placeholder="Search leads by name, phone..." value="${esc(searchQuery)}" onkeyup="if(event.key==='Enter')searchCmsInquiries(this.value)" style="width:220px;padding:6px 10px;font-size:13px;">
          <button class="small" onclick="searchCmsInquiries(document.getElementById('cmsInquirySearchInput').value)">Search</button>
        </div>
      </div>

      ${inquiries.length ? `
        <div class="table-container" style="overflow-x:auto;">
          <table class="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Applicant</th>
                <th>Contact</th>
                <th>Program</th>
                <th>Status</th>
                <th>Follow-up Notes</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      ` : `
        <div style="padding:40px;text-align:center;color:var(--text-muted);">
          <p style="font-size:16px;margin:0 0 8px;">No admission inquiries found</p>
          <small>New submissions via the website inquiry form will appear here automatically.</small>
        </div>
      `}
    </div>
  `;
}

function filterCmsInquiries(status) {
  window._cmsInquiryFilter = status;
  switchCmsTab('inquiries');
}

function searchCmsInquiries(query) {
  window._cmsInquirySearch = query.trim();
  switchCmsTab('inquiries');
}

function cmsInquiryStatusModal(inquiryId) {
  const inq = (window._cmsInquiriesList || []).find(i => i.id === inquiryId);
  if (!inq) return;

  const statuses = ['New', 'Contacted', 'Counseling Scheduled', 'Enrolled', 'Closed'];

  const host = modal(`Inquiry Follow-up: ${inq.full_name}`, `
    <form class="form" id="cmsInquiryModalForm">
      <div style="padding:12px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
          <b>${esc(inq.full_name)}</b>
          <span class="muted">${esc(inq.phone)}</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted);">Program: <b>${esc(inq.course_name || 'General')}</b> • Level: ${esc(inq.grade_level || 'N/A')}</div>
        ${inq.message ? `<p style="font-size:12px;margin:8px 0 0;padding:6px 8px;background:var(--bg-body);border-radius:6px;font-style:italic;">"${esc(inq.message)}"</p>` : ''}
      </div>
      <label>
        <span>Status *</span>
        <select name="status">
          ${statuses.map(s => `
            <option value="${s}" ${inq.status === s ? 'selected' : ''}>${s}</option>
          `).join('')}
        </select>
      </label>
      <label>
        <span>Staff Follow-up Notes</span>
        <textarea name="staff_notes" rows="4" placeholder="e.g. Called on 2083/05/12. Student is interested in Morning SEE batch. Fee discussed.">${esc(inq.staff_notes || '')}</textarea>
      </label>
      <div class="form-actions">
        <button type="button" onclick="this.closest('.modal').remove()">Cancel</button>
        <button type="submit" class="primary">Update Status & Notes</button>
      </div>
    </form>
  `);

  host.querySelector('form').onsubmit = async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    try {
      await api(`/cms/inquiries/${inquiryId}`, {
        method: 'PUT',
        body: JSON.stringify({
          status: fd.get('status'),
          staff_notes: fd.get('staff_notes')
        })
      });
      host.remove();
      showCmsToast('Admission inquiry updated!');
      switchCmsTab('inquiries');
    } catch (err) {
      showError(err);
    }
  };
}

async function deleteCmsInquiry(inquiryId) {
  if (!confirm('Are you sure you want to delete this admission inquiry?')) return;
  try {
    await api(`/cms/inquiries/${inquiryId}`, { method: 'DELETE' });
    showCmsToast('Admission inquiry deleted!');
    switchCmsTab('inquiries');
  } catch (err) {
    showError(err);
  }
}

async function renderPublicWebsite(initialSection = '') {
  const isLoggedIn = !!token && !!me;
  await loadWebsiteCmsData();

  const cmsData = window._websiteCmsData || {};
  const hero = cmsData.hero || {};
  const gen = cmsData.general || {};
  const stats = cmsData.stats || {};
  const iot = cmsData.iot_showcase || {};
  const languages = cmsData.languages || [];
  const pillars = cmsData.pillars || [];
  const events = cmsData.events || [];
  const testimonials = cmsData.testimonials || [];
  const faqs = cmsData.faqs || [];

  const rawCourses = cmsData.courses || webCourseData;
  const courseOptionsHtml = rawCourses.map(c => `<option value="${esc(c.title)}">${esc(c.title)}</option>`).join('');

  const html = `
    <div class="elh-website">
      <!-- Top Announcement Strip -->
      <div class="elh-topbar">
        <div class="elh-topbar-inner">
          <div class="elh-topbar-links">
            <span>📍 ${esc(gen.address || 'Expert Tower, Shikar Chowk, Pathari-1, Morang, Nepal')}</span>
            <a href="tel:${esc(gen.phone || '+9779800924090')}">📞 ${esc(gen.phone || '+977 9800924090')}</a>
            <a href="mailto:${esc(gen.email || 'info@expertlearninghub.edu.np')}">✉️ ${esc(gen.email || 'info@expertlearninghub.edu.np')}</a>
          </div>
          <div class="elh-topbar-links">
            ${hero.announcement_active !== false ? `
              <span style="color:#fde047;font-weight:700;">✦ ${esc(hero.announcement_text || 'Admissions Open 2024–25')}</span>
            ` : ''}
            <a href="javascript:void(0)" onclick="openPortalLoginModal('student')">Student Portal</a>
            <a href="javascript:void(0)" onclick="openPortalLoginModal('teacher')">Staff Portal</a>
            ${has('cms.manage') ? `
              <a href="javascript:void(0)" onclick="go('cms')" style="color:#38bdf8;font-weight:700;">⚙️ Website CMS</a>
            ` : ''}
            <button class="theme-toggle-btn" onclick="toggleDarkMode()" aria-label="Toggle theme" style="width:24px;height:24px;padding:2px;background:none;border:none;color:#cbd5e1;cursor:pointer;">
              ${isDarkMode ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
      </div>

      <!-- Glassmorphic Sticky Header -->
      <header class="elh-nav">
        <div class="elh-nav-inner">
          <a class="elh-logo-link" href="#home">
            <div class="elh-logo-badge">E</div>
            <div class="elh-logo-text">
              <b>${esc(gen.name || 'EXPERT')}</b>
              <span>${esc(gen.tagline ? gen.tagline.split('Through')[0].trim() : 'Learning Hub')}</span>
            </div>
          </a>

          <ul class="elh-nav-menu">
            <li class="elh-nav-item"><a href="#home">Home</a></li>
            <li class="elh-nav-item"><a href="#coursesSection">Courses & Tuition</a></li>
            <li class="elh-nav-item"><a href="#iotSection">IoT Mentorship</a></li>
            <li class="elh-nav-item"><a href="#languagesSection">Global Languages</a></li>
            <li class="elh-nav-item"><a href="#methodologySection">Pillars</a></li>
            <li class="elh-nav-item"><a href="#eventsSection">Events</a></li>
            <li class="elh-nav-item"><a href="#testimonialsSection">Testimonials</a></li>
            <li class="elh-nav-item"><a href="#faqsSection">FAQs</a></li>
            <li class="elh-nav-item"><a href="#contactSection">Contact</a></li>
          </ul>

          <div class="elh-nav-cta">
            ${isLoggedIn ? `
              <button class="elh-btn-portal" onclick="go('dashboard')" style="background:var(--brand-light);color:var(--brand);border-color:var(--brand);">
                👋 Dashboard (${esc(me?.display_name || me?.username || 'User')}) →
              </button>
            ` : `
              <button class="elh-btn-portal" onclick="openPortalLoginModal()">
                ${uiIcon('lock', 14)} Portal Sign In
              </button>
              <a href="#contactSection" class="elh-btn-primary">
                Inquire Now
              </a>
            `}
            <button class="elh-mobile-toggle" onclick="toggleMobileNav(this)" aria-label="Menu">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            </button>
          </div>
        </div>
      </header>

      <!-- HERO SECTION -->
      <section class="elh-hero" id="home">
        <div class="elh-hero-glow"></div>
        <div class="elh-hero-content">
          <div class="elh-pill-badge">
            <span class="elh-pulse-dot"></span>
            <span>${esc(hero.badge || 'Leading Coaching & Tech Mentorship in Morang')}</span>
          </div>

          <h1>
            ${esc(hero.title || 'Empowering Future Leaders & Tech Innovators')}
          </h1>

          <p>
            ${esc(hero.subtitle || 'Expert Learning Hub bridges traditional secondary education with modern robotics, IoT engineering, and global career pathways. From SEE toppers to international scholars, your journey starts here.')}
          </p>

          <div class="elh-hero-actions">
            <a href="${esc(hero.cta_primary_link || '#coursesSection')}" class="elh-btn-primary" style="font-size:15px;padding:12px 26px;">
              ${esc(hero.cta_primary_text || 'Explore Courses')} ${uiIcon('arrowRight', 16)}
            </a>
            ${isLoggedIn ? `
              <button class="elh-btn-portal" onclick="go('dashboard')" style="font-size:15px;padding:12px 22px;">
                Open My Dashboard →
              </button>
            ` : `
              <button class="elh-btn-portal" onclick="openPortalLoginModal()" style="font-size:15px;padding:12px 22px;">
                ${uiIcon('lock', 16)} Portal Login
              </button>
            `}
            <a href="${esc(hero.cta_secondary_link || '#iotSection')}" class="btn" style="font-size:15px;padding:12px 20px;border-radius:var(--radius-md);">
              ${esc(hero.cta_secondary_text || 'IoT Mentorship')}
            </a>
          </div>

          <!-- Counter Stats Grid -->
          <div class="elh-stats-grid">
            <div class="elh-stat-box">
              <div class="elh-stat-num">${esc(stats.students_count || '500+')}</div>
              <div class="elh-stat-label">${esc(stats.students_label || 'Enrolled Students')}</div>
              <div class="elh-stat-sub">Across Basic, SEE & +2</div>
            </div>
            <div class="elh-stat-box">
              <div class="elh-stat-num">${esc(stats.success_rate || '98.6%')}</div>
              <div class="elh-stat-label">${esc(stats.success_label || 'Board Success Rate')}</div>
              <div class="elh-stat-sub">Distinction & Top Ranks</div>
            </div>
            <div class="elh-stat-box">
              <div class="elh-stat-num">${esc(stats.teachers_count || '14+')}</div>
              <div class="elh-stat-label">${esc(stats.teachers_label || 'Expert Educators')}</div>
              <div class="elh-stat-sub">Dedicated subject specialists</div>
            </div>
            <div class="elh-stat-box">
              <div class="elh-stat-num">${esc(stats.projects_count || '25+')}</div>
              <div class="elh-stat-label">${esc(stats.projects_label || 'IoT & Tech Capstones')}</div>
              <div class="elh-stat-sub">Practical engineering kits</div>
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 2: Specialized Learning Pathways (Courses) -->
      <section class="elh-section" id="coursesSection">
        <div class="elh-section-header">
          <span class="elh-section-badge">Academic Excellence</span>
          <h2 class="elh-section-title">Specialized Learning Pathways</h2>
          <p class="elh-section-sub">
            From foundation school tuition to competitive board examination coaching and career programs, explore our structured curriculums designed for mastery.
          </p>
        </div>

        <div class="elh-filter-bar">
          <button class="elh-filter-btn active" data-category="all" onclick="filterWebCourses('all')">All Pathways</button>
          <button class="elh-filter-btn" data-category="school" onclick="filterWebCourses('school')">Secondary (Grades 8-10)</button>
          <button class="elh-filter-btn" data-category="plus2" onclick="filterWebCourses('plus2')">+2 Science & Commerce</button>
          <button class="elh-filter-btn" data-category="tech" onclick="filterWebCourses('tech')">Tech & IoT Prototyping</button>
          <button class="elh-filter-btn" data-category="language" onclick="filterWebCourses('language')">Global Languages</button>
        </div>

        <div class="elh-course-grid" id="webCourseGridContainer">
          <!-- Populated by filterWebCourses() -->
        </div>
      </section>

      <!-- SECTION 3: Tech & IoT Mastery (Showcase) -->
      <section class="elh-section" id="iotSection" style="padding-top:20px;">
        <div class="elh-iot-showcase">
          <div class="elh-iot-glow"></div>
          <div class="elh-iot-content">
            <div class="elh-iot-badge">⚡ ${esc(iot.badge || 'Future-Proof Technology')}</div>
            <h2 class="elh-iot-title">${esc(iot.title || 'Hardware, Embedded Firmware & Cloud Telemetry')}</h2>
            <p class="elh-iot-desc">
              ${esc(iot.subtitle || 'Join our cutting-edge mentorship program. Build real-world connected hardware, interface microcontrollers (ESP32 / Arduino / Raspberry Pi), connect live sensor telemetry to the cloud, and build autonomous smart automation systems under direct mentor guidance.')}
            </p>
            <div class="elh-iot-features">
              ${(iot.highlights || [
                { title: 'ESP32 & Microcontrollers', desc: 'Hardware kits & sensors provided' },
                { title: 'Cloud Telemetry & MQTT', desc: 'Live mobile & web dashboarding' },
                { title: 'Robotics & Automation', desc: 'Practical smart prototypes built in lab' },
                { title: 'Mentorship Capstones', desc: 'Portfolio review & competition prep' }
              ]).map(h => `
                <div class="elh-iot-feat">
                  <span>✓</span>
                  <div><b>${esc(h.title)}:</b> ${esc(h.desc)}</div>
                </div>
              `).join('')}
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;">
              <button class="elh-btn-primary" onclick="prefillInquiryCourse('Tech & IoT Engineering Mentorship')">
                ${esc(iot.cta_text || 'Enroll in IoT Program')} →
              </button>
              <a href="#contactSection" class="btn" style="background:rgba(255,255,255,0.1);color:#ffffff;border-color:rgba(255,255,255,0.2);padding:9px 18px;border-radius:var(--radius-md);">
                Visit Prototyping Lab
              </a>
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 4: Global Gateway (Languages) -->
      <section class="elh-section" id="languagesSection">
        <div class="elh-section-header">
          <span class="elh-section-badge">International Gateway</span>
          <h2 class="elh-section-title">Global Linguistic Mastery</h2>
          <p class="elh-section-sub">
            Your bridge to international opportunities through linguistic excellence, structured exam certifications, and cultural orientation.
          </p>
        </div>

        <div class="elh-lang-grid">
          ${languages.map(l => `
            <div class="elh-lang-card" onclick="prefillInquiryCourse('${esc(l.name)}')">
              <div class="elh-lang-flag">${l.code === 'KR' ? '🇰🇷' : l.code === 'JP' ? '🇯🇵' : '🇬🇧'}</div>
              <div class="elh-lang-info">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <h3 style="margin:0;">${esc(l.name)}</h3>
                  <span class="badge active" style="font-size:11px;">${esc(l.badge || '')}</span>
                </div>
                <p style="margin:8px 0;">${esc(l.description)}</p>
                <small class="muted">Target: <b>${esc(l.target_exam || '')}</b> • Duration: ${esc(l.duration || '')}</small>
              </div>
            </div>
          `).join('')}
        </div>
      </section>

      <!-- SECTION 5: Why Choose ELH (Pillars) -->
      <section class="elh-section" id="methodologySection">
        <div class="elh-section-header">
          <span class="elh-section-badge">The ELH Advantage</span>
          <h2 class="elh-section-title">Why Students & Parents Trust ELH</h2>
          <p class="elh-section-sub">
            We combine high-caliber educators, modern digital management, and continuous personalized feedback to deliver unmatched learning outcomes.
          </p>
        </div>

        <div class="elh-pillars-grid">
          ${pillars.map(p => `
            <div class="elh-pillar-card">
              <div class="elh-pillar-icon">${p.icon === 'brain' ? '🧠' : p.icon === 'chart' ? '📊' : p.icon === 'cpu' ? '🤖' : '🌐'}</div>
              <h3>${esc(p.title)}</h3>
              <b style="color:var(--brand);font-size:13px;display:block;margin-bottom:6px;">${esc(p.subtitle)}</b>
              <p>${esc(p.desc)}</p>
            </div>
          `).join('')}
        </div>
      </section>

      <!-- SECTION 6: Events, Seminars & Workshops -->
      <section class="elh-section" id="eventsSection">
        <div class="elh-section-header">
          <span class="elh-section-badge">Events & Exposure</span>
          <h2 class="elh-section-title">Upcoming Workshops & Seminars</h2>
          <p class="elh-section-sub">
            Expanding horizons beyond textbooks with practical seminars, global webinars, and interactive workshops.
          </p>
        </div>

        <div class="elh-events-grid">
          ${events.map(ev => `
            <div class="elh-event-card">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span class="elh-event-type">${esc(ev.category)}</span>
                <span class="badge" style="font-size:11px;font-weight:700;">${esc(ev.status || 'Upcoming')}</span>
              </div>
              <h3 class="elh-event-title">${esc(ev.title)}</h3>
              <div class="elh-event-date">📅 ${esc(ev.date)} • 📍 ${esc(ev.venue || 'ELH Campus')}</div>
              <p class="muted" style="font-size:13px;margin:8px 0 0;">${esc(ev.desc)}</p>
            </div>
          `).join('')}
        </div>
      </section>

      <!-- SECTION 7: Testimonials & Student Reviews -->
      ${testimonials.length ? `
        <section class="elh-section" id="testimonialsSection" style="background:var(--bg-body);padding:60px 20px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);">
          <div class="elh-section-header">
            <span class="elh-section-badge">Student Voices</span>
            <h2 class="elh-section-title">Real Success Stories from ELH Learners</h2>
            <p class="elh-section-sub">Hear from our students and alumni about how Expert Learning Hub accelerated their academic performance and technical skills.</p>
          </div>
          <div class="elh-list-grid" style="max-width:1200px;margin:0 auto;">
            ${testimonials.map(t => `
              <div class="cms-item-card" style="background:var(--bg-card);border:1px solid var(--line);padding:24px;border-radius:18px;">
                <div style="color:#eab308;font-size:16px;margin-bottom:12px;">★★★★★</div>
                <p style="font-size:14px;line-height:1.6;font-style:italic;color:var(--ink-dark);margin:0 0 16px;">"${esc(t.quote)}"</p>
                <div style="display:flex;align-items:center;gap:12px;margin-top:auto;padding-top:12px;border-top:1px solid var(--line);">
                  <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#465fff,#7c3aed);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;">
                    ${esc(t.avatar || t.student_name.slice(0, 2).toUpperCase())}
                  </div>
                  <div>
                    <b style="display:block;font-size:14px;color:var(--ink-dark);">${esc(t.student_name)}</b>
                    <small class="muted">${esc(t.course)} • <span style="color:var(--brand);font-weight:700;">${esc(t.achievement)}</span></small>
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
        </section>
      ` : ''}

      <!-- SECTION 8: Frequently Asked Questions (FAQs) -->
      ${faqs.length ? `
        <section class="elh-section" id="faqsSection">
          <div class="elh-section-header">
            <span class="elh-section-badge">Got Questions?</span>
            <h2 class="elh-section-title">Frequently Asked Questions</h2>
            <p class="elh-section-sub">Clear answers regarding coaching batches, enrollments, fees, and mentoring.</p>
          </div>
          <div style="max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:12px;">
            ${faqs.map(f => `
              <details style="background:var(--bg-card);border:1px solid var(--line);border-radius:14px;padding:16px 20px;cursor:pointer;">
                <summary style="font-weight:700;font-size:15px;color:var(--ink-dark);display:flex;justify-content:space-between;align-items:center;">
                  <span>${esc(f.question)}</span>
                  <span class="badge" style="font-size:11px;">${esc(f.category || 'General')}</span>
                </summary>
                <p style="margin:12px 0 0;font-size:14px;line-height:1.6;color:var(--muted);">${esc(f.answer)}</p>
              </details>
            `).join('')}
          </div>
        </section>
      ` : ''}

      <!-- SECTION 9: Contact & Online Admission Inquiry -->
      <section class="elh-section" id="contactSection">
        <div class="elh-inquiry-box">
          <div class="elh-inquiry-info">
            <div>
              <span class="elh-section-badge">Get in Touch</span>
              <h2>Start Your Journey with Expert Learning Hub</h2>
              <p>
                Have questions about course admissions, fee structures, batch schedules, or need academic counseling? Reach out to our campus office or submit the form for a prompt callback.
              </p>

              <div class="elh-contact-item">
                <div class="elh-contact-icon">📍</div>
                <div class="elh-contact-text">
                  <b>Our Campus Location</b>
                  <span>${esc(gen.address || 'Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal')}</span>
                </div>
              </div>

              <div class="elh-contact-item">
                <div class="elh-contact-icon">📞</div>
                <div class="elh-contact-text">
                  <b>Direct Phone / WhatsApp</b>
                  <span><a href="tel:${esc(gen.phone || '+9779800924090')}">${esc(gen.phone || '+977 9800924090')}</a> ${gen.alt_phone ? `/ <a href="tel:${esc(gen.alt_phone)}">${esc(gen.alt_phone)}</a>` : ''}</span>
                </div>
              </div>

              <div class="elh-contact-item">
                <div class="elh-contact-icon">✉️</div>
                <div class="elh-contact-text">
                  <b>Email Inquiries</b>
                  <span><a href="mailto:${esc(gen.email || 'info@expertlearninghub.edu.np')}">${esc(gen.email || 'info@expertlearninghub.edu.np')}</a></span>
                </div>
              </div>

              <div class="elh-contact-item">
                <div class="elh-contact-icon">⏰</div>
                <div class="elh-contact-text">
                  <b>Office & Class Hours</b>
                  <span>${esc(gen.working_hours || 'Sunday – Friday: 6:00 AM – 7:00 PM')}</span>
                </div>
              </div>

              ${(gen.facebook_url || gen.youtube_url || gen.tiktok_url || gen.instagram_url) ? `
                <div style="margin-top:16px;display:flex;gap:10px;">
                  ${gen.facebook_url ? `<a href="${esc(gen.facebook_url)}" target="_blank" class="btn small" style="border-radius:8px;">Facebook</a>` : ''}
                  ${gen.youtube_url ? `<a href="${esc(gen.youtube_url)}" target="_blank" class="btn small" style="border-radius:8px;">YouTube</a>` : ''}
                  ${gen.instagram_url ? `<a href="${esc(gen.instagram_url)}" target="_blank" class="btn small" style="border-radius:8px;">Instagram</a>` : ''}
                  ${gen.tiktok_url ? `<a href="${esc(gen.tiktok_url)}" target="_blank" class="btn small" style="border-radius:8px;">TikTok</a>` : ''}
                </div>
              ` : ''}
            </div>

            <div style="margin-top:20px;padding:14px 18px;background:var(--brand-light);border:1px solid rgba(70,95,255,0.2);border-radius:12px;">
              <b style="color:var(--brand);display:block;font-size:13px;margin-bottom:2px;">Already Enrolled?</b>
              <span style="font-size:12px;color:var(--muted);">Access real-time routines, attendance records, and dues via the</span>
              <a href="javascript:void(0)" onclick="openPortalLoginModal('student')" style="font-size:12px;font-weight:700;color:var(--brand);margin-left:4px;text-decoration:none;">Student Portal →</a>
            </div>
          </div>

          <div style="background:var(--bg-body);padding:28px 24px;border-radius:var(--radius-xl);border:1px solid var(--line);">
            <div id="inquirySuccessAlert" style="display:none;"></div>

            <h3 style="margin:0 0 16px 0;font-size:18px;font-weight:800;color:var(--ink-dark);">Online Admission & Course Inquiry</h3>
            <form id="publicInquiryForm" class="form" onsubmit="handleWebInquiry(event)">
              <div class="elh-form-grid">
                <div>
                  <label>Full Name *
                    <input name="full_name" required placeholder="e.g. Aarav Sharma" autocomplete="name">
                  </label>
                </div>
                <div>
                  <label>Mobile Number (WhatsApp) *
                    <input name="phone" required placeholder="e.g. 98XXXXXXXX" type="tel" autocomplete="tel">
                  </label>
                </div>
                <div>
                  <label>Email Address
                    <input name="email" placeholder="e.g. aarav@example.com" type="email" autocomplete="email">
                  </label>
                </div>
                <div>
                  <label>Class / Grade Level
                    <select name="grade">
                      <option value="">-- Select Current Level --</option>
                      <option value="Class 8">Class 8</option>
                      <option value="Class 9">Class 9</option>
                      <option value="Class 10 (SEE)">Class 10 (SEE)</option>
                      <option value="+2 Science">+2 Science</option>
                      <option value="+2 Management">+2 Management</option>
                      <option value="Graduate / Professional">Graduate / Professional</option>
                    </select>
                  </label>
                </div>
                <div class="elh-form-full">
                  <label>Program of Interest
                    <select name="course_interest" id="inquiryCourseSelect">
                      <option value="">-- Select Course / Program --</option>
                      ${courseOptionsHtml}
                    </select>
                  </label>
                </div>
                <div class="elh-form-full">
                  <label>Message or Specific Requirements
                    <textarea name="message" rows="3" placeholder="Tell us about your learning goals or batch timing preference..."></textarea>
                  </label>
                </div>
                <div class="elh-form-full">
                  <button class="elh-btn-primary" type="submit" style="width:100%;justify-content:center;padding:12px;font-size:14px;border-radius:10px;">
                    Submit Online Inquiry →
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </section>

      <!-- FOOTER -->
      <footer class="elh-footer">
        <div class="elh-footer-inner">
          <div class="elh-footer-brand">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
              <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg, #465fff, #7c3aed);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px;">E</div>
              <h3 style="margin:0;font-size:18px;">${esc(gen.name || 'Expert Learning Hub')}</h3>
            </div>
            <p>
              ${esc(gen.tagline || 'Redefining Education Through Excellence & Innovation. Established with a vision to bridge traditional curriculum learning with international standards.')}
            </p>
            <div style="display:flex;gap:10px;margin-top:12px;">
              ${gen.facebook_url ? `<a href="${esc(gen.facebook_url)}" target="_blank" rel="noopener" style="color:#cbd5e1;font-size:18px;text-decoration:none;">🌐</a>` : ''}
              <a href="tel:${esc(gen.phone || '+9779800924090')}" style="color:#cbd5e1;font-size:18px;text-decoration:none;">📞</a>
              <a href="mailto:${esc(gen.email || 'info@expertlearninghub.edu.np')}" style="color:#cbd5e1;font-size:18px;text-decoration:none;">✉️</a>
            </div>
          </div>

          <div class="elh-footer-col">
            <h4>Quick Links</h4>
            <ul>
              <li><a href="#home">Home</a></li>
              <li><a href="#coursesSection">Our Courses</a></li>
              <li><a href="#iotSection">IoT Mentorship</a></li>
              <li><a href="#languagesSection">Language Prep</a></li>
              <li><a href="#eventsSection">Events & Workshops</a></li>
              <li><a href="#contactSection">Contact Us</a></li>
            </ul>
          </div>

          <div class="elh-footer-col">
            <h4>Portal Access</h4>
            <ul>
              <li><a href="javascript:void(0)" onclick="openPortalLoginModal('student')">Student Portal Login</a></li>
              <li><a href="javascript:void(0)" onclick="openPortalLoginModal('teacher')">Staff / Teacher Portal</a></li>
              <li><a href="javascript:void(0)" onclick="openPortalLoginModal('admin')">Administration Console</a></li>
              ${has('cms.manage') ? `<li><a href="javascript:void(0)" onclick="go('cms')">Website CMS Dashboard</a></li>` : ''}
              <li><a href="#contactSection">Admission Inquiries</a></li>
              <li><a href="javascript:void(0)" onclick="go('dashboard')">Active Session Dashboard</a></li>
            </ul>
          </div>

          <div class="elh-footer-col">
            <h4>Find Us</h4>
            <div style="font-size:13px;line-height:1.6;margin-bottom:12px;">
              <b>${esc(gen.address || 'Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal')}</b><br>
              Phone: ${esc(gen.phone || '+977 9800924090')} ${gen.alt_phone ? `/ ${esc(gen.alt_phone)}` : ''}<br>
              Email: ${esc(gen.email || 'info@expertlearninghub.edu.np')}
            </div>
            <div style="background:rgba(255,255,255,0.05);padding:10px 14px;border-radius:8px;font-size:12px;border:1px solid rgba(255,255,255,0.08);">
              <span style="color:#38bdf8;font-weight:700;">Affiliated Learning Hub</span>
              <p style="margin:2px 0 0 0;color:#94a3b8;font-size:11px;">Empowering students with 21st-century academic and technical excellence.</p>
            </div>
          </div>
        </div>

        <div class="elh-footer-bottom">
          <div>© 2024–2026 ${esc(gen.name || 'Expert Learning Hub')}. All Rights Reserved.</div>
          <div style="display:flex;gap:18px;">
            <a href="javascript:void(0)" onclick="alert('Privacy Policy: All student data is handled securely under ELH Privacy Guidelines.')" style="color:#64748b;text-decoration:none;">Privacy Policy</a>
            <a href="javascript:void(0)" onclick="alert('Terms: Institute admissions and tuition policies apply.')" style="color:#64748b;text-decoration:none;">Terms of Service</a>
            <a href="javascript:void(0)" onclick="openPortalLoginModal()" style="color:#38bdf8;text-decoration:none;font-weight:600;">Sign In to Portal</a>
          </div>
        </div>
      </footer>
    </div>
  `;

  app.innerHTML = html;

  // Initialize course grid with all courses
  filterWebCourses('all');

  // Scroll to section if passed
  if (initialSection) {
    setTimeout(() => {
      const target = document.querySelector(`#${initialSection}`) || document.querySelector(`#${initialSection}Section`);
      if (target) target.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  }
}

function renderLoginView() {
  applyTheme();
  app.innerHTML = `
    <div class="login-wrap">
      <div class="login-theme-toggle">
        <button class="btn" onclick="go('website')" style="font-size:12px;padding:6px 12px;display:inline-flex;align-items:center;gap:6px;margin-right:10px;border-radius:var(--radius-pill);">
          ← Return to Website
        </button>
        <button id="themeToggleBtn" class="theme-toggle-btn" onclick="toggleDarkMode()" aria-label="Toggle theme">
          ${isDarkMode
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`}
        </button>
      </div>
      <form id="login" class="login" onsubmit="event.preventDefault(); login(this);">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
          <div class="brand-icon">E</div>
          <div class="brand-text">
            <b>ELH</b><span>Portal</span>
          </div>
        </div>
        <h1>Portal Sign In</h1>
        <p class="muted">Enter your account credentials to access ELH Student, Teacher or Admin portal</p>
        <div class="login-error" id="error" style="display:none;background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px;"></div>
        <div class="form">
          <label>Username or Email
            <input name="username" required autofocus autocomplete="username" placeholder="e.g. student, staff or admin">
          </label>
          <label>Password
            <input type="password" name="password" required autocomplete="current-password" placeholder="••••••••">
          </label>
          <button class="primary" type="submit" style="margin-top:10px;padding:12px;font-size:14px;font-weight:700;">Sign In to Account</button>
        </div>
        <div style="margin-top:20px;text-align:center;">
          <a href="#home" style="font-size:13px;color:var(--brand);text-decoration:none;font-weight:600;">← Back to Public Website</a>
        </div>
      </form>
    </div>
  `;
}

function toggleMobileNav(btn) {
  const menu = document.querySelector('.elh-nav-menu');
  if (!menu) return;
  const isHidden = getComputedStyle(menu).display === 'none';
  menu.style.display = isHidden ? 'flex' : 'none';
  menu.style.flexDirection = 'column';
  menu.style.position = 'absolute';
  menu.style.top = '100%';
  menu.style.left = '0';
  menu.style.right = '0';
  menu.style.background = 'var(--bg-card)';
  menu.style.padding = '16px 20px';
  menu.style.borderBottom = '1px solid var(--line)';
  menu.style.boxShadow = 'var(--shadow-lg)';
}

// ---------------------------------------------------------------------------
// Proxy & Substitute Class Management
// ---------------------------------------------------------------------------
let _proxyFilter = 'all';
let _proxyData = [];
window._proxySearch = '';

async function teacher_proxy() {
  const data = await api('/dashboard');
  if (data.role === 'staff' || data.role === 'teacher') {
    renderTeacherDashboard(data);
    setTimeout(() => document.querySelector('#teacherProxySection')?.scrollIntoView({ behavior: 'smooth' }), 100);
  } else {
    go('proxy');
  }
}

async function proxy() {
  if (me && (me.role === 'staff' || me.role === 'teacher') && !has('staff.manage')) {
    return teacher_proxy();
  }
  const [requests, smsSettings] = await Promise.all([
    api('/proxy/requests'),
    api('/proxy/sms-settings').catch(() => ({ mode: 'disabled' }))
  ]);
  _proxyData = requests;
  renderProxyPage(smsSettings.mode);
}

function filterProxyRequests(filter) {
  _proxyFilter = filter;
  document.querySelectorAll('.proxy-filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === filter);
  });
  renderProxyTable();
}

function searchProxyTable(q) {
  window._proxySearch = (q || '').trim().toLowerCase();
  renderProxyTable();
}

function renderProxyPage(smsMode) {
  const pendingApproval = _proxyData.filter(r => r.status === 'Pending').length;
  const pendingProxy = _proxyData.filter(r => r.status === 'Approved' && (!r.proxy_teacher_id || r.proxy_status === 'Pending')).length;
  const confirmedProxy = _proxyData.filter(r => r.proxy_status === 'Accepted').length;
  const total = _proxyData.length;

  const modeBadge = smsMode === 'auto'
    ? '<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;">● Auto SMS Enabled</span>'
    : (smsMode === 'manual'
      ? '<span class="badge" style="background:#e0f2fe;color:#0369a1;font-weight:700;">● Manual SMS Mode</span>'
      : '<span class="badge" style="background:#f1f5f9;color:#64748b;font-weight:700;">○ SMS Disabled</span>');

  const html = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
      <div>
        <h2 style="margin:0;display:flex;align-items:center;gap:10px;">
          ${uiIcon('proxy', 22)} Proxy & Substitute Class Management
        </h2>
        <small class="muted">Manage faculty leave requests, smart substitute assignments, student notifications & SMS alerts</small>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <button onclick="proxySmsSettingsModal()" style="display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:6px 12px;">
          ⚙️ SMS Settings ${modeBadge}
        </button>
        <button class="primary" onclick="proxyLeaveRequestModal()" style="display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:6px 14px;">
          ${uiIcon('plus', 14)} Record Absence / Assign Proxy
        </button>
      </div>
    </div>

    <div class="cards" style="margin-bottom:18px;">
      <div class="card" onclick="filterProxyRequests('all')" style="cursor:pointer;">
        <span>Total Proxy Requests</span>
        <b style="font-size:24px;margin-top:6px;">${total}</b>
        <small class="muted">All historical & upcoming records</small>
      </div>
      <div class="card" onclick="filterProxyRequests('pending_approval')" style="cursor:pointer;">
        <span style="color:#b45309;">Pending Leave Approval</span>
        <b style="font-size:24px;margin-top:6px;color:#d97706;">${pendingApproval}</b>
        <small class="muted">Awaiting administrator approval</small>
      </div>
      <div class="card" onclick="filterProxyRequests('proxy_pending')" style="cursor:pointer;">
        <span style="color:#2563eb;">Proxy Needed / Pending</span>
        <b style="font-size:24px;margin-top:6px;color:#3b82f6;">${pendingProxy}</b>
        <small class="muted">Needs substitute assignment or response</small>
      </div>
      <div class="card" onclick="filterProxyRequests('accepted')" style="cursor:pointer;">
        <span style="color:#15803d;">Confirmed Substitutes</span>
        <b style="font-size:24px;margin-top:6px;color:#16a34a;">${confirmedProxy}</b>
        <small class="muted">Proxy faculty accepted & students notified</small>
      </div>
    </div>

    <section class="panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
        <div style="display:gap:6px;display:flex;flex-wrap:wrap;">
          <button class="btn proxy-filter-btn active" data-filter="all" onclick="filterProxyRequests('all')" style="font-size:12px;padding:4px 10px;">All Requests (${total})</button>
          <button class="btn proxy-filter-btn" data-filter="pending_approval" onclick="filterProxyRequests('pending_approval')" style="font-size:12px;padding:4px 10px;">Pending Approval (${pendingApproval})</button>
          <button class="btn proxy-filter-btn" data-filter="proxy_pending" onclick="filterProxyRequests('proxy_pending')" style="font-size:12px;padding:4px 10px;">Proxy Pending (${pendingProxy})</button>
          <button class="btn proxy-filter-btn" data-filter="accepted" onclick="filterProxyRequests('accepted')" style="font-size:12px;padding:4px 10px;">Accepted (${confirmedProxy})</button>
          <button class="btn proxy-filter-btn" data-filter="declined" onclick="filterProxyRequests('declined')" style="font-size:12px;padding:4px 10px;">Declined</button>
          <button class="btn proxy-filter-btn" data-filter="rejected" onclick="filterProxyRequests('rejected')" style="font-size:12px;padding:4px 10px;">Rejected</button>
        </div>
        <input type="text" placeholder="Search teacher or subject..." oninput="searchProxyTable(this.value)" style="max-width:220px;font-size:12px;padding:4px 10px;">
      </div>

      <div id="proxyTableContainer"></div>
    </section>
  `;

  shell('Proxy & Substitute Classes', 'Manage faculty leaves, proxy assignments, and student alerts', html);
  renderProxyTable();
}

function renderProxyTable() {
  const container = document.querySelector('#proxyTableContainer');
  if (!container) return;

  let filtered = _proxyData || [];
  const f = _proxyFilter;
  if (f === 'pending_approval') filtered = filtered.filter(r => r.status === 'Pending');
  else if (f === 'proxy_pending') filtered = filtered.filter(r => r.status === 'Approved' && (!r.proxy_teacher_id || r.proxy_status === 'Pending'));
  else if (f === 'accepted') filtered = filtered.filter(r => r.proxy_status === 'Accepted');
  else if (f === 'declined') filtered = filtered.filter(r => r.proxy_status === 'Declined');
  else if (f === 'rejected') filtered = filtered.filter(r => r.status === 'Rejected');

  if (window._proxySearch) {
    const q = window._proxySearch;
    filtered = filtered.filter(r =>
      (r.original_teacher_name || '').toLowerCase().includes(q) ||
      (r.proxy_teacher_name || '').toLowerCase().includes(q) ||
      (r.subject_name || '').toLowerCase().includes(q) ||
      (r.display_class_name || r.class_name || '').toLowerCase().includes(q)
    );
  }

  if (!filtered.length) {
    container.innerHTML = '<p class="muted" style="padding:20px 0;text-align:center;">No proxy requests match the selected filter.</p>';
    return;
  }

  const cols = [
    {
      key: 'class_date',
      label: 'Class Date',
      render: r => `<div><b>${esc(r.class_date)}</b><br><small class="muted">${esc(r.day_of_week || '')}</small></div>`
    },
    {
      key: 'routine',
      label: 'Class / Period',
      render: r => `<div><b>${esc(r.display_class_name || r.class_name || '-')}</b><br><small class="muted">${esc(r.period_label || '')} (${esc(r.start_time || '')} - ${esc(r.end_time || '')})</small></div>`
    },
    {
      key: 'subject_name',
      label: 'Subject',
      render: r => `<b style="color:var(--brand);">${esc(r.subject_name || '-')}</b>`
    },
    {
      key: 'original_teacher_name',
      label: 'Absent Teacher',
      render: r => `<div><b>${esc(r.original_teacher_name || 'Unassigned')}</b><br><small class="muted">Req by: ${esc(r.requested_by_teacher_name || r.requested_by_user_name || 'Self')}</small></div>`
    },
    {
      key: 'leave_details',
      label: 'Leave & Reason',
      render: r => `<div><span class="badge active" style="font-size:11px;">${esc(r.leave_type || 'Absent')}</span><br><small class="muted">${esc(r.reason || 'No reason specified')}</small></div>`
    },
    {
      key: 'leave_status',
      label: 'Leave Approval',
      render: r => {
        if (r.status === 'Approved') return `<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;">Approved</span>`;
        if (r.status === 'Rejected') return `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;">Rejected</span>`;
        return `<span class="badge" style="background:#fef3c7;color:#b45309;font-weight:700;">Pending</span>`;
      }
    },
    {
      key: 'proxy_teacher',
      label: 'Proxy Faculty',
      render: r => {
        if (!r.proxy_teacher_id) {
          return `<button class="primary" style="padding:3px 8px;font-size:11px;" onclick="assignProxyModal(${r.id}, ${r.routine_id}, '${r.class_date}', '${esc(r.subject_name)}', '${esc(r.original_teacher_name)}')">
            + Assign Proxy
          </button>`;
        }
        let statusBadge = '';
        if (r.proxy_status === 'Accepted') statusBadge = `<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;font-size:11px;">● Accepted</span>`;
        else if (r.proxy_status === 'Declined') statusBadge = `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-weight:700;font-size:11px;">● Declined</span>`;
        else statusBadge = `<span class="badge" style="background:#fef3c7;color:#b45309;font-weight:700;font-size:11px;">● Pending Response</span>`;

        return `<div>
          <b>${esc(r.proxy_teacher_name)}</b><br>
          ${statusBadge}
        </div>`;
      }
    },
    {
      key: 'sms_status',
      label: 'Student SMS',
      render: r => {
        if (r.sms_sent > 0) {
          return `<span class="badge" style="background:#dcfce7;color:#15803d;font-weight:700;font-size:11px;" title="Sent on ${esc(r.sms_sent_at || '')}">✓ Sent (${r.sms_sent})</span>`;
        }
        return `<button style="font-size:11px;padding:2px 7px;" onclick="sendProxySms(${r.id})" title="Send SMS notification to enrolled students">Send SMS</button>`;
      }
    },
    {
      key: 'actions',
      label: 'Actions',
      render: r => {
        const btns = [];
        if (r.status === 'Pending') {
          btns.push(`<button class="primary" style="padding:3px 8px;font-size:11px;background:#16a34a;border-color:#16a34a;" onclick="approveProxyLeave(${r.id})">Approve</button>`);
          btns.push(`<button style="padding:3px 8px;font-size:11px;color:#dc2626;border-color:#fca5a5;" onclick="rejectProxyLeave(${r.id})">Reject</button>`);
        }
        if (r.proxy_teacher_id && r.proxy_status === 'Pending') {
          btns.push(`<button class="primary" style="padding:3px 8px;font-size:11px;background:#2563eb;border-color:#1d4ed8;" onclick="adminConfirmProxy(${r.id})" title="Confirm proxy on behalf of teacher">Confirm</button>`);
        }
        if (r.proxy_teacher_id) {
          btns.push(`<button style="padding:3px 8px;font-size:11px;" onclick="assignProxyModal(${r.id}, ${r.routine_id}, '${r.class_date}', '${esc(r.subject_name)}', '${esc(r.original_teacher_name)}')">Reassign</button>`);
        }
        return `<div style="display:flex;gap:4px;flex-wrap:wrap;">${btns.join('')}</div>`;
      }
    }
  ];

  container.innerHTML = table(filtered, cols);
}

async function proxyLeaveRequestModal(defaultRoutineId = null) {
  const [routines, lk] = await Promise.all([
    api('/routines').catch(() => []),
    getLookups()
  ]);

  const teachers = lk.teachers || [];
  const today = new Date().toISOString().split('T')[0];
  const isAdmin = has('staff.manage') || (me && (me.role === 'admin' || me.role === 'super_admin'));

  const routineOptions = routines.map(r => {
    const selected = defaultRoutineId && Number(defaultRoutineId) === Number(r.id) ? 'selected' : '';
    const timeLabel = r.start_time ? ` [${r.start_time} - ${r.end_time}]` : '';
    return `<option value="${r.id}" ${selected}>${esc(r.day_of_week)} · ${esc(r.class_name || '')} · ${esc(r.subject_name)} (${esc(r.period_label)})${timeLabel} - ${esc(r.teacher_name || 'Unassigned')}</option>`;
  }).join('');

  const teacherOptions = teachers.map(t => `<option value="${t.id}">${esc(t.teacher_name)} (${esc(t.subject || 'General')})</option>`).join('');

  modal('Record Absence & Request Proxy', `
    <form class="form" onsubmit="event.preventDefault(); submitProxyLeaveRequest(this);">
      <label>Class Routine *
        <select name="routine_id" required>
          <option value="">-- Select Scheduled Class Routine --</option>
          ${routineOptions}
        </select>
      </label>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <label>Absence / Class Date *
          <input type="date" name="class_date" value="${today}" required>
        </label>
        <label>Leave Type
          <select name="leave_type">
            <option value="Absent">General Absence</option>
            <option value="Sick Leave">Sick Leave</option>
            <option value="Casual Leave">Casual Leave</option>
            <option value="Emergency">Emergency</option>
            <option value="Duty / Official">Duty / Official</option>
          </select>
        </label>
      </div>

      <label>Reason / Absence Notes
        <textarea name="reason" rows="2" placeholder="Provide details regarding the absence or specific lesson instructions for the proxy teacher..."></textarea>
      </label>

      ${isAdmin ? `
        <div style="border-top:1px solid var(--line);padding-top:10px;margin-top:4px;">
          <small class="muted" style="display:block;margin-bottom:8px;">Administrator Controls</small>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <label>Regular / Absent Teacher
              <select name="original_teacher_id">
                <option value="">-- Auto from Routine --</option>
                ${teacherOptions}
              </select>
            </label>
            <label>Directly Assign Proxy (Optional)
              <select name="proxy_teacher_id">
                <option value="">-- Assign Later --</option>
                ${teacherOptions}
              </select>
            </label>
          </div>
        </div>
      ` : ''}

      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
        <button type="button" onclick="closeModal()">Cancel</button>
        <button class="primary" type="submit">Submit Request</button>
      </div>
    </form>
  `);
}

async function submitProxyLeaveRequest(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.routine_id = Number(data.routine_id);
  if (data.original_teacher_id) data.original_teacher_id = Number(data.original_teacher_id);
  else delete data.original_teacher_id;
  if (data.proxy_teacher_id) data.proxy_teacher_id = Number(data.proxy_teacher_id);
  else delete data.proxy_teacher_id;

  try {
    const res = await api('/proxy/requests', { method: 'POST', body: JSON.stringify(data) });
    closeModal();
    alert(res.message || 'Leave request submitted successfully.');
    if (location.hash === '#proxy') proxy();
    else if (location.hash === '#teacher-proxy' || (me && (me.role === 'staff' || me.role === 'teacher'))) dashboard();
    else proxy();
  } catch (err) {
    showError(err);
  }
}

async function assignProxyModal(requestId, routineId, classDate, subjectName, origTeacher) {
  modal('Assign Proxy Substitute Teacher', `<p class="muted" style="padding:10px 0;">Loading smart matching suggestions...</p>`);

  try {
    const [suggestions, lk] = await Promise.all([
      api(`/proxy/suggestions/${routineId}/${classDate}`).catch(() => []),
      getLookups()
    ]);

    const allTeachers = lk.teachers || [];
    const suggestionsHtml = suggestions.length ? `
      <div style="margin-bottom:14px;">
        <b style="font-size:13px;display:flex;align-items:center;gap:6px;margin-bottom:8px;color:#1e293b;">
          🎯 Smart Matching Suggestions (Subject Match & Period Availability)
        </b>
        <div style="display:flex;flex-direction:column;gap:6px;max-height:160px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;padding:8px;">
          ${suggestions.map(s => {
            const matchBadge = s.subject_match ? `<span class="badge" style="background:#dcfce7;color:#15803d;font-size:10px;">Subject Match</span>` : '';
            const busyBadge = s.is_busy ? `<span class="badge" style="background:#fee2e2;color:#b91c1c;font-size:10px;">Busy In Period</span>` : `<span class="badge" style="background:#e0f2fe;color:#0369a1;font-size:10px;">Free In Period</span>`;
            const absentBadge = s.is_absent ? `<span class="badge" style="background:#fef3c7;color:#b45309;font-size:10px;">Absent</span>` : '';

            return `
              <div onclick="selectProxyTeacher(${s.id})" style="padding:6px 10px;border-radius:6px;background:var(--bg-card);border:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;cursor:pointer;font-size:12px;" onmouseover="this.style.borderColor='var(--brand)'" onmouseout="this.style.borderColor='var(--line)'">
                <div>
                  <b>${esc(s.teacher_name)}</b> <small class="muted">(${esc(s.subject)})</small>
                </div>
                <div style="display:flex;gap:4px;">
                  ${matchBadge} ${busyBadge} ${absentBadge}
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    ` : '';

    const teacherOptions = allTeachers.map(t => `<option value="${t.id}">${esc(t.teacher_name)} (${esc(t.subject || 'General')})</option>`).join('');

    modal('Assign Proxy Substitute Teacher', `
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:13px;">
        <div>Class Date: <b>${esc(classDate)}</b> · Subject: <b style="color:var(--brand);">${esc(subjectName)}</b></div>
        <div style="margin-top:2px;color:#64748b;">Absent Regular Faculty: <b>${esc(origTeacher)}</b></div>
      </div>

      ${suggestionsHtml}

      <form class="form" onsubmit="event.preventDefault(); submitAssignProxy(${requestId}, this);">
        <label>Select Proxy / Substitute Faculty *
          <select id="proxyTeacherSelect" name="proxy_teacher_id" required>
            <option value="">-- Choose Substitute Teacher --</option>
            ${teacherOptions}
          </select>
        </label>
        <label>Administrator Note / Lesson Instructions
          <textarea name="admin_note" rows="2" placeholder="e.g. Please cover Chapter 4 exercises..."></textarea>
        </label>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
          <button type="button" onclick="closeModal()">Cancel</button>
          <button class="primary" type="submit">Assign Proxy Teacher</button>
        </div>
      </form>
    `);
  } catch (err) {
    showError(err);
  }
}

function selectProxyTeacher(teacherId) {
  const sel = document.querySelector('#proxyTeacherSelect');
  if (sel) {
    sel.value = String(teacherId);
    sel.style.borderColor = 'var(--brand)';
  }
}

async function submitAssignProxy(requestId, form) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.proxy_teacher_id = Number(data.proxy_teacher_id);
  try {
    const res = await api(`/proxy/requests/${requestId}/assign-proxy`, { method: 'POST', body: JSON.stringify(data) });
    closeModal();
    alert(res.message || 'Proxy assigned.');
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function proxySmsSettingsModal() {
  try {
    const settings = await api('/proxy/sms-settings');
    const currentMode = settings.mode || 'disabled';

    modal('Proxy Notification SMS Settings', `
      <form class="form" onsubmit="event.preventDefault(); submitProxySmsSettings(this);">
        <p class="muted" style="margin-top:0;font-size:13px;">
          Configure how student SMS alerts are delivered when a substitute proxy class is assigned and confirmed.
        </p>

        <div style="display:flex;flex-direction:column;gap:10px;margin:14px 0;">
          <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;padding:10px;border:1px solid var(--line);border-radius:8px;">
            <input type="radio" name="mode" value="disabled" ${currentMode === 'disabled' ? 'checked' : ''} style="margin-top:3px;">
            <div>
              <b>Disabled (Default)</b>
              <div style="font-size:12px;color:var(--text-muted);">No SMS messages are queued or sent for proxy class substitutions. Only in-portal notices are shown.</div>
            </div>
          </label>

          <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;padding:10px;border:1px solid var(--line);border-radius:8px;">
            <input type="radio" name="mode" value="manual" ${currentMode === 'manual' ? 'checked' : ''} style="margin-top:3px;">
            <div>
              <b>Manual Mode</b>
              <div style="font-size:12px;color:var(--text-muted);">Administrators can explicitly click the "Send SMS" button on each proxy request to broadcast alerts to students.</div>
            </div>
          </label>

          <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;padding:10px;border:1px solid var(--line);border-radius:8px;">
            <input type="radio" name="mode" value="auto" ${currentMode === 'auto' ? 'checked' : ''} style="margin-top:3px;">
            <div>
              <b>Automatic Mode</b>
              <div style="font-size:12px;color:var(--text-muted);">SMS is automatically dispatched to all enrolled class students immediately upon proxy acceptance or admin confirmation.</div>
            </div>
          </label>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
          <button type="button" onclick="closeModal()">Cancel</button>
          <button class="primary" type="submit">Save Setting</button>
        </div>
      </form>
    `);
  } catch (err) {
    showError(err);
  }
}

async function submitProxySmsSettings(form) {
  const mode = new FormData(form).get('mode');
  try {
    const res = await api('/proxy/sms-settings', { method: 'POST', body: JSON.stringify({ mode }) });
    closeModal();
    alert(res.message || 'Settings saved.');
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function approveProxyLeave(requestId) {
  if (!confirm('Approve this teacher absence / leave request?')) return;
  try {
    const res = await api(`/proxy/requests/${requestId}/approve`, { method: 'POST', body: JSON.stringify({ status: 'Approved', admin_note: 'Approved by admin' }) });
    alert(res.message || 'Leave approved.');
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function rejectProxyLeave(requestId) {
  const note = prompt('Enter rejection reason or note:');
  if (note === null) return;
  try {
    const res = await api(`/proxy/requests/${requestId}/reject`, { method: 'POST', body: JSON.stringify({ status: 'Rejected', admin_note: note || 'Rejected' }) });
    alert(res.message || 'Leave rejected.');
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function adminConfirmProxy(requestId) {
  if (!confirm('Confirm this proxy substitute assignment? Enrolled students will be notified.')) return;
  try {
    const res = await api(`/proxy/requests/${requestId}/admin-confirm`, { method: 'POST', body: JSON.stringify({}) });
    alert(res.message || 'Proxy confirmed.');
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function sendProxySms(requestId) {
  if (!confirm('Queue SMS notification to all enrolled students for this proxy class?')) return;
  try {
    const res = await api(`/proxy/requests/${requestId}/send-sms`, { method: 'POST', body: JSON.stringify({}) });
    alert(res.message || `SMS queued for ${res.count} students.`);
    proxy();
  } catch (err) {
    showError(err);
  }
}

async function respondProxy(requestId, response) {
  let declined_reason = '';
  if (response === 'Decline') {
    declined_reason = prompt('Please provide reason for declining this proxy class:') || 'Unable to cover';
    if (!declined_reason) return;
  } else {
    if (!confirm('Accept this proxy class substitution? Enrolled students will be notified.')) return;
  }

  try {
    const res = await api(`/proxy/requests/${requestId}/proxy-response`, {
      method: 'POST',
      body: JSON.stringify({ response, declined_reason })
    });
    alert(res.message || `Proxy class ${response.toLowerCase()}ed.`);
    dashboard();
  } catch (err) {
    showError(err);
  }
}

async function markProxyNotifRead(notificationId, btn) {
  try {
    await api(`/student/proxy-notifications/${notificationId}/read`, { method: 'POST', body: JSON.stringify({}) });
    if (btn) {
      btn.outerHTML = `<span class="muted" style="font-size:11px;">✓ Seen</span>`;
    }
  } catch (err) {
    console.error(err);
  }
}

const pages = {
  home: renderPublicWebsite,
  website: renderPublicWebsite,
  landing: renderPublicWebsite,
  login: renderLoginView,
  dashboard,
  'teacher-classes': teacher_classes,
  teacher_classes,
  'teacher-attendance': teacher_attendance,
  teacher_attendance,
  'teacher-payments': teacher_payments,
  teacher_payments,
  students,
  'student-profile': student_profile,
  student_profile,
  enrollments,
  bills,
  'student-transactions': student_transactions,
  student_transactions,
  certificates,
  attendance,
  calendar,
  tasks,
  courses,
  schools,
  staff,
  advances,
  salary,
  finance,
  transfers,
  routines,
  grades,
  reports,
  assistant,
  company,
  settings,
  users,
  cms,
  inquiries,
  proxy,
  'teacher-proxy': teacher_proxy,
  teacher_proxy,
};

async function go(page) {
  location.hash = page;
  const pageName = page.split('?')[0];

  if (['home', 'website', 'landing', ''].includes(pageName)) {
    renderPublicWebsite();
    return;
  }
  if (pageName === 'login') {
    if (token && me) {
      go('dashboard');
      return;
    }
    renderLoginView();
    return;
  }
  if (!token && ['courses', 'iot', 'languages', 'growth', 'events', 'about', 'contact'].includes(pageName)) {
    renderPublicWebsite(pageName);
    return;
  }

  try {
    if (!me) me = await api('/auth/me');
    await (pages[pageName] || dashboard)();
  } catch (error) {
    if (/sign in/i.test(error.message)) {
      logout();
    } else {
      app.innerHTML = `<div class="error-page"><h1>Unable to open this page</h1><p>${esc(error.message)}</p><button onclick="go('dashboard')">Return to dashboard</button></div>`;
    }
  }
}

function boot() {
  applyTheme();
  const rawHash = (location.hash || '').replace(/^#\/?/, '');
  const pageName = rawHash.split('?')[0];

  if (!token) {
    if (pageName === 'login') {
      renderLoginView();
    } else {
      renderPublicWebsite(pageName);
    }
    return;
  }

  if (['home', 'website', 'landing'].includes(pageName)) {
    renderPublicWebsite();
    return;
  }

  go(pageName || 'dashboard');
}

Object.assign(window, {
  go, logout, toggleDarkMode, toggleSidebar, toggleNavGroup, triggerAttendanceSync, filterStudents, exportStudentCsv, studentForm, editStudent, archiveStudent,
  viewStudentProfile, downloadStudentProfilePdf, switchProfileTab, student_profile, exportEnrollments, enrollmentForm,
  exportBills, billGenerationForm, billPayment, toggleSelectAllBills, onBillCheckboxChange, updateSelectedBillsUI, openSelectedBillsPayment, multiBillPaymentModal, attendanceAlerts, manualAttendanceForm, switchManualPeople,
  attendanceReviewForm, exportCourses, courseForm, exportSchools, schoolForm, exportStaff, staffForm, accountForm,
  moneyForm, taskForm, completeTask, bugForm, transferForm, openCalendarMonth, calendarEventForm,
  changePasswordModal, assistant, runAssistantCmd, clearAssistant, handleAssistantSubmit, sendAssistantQuery,
  certificates, exportCertificates, regenerateCertificate, certificateForm, onCertEnrollChange,
  student_transactions, exportStudentTransactions, studentTransactionForm,
  grades, gradeForm, classLevelForm,
  routines, switchRoutinePlan, switchRoutineCourse, downloadRoutinePdf, deleteRoutinePeriod, routinePeriodForm, newRoutinePlanForm,
  advances, exportAdvances, advanceForm,
  salary, exportSalary, salaryPayoutForm, onSalaryStaffChange, calculateSalaryData, recalcSalaryNet,
  settings, switchSettingsCategory, saveSettings, triggerBackup,
  users, filterUsersList, renderUsersTable, userForm, onUserRoleChange, onUserStaffSelect, onUserStudentSelect,
  setPermissionsAll, resetPermissionsToRoleDefaults, userResetPasswordModal, generateRandomPassword, validateClientPassword,
  openCreateUserForStaff, openCreateUserForStudent, toggleUserDropdown, closeUserDropdown,
  unlockUser, toggleUser, userAuditLogModal, exportUsersCsv,
  renderPublicWebsite, renderLoginView, openPortalLoginModal, switchModalRole, filterWebCourses, prefillInquiryCourse, handleWebInquiry, toggleMobileNav,
  cms, inquiries, switchCmsTab, renderCmsTabContent, saveCmsHero, saveCmsGeneral, saveCmsStats, saveCmsIot, saveCmsPillars,
  cmsCourseModal, toggleCmsCourseStatus, deleteCmsCourse, cmsLanguageModal, deleteCmsLanguage,
  cmsEventModal, deleteCmsEvent, cmsTestimonialModal, deleteCmsTestimonial, cmsFaqModal, deleteCmsFaq,
  filterCmsInquiries, searchCmsInquiries, cmsInquiryStatusModal, deleteCmsInquiry, resetCmsDefaults, showCmsToast,
  proxy, teacher_proxy, filterProxyRequests, searchProxyTable, proxyLeaveRequestModal, submitProxyLeaveRequest,
  assignProxyModal, selectProxyTeacher, submitAssignProxy, proxySmsSettingsModal, submitProxySmsSettings,
  approveProxyLeave, rejectProxyLeave, adminConfirmProxy, sendProxySms, respondProxy, markProxyNotifRead,
});
boot();
