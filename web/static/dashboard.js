// ── Shared constants ──────────────────────────────────────────────────────
const _ENC_COLORS = {
  libx265:      { bg:'#e3f2fd', color:'#1565c0' },
  nvenc:        { bg:'#e8f5e9', color:'#2e7d32' },
  vaapi:        { bg:'#fff3e0', color:'#e65100' },
  videotoolbox: { bg:'#f3e5f5', color:'#6a1b9a' },
};
function _encBadge(enc) {
  if (!enc) return '<span style="color:#aaa">—</span>';
  const c = _ENC_COLORS[enc] || { bg:'#f5f5f5', color:'#666' };
  return `<span style="background:${c.bg};color:${c.color};padding:.1rem .35rem;border-radius:3px;font-size:.7rem;font-weight:700;white-space:nowrap">${_esc(enc)}</span>`;
}

const _ST_COLORS = {
  pending:    { bg:'#f5f5f5', color:'#666' },
  assigned:   { bg:'#fff3e0', color:'#e65100' },
  processing: { bg:'#e3f2fd', color:'#1565c0' },
  complete:   { bg:'#e8f5e9', color:'#2e7d32' },
  discarded:  { bg:'#f5f5f5', color:'#aaa' },
  cancelled:  { bg:'#fbe9e7', color:'#bf360c' },
  error:      { bg:'#ffebee', color:'#c62828' },
  duplicate:  { bg:'#ede7f6', color:'#4527a0' },
};

// ── Dashboard file table ──────────────────────────────────────────────────
let _dashFiles  = [];
let _dashSlaves = [];
let _dashFilter = new Set();
let _dashPage   = 1;
let _dashQuery  = '';
let _dashPerPage = parseInt(localStorage.getItem('dashPerPage') || '50', 10);

function _dashFiltered() {
  let result = _dashFiles;
  if (_dashFilter.size) result = result.filter(f => _dashFilter.has(f.status));
  if (_dashQuery) {
    const q = _norm(_dashQuery);
    result = result.filter(f =>
      _norm(f.file_name).includes(q) ||
      _norm(f.file_path).includes(q) ||
      _norm(f.slave_id).includes(q)
    );
  }
  return result;
}

function _setDashFilter(s) {
  if (s === null) {
    _dashFilter.clear();
  } else if (_dashFilter.has(s)) {
    _dashFilter.delete(s);
  } else {
    _dashFilter.add(s);
  }
  _dashPage = 1;
  _renderDashFiles();
}

function _dashUpdateSel() {
  const n = document.querySelectorAll('.dash-row-chk:checked').length;
  const el = document.getElementById('dash-sel-count');
  if (el) el.textContent = n ? `${n} selected` : '';
  document.querySelectorAll('.dash-bulk-btn').forEach(b => b.disabled = n === 0);
  const sel = document.getElementById('dash-assign-sel');
  if (sel) sel.disabled = n === 0;
}

function _dashToggleAll(src) {
  document.querySelectorAll('.dash-row-chk').forEach(c => c.checked = src.checked);
  _dashUpdateSel();
}

function _dashSelectedIds() {
  return [...document.querySelectorAll('.dash-row-chk:checked')].map(el => +el.value);
}

