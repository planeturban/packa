# Dashboard UI

The web dashboard is a single-page app served by the web process. It auto-refreshes every 3 seconds (configurable in Settings). Fonts (IBM Plex Sans, IBM Plex Mono) are served locally — no external network requests.

---

## Tabs

| Tab | Contents |
|-----|----------|
| **Overview** | Status chips with file counts, overall progress bar, worker summary list |
| **Files** | Full file table with filter chips, search, checkboxes, and bulk actions |
| **Statistics** | Aggregated and per-worker stats: jobs, bytes, space saved, bitrate, playtime |
| **Workers** | Per-worker cards with live progress, controls, encoder and batch settings |
| **Master** | Probe/scan stats, manual and periodic scan, editable master configuration |
| **Settings** | Dashboard poll interval and other preferences |

---

## Files tab

### Filter chips

The filter bar above the file table supports multi-status filtering.

| Interaction | Effect |
|-------------|--------|
| **Click** | Show only that status. Click the same chip again to deselect (back to All). If multiple are active, click one to remove only that one. |
| **Option-click** (Mac) / **Ctrl-click** (Win/Linux) | Add a status to the active set — results show files matching **any** selected status (OR). |
| **Shift-click** | Exclude a status — shown in red with strikethrough. Excluded files are hidden regardless of other filters. |
| **All** | Clear all active and excluded filters. |

Active filters are highlighted in the accent colour. Excluded filters are highlighted in red with strikethrough.

### Bulk actions

Select files using the checkboxes, then use the bulk-action row in the table header to:
- Set selected files → Pending
- Set selected files → Cancelled
- Delete selected files
- Queue selected files to a specific worker

### Search

The search box filters by filename, full path, or worker ID.

---

## Overview tab

Clicking any status chip opens a modal listing all files with that status. The modal supports the same bulk actions as the Files tab. After any action the modal refreshes in place without closing.

The worker summary list shows each worker's name, status badge, encoder info, and — when processing — the current filename, progress bar and percentage. Pause, Drain and Stop controls are always visible; they are active when the worker is processing, Wake is active when sleeping, and all are disabled when idle.

---

## Workers tab

Each registered worker has a card showing:

- **Status badge** — online / processing / paused / draining / sleeping / disk full / offline
- **Progress section** (when processing) — filename (truncated; hover for full path), percent, FPS, speed, progress bar, ETA, queue depth, current output size → projected output size, bitrate
- **CMD button** — appears when a conversion is running; toggles a panel showing the full ffmpeg command
- **Stats** — converted count, error count, encoder, batch size (both editable inline)
- **Controls** — always visible; Pause/Resume/Stop/Drain are active when processing, Wake is active when sleeping, all disabled when idle. Pause switches to Resume when paused; Drain highlights when active and switches to Resume to cancel.

### Inline editing

Click the **Encoder** or **Batch** stat cell to edit it inline. Press Enter or click ✓ to save, Escape to cancel.

### Settings panel

Click **Settings** to expand a panel with:
- A summary of the current running configuration (encoder, batch, replace original, queue depth, master URL).
- The **Replace original** toggle and **Save settings** button.
- A **Worker Configuration** section — same layered editor as the Master tab. Fields: path prefix, output directory, ffmpeg binary, extra ffmpeg args, poll interval. All changes take effect on the next job or poll cycle without a restart. Network identity settings (`bind`, `api_port`, `master_host`, `master_port`) are set via config file, environment variables, or CLI flags only.

### TLS onboarding

When master has TLS active, worker cards for workers that have not yet been onboarded show an **Onboard TLS** button. All other controls on that card are disabled until the worker is onboarded. Clicking **Onboard TLS** generates a new bootstrap token, sends it to the worker, and triggers a worker restart. Once the worker restarts with its new cert, normal controls become available.

### Drain mode

Drain finishes the current job then stops polling. The worker goes to sleep after the job completes. Click Resume (replaces the Drain button while active) to cancel drain and continue polling.

---

## Master tab

The Master tab surfaces four stat cards (average conversion time, probe rate, scan speed, probe queue depth) and a probe-progress bar, followed by the scanner controls and the editable master configuration.

### Scanner

- **Scan status bar** — shows whether a scan is running and, when idle, the configured path prefix. The top-bar **Scan** button is disabled when `master.paths.prefix` is empty.
- **Periodic scanning** is controlled via the Master Configuration form below (`scan_periodic_enabled`, `scan_interval_seconds`). Edits take effect on the next tick of the periodic-scan loop.

### Master Configuration

Every master setting is rendered as its own row with an input and action buttons:

| Action | Effect |
|--------|--------|
| **Edit + blur / Enter** | Saves the new value into the database (`db` source). |
| **Restore from file** | Copies the value from `packa.toml` into the database. Shown when that layer has a value. |
| **Restore from env** | Copies the value from the process environment. Shown when that layer has a value. |
| **Default** | Copies the built-in default into the database. |
| **Revert** | Clears the database override so the value falls back through env → file → default. Shown only when the current source is `db`. |

Fields flagged **restart required on change** (`bind`, `api_port`) are persisted immediately but only take effect after the master restarts. A toast confirms each save and surfaces the restart flag.

### TLS card

The Master tab includes a TLS card showing the CA fingerprint, whether TLS is active, and the current bootstrap token with its expiry time. A **New token** button generates a fresh token (invalidating the old one). Use this to onboard new workers or re-onboard workers after cert expiry.

If a value is currently overridden by a CLI flag (`--bind`, `--api-port`) the row shows a note explaining that database edits take effect only after a restart without the flag.

---

## Poll guard

Live refresh is paused automatically when:
- Any input, select, or textarea has keyboard focus
- A worker settings or CMD panel is open
- Any files are selected in the modal

This prevents in-progress edits from being wiped by a poll.

---

## Login page

When authentication is enabled, an email/password form is shown. If the web process has not yet bootstrapped its TLS certificate, a **Bootstrap token** input appears above the login form. Paste the token printed by master on startup, click **Bootstrap TLS**, and the web process will fetch its client cert from master and restart with TLS enabled. After restart the bootstrap input disappears.

---

## Themes

The theme cycles **dark → light → system** via the button in the top bar. In system mode the OS `prefers-color-scheme` setting is followed and updates live. The preference is stored in `localStorage` and applied before first render to avoid a flash.

## Tabs

The tab bar scrolls horizontally on narrow screens (scrollbar hidden). Swipe to reach tabs that don't fit.
