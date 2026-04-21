// ── Helpers ─────────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (b == null || b === 0) return '—';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0;
  while (b >= 1024 && i < 4) { b /= 1024; i++; }
  return `${b.toFixed(1)} ${u[i]}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('sv', {day:'2-digit', month:'short'}) + ' ' +
         d.toLocaleTimeString('sv', {hour:'2-digit', minute:'2-digit'});
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtBitrate(bps) {
  if (bps == null || bps === 0) return '—';
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`;
  if (bps >= 1_000)     return `${(bps / 1_000).toFixed(0)} kbps`;
  return `${Math.round(bps)} bps`;
}

function fmtDuration(s) {
  if (s == null || s === 0) return '—';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h >= 24) return `${Math.floor(h/24)}d ${h%24}h`;
  if (h > 0)   return `${h}h ${m}m`;
  return `${m}m`;
}

function badge(status) {
  const map = {
    scanning:'badge-discarded',
    pending:'badge-pending', assigned:'badge-assigned',
    processing:'badge-processing', complete:'badge-done', done:'badge-done',
    discarded:'badge-discarded', cancelled:'badge-cancelled',
    error:'badge-error', duplicate:'badge-duplicate',
    sleeping:'badge-sleeping', draining:'badge-draining', online:'badge-online', offline:'badge-offline',
    'disk full':'badge-error',
  };
  const cls = map[status] || 'badge-discarded';
  const label = status === 'complete' ? 'done' : status;
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

function svgIcon(name, size = 16) {
  const paths = {
    box: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z',
    plus: 'M12 5v14M5 12h14',
    trash: 'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6',
    stop: 'M6 6h12v12H6z',
    pause: 'M6 4h4v16H6zM14 4h4v16h-4z',
    play: 'M5 3l14 9-14 9V3z',
    settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
    sleep: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z',
    sun: 'M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z',
    moon: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z',
    chevronDown: 'M6 9l6 6 6-6',
    chevronRight: 'M9 18l6-6-6-6',
  };
  const d = paths[name] || '';
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

// ── State ────────────────────────────────────────────────────────────────────
const ST = {
  data: window._INIT_DATA || null,
  tab: localStorage.getItem('packa-tab') || 'overview',
  theme: localStorage.getItem('packa-theme') || 'system',
  connected: null,
  demo: false,
  pollInterval: 3000,
  workerPollInterval: 500,
  _pollTimer: null,
  // files tab
  fileFilters: new Set(),     // OR — empty means all
  fileFiltersNot: new Set(),  // NOT — always excluded
  fileSearch: '',
  fileSelected: new Set(),
  fileBulkOpen: false,
  // modal
  modalStatus: null,
  modalSelected: new Set(),
  modalBulkOpen: false,
  // workers tab
  workerSettingsOpen: {},   // configId → bool
  workerCmdOpen: {},        // configId → bool
  workerInlineEdit: {},     // configId → 'encoder' | 'batch' | null
  // scan tab
  scanEnabled: false,
  scanInterval: 60,
};

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  applyTheme(ST.theme);
  setTab(ST.tab, false);

  if (ST.data) {
    if (ST.data.master_error) {
      ST.connected = false;
      ST.demo = true;
    } else {
      ST.connected = true;
      ST.demo = false;
    }
    updateFromData(ST.data);
    render();
  }

  fetchAll();
  document.addEventListener('click', function(e) {
    if (ST.fileBulkOpen && !e.target.closest('.dropdown')) {
      ST.fileBulkOpen = false;
      ST.fileQueueOpen = false;
      renderFileBulkMenu();
    }
  });
});

// ── Theme ────────────────────────────────────────────────────────────────────
function _resolvedTheme(t) {
  return t === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : t;
}

function applyTheme(t) {
  ST.theme = t;
  document.documentElement.setAttribute('data-theme', _resolvedTheme(t));
  localStorage.setItem('packa-theme', t);
  const icon = document.getElementById('theme-icon');
  if (icon) {
    const paths = {
      dark:   'M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z',
      light:  'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z',
      system: 'M2 3h20v14H2zM8 21h8M12 17v4',
    };
    icon.querySelector('path').setAttribute('d', paths[t] || paths.system);
  }
}

function toggleTheme() {
  const next = { dark: 'light', light: 'system', system: 'dark' };
  applyTheme(next[ST.theme] || 'system');
}

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (ST.theme === 'system') applyTheme('system');
});

// ── Tab switching ────────────────────────────────────────────────────────────
function setTab(t, doRender = true) {
  ST.tab = t;
  localStorage.setItem('packa-tab', t);
  document.querySelectorAll('.tab').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === t);
  });
  document.querySelectorAll('[id^="tab-"]').forEach(el => {
    el.style.display = el.id === `tab-${t}` ? '' : 'none';
  });
  if (doRender) renderActiveTab();
  // Reset poll timer when switching to/from workers tab so interval takes effect immediately
  clearTimeout(ST._pollTimer);
  const interval = t === 'workers' ? ST.workerPollInterval : ST.pollInterval;
  if (interval > 0) ST._pollTimer = setTimeout(fetchAll, interval);
}