async function bulkDashDelete() {
  const ids = _dashSelectedIds();
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} record(s)?`)) return;
  await fetch('/data/files/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids}),
  });
  const r = await fetch('/data/dashboard');
  if (r.ok) _applyDashboard(await r.json());
}

async function bulkDashPending() {
  const ids = _dashSelectedIds();
  if (!ids.length) return;
  await fetch('/data/files/pending', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids}),
  });
  const r = await fetch('/data/dashboard');
  if (r.ok) _applyDashboard(await r.json());
}

async function bulkDashAssign(slaveConfigId) {
  const ids = _dashSelectedIds();
  if (!ids.length) return;
  await fetch('/data/files/assign', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids, slave_config_id: slaveConfigId}),
  });
  const r = await fetch('/data/dashboard');
  if (r.ok) _applyDashboard(await r.json());
}

async function bulkDashCancel() {
  const ids = _dashSelectedIds();
  if (!ids.length) return;
  await fetch('/data/files/cancel', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids}),
  });
  const r = await fetch('/data/dashboard');
  if (r.ok) _applyDashboard(await r.json());
}

function _renderDashFiles() {
  const filtered = _dashFiltered();
  const total    = filtered.length;
  const pages    = Math.max(1, Math.ceil(total / _dashPerPage));
  if (_dashPage > pages) _dashPage = pages;
  const slice = filtered.slice((_dashPage - 1) * _dashPerPage, _dashPage * _dashPerPage);

  // File count
  const cntEl = document.getElementById('dash-file-count');
  if (cntEl) cntEl.textContent = _dashFiles.length;

  // Status filter buttons
  const base   = 'border:none;border-radius:3px;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;font-family:inherit;padding:.18rem .52rem;';
  const shadow = 'box-shadow:inset 0 0 0 1.5px currentColor;';
  let filters  = '<div style="display:flex;gap:.3rem;flex-wrap:wrap;margin-bottom:.55rem">';
  const allActive = _dashFilter.size === 0;
  filters += `<button onclick="_setDashFilter(null)" style="${base}background:${allActive?'#e8eaf6':'#f0f0f0'};color:#3949ab;${allActive?shadow:''}">All</button>`;
  for (const [s, c] of Object.entries(_ST_COLORS)) {
    const n = _dashFiles.filter(f => f.status === s).length;
    if (!n) continue;
    const active = _dashFilter.has(s);
    filters += `<button onclick="_setDashFilter('${s}')" style="${base}background:${c.bg};color:${c.color};${active?shadow:''}">${s} (${n})</button>`;
  }
  filters += '</div>';
  const filtersEl = document.getElementById('dash-status-filters');
  if (filtersEl) filtersEl.innerHTML = filters;

  // Search + action bar
  let h = `<input type="text" class="modal-search" id="dash-search" placeholder="Filter by filename, path or slave…"
              value="${_esc(_dashQuery)}" oninput="_dashQuery=this.value;_dashPage=1;_renderDashFiles()">
    <div class="modal-bar">
      <select onchange="_dashPerPage=+this.value;localStorage.setItem('dashPerPage',this.value);_dashPage=1;_renderDashFiles()"
        style="padding:.22rem .4rem;border:1px solid var(--border-input);border-radius:4px;font-size:.78rem;font-family:inherit;background:var(--surface);color:var(--text)">
        ${[25,50,100,250].map(n=>`<option value="${n}"${n===_dashPerPage?' selected':''}>${n} per page</option>`).join('')}
      </select>
      <span class="sel-count" id="dash-sel-count"></span>
      <div class="modal-bar-right">
        <button class="btn-act dash-bulk-btn" disabled onclick="bulkDashPending()">Set to pending</button>
        <button class="btn-act dash-bulk-btn" disabled onclick="bulkDashCancel()">Set to cancelled</button>
        <button class="btn-act danger dash-bulk-btn" disabled onclick="bulkDashDelete()">Delete selected</button>
        ${(() => { const assignable = _dashSlaves.filter(s => s.state !== 'unreachable' && !s.unconfigured); return assignable.length ? `<select id="dash-assign-sel" disabled onchange="if(this.value){bulkDashAssign(this.value);this.value=''}" style="padding:.22rem .4rem;border:1px solid var(--border-input);border-radius:4px;font-size:.78rem;font-family:inherit;background:var(--surface);color:var(--text);cursor:pointer"><option value="">Assign to slave…</option>${assignable.map(s=>`<option value="${_esc(s.config_id)}">${_esc(s.config_id)}</option>`).join('')}</select>` : ''; })()}
      </div>
    </div>`;

  // Table
  h += '<div style="overflow-x:auto"><table class="modal-table"><thead><tr>';
  h += `<th><input type="checkbox" class="chk-all" onchange="_dashToggleAll(this)"></th>`;
  h += '<th>ID</th><th>Filename</th><th>Status</th><th>Slave</th><th>Source</th><th>Output</th><th>Duration</th><th>Finished</th>';
  h += '</tr></thead><tbody>';
  if (!slice.length) {
    const msg = total === 0 && _dashQuery ? 'No results for this search.' : 'No files.';
    h += `<tr><td colspan="9" style="color:#aaa;text-align:center;padding:.8rem">${msg}</td></tr>`;
  } else {
    for (const f of slice) {
      h += `<tr>
        <td><input type="checkbox" class="dash-row-chk" value="${f.id}" onchange="_dashUpdateSel()"></td>
        <td>${f.id}</td>
        <td><span class="modal-fname" title="${_esc(f.file_path)}">${_esc(f.file_name)}</span></td>
        <td>${stBadge(f.status, f)}</td>
        <td>${f.slave_id ? _esc(f.slave_id) : '—'}</td>
        <td>${fmtBytes(f.file_size)}</td>
        <td>${fmtBytes(f.output_size)}</td>
        <td>${fmtDuration(f.started_at, f.finished_at)}</td>
        <td>${fmtDate(f.finished_at)}</td>
      </tr>`;
    }
  }
  h += '</tbody></table></div>';

  // Pagination
  if (pages > 1) {
    h += `<div class="modal-pagination">
      <button class="btn-act" onclick="_dashPage--;_renderDashFiles()" ${_dashPage<=1?'disabled':''}>← Prev</button>
      <span class="pag-info">Page ${_dashPage} of ${pages} &nbsp;·&nbsp; ${total} rows</span>
      <button class="btn-act" onclick="_dashPage++;_renderDashFiles()" ${_dashPage>=pages?'disabled':''}>Next →</button>
    </div>`;
  } else if (total > 0) {
    h += `<div class="modal-pagination"><span class="pag-info">${total} row${total!==1?'s':''}</span></div>`;
  }

  const prevChecked = new Set(_dashSelectedIds());
  const searchWasActive = document.activeElement?.id === 'dash-search';
  const tblEl = document.getElementById('dash-file-table');
  if (tblEl) tblEl.innerHTML = h;
  // Restore checked state
  document.querySelectorAll('.dash-row-chk').forEach(c => {
    if (prevChecked.has(+c.value)) c.checked = true;
  });
  const dashAllChk = document.querySelector('#dash-file-table .chk-all');
  if (dashAllChk) {
    const total   = document.querySelectorAll('.dash-row-chk').length;
    const checked = document.querySelectorAll('.dash-row-chk:checked').length;
    dashAllChk.checked       = total > 0 && checked === total;
    dashAllChk.indeterminate = checked > 0 && checked < total;
  }
  if (searchWasActive) {
    const el = document.getElementById('dash-search');
    if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }
  _dashUpdateSel();
}

// ── Auto-refresh (smooth, no page reload) ────────────────────────────────
let _refreshTimer = null;

function _pauseRefresh() { clearTimeout(_refreshTimer); }
function _resumeRefresh() { _refreshTimer = setTimeout(_dashRefresh, 3000); }

async function _dashRefresh() {
  try {
    const r = await fetch('/data/dashboard');
    if (r.ok) _applyDashboard(await r.json());
  } catch(e) {}
  if (!_ctx) _resumeRefresh();
}

function _applyDashboard(data) {
  // Master error / content
  const errEl     = document.getElementById('master-error');
  const contentEl = document.getElementById('master-content');
  if (data.master_error) {
    errEl?.classList.remove('hidden');
    contentEl?.classList.add('hidden');
    const msg = document.getElementById('master-error-msg');
    if (msg) msg.textContent = data.master_error;
  } else {
    errEl?.classList.add('hidden');
    contentEl?.classList.remove('hidden');
    // File counts
    for (const [s, n] of Object.entries(data.file_counts || {})) {
      const el = document.getElementById('cnt-' + s);
      if (el) el.textContent = n;
    }
    // Scan live area
    const scanEl = document.getElementById('scan-live');
    if (scanEl && data.scan) scanEl.innerHTML = _scanLiveHtml(data.scan);
  }
  // File table
  if (data.files) {
    _dashFiles = data.files.slice().sort((a, b) => b.id - a.id);
    _renderDashFiles();
  }

  // Slave section
  const cntEl = document.getElementById('slave-count');
  const secEl = document.getElementById('slave-section');
  const slaves = data.slaves || [];
  _dashSlaves = slaves;
  if (cntEl) cntEl.textContent = slaves.length;
  if (secEl) {
    // Lock current height before updating so the section can only grow, never shrink.
    // This prevents the file table from jumping when a slave card changes between states.
    secEl.style.minHeight = secEl.offsetHeight + 'px';
    if (!slaves.length) {
      secEl.innerHTML = '<p style="color:#aaa;font-size:.9rem;margin-top:.5rem">No slaves registered.</p>';
    } else {
      secEl.innerHTML = '<div class="slave-grid">' + slaves.map(_slaveCardHtml).join('') + '</div>';
    }
  }
}

function _scanLiveHtml(scan) {
  if (scan.running) {
    return `<span class="badge badge-scanning">Scanning</span>
      <div class="scan-stats">
        <span>Found: ${scan.found}</span>
        <span>Skipped: ${scan.skipped}</span>
        ${scan.errors ? `<span class="scan-err">Errors: ${scan.errors}</span>` : ''}
      </div>
      <div class="actions" style="margin-top:.6rem">
        <form method="post" action="/actions/scan/stop">
          <button class="btn-act danger" type="submit">Stop scan</button>
        </form>
        ${scan.path ? `<span style="font-size:.76rem;color:#aaa;align-self:center">${_esc(scan.path)}</span>` : ''}
      </div>`;
  }
  return `<span class="badge badge-idle">Scan idle</span>
    <div class="actions" style="margin-top:.6rem">
      <form method="post" action="/actions/scan/start">
        <button class="btn-act" type="submit">Start scan</button>
      </form>
      ${scan.path ? `<span style="font-size:.76rem;color:#aaa;align-self:center">${_esc(scan.path)}</span>` : ''}
    </div>`;
}

function _slaveCardHtml(s) {
  const badge = s.state === 'unreachable'
    ? '<span class="badge badge-unreachable">Unreachable</span>'
    : s.unconfigured ? '<span class="badge badge-unconfigured">Unconfigured</span>'
    : s.disk_full ? '<span class="badge badge-disk-full">Disk full</span>'
    : s.sleeping ? '<span class="badge badge-sleeping">Sleeping</span>'
    : s.paused   ? '<span class="badge badge-paused">Paused</span>'
    : s.state === 'processing' ? `<span class="badge badge-processing">${s.drain ? 'Draining' : 'Converting'}</span>`
    : s.drain    ? '<span class="badge badge-drain">Draining</span>'
    : '<span class="badge badge-idle">Idle</span>';

  let h = `<div class="slave-card" data-host="${_esc(s.host)}" data-port="${s.api_port}" data-name="${_esc(s.config_id)}"
    onclick="showSlave(this.dataset.host,+this.dataset.port,this.dataset.name)">
    <div class="slave-head">
      <div><div class="slave-name">${_esc(s.config_id)}</div>
      <div class="slave-host">${_esc(s.host)}:${s.api_port}</div></div>
      ${badge}
    </div>`;

  if (s.state !== 'unreachable') {
    h += `<div class="meta-row"><span>Queue</span><span>${s.queued} job${s.queued!==1?'s':''}</span></div>`;
    if (!s.unconfigured)
      h += `<div class="meta-row"><span>Encoder</span><span>${_encBadge(s.encoder)}</span></div>`;
  }

  if (s.state === 'processing' && s.progress) {
    const p = s.progress;
    const pct = Math.min(p.percent || 0, 100);
    h += `<div class="prog-wrap"><div class="prog-bar" style="width:${pct}%"></div></div>
      <div class="meta-row">
        <span>${pct.toFixed(1)}%</span>
        <span>${p.fps ? p.fps+'\u00a0fps\u00a0\u00a0' : ''}${p.speed ? p.speed+'×\u00a0\u00a0' : ''}${p.eta_seconds != null ? 'ETA\u00a0'+fmtEta(p.eta_seconds) : ''}</span>
      </div>`;
    if (p.current_size_bytes) {
      h += `<div class="meta-row"><span>Size</span><span>${fmtBytes(p.current_size_bytes)}${p.projected_size_bytes ? ' → '+fmtBytes(p.projected_size_bytes) : ''}</span></div>`;
      if (p.bitrate) h += `<div class="meta-row"><span>Bitrate</span><span>${_esc(p.bitrate)}</span></div>`;
    }
  } else if (s.state === 'processing') {
    h += '<p style="font-size:.78rem;color:#aaa;margin-top:.5rem">Waiting for progress…</p>';
  }

  if (s.state !== 'unreachable') {
    h += `<div class="actions" onclick="event.stopPropagation()">`;
    if (s.unconfigured) {
      // no buttons — user opens the modal to select encoder and activate
    } else if (s.sleeping) {
      h += _slaveBtn('/actions/slave/wake', s, 'Wake up', '');
    } else if (s.paused) {
      h += _slaveBtn('/actions/slave/resume', s, 'Resume', '') + _slaveBtn('/actions/slave/stop', s, 'Stop', 'danger');
    } else if (s.state === 'processing') {
      h += _slaveBtn('/actions/slave/pause', s, 'Pause', '');
      if (!s.drain) h += _slaveBtn('/actions/slave/drain', s, 'Finish current', 'warn');
      h += _slaveBtn('/actions/slave/stop', s, 'Stop', 'danger');
    } else if (s.drain) {
      h += _slaveBtn('/actions/slave/resume', s, 'Resume polling', '');
    } else {
      h += _slaveBtn('/actions/slave/sleep', s, 'Sleep', '');
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

function _slaveBtn(action, s, label, cls) {
  return `<form method="post" action="${action}">
    <input type="hidden" name="host" value="${_esc(s.host)}">
    <input type="hidden" name="api_port" value="${s.api_port}">
    <button class="btn-act ${cls}" type="submit">${label}</button>
  </form>`;
}

function _showCopied(anchor) {
  const existing = document.getElementById('_copy-toast');
  if (existing) existing.remove();
  const t = document.createElement('div');
  t.id = '_copy-toast';
  t.textContent = 'Copied to clipboard';
  t.style.cssText = 'position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);background:#323232;color:#fff;font-size:.8rem;padding:.45rem 1rem;border-radius:6px;pointer-events:none;opacity:1;transition:opacity .4s;z-index:9999;white-space:nowrap';
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 1800);
}

function _norm(s) {
  return String(s).toLowerCase().replace(/[^\p{L}\p{N} ]/gu, ' ').replace(/\s+/g, ' ').trim();
}

function _esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Statistics ────────────────────────────────────────────────────────────
function _fmtRatio(r) {
  return (r != null && r > 0) ? (r * 100).toFixed(1) + '%' : '—';
}

function _statsSummaryHtml(o) {
  return `<div style="display:flex;gap:2.5rem;flex-wrap:wrap;margin-bottom:1.2rem">
    ${[
      [o.jobs,                                          'Converted'],
      [fmtBytes(o.total_input_bytes),                   'Original size'],
      [fmtBytes(o.total_saved_bytes),                   'Saved'],
      [_fmtRatio(o.avg_compression_ratio),              'Avg size ratio'],
      [fmtEta(Math.round(o.avg_duration_seconds || 0)), 'Avg duration'],
    ].map(([v, lbl]) => `<div>
      <div style="font-size:1.4rem;font-weight:700;color:var(--text)">${v}</div>
      <div style="font-size:.7rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${lbl}</div>
    </div>`).join('')}
  </div>`;
}

function _fmtRange(lo, hi, fmt) {
  if (lo == null && hi == null) return '—';
  if (lo == null || hi == null) return fmt(lo ?? hi);
  if (Math.abs(lo - hi) < 0.01) return fmt(lo);
  return `${fmt(lo)} – ${fmt(hi)}`;
}

function _statsEncoderTableHtml(by_encoder) {
  const encoders = Object.entries(by_encoder || {}).sort((a, b) => b[1].jobs - a[1].jobs);
  if (!encoders.length) return '';
  const hasFps   = encoders.some(([, e]) => e.min_fps   != null);
  const hasSpeed = encoders.some(([, e]) => e.min_speed != null);
  let h = `<table class="modal-table" style="margin-bottom:1.2rem"><thead><tr>
    <th>Encoder</th><th>Jobs</th>
    <th>Min dur</th><th>Max dur</th>
    ${hasFps   ? '<th>Min fps</th><th>Max fps</th>'     : ''}
    ${hasSpeed ? '<th>Min speed</th><th>Max speed</th>' : ''}
    <th>Min ratio</th><th>Max ratio</th>
    <th>Total saved</th>
  </tr></thead><tbody>`;
  for (const [enc, e] of encoders) {
    const fmtDur = s => s != null ? fmtEta(Math.round(s)) : '—';
    const fmtFps = v => v != null ? v.toFixed(1) : '—';
    const fmtSpd = v => v != null ? v.toFixed(1) + '×' : '—';
    const fmtRat = v => v != null ? _fmtRatio(v) : '—';
    h += `<tr>
      <td>${_encBadge(enc)}</td>
      <td>${e.jobs}</td>
      <td>${fmtDur(e.min_duration_seconds)}</td>
      <td>${fmtDur(e.max_duration_seconds)}</td>
      ${hasFps   ? `<td>${fmtFps(e.min_fps)}</td><td>${fmtFps(e.max_fps)}</td>`     : ''}
      ${hasSpeed ? `<td>${fmtSpd(e.min_speed)}</td><td>${fmtSpd(e.max_speed)}</td>` : ''}
      <td>${fmtRat(e.min_size_ratio)}</td>
      <td>${fmtRat(e.max_size_ratio)}</td>
      <td>${fmtBytes(e.total_saved_bytes)}</td>
    </tr>`;
  }
  return h + '</tbody></table>';
}

function _statsDayChartHtml(by_day) {
  const days = (by_day || []).slice(-60);
  if (days.length < 2) return '';
  const maxJobs = Math.max(...days.map(d => d.jobs), 1);
  let h = `<div style="margin-top:.4rem">
    <div style="font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:.35rem">Jobs per day</div>
    <div style="display:flex;align-items:flex-end;gap:2px;height:56px">`;
  for (const d of days) {
    const pct = Math.max(Math.round((d.jobs / maxJobs) * 100), 2);
    h += `<div title="${d.date}: ${d.jobs} job${d.jobs !== 1 ? 's' : ''}, ${fmtBytes(d.saved_bytes)} saved"
      style="flex:1;min-width:3px;height:${pct}%;background:#1976d2;opacity:.55;border-radius:2px 2px 0 0"></div>`;
  }
  return h + '</div></div>';
}

function _renderStats(data) {
  const el = document.getElementById('stats-content');
  if (!el) return;
  if (!data || data.error) { el.innerHTML = '<p style="color:#aaa;font-size:.9rem">Could not load statistics.</p>'; return; }
  const o = data.overall || {};
  if (!o.jobs) { el.innerHTML = '<p style="color:#aaa;font-size:.9rem">No completed conversions yet.</p>'; return; }

  let h = _statsSummaryHtml(o);

  // Slave table (clickable rows)
  const slaves = (data.by_slave || []).sort((a, b) => b.jobs - a.jobs);
  if (slaves.length) {
    h += `<table class="modal-table" style="margin-bottom:1.2rem">
      <thead><tr><th>Slave</th><th>Jobs</th><th>Total saved</th><th>Avg size ratio</th><th>Avg duration</th></tr></thead>
      <tbody>`;
    for (const s of slaves) {
      h += `<tr style="cursor:pointer" onclick="showSlaveStats('${_esc(s.slave_id)}')" title="Click for details">
        <td>${_esc(s.slave_id)}</td>
        <td>${s.jobs}</td>
        <td>${fmtBytes(s.total_saved_bytes)}</td>
        <td>${_fmtRatio(s.avg_compression_ratio ?? null)}</td>
        <td>${fmtEta(Math.round(s.avg_duration_seconds || 0))}</td>
      </tr>`;
    }
    h += '</tbody></table>';
  }

  h += _statsDayChartHtml(data.by_day);
  el.innerHTML = h;
}

async function showSlaveStats(slaveId) {
  _ctx = { type: 'slavestats', slave_id: slaveId };
  _stopSlavePoll();
  _setModal(slaveId + ' — Statistics', '<p class="modal-note">Loading…</p>');
  try {
    const r = await fetch(`/data/stats/slave?slave_id=${encodeURIComponent(slaveId)}`);
    const data = await r.json();
    if (!data || data.error) {
      document.getElementById('modal-body').innerHTML = '<p class="modal-err">Failed to load.</p>';
      return;
    }
    const o = data.overall || {};
    if (!o.jobs) {
      document.getElementById('modal-body').innerHTML = '<p style="color:#aaa;font-size:.9rem">No completed conversions for this slave.</p>';
      return;
    }
    document.getElementById('modal-body').innerHTML =
      _statsSummaryHtml(o) +
      _statsEncoderTableHtml(data.by_encoder) +
      _statsDayChartHtml(data.by_day);
  } catch(e) {
    document.getElementById('modal-body').innerHTML = '<p class="modal-err">Failed to load.</p>';
  }
}

async function _fetchStats() {
  try {
    const r = await fetch('/data/stats');
    if (r.ok) _renderStats(await r.json());
  } catch(e) {}
  setTimeout(_fetchStats, 30000);
}

// Seed file table from server-rendered data on first load
_dashFiles = JSON.parse(document.getElementById('init-files').textContent).sort((a, b) => b.id - a.id);
_renderDashFiles();

_resumeRefresh();
_fetchStats();

// ── Slave status polling (500ms when slave modal is open) ─────────────────
let _slaveStatusTimer = null;
function _startSlavePoll(host, port) {
  _stopSlavePoll();
  _scheduleSlavePoll(host, port, 500);
}
function _stopSlavePoll() {
  if (_slaveStatusTimer) { clearTimeout(_slaveStatusTimer); _slaveStatusTimer = null; }
}
function _scheduleSlavePoll(host, port, delay) {
  _slaveStatusTimer = setTimeout(() => _doSlavePoll(host, port), delay);
}
async function _doSlavePoll(host, port) {
  _slaveStatusTimer = null;
  if (!_ctx || _ctx.type !== 'slave') return;
  try {
    const r = await fetch(`/data/slave?host=${encodeURIComponent(host)}&port=${port}`);
    if (!r.ok) { _scheduleSlavePoll(host, port, 2000); return; }
    const data = await r.json();
    const el = document.getElementById('slave-status');
    if (el) {
      const encSel = document.getElementById(`enc-${port}`);
      const savedEnc = encSel ? encSel.value : null;
      const batchInp = document.getElementById(`batch-${port}`);
      const savedBatch = batchInp ? batchInp.value : null;
      const replaceChk = document.getElementById(`replace-${port}`);
      const savedReplace = replaceChk ? replaceChk.checked : null;
      const cmdEl = document.getElementById(`ffcmd-${port}`);
      const cmdOpen = cmdEl ? cmdEl.style.display === 'block' : false;
      const focusedId = document.activeElement?.id || null;
      el.innerHTML = _slaveStatusHtml(data.status, host, port);
      if (savedEnc) {
        const newSel = document.getElementById(`enc-${port}`);
        if (newSel) newSel.value = savedEnc;
      }
      if (savedBatch) {
        const newInp = document.getElementById(`batch-${port}`);
        if (newInp) newInp.value = savedBatch;
      }
      if (savedReplace !== null) {
        const newChk = document.getElementById(`replace-${port}`);
        if (newChk) newChk.checked = savedReplace;
      }
      if (focusedId) {
        const refEl = document.getElementById(focusedId);
        if (refEl) refEl.focus();
      }
      if (cmdOpen) {
        const newCmd = document.getElementById(`ffcmd-${port}`);
        if (newCmd) newCmd.style.display = 'block';
      }
    }
    // Refresh the file table if the list has changed
    if (data.files) {
      const sorted = (data.files).slice().sort((a,b) =>
        (b.updated_at||'').localeCompare(a.updated_at||''));
      const prevIds = _allFiles.map(f=>f.id+f.status).join(',');
      const newIds  = sorted.map(f=>f.id+f.status).join(',');
      if (prevIds !== newIds) {
        _allFiles = sorted;
        _renderTable();
      }
    }
    // Fast poll only during active conversion; idle/sleeping needs no sub-second updates
    const active = data.status && data.status.state === 'processing';
    _scheduleSlavePoll(host, port, active ? 500 : 2000);
  } catch(e) {
    _scheduleSlavePoll(host, port, 2000);
  }
}
async function _refreshSlaveStatus(host, port) {
  return _doSlavePoll(host, port);
}

// ── Modal state ───────────────────────────────────────────────────────────
let _ctx           = null;  // { type:'master', status } | { type:'slave', host, port, name }
let _allFiles      = [];    // full fetched list
let _cols          = [];    // column definitions for current table
let _page          = 1;
let _query         = '';
let _statusFilter  = null;  // null = all, or a status string (slave modal only)
let _encoderFilter = null;  // null = all, or an encoder string
const _PER_PAGE    = 50;

// ── Modal open/close ──────────────────────────────────────────────────────
function _setModal(title, html) {
  _pauseRefresh();
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal').style.display = 'flex';
}
function closeModal() {
  document.getElementById('modal').style.display = 'none';
  _ctx = null;
  _stopSlavePoll();
  _dashRefresh(); // immediate refresh so cards reflect latest state
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Formatters ────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (b == null || b === 0) return '—';
  const units = ['B','KB','MB','GB','TB'];
  for (const u of units) { if (b < 1024) return Math.round(b) + '\u00a0' + u; b /= 1024; }
  return b.toFixed(1) + '\u00a0PB';
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {dateStyle:'short', timeStyle:'short'});
}
function fmtDuration(a, b) {
  if (!a || !b) return '—';
  let s = Math.round((new Date(b) - new Date(a)) / 1000);
  if (s < 0) return '—';
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm\u00a0' + String(s%60).padStart(2,'0') + 's';
  return Math.floor(s/3600) + 'h\u00a0' + String(Math.floor((s%3600)/60)).padStart(2,'0') + 'm';
}
function fmtEta(s) {
  if (s == null) return '';
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm\u00a0' + String(s%60).padStart(2,'0') + 's';
  return Math.floor(s/3600) + 'h\u00a0' + String(Math.floor((s%3600)/60)).padStart(2,'0') + 'm';
}
function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function stBadge(s, f) {
  let title = '';
  if (s === 'discarded') title = ' title="Already HEVC — no conversion needed"';
  else if (s === 'cancelled') {
    const reason = (f && f.cancel_reason) === 'auto'
      ? 'Cancelled automatically — output exceeded source size'
      : 'Cancelled by user';
    title = ` title="${reason}"`;
  }
  return `<span class="st-badge st-${s}"${title}>${s}</span>`;
}

// ── Status filter (slave modal) ───────────────────────────────────────────

function _setStatusFilter(s) {
  _statusFilter = s;
  _page = 1;
  _renderTable();
}

function _setEncoderFilter(e) {
  _encoderFilter = (e === _encoderFilter) ? null : e;
  _page = 1;
  _renderTable();
}

function _encoderFilterHtml() {
  const encoders = [...new Set(_allFiles.map(f => f.encoder).filter(Boolean))].sort();
  if (!encoders.length) return '';
  const base   = 'border:none;border-radius:3px;font-size:.68rem;font-weight:700;cursor:pointer;font-family:inherit;padding:.18rem .52rem;';
  const shadow = 'box-shadow:inset 0 0 0 1.5px currentColor;';
  let h = '<div style="display:flex;gap:.3rem;flex-wrap:wrap;margin:.2rem 0 .35rem">';
  for (const enc of encoders) {
    const c = _ENC_COLORS[enc] || { bg:'#f5f5f5', color:'#666' };
    const active = _encoderFilter === enc;
    h += `<button onclick="_setEncoderFilter('${_esc(enc)}')" style="${base}background:${c.bg};color:${c.color};${active?shadow:''}">${_esc(enc)}</button>`;
  }
  h += '</div>';
  return h;
}

function _statusFilterHtml() {
  const base = 'border:none;border-radius:3px;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;font-family:inherit;padding:.18rem .52rem;';
  const shadow = 'box-shadow:inset 0 0 0 1.5px currentColor;';
  let h = '<div style="display:flex;gap:.3rem;flex-wrap:wrap;margin:.35rem 0 .55rem">';
  const allActive = _statusFilter === null;
  h += `<button onclick="_setStatusFilter(null)" style="${base}background:${allActive?'#e8eaf6':'#f0f0f0'};color:#3949ab;${allActive?shadow:''}">All</button>`;
  for (const [s, c] of Object.entries(_ST_COLORS)) {
    const active = _statusFilter === s;
    h += `<button onclick="_setStatusFilter('${s}')" style="${base}background:${c.bg};color:${c.color};${active?shadow:''}">${s}</button>`;
  }
  h += '</div>';
  return h;
}

// ── Search & pagination ───────────────────────────────────────────────────
function _filtered() {
  let result = _allFiles;
  if (_statusFilter)  result = result.filter(f => f.status === _statusFilter);
  if (_encoderFilter) result = result.filter(f => f.encoder === _encoderFilter);
  if (_query) {
    const q = _norm(_query);
    result = result.filter(f =>
      _norm(f.file_name).includes(q) ||
      _norm(f.file_path).includes(q) ||
      _norm(f.slave_id).includes(q)
    );
  }
  return result;
}

function _renderTable() {
  const filtered = _filtered();
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / _PER_PAGE));
  if (_page > pages) _page = pages;
  const slice = filtered.slice((_page - 1) * _PER_PAGE, _page * _PER_PAGE);

  let h = '<div class="modal-table-wrap"><table class="modal-table"><thead><tr>';
  h += `<th><input type="checkbox" class="chk-all" onchange="toggleAll(this)"></th>`;
  _cols.forEach(c => h += `<th>${c.label}</th>`);
  h += '</tr></thead><tbody>';

  if (!slice.length) {
    const msg = total === 0 && _query ? 'No results for this search.' : 'No files.';
    h += `<tr><td colspan="${_cols.length + 1}" style="color:#aaa;text-align:center;padding:.8rem">${msg}</td></tr>`;
  } else {
    slice.forEach(f => {
      h += `<tr><td><input type="checkbox" class="row-chk" value="${f.id}" onchange="_updateSel()"></td>`;
      h += _cols.map(c => `<td>${c.cell(f)}</td>`).join('');
      h += '</tr>';
    });
  }
  h += '</tbody></table></div>';

  // Pagination controls
  h += `<div class="modal-pagination">`;
  if (pages > 1) {
    h += `<button class="btn-act" onclick="_goPage(${_page-1})" ${_page<=1?'disabled':''}>← Prev</button>`;
  }
  h += `<span class="pag-info">`;
  if (pages > 1) h += `Page ${_page} of ${pages} &nbsp;·&nbsp; `;
  h += `${total} row${total!==1?'s':''}</span>`;
  if (pages > 1) {
    h += `<button class="btn-act" onclick="_goPage(${_page+1})" ${_page>=pages?'disabled':''}>Next →</button>`;
  }
  h += '</div>';

  document.getElementById('tbl').innerHTML = h;
  const filtersEl = document.getElementById('status-filters');
  if (filtersEl) {
    const statusHtml  = (_ctx && _ctx.type === 'slave') ? _statusFilterHtml() : '';
    const encoderHtml = _encoderFilterHtml();
    filtersEl.innerHTML = statusHtml + encoderHtml;
  }
  const tblAllChk = document.querySelector('#tbl .chk-all');
  if (tblAllChk) {
    const total   = document.querySelectorAll('.row-chk').length;
    const checked = document.querySelectorAll('.row-chk:checked').length;
    tblAllChk.checked       = total > 0 && checked === total;
    tblAllChk.indeterminate = checked > 0 && checked < total;
  }
  _updateSel();
}

function _onSearch() {
  _query = document.getElementById('modal-search').value;
  _page = 1;
  _renderTable();
}
function _goPage(n) { _page = n; _renderTable(); }

// ── Checkbox helpers ──────────────────────────────────────────────────────
function toggleAll(src) {
  document.querySelectorAll('.row-chk').forEach(c => c.checked = src.checked);
  _updateSel();
}
function _updateSel() {
  const n = document.querySelectorAll('.row-chk:checked').length;
  const el = document.getElementById('sel-count');
  if (el) el.textContent = n ? `${n} selected` : '';
  document.querySelectorAll('.bulk-btn').forEach(b => b.disabled = n === 0);
}
function _selectedIds() {
  return [...document.querySelectorAll('.row-chk:checked')].map(el => +el.value);
}

// ── Bulk actions ──────────────────────────────────────────────────────────
async function bulkDelete() {
  const ids = _selectedIds();
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} record(s)?`)) return;
  const url = _ctx.type === 'master'
    ? '/data/files/delete'
    : `/data/slave/delete?host=${encodeURIComponent(_ctx.host)}&port=${_ctx.port}`;
  await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids})});
  _ctxReload();
}
async function bulkPending() {
  const ids = _selectedIds();
  if (!ids.length) return;
  const url = _ctx.type === 'master'
    ? '/data/files/pending'
    : `/data/slave/pending?host=${encodeURIComponent(_ctx.host)}&port=${_ctx.port}`;
  await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids})});
  _ctxReload();
}
async function bulkCancel() {
  const ids = _selectedIds();
  if (!ids.length) return;
  const url = _ctx.type === 'master'
    ? '/data/files/cancel'
    : `/data/slave/cancel?host=${encodeURIComponent(_ctx.host)}&port=${_ctx.port}`;
  await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids})});
  _ctxReload();
}
function _ctxReload() {
  if (_ctx.type === 'master') showFiles(_ctx.status);
  else showSlave(_ctx.host, _ctx.port, _ctx.name);
}

