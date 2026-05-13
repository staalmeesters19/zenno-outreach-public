"""Standalone build for the public Zennosurf outreach dashboard.

Reads:
  - leads-wave3.csv         (NL surf orgs — wave 3)
  - leads-wave12.csv        (NL reis-operators — wave 1/2)
  - leads-international.csv (international peer orgs)
  - data_status.json        (Gmail-derived status, refreshed by refresh.py)
  - manual_overrides.json   (optional manual next_action / notes)

Writes:
  - index.html              (masked, AVG-safe, served by GitHub Pages)
  - dashboard-public.html   (same content; legacy filename)

All email addresses are masked. Beslisser names are reduced to initials.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent
WAVE3_CSV = SCRIPT_DIR / "leads-wave3.csv"
WAVE12_CSV = SCRIPT_DIR / "leads-wave12.csv"
INTERNATIONAL_CSV = SCRIPT_DIR / "leads-international.csv"
DATA_STATUS = SCRIPT_DIR / "data_status.json"
MANUAL_OVERRIDES = SCRIPT_DIR / "manual_overrides.json"


# ----------------------------------------------------------------------------
# Name → email patch for CSV rows with TBD/empty email but known outreach addr.
# Copied from _build_dashboard.py (private). Lower-case lead name as key.
# ----------------------------------------------------------------------------
NAME_EMAIL_PATCH = {
    "s.w.v. plankenkoorts": "voorzitter@plankenkoorts.com",
    "my own retreat / jessica groenenberg": "info@myownretreat.com",
    "sup sup club": "info@supsupclub.com",
    "wave sup school": "info@flow-events.nl",
    "surfschool foamball": "info@surfschoolfoamball.com",
    "boardshortz.nl": "jurjen@boardshortz.nl",
    "jumpteam scheveningen": "vicevoorzitter@jumpteam.nl",
    "holland surfing association (hsa)": "info@hsa.nl",
    "natural high surfshop ouddorp": "",
    "brunotti": "contact@brunottisurfcamps.com",
    "noordzee boardstore": "noordzeeboardstore@gmail.com",
    "backyard surf shop": "info@backyardsurfshop.nl",
    "quiksilver surfschool": "nienke@quiksilversurfschool.nl",
    "pepsports zandvoort": "info@pepsports.com",
    "noordzee surfschool": "info@noordboardstore.nl",
    "mifune watersports": "watersports@mifune.nl",
    "ameland adventure": "info@amelandadventure.nl",
    "watersport vereniging zandvoort (wvz)": "info@wvzandvoort.nl",
    "tasha's surfcamp": "natasha@tashasurfcamp.com",
    "soul magazine / 6|surf": "info@soulonline.nl",
    "surfclub callantsoog": "info@surfclubcallantsoog.nl",
    "freakwave castricum": "info@sportsatsea.nl",
    "aloha surf scheveningen": "surfschool@alohasurf.nl",
    "nalu surf & skate shop": "info@nalusb.nl",
    "aquasports katwijk": "info@aquasports.nl",
    "de surf club domburg": "info@desurfclub.com",
    "iksup loosdrecht": "info@iksuploosdrecht.nl",
    "sup away": "frieda@supawayheerenveen.nl",
    "soal surf": "info@soalsurf.nl",
    "supvibes": "info@supvibes.nl",
    "canal sup amsterdam": "yannick@canalsup.nl",
    "cablepark aquabest": "info@cableparkaquabest.nl",
    "surfvillage terschelling": "info@surfvillage.nl",
    "surfschool veerse dam": "info@windsurfschool.nl",
    "surfschool zandvoort (rapa nui)": "info@surfzandvoort.nl",
    "surfschool texel (paal 17)": "info@surfschool-texel.nl",
    # wave1/2
    "explorista travel": "",
    "weadventures": "info@weadventures.com",
    "diogenes reizen": "info@diogenesreizen.nl",
    "sawadee": "info@sawadee.nl",
    "mambo reizen": "info@mambo.nl",
}


# ----------------------------------------------------------------------------
# CSV loaders
# ----------------------------------------------------------------------------

def normalise_email(e):
    if not e:
        return ""
    e = e.strip().lower()
    if e in ("", "tbd"):
        return ""
    return e


def load_wave3():
    leads = []
    if not WAVE3_CSV.exists():
        print(f"  WARN: {WAVE3_CSV.name} missing — skipping")
        return leads
    with open(WAVE3_CSV, "r", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            leads.append({
                "wave": "wave3",
                "segment": (row.get("segment") or "").strip(),
                "naam": (row.get("naam") or "").strip(),
                "type": (row.get("type") or "").strip(),
                "locatie": (row.get("locatie") or "").strip(),
                "website": (row.get("website") or "").strip(),
                "email": normalise_email(row.get("email")),
                "beslisser": (row.get("beslisser") or "").strip(),
                "score": int((row.get("score") or "0") or 0),
                "marokko_al": (row.get("marokko_aanbod_al") or "").strip(),
            })
    return leads


def load_wave12():
    leads = []
    if not WAVE12_CSV.exists():
        print(f"  WARN: {WAVE12_CSV.name} missing — skipping")
        return leads
    seen = set()
    with open(WAVE12_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            naam = (row.get("naam") or "").strip()
            e1 = normalise_email(row.get("email_primary"))
            e2 = normalise_email(row.get("email_secondary"))
            email = e1 or e2
            key = (naam.lower(), email)
            if key in seen:
                continue
            seen.add(key)
            leads.append({
                "wave": "wave12",
                "segment": "wave1-operators",
                "naam": naam,
                "type": (row.get("bucket") or "").strip(),
                "locatie": "",
                "website": (row.get("url") or "").strip(),
                "email": email,
                "beslisser": (row.get("beslisser") or "").strip(),
                "score": 3,
                "marokko_al": "Y",
            })
    return leads


def load_international():
    leads = []
    if not INTERNATIONAL_CSV.exists():
        print(f"  WARN: {INTERNATIONAL_CSV.name} missing — skipping")
        return leads
    with open(INTERNATIONAL_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            leads.append({
                "wave": "wave3-int",
                "segment": (row.get("segment") or "").strip(),
                "naam": (row.get("naam") or "").strip(),
                "type": (row.get("type") or "").strip(),
                "locatie": (row.get("locatie") or "").strip(),
                "website": (row.get("website") or "").strip(),
                "email": normalise_email(row.get("email")),
                "beslisser": (row.get("beslisser") or "").strip(),
                "score": int((row.get("score") or "0") or 0),
                "marokko_al": (row.get("marokko_aanbod_al") or "").strip(),
            })
    return leads


# ----------------------------------------------------------------------------
# Status map merge
# ----------------------------------------------------------------------------

def load_status_map():
    if not DATA_STATUS.exists():
        print(f"  WARN: {DATA_STATUS.name} missing — all leads will be 'not-mailed'")
        return {}
    try:
        return json.loads(DATA_STATUS.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARN: data_status.json invalid: {e}")
        return {}


def load_manual_overrides():
    if not MANUAL_OVERRIDES.exists():
        return {}
    try:
        return json.loads(MANUAL_OVERRIDES.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARN: manual_overrides.json invalid: {e}")
        return {}


def patch_email(lead):
    if lead.get("email"):
        return
    patched = NAME_EMAIL_PATCH.get(lead["naam"].lower())
    if patched:
        lead["email"] = patched


def apply_status(lead, status_map, manual):
    email = (lead.get("email") or "").lower()
    if not email:
        lead.update({"status": "not-mailed", "tone": None, "sent_date": "", "next_action": ""})
        return
    info = dict(status_map.get(email) or {})
    # Manual override layered on top
    if email in manual:
        for k, v in manual[email].items():
            if v is not None:
                info[k] = v
    if not info:
        lead.update({"status": "not-mailed", "tone": None, "sent_date": "", "next_action": ""})
        return
    lead["status"] = info.get("status") or "not-mailed"
    lead["tone"] = info.get("tone")
    lead["sent_date"] = info.get("sent_date") or ""
    lead["next_action"] = info.get("next_action") or ""


# ----------------------------------------------------------------------------
# Masking
# ----------------------------------------------------------------------------

def mask_email(email):
    return "***@***.***" if email else ""


def mask_beslisser(name):
    if not name:
        return ""
    generic_exact = {"bestuur", "bondsbestuur", "editor-in-chief", "local crew (anoniem)", "tbd"}
    name_lower = name.strip().lower()
    if name_lower in generic_exact:
        return name
    if name_lower.startswith("team "):
        return name
    parts = re.split(r"\s*/\s*|\s*\+\s*", name)

    def init_person(p):
        p = p.strip()
        if not p:
            return ""
        p_clean = re.sub(r"\s*\(.*?\)", "", p).strip()
        if not p_clean:
            return p
        tokens = p_clean.split()
        if not tokens:
            return p
        return ". ".join(t[0].upper() for t in tokens if t) + "."

    return " / ".join(init_person(p) for p in parts if p.strip())


def status_emoji(l):
    status = l.get("status", "")
    tone = l.get("tone", "")
    if status == "replied":
        if tone == "positive":   return "\U0001f7e2 in gesprek"
        if tone == "negative":   return "\U0001f534 afgewezen"
        if tone == "auto-reply": return "\U0001f7e1 wachten"
        if tone == "bounce":     return "\U0001f534 bounce"
        if tone == "neutral":    return "\U0001f7e1 wachten"
        return "\U0001f7e1 wachten"
    if status == "sent-no-reply": return "\U0001f7e1 wachten"
    if status == "not-mailed":    return "⏳ niet gemailed"
    if status == "draft-pending": return "\U0001f535 draft"
    return "⚪ open"


# ----------------------------------------------------------------------------
# HTML template (same UI as private dashboard, just masked)
# ----------------------------------------------------------------------------

PUBLIC_HTML = """\
<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex,nofollow" />
<title>Zennosurf Outreach Dashboard — Publieke samenvatting</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  th { cursor: pointer; user-select: none; }
  th .arrow { opacity: 0.35; font-size: 0.7rem; margin-left: 2px; }
  th.sorted .arrow { opacity: 1; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
  .filter-btn { padding: 4px 10px; border-radius: 9999px; font-size: 0.78rem; border: 1px solid #cbd5e1; background: white; transition: all .15s; }
  .filter-btn:hover { background: #f1f5f9; }
  .filter-btn.active { background: #0f172a; color: white; border-color: #0f172a; }
  .stat-card { padding: 14px 16px; border-radius: 12px; }
  .stat-num { font-size: 1.8rem; font-weight: 700; line-height: 1.1; }
  .stat-label { font-size: 0.78rem; opacity: 0.85; margin-top: 2px; }
</style>
</head>
<body class="bg-slate-100 text-slate-900">

<div class="max-w-[1500px] mx-auto p-4 md:p-6">

  <header class="mb-4">
    <h1 class="text-2xl md:text-3xl font-bold">Zennosurf Outreach Dashboard</h1>
    <p class="text-slate-600 mt-1">Wave 3 + wave 1/2 + internationaal — peer-to-peer NL surf-organisaties, reis-operators en EU partners</p>
    <p class="text-xs text-slate-500 mt-1" id="refresh-stamp"></p>
  </header>

  <div class="mb-5 bg-sky-50 border border-sky-200 rounded-xl px-4 py-3 text-sm text-sky-900">
    <strong>\U0001f30d Public summary view</strong> — gemaskerd voor AVG-conformiteit. Volledige dashboard alleen privé toegankelijk.
  </div>

  <section id="stat-cards" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3 mb-5"></section>

  <section class="bg-white rounded-xl shadow-sm p-4 mb-4 sticky top-2 z-10">
    <div class="mb-3">
      <div class="text-xs uppercase font-semibold text-slate-500 mb-2">Status</div>
      <div id="filter-status" class="flex flex-wrap gap-2"></div>
    </div>
    <div class="mb-3">
      <div class="text-xs uppercase font-semibold text-slate-500 mb-2">Score</div>
      <div id="filter-score" class="flex flex-wrap gap-2"></div>
    </div>
    <div>
      <div class="text-xs uppercase font-semibold text-slate-500 mb-2">Segment</div>
      <div id="filter-segment" class="flex flex-wrap gap-2"></div>
    </div>
  </section>

  <section class="bg-white rounded-xl shadow-sm overflow-hidden">
    <div class="overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-100 text-slate-700 sticky top-0">
          <tr>
            <th data-col="idx" class="px-2 py-2 text-left">#<span class="arrow"></span></th>
            <th data-col="naam" class="px-3 py-2 text-left">Lead<span class="arrow"></span></th>
            <th data-col="type" class="px-3 py-2 text-left">Type<span class="arrow"></span></th>
            <th data-col="locatie" class="px-3 py-2 text-left">Locatie<span class="arrow"></span></th>
            <th data-col="beslisser" class="px-3 py-2 text-left">Beslisser<span class="arrow"></span></th>
            <th data-col="email" class="px-3 py-2 text-left">Email<span class="arrow"></span></th>
            <th data-col="segment" class="px-3 py-2 text-left">Segment<span class="arrow"></span></th>
            <th data-col="score" class="px-3 py-2 text-center">Score<span class="arrow"></span></th>
            <th data-col="status" class="px-3 py-2 text-left">Status<span class="arrow"></span></th>
            <th data-col="tone" class="px-3 py-2 text-left">Tone<span class="arrow"></span></th>
            <th data-col="sent_date" class="px-3 py-2 text-left">Sent<span class="arrow"></span></th>
            <th data-col="status_label" class="px-3 py-2 text-left">Stand<span class="arrow"></span></th>
          </tr>
        </thead>
        <tbody id="lead-tbody"></tbody>
      </table>
    </div>
    <div class="px-3 py-2 text-xs text-slate-500 bg-slate-50 border-t" id="row-count"></div>
  </section>

  <footer class="mt-6">
    <div class="bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-600 leading-relaxed">
      <strong>Disclaimer:</strong> Dit is een publieke samenvatting. Persoonlijke gegevens (emailadressen, namen van beslissers) zijn gemaskerd conform AVG. Het originele dashboard met volledige gegevens is privé en niet publiek bereikbaar.
      <span class="block mt-1 text-slate-500">Auto-refresh elke 6 uur via GitHub Actions — build-tijd: __BUILD_TIME__</span>
    </div>
  </footer>

</div>

<script id="leads-data" type="application/json">
__MASKED_JSON__
</script>

<script>
(function () {
  var data = JSON.parse(document.getElementById('leads-data').textContent);

  var STATUSES = [
    { key: 'all',            label: 'All' },
    { key: 'not-mailed',     label: 'Niet gemailed' },
    { key: 'draft-pending',  label: 'Draft' },
    { key: 'sent-no-reply',  label: 'Verzonden' },
    { key: 'replied',        label: 'Reply' },
    { key: 'positive',       label: 'Positief' },
    { key: 'negative',       label: 'Afgewezen' },
    { key: 'auto-reply',     label: 'Auto-reply' },
    { key: 'bounce',         label: 'Bounce' },
  ];

  var SCORES = ['all','5','4','3','2','1'];

  function buildSegments() {
    var segs = [];
    var seen = {};
    data.forEach(function(l) { if (!seen[l.segment]) { seen[l.segment] = true; segs.push(l.segment); } });
    segs.sort();
    var internationalSegs = segs.filter(function(s){ return s && s.indexOf('international-') === 0; });
    var nonInt = segs.filter(function(s){ return !s || s.indexOf('international-') !== 0; });
    var out = [{ key: 'all', label: 'All' }];
    nonInt.forEach(function(s){ out.push({ key: s, label: s }); });
    if (internationalSegs.length) {
      out.push({ key: '__international__', label: '\U0001f30d Internationaal' });
      internationalSegs.forEach(function(s){ out.push({ key: s, label: s }); });
    }
    return out;
  }
  var SEGMENTS = buildSegments();

  var filters = { status: 'all', score: 'all', segment: 'all' };
  var sortState = { col: 'idx', dir: 'asc' };

  function buildFilters() {
    function render(containerId, defs, key, labelKey, valKey) {
      var c = document.getElementById(containerId);
      c.innerHTML = '';
      defs.forEach(function(d) {
        var isStr = typeof d === 'string';
        var val = isStr ? d : d[valKey];
        var lbl = isStr ? (d === 'all' ? 'All' : d) : d[labelKey];
        var btn = document.createElement('button');
        btn.className = 'filter-btn' + (filters[key] === val ? ' active' : '');
        btn.dataset.val = val;
        btn.textContent = lbl;
        btn.addEventListener('click', function(){
          filters[key] = val;
          buildFilters();
          renderTable();
        });
        c.appendChild(btn);
      });
    }
    render('filter-status', STATUSES, 'status', 'label', 'key');
    render('filter-score',  SCORES,   'score');
    render('filter-segment', SEGMENTS, 'segment', 'label', 'key');
  }

  function renderStats() {
    var active = data;
    var total = active.length;
    var intCount = active.filter(function(l){ return l.segment && l.segment.indexOf('international-') === 0; }).length;
    var sentCount = active.filter(function(l){ return l.status !== 'not-mailed' && l.status !== 'draft-pending'; }).length;
    var replies = active.filter(function(l){ return l.status === 'replied'; }).length;
    var positive = active.filter(function(l){ return l.status === 'replied' && l.tone === 'positive'; }).length;
    var rate = sentCount ? ((replies / sentCount) * 100).toFixed(1) : '0.0';
    var drafts = active.filter(function(l){ return l.status === 'draft-pending'; }).length;

    var cards = [
      { label: 'Total leads',    val: total,      bg: 'bg-slate-800 text-white' },
      { label: 'Internationaal', val: intCount,   bg: 'bg-cyan-700 text-white' },
      { label: 'Verzonden',      val: sentCount,  bg: 'bg-blue-600 text-white' },
      { label: 'Replies binnen', val: replies,    bg: 'bg-indigo-600 text-white' },
      { label: 'Positief',       val: positive,   bg: 'bg-green-600 text-white' },
      { label: 'Response-rate',  val: rate + '%', bg: 'bg-emerald-600 text-white' },
      { label: 'Drafts wachtend',val: drafts,     bg: 'bg-amber-500 text-white' },
    ];
    document.getElementById('stat-cards').innerHTML = cards.map(function(c){
      return '<div class="stat-card shadow-sm ' + c.bg + '">' +
        '<div class="stat-num">' + c.val + '</div>' +
        '<div class="stat-label">' + c.label + '</div>' +
      '</div>';
    }).join('');
  }

  function statusBadge(s) {
    var map = {
      'not-mailed':    { cls: 'bg-slate-200 text-slate-700',  txt: 'niet gemailed' },
      'draft-pending': { cls: 'bg-amber-100 text-amber-800',  txt: 'draft' },
      'sent-no-reply': { cls: 'bg-blue-100 text-blue-800',    txt: 'verzonden' },
      'replied':       { cls: 'bg-indigo-100 text-indigo-800',txt: 'reply' },
    };
    var m = map[s] || { cls: 'bg-slate-100 text-slate-700', txt: s };
    return '<span class="badge ' + m.cls + '">' + m.txt + '</span>';
  }

  function toneBadge(t) {
    if (!t) return '';
    var map = {
      'positive':   { cls: 'bg-green-100 text-green-800',   txt: 'positief' },
      'neutral':    { cls: 'bg-slate-100 text-slate-700',   txt: 'neutraal' },
      'negative':   { cls: 'bg-red-100 text-red-800',       txt: 'afgewezen' },
      'auto-reply': { cls: 'bg-yellow-100 text-yellow-800', txt: 'auto-reply' },
      'bounce':     { cls: 'bg-orange-100 text-orange-800', txt: 'bounce' },
    };
    var m = map[t] || { cls: 'bg-slate-100 text-slate-700', txt: t };
    return '<span class="badge ' + m.cls + '">' + m.txt + '</span>';
  }

  function rowClass(l) {
    if (l.status === 'replied' && l.tone === 'positive')   return 'bg-green-50 hover:bg-green-100';
    if (l.status === 'replied' && l.tone === 'negative')   return 'bg-red-50 hover:bg-red-100';
    if (l.status === 'replied' && l.tone === 'auto-reply') return 'bg-yellow-50 hover:bg-yellow-100';
    if (l.tone === 'bounce')                                return 'bg-orange-50 hover:bg-orange-100';
    if (l.status === 'draft-pending')                       return 'bg-blue-50 hover:bg-blue-100';
    if (l.status === 'sent-no-reply')                       return 'bg-slate-50 hover:bg-slate-100';
    return 'bg-white hover:bg-slate-50';
  }

  function applyFilters(rows) {
    return rows.filter(function(l) {
      if (filters.status !== 'all') {
        if (filters.status === 'positive')        { if (!(l.status === 'replied' && l.tone === 'positive')) return false; }
        else if (filters.status === 'negative')   { if (!(l.status === 'replied' && l.tone === 'negative')) return false; }
        else if (filters.status === 'auto-reply') { if (!(l.status === 'replied' && l.tone === 'auto-reply')) return false; }
        else if (filters.status === 'bounce')     { if (l.tone !== 'bounce') return false; }
        else { if (l.status !== filters.status) return false; }
      }
      if (filters.score !== 'all' && String(l.score) !== filters.score) return false;
      if (filters.segment !== 'all') {
        if (filters.segment === '__international__') {
          if (!(l.segment && l.segment.indexOf('international-') === 0)) return false;
        } else if (l.segment !== filters.segment) {
          return false;
        }
      }
      return true;
    });
  }

  function applySort(rows) {
    var k = sortState.col, dir = sortState.dir === 'asc' ? 1 : -1;
    return rows.slice().sort(function(a, b) {
      var va = a[k], vb = b[k];
      if (k === 'idx' || k === 'score') { va = Number(va) || 0; vb = Number(vb) || 0; return (va - vb) * dir; }
      va = (va == null ? '' : String(va)).toLowerCase();
      vb = (vb == null ? '' : String(vb)).toLowerCase();
      if (va < vb) return -1 * dir;
      if (va > vb) return  1 * dir;
      return 0;
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function renderTable() {
    var filtered = applyFilters(data);
    var sorted = applySort(filtered);
    var tbody = document.getElementById('lead-tbody');

    tbody.innerHTML = sorted.map(function(l) {
      var nameCell = l.website
        ? '<a class="font-medium text-slate-900 hover:underline" href="' + esc(l.website) + '" target="_blank" rel="noopener noreferrer">' + esc(l.naam) + '</a>'
        : '<span class="font-medium">' + esc(l.naam) + '</span>';
      var emailCell = l.email
        ? '<span class="font-mono text-slate-400 text-xs">' + esc(l.email) + '</span>'
        : '<span class="text-slate-400">—</span>';
      var beslisserCell = l.beslisser
        ? '<span class="text-slate-600">' + esc(l.beslisser) + '</span>'
        : '<span class="text-slate-400">—</span>';

      return '<tr class="' + rowClass(l) + ' border-b border-slate-200">' +
        '<td class="px-2 py-2 text-slate-500">' + esc(l.idx) + '</td>' +
        '<td class="px-3 py-2">' + nameCell + '</td>' +
        '<td class="px-3 py-2 text-slate-600">' + esc(l.type) + '</td>' +
        '<td class="px-3 py-2 text-slate-600">' + esc(l.locatie) + '</td>' +
        '<td class="px-3 py-2 text-slate-700">' + beslisserCell + '</td>' +
        '<td class="px-3 py-2 text-xs">' + emailCell + '</td>' +
        '<td class="px-3 py-2 text-xs text-slate-600">' + esc(l.segment) + '</td>' +
        '<td class="px-3 py-2 text-center font-semibold">' + esc(l.score) + '</td>' +
        '<td class="px-3 py-2">' + statusBadge(l.status) + '</td>' +
        '<td class="px-3 py-2">' + toneBadge(l.tone) + '</td>' +
        '<td class="px-3 py-2 text-xs text-slate-500 whitespace-nowrap">' + esc(l.sent_date) + '</td>' +
        '<td class="px-3 py-2 text-xs text-slate-700">' + esc(l.status_label) + '</td>' +
      '</tr>';
    }).join('');

    document.getElementById('row-count').textContent =
      'Tonen: ' + sorted.length + ' / ' + data.length + ' leads ' +
      '(status=' + filters.status + ', score=' + filters.score + ', segment=' + filters.segment + ')';

    document.querySelectorAll('thead th[data-col]').forEach(function(th) {
      th.classList.toggle('sorted', th.dataset.col === sortState.col);
      var a = th.querySelector('.arrow');
      if (a) a.textContent = (th.dataset.col === sortState.col) ? (sortState.dir === 'asc' ? '▲' : '▼') : '';
    });
  }

  document.querySelectorAll('thead th[data-col]').forEach(function(th) {
    th.addEventListener('click', function() {
      var col = th.dataset.col;
      if (sortState.col === col) sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
      else { sortState.col = col; sortState.dir = 'asc'; }
      renderTable();
    });
  });

  document.getElementById('refresh-stamp').textContent = 'Laatste auto-refresh (build): __BUILD_TIME__';

  buildFilters();
  renderStats();
  renderTable();
})();
</script>
</body>
</html>"""


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    status_map = {k.lower(): v for k, v in load_status_map().items()}
    manual = {k.lower(): v for k, v in load_manual_overrides().items()}

    wave3 = load_wave3()
    wave12 = load_wave12()
    intl = load_international()
    print(f"  Loaded {len(wave3)} wave3, {len(wave12)} wave12, {len(intl)} international leads")

    all_leads = wave3 + wave12 + intl
    for i, l in enumerate(all_leads, 1):
        l["idx"] = i
        patch_email(l)
        apply_status(l, status_map, manual)

    masked = []
    for l in all_leads:
        masked.append({
            "idx":          l.get("idx", ""),
            "wave":         l.get("wave", ""),
            "segment":      l.get("segment", ""),
            "naam":         l.get("naam", ""),
            "type":         l.get("type", ""),
            "locatie":      l.get("locatie", ""),
            "website":      l.get("website", ""),
            "email":        mask_email(l.get("email", "")),
            "beslisser":    mask_beslisser(l.get("beslisser", "")),
            "score":        l.get("score", ""),
            "marokko_al":   l.get("marokko_al", ""),
            "status":       l.get("status", ""),
            "tone":         l.get("tone", ""),
            "sent_date":    l.get("sent_date", ""),
            "status_label": status_emoji(l),
        })

    from datetime import datetime, timezone
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    masked_json = json.dumps(masked, ensure_ascii=False, indent=2)
    output = PUBLIC_HTML.replace("__MASKED_JSON__", masked_json).replace("__BUILD_TIME__", build_time)

    # Write both filenames for compatibility (GH Pages serves index.html)
    for name in ("index.html", "dashboard-public.html"):
        out_path = SCRIPT_DIR / name
        out_path.write_text(output, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  Written: {name} ({size_kb:.1f} KB)")

    # Tallies
    by_status = {}
    for l in all_leads:
        by_status[l["status"]] = by_status.get(l["status"], 0) + 1
    print(f"  Total leads: {len(all_leads)}")
    print("  By status:")
    for k, v in sorted(by_status.items()):
        print(f"    {k:18s} {v}")

    # Verify masking
    real_email_pat = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    matches = real_email_pat.findall(output)
    real = [x for x in matches if "***" not in x and "tailwindcss.com" not in x and "cdn." not in x]
    if real:
        print(f"  WARNING: unmasked emails found in output: {set(real[:10])}")
        sys.exit(2)
    print("  OK: no real email addresses in output")


if __name__ == "__main__":
    main()
