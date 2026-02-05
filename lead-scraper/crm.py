#!/usr/bin/env python3
"""
Minimal CRM web UI for leads.db — zero external dependencies.
Uses only Python stdlib: http.server, sqlite3, json.

Usage:
    python3 crm.py              # opens on port 8080
    python3 crm.py --port 9000  # custom port
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClearPresence CRM</title>
<style>
  :root{--accent:#0b66ff;--bg:#f7f8fb;--card:#fff;--border:#e6e9f0;--text:#0f1724;--muted:#6b7280;--green:#16a34a;--yellow:#ca8a04;--red:#dc2626}
  *{box-sizing:border-box;margin:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);padding:20px}
  h1{font-size:22px;margin-bottom:4px}
  .subtitle{color:var(--muted);font-size:14px;margin-bottom:20px}
  .controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;align-items:center}
  .controls select,.controls input{padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:14px}
  .controls input[type=text]{width:240px}
  .stats{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 18px}
  .stat .n{font-size:24px;font-weight:700;color:var(--accent)}
  .stat .label{font-size:12px;color:var(--muted)}
  table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;font-size:13px}
  th{background:var(--bg);text-align:left;padding:10px 12px;font-weight:600;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.3px;border-bottom:2px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap}
  th:hover{color:var(--text)}
  td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}
  tr:last-child td{border-bottom:none}
  tr:hover{background:#f0f4ff}
  .score{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:700;font-size:12px;min-width:28px;text-align:center}
  .score-high{background:#fee2e2;color:var(--red)}
  .score-med{background:#fef3c7;color:var(--yellow)}
  .score-low{background:#dcfce7;color:var(--green)}
  .badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .badge-new{background:#dbeafe;color:#1d4ed8}
  .badge-contacted{background:#fef3c7;color:#92400e}
  .badge-replied{background:#d1fae5;color:#065f46}
  .badge-closed{background:#e5e7eb;color:#374151}
  .reasons{font-size:11px;color:var(--muted);max-width:200px}
  .phone-link{color:var(--accent);text-decoration:none;white-space:nowrap}
  .web-link{color:var(--accent);font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
  .actions{display:flex;gap:4px}
  .actions button{padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--card);cursor:pointer;font-size:11px}
  .actions button:hover{background:var(--bg)}
  .del-bar{display:none;align-items:center;gap:12px;margin-bottom:14px;padding:10px 16px;background:#fee2e2;border:1px solid #fca5a5;border-radius:8px}
  .del-bar.visible{display:flex}
  .del-bar .del-btn{background:var(--red);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px}
  .del-bar .del-btn:hover{opacity:.85}
  .del-bar .del-count{font-size:13px;font-weight:600;color:var(--red)}
  .del-bar .del-cancel{background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;text-decoration:underline}
  .cb{width:16px;height:16px;cursor:pointer;accent-color:var(--red)}
  th .cb{margin:0}
  /* Modal */
  .overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.4);z-index:50;align-items:center;justify-content:center}
  .overlay.open{display:flex}
  .modal{background:#fff;border-radius:10px;padding:24px;width:420px;max-width:95vw;box-shadow:0 20px 60px rgba(0,0,0,.15)}
  .modal h2{font-size:18px;margin-bottom:16px}
  .modal label{display:block;font-size:12px;color:var(--muted);margin-top:12px;margin-bottom:4px}
  .modal select,.modal input,.modal textarea{width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px;font-family:inherit}
  .modal textarea{height:80px;resize:vertical}
  .modal-actions{display:flex;gap:8px;margin-top:18px;justify-content:flex-end}
  .modal-actions button{padding:8px 16px;border-radius:6px;border:1px solid var(--border);background:var(--card);cursor:pointer;font-size:14px}
  .modal-actions .save{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
  .empty{text-align:center;padding:40px;color:var(--muted)}
  .actions button.btn-text{background:#16a34a;color:#fff;border:1px solid #16a34a;font-weight:600}
  .actions button.btn-text:hover{opacity:.85}
  .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#0f1724;color:#fff;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;z-index:100;opacity:0;transition:opacity .3s;pointer-events:none}
  .toast.show{opacity:1}
</style>
</head>
<body>

<h1>ClearPresence CRM</h1>
<p class="subtitle">Lead tracking — <span id="dbpath"></span></p>

<div class="stats" id="stats"></div>

<div class="controls">
  <select id="filterStatus">
    <option value="">All statuses</option>
    <option value="new">New</option>
    <option value="contacted">Contacted</option>
    <option value="replied">Replied</option>
    <option value="closed">Closed</option>
  </select>
  <select id="filterScore">
    <option value="0">All scores</option>
    <option value="5">Score 5+</option>
    <option value="3">Score 3+</option>
    <option value="8">Score 8+</option>
  </select>
  <input type="text" id="searchBox" placeholder="Search name, phone, category...">
</div>

<div class="del-bar" id="delBar">
  <span class="del-count"><span id="delCount">0</span> selected</span>
  <button class="del-btn" onclick="deleteSelected()">Delete selected</button>
  <button class="del-cancel" onclick="clearSelection()">Cancel</button>
</div>

<table>
  <thead>
    <tr>
      <th><input type="checkbox" class="cb" id="selectAll" onchange="toggleAll(this)"></th>
      <th data-col="lead_score">Score</th>
      <th data-col="contact_status">Status</th>
      <th data-col="name">Business</th>
      <th data-col="phone">Phone</th>
      <th data-col="website">Website</th>
      <th data-col="rating">Rating</th>
      <th data-col="review_count">Reviews</th>
      <th>Reasons</th>
      <th data-col="last_contacted">Last Contact</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>

<div class="overlay" id="overlay">
  <div class="modal">
    <h2 id="modalTitle">Edit Lead</h2>
    <input type="hidden" id="editLink">
    <label>Status</label>
    <select id="editStatus">
      <option value="new">New</option>
      <option value="contacted">Contacted</option>
      <option value="replied">Replied</option>
      <option value="closed">Closed</option>
    </select>
    <label>Last Contacted</label>
    <input type="date" id="editDate">
    <label>Notes</label>
    <textarea id="editNotes"></textarea>
    <div class="modal-actions">
      <button onclick="closeModal()">Cancel</button>
      <button class="save" onclick="saveEdit()">Save</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const MSG_TEMPLATE = `Hi [NAME], this is Aharon from Clear Presence Digital. I took a quick look at your Google listing and noticed a few areas that may be limiting visibility and reviews — mostly easy fixes that can make a real difference. I offer a free quick audit showing specific improvements. If you'd like, I can send the report today — no obligation.`;

let leads = [];
let sortCol = 'lead_score';
let sortAsc = false;
let selected = new Set();

async function load() {
  const res = await fetch('/api/leads');
  leads = await res.json();
  render();
}

function render() {
  const status = document.getElementById('filterStatus').value;
  const minScore = parseInt(document.getElementById('filterScore').value) || 0;
  const search = document.getElementById('searchBox').value.toLowerCase();

  let filtered = leads.filter(l => {
    if (status && l.contact_status !== status) return false;
    if (l.lead_score < minScore) return false;
    if (search) {
      const hay = [l.name, l.phone, l.category, l.address, l.notes || ''].join(' ').toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    let va = a[sortCol] ?? '', vb = b[sortCol] ?? '';
    if (typeof va === 'number' && typeof vb === 'number') return sortAsc ? va - vb : vb - va;
    va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
    return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
  });

  // Stats
  const total = leads.length;
  const newC = leads.filter(l => l.contact_status === 'new').length;
  const contacted = leads.filter(l => l.contact_status === 'contacted').length;
  const replied = leads.filter(l => l.contact_status === 'replied').length;
  const closed = leads.filter(l => l.contact_status === 'closed').length;
  const highP = leads.filter(l => l.lead_score >= 5).length;
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="n">${total}</div><div class="label">Total leads</div></div>
    <div class="stat"><div class="n">${highP}</div><div class="label">High priority (5+)</div></div>
    <div class="stat"><div class="n">${newC}</div><div class="label">New</div></div>
    <div class="stat"><div class="n">${contacted}</div><div class="label">Contacted</div></div>
    <div class="stat"><div class="n">${replied}</div><div class="label">Replied</div></div>
    <div class="stat"><div class="n">${closed}</div><div class="label">Closed</div></div>
  `;
  document.getElementById('dbpath').textContent = 'leads.db';

  const tbody = document.getElementById('tbody');
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" class="empty">No leads match your filters</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(l => {
    const sc = l.lead_score;
    const scClass = sc >= 7 ? 'score-high' : sc >= 4 ? 'score-med' : 'score-low';
    const bClass = 'badge-' + (l.contact_status || 'new');
    const phone = l.phone || '—';
    const phoneHref = phone !== '—' ? `tel:${phone.replace(/[^+\\d]/g, '')}` : '#';
    const web = l.website || '';
    const webShort = web ? web.replace(/^https?:\\/\\//, '').replace(/\\/$/, '') : '—';
    const rating = l.rating != null ? l.rating.toFixed(1) : '—';
    const reviews = l.review_count != null ? l.review_count : '—';
    const reasons = l.score_reasons || '';
    const lastC = l.last_contacted || '—';
    const link = encodeURIComponent(l.maps_link);
    const checked = selected.has(l.maps_link) ? 'checked' : '';
    return `<tr>
      <td><input type="checkbox" class="cb row-cb" data-link="${link}" ${checked} onchange="onRowCheck()"></td>
      <td><span class="score ${scClass}">${sc}</span></td>
      <td><span class="badge ${bClass}">${l.contact_status || 'new'}</span></td>
      <td><strong>${esc(l.name)}</strong><br><span style="font-size:11px;color:var(--muted)">${esc(l.category || '')}</span></td>
      <td><a class="phone-link" href="${phoneHref}">${esc(phone)}</a></td>
      <td>${web ? `<a class="web-link" href="${esc(web)}" target="_blank">${esc(webShort)}</a>` : '—'}</td>
      <td>${rating}</td>
      <td>${reviews}</td>
      <td><span class="reasons">${esc(reasons)}</span></td>
      <td>${lastC}</td>
      <td><div class="actions">
        <button onclick="openEdit('${link}')">Edit</button>
        <a href="${esc(l.maps_link)}" target="_blank"><button>Maps</button></a>
        ${phone !== '—' ? `<button class="btn-text" onclick="sendText('${link}')">Text</button>` : ''}
      </div></td>
    </tr>`;
  }).join('');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function openEdit(encodedLink) {
  const link = decodeURIComponent(encodedLink);
  const l = leads.find(x => x.maps_link === link);
  if (!l) return;
  document.getElementById('modalTitle').textContent = l.name;
  document.getElementById('editLink').value = l.maps_link;
  document.getElementById('editStatus').value = l.contact_status || 'new';
  document.getElementById('editDate').value = l.last_contacted || '';
  document.getElementById('editNotes').value = l.notes || '';
  document.getElementById('overlay').classList.add('open');
}

function closeModal() { document.getElementById('overlay').classList.remove('open'); }

async function saveEdit() {
  const body = {
    maps_link: document.getElementById('editLink').value,
    contact_status: document.getElementById('editStatus').value,
    last_contacted: document.getElementById('editDate').value,
    notes: document.getElementById('editNotes').value,
  };
  await fetch('/api/update', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  closeModal();
  await load();
}

function sendText(encodedLink) {
  const link = decodeURIComponent(encodedLink);
  const l = leads.find(x => x.maps_link === link);
  if (!l || !l.phone || l.phone === '—') return;
  const name = l.name.split(/[^a-zA-Z'\\- ]/)[0].trim();
  const msg = MSG_TEMPLATE.replace('[NAME]', name);
  const phone = l.phone;
  // Copy message to clipboard (the long part — phone is shown in toast)
  navigator.clipboard.writeText(msg).then(() => {
    showToast('Message copied — send to: ' + phone, 8000);
  });
  window.open('https://voice.google.com/u/2/messages', '_blank');
}

function showToast(text, duration) {
  const t = document.getElementById('toast');
  t.textContent = text;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration || 3000);
}

function onRowCheck() {
  document.querySelectorAll('.row-cb').forEach(cb => {
    const link = decodeURIComponent(cb.dataset.link);
    if (cb.checked) selected.add(link);
    else selected.delete(link);
  });
  updateDelBar();
}

function toggleAll(master) {
  document.querySelectorAll('.row-cb').forEach(cb => {
    cb.checked = master.checked;
    const link = decodeURIComponent(cb.dataset.link);
    if (master.checked) selected.add(link);
    else selected.delete(link);
  });
  updateDelBar();
}

function updateDelBar() {
  const bar = document.getElementById('delBar');
  document.getElementById('delCount').textContent = selected.size;
  if (selected.size > 0) bar.classList.add('visible');
  else bar.classList.remove('visible');
}

function clearSelection() {
  selected.clear();
  document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
  document.getElementById('selectAll').checked = false;
  updateDelBar();
}

async function deleteSelected() {
  if (selected.size === 0) return;
  if (!confirm(`Delete ${selected.size} lead(s)? This cannot be undone.`)) return;
  const links = Array.from(selected);
  await fetch('/api/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ maps_links: links })
  });
  selected.clear();
  document.getElementById('selectAll').checked = false;
  updateDelBar();
  await load();
}

// Column sort
document.querySelectorAll('th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (sortCol === col) sortAsc = !sortAsc;
    else { sortCol = col; sortAsc = false; }
    render();
  });
});

// Filter listeners
document.getElementById('filterStatus').addEventListener('change', render);
document.getElementById('filterScore').addEventListener('change', render);
document.getElementById('searchBox').addEventListener('input', render);

// Escape key closes modal
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

load();
</script>
</body>
</html>"""


class CRMHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/leads":
            self._send_json(self._get_leads())
        elif parsed.path == "/" or parsed.path == "":
            self._send_html(HTML_PAGE)
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if self.path == "/api/update":
            self._update_lead(body)
            self._send_json({"ok": True})
        elif self.path == "/api/delete":
            self._delete_leads(body.get("maps_links", []))
            self._send_json({"ok": True})
        else:
            self.send_error(404)

    def _get_leads(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM leads ORDER BY lead_score DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _update_lead(self, data):
        conn = sqlite3.connect(DB_PATH)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE leads SET contact_status=?, last_contacted=?, notes=?, updated_at=? WHERE maps_link=?",
            (data["contact_status"], data.get("last_contacted") or None,
             data.get("notes") or None, now, data["maps_link"])
        )
        conn.commit()
        conn.close()

    def _delete_leads(self, maps_links):
        if not maps_links:
            return
        conn = sqlite3.connect(DB_PATH)
        placeholders = ",".join("?" for _ in maps_links)
        conn.execute(f"DELETE FROM leads WHERE maps_link IN ({placeholders})", maps_links)
        conn.commit()
        conn.close()

    def _send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress per-request logs


def main():
    parser = argparse.ArgumentParser(description="CRM web UI for leads.db")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Run scraper.py first.")
        return

    server = HTTPServer(("0.0.0.0", args.port), CRMHandler)
    print(f"CRM running at http://localhost:{args.port}")
    print(f"Database: {DB_PATH}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