// ── Shell HTML (search + action bar + table placeholder) ─────────────────
function _shell() {
  return `<input type="text" id="modal-search" class="modal-search"
            placeholder="Filter by filename, path or slave…" oninput="_onSearch()">
    <div id="status-filters"></div>
    <div class="modal-bar">
      <span class="sel-count" id="sel-count"></span>
      <div class="modal-bar-right">
        <button class="btn-act bulk-btn" disabled onclick="bulkPending()">Set to pending</button>
        <button class="btn-act bulk-btn" disabled onclick="bulkCancel()">Set to cancelled</button>
        <button class="btn-act danger bulk-btn" disabled onclick="bulkDelete()">Delete selected</button>
      </div>
    </div>
    <div id="tbl"></div>`;
}

// ── Master files modal ────────────────────────────────────────────────────
async function showFiles(status) {
  if (status === 'duplicate') { showDuplicates(); return; }
  _ctx = { type:'master', status };
  _page = 1; _query = ''; _allFiles = []; _statusFilter = null; _encoderFilter = null;
  _cols = fileColumns(status);
  _setModal(cap(status) + ' files',
    _shell() + '<p class="modal-note" style="margin-top:.5rem">Loading…</p>');
  try {
    const r = await fetch('/data/files?status=' + status);
    _allFiles = await r.json();
    _sortFiles(status);
    _renderTable();
  } catch(e) {
    document.getElementById('tbl').innerHTML = '<p class="modal-err">Failed to load.</p>';
  }
}

