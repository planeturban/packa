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
| **Scan** | Manual scan trigger, periodic scan toggle and interval |
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

Click **Settings** to expand a panel with the Replace Original toggle and a Save button.

### Drain mode

Drain finishes the current job then stops polling. The worker goes to sleep after the job completes. Click Resume (replaces the Drain button while active) to cancel drain and continue polling.

---

## Poll guard

Live refresh is paused automatically when:
- Any input, select, or textarea has keyboard focus
- A worker settings or CMD panel is open
- Any files are selected in the modal

This prevents in-progress edits from being wiped by a poll.

---

## Themes

The theme cycles **dark → light → system** via the button in the top bar. In system mode the OS `prefers-color-scheme` setting is followed and updates live. The preference is stored in `localStorage` and applied before first render to avoid a flash.

## Tabs

The tab bar scrolls horizontally on narrow screens (scrollbar hidden). Swipe to reach tabs that don't fit.
