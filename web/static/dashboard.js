// ── Helpers ─────────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (b == null || b === 0) return '—';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0;
  while (b >= 1024 && i < 4) { b /= 1024; i++; }
  return `${b.toFixed(1)} ${u[i]}`;
}

function fmtResolution(w, h) {
  if (!w || !h) return '—';
  if (h >= 3240) return '8K';
  if (h >= 1620) return '4K';
  if (h >= 900)  return '1080p';
  if (h >= 600)  return '720p';
  return 'SD';
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
    sleeping:'badge-sleeping', paused:'badge-paused', draining:'badge-draining', online:'badge-online', offline:'badge-offline',
    'disk full':'badge-error', 'setup required':'badge-pending',
    user:'badge-cancelled', auto:'badge-error',
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
  filePage: 0,
  fileSort: {col: 'created_at', dir: 'desc'},
  // modal
  modalStatus: null,
  modalSelected: new Set(),
  modalBulkOpen: false,
  modalPage: 0,
  modalSort: {col: 'created_at', dir: 'desc'},
  // workers tab
  workerSettingsOpen: {},   // configId → bool
  workerCmdOpen: {},        // configId → bool
  workerExpanded: new Set(), // configIds that are expanded in overview
  modalDiscardFilter: new Set(),
  modalDiscardFilterNot: new Set(),
  modalCancelFilter: new Set(),
  modalCancelFilterNot: new Set(),
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
  const cfg = (ST.data && ST.data.master_config) || {};
  const values = cfg.values || {};
  const noPrefix = !values.path_prefix;
  if (scan.running) {
    btn.textContent = '⏹ Stop scan';
    btn.className = 'btn btn-sm btn-danger';
    btn.style.cssText = 'font-size:11px;padding:3px 10px;height:26px';
    btn.disabled = false;
    btn.title = '';
  } else {
    btn.innerHTML = '▶ Scan';
    btn.className = 'btn btn-sm btn-primary';
    btn.style.cssText = 'font-size:11px;padding:3px 10px;height:26px';
    btn.disabled = noPrefix;
    btn.title = noPrefix ? 'Set master.paths.prefix to enable scanning' : '';
    if (noPrefix) btn.style.cssText += ';opacity:0.5;cursor:not-allowed';
  }
}