async function showDuplicates() {
  _setModal('Duplicate files', '<p class="modal-note">Loading…</p>');
  try {
    const r = await fetch('/data/files/duplicate-pairs');
    const pairs = await r.json();
    if (!pairs.length) {
      document.getElementById('modal-body').innerHTML = '<p class="modal-note">No duplicates found.</p>';
      return;
    }
    const rows = pairs.map(p => `
      <tr>
        <td style="padding:.3rem .5rem;color:#888;font-size:.8rem">${p.id}</td>
        <td style="padding:.3rem .5rem;font-size:.85rem;word-break:break-all">${_esc(p.file_path)}</td>
        <td style="padding:.3rem .5rem;color:#888;font-size:.75rem;white-space:nowrap">→ #${p.duplicate_of_id}</td>
        <td style="padding:.3rem .5rem;font-size:.85rem;word-break:break-all">${p.original_file_path ? _esc(p.original_file_path) : '<span style="color:#aaa">—</span>'}</td>
      </tr>`).join('');
    document.getElementById('modal-body').innerHTML = `
      <p class="modal-note" style="margin-bottom:.5rem">${pairs.length} duplicate${pairs.length===1?'':'s'} found</p>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid var(--border)">
            <th style="padding:.3rem .5rem;text-align:left;font-size:.75rem;color:#888">ID</th>
            <th style="padding:.3rem .5rem;text-align:left;font-size:.75rem;color:#888">Duplicate path</th>
            <th style="padding:.3rem .5rem;text-align:left;font-size:.75rem;color:#888"></th>
            <th style="padding:.3rem .5rem;text-align:left;font-size:.75rem;color:#888">Original path</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch(e) {
    document.getElementById('modal-body').innerHTML = '<p class="modal-err">Failed to load.</p>';
  }
}

function _sortFiles(status) {
  _allFiles.sort((a, b) => {
    if (status === 'pending') return a.id - b.id;
    return (b.finished_at || b.updated_at || '').localeCompare(a.finished_at || a.updated_at || '');
  });
}

function fileColumns(status) {
  const id       = { label:'ID',       cell: f => f.id };
  const name     = { label:'Filename', cell: f => `<span class="modal-fname">${f.file_name}</span>` };
  const path     = { label:'Path',     cell: f => `<span class="modal-path">${f.file_path}</span>` };
  const slave    = { label:'Slave',    cell: f => f.slave_id || '—' };
  const added    = { label:'Added',    cell: f => fmtDate(f.created_at) };
  const started  = { label:'Started',  cell: f => fmtDate(f.started_at) };
  const finished = { label:'Finished', cell: f => fmtDate(f.finished_at) };
  const duration = { label:'Duration', cell: f => fmtDuration(f.started_at, f.finished_at) };
  const output   = { label:'Output',   cell: f => fmtBytes(f.output_size) };
  const encoder  = { label:'Encoder',  cell: f => _encBadge(f.encoder) };
  switch (status) {
    case 'pending':    return [id, name, path, added];
    case 'assigned':   return [id, name, slave, path, {label:'Claimed', cell: f => fmtDate(f.updated_at)}];
    case 'processing': return [id, name, slave, encoder, path, started];
    case 'complete':   return [id, name, slave, encoder, output, duration, finished];
    case 'discarded':  return [id, name, slave, finished];
    case 'cancelled':  return [id, name, slave, encoder, output, duration, finished];
    case 'error':      return [id, name, slave, encoder, path, started, finished];
    default:           return [id, name, path, added];
  }
}

// ── Slave detail modal ────────────────────────────────────────────────────
async function showSlave(host, port, name) {
  _ctx = { type:'slave', host, port, name };
  _page = 1; _query = ''; _allFiles = []; _statusFilter = null; _encoderFilter = null;
  _cols = [
    { label:'ID',       cell: f => f.id },
    { label:'Filename', cell: f => `<span class="modal-fname">${f.file_name}</span>` },
    { label:'Status',   cell: f => stBadge(f.status, f) },
    { label:'Encoder',  cell: f => _encBadge(f.encoder) },
    { label:'Source',   cell: f => fmtBytes(f.file_size) },
    { label:'Output',   cell: f => fmtBytes(f.output_size) },
    { label:'Duration', cell: f => fmtDuration(f.started_at, f.finished_at) },
    { label:'Finished', cell: f => fmtDate(f.finished_at) },
  ];
  _setModal(name, '<p class="modal-note">Loading…</p>');
  try {
    const r = await fetch(`/data/slave?host=${encodeURIComponent(host)}&port=${port}`);
    const data = await r.json();
    _allFiles = (data.files || []).sort((a,b) =>
      (b.updated_at||'').localeCompare(a.updated_at||''));

    const section = `<div class="modal-section">File history (${_allFiles.length} records)</div>`;
    _setModal(name,
      `<div id="slave-status">${_slaveStatusHtml(data.status, host, port)}</div>` +
      section + _shell());
    _renderTable();
    _startSlavePoll(host, port);
  } catch(e) {
    document.getElementById('modal-body').innerHTML = '<p class="modal-err">Failed to load.</p>';
  }
}


async function saveSlaveSettings(host, port) {
  const sel = document.getElementById(`enc-${port}`);
  const inp = document.getElementById(`batch-${port}`);
  const chk = document.getElementById(`replace-${port}`);
  if (!sel) return;
  const encoder = sel.value;
  if (!encoder) return;
  const batch_size = Math.max(1, parseInt(inp?.value) || 1);
  if (inp) inp.value = batch_size;
  const replace_original = chk ? chk.checked : false;
  const btn = document.getElementById(`settings-save-${port}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const r = await fetch('/data/slave/encoder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host, port, encoder, batch_size, replace_original}),
    });
    if (!r.ok) throw new Error('failed');
    if (btn) { btn.textContent = 'Saved'; setTimeout(() => { if (btn) btn.textContent = 'Save'; }, 1500); }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Error — retry'; }
    return;
  }
  if (btn) btn.disabled = false;
  await _refreshSlaveStatus(host, port);
  const r = await fetch('/data/dashboard');
  if (r.ok) _applyDashboard(await r.json());
}

