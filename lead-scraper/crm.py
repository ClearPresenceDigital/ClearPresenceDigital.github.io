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
PENDING = {"phone": "", "msg": ""}

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
  .badge-do_not_contact{background:#fee2e2;color:#991b1b}
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
  .actions button.btn-text2{background:#0b66ff;color:#fff;border:1px solid #0b66ff;font-weight:600}
  .actions button.btn-text2:hover{opacity:.85}
  .actions .btn-group{display:flex;gap:2px}
  .actions .btn-group button{border-radius:0;font-size:10px;padding:4px 6px}
  .actions .btn-group button:first-child{border-radius:4px 0 0 4px}
  .actions .btn-group button:last-child{border-radius:0 4px 4px 0}
  .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#0f1724;color:#fff;padding:12px 20px;border-radius:8px;font-size:13px;font-weight:600;z-index:100;opacity:0;transition:opacity .3s;pointer-events:none;display:flex;align-items:center;gap:12px;max-width:90vw}
  .toast.show{opacity:1;pointer-events:auto}
  .toast .copy-msg-btn{background:#16a34a;color:#fff;border:none;padding:6px 14px;border-radius:5px;font-weight:700;cursor:pointer;font-size:12px;white-space:nowrap}
  .toast .copy-msg-btn:hover{opacity:.85}
  .toast .dismiss-btn{background:none;border:none;color:#999;cursor:pointer;font-size:16px;padding:0 4px}
  /* Salesman selector */
  .salesman-bar{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding:10px 16px;background:var(--card);border:1px solid var(--border);border-radius:8px}
  .salesman-bar label{font-size:13px;font-weight:600;color:var(--muted)}
  .salesman-bar select{padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px;font-weight:600}
  .salesman-bar .salesman-indicator{margin-left:auto;font-size:12px;color:var(--muted)}
  /* Call buttons */
  .actions button.btn-call{background:#7c3aed;color:#fff;border:1px solid #7c3aed;font-weight:600}
  .actions button.btn-call:hover{opacity:.85}
  /* Activity log modal */
  .log-table{width:100%;font-size:12px;margin-top:12px;max-height:300px;overflow-y:auto;display:block}
  .log-table th,.log-table td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--border)}
  .log-table th{background:var(--bg);position:sticky;top:0}
</style>
</head>
<body>

<h1>ClearPresence CRM</h1>
<p class="subtitle">Lead tracking — <span id="dbpath"></span> &nbsp;|&nbsp; Drag this to bookmarks bar: <a href="javascript:void(fetch('http://localhost:9000/api/pending').then(r=>r.json()).then(d=>{if(!d.phone){alert('No pending message. Click Text in CRM first.');return;}function setVal(el,v){el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}function waitFor(sel,cb,n){n=n||0;var el=document.querySelector(sel);if(el)return cb(el);if(n<30)setTimeout(()=>waitFor(sel,cb,n+1),500);}var toInput=document.querySelector('input[placeholder*=name i],input[placeholder*=number i],input[aria-label*=name i]');if(toInput){setVal(toInput,d.phone);setTimeout(()=>{toInput.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));setTimeout(()=>{waitFor('textarea.message-input,textarea.cdk-textarea-autosize',el=>{setVal(el,d.msg);el.focus();});},1500);},800);}else{waitFor('textarea.message-input,textarea.cdk-textarea-autosize',el=>{setVal(el,d.msg);el.focus();alert('Phone field not found. Paste phone manually: '+d.phone);});}}).catch(()=>alert('CRM server not running on localhost:9000')))" style="display:inline-block;padding:3px 10px;background:var(--accent);color:#fff;border-radius:4px;font-size:12px;font-weight:600;cursor:grab">GV Fill</a></p>

<div class="salesman-bar">
  <label>Salesman:</label>
  <select id="salesmanSelect" onchange="saveSalesman()">
    <option value="">-- Select --</option>
    <option value="Ron">Ron</option>
    <option value="Salesman2">Salesman 2</option>
    <option value="Salesman3">Salesman 3</option>
  </select>
  <span class="salesman-indicator">All actions logged</span>
  <button onclick="showActivityLog()" style="margin-left:8px;padding:4px 10px;border:1px solid var(--border);border-radius:4px;background:var(--card);cursor:pointer;font-size:12px">View Log</button>
</div>

<div class="stats" id="stats"></div>

<div class="controls">
  <select id="filterStatus">
    <option value="">All statuses</option>
    <option value="new">New</option>
    <option value="contacted">Contacted</option>
    <option value="replied">Replied</option>
    <option value="closed">Closed</option>
    <option value="do_not_contact">Do Not Contact</option>
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
      <th data-col="scraped_at">Scraped</th>
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
      <option value="do_not_contact">Do Not Contact</option>
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

<div class="overlay" id="logOverlay">
  <div class="modal" style="width:600px">
    <h2>Activity Log</h2>
    <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Irrevocable record of all salesman actions</p>
    <table class="log-table">
      <thead><tr><th>Time</th><th>Salesman</th><th>Action</th><th>Lead</th></tr></thead>
      <tbody id="logBody"></tbody>
    </table>
    <div class="modal-actions">
      <button onclick="closeLogModal()">Close</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// Message templates for two-step outreach flow
const MSG_TEMPLATES = {
  // Text 1: Initial outreach (no link) - for NEW leads
  initial: `Hi [NAME], this is Ron from ClearPresence Digital. I noticed a few areas on your Google listing that may be limiting visibility and reviews — mostly easy fixes. I offer a free quick audit showing specific improvements. Want me to send it over? Reply STOP to opt out.`,

  // Text 2: Follow-up with audit (with link) - for REPLIED leads
  followup: `Hi [NAME], here's the quick audit I mentioned for your Google Business Profile. I found [X] areas for improvement. You can see the details here: clearpresencedigital.com — Happy to walk through it if you have questions. Reply STOP to opt out.`
};

let leads = [];
let sortCol = 'lead_score';
let sortAsc = false;
let selected = new Set();
let gvWindow = null;

// === Salesman & Activity Logging ===
function getSalesman() {
  return localStorage.getItem('crm_salesman') || '';
}

function saveSalesman() {
  const val = document.getElementById('salesmanSelect').value;
  localStorage.setItem('crm_salesman', val);
}

function initSalesman() {
  const saved = getSalesman();
  if (saved) {
    document.getElementById('salesmanSelect').value = saved;
  }
}

function logActivity(action, leadName, details = '') {
  const salesman = getSalesman();
  if (!salesman) {
    alert('Please select a salesman first!');
    return false;
  }
  const entry = {
    timestamp: new Date().toISOString(),
    salesman: salesman,
    action: action,
    lead: leadName,
    details: details
  };
  // Store in localStorage (append to array)
  const logs = JSON.parse(localStorage.getItem('crm_activity_log') || '[]');
  logs.unshift(entry); // newest first
  // Keep last 1000 entries
  if (logs.length > 1000) logs.length = 1000;
  localStorage.setItem('crm_activity_log', JSON.stringify(logs));
  // Also send to server for permanent storage
  fetch('/api/log', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(entry)
  }).catch(() => {}); // ignore errors, localStorage is backup
  return true;
}

function showActivityLog() {
  const logs = JSON.parse(localStorage.getItem('crm_activity_log') || '[]');
  const tbody = document.getElementById('logBody');
  if (logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted)">No activity yet</td></tr>';
  } else {
    tbody.innerHTML = logs.slice(0, 100).map(e => {
      const time = new Date(e.timestamp).toLocaleString();
      return `<tr><td>${time}</td><td>${esc(e.salesman)}</td><td>${esc(e.action)}</td><td>${esc(e.lead)}</td></tr>`;
    }).join('');
  }
  document.getElementById('logOverlay').classList.add('open');
}

function closeLogModal() {
  document.getElementById('logOverlay').classList.remove('open');
}

async function load() {
  const res = await fetch('/api/leads');
  leads = await res.json();
  initSalesman();
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
  const dnc = leads.filter(l => l.contact_status === 'do_not_contact').length;
  const highP = leads.filter(l => l.lead_score >= 5).length;
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="n">${total}</div><div class="label">Total leads</div></div>
    <div class="stat"><div class="n">${highP}</div><div class="label">High priority (5+)</div></div>
    <div class="stat"><div class="n">${newC}</div><div class="label">New</div></div>
    <div class="stat"><div class="n">${contacted}</div><div class="label">Contacted</div></div>
    <div class="stat"><div class="n">${replied}</div><div class="label">Replied</div></div>
    <div class="stat"><div class="n">${closed}</div><div class="label">Closed</div></div>
    ${dnc > 0 ? `<div class="stat"><div class="n" style="color:var(--red)">${dnc}</div><div class="label">Do Not Contact</div></div>` : ''}
  `;
  document.getElementById('dbpath').textContent = 'leads.db';

  const tbody = document.getElementById('tbody');
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="12" class="empty">No leads match your filters</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(l => {
    const sc = l.lead_score;
    const scClass = sc >= 7 ? 'score-high' : sc >= 4 ? 'score-med' : 'score-low';
    const bClass = 'badge-' + (l.contact_status || 'new');
    const phone = l.phone || '—';
    const phoneClean = phone.replace(/[^+\\d]/g, '');
    const phoneHref = phone !== '—' ? `https://voice.google.com/u/2/calls?a=nc&n=${encodeURIComponent(phoneClean)}` : '#';
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
      <td style="font-size:11px;color:var(--muted)">${l.scraped_at ? l.scraped_at.split('T')[0] : '—'}</td>
      <td><div class="actions">
        <button onclick="openEdit('${link}')">Edit</button>
        <a href="${esc(l.maps_link)}" target="_blank"><button>Maps</button></a>
        ${getTextButtons(l, link, phone)}
      </div></td>
    </tr>`;
  }).join('');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// Returns appropriate text button(s) based on lead status
function getTextButtons(lead, link, phone) {
  if (phone === '—') return '';
  const status = lead.contact_status || 'new';
  const phoneClean = phone.replace(/[^+\\d]/g, '');

  // Call button (always shown if phone exists, except for do_not_contact)
  const callBtn = status !== 'do_not_contact'
    ? `<button class="btn-call" onclick="makeCall('${link}', '${phoneClean}')" title="Call via tel:">Call</button>`
    : '';

  // No text buttons for closed or do_not_contact
  if (status === 'closed' || status === 'do_not_contact') return callBtn;

  // For NEW leads: show "Text 1" (initial outreach)
  if (status === 'new') {
    return `${callBtn}<button class="btn-text" onclick="sendText('${link}', 'initial')">Text 1</button>`;
  }

  // For CONTACTED leads: show both options
  if (status === 'contacted') {
    return `${callBtn}<div class="btn-group">
      <button class="btn-text" onclick="sendText('${link}', 'initial')" title="Resend initial">1</button>
      <button class="btn-text2" onclick="sendText('${link}', 'followup')" title="Send audit follow-up">2</button>
    </div>`;
  }

  // For REPLIED leads: show "Text 2" (follow-up with audit)
  if (status === 'replied') {
    return `${callBtn}<button class="btn-text2" onclick="sendText('${link}', 'followup')">Text 2</button>`;
  }

  return callBtn;
}

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
  const link = document.getElementById('editLink').value;
  const l = leads.find(x => x.maps_link === link);
  const body = {
    maps_link: link,
    contact_status: document.getElementById('editStatus').value,
    last_contacted: document.getElementById('editDate').value,
    notes: document.getElementById('editNotes').value,
  };
  // Log activity
  if (!logActivity('edited', l ? l.name : 'Unknown', `Status: ${body.contact_status}`)) return;
  await fetch('/api/update', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  closeModal();
  await load();
}

// Make a call via tel: link (works on mobile)
function makeCall(encodedLink, phoneClean) {
  const link = decodeURIComponent(encodedLink);
  const l = leads.find(x => x.maps_link === link);
  if (!l) return;
  // Log activity
  if (!logActivity('called', l.name, `Phone: ${l.phone}`)) return;
  // Open tel: link
  window.open('tel:' + phoneClean, '_self');
}

function sendText(encodedLink, templateType = 'initial') {
  const link = decodeURIComponent(encodedLink);
  const l = leads.find(x => x.maps_link === link);
  if (!l || !l.phone || l.phone === '—') return;

  // Log activity first (will alert if no salesman selected)
  const actionName = templateType === 'initial' ? 'texted (initial)' : 'texted (follow-up)';
  if (!logActivity(actionName, l.name, `Phone: ${l.phone}`)) return;

  const name = l.name.split(/[^a-zA-Z'\\- ]/)[0].trim();
  const template = MSG_TEMPLATES[templateType] || MSG_TEMPLATES.initial;
  const msg = template.replace('[NAME]', name);
  const phone = l.phone;

  // Determine new status based on template type
  const newStatus = templateType === 'initial' ? 'contacted' : l.contact_status;
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

  // Auto-update status and date
  fetch('/api/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      maps_link: link,
      contact_status: newStatus,
      last_contacted: today,
      notes: l.notes || ''
    })
  }).then(() => {
    // Update local state so UI reflects change immediately
    l.contact_status = newStatus;
    l.last_contacted = today;
    render();
  });

  // Store pending phone+msg on server for bookmarklet to fetch
  fetch('/api/pending', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ phone, msg })
  }).then(() => {
    const label = templateType === 'initial' ? 'Text 1 ready' : 'Text 2 (audit) ready';
    showToast(label + ' — switch to GV tab and run bookmarklet (or Ctrl+V phone: ' + phone + ')', msg);
  });
  // Also copy phone to clipboard as fallback
  navigator.clipboard.writeText(phone);
  // Open or focus GV draft
  if (gvWindow && !gvWindow.closed) {
    gvWindow.focus();
  } else {
    gvWindow = window.open('https://voice.google.com/u/2/messages?itemId=draft', 'googlevoice');
  }
}

function showToast(text, pendingMsg) {
  const t = document.getElementById('toast');
  if (pendingMsg) {
    t.innerHTML = '<span>' + esc(text) + '</span>'
      + '<button class="copy-msg-btn" onclick="copyMsg()">Copy Message</button>'
      + '<button class="dismiss-btn" onclick="hideToast()">&times;</button>';
    window._pendingMsg = pendingMsg;
  } else {
    t.innerHTML = '<span>' + esc(text) + '</span>';
    setTimeout(() => t.classList.remove('show'), 3000);
  }
  t.classList.add('show');
}

function copyMsg() {
  if (!window._pendingMsg) return;
  navigator.clipboard.writeText(window._pendingMsg).then(() => {
    const t = document.getElementById('toast');
    t.innerHTML = '<span>Message copied — Ctrl+V in message field</span>';
    setTimeout(() => t.classList.remove('show'), 4000);
    if (gvWindow && !gvWindow.closed) gvWindow.focus();
  });
}

function hideToast() {
  document.getElementById('toast').classList.remove('show');
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

// Escape key closes modals
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeModal(); closeLogModal(); } });

load();
</script>
</body>
</html>"""


class CRMHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight for bookmarklet cross-origin requests."""
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/leads":
            self._send_json(self._get_leads())
        elif parsed.path == "/api/pending":
            self._send_json(PENDING)
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
        elif self.path == "/api/pending":
            PENDING["phone"] = body.get("phone", "")
            PENDING["msg"] = body.get("msg", "")
            self._send_json({"ok": True})
        elif self.path == "/api/log":
            self._log_activity(body)
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

    def _log_activity(self, data):
        """Append activity to irrevocable log file."""
        log_path = os.path.join(os.path.dirname(DB_PATH), "activity_log.jsonl")
        entry = {
            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "salesman": data.get("salesman", "unknown"),
            "action": data.get("action", ""),
            "lead": data.get("lead", ""),
            "details": data.get("details", "")
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self._cors_headers()
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