function topbarScanClick() {
  const scan = (ST.data && ST.data.scan) || {};
  const cfg = (ST.data && ST.data.master_config) || {};
  const values = cfg.values || {};
  if (scan.running) { scanStop(); return; }
  if (!values.path_prefix) { toast('Set master.paths.prefix to enable scanning', 'error'); return; }
  scanStart();
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
  const remaining = (fc.pending||0) + (fc.assigned||0) + (fc.processing||0);
  const availableWorkers = workers.filter(w => !w.sleeping && !w.unconfigured && w.state !== 'unreachable');
  const totalRate = availableWorkers.reduce((sum, w) => w.avg_duration_s > 0 ? sum + 1 / w.avg_duration_s : sum, 0);
  const etaSecs = (remaining > 0 && totalRate > 0) ? Math.round(remaining / totalRate) : null;

  // Projected savings: per-resolution-tier compression ratio from completed files
  const files = data.files || [];
  const tierOf = h => !h ? null : h >= 3240 ? '8k' : h >= 1620 ? '4k' : h >= 900 ? '1080p' : h >= 600 ? '720p' : 'sd';
  const tierStats = {};
  for (const f of files) {
    if (f.status !== 'complete' || !f.file_size || !f.output_size || !f.height) continue;
    const t = tierOf(f.height);
    if (!t) continue;
    if (!tierStats[t]) tierStats[t] = { totalIn: 0, totalOut: 0, n: 0 };
    tierStats[t].totalIn  += f.file_size;
    tierStats[t].totalOut += f.output_size;
    tierStats[t].n++;
  }
  let projSavedBytes = 0, projTotalSamples = 0, projTotalFiles = 0, projLowConf = false;
  for (const f of files) {
    if (f.status !== 'pending' && f.status !== 'assigned') continue;
    if (!f.file_size || !f.height) continue;
    const t = tierOf(f.height);
    const ts = t && tierStats[t];
    if (!ts || ts.n === 0) continue;
    const ratio = ts.totalOut / ts.totalIn;
    projSavedBytes += f.file_size * (1 - ratio);
    projTotalSamples += ts.n;
    projTotalFiles++;
    if (ts.n < 10) projLowConf = true;
  }
  const avgSamples = projTotalFiles > 0 ? Math.round(projTotalSamples / projTotalFiles) : 0;

  const statusChips = [
    { key:'scanning',   label:'Probing',    color:'var(--text-dim)' },
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
      <div class="stat-card${projLowConf ? ' stat-card-dim' : ''}">
        <div class="stat-label">Projected Savings</div>
        <div class="stat-value${projLowConf ? ' stat-dim' : ' stat-accent'}">${projTotalFiles > 0 ? fmtBytes(projSavedBytes) : '—'}</div>
        <div class="stat-sub">${projTotalFiles > 0 ? `${projTotalFiles.toLocaleString()} pending files · ${avgSamples} sample${avgSamples !== 1 ? 's' : ''}${projLowConf ? ' · low confidence' : ''}` : 'no estimate available'}</div>
      </div>
      <div class="stat-card${projLowConf ? ' stat-card-dim' : ''}">
        <div class="stat-label">Total Savings Est.</div>
        <div class="stat-value${projLowConf ? ' stat-dim' : ' stat-accent'}">${projTotalFiles > 0 ? fmtBytes((stats.saved_bytes || 0) + projSavedBytes) : fmtBytes(stats.saved_bytes || 0)}</div>
        <div class="stat-sub">${projTotalFiles > 0 ? `saved + projected${projLowConf ? ' · low confidence' : ''}` : 'saved so far'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Library ETA</div>
        <div class="stat-value">${etaSecs != null ? fmtDuration(etaSecs) : '—'}</div>
        <div class="stat-sub">${etaSecs != null ? `${remaining.toLocaleString()} files · ${availableWorkers.length} worker${availableWorkers.length !== 1 ? 's' : ''}` : 'no estimate available'}</div>
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
      <div class="card-title" style="display:flex;align-items:center">
        <span style="flex:1">Workers — ${workers.length} registered, ${activeWorkers} active</span>
        ${workers.length > 0 ? `<button class="btn btn-sm" onclick="toggleAllWorkersExpanded()" style="font-size:11px">${ST.workerExpanded.size >= workers.length ? 'Collapse all' : 'Expand all'}</button>` : ''}
      </div>
      ${workers.length === 0 ? '<div class="empty">No workers registered</div>' : workers.map(s => {
        const expanded = ST.workerExpanded.has(s.config_id);
        const dotColor = s.disk_full ? 'var(--red)' : s.state === 'processing' ? 'var(--blue)' : s.sleeping ? 'var(--text-faint)' : 'var(--green)';
        const p = s.progress;
        const pct = p ? Math.round(p.percent || 0) : 0;
        const statusStr = s.disk_full ? 'disk full' : s.sleeping ? 'sleeping' : s.drain ? 'draining' : s.state === 'processing' ? (s.paused ? 'paused' : 'processing') : 'online';
        return `
        <div style="padding:10px 0;border-bottom:1px solid var(--border-subtle)">
          <div style="display:flex;align-items:center;gap:8px;cursor:pointer" onclick="toggleWorkerExpanded('${esc(s.config_id)}')">
            <div style="width:8px;height:8px;border-radius:50%;background:${dotColor};flex-shrink:0"></div>
            <div style="font-size:13px;font-weight:500;flex:1">${esc(s.hostname)}</div>
            ${!expanded && s.state === 'processing' && p ? `
            <div style="display:flex;align-items:center;gap:8px;min-width:0">
              <div class="progress-track" style="width:80px;flex-shrink:0"><div class="progress-fill" style="width:${pct}%"></div></div>
              <span style="font-size:11px;color:var(--text-dim);font-family:'IBM Plex Mono',monospace;white-space:nowrap">${pct}%</span>
            </div>` : ''}
            <div style="width:100px;flex-shrink:0;text-align:right">${badge(statusStr)}</div>
            <div style="color:var(--text-faint);font-size:11px;width:14px;text-align:center">${expanded ? '▲' : '▼'}</div>
          </div>
          ${expanded ? `
          <div style="padding-top:8px">
            <div style="display:flex;align-items:center;gap:12px;min-width:0">
              <div style="font-size:11px;color:var(--text-faint);font-family:'IBM Plex Mono',monospace;white-space:nowrap;padding-left:16px">${s.unconfigured ? 'SETUP REQUIRED' : esc((s.encoder||'').toUpperCase())} · batch ${s.batch_size||1} · ${s.converted||0} converted</div>
              ${s.state === 'processing' && p ? `
              <div style="flex:1;min-width:0;display:flex;align-items:center;gap:8px">
                <span style="font-size:11px;color:var(--text-dim);font-family:'IBM Plex Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1" title="${esc(s.current_file||'')}">${esc((s.current_file||'…').split('/').pop())}</span>
                <div class="progress-track" style="width:120px;flex-shrink:0"><div class="progress-fill" style="width:${pct}%"></div></div>
                <span style="font-size:11px;color:var(--text-dim);font-family:'IBM Plex Mono',monospace;white-space:nowrap;min-width:32px;text-align:right">${pct}%</span>
              </div>` : '<div style="flex:1"></div>'}
              ${s.state === 'processing' ? `
              <div style="display:flex;gap:4px;flex-shrink:0">
                ${s.drain
                  ? `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'wake')" title="Wake">${svgIcon('play',11)}</button>`
                  : s.paused
                    ? `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'resume')" title="Resume">${svgIcon('play',11)}</button>`
                    : `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'pause')" title="Pause">${svgIcon('pause',11)}</button>`
                }
                <button class="btn btn-sm ${s.drain?'btn-primary':''}" onclick="workerAction('${esc(s.host)}',${s.api_port},'drain')" title="Drain">⏭</button>
                <button class="btn btn-sm btn-danger" onclick="workerAction('${esc(s.host)}',${s.api_port},'stop')" title="Stop">${svgIcon('stop',11)}</button>
              </div>` : `
              <div style="display:flex;gap:4px;flex-shrink:0">
                ${s.sleeping
                  ? `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'wake')" title="Wake">${svgIcon('play',11)}</button>`
                  : `<button class="btn btn-sm" disabled>${svgIcon('pause',11)}</button>`
                }
                <button class="btn btn-sm" disabled>⏭</button>
                <button class="btn btn-sm" disabled>${svgIcon('stop',11)}</button>
              </div>`}
            </div>
          </div>` : ''}
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

const FILES_PAGE_SIZES = [10, 25, 50, 100, 500];
let FILES_PAGE_SIZE = 25;

function _getFilteredFiles() {
  const files = (ST.data && ST.data.files) || [];
  return files.filter(f => {
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
}

function _sortedFiles(filtered) {
  const {col, dir} = ST.fileSort;
  const m = dir === 'asc' ? 1 : -1;
  return [...filtered].sort((a, b) => {
    switch (col) {
      case 'file_path':   return m * (a.file_path||'').localeCompare(b.file_path||'');
      case 'status':      return m * (a.status||'').localeCompare(b.status||'');
      case 'worker_id':   return m * (a.worker_id||'').localeCompare(b.worker_id||'');
      case 'file_size':   return m * ((a.file_size||0) - (b.file_size||0));
      case 'output_size': return m * ((a.output_size||0) - (b.output_size||0));
      case 'saved':       return m * (((a.file_size||0)-(a.output_size||0)) - ((b.file_size||0)-(b.output_size||0)));
      case 'finished_at': return m * (a.finished_at||'').localeCompare(b.finished_at||'');
      default:            return m * (a.created_at||'').localeCompare(b.created_at||'');
    }
  });
}

function _sortTh(label, col) {
  const active = ST.fileSort.col === col;
  const arrow = active ? (ST.fileSort.dir === 'asc' ? ' ↑' : ' ↓') : '';
  return `<th class="sortable-th${active?' sort-active':''}" onclick="setFileSort('${col}')">${label}${arrow}</th>`;
}

function renderFiles() {
  const el = document.getElementById('tab-files');
  if (!el) return;
  const files = (ST.data && ST.data.files) || [];
  const workers = (ST.data && ST.data.workers) || [];

  const statuses = ['all','scanning','pending','assigned','processing','complete','error','duplicate','discarded','cancelled'];
  const counts = {};
  statuses.forEach(s => counts[s] = s === 'all' ? files.length : files.filter(f => f.status === s).length);

  const filtered = _getFilteredFiles();
  const sorted = _sortedFiles(filtered);
  const totalPages = Math.max(1, Math.ceil(sorted.length / FILES_PAGE_SIZE));
  const page = Math.min(ST.filePage, totalPages - 1);
  const pageFiles = sorted.slice(page * FILES_PAGE_SIZE, (page + 1) * FILES_PAGE_SIZE);
  const pageIds = pageFiles.map(f => f.id);

  const allPageSelected = pageIds.length > 0 && pageIds.every(id => ST.fileSelected.has(id));
  const somePageSelected = pageIds.some(id => ST.fileSelected.has(id));
  const nSel = ST.fileSelected.size;
  const allPagesSelectable = allPageSelected && nSel < filtered.length;

  const chipLabels = {
    all: 'All', scanning: 'Probing', pending: 'Pending', assigned: 'Assigned',
    processing: 'Processing', complete: 'Done', error: 'Error',
    duplicate: 'Duplicate', discarded: 'Discarded', cancelled: 'Cancelled',
  };
  const visibleChips = ['all','scanning','pending','processing','complete','error','duplicate','discarded','cancelled'];

  const paginationBar = totalPages > 1 ? `
    <div class="pagination-bar">
      <button class="btn btn-sm" onclick="setFilePage(${page-1})" ${page===0?'disabled':''}>←</button>
      ${Array.from({length: totalPages}, (_,i) => {
        if (totalPages <= 7 || i === 0 || i === totalPages-1 || Math.abs(i - page) <= 1) {
          return `<button class="btn btn-sm${i===page?' btn-primary':''}" onclick="setFilePage(${i})">${i+1}</button>`;
        } else if (Math.abs(i - page) === 2) {
          return `<span style="color:var(--text-faint);padding:0 2px">…</span>`;
        }
        return '';
      }).filter((x,i,a) => x && (x !== a[i-1])).join('')}
      <button class="btn btn-sm" onclick="setFilePage(${page+1})" ${page===totalPages-1?'disabled':''}>→</button>
      <span style="color:var(--text-faint);font-size:12px;margin-left:4px">${sorted.length} files</span>
      <select class="input" style="margin-left:auto;width:auto;padding:2px 6px;font-size:12px" onchange="setPageSize(+this.value)">
        ${FILES_PAGE_SIZES.map(n => `<option value="${n}"${n===FILES_PAGE_SIZE?' selected':''}>${n} / page</option>`).join('')}
      </select>
    </div>` : `
    <div class="pagination-bar" style="justify-content:flex-end">
      <select class="input" style="width:auto;padding:2px 6px;font-size:12px" onchange="setPageSize(+this.value)">
        ${FILES_PAGE_SIZES.map(n => `<option value="${n}"${n===FILES_PAGE_SIZE?' selected':''}>${n} / page</option>`).join('')}
      </select>
    </div>`;

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
      ${allPagesSelectable ? `
      <div class="select-all-banner">
        ${nSel} files on this page selected —
        <a href="#" onclick="selectAllFilteredFiles(event)">Select all ${filtered.length} matching files</a>
      </div>` : nSel > 0 && nSel >= filtered.length && totalPages > 1 ? `
      <div class="select-all-banner">
        All ${nSel} matching files selected —
        <a href="#" onclick="clearSelection()">Clear selection</a>
      </div>` : ''}
      <div class="table-wrap">
        <table>
          <thead>${nSel > 0 ? `
          <tr style="height:38px;background:var(--accent-glow)">
            <th style="width:36px;padding:0 0 0 14px">
              <input type="checkbox" ${allPageSelected?'checked':''} onchange="toggleAllFiles(this)" style="accent-color:var(--accent)">
            </th>
            <th style="padding:0" colspan="7">
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
              <input type="checkbox" ${allPageSelected?'checked':''} onchange="toggleAllFiles(this)"
                     style="accent-color:var(--accent)">
            </th>
            ${_sortTh('Path','file_path')}
            ${_sortTh('Status','status')}
            ${_sortTh('Worker','worker_id')}
            ${_sortTh('Original','file_size')}
            ${_sortTh('Converted','output_size')}
            ${_sortTh('Saved','saved')}
            ${_sortTh('Added','created_at')}
            ${_sortTh('Finished','finished_at')}
            <th></th>
          </tr>`}
          </thead>
          <tbody>
            ${pageFiles.length === 0 ? `<tr><td colspan="10"><div class="empty">No files matching filter</div></td></tr>` :
              pageFiles.map(f => {
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
                  <td><span class="mono">${fmtDate(f.finished_at)}</span></td>
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
      ${paginationBar}
    </div>
  `;

  // Re-apply indeterminate state
  const hdr = el.querySelector('thead input[type="checkbox"]');
  if (hdr) hdr.indeterminate = somePageSelected && !allPageSelected;
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
  ST.filePage = 0;
  renderFiles();
}

function setFileSearch(q) {
  ST.fileSearch = q;
  ST.fileSelected.clear();
  ST.filePage = 0;
  renderFiles();
  const inp = document.getElementById('file-search-input');
  if (inp) { inp.focus(); inp.setSelectionRange(q.length, q.length); }
}

function setFileSort(col) {
  if (ST.fileSort.col === col) {
    ST.fileSort.dir = ST.fileSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    ST.fileSort = {col, dir: (col === 'created_at' || col === 'finished_at') ? 'desc' : 'asc'};
  }
  ST.filePage = 0;
  renderFiles();
}

function setFilePage(p) {
  ST.filePage = p;
  renderFiles();
}

function setPageSize(n) {
  FILES_PAGE_SIZE = n;
  ST.filePage = 0;
  ST.modalPage = 0;
  renderFiles();
  renderStatusModal();
}

function toggleAllFiles(src) {
  const filtered = _getFilteredFiles();
  const sorted = _sortedFiles(filtered);
  const page = Math.min(ST.filePage, Math.max(0, Math.ceil(sorted.length / FILES_PAGE_SIZE) - 1));
  const pageIds = sorted.slice(page * FILES_PAGE_SIZE, (page + 1) * FILES_PAGE_SIZE).map(f => f.id);
  if (src.checked) pageIds.forEach(id => ST.fileSelected.add(id));
  else ST.fileSelected.clear();
  renderFiles();
}

function selectAllFilteredFiles(e) {
  e.preventDefault();
  _getFilteredFiles().forEach(f => ST.fileSelected.add(f.id));
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
  const statusStr = isDiskFull ? 'disk full' : s.unconfigured ? 'setup required' : isSleeping ? 'sleeping' : s.drain ? 'draining' : isProcessing ? (isPaused ? 'paused' : 'processing') : (s.state === 'unreachable' ? 'offline' : 'online');

  const labels = s.encoder_labels || {};
  const showCmd = !!ST.workerCmdOpen[s.config_id];
  const currentFile = s.current_file || '';
  const currentFileName = currentFile ? currentFile.split('/').pop() : '…';
  const notOnboarded = !s.tls_enabled && !!((ST.data.tls_status||{}).enabled);
  const disableControls = notOnboarded || s.unconfigured;

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
      <div class="progress-track"><div class="progress-fill${p.stalled ? ' stalled' : ''}" style="width:${pct}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-faint);margin-top:4px;font-family:'IBM Plex Mono',monospace">
        <span>${p.stalled ? '<span style="color:var(--warn)">timestamps frozen</span>' : (p.eta_seconds != null ? `ETA ${fmtEta(p.eta_seconds)}` : '—')}</span>
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
      <div class="worker-stat">
        <div class="worker-stat-label">Queue</div>
        <div class="worker-stat-value">${s.queued||0}</div>
      </div>
      <div class="worker-stat" style="min-width:0">
        <div class="worker-stat-label">Path</div>
        <div class="worker-stat-value" style="font-size:11px;font-family:'IBM Plex Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc((s.worker_config&&s.worker_config.values&&s.worker_config.values.path_prefix)||'')}">${esc((s.worker_config&&s.worker_config.values&&s.worker_config.values.path_prefix)||'—')}</div>
      </div>
    </div>

    <div class="worker-controls">
      ${isProcessing ? `
        ${s.drain
          ? `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'resume')" ${disableControls?'disabled':''}>${svgIcon('play',12)} Resume</button>`
          : isPaused
            ? `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'resume')" ${disableControls?'disabled':''}>${svgIcon('play',12)} Resume</button>`
            : `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'pause')" ${disableControls?'disabled':''}>${svgIcon('pause',12)} Pause</button>`
        }
        <button class="btn btn-sm btn-danger" onclick="workerAction('${esc(s.host)}',${s.api_port},'stop')" ${disableControls?'disabled':''}>${svgIcon('stop',12)} Stop</button>
        <button class="btn btn-sm ${s.drain?'btn-primary':''}" onclick="workerAction('${esc(s.host)}',${s.api_port},'drain')" ${disableControls?'disabled':''}>Drain</button>
      ` : isSleeping ? `
        <button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'wake')" ${disableControls?'disabled':''}>${svgIcon('play',12)} Wake</button>
        <button class="btn btn-sm" disabled>${svgIcon('stop',12)} Stop</button>
        <button class="btn btn-sm" disabled>Drain</button>
      ` : `
        <button class="btn btn-sm" disabled>${svgIcon('pause',12)} Pause</button>
        <button class="btn btn-sm" disabled>${svgIcon('stop',12)} Stop</button>
        <button class="btn btn-sm" disabled>Drain</button>
      `}
      ${isSleeping
        ? `<button class="btn btn-primary btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'wake')" ${disableControls?'disabled':''}>${svgIcon('play',12)} Wake</button>`
        : `<button class="btn btn-sm" onclick="workerAction('${esc(s.host)}',${s.api_port},'sleep')" ${disableControls?'disabled':''}>${svgIcon('moon',12)} Sleep</button>`
      }
      <button class="btn btn-sm" onclick="toggleWorkerSettings('${esc(s.config_id)}')">${svgIcon('settings',12)} Settings</button>
      ${s.current_cmd ? `<button class="btn btn-sm ${showCmd?'btn-primary':''}" onclick="toggleWorkerCmd('${esc(s.config_id)}')" ${disableControls?'disabled':''}>CMD</button>` : ''}
      <button class="btn btn-sm" style="margin-left:auto" onclick="restartWorker('${esc(s.host)}',${s.api_port})" ${disableControls?'disabled':''} title="Restart worker process">Restart</button>
      ${notOnboarded ? `<button class="btn btn-sm btn-primary" onclick="onboardWorkerTls('${esc(s.host)}',${s.api_port})" title="Bootstrap TLS for this worker">Onboard TLS</button>` : ''}
      <button class="btn btn-sm btn-danger" onclick="deregisterWorker('${esc(s.config_id)}')" title="Deregister">${svgIcon('trash',12)}</button>
    </div>

    ${showCmd && s.current_cmd ? `
    <div style="margin-top:8px;padding:8px;background:var(--bg-subtle);border-radius:6px;font-size:10px;font-family:'IBM Plex Mono',monospace;color:var(--text-faint);word-break:break-all;white-space:pre-wrap">${esc(s.current_cmd)}</div>` : ''}

    ${showSettings ? `
    <div class="worker-settings-panel">
      <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-faint);margin-bottom:8px">Running config</div>
      <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:11px;margin-bottom:12px;font-family:'IBM Plex Mono',monospace">
        <span style="color:var(--text-faint)">Encoder</span><span>${s.unconfigured ? 'Setup required' : esc(labels[s.encoder]||s.encoder||'—')}</span>
        <span style="color:var(--text-faint)">Batch</span><span>${s.batch_size||1}</span>
        <span style="color:var(--text-faint)">Replace orig.</span><span>${s.replace_original?'yes':'no'}</span>
        <span style="color:var(--text-faint)">Queue</span><span>${s.queued||0}</span>
        <span style="color:var(--text-faint)">Master</span><span>${esc(s.url||'—')}</span>
      </div>
      <div style="border-top:1px solid var(--border-subtle);margin:0 0 12px"></div>
      <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 12px;align-items:center">
        <label class="label" style="white-space:nowrap">Replace original</label>
        <div class="toggle ${s.replace_original?'on':''}" id="repl-${esc(s.config_id)}"
             onclick="this.classList.toggle('on')"></div>
      </div>
      <button class="btn btn-primary btn-sm" style="margin-top:10px"
              onclick="saveWorkerSettings('${esc(s.config_id)}','${esc(s.host)}',${s.api_port})">
        Save settings
      </button>
      ${renderWorkerConfigCard(s)}
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


function toggleWorkerExpanded(configId) {
  if (ST.workerExpanded.has(configId)) ST.workerExpanded.delete(configId);
  else ST.workerExpanded.add(configId);
  renderOverview();
}

function toggleAllWorkersExpanded() {
  const workers = (ST.data && ST.data.workers) || [];
  if (ST.workerExpanded.size >= workers.length) ST.workerExpanded.clear();
  else workers.forEach(w => ST.workerExpanded.add(w.config_id));
  renderOverview();
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

async function saveWorkerEncoder(configId, host, port, value) {
  const workers = (ST.data && ST.data.workers) || [];
  const w = workers.find(x => x.config_id === configId);
  if (!w) return;
  if (ST.demo) { toast('[Demo] Encoder changed', 'info'); return; }
  try {
    const r = await fetch('/data/worker/encoder', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port, encoder: value, replace_original: w.replace_original}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Encoder saved', 'success');
    await fetchAll();
    renderActiveTab();
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

// ── TLS helpers ──────────────────────────────────────────────────────────────
function fmtTokenExpiry(expiresAt) {
  if (!expiresAt) return null;
  const diff = Math.floor((new Date(expiresAt) - Date.now()) / 1000);
  if (diff <= 0) return 'expired';
  if (diff < 60) return `${diff}s`;
  return `${Math.floor(diff / 60)}m ${diff % 60}s`;
}

async function generateToken() {
  const btn = document.getElementById('btn-gen-token');
  if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }
  try {
    await fetch('/data/tls/token', {method: 'POST'});
    await fetchAll();
    renderActiveTab();
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate token'; }
  }
}

function renderTlsCard(tlsStatus, tlsToken) {
  if (!tlsStatus || !tlsStatus.enabled) return '';
  const fp = tlsStatus.ca_fingerprint;
  const token = tlsToken && tlsToken.token ? tlsToken.token : null;
  const expiresAt = tlsToken && tlsToken.expires_at ? tlsToken.expires_at : null;
  const expStr = fmtTokenExpiry(expiresAt);
  const tokenHtml = token
    ? `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <code style="font-size:12px;background:var(--bg-subtle);padding:4px 8px;border-radius:4px;word-break:break-all">${esc(token)}</code>
        <span style="font-size:11px;color:var(--text-dim)">${expStr ? `expires in ${expStr}` : ''}</span>
       </div>`
    : `<span style="font-size:12px;color:var(--text-dim)">No active token</span>`;
  return `
    <div class="card" style="margin-top:16px">
      <div class="card-title">TLS / mTLS</div>
      ${fp ? `<div style="font-size:11px;color:var(--text-dim);margin-bottom:10px">CA fingerprint: <code style="font-size:11px">${esc(fp)}</code></div>` : ''}
      <div style="margin-bottom:8px;font-size:12px;color:var(--text-dim)">Bootstrap token (10 min, multi-use)</div>
      <div style="margin-bottom:10px">${tokenHtml}</div>
      <button id="btn-gen-token" class="btn btn-sm" onclick="generateToken()">Generate token</button>
      <div style="font-size:11px;color:var(--text-faint);margin-top:6px">
        Workers and web use this token with <code>bootstrap_token</code> in their config to obtain a client certificate.
      </div>
    </div>
  `;
}

// ── Scan tab ─────────────────────────────────────────────────────────────────
function renderScan() {
  const el = document.getElementById('tab-master');
  if (!el) return;
  const data = ST.data || {};
  const scan = data.scan || {running: false};
  const meta = data.master_meta || {};
  const cfg = data.master_config || {};
  const tlsStatus = data.tls_status || {};
  const tlsToken  = data.tls_token  || {};
  const running = scan.running;
  const scanned = scan.scanned || 0;
  const total = scan.total || 0;
  const found = scan.found || 0;
  const scanPct = total > 0 ? Math.round(scanned / total * 100) : 0;

  const avgConvS = meta.avg_conversion_s;
  const avgConvStr = avgConvS != null ? fmtDuration(avgConvS) : '—';
  const probeRate = meta.probe_rate_per_s;
  const probeRateStr = probeRate != null ? `${probeRate}/s` : '—';
  const scanRate = meta.scan_rate_per_s;
  const scanRateStr = scanRate != null ? `${scanRate} files/s` : (running ? 'measuring…' : '—');
  const scanningQ = meta.scanning_queue ?? 0;

  const st = data.stats || {};
  const probeTotal = (st.total || 0) - (st.duplicate || 0);
  const probeDone = probeTotal - scanningQ;
  const probePct = probeTotal > 0 ? Math.min(100, Math.round(probeDone / probeTotal * 100)) : 0;

  const configCard = renderMasterConfigCard(cfg);

  el.innerHTML = `
    <div style="max-width:720px">
      <div class="stats-grid" style="margin-bottom:20px;grid-template-columns:repeat(4,1fr)">
        <div class="stat-card">
          <div class="stat-label">Avg conversion</div>
          <div class="stat-value">${avgConvStr}</div>
          <div class="stat-sub">per file</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Probe rate</div>
          <div class="stat-value">${probeRateStr}</div>
          <div class="stat-sub">last 60 s</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Scan speed</div>
          <div class="stat-value">${scanRateStr}</div>
          <div class="stat-sub">current scan</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Probe queue</div>
          <div class="stat-value ${scanningQ > 0 ? 'stat-accent' : ''}">${scanningQ.toLocaleString()}</div>
          <div class="stat-sub">awaiting probe</div>
        </div>
      </div>
      ${probeTotal > 0 ? `
      <div style="margin-bottom:20px">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-dim);margin-bottom:6px">
          <span>Probe progress</span>
          <span>${probeDone.toLocaleString()} / ${probeTotal.toLocaleString()} · ${probePct}%</span>
        </div>
        <div class="progress-track" style="height:8px">
          <div class="progress-fill" style="width:${probePct}%"></div>
        </div>
      </div>` : ''}

      <div class="scan-status-bar">
        <div class="scan-indicator ${running?'scanning':''}"></div>
        <div class="scan-info">
          <div class="scan-title">${running ? 'Scan in progress…' : 'Scanner idle'}</div>
          <div class="scan-sub">
            ${running
              ? `${(found + (scan.skipped||0) + (scan.errors||0)).toLocaleString()} processed · ${found} new · ${scan.skipped||0} skipped${scan.errors ? ` · ${scan.errors} errors` : ''}`
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

      ${configCard}

      ${renderTlsCard(tlsStatus, tlsToken)}

      <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border-subtle);display:flex;align-items:center;gap:8px">
        <button class="btn btn-sm btn-danger" onclick="restartMaster()" title="Restart the master process">Restart master</button>
        <span style="font-size:11px;color:var(--text-faint)">Gracefully terminates and restarts the master process. Requires a process manager (e.g. Docker) to restart it.</span>
      </div>
    </div>
  `;
}

function _cfgDisplayValue(field, value) {
  if (field.type === 'list[str]') return (value || []).join(', ');
  if (value == null) return '';
  return String(value);
}

function renderMasterConfigCard(cfg) {
  const fields = cfg.fields || [];
  if (!fields.length) return '';
  const values  = cfg.values  || {};
  const sources = cfg.sources || {};
  const fileV   = cfg.file    || {};
  const envV    = cfg.env     || {};
  const cliV    = cfg.cli     || {};
  const cfgFile = cfg.config_file || '';
  const rows = fields.map(f => renderMasterConfigRow(f, values[f.key], sources[f.key], fileV, envV, cliV)).join('');
  const fileNote = cfgFile ? `<div style="font-size:11px;color:var(--text-faint);margin-top:4px">Config file: <code>${esc(cfgFile)}</code></div>` : '';
  return `
    <div class="card" style="margin-top:16px">
      <div class="card-title">Master Configuration</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:12px">
        Priority: default &lt; file &lt; env &lt; database &lt; CLI. Edits are stored in the database.
        ${fileNote}
      </div>
      ${rows}
    </div>
  `;
}

function renderMasterConfigRow(f, value, source, fileV, envV, cliV) {
  const hasFile = Object.prototype.hasOwnProperty.call(fileV, f.key);
  const hasEnv  = Object.prototype.hasOwnProperty.call(envV,  f.key);
  const hasCli  = Object.prototype.hasOwnProperty.call(cliV,  f.key);
  const isDb    = source === 'db';
  const restartFlag = f.requires_restart
    ? ` <span style="font-size:10px;color:#ef5350;text-transform:uppercase;letter-spacing:.5px">restart required on change</span>`
    : '';
  const cliNotice = hasCli
    ? `<div style="font-size:11px;color:#ab47bc;margin-top:4px">CLI flag active — DB edits take effect only after restart without the flag.</div>`
    : '';
  const keyAttr = esc(f.key);
  let control;
  if (f.type === 'bool') {
    const on = value === true || value === 1 || value === '1' || value === 'true';
    control = `<div class="toggle ${on ? 'on' : ''}" title="${on ? 'On' : 'Off'} — click to toggle"
                    onclick="masterConfigToggleBool('${keyAttr}')" style="flex:none"></div>
               <div style="flex:1;min-width:0;font-size:12px;color:var(--text-dim)">${on ? 'On' : 'Off'}</div>`;
  } else {
    const display = esc(_cfgDisplayValue(f, value));
    const inputType = f.type === 'int' ? 'number' : 'text';
    control = `<input class="input" type="${inputType}" value="${display}"
                      data-cfg-key="${keyAttr}" data-cfg-type="${esc(f.type)}"
                      style="flex:1;min-width:220px;font-family:'IBM Plex Mono',monospace"
                      onkeydown="if(event.key==='Enter'){this.blur();}"
                      onblur="masterConfigSave('${keyAttr}','${esc(f.type)}',this.value)">`;
  }
  const revertTitle = (!hasFile && !hasEnv)
    ? 'No file or env value to revert to — use Default to reset'
    : 'Clear DB override; revert via priority chain';
  const revertDisabled = (!hasFile && !hasEnv) ? 'disabled' : '';
  return `
    <div class="settings-row" style="display:block;padding:12px 0">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
        <strong>${esc(f.label || f.key)}</strong>
        <code style="font-size:11px;color:var(--text-faint)">${keyAttr}</code>
        ${restartFlag}
      </div>
      ${f.help ? `<div style="margin:0 0 6px 0;font-size:12px;color:var(--text-dim)">${esc(f.help)}</div>` : ''}
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${control}
        ${hasFile ? `<button class="btn btn-sm" title="Copy file value to DB" onclick="masterConfigRestore('${keyAttr}','file')">Restore from file</button>` : ''}
        ${hasEnv  ? `<button class="btn btn-sm" title="Copy env value to DB"  onclick="masterConfigRestore('${keyAttr}','env')">Restore from env</button>`  : ''}
        <button class="btn btn-sm" title="Copy default value to DB" onclick="masterConfigRestore('${keyAttr}','default')">Default</button>
        ${isDb ? `<button class="btn btn-sm btn-danger" title="${revertTitle}" onclick="masterConfigRevert('${keyAttr}')" ${revertDisabled}>Revert</button>` : ''}
      </div>
      ${cliNotice}
    </div>
  `;
}

function _cfgCoerce(type, raw) {
  if (type === 'int') {
    const n = Number(String(raw).trim());
    if (!Number.isFinite(n)) throw new Error('expected a number');
    return Math.trunc(n);
  }
  if (type === 'list[str]') {
    return String(raw).split(',').map(s => s.trim()).filter(Boolean);
  }
  return String(raw);
}

function _cfgSameValue(type, a, b) {
  if (type === 'list[str]') {
    const aa = Array.isArray(a) ? a : [];
    const bb = Array.isArray(b) ? b : [];
    return aa.length === bb.length && aa.every((v, i) => String(v) === String(bb[i]));
  }
  return String(a ?? '') === String(b ?? '');
}

async function masterConfigSave(key, type, raw) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  const cfg = (ST.data && ST.data.master_config) || {};
  const current = (cfg.values || {})[key];
  let newValue;
  try { newValue = _cfgCoerce(type, raw); }
  catch (e) { toast(`${key}: ${e.message}`, 'error'); return; }
  if (_cfgSameValue(type, current, newValue)) return;
  try {
    const r = await fetch(`/data/master/config/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({value: newValue}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} saved${res.requires_restart ? ' (restart required)' : ''}`, 'success');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function masterConfigToggleBool(key) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  const cfg = (ST.data && ST.data.master_config) || {};
  const current = (cfg.values || {})[key];
  const next = !(current === true || current === 1 || current === '1' || current === 'true');
  try {
    const r = await fetch(`/data/master/config/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({value: next}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} ${next ? 'enabled' : 'disabled'}${res.requires_restart ? ' (restart required)' : ''}`, 'success');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function masterConfigRestore(key, source) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  try {
    const r = await fetch(`/data/master/config/${encodeURIComponent(key)}/restore`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({source}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} restored from ${source}${res.requires_restart ? ' (restart required)' : ''}`, 'success');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function masterConfigRevert(key) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  try {
    const r = await fetch(`/data/master/config/${encodeURIComponent(key)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} reverted${res.requires_restart ? ' (restart required)' : ''}`, 'info');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ---------------------------------------------------------------------------
// Worker config card (layered: default < file < env < db < cli)
// ---------------------------------------------------------------------------

function renderWorkerConfigCard(s) {
  const cfg = s.worker_config || {};
  const fields = cfg.fields || [];
  const values  = cfg.values  || {};
  const sources = cfg.sources || {};
  const fileV   = cfg.file    || {};
  const envV    = cfg.env     || {};
  const cliV    = cfg.cli     || {};
  const cfgFile = cfg.config_file || '';
  const host = esc(s.host);
  const port = s.api_port;
  const configId = esc(s.config_id);

  const encoders = s.available_encoders || ['libx265'];
  const encLabels = s.encoder_labels || {};
  const encPlaceholder = s.unconfigured ? `<option value="" selected disabled>Setup required — select an encoder</option>` : '';
  const encOptions = encPlaceholder + encoders.map(e => `<option value="${esc(e)}" ${!s.unconfigured&&s.encoder===e?'selected':''}>${esc(encLabels[e]||e)}</option>`).join('');
  const encoderRow = `
    <div class="settings-row" style="display:block;padding:8px 0">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
        <strong style="font-size:12px">Encoder</strong>
      </div>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        <select class="input" style="flex:1;min-width:180px;font-size:12px"
                onchange="saveWorkerEncoder('${configId}','${host}',${port},this.value)">
          ${encOptions}
        </select>
      </div>
    </div>`;

  const cfgRows = fields.map(f => renderWorkerConfigRow(f, values[f.key], sources[f.key], fileV, envV, cliV, host, port)).join('');
  const fileNote = cfgFile ? `<div style="font-size:11px;color:var(--text-faint);margin-top:4px">Config file: <code>${esc(cfgFile)}</code></div>` : '';
  return `
    <div style="border-top:1px solid var(--border-subtle);margin:12px 0 0"></div>
    <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-faint);margin:12px 0 4px">Worker Configuration</div>
    <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">
      Priority: default &lt; file &lt; env &lt; database &lt; CLI. Edits are stored in the database.
      ${fileNote}
    </div>
    ${encoderRow}
    ${cfgRows}
  `;
}

function renderWorkerConfigRow(f, value, source, fileV, envV, cliV, host, port) {
  const hasFile = Object.prototype.hasOwnProperty.call(fileV, f.key);
  const hasEnv  = Object.prototype.hasOwnProperty.call(envV,  f.key);
  const hasCli  = Object.prototype.hasOwnProperty.call(cliV,  f.key);
  const isDb    = source === 'db';
  const keyAttr = esc(f.key);
  const restartFlag = f.requires_restart
    ? ` <span style="font-size:10px;color:#ef5350;text-transform:uppercase;letter-spacing:.5px">restart required on change</span>`
    : '';
  const cliNotice = hasCli
    ? `<div style="font-size:11px;color:#ab47bc;margin-top:4px">CLI flag active — DB edits take effect only after restart without the flag.</div>`
    : '';
  const display = esc(_cfgDisplayValue(f, value));
  const inputType = f.type === 'int' ? 'number' : 'text';
  const control = `<input class="input" type="${inputType}" value="${display}"
                          data-cfg-key="${keyAttr}" data-cfg-type="${esc(f.type)}"
                          style="flex:1;min-width:180px;font-family:'IBM Plex Mono',monospace;font-size:12px"
                          onkeydown="if(event.key==='Enter'){this.blur();}"
                          onblur="workerCfgSave('${host}',${port},'${keyAttr}','${esc(f.type)}',this.value)">`;
  const revertTitle = (!hasFile && !hasEnv)
    ? 'No file or env value to revert to — use Default to reset'
    : 'Clear DB override; revert via priority chain';
  const revertDisabled = (!hasFile && !hasEnv) ? 'disabled' : '';
  return `
    <div class="settings-row" style="display:block;padding:8px 0">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
        <strong style="font-size:12px">${esc(f.label || f.key)}</strong>
        <code style="font-size:10px;color:var(--text-faint)">${keyAttr}</code>
        ${restartFlag}
      </div>
      ${f.help ? `<div style="margin:0 0 4px 0;font-size:11px;color:var(--text-dim)">${esc(f.help)}</div>` : ''}
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${control}
        ${hasFile ? `<button class="btn btn-sm" onclick="workerCfgRestore('${host}',${port},'${keyAttr}','file')">Restore from file</button>` : ''}
        ${hasEnv  ? `<button class="btn btn-sm" onclick="workerCfgRestore('${host}',${port},'${keyAttr}','env')">Restore from env</button>`  : ''}
        <button class="btn btn-sm" onclick="workerCfgRestore('${host}',${port},'${keyAttr}','default')">Default</button>
        ${isDb ? `<button class="btn btn-sm btn-danger" title="${revertTitle}" onclick="workerCfgRevert('${host}',${port},'${keyAttr}')" ${revertDisabled}>Revert</button>` : ''}
      </div>
      ${cliNotice}
    </div>
  `;
}

async function workerCfgSave(host, port, key, type, raw) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  const worker = (ST.data && ST.data.workers || []).find(w => w.host === host && w.api_port === port);
  const current = ((worker && worker.worker_config && worker.worker_config.values) || {})[key];
  let newValue;
  try { newValue = _cfgCoerce(type, raw); }
  catch (e) { toast(`${key}: ${e.message}`, 'error'); return; }
  if (_cfgSameValue(type, current, newValue)) return;
  try {
    const r = await fetch(`/data/worker/config/${encodeURIComponent(key)}?host=${encodeURIComponent(host)}&port=${port}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({value: newValue}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} saved${res.requires_restart ? ' (restart required)' : ''}`, 'success');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function workerCfgRestore(host, port, key, source) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  try {
    const r = await fetch(`/data/worker/config/${encodeURIComponent(key)}/restore?host=${encodeURIComponent(host)}&port=${port}`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({source}),
    });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} restored from ${source}${res.requires_restart ? ' (restart required)' : ''}`, 'success');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function workerCfgRevert(host, port, key) {
  if (ST.demo) { toast('[Demo] Config unchanged', 'info'); return; }
  try {
    const r = await fetch(`/data/worker/config/${encodeURIComponent(key)}?host=${encodeURIComponent(host)}&port=${port}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    toast(`${key} reverted${res.requires_restart ? ' (restart required)' : ''}`, 'info');
    fetchAll();
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function restartMaster() {
  if (ST.demo) { toast('[Demo] Restart skipped', 'info'); return; }
  if (!confirm('Restart the master process?')) return;
  try {
    const r = await fetch('/data/master/restart', {method:'POST'});
    if (!r.ok) throw new Error(await r.text());
    toast('Master restarting…', 'info');
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function onboardWorkerTls(host, port) {
  try {
    const r = await fetch('/data/worker/tls/onboard', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port}),
    });
    if (!r.ok) throw new Error((await r.json()).error || await r.text());
    toast('TLS onboarded — worker restarting', 'info');
  } catch (e) {
    toast(`Onboard failed: ${e.message}`, 'error');
  }
}

async function restartWorker(host, port) {
  if (ST.demo) { toast('[Demo] Restart skipped', 'info'); return; }
  if (!confirm(`Restart worker at ${host}:${port}?`)) return;
  try {
    const r = await fetch('/data/worker/restart', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('Worker restarting…', 'info');
  } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
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

// ── Settings tab ──────────────────────────────────────────────────────────────
function renderSettings() {
  const el = document.getElementById('tab-settings');
  if (!el) return;
  const auth = (ST.data || {}).auth || {};

  el.innerHTML = `
    <div style="max-width:600px">
      <div class="card" style="margin-bottom:16px">
        <div class="card-title">Authentication</div>
        <div class="settings-row" style="align-items:flex-start;flex-direction:column;gap:12px">
          <div style="font-size:13px;color:var(--text-dim)">
            ${auth.enabled ? `Auth enabled — username: <strong>${esc(auth.username)}</strong>` : 'Auth disabled — dashboard is publicly accessible.'}
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;width:100%">
            <input id="auth-username" class="input" type="text" placeholder="Username (leave empty to disable auth)"
              value="${esc(auth.username)}" autocomplete="username" style="max-width:320px">
            <input id="auth-password" class="input" type="password" placeholder="New password"
              autocomplete="new-password" style="max-width:320px">
            <div style="display:flex;gap:8px;align-items:center">
              <button class="btn btn-sm btn-primary" onclick="saveAuth()">Save</button>
              ${auth.enabled ? `<button class="btn btn-sm btn-danger" onclick="disableAuth()">Disable auth</button>` : ''}
              <span id="auth-msg" style="font-size:12px;color:var(--text-dim)"></span>
            </div>
          </div>
        </div>
      </div>
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

async function saveAuth() {
  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value.trim();
  const msg = document.getElementById('auth-msg');
  try {
    const r = await fetch('/data/auth', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username, password})});
    const j = await r.json();
    if (!r.ok) { msg.style.color = 'var(--red)'; msg.textContent = j.error || 'Error'; return; }
    msg.style.color = 'var(--green)'; msg.textContent = 'Saved';
    await fetchAll();
    renderSettings();
  } catch(e) { msg.style.color = 'var(--red)'; msg.textContent = String(e); }
}

async function disableAuth() {
  const msg = document.getElementById('auth-msg');
  try {
    const r = await fetch('/data/auth', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username:'', password:''})});
    const j = await r.json();
    if (!r.ok) { msg.style.color = 'var(--red)'; msg.textContent = j.error || 'Error'; return; }
    msg.style.color = 'var(--green)'; msg.textContent = 'Auth disabled';
    await fetchAll();
    renderSettings();
  } catch(e) { msg.style.color = 'var(--red)'; msg.textContent = String(e); }
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
  ST.modalPage = 0;
  ST.modalSort = {col: 'created_at', dir: 'desc'};
  ST.modalDiscardFilter.clear(); ST.modalDiscardFilterNot.clear();
  ST.modalCancelFilter.clear();  ST.modalCancelFilterNot.clear();
  document.getElementById('status-modal-backdrop').style.display = 'flex';
  renderStatusModal();
}

function closeStatusModal() {
  document.getElementById('status-modal-backdrop').style.display = 'none';
  ST.modalStatus = null;
  ST.modalSelected.clear();
  ST.modalBulkOpen = false;
}

const _MODAL_STATUS_ORDER = ['scanning','pending','assigned','processing','complete','discarded','cancelled','error','duplicate'];

function navigateStatusModal(dir) {
  const idx = _MODAL_STATUS_ORDER.indexOf(ST.modalStatus);
  if (idx === -1) return;
  const next = _MODAL_STATUS_ORDER[(idx + dir + _MODAL_STATUS_ORDER.length) % _MODAL_STATUS_ORDER.length];
  openStatusModal(next);
}

document.addEventListener('keydown', e => {
  if (!ST.modalStatus) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft')  { e.preventDefault(); navigateStatusModal(-1); }
  if (e.key === 'ArrowRight') { e.preventDefault(); navigateStatusModal(1); }
  if (e.key === 'Escape')     { closeStatusModal(); }
});

function _modalSortTh(label, col, right) {
  const active = ST.modalSort.col === col;
  const arrow = active ? (ST.modalSort.dir === 'asc' ? ' ↑' : ' ↓') : '';
  const base = `padding:0 12px 0 0;font-weight:500;white-space:nowrap;cursor:pointer;user-select:none;text-align:${right?'right':'left'};`;
  const color = active ? 'color:var(--text);' : 'color:var(--text-dim);';
  return `<th style="${base}${color}" onclick="setModalSort('${col}')">${label}${arrow}</th>`;
}

function _modalCols(status) {
  // Returns array of {key, label, right?, th(), td(f, workers)}
  const mono = 'font-family:\'IBM Plex Mono\',monospace;white-space:nowrap;color:var(--text-dim)';
  const cell = (content, extra) => `<td style="padding:7px 12px 7px 0;${extra||mono}">${content}</td>`;
  const cols = {
    path: {
      key: 'file_path', label: 'Path',
      td: (f) => `<td style="padding:7px 12px 7px 0;font-family:'IBM Plex Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:320px" title="${esc(f.file_path)}">${esc(stripPrefix(f.file_path))}</td>`,
    },
    status: {
      key: 'status', label: 'Status',
      td: (f) => `<td style="padding:7px 12px 7px 0;white-space:nowrap">${badge(f.status)}</td>`,
    },
    worker: {
      key: 'worker_id', label: 'Worker',
      td: (f, workers) => { const w = workers.find(w => w.config_id === f.worker_id); return cell(w ? esc(w.hostname) : '<span style="color:var(--text-faint)">—</span>', `${mono};color:var(--accent)`); },
    },
    resolution: {
      key: 'resolution', label: 'Resolution',
      td: (f) => cell(fmtResolution(f.width, f.height)),
    },
    cancelReason: {
      key: 'cancel_reason', label: 'Reason',
      td: (f) => {
        if (!f.cancel_reason) return cell('—');
        if (f.cancel_reason === 'user') return `<td style="padding:7px 12px 7px 0">${badge('user')}</td>`;
        const tip = f.cancel_detail ? ` title="${esc(f.cancel_detail)}"` : '';
        return `<td style="padding:7px 12px 7px 0"><span${tip} style="cursor:${f.cancel_detail?'help':'default'}">${badge('auto')}</span></td>`;
      },
    },
    discardReason: {
      key: 'discard_reason', label: 'Reason',
      td: (f) => {
        if (!f.discard_reason) return cell('—');
        if (f.discard_reason === 'hevc') return `<td style="padding:7px 12px 7px 0"><span class="badge badge-discarded">HEVC</span></td>`;
        if (f.discard_reason === 'corrupt') return `<td style="padding:7px 12px 7px 0"><span class="badge badge-error">Corrupt</span></td>`;
        if (f.discard_reason === 'truncated') return `<td style="padding:7px 12px 7px 0"><span class="badge badge-cancelled">Truncated</span></td>`;
        return cell(f.discard_reason);
      },
    },
    size: {
      key: 'file_size', label: 'Size', right: true,
      td: (f) => cell(fmtBytes(f.file_size), `${mono};text-align:right`),
    },
    original: {
      key: 'file_size', label: 'Original', right: true,
      td: (f) => cell(fmtBytes(f.file_size), `${mono};text-align:right`),
    },
    saved: {
      key: 'saved', label: 'Saved', right: true,
      td: (f) => { const s = (f.file_size&&f.output_size) ? f.file_size-f.output_size : 0; const pct = f.file_size ? Math.round(s/f.file_size*100) : 0; return cell(pct > 0 ? `${pct}%` : '—', `${mono};text-align:right;color:${pct>0?'var(--green)':'var(--text-faint)'}`); },
    },
    added: {
      key: 'created_at', label: 'Added',
      td: (f) => cell(fmtDate(f.created_at)),
    },
    finished: {
      key: 'finished_at', label: 'Finished',
      td: (f) => cell(fmtDate(f.finished_at)),
    },
  };
  switch (status) {
    case 'scanning':   return [cols.path, cols.size, cols.added];
    case 'pending':    return [cols.path, cols.resolution, cols.size, cols.added];
    case 'assigned':   return [cols.path, cols.worker, cols.resolution, cols.size, cols.added];
    case 'processing': return [cols.path, cols.worker, cols.resolution, cols.size, cols.added];
    case 'complete':   return [cols.path, cols.worker, cols.resolution, cols.original, cols.saved, cols.added, cols.finished];
    case 'cancelled':  return [cols.path, cols.worker, cols.resolution, cols.original, cols.saved, cols.added, cols.finished, cols.cancelReason];
    case 'error':      return [cols.path, cols.worker, cols.resolution, cols.size, cols.added, cols.finished];
    case 'discarded':  return [cols.path, cols.size, cols.added, cols.finished, cols.discardReason];
    case 'duplicate':  return [cols.path, cols.size, cols.added];
    default:           return [cols.path, cols.status, cols.worker, cols.resolution, cols.size, cols.added, cols.finished];
  }
}

function renderStatusModal() {
  if (!ST.modalStatus) return;
  const status = ST.modalStatus;
  const files = (ST.data && ST.data.files) || [];
  const workers = (ST.data && ST.data.workers) || [];
  let filtered = status === 'all' ? files : files.filter(f => f.status === status);

  // Discard reason filter chips
  const discardReasons = ['hevc', 'corrupt', 'truncated'];
  const discardCounts = status === 'discarded'
    ? Object.fromEntries(discardReasons.map(r => [r, filtered.filter(f => f.discard_reason === r).length]))
    : {};
  if (status === 'discarded') {
    if (ST.modalDiscardFilterNot.size > 0) filtered = filtered.filter(f => !ST.modalDiscardFilterNot.has(f.discard_reason));
    if (ST.modalDiscardFilter.size > 0)    filtered = filtered.filter(f => ST.modalDiscardFilter.has(f.discard_reason));
  }

  // Cancel reason filter chips
  const cancelReasons = ['user', 'auto'];
  const cancelCounts = status === 'cancelled'
    ? Object.fromEntries(cancelReasons.map(r => [r, filtered.filter(f => f.cancel_reason === r).length]))
    : {};
  if (status === 'cancelled') {
    if (ST.modalCancelFilterNot.size > 0) filtered = filtered.filter(f => !ST.modalCancelFilterNot.has(f.cancel_reason));
    if (ST.modalCancelFilter.size > 0)    filtered = filtered.filter(f => ST.modalCancelFilter.has(f.cancel_reason));
  }

  const labels = {
    all:'All Files', scanning:'Probing', pending:'Pending', assigned:'Assigned',
    processing:'Processing', complete:'Complete', discarded:'Discarded',
    cancelled:'Cancelled', error:'Error', duplicate:'Duplicate',
  };

  const cols = _modalCols(status);

  const {col, dir} = ST.modalSort;
  const m = dir === 'asc' ? 1 : -1;
  const sorted = [...filtered].sort((a, b) => {
    switch (col) {
      case 'file_path':   return m * (a.file_path||'').localeCompare(b.file_path||'');
      case 'status':      return m * (a.status||'').localeCompare(b.status||'');
      case 'worker_id':   return m * (a.worker_id||'').localeCompare(b.worker_id||'');
      case 'file_size':   return m * ((a.file_size||0) - (b.file_size||0));
      case 'resolution':  return m * ((a.width||0)*(a.height||0) - (b.width||0)*(b.height||0));
      case 'saved':       return m * (((a.file_size||0)-(a.output_size||0)) - ((b.file_size||0)-(b.output_size||0)));
      case 'cancel_reason': return m * (a.cancel_reason||'').localeCompare(b.cancel_reason||'');
      case 'discard_reason': return m * (a.discard_reason||'').localeCompare(b.discard_reason||'');
      case 'finished_at': return m * (a.finished_at||'').localeCompare(b.finished_at||'');
      default:            return m * (a.created_at||'').localeCompare(b.created_at||'');
    }
  });

  const totalPages = Math.max(1, Math.ceil(sorted.length / FILES_PAGE_SIZE));
  const page = Math.min(ST.modalPage, totalPages - 1);
  const pageFiles = sorted.slice(page * FILES_PAGE_SIZE, (page + 1) * FILES_PAGE_SIZE);
  const pageIds = pageFiles.map(f => f.id);

  const nSel = ST.modalSelected.size;
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => ST.modalSelected.has(id));
  const somePageSelected = pageIds.some(id => ST.modalSelected.has(id));
  const allPagesSelectable = allPageSelected && nSel < filtered.length;

  document.getElementById('status-modal-title').textContent =
    `${labels[status] || status} — ${filtered.length} file${filtered.length !== 1 ? 's' : ''}`;

  const body = document.getElementById('status-modal-body');

  const paginationBar = totalPages > 1 ? `
    <div class="pagination-bar" style="border-top:1px solid var(--border)">
      <button class="btn btn-sm" onclick="setModalPage(${page-1})" ${page===0?'disabled':''}>←</button>
      ${Array.from({length: totalPages}, (_,i) => {
        if (totalPages <= 7 || i === 0 || i === totalPages-1 || Math.abs(i - page) <= 1)
          return `<button class="btn btn-sm${i===page?' btn-primary':''}" onclick="setModalPage(${i})">${i+1}</button>`;
        else if (Math.abs(i - page) === 2)
          return `<span style="color:var(--text-faint);padding:0 2px">…</span>`;
        return '';
      }).filter((x,i,a) => x && (x !== a[i-1])).join('')}
      <button class="btn btn-sm" onclick="setModalPage(${page+1})" ${page===totalPages-1?'disabled':''}>→</button>
      <span style="color:var(--text-faint);font-size:12px;margin-left:4px">${sorted.length} files</span>
      <select class="input" style="margin-left:auto;width:auto;padding:2px 6px;font-size:12px" onchange="setPageSize(+this.value)">
        ${FILES_PAGE_SIZES.map(n => `<option value="${n}"${n===FILES_PAGE_SIZE?' selected':''}>${n} / page</option>`).join('')}
      </select>
    </div>` : `
    <div class="pagination-bar" style="border-top:1px solid var(--border);justify-content:flex-end">
      <select class="input" style="width:auto;padding:2px 6px;font-size:12px" onchange="setPageSize(+this.value)">
        ${FILES_PAGE_SIZES.map(n => `<option value="${n}"${n===FILES_PAGE_SIZE?' selected':''}>${n} / page</option>`).join('')}
      </select>
    </div>`;

  const selectBanner = allPagesSelectable ? `
    <div class="select-all-banner">
      ${nSel} files on this page selected —
      <a href="#" onclick="selectAllModalFiles(event)">Select all ${filtered.length} matching files</a>
    </div>` : nSel > 0 && nSel >= filtered.length && totalPages > 1 ? `
    <div class="select-all-banner">
      All ${nSel} matching files selected —
      <a href="#" onclick="ST.modalSelected.clear();renderStatusModal()">Clear selection</a>
    </div>` : '';

  const colSpan = cols.length + 2; // +1 checkbox, +1 clear button col

  const thead = nSel > 0 ? `
    <thead><tr style="height:36px;font-size:11px;border-bottom:1px solid var(--border-subtle);background:var(--accent-glow)">
      <th style="width:36px;padding:0 0 0 14px;font-weight:500">
        <input type="checkbox" ${allPageSelected?'checked':''} onchange="toggleAllModal(this)" style="accent-color:var(--accent)">
      </th>
      <th style="padding:0;font-weight:500;text-align:left" colspan="${cols.length}">
        <span style="color:var(--accent);margin-right:12px">${nSel} selected</span>
        <div class="dropdown" id="modal-bulk-dropdown" style="display:inline-block">
          <button class="btn btn-sm" onclick="toggleModalBulkMenu(event)" style="display:inline-flex;align-items:center;gap:6px">
            <span>Actions…</span>${svgIcon('chevronDown',12)}
          </button>
          ${ST.modalBulkOpen ? `
          <div class="dropdown-menu">
            <div class="dropdown-item" onclick="modalBulkSetStatus('pending')">Set → Pending</div>
            <div class="dropdown-item" onclick="modalBulkSetStatus('cancelled')">Set → Cancelled</div>
            ${status === 'cancelled' ? `
            <div class="dropdown-item" onclick="modalBulkForceEncode(false)">Re-encode</div>
            <div class="dropdown-item" onclick="modalBulkForceEncode(true)">Re-encode (skip size check)</div>` : ''}
            ${status === 'discarded' ? `
            <div class="dropdown-item" onclick="modalBulkForceEncode(false)">Force encode</div>
            <div class="dropdown-item" onclick="modalBulkForceEncode(true)">Force encode (skip size check)</div>` : ''}
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
      <th style="width:36px;padding:0 0 0 14px;font-weight:500"></th>
      ${cols.map(c => _modalSortTh(c.label, c.key, c.right)).join('')}
    </tr></thead>`;

  const _modalFilterChips = (reasons, counts, activeSet, notSet, toggleFn) => `
    <div class="filter-bar" style="padding:8px 14px;border-bottom:1px solid var(--border)">
      <div class="filter-chip ${activeSet.size === 0 && notSet.size === 0 ? 'active' : ''}" onclick="${toggleFn}('all',event)">
        All <span style="opacity:0.6;font-size:11px">(${Object.values(counts).reduce((a,b)=>a+b,0)})</span>
      </div>
      ${reasons.map(r => {
        const cls = notSet.has(r) ? 'not' : activeSet.has(r) ? 'active' : '';
        return `<div class="filter-chip ${cls}" onclick="${toggleFn}('${r}',event)">
          ${r[0].toUpperCase()+r.slice(1)} <span style="opacity:0.6;font-size:11px">(${counts[r]||0})</span>
        </div>`;
      }).join('')}
    </div>`;

  const discardFilterBar = status === 'discarded'
    ? _modalFilterChips(discardReasons, discardCounts, ST.modalDiscardFilter, ST.modalDiscardFilterNot, 'toggleModalDiscardFilter')
    : status === 'cancelled'
    ? _modalFilterChips(cancelReasons, cancelCounts, ST.modalCancelFilter, ST.modalCancelFilterNot, 'toggleModalCancelFilter')
    : '';

  body.innerHTML = `
    ${discardFilterBar}
    ${selectBanner}
    <table style="width:100%;border-collapse:collapse">
      ${thead}
      <tbody>
        ${pageFiles.length === 0
          ? `<tr><td colspan="${colSpan}"><div class="modal-empty">No files with this status.</div></td></tr>`
          : pageFiles.map(f => {
              const isSel = ST.modalSelected.has(f.id);
              const bg = isSel ? 'var(--accent-glow)' : '';
              const hoverBg = isSel ? 'var(--accent-glow)' : 'var(--surface2)';
              return `<tr style="background:${bg};font-size:12px;border-bottom:1px solid var(--border-subtle)" onmouseenter="this.style.background='${hoverBg}'" onmouseleave="this.style.background='${bg}'">
                <td style="padding:7px 0 7px 14px">
                  <input type="checkbox" ${isSel?'checked':''} onchange="toggleModalFile(${f.id})" style="accent-color:var(--accent)">
                </td>
                ${cols.map(c => c.td(f, workers)).join('')}
              </tr>`;
            }).join('')}
      </tbody>
    </table>
    ${paginationBar}`;

  const hdr = body.querySelector('thead input[type="checkbox"]');
  if (hdr) hdr.indeterminate = somePageSelected && !allPageSelected;
}

function toggleModalFile(id) {
  if (ST.modalSelected.has(id)) ST.modalSelected.delete(id);
  else ST.modalSelected.add(id);
  renderStatusModal();
}

function toggleAllModal(src) {
  const files = (ST.data && ST.data.files) || [];
  const filtered = ST.modalStatus === 'all' ? files : files.filter(f => f.status === ST.modalStatus);
  const {col, dir} = ST.modalSort; const m = dir==='asc'?1:-1;
  const sorted = [...filtered].sort((a,b) => {
    switch(col) {
      case 'file_path':   return m*(a.file_path||'').localeCompare(b.file_path||'');
      case 'status':      return m*(a.status||'').localeCompare(b.status||'');
      case 'worker_id':   return m*(a.worker_id||'').localeCompare(b.worker_id||'');
      case 'file_size':   return m*((a.file_size||0)-(b.file_size||0));
      case 'resolution':  return m*((a.width||0)*(a.height||0)-(b.width||0)*(b.height||0));
      case 'saved':       return m*(((a.file_size||0)-(a.output_size||0))-((b.file_size||0)-(b.output_size||0)));
      case 'finished_at': return m*(a.finished_at||'').localeCompare(b.finished_at||'');
      default:            return m*(a.created_at||'').localeCompare(b.created_at||'');
    }
  });
  const page = Math.min(ST.modalPage, Math.max(0, Math.ceil(sorted.length/FILES_PAGE_SIZE)-1));
  const pageIds = sorted.slice(page*FILES_PAGE_SIZE, (page+1)*FILES_PAGE_SIZE).map(f=>f.id);
  if (src.checked) pageIds.forEach(id => ST.modalSelected.add(id));
  else ST.modalSelected.clear();
  renderStatusModal();
}

function selectAllModalFiles(e) {
  e.preventDefault();
  const files = (ST.data && ST.data.files) || [];
  const filtered = ST.modalStatus === 'all' ? files : files.filter(f => f.status === ST.modalStatus);
  filtered.forEach(f => ST.modalSelected.add(f.id));
  renderStatusModal();
}

function _toggleModalFilter(r, event, include, not, render) {
  const alt = event && (event.altKey || event.ctrlKey);
  const shift = event && event.shiftKey;
  if (r === 'all') {
    include.clear(); not.clear();
  } else if (shift) {
    if (not.has(r)) { not.delete(r); } else { not.add(r); include.delete(r); }
  } else if (alt) {
    if (include.has(r)) { include.delete(r); } else { include.add(r); not.delete(r); }
  } else {
    if (include.size > 1 && include.has(r)) {
      include.delete(r);
    } else {
      const wasOnly = include.size === 1 && include.has(r) && not.size === 0;
      include.clear(); not.clear();
      if (!wasOnly) include.add(r);
    }
  }
  ST.modalPage = 0;
  render();
}

function toggleModalDiscardFilter(r, event) {
  _toggleModalFilter(r, event, ST.modalDiscardFilter, ST.modalDiscardFilterNot, renderStatusModal);
}

function toggleModalCancelFilter(r, event) {
  _toggleModalFilter(r, event, ST.modalCancelFilter, ST.modalCancelFilterNot, renderStatusModal);
}

function setModalSort(col) {
  if (ST.modalSort.col === col) {
    ST.modalSort.dir = ST.modalSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    ST.modalSort = {col, dir: (col === 'created_at' || col === 'finished_at') ? 'desc' : 'asc'};
  }
  ST.modalPage = 0;
  renderStatusModal();
}

function setModalPage(p) {
  ST.modalPage = p;
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

async function modalBulkForceEncode(skipSizeCheck) {
  const ids = [...ST.modalSelected];
  if (!ids.length) return;
  ST.modalBulkOpen = false;
  try {
    const r = await fetch('/data/files/force-encode', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids, skip_size_check: skipSizeCheck}) });
    if (!r.ok) throw new Error(await r.text());
    toast(`Queued ${ids.length} file(s) for re-encode`, 'success');
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