// ── Edit-guard helpers ────────────────────────────────────────────────────────
function isFocused() {
  const a = document.activeElement;
  return !!(a && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA'));
}

// Returns true when the user is mid-edit: focused input OR a worker settings panel is open.
function isEditing() {
  if (isFocused()) return true;
  if (ST.modalSelected.size > 0) return true;
  if (Object.values(ST.workerSettingsOpen).some(Boolean)) return true;
  if (Object.values(ST.workerInlineEdit).some(Boolean)) return true;
  return Object.values(ST.workerCmdOpen).some(Boolean);
}

// ── Polling ──────────────────────────────────────────────────────────────────
async function fetchAll() {
  try {
    const r = await fetch('/data/dashboard');
    if (!r.ok) throw new Error(`${r.status}`);
    const data = await r.json();
    if (data.master_error) {
      ST.connected = false;
      ST.demo = true;
    } else {
      ST.connected = true;
      ST.demo = false;
      if (!isEditing()) updateFromData(data);
    }
    ST.data = data;
    render();
  } catch(e) {
    ST.connected = false;
    updateConnectionUI();
  } finally {
    const nextInterval = ST.tab === 'workers' ? ST.workerPollInterval : ST.pollInterval;
    if (nextInterval > 0) {
      clearTimeout(ST._pollTimer);
      ST._pollTimer = setTimeout(fetchAll, nextInterval);
    }
  }
}

function updateFromData(data) {
  if (data.scan_settings) {
    ST.scanEnabled = !!data.scan_settings.enabled;
    ST.scanInterval = Math.round((data.scan_settings.interval || 60) / 60);
  }
}

// ── Top-level render ─────────────────────────────────────────────────────────
function render() {
  updateConnectionUI();
  updateTabBadges();
  updateScanButton();
  if (!isEditing()) renderActiveTab();
}

function updateScanButton() {
  const btn = document.getElementById('topbar-scan-btn');
  if (!btn) return;
  const scan = (ST.data && ST.data.scan) || {};
  if (scan.running) {
    btn.textContent = '⏹ Stop scan';
    btn.className = 'btn btn-sm btn-danger';
    btn.style.cssText = 'font-size:11px;padding:3px 10px;height:26px';
  } else {
    btn.innerHTML = '▶ Scan';
    btn.className = 'btn btn-sm btn-primary';
    btn.style.cssText = 'font-size:11px;padding:3px 10px;height:26px';
  }
}

function topbarScanClick() {
  const scan = (ST.data && ST.data.scan) || {};
  if (scan.running) scanStop(); else scanStart();
}

function updateConnectionUI() {
  const dot = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  const pill = document.getElementById('processing-pill');
  const cnt = document.getElementById('processing-count');
  if (dot) {
    dot.className = 'status-dot ' + (ST.connected === null ? 'connecting' : ST.connected ? 'connected' : '');
  }
  if (label) {
    label.textContent = ST.connected === null ? 'Connecting…' : ST.connected ? 'Connected' : 'Offline';
  }
  const workers = (ST.data && ST.data.workers) || [];
  const processing = workers.filter(s => s.state === 'processing').length;
  if (pill && cnt) {
    cnt.textContent = processing;
    pill.style.display = processing > 0 ? '' : 'none';
  }
}

function updateTabBadges() {
  if (!ST.data) return;
  const filesBadge = document.getElementById('tab-badge-files');
  const workersBadge = document.getElementById('tab-badge-workers');
  if (filesBadge) filesBadge.textContent = (ST.data.files || []).length;
  if (workersBadge) workersBadge.textContent = (ST.data.workers || []).length;
}

function renderActiveTab() {
  const renders = {
    overview: renderOverview,
    files: renderFiles,
    stats: renderStats,
    workers: renderWorkers,
    master: renderScan,
    settings: renderSettings,
  };
  if (renders[ST.tab]) renders[ST.tab]();
}

// ── Overview tab ─────────────────────────────────────────────────────────────
function renderOverview() {
  const el = document.getElementById('tab-overview');
  if (!el) return;
  const data = ST.data || {};
  const stats = data.stats || {total:0,converted:0,pending:0,processing:0,error:0,duplicate:0,saved_bytes:0};
  const workers = data.workers || [];
  const activeWorkers = workers.filter(s => s.state === 'processing').length;
  const fc = data.file_counts || {};
  const activeTotal = (fc.pending||0) + (fc.assigned||0) + (fc.processing||0) + (fc.complete||0);
  const donePct = activeTotal ? Math.round(((fc.complete||0) / activeTotal) * 100) : 0;
  const statusChips = [
    { key:'scanning',   label:'Scanning',   color:'var(--text-dim)' },
    { key:'pending',    label:'Pending',    color:'var(--yellow)' },
    { key:'assigned',   label:'Assigned',   color:'var(--blue)' },
    { key:'processing', label:'Processing', color:'var(--blue)' },
    { key:'complete',   label:'Complete',   color:'var(--green)' },
    { key:'discarded',  label:'Discarded',  color:'var(--text-dim)' },
    { key:'cancelled',  label:'Cancelled',  color:'var(--text-dim)' },
    { key:'error',      label:'Error',      color:'var(--red)' },
    { key:'duplicate',  label:'Duplicate',  color:'var(--purple)' },
  ];

  el.innerHTML = `
    ${ST.demo ? `<div class="demo-banner">⚡ Demo mode — master unreachable. Showing last known data.</div>` : ''}

    <div class="stats-grid" style="margin-bottom:12px">
      <div class="stat-card">
        <div class="stat-label">Total Files</div>
        <div class="stat-value">${(stats.total || 0).toLocaleString()}</div>
        <div class="stat-sub">${donePct}% complete</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Space Saved</div>
        <div class="stat-value stat-accent">${fmtBytes(stats.saved_bytes)}</div>
        <div class="stat-sub">after compression</div>
      </div>
    </div>

    <div class="status-grid">
      ${statusChips.map(c => `
        <div class="status-chip" onclick="openStatusModal('${c.key}')">
          <div>
            <div class="status-chip-label">${c.label}</div>
            <div class="status-chip-count" style="color:${c.color}">${(fc[c.key] || 0).toLocaleString()}</div>
          </div>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-faint);flex-shrink:0"><path d="M9 18l6-6-6-6"/></svg>
        </div>`).join('')}
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-title">Overall Progress</div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-dim);margin-bottom:8px;font-family:'IBM Plex Mono',monospace">
        <span>${(stats.converted||0).toLocaleString()} converted</span>
        <span>${donePct}%</span>
      </div>
      <div class="progress-track" style="height:8px">
        <div class="progress-fill green" style="width:${donePct}%"></div>
      </div>
      <div style="display:flex;gap:16px;margin-top:10px;font-size:11px;flex-wrap:wrap">
        <span style="color:var(--green)">■ ${stats.converted||0} done</span>
        <span style="color:var(--yellow)">■ ${stats.pending||0} pending</span>
        <span style="color:var(--blue)">■ ${stats.processing||activeWorkers} processing</span>
        <span style="color:var(--red)">■ ${stats.error||0} error</span>
        <span style="color:var(--purple)">■ ${stats.duplicate||0} duplicate</span>
        <span style="color:var(--text-dim)">■ ${stats.cancelled||0} cancelled</span>
        <span style="color:var(--text-faint)">■ ${stats.discarded||0} discarded</span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Workers — ${workers.length} registered, ${activeWorkers} active</div>
      ${workers.length === 0 ? '<div class="empty">No workers registered</div>' : workers.map(s => {
        const dotColor = s.disk_full ? 'var(--red)' : s.state === 'processing' ? 'var(--blue)' : s.sleeping ? 'var(--text-faint)' : 'var(--green)';
        const p = s.progress;
        const pct = p ? Math.round(p.percent || 0) : 0;
        const statusStr = s.disk_full ? 'disk full' : s.sleeping ? 'sleeping' : s.drain ? 'draining' : s.state === 'processing' ? 'processing' : 'online';
        return `
        <div style="padding:10px 0;border-bottom:1px solid var(--border-subtle)">
          <div style="font-size:13px;font-weight:500;margin-bottom:5px">${esc(s.hostname)}</div>
          <div style="display:flex;align-items:center;gap:12px;min-width:0">
            <div style="width:8px;height:8px;border-radius:50%;background:${dotColor};flex-shrink:0"></div>
            <div style="font-size:11px;color:var(--text-faint);font-family:'IBM Plex Mono',monospace;white-space:nowrap">${s.unconfigured ? 'SETUP REQUIRED' : esc((s.encoder||'').toUpperCase())} · batch ${s.batch_size||1} · ${s.converted||0} converted</div>
            ${s.state === 'processing' && p ? `
            <div style="flex:1;min-width:0;display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;color:var(--text-dim);font-family:'IBM Plex Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1" title="${esc(s.current_file||'')}">${esc((s.current_file||'…').split('/').pop())}</span>
              <div class="progress-track" style="width:120px;flex-shrink:0"><div class="progress-fill" style="width:${pct}%"></div></div>
              <span style="font-size:11px;color:var(--text-dim);font-family:'IBM Plex Mono',monospace;white-space:nowrap;min-width:32px;text-align:right">${pct}%</span>
            </div>` : '<div style="flex:1"></div>'}
            ${badge(statusStr)}
            ${s.state === 'processing' ? `
            <div style="display:flex;gap:4px;flex-shrink:0">
              ${s.paused
                ? `<button class="btn btn-sm btn-primary" onclick="workerAction('${esc(s.host)}',${s.api_port},'resume')" title="Resume">${svgIcon('play',11)}</button>`
                : `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'pause')" title="Pause">${svgIcon('pause',11)}</button>`
              }
              <button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'drain')" title="Drain">⏭</button>
              <button class="btn btn-sm btn-danger" onclick="workerAction('${esc(s.host)}',${s.api_port},'stop')" title="Stop">${svgIcon('stop',11)}</button>
            </div>` : ''}
          </div>
        </div>`;
      }).join('')}
    </div>
  `;

  // Derive current_file from active record
  (ST.data && ST.data.workers || []).forEach(s => {
    s.current_file = s.current_file || (s.progress && s.progress.file_path) || null;
  });
}

// ── Files tab ────────────────────────────────────────────────────────────────
function stripPrefix(path) {
  const prefix = (ST.data && ST.data.scan && ST.data.scan.path) || '';
  if (prefix && path && path.startsWith(prefix)) return path.slice(prefix.length);
  return path;
}

function renderFiles() {
  const el = document.getElementById('tab-files');
  if (!el) return;
  const files = (ST.data && ST.data.files) || [];
  const workers = (ST.data && ST.data.workers) || [];

  const statuses = ['all','scanning','pending','assigned','processing','complete','error','duplicate','discarded','cancelled'];
  const counts = {};
  statuses.forEach(s => counts[s] = s === 'all' ? files.length : files.filter(f => f.status === s).length);

  const filtered = files.filter(f => {
    if (ST.fileFilters.size > 0 && !ST.fileFilters.has(f.status)) return false;
    if (ST.fileFiltersNot.has(f.status)) return false;
    if (ST.fileSearch) {
      const q = ST.fileSearch.toLowerCase();
      if (!(f.file_path||'').toLowerCase().includes(q) &&
          !(f.file_name||'').toLowerCase().includes(q) &&
          !(f.worker_id||'').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const visibleIds = filtered.slice(0, 100).map(f => f.id);
  const allSelected = visibleIds.length > 0 && visibleIds.every(id => ST.fileSelected.has(id));
  const someSelected = visibleIds.some(id => ST.fileSelected.has(id));
  const nSel = ST.fileSelected.size;

  const chipLabels = {
    all: 'All', scanning: 'Scanning', pending: 'Pending', assigned: 'Assigned',
    processing: 'Processing', complete: 'Done', error: 'Error',
    duplicate: 'Duplicate', discarded: 'Discarded', cancelled: 'Cancelled',
  };
  const visibleChips = ['all','scanning','pending','processing','complete','error','duplicate','discarded','cancelled'];

  el.innerHTML = `
    <div class="section-header">
      <div class="section-title">Files</div>
    </div>

    <div class="filter-bar">
      ${visibleChips.filter(s => counts[s] > 0 || s === 'all').map(s => {
        const isAll = s === 'all';
        const isActive = isAll ? (ST.fileFilters.size === 0 && ST.fileFiltersNot.size === 0) : ST.fileFilters.has(s);
        const isNot = ST.fileFiltersNot.has(s);
        const cls = isNot ? 'not' : isActive ? 'active' : '';
        return `<div class="filter-chip ${cls}" onclick="toggleFileFilter('${s}',event)">
          ${chipLabels[s]} <span style="opacity:0.6;font-size:11px">(${counts[s]})</span>
        </div>`;
      }).join('')}
      <div style="flex:1"></div>
      <input class="input" id="file-search-input" style="width:220px" placeholder="Search filename or worker…"
             value="${esc(ST.fileSearch)}"
             oninput="setFileSearch(this.value)">
    </div>

    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>${nSel > 0 ? `
          <tr style="height:38px;background:var(--accent-glow)">
            <th style="width:36px;padding:0 0 0 14px">
              <input type="checkbox" ${allSelected?'checked':''} onchange="toggleAllFiles(this)" style="accent-color:var(--accent)">
            </th>
            <th style="padding:0" colspan="6">
              <span style="font-size:13px;font-weight:500;color:var(--accent);margin-right:12px">${nSel} selected</span>
              <div class="dropdown" id="bulk-dropdown" style="display:inline-block">
                <button class="btn btn-sm" onclick="toggleBulkMenu(event)" style="display:inline-flex;align-items:center;gap:6px">
                  <span>Actions…</span>${svgIcon('chevronDown',12)}
                </button>
                ${ST.fileBulkOpen ? `
                <div class="dropdown-menu">
                  <div class="dropdown-item" onclick="bulkSetStatus('pending')">Set → Pending</div>
                  <div class="dropdown-item" onclick="bulkSetStatus('cancelled')">Set → Cancelled</div>
                  <div class="dropdown-item" onclick="bulkSetStatus('error')">Set → Error</div>
                  <div class="dropdown-item" onclick="bulkDelete()">Delete records</div>
                  ${workers.length > 0 ? `
                  <div class="dropdown-item dropdown-item-sub" style="display:flex;justify-content:space-between;align-items:center">
                    <span>Queue to…</span>${svgIcon('chevronRight',12)}
                    <div class="submenu">
                      ${workers.map(w => `<div class="dropdown-item" onclick="bulkQueue('${esc(w.config_id)}')">${esc(w.hostname)}</div>`).join('')}
                    </div>
                  </div>` : ''}
                </div>` : ''}
              </div>
            </th>
            <th style="padding:0 14px 0 0;text-align:right" colspan="2">
              <button class="btn btn-sm" onclick="clearSelection()">Clear</button>
            </th>
          </tr>` : `
          <tr style="height:38px">
            <th style="width:36px;padding-left:14px">
              <input type="checkbox" ${allSelected?'checked':''} onchange="toggleAllFiles(this)"
                     style="accent-color:var(--accent)">
            </th>
            <th>Path</th>
            <th>Status</th>
            <th>Worker</th>
            <th>Original</th>
            <th>Converted</th>
            <th>Saved</th>
            <th>Added</th>
            <th></th>
          </tr>`}
          </thead>
          <tbody>
            ${filtered.length === 0 ? `<tr><td colspan="9"><div class="empty">No files matching filter</div></td></tr>` :
              filtered.slice(0, 100).map(f => {
                const saved = (f.file_size && f.output_size) ? f.file_size - f.output_size : 0;
                const savedPct = f.file_size ? Math.round(saved / f.file_size * 100) : 0;
                const worker = workers.find(w => w.config_id === f.worker_id);
                const isSel = ST.fileSelected.has(f.id);
                return `<tr${isSel?' style="background:var(--accent-glow)"':''}>
                  <td style="padding-left:14px">
                    <input type="checkbox" ${isSel?'checked':''} value="${f.id}"
                           onchange="toggleFileSelect(${f.id})"
                           style="accent-color:var(--accent)">
                  </td>
                  <td><div class="path-cell" title="${esc(f.file_path)}">${esc(stripPrefix(f.file_path))}</div></td>
                  <td>${badge(f.status)}</td>
                  <td><span class="mono">${worker ? esc(worker.hostname) : '<span style="color:var(--text-faint)">—</span>'}</span></td>
                  <td><span class="mono">${fmtBytes(f.file_size)}</span></td>
                  <td><span class="mono">${f.status === 'complete' ? fmtBytes(f.output_size) : '—'}</span></td>
                  <td><span class="mono" style="color:${savedPct > 0 ? 'var(--green)' : 'var(--text-faint)'}">
                    ${f.status === 'complete' && savedPct > 0 ? `${savedPct}%` : '—'}
                  </span></td>
                  <td><span class="mono">${fmtDate(f.created_at)}</span></td>
                  <td>
                    <button class="btn btn-sm btn-danger" onclick="deleteFile(${f.id})" title="Delete record">
                      ${svgIcon('trash',12)}
                    </button>
                  </td>
                </tr>`;
              }).join('')
            }
          </tbody>
        </table>
      </div>
      ${filtered.length > 100 ? `<div style="padding:10px 16px;border-top:1px solid var(--border);font-size:12px;color:var(--text-faint)">Showing 100 of ${filtered.length} records</div>` : ''}
    </div>
  `;

  // Re-apply indeterminate state
  const hdr = el.querySelector('thead input[type="checkbox"]');
  if (hdr) hdr.indeterminate = someSelected && !allSelected;
}

function toggleFileFilter(s, event) {
  const alt = event && (event.altKey || event.ctrlKey);
  const shift = event && event.shiftKey;
  if (s === 'all') {
    ST.fileFilters.clear();
    ST.fileFiltersNot.clear();
  } else if (shift) {
    if (ST.fileFiltersNot.has(s)) { ST.fileFiltersNot.delete(s); }
    else { ST.fileFiltersNot.add(s); ST.fileFilters.delete(s); }
  } else if (alt) {
    if (ST.fileFilters.has(s)) { ST.fileFilters.delete(s); }
    else { ST.fileFilters.add(s); ST.fileFiltersNot.delete(s); }
  } else {
    if (ST.fileFilters.size > 1 && ST.fileFilters.has(s)) {
      ST.fileFilters.delete(s);
    } else {
      const wasOnly = ST.fileFilters.size === 1 && ST.fileFilters.has(s) && ST.fileFiltersNot.size === 0;
      ST.fileFilters.clear();
      ST.fileFiltersNot.clear();
      if (!wasOnly) ST.fileFilters.add(s);
    }
  }
  ST.fileSelected.clear();
  renderFiles();
}

function setFileSearch(q) {
  ST.fileSearch = q;
  ST.fileSelected.clear();
  renderFiles();
  const inp = document.getElementById('file-search-input');
  if (inp) { inp.focus(); inp.setSelectionRange(q.length, q.length); }
}

function toggleAllFiles(src) {
  const files = (ST.data && ST.data.files) || [];
  const filtered = files.filter(f => {
    if (ST.fileFilters.size > 0 && !ST.fileFilters.has(f.status)) return false;
    if (ST.fileFiltersNot.has(f.status)) return false;
    if (ST.fileSearch) {
      const q = ST.fileSearch.toLowerCase();
      if (!(f.file_path||'').toLowerCase().includes(q) && !(f.file_name||'').toLowerCase().includes(q)) return false;
    }
    return true;
  });
  const visibleIds = filtered.slice(0, 100).map(f => f.id);
  if (src.checked) visibleIds.forEach(id => ST.fileSelected.add(id));
  else ST.fileSelected.clear();
  renderFiles();
}

function toggleFileSelect(id) {
  if (ST.fileSelected.has(id)) ST.fileSelected.delete(id);
  else ST.fileSelected.add(id);
  renderFiles();
}

function clearSelection() {
  ST.fileSelected.clear();
  ST.fileBulkOpen = false;
  renderFiles();
}

function toggleBulkMenu(e) {
  e.stopPropagation();
  ST.fileBulkOpen = !ST.fileBulkOpen;
  renderFiles();
}

async function addFileFromInput() {
  const input = document.getElementById('add-path-input');
  if (!input || !input.value.trim()) return;
  const path = input.value.trim();
  if (ST.demo) { toast(`[Demo] Add: ${path}`, 'info'); input.value = ''; return; }
  try {
    const r = await fetch('/data/transfer', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({file_path: path}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('File added to queue', 'success');
    input.value = '';
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function deleteFile(id) {
  if (ST.demo) { toast('[Demo] Delete record', 'info'); return; }
  try {
    const r = await fetch('/data/files/delete', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ids: [id]}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Record deleted', 'success');
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function bulkSetStatus(status) {
  const ids = [...ST.fileSelected];
  if (!ids.length) return;
  ST.fileBulkOpen = false;
  if (ST.demo) { toast(`[Demo] Set ${ids.length} → ${status}`, 'info'); ST.fileSelected.clear(); renderFiles(); return; }
  const endpoint = status === 'pending' ? '/data/files/pending' : '/data/files/cancel';
  try {
    const r = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ids}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast(`${ids.length} records updated`, 'success');
    ST.fileSelected.clear();
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function bulkDelete() {
  const ids = [...ST.fileSelected];
  if (!ids.length) return;
  ST.fileBulkOpen = false;
  if (!confirm(`Delete ${ids.length} record(s)?`)) return;
  if (ST.demo) { toast(`[Demo] Delete ${ids.length} records`, 'info'); ST.fileSelected.clear(); renderFiles(); return; }
  try {
    const r = await fetch('/data/files/delete', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ids}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast(`${ids.length} records deleted`, 'success');
    ST.fileSelected.clear();
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function bulkQueue(workerConfigId) {
  const ids = [...ST.fileSelected];
  if (!ids.length) return;
  ST.fileBulkOpen = false;
  if (ST.demo) { toast(`[Demo] Queue ${ids.length} → ${workerConfigId}`, 'info'); ST.fileSelected.clear(); renderFiles(); return; }
  try {
    const r = await fetch('/data/files/assign', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ids, worker_config_id: workerConfigId}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`Queued ${res.assigned || ids.length} files`, 'success');
    ST.fileSelected.clear();
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ── Statistics tab ────────────────────────────────────────────────────────────
function renderStats() {
  const el = document.getElementById('tab-stats');
  if (!el) return;
  const data = ST.data || {};
  const stats = data.stats || {};
  const workers = data.workers || [];
  const ms = data.master_stats || {};
  const overall = ms.overall || {};
  const byEncoder = ms.by_encoder || {};
  const byResolution = ms.by_resolution || {};
  const byBitrateTier = ms.by_bitrate_tier || {};

  const total = stats.total || 1;
  const errorRate = total > 1 ? ((stats.error||0) / total * 100).toFixed(1) : '0.0';
  const avgRatio = overall.avg_compression_ratio
    ? Math.round((1 - overall.avg_compression_ratio) * 100)
    : 0;

  const segments = [
    {label:'Done',      value:stats.converted||0, color:'var(--green)'},
    {label:'Pending',   value:stats.pending||0,   color:'var(--yellow)'},
    {label:'Processing',value:stats.processing||0,color:'var(--blue)'},
    {label:'Cancelled', value:stats.cancelled||0, color:'var(--text-dim)'},
    {label:'Error',     value:stats.error||0,     color:'var(--red)'},
    {label:'Duplicate', value:stats.duplicate||0, color:'var(--purple)'},
    {label:'Discarded', value:stats.discarded||0, color:'var(--text-faint)'},
  ].filter(s => s.value > 0 || s.label === 'Done');

  el.innerHTML = `
    <div class="stats-grid" style="margin-bottom:20px">
      <div class="stat-card">
        <div class="stat-label">Total converted</div>
        <div class="stat-value stat-accent">${(stats.converted||0).toLocaleString()}</div>
        <div class="stat-sub">of ${(stats.total||0).toLocaleString()} files</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Space saved</div>
        <div class="stat-value stat-accent">${fmtBytes(stats.saved_bytes)}</div>
        <div class="stat-sub">avg ${avgRatio}% reduction</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Error rate</div>
        <div class="stat-value" style="color:${(stats.error||0) > 20 ? 'var(--red)' : 'var(--text)'}">
          ${errorRate}%
        </div>
        <div class="stat-sub">${stats.error||0} failed files</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active workers</div>
        <div class="stat-value">${workers.filter(s=>s.state==='processing').length}</div>
        <div class="stat-sub">of ${workers.length} registered</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg MB/s</div>
        <div class="stat-value">${overall.avg_mb_per_s != null ? overall.avg_mb_per_s : '—'}</div>
        <div class="stat-sub">input throughput</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg FPS</div>
        <div class="stat-value">${overall.avg_fps != null ? overall.avg_fps : '—'}</div>
        <div class="stat-sub">${overall.avg_speed != null ? overall.avg_speed + '× speed' : 'encode speed'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Library playtime</div>
        <div class="stat-value">${overall.total_duration_seconds != null ? fmtDuration(overall.total_duration_seconds) : '—'}</div>
        <div class="stat-sub">total source duration</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg source bitrate</div>
        <div class="stat-value">${overall.avg_bitrate_bps != null ? fmtBitrate(overall.avg_bitrate_bps) : '—'}</div>
        <div class="stat-sub">across library</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
      <div class="card">
        <div class="card-title">Status breakdown</div>
        ${segments.map(seg => `
        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px">
            <span style="color:${seg.color};font-weight:500">${seg.label}</span>
            <span style="font-family:'IBM Plex Mono',monospace;color:var(--text-dim)">${(seg.value).toLocaleString()}
              <span style="color:var(--text-faint)">${Math.round(seg.value/total*100)}%</span></span>
          </div>
          <div class="progress-track">
            <div style="height:100%;border-radius:2px;background:${seg.color};width:${Math.round(seg.value/total*100)}%;transition:width 0.4s ease"></div>
          </div>
        </div>`).join('')}
      </div>

      <div class="card">
        <div class="card-title">By encoder</div>
        ${Object.keys(byEncoder).length === 0
          ? '<div style="color:var(--text-faint);font-size:13px">No data</div>'
          : Object.entries(byEncoder).map(([codec, enc]) => {
              const totalConv = Object.values(byEncoder).reduce((s,e)=>s+(e.jobs||0),0) || 1;
              const pct = Math.round((enc.jobs||0)/totalConv*100);
              const dur = enc.avg_duration_seconds || 0;
              const durStr = dur >= 60
                ? `${Math.floor(dur/60)}m ${Math.round(dur%60)}s`
                : `${Math.round(dur)}s`;
              const savedPct = enc.total_input_bytes
                ? Math.round((enc.total_saved_bytes||0) / enc.total_input_bytes * 100)
                : 0;
              return `<div style="margin-bottom:16px">
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px">
                  <span style="font-family:'IBM Plex Mono',monospace;font-weight:500;color:var(--accent)">${esc(codec.toUpperCase())}</span>
                  <span style="font-family:'IBM Plex Mono',monospace;color:var(--text-dim)">${(enc.jobs||0).toLocaleString()} jobs <span style="color:var(--text-faint)">${pct}%</span></span>
                </div>
                <div class="progress-track" style="margin-bottom:10px">
                  <div style="height:100%;border-radius:2px;background:var(--accent);width:${pct}%;transition:width 0.4s ease"></div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px;font-size:11px;font-family:'IBM Plex Mono',monospace">
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Saved</div>
                    <div style="color:var(--green)">${fmtBytes(enc.total_saved_bytes)} <span style="color:var(--text-faint)">${savedPct}%</span></div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Avg time</div>
                    <div>${dur ? durStr : '—'}</div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Avg FPS</div>
                    <div>${enc.avg_fps != null ? enc.avg_fps : '—'}</div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Avg speed</div>
                    <div>${enc.avg_speed != null ? enc.avg_speed + '×' : '—'}</div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">MB/s</div>
                    <div>${enc.avg_mb_per_s != null ? enc.avg_mb_per_s : '—'}</div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Src bitrate</div>
                    <div>${enc.avg_src_bitrate_bps != null ? fmtBitrate(enc.avg_src_bitrate_bps) : '—'}</div>
                  </div>
                  <div style="background:var(--surface2);border-radius:6px;padding:6px 8px">
                    <div style="color:var(--text-faint);margin-bottom:2px">Input</div>
                    <div>${fmtBytes(enc.total_input_bytes)}</div>
                  </div>
                </div>
              </div>`;
            }).join('')
        }
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
      <div class="card">
        <div class="card-title">By resolution</div>
        ${Object.keys(byResolution).length === 0
          ? '<div style="color:var(--text-faint);font-size:13px">No data</div>'
          : (() => {
              const order = ['4K','1080p','720p','SD'];
              const resTotal = Object.values(byResolution).reduce((s,v)=>s+(v.count||0),0) || 1;
              return order.filter(k => byResolution[k]).map(k => {
                const r = byResolution[k];
                const pct = Math.round((r.count||0) / resTotal * 100);
                const dur = r.total_duration_seconds || 0;
                return `<div style="margin-bottom:14px">
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px">
                    <span style="font-weight:500">${esc(k)}</span>
                    <span style="font-family:'IBM Plex Mono',monospace;color:var(--text-dim)">${(r.count||0).toLocaleString()} <span style="color:var(--text-faint)">${pct}%</span></span>
                  </div>
                  <div class="progress-track" style="margin-bottom:8px">
                    <div style="height:100%;border-radius:2px;background:var(--blue);width:${pct}%;transition:width 0.4s ease"></div>
                  </div>
                  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font-size:11px;font-family:'IBM Plex Mono',monospace">
                    <div style="background:var(--surface2);border-radius:6px;padding:5px 8px">
                      <div style="color:var(--text-faint);margin-bottom:2px">Avg bitrate</div>
                      <div>${r.avg_bitrate_bps != null ? fmtBitrate(r.avg_bitrate_bps) : '—'}</div>
                    </div>
                    <div style="background:var(--surface2);border-radius:6px;padding:5px 8px">
                      <div style="color:var(--text-faint);margin-bottom:2px">Playtime</div>
                      <div>${dur ? fmtDuration(dur) : '—'}</div>
                    </div>
                    <div style="background:var(--surface2);border-radius:6px;padding:5px 8px">
                      <div style="color:var(--text-faint);margin-bottom:2px">Saved</div>
                      <div style="color:var(--green)">${r.total_saved_bytes ? fmtBytes(r.total_saved_bytes) : '—'}</div>
                    </div>
                  </div>
                </div>`;
              }).join('');
            })()
        }
      </div>

      <div class="card">
        <div class="card-title">By source bitrate</div>
        ${Object.keys(byBitrateTier).length === 0
          ? '<div style="color:var(--text-faint);font-size:13px">No data</div>'
          : (() => {
              const order = ['<5 Mbps','5–15 Mbps','15–40 Mbps','40+ Mbps'];
              const brTotal = Object.values(byBitrateTier).reduce((s,v)=>s+(v.count||0),0) || 1;
              return order.filter(k => byBitrateTier[k]).map(k => {
                const b = byBitrateTier[k];
                const pct = Math.round((b.count||0) / brTotal * 100);
                return `<div style="margin-bottom:14px">
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px">
                    <span style="font-weight:500">${esc(k)}</span>
                    <span style="font-family:'IBM Plex Mono',monospace;color:var(--text-dim)">${(b.count||0).toLocaleString()} <span style="color:var(--text-faint)">${pct}%</span></span>
                  </div>
                  <div class="progress-track" style="margin-bottom:8px">
                    <div style="height:100%;border-radius:2px;background:var(--purple);width:${pct}%;transition:width 0.4s ease"></div>
                  </div>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;font-family:'IBM Plex Mono',monospace">
                    <div style="background:var(--surface2);border-radius:6px;padding:5px 8px">
                      <div style="color:var(--text-faint);margin-bottom:2px">Space saved</div>
                      <div style="color:var(--green)">${b.total_saved_bytes ? fmtBytes(b.total_saved_bytes) : '—'}</div>
                    </div>
                    <div style="background:var(--surface2);border-radius:6px;padding:5px 8px">
                      <div style="color:var(--text-faint);margin-bottom:2px">Share</div>
                      <div>${pct}% of library</div>
                    </div>
                  </div>
                </div>`;
              }).join('');
            })()
        }
      </div>
    </div>

    <div class="card" style="padding:0;overflow:hidden">
      <div style="padding:16px 20px 12px;border-bottom:1px solid var(--border)">
        <div class="card-title" style="margin-bottom:0">Per-worker statistics</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Worker</th><th>Encoder</th><th>Converted</th><th>Errors</th>
            <th>Input</th><th>Output</th><th>Saved</th><th>MB/s</th>
          </tr></thead>
          <tbody>
            ${workers.length === 0
              ? '<tr><td colspan="8"><div class="empty">No worker statistics available</div></td></tr>'
              : workers.map(s => {
                  const se = (ms.by_worker||[]).find(b=>b.worker_id===s.config_id) || {};
                  const inp = se.total_input_bytes || 0;
                  const out = se.total_output_bytes || 0;
                  const saved = inp - out;
                  const savedPct = inp > 0 ? Math.round(saved/inp*100) : 0;
                  return `<tr>
                    <td style="font-weight:500">${esc(s.hostname)}</td>
                    <td><span class="mono" style="color:var(--accent)">${s.unconfigured ? 'SETUP REQUIRED' : esc((s.encoder||'').toUpperCase())}</span></td>
                    <td><span class="mono">${(s.converted||0).toLocaleString()}</span></td>
                    <td><span class="mono" style="color:${(s.errors||0)>0?'var(--red)':'var(--text-faint)'}">${s.errors||0}</span></td>
                    <td><span class="mono">${fmtBytes(inp||null)}</span></td>
                    <td><span class="mono">${fmtBytes(out||null)}</span></td>
                    <td><span class="mono" style="color:var(--green)">${savedPct > 0 ? `${savedPct}% (${fmtBytes(saved)})` : '—'}</span></td>
                    <td><span class="mono">${se.avg_mb_per_s != null ? se.avg_mb_per_s : '—'}</span></td>
                  </tr>`;
                }).join('')
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ── Workers (workers) tab ──────────────────────────────────────────────────────
function renderWorkers() {
  const el = document.getElementById('tab-workers');
  if (!el) return;
  const workers = (ST.data && ST.data.workers) || [];

  el.innerHTML = `
    <div class="section-header">
      <div class="section-title">Workers — ${workers.length}</div>
    </div>
    <div class="workers-grid">
      ${workers.length === 0
        ? '<div class="card"><div class="empty">No workers registered</div></div>'
        : workers.map(s => renderWorkerCard(s)).join('')
      }
    </div>
  `;
}

function renderWorkerCard(s) {
  const isProcessing = s.state === 'processing';
  const isSleeping = s.sleeping;
  const isPaused = s.paused;
  const showSettings = !!ST.workerSettingsOpen[s.config_id];
  const p = s.progress;
  const pct = p ? Math.round(p.percent || 0) : 0;
  const isDiskFull = !!s.disk_full;
  const statusStr = isDiskFull ? 'disk full' : isSleeping ? 'sleeping' : s.drain ? 'draining' : isProcessing ? (isPaused ? 'paused' : 'processing') : (s.state === 'unreachable' ? 'offline' : 'online');

  const encoders = s.available_encoders || ['libx265'];
  const labels = s.encoder_labels || {};
  const encOptions = encoders.map(e => `<option value="${esc(e)}" ${s.encoder===e?'selected':''}>${esc(labels[e]||e)}</option>`).join('');
  const inlineEdit = ST.workerInlineEdit[s.config_id] || null;
  const showCmd = !!ST.workerCmdOpen[s.config_id];
  const currentFile = s.current_file || '';
  const currentFileName = currentFile ? currentFile.split('/').pop() : '…';

  return `
  <div class="worker-card ${isProcessing?'active':''}">
    <div class="worker-header">
      <div class="worker-header-info">
        <div class="worker-name">${esc(s.hostname)}</div>
        <div class="worker-meta">${esc(s.config_id)} · ${esc(s.url)}</div>
      </div>
      ${badge(statusStr)}
    </div>

    ${isProcessing && p ? `
    <div class="worker-progress">
      <div class="worker-progress-label">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1" title="${esc(currentFile)}">${esc(currentFileName)}</span>
        <span style="white-space:nowrap;margin-left:8px;min-width:140px;text-align:right">${pct}%${p.fps ? ` · ${p.fps} fps` : ''}${p.speed ? ` · ${p.speed}×` : ''}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-faint);margin-top:4px;font-family:'IBM Plex Mono',monospace">
        <span>${p.eta_seconds != null ? `ETA ${fmtEta(p.eta_seconds)}` : '—'}</span>
        <span>Queue: ${s.queued||0}</span>
      </div>
      ${p.current_size_bytes != null ? `
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-faint);margin-top:3px;font-family:'IBM Plex Mono',monospace">
        <span>${fmtBytes(p.current_size_bytes)}${p.projected_size_bytes != null ? ` → ${fmtBytes(p.projected_size_bytes)}` : ''}</span>
        ${p.bitrate ? `<span>${esc(p.bitrate)}</span>` : ''}
      </div>` : ''}
    </div>` : ''}

    <div class="worker-stats">
      <div class="worker-stat">
        <div class="worker-stat-label">Converted</div>
        <div class="worker-stat-value">${s.converted||0}</div>
      </div>
      <div class="worker-stat">
        <div class="worker-stat-label">Errors</div>
        <div class="worker-stat-value" style="color:${(s.errors||0)>0?'var(--red)':'inherit'}">${s.errors||0}</div>
      </div>
      <div class="worker-stat" style="cursor:pointer" onclick="startInlineEdit('${esc(s.config_id)}','encoder')">
        <div class="worker-stat-label">Encoder</div>
        ${inlineEdit === 'encoder' ? `
        <div style="display:flex;gap:4px;align-items:center" onclick="event.stopPropagation()">
          <select class="select" style="font-size:11px;padding:2px 4px;height:24px" id="inline-enc-${esc(s.config_id)}"
                  onkeydown="if(event.key==='Escape')cancelInlineEdit('${esc(s.config_id)}')">${encOptions}</select>
          <button class="btn btn-primary btn-sm" onclick="saveInlineEdit('${esc(s.config_id)}','${esc(s.host)}',${s.api_port})">✓</button>
          <button class="btn btn-sm" onclick="cancelInlineEdit('${esc(s.config_id)}')">✕</button>
        </div>` : `<div class="worker-stat-value" style="font-size:12px">${s.unconfigured ? 'SETUP REQUIRED' : esc((s.encoder||'').toUpperCase())}</div>`}
      </div>
      <div class="worker-stat" style="cursor:pointer" onclick="startInlineEdit('${esc(s.config_id)}','batch')">
        <div class="worker-stat-label">Batch</div>
        ${inlineEdit === 'batch' ? `
        <div style="display:flex;gap:4px;align-items:center" onclick="event.stopPropagation()">
          <input class="input" type="number" min="1" max="16" value="${s.batch_size||1}" id="inline-batch-${esc(s.config_id)}"
                 style="width:56px;font-size:11px;padding:2px 4px;height:24px"
                 onkeydown="if(event.key==='Enter')saveInlineEdit('${esc(s.config_id)}','${esc(s.host)}',${s.api_port});if(event.key==='Escape')cancelInlineEdit('${esc(s.config_id)}')">
          <button class="btn btn-primary btn-sm" onclick="saveInlineEdit('${esc(s.config_id)}','${esc(s.host)}',${s.api_port})">✓</button>
          <button class="btn btn-sm" onclick="cancelInlineEdit('${esc(s.config_id)}')">✕</button>
        </div>` : `<div class="worker-stat-value">${s.batch_size||1}</div>`}
      </div>
    </div>

    <div class="worker-controls">
      ${isProcessing ? `
        <button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'pause')">${svgIcon('pause',12)} Pause</button>
        <button class="btn btn-sm btn-danger" onclick="workerAction('${esc(s.host)}',${s.api_port},'stop')">${svgIcon('stop',12)} Stop</button>
        <button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'drain')">Drain</button>
      ` : ''}
      ${isPaused ? `
        <button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'resume')">${svgIcon('play',12)} Resume</button>
      ` : ''}
      ${isSleeping
        ? `<button class="btn btn-primary btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'wake')">${svgIcon('play',12)} Wake</button>`
        : `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'sleep')">${svgIcon('moon',12)} Sleep</button>`
      }
      <button class="btn btn-sm" onclick="toggleWorkerSettings('${esc(s.config_id)}')">${svgIcon('settings',12)} Settings</button>
      ${s.current_cmd ? `<button class="btn btn-sm ${showCmd?'btn-primary':''}" onclick="toggleWorkerCmd('${esc(s.config_id)}')">CMD</button>` : ''}
      <button class="btn btn-sm btn-danger" style="margin-left:auto" onclick="deregisterWorker('${esc(s.config_id)}')" title="Deregister">${svgIcon('trash',12)}</button>
    </div>

    ${showCmd && s.current_cmd ? `
    <div style="margin-top:8px;padding:8px;background:var(--bg-subtle);border-radius:6px;font-size:10px;font-family:'IBM Plex Mono',monospace;color:var(--text-faint);word-break:break-all;white-space:pre-wrap">${esc(s.current_cmd)}</div>` : ''}

    ${showSettings ? `
    <div class="worker-settings-panel">
      <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-faint);margin-bottom:8px">Running config</div>
      <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:11px;margin-bottom:12px;font-family:'IBM Plex Mono',monospace">
        <span style="color:var(--text-faint)">Encoder</span><span>${esc(labels[s.encoder]||s.encoder||'—')}</span>
        <span style="color:var(--text-faint)">Batch</span><span>${s.batch_size||1}</span>
        <span style="color:var(--text-faint)">Replace orig.</span><span>${s.replace_original?'yes':'no'}</span>
        <span style="color:var(--text-faint)">Queue</span><span>${s.queued||0}</span>
        <span style="color:var(--text-faint)">Master</span><span>${esc(s.url||'—')}</span>
      </div>
      <div style="border-top:1px solid var(--border-subtle);margin:0 0 12px"></div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <label class="label">Replace original</label>
        <div class="toggle ${s.replace_original?'on':''}" id="repl-${esc(s.config_id)}"
             onclick="this.classList.toggle('on')"></div>
      </div>
      <button class="btn btn-primary btn-sm" style="margin-top:8px"
              onclick="saveWorkerSettings('${esc(s.config_id)}','${esc(s.host)}',${s.api_port})">
        Save settings
      </button>
    </div>` : ''}
  </div>`;
}

function fmtEta(seconds) {
  if (seconds == null) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function toggleWorkerSettings(configId) {
  ST.workerSettingsOpen[configId] = !ST.workerSettingsOpen[configId];
  renderWorkers();
}

function toggleWorkerCmd(configId) {
  ST.workerCmdOpen[configId] = !ST.workerCmdOpen[configId];
  renderWorkers();
}

function startInlineEdit(configId, field) {
  ST.workerInlineEdit[configId] = field;
  renderWorkers();
  const id = field === 'encoder' ? `inline-enc-${configId}` : `inline-batch-${configId}`;
  const el = document.getElementById(id);
  if (el) el.focus();
}

function cancelInlineEdit(configId) {
  ST.workerInlineEdit[configId] = null;
  renderWorkers();
}

async function saveInlineEdit(configId, host, port) {
  const workers = (ST.data && ST.data.workers) || [];
  const w = workers.find(x => x.config_id === configId);
  if (!w) return;
  const encEl = document.getElementById(`inline-enc-${configId}`);
  const batchEl = document.getElementById(`inline-batch-${configId}`);
  const encoder = encEl ? encEl.value : w.encoder;
  const batch_size = batchEl ? parseInt(batchEl.value, 10) : (w.batch_size || 1);
  const payload = { host, port, encoder, batch_size, replace_original: w.replace_original };
  if (ST.demo) { toast('[Demo] Settings saved', 'info'); return; }
  try {
    const r = await fetch('/data/worker/encoder', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Saved', 'success');
    ST.workerInlineEdit[configId] = null;
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function workerAction(host, port, action) {
  if (ST.demo) { toast(`[Demo] ${action} → ${host}:${port}`, 'info'); return; }
  try {
    const r = await fetch('/data/worker/action', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port, action}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast(`${action} sent`, 'success');
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function saveWorkerSettings(configId, host, port) {
  const repl = document.getElementById(`repl-${configId}`);
  const workers = (ST.data && ST.data.workers) || [];
  const w = workers.find(x => x.config_id === configId);
  if (!w) return;
  const payload = {
    host, port,
    encoder: w.encoder,
    batch_size: w.batch_size || 1,
    replace_original: repl ? repl.classList.contains('on') : w.replace_original,
  };
  if (ST.demo) { toast('[Demo] Settings saved', 'info'); return; }
  try {
    const r = await fetch('/data/worker/encoder', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Settings saved', 'success');
    ST.workerSettingsOpen[configId] = false;
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function registerWorker() {
  const id = document.getElementById('reg-id');
  const url = document.getElementById('reg-url');
  if (!id || !url || !id.value.trim() || !url.value.trim()) return;
  if (ST.demo) { toast('[Demo] Register worker', 'info'); return; }
  try {
    const r = await fetch('/data/workers/register', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({id: id.value.trim(), url: url.value.trim()}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Worker registered', 'success');
    id.value = ''; url.value = '';
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function deregisterWorker(configId) {
  if (!confirm(`Deregister worker ${configId}?`)) return;
  if (ST.demo) { toast('[Demo] Deregister worker', 'info'); return; }
  try {
    const r = await fetch(`/data/workers/${encodeURIComponent(configId)}`, {method: 'DELETE'});
    if (!r.ok) throw new Error(await r.text());
    toast('Worker deregistered', 'success');
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ── Scan tab ─────────────────────────────────────────────────────────────────
function renderScan() {
  const el = document.getElementById('tab-master');
  if (!el) return;
  const data = ST.data || {};
  const scan = data.scan || {running: false};
  const running = scan.running;
  const scanned = scan.scanned || 0;
  const total = scan.total || 0;
  const found = scan.found || 0;
  const scanPct = total > 0 ? Math.round(scanned / total * 100) : 0;

  el.innerHTML = `
    <div style="max-width:720px">
      <div class="scan-status-bar">
        <div class="scan-indicator ${running?'scanning':''}"></div>
        <div class="scan-info">
          <div class="scan-title">${running ? 'Scan in progress…' : 'Scanner idle'}</div>
          <div class="scan-sub">
            ${running
              ? `${scanned.toLocaleString()} / ${total.toLocaleString()} scanned · ${found} new files found`
              : scan.path ? `Path: ${esc(scan.path)}` : 'No scan running'
            }
          </div>
        </div>
      </div>

      ${running ? `
      <div style="margin-bottom:20px">
        <div class="progress-track" style="height:6px">
          <div class="progress-fill" style="width:${scanPct}%"></div>
        </div>
      </div>` : ''}

      <div class="card">
        <div class="card-title">Periodic Scan Settings</div>
        <div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable periodic scanning</strong>
              <p>Automatically scan for new files on schedule</p>
            </div>
            <div class="toggle ${ST.scanEnabled?'on':''}" id="scan-enabled-toggle"
                 onclick="ST.scanEnabled=!ST.scanEnabled;this.classList.toggle('on')"></div>
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Scan interval</strong>
              <p>How often to run a background scan</p>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <input class="input" type="number" min="1" max="10080" value="${ST.scanInterval}"
                     id="scan-interval-input" style="width:80px"
                     oninput="ST.scanInterval=+this.value">
              <span style="font-size:13px;color:var(--text-dim)">minutes</span>
            </div>
          </div>
        </div>
        <div style="margin-top:16px">
          <button class="btn btn-primary" onclick="saveScanSettings()">Save settings</button>
        </div>
      </div>
    </div>
  `;
}

async function scanStart() {
  if (ST.demo) { toast('[Demo] Scan started', 'info'); return; }
  try {
    const r = await fetch('/data/scan/start', {method:'POST'});
    if (!r.ok) throw new Error(await r.text());
    toast('Scan started', 'success');
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function scanStop() {
  if (ST.demo) { toast('[Demo] Scan stopped', 'info'); return; }
  try {
    const r = await fetch('/data/scan/stop', {method:'POST'});
    if (!r.ok) throw new Error(await r.text());
    toast('Scan stopped', 'info');
    fetchAll();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function saveScanSettings() {
  if (ST.demo) { toast('[Demo] Settings saved', 'success'); return; }
  try {
    const r = await fetch('/data/scan/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({enabled: ST.scanEnabled, interval_minutes: ST.scanInterval}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Scan settings saved', 'success');
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ── Settings tab ──────────────────────────────────────────────────────────────
function renderSettings() {
  const el = document.getElementById('tab-settings');
  if (!el) return;

  el.innerHTML = `
    <div style="max-width:600px">
      <div class="card">
        <div class="card-title">Connection</div>
        <div class="settings-row">
          <div class="settings-label">
            <strong>Poll interval</strong>
            <p>How often the UI fetches new data</p>
          </div>
          <select class="select" onchange="setPollInterval(+this.value)" style="width:auto">
            <option value="1000" ${ST.pollInterval===1000?'selected':''}>1 second</option>
            <option value="3000" ${ST.pollInterval===3000?'selected':''}>3 seconds</option>
            <option value="5000" ${ST.pollInterval===5000?'selected':''}>5 seconds</option>
            <option value="10000" ${ST.pollInterval===10000?'selected':''}>10 seconds</option>
            <option value="0" ${ST.pollInterval===0?'selected':''}>Manual only</option>
          </select>
        </div>
        <div class="settings-row">
          <div class="settings-label">
            <strong>Workers tab poll interval</strong>
            <p>How often worker cards refresh when on the Workers tab</p>
          </div>
          <select class="select" onchange="setWorkerPollInterval(+this.value)" style="width:auto">
            <option value="500"  ${ST.workerPollInterval===500 ?'selected':''}>0.5 seconds</option>
            <option value="1000" ${ST.workerPollInterval===1000?'selected':''}>1 second</option>
            <option value="2000" ${ST.workerPollInterval===2000?'selected':''}>2 seconds</option>
            <option value="3000" ${ST.workerPollInterval===3000?'selected':''}>3 seconds</option>
          </select>
        </div>
      </div>

    </div>
  `;
}

function setPollInterval(ms) {
  ST.pollInterval = ms;
  clearTimeout(ST._pollTimer);
  const interval = ST.tab === 'workers' ? ST.workerPollInterval : ms;
  if (interval > 0) ST._pollTimer = setTimeout(fetchAll, interval);
}

function setWorkerPollInterval(ms) {
  ST.workerPollInterval = ms;
  if (ST.tab === 'workers') {
    clearTimeout(ST._pollTimer);
    if (ms > 0) ST._pollTimer = setTimeout(fetchAll, ms);
  }
}

// ── Toast ────────────────────────────────────────────────────────────────────
function openStatusModal(status) {
  ST.modalStatus = status;
  ST.modalSelected.clear();
  ST.modalBulkOpen = false;
  document.getElementById('status-modal-backdrop').style.display = 'flex';
  renderStatusModal();
}

function closeStatusModal() {
  document.getElementById('status-modal-backdrop').style.display = 'none';
  ST.modalStatus = null;
  ST.modalSelected.clear();
  ST.modalBulkOpen = false;
}

function renderStatusModal() {
  if (!ST.modalStatus) return;
  const status = ST.modalStatus;
  const files = (ST.data && ST.data.files) || [];
  const workers = (ST.data && ST.data.workers) || [];
  const filtered = status === 'all' ? files : files.filter(f => f.status === status);
  const labels = {
    all:'All Files', pending:'Pending', assigned:'Assigned', processing:'Processing',
    complete:'Complete', discarded:'Discarded', cancelled:'Cancelled', error:'Error', duplicate:'Duplicate',
  };
  const nSel = ST.modalSelected.size;
  const allSelected = filtered.length > 0 && filtered.every(f => ST.modalSelected.has(f.id));

  document.getElementById('status-modal-title').textContent =
    `${labels[status] || status} — ${filtered.length} file${filtered.length !== 1 ? 's' : ''}`;

  const body = document.getElementById('status-modal-body');

  const thead = nSel > 0 ? `
      <thead><tr style="height:36px;font-size:11px;color:var(--text-dim);border-bottom:1px solid var(--border-subtle);background:var(--accent-glow)">
        <th style="width:36px;padding:0 0 0 14px;font-weight:500">
          <input type="checkbox" ${allSelected?'checked':''} onchange="toggleAllModal(this)" style="accent-color:var(--accent)">
        </th>
        <th style="padding:0;font-weight:500;text-align:left" colspan="2">
          <span style="color:var(--accent);margin-right:12px">${nSel} selected</span>
          <div class="dropdown" id="modal-bulk-dropdown" style="display:inline-block">
            <button class="btn btn-sm" onclick="toggleModalBulkMenu(event)"
                    style="display:inline-flex;align-items:center;gap:6px">
              <span>Actions…</span>${svgIcon('chevronDown',12)}
            </button>
            ${ST.modalBulkOpen ? `
            <div class="dropdown-menu">
              <div class="dropdown-item" onclick="modalBulkSetStatus('pending')">Set → Pending</div>
              <div class="dropdown-item" onclick="modalBulkSetStatus('cancelled')">Set → Cancelled</div>
              <div class="dropdown-item" onclick="modalBulkDelete()">Delete records</div>
              ${workers.length > 0 ? `
              <div class="dropdown-item dropdown-item-sub" style="display:flex;justify-content:space-between;align-items:center">
                <span>Queue to…</span>${svgIcon('chevronRight',12)}
                <div class="submenu">
                  ${workers.map(w => `<div class="dropdown-item" onclick="modalBulkQueue('${esc(w.config_id)}')">${esc(w.hostname)}</div>`).join('')}
                </div>
              </div>` : ''}
            </div>` : ''}
          </div>
        </th>
        <th style="padding:0 14px 0 0;text-align:right">
          <button class="btn btn-sm" onclick="ST.modalSelected.clear();ST.modalBulkOpen=false;renderStatusModal()">Clear</button>
        </th>
      </tr></thead>` : `
      <thead><tr style="height:36px;font-size:11px;color:var(--text-dim);border-bottom:1px solid var(--border-subtle)">
        <th style="width:36px;padding:0 0 0 14px;font-weight:500">
          <input type="checkbox" ${allSelected?'checked':''} onchange="toggleAllModal(this)" style="accent-color:var(--accent)">
        </th>
        <th style="padding:0 12px 0 0;font-weight:500;text-align:left">Path</th>
        <th style="padding:0 14px 0 0;font-weight:500;text-align:left;white-space:nowrap">Worker</th>
        <th style="padding:0 14px 0 0;font-weight:500;text-align:right;white-space:nowrap">Size</th>
      </tr></thead>`;

  if (filtered.length === 0) {
    body.innerHTML = `<table style="width:100%;border-collapse:collapse">${thead}<tbody><tr><td colspan="4"><div class="modal-empty">No files with this status.</div></td></tr></tbody></table>`;
    return;
  }

  body.innerHTML = `
    <table style="width:100%;border-collapse:collapse">
      ${thead}
      <tbody>
        ${filtered.map(f => {
          const isSel = ST.modalSelected.has(f.id);
          const worker = workers.find(w => w.config_id === f.worker_id);
          return `<tr style="${isSel?'background:var(--accent-glow)':''};font-size:12px;border-bottom:1px solid var(--border-subtle)" onmouseenter="this.style.background='${isSel?'var(--accent-glow)':'var(--surface2)'}'" onmouseleave="this.style.background='${isSel?'var(--accent-glow)':''}'">
            <td style="padding:7px 0 7px 14px">
              <input type="checkbox" ${isSel?'checked':''} onchange="toggleModalFile(${f.id})" style="accent-color:var(--accent)">
            </td>
            <td style="padding:7px 12px 7px 0;font-family:'IBM Plex Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:400px" title="${esc(f.file_path)}">${esc(stripPrefix(f.file_path))}</td>
            <td style="padding:7px 14px 7px 0;font-family:'IBM Plex Mono',monospace;color:var(--accent);white-space:nowrap">${worker ? esc(worker.hostname) : '<span style="color:var(--text-faint)">—</span>'}</td>
            <td style="padding:7px 14px 7px 0;font-family:'IBM Plex Mono',monospace;text-align:right;white-space:nowrap;color:var(--text-dim)">${fmtBytes(f.file_size)}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

function toggleModalFile(id) {
  if (ST.modalSelected.has(id)) ST.modalSelected.delete(id);
  else ST.modalSelected.add(id);
  renderStatusModal();
}

function toggleAllModal(src) {
  const files = (ST.data && ST.data.files) || [];
  const filtered = ST.modalStatus === 'all' ? files : files.filter(f => f.status === ST.modalStatus);
  if (src.checked) filtered.forEach(f => ST.modalSelected.add(f.id));
  else ST.modalSelected.clear();
  renderStatusModal();
}

function toggleModalBulkMenu(e) {
  e.stopPropagation();
  ST.modalBulkOpen = !ST.modalBulkOpen;
  renderStatusModal();
}

async function modalBulkSetStatus(status) {
  const ids = [...ST.modalSelected];
  if (!ids.length) return;
  ST.modalBulkOpen = false;
  const endpoint = status === 'pending' ? '/data/files/pending' : '/data/files/cancel';
  try {
    const r = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids}) });
    if (!r.ok) throw new Error(await r.text());
    toast(`${ids.length} records updated`, 'success');
    ST.modalSelected.clear();
    await fetchAll();
    renderStatusModal();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function modalBulkDelete() {
  const ids = [...ST.modalSelected];
  if (!ids.length) return;
  ST.modalBulkOpen = false;
  if (!confirm(`Delete ${ids.length} record(s)?`)) return;
  try {
    const r = await fetch('/data/files/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids}) });
    if (!r.ok) throw new Error(await r.text());
    toast(`${ids.length} records deleted`, 'success');
    ST.modalSelected.clear();
    await fetchAll();
    renderStatusModal();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function modalBulkQueue(workerConfigId) {
  const ids = [...ST.modalSelected];
  if (!ids.length) return;
  ST.modalBulkOpen = false;
  try {
    const r = await fetch('/data/files/assign', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids, worker_config_id: workerConfigId}) });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`Queued ${res.assigned || ids.length} files`, 'success');
    ST.modalSelected.clear();
    await fetchAll();
    renderStatusModal();
  } catch(e) { toast(`Failed: ${e.message}`, 'error'); }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeStatusModal(); });

function toast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `toast ${type}`;
  div.textContent = msg;
  container.appendChild(div);
  setTimeout(() => div.remove(), 3500);
}