function _encoderSelect(encoder, host, port, unconfigured, availableEncoders, encoderLabels) {
  const labels = encoderLabels || {};
  const available = (availableEncoders && availableEncoders.length)
    ? availableEncoders
    : Object.keys(labels);
  let opts = unconfigured
    ? '<option value="" disabled selected>— Select encoder —</option>'
    : '';
  opts += available
    .map(v => `<option value="${v}"${!unconfigured && v === encoder ? ' selected' : ''}>${labels[v] || v}</option>`)
    .join('');
  // Pause live-refresh while user has the dropdown open so it can't reset their selection
  const sel = `<select id="enc-${port}"
    onfocus="_stopSlavePoll()"
    onblur="_scheduleSlavePoll('${_esc(host)}',${port},3000)"
    style="padding:.25rem .45rem;border:1px solid var(--border-input);border-radius:4px;font-size:.8rem;font-family:inherit;background:var(--surface);color:var(--text);cursor:pointer">${opts}</select>`;
  return sel;
}

function _slaveStatusHtml(st, host, port) {
  let h = `<div style="font-size:.8rem;color:#aaa;margin-bottom:.7rem">${host}:${port}</div>`;
  if (!st) return h + '<p class="modal-err" style="margin-bottom:.8rem">Unreachable.</p>';

  const label = st.unconfigured ? 'Unconfigured'
              : st.disk_full ? 'Disk full'
              : st.sleeping ? 'Sleeping' : st.paused ? 'Paused' : st.drain ? 'Draining'
              : st.state === 'processing' ? 'Converting' : 'Idle';
  const cls   = st.unconfigured ? 'badge-unconfigured'
              : st.disk_full ? 'badge-disk-full'
              : st.sleeping ? 'badge-sleeping' : st.paused ? 'badge-paused' : st.drain ? 'badge-drain'
              : st.state === 'processing' ? 'badge-processing' : 'badge-idle';
  const slaveActions = st.sleeping
    ? `<form method="post" action="/actions/slave/wake" onclick="event.stopPropagation()">
        <input type="hidden" name="host" value="${_esc(host)}">
        <input type="hidden" name="api_port" value="${port}">
        <button class="btn-act" type="submit">Wake up</button>
      </form>`
    : `<form method="post" action="/actions/slave/sleep" onclick="event.stopPropagation()">
        <input type="hidden" name="host" value="${_esc(host)}">
        <input type="hidden" name="api_port" value="${port}">
        <button class="btn-act" type="submit">Sleep</button>
      </form>`;
  h += `<div class="modal-state-row">
    <span class="badge ${cls}">${label}</span>
    <span class="modal-meta">Queue: ${st.queued} job${st.queued!==1?'s':''}</span>`;
  if (st.record_id != null) h += `<span class="modal-meta">Record #${st.record_id}</span>`;
  h += slaveActions + '</div>';
  if (st.unconfigured) {
    h += `<div style="font-size:.82rem;color:var(--text-dim);margin-bottom:.6rem">
      Select an encoder to activate this slave:
    </div>`;
  }
  h += `<div style="display:flex;flex-wrap:nowrap;align-items:center;gap:.75rem;margin-bottom:.8rem;font-size:.8rem;color:var(--text-dim)">
    <span>Encoder</span>${_encoderSelect(st.encoder || 'libx265', host, port, st.unconfigured, st.available_encoders, st.encoder_labels)}
    <span style="margin-left:.25rem">Queue size</span>
    <input id="batch-${port}" type="number" min="1" value="${st.batch_size || 1}"
      onfocus="_stopSlavePoll()"
      onblur="_scheduleSlavePoll('${_esc(host)}',${port},3000)"
      style="width:4rem;padding:.25rem .45rem;border:1px solid var(--border-input);border-radius:4px;font-size:.8rem;font-family:inherit;background:var(--surface);color:var(--text)">
    <label style="display:flex;align-items:center;gap:.3rem;cursor:pointer;white-space:nowrap">
      <input id="replace-${port}" type="checkbox" ${st.replace_original ? 'checked' : ''}
        onclick="_stopSlavePoll(); _scheduleSlavePoll('${_esc(host)}',${port},3000)">Replace original</label>
    <button id="settings-save-${port}" class="btn-act" type="button" onclick="saveSlaveSettings('${_esc(host)}',${port})" style="margin-left:auto">Save</button>
  </div>`;

  if (st.state === 'processing') {
    const cmdId = `ffcmd-${port}`;
    const cmdBtn = st.current_cmd
      ? ` <button onclick="document.getElementById('${cmdId}').style.display=document.getElementById('${cmdId}').style.display==='none'?'block':'none'"
             style="border:none;background:none;color:var(--text-dim);font-size:.7rem;cursor:pointer;padding:.1rem .3rem;text-decoration:underline">cmd</button>
           <div id="${cmdId}" data-cmd="${_esc(st.current_cmd)}" style="display:none;position:relative;margin:.4rem 0 0">
             <button onclick="navigator.clipboard.writeText(this.parentElement.dataset.cmd).then(()=>_showCopied(this))"
               title="Copy to clipboard"
               style="position:absolute;top:.35rem;right:.35rem;border:none;background:none;color:var(--text-dim);cursor:pointer;font-size:.85rem;padding:.1rem .25rem;line-height:1">⎘</button>
             <pre style="font-size:.7rem;white-space:pre-wrap;word-break:break-all;background:var(--surface-2);border:1px solid var(--border-2);border-radius:4px;padding:.5rem;color:var(--text);margin:0">${_esc(st.current_cmd)}</pre>
           </div>`
      : '';
    h += `<div style="font-size:.8rem;color:var(--text-dim);margin-bottom:.6rem">Active: ${_encBadge(st.encoder)}${cmdBtn}</div>`;
  }

  if (st.state === 'processing' && st.progress) {
    const p = st.progress;
    const pct = Math.min(p.percent || 0, 100).toFixed(1);
    h += `<div style="margin:.4rem 0 1rem">
      <div class="prog-wrap-lg">
        <div class="prog-bar-lg" style="width:${pct}%"></div>
      </div>
      <div class="meta-sm" style="display:flex;justify-content:space-between">
        <span>${pct}%</span>
        <span>${p.fps?p.fps+'\u00a0fps\u00a0\u00a0':''}${p.speed?p.speed+'×\u00a0\u00a0':''}${p.eta_seconds!=null?'ETA\u00a0'+fmtEta(p.eta_seconds):''}</span>
      </div>`;
    if (p.current_size_bytes)
      h += `<div class="meta-xs">${fmtBytes(p.current_size_bytes)}${p.projected_size_bytes?' → '+fmtBytes(p.projected_size_bytes):''}${p.bitrate?' &middot; '+p.bitrate:''}</div>`;
    h += '</div>';
  }
  return h;
}
