"""The dashboard web page: one HTML file with its CSS and JavaScript. No internet needed."""

from stockproof.earnings_report import EXTRA_CSS as EARNINGS_CSS
from stockproof.report import CSS as REPORT_CSS

DASH_CSS = """
.wrap { max-width:1280px; }
header { display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between; gap:12px; }
.langs button { border:1px solid var(--line); background:var(--card); color:var(--muted); padding:5px 10px;
                cursor:pointer; font:inherit; font-size:13px; }
.langs button:first-child { border-radius:8px 0 0 8px; } .langs button:last-child { border-radius:0 8px 8px 0; border-left:none; }
.langs button.on { color:var(--text); background:var(--neu-bg); font-weight:600; }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:18px; }
.toolbar input { flex:1 1 260px; min-width:0; padding:9px 12px; border:1px solid var(--line); border-radius:10px;
                 background:var(--card); color:var(--text); font:inherit; }
.toolbar input.small { flex:0 1 160px; }
.btn { padding:9px 14px; border-radius:10px; border:1px solid var(--line); background:var(--card); color:var(--text);
       font:inherit; font-weight:500; cursor:pointer; white-space:nowrap; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
@media (prefers-color-scheme: dark) { .btn.primary { color:#0d1424; } }
.btn:disabled { opacity:.5; cursor:default; }
.status { margin-top:10px; font-size:13px; color:var(--muted); min-height:20px; display:flex; align-items:center; gap:10px; }
.progress { flex:0 0 160px; height:6px; background:var(--neu-bg); border-radius:3px; overflow:hidden; }
.progress div { height:100%; background:var(--accent); width:0; transition:width .3s; }
.cols { display:grid; grid-template-columns:minmax(0, 1.35fr) minmax(0, 1fr); gap:20px; align-items:start; }
@media (max-width:960px) { .cols { grid-template-columns:minmax(0, 1fr); }
  .detail { position:static; max-height:none; overflow:visible; } }
@media (max-width:600px) { tr.groups { display:none; } .progress { flex-basis:90px; } }
.cols > .card { margin-top:16px; }
.detail { position:sticky; top:12px; max-height:calc(100vh - 24px); overflow-y:auto; }
th.sort { cursor:pointer; user-select:none; }
th.sort:hover { color:var(--text); }
th.sort.on::after { content:" ▾"; } th.sort.on.asc::after { content:" ▴"; }
tbody tr.row { cursor:pointer; }
tbody tr.row:hover td { background:var(--bg); }
tbody tr.row.sel td { background:var(--bg); box-shadow:inset 0 1px 0 var(--accent), inset 0 -1px 0 var(--accent); }
tbody tr.row.sel td:first-child { box-shadow:inset 3px 0 0 var(--accent), inset 0 1px 0 var(--accent), inset 0 -1px 0 var(--accent); }
.x { border:none; background:none; color:var(--muted); cursor:pointer; font-size:16px; padding:2px 6px; border-radius:6px; }
.x:hover { color:var(--neg); background:var(--neg-bg); }
tr.groups th { border-bottom:none; padding-bottom:0; }
.group { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; text-align:center; }
.empty { padding:30px 10px; text-align:center; color:var(--muted); }
.chart { width:100%; height:auto; display:block; margin:6px 0 4px; }
.chart .axis { stroke:var(--line); } .chart .zero { stroke:var(--muted); stroke-dasharray:3 3; opacity:.6; }
.chart text { fill:var(--muted); font-size:10px; }
.toggle { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--muted); margin:6px 0; cursor:pointer; }
h3 { font-size:15px; margin:18px 0 6px; }
.back { display:none; float:right; text-decoration:none; color:var(--accent); font-size:18px; padding:0 6px; }
@media (max-width:960px) { .back { display:inline; } }
.err { color:var(--neg); }
[hidden] { display:none !important; }
.alerts { margin-top:16px; padding:12px 18px; }
.alerts h2 { font-size:14px; margin:0 0 6px; color:var(--muted); font-weight:600; }
.alert { display:flex; flex-wrap:wrap; align-items:center; gap:6px 12px; padding:9px 0; border-top:1px solid var(--line); cursor:pointer; }
.alert:first-of-type { border-top:none; }
.alert:hover .tk { color:var(--accent); }
.alert .when { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.alert .hist { color:var(--muted); font-size:13px; flex:1 1 280px; }
.histbox { border-left:3px solid var(--accent); padding:4px 12px; margin:10px 0; }
.histbox p { margin:6px 0; }
.ann { display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; padding:8px 0 8px 10px; border-top:1px solid var(--line);
       border-left:3px solid transparent; }
.ann.imp3 { border-left-color:var(--neg); } .ann.imp2 { border-left-color:var(--muted); }
.ann .tk { cursor:pointer; } .ann .tk:hover { color:var(--accent); }
.ann .when { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.ann-title { flex:1 1 300px; font-size:14px; } .ann-title a { color:var(--text); text-decoration:none; }
.ann-title a:hover { color:var(--accent); text-decoration:underline; }
.ann-sum { flex-basis:100%; color:var(--muted); font-size:13px; }
.badge.cat { font-size:11px; }
.price { display:flex; flex-wrap:wrap; align-items:center; gap:8px 18px; margin:6px 0 10px; }
.price .close { font-size:22px; } .price .rets { display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; font-size:13px; }
.move { display:flex; flex-wrap:wrap; align-items:center; gap:10px; padding:8px 12px; border-radius:10px; background:var(--neu-bg); }
.tabs { display:flex; gap:4px; margin-top:16px; border-bottom:1px solid var(--line); }
.tabs button { border:none; background:none; color:var(--muted); font:inherit; font-weight:600; padding:8px 14px;
               cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
.tabs button.on { color:var(--text); border-bottom-color:var(--accent); }
.seg { display:inline-flex; }
.seg button { border:1px solid var(--line); background:var(--card); color:var(--muted); padding:8px 12px; cursor:pointer; font:inherit; }
.seg button:first-child { border-radius:10px 0 0 10px; } .seg button:last-child { border-radius:0 10px 10px 0; border-left:none; }
.seg button.on { color:var(--text); background:var(--neu-bg); font-weight:600; }
.dims { width:100%; border-collapse:collapse; margin:8px 0; }
.dims td { padding:6px 4px; border-top:1px solid var(--line); font-size:14px; vertical-align:top; }
.dims td.sc { width:44px; text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }
.dims tr.ref td { color:var(--muted); }
.dims .meter { width:90px; height:6px; background:var(--neu-bg); border-radius:3px; overflow:hidden; margin-top:7px; }
.dims .meter div { height:100%; border-radius:3px; }
.dims small { display:block; color:var(--muted); font-size:12px; }
.overall { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.overall b { font-size:28px; font-variant-numeric:tabular-nums; }
.reasons { font-size:13px; color:var(--muted); }
.btn.sm { padding:4px 9px; font-size:13px; }
.home { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:16px; margin-top:16px; }
@media (max-width:860px) { .home { grid-template-columns:minmax(0, 1fr); } }
.home .card { margin-top:0; display:flex; flex-direction:column; }
.home h2 { display:flex; align-items:center; gap:8px; font-size:18px; margin:0 0 4px; }
.home .icon { font-size:20px; }
.home p.lead { color:var(--muted); margin:0 0 10px; font-size:14px; }
.ex { display:flex; align-items:center; gap:8px; padding:8px 0; border-top:1px solid var(--line); }
.ex:first-of-type { border-top:none; }
.ex .go { flex:1; text-align:left; border:none; background:none; color:var(--accent); font:inherit; cursor:pointer; padding:2px 0; }
.ex .go:hover { text-decoration:underline; }
.ex .go:disabled { color:var(--muted); cursor:default; text-decoration:none; }
.ex .cp { border:1px solid var(--line); background:var(--card); color:var(--muted); border-radius:8px; font-size:12px;
          padding:3px 8px; cursor:pointer; white-space:nowrap; }
.ex .cp:hover { color:var(--text); }
.home-out { font-size:13px; color:var(--muted); margin-top:6px; min-height:18px; }
.toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:var(--text); color:var(--bg);
         padding:8px 14px; border-radius:10px; font-size:13px; z-index:20; opacity:0; transition:opacity .2s; pointer-events:none; }
.toast.on { opacity:.92; }
.labform { display:grid; gap:10px; }
.labform label { font-size:13px; color:var(--muted); display:flex; flex-direction:column; gap:4px; }
.labform select, .labform input { padding:8px 10px; border:1px solid var(--line); border-radius:10px; background:var(--card);
                                  color:var(--text); font:inherit; min-width:0; }
.frow { display:grid; grid-template-columns:minmax(0, 2fr) minmax(0, 1fr) minmax(0, 2fr) auto; gap:8px; align-items:center; margin-top:6px; }
.inline { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
.inline label { flex:1 1 140px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chips button { border:1px solid var(--line); background:var(--card); color:var(--text); border-radius:999px; padding:5px 12px;
                cursor:pointer; font:inherit; font-size:13px; }
.chips button:hover { border-color:var(--accent); color:var(--accent); }
#pf-saved a { color:var(--accent); text-decoration:none; } #pf-saved div { padding:3px 0; }
#research-frame { width:100%; border:none; display:block; min-height:400px; margin-top:8px; background:transparent; }
"""

BODY = """
<div class="wrap">
<header>
  <div><h1 id="t-title">stockproof</h1><p id="t-subtitle"></p></div>
  <div class="langs"><button data-lang="en">EN</button><button data-lang="zh">中文</button></div>
</header>
<div class="meta"><span id="model"></span><span id="daily"></span><span id="tip"></span></div>
<nav class="tabs"><button data-tab="home" id="tab-home"></button><button data-tab="stocks" id="tab-stocks"></button><button data-tab="digest" id="tab-digest"></button><button data-tab="screen" id="tab-screen"></button><button data-tab="lab" id="tab-lab"></button><button data-tab="portfolio" id="tab-portfolio"></button><button data-tab="research" id="tab-research"></button></nav>
<div id="view-home" hidden>
  <p class="note" id="home-intro" style="margin:12px 0 0"></p>
  <div class="home" id="home-cards"></div>
</div>
<div id="view-lab" hidden>
  <div class="cols" style="margin-top:4px">
    <section class="card">
      <h2 id="lab-h-templates"></h2><div class="chips" id="lab-templates"></div>
      <h2 id="lab-h-design" style="margin-top:18px"></h2>
      <div class="labform">
        <div class="inline">
          <label><span id="lab-l-type"></span><select id="lab-type"></select></label>
          <label id="lab-market-wrap"><span id="lab-l-market"></span><select id="lab-market"><option value="cn">A 股 / China</option><option value="us">US</option></select></label>
          <label><span id="lab-l-name"></span><input id="lab-name" autocomplete="off"></label>
        </div>
        <div id="lab-filters-wrap"><span class="note" id="lab-l-filters"></span><div id="lab-filters"></div>
          <button class="btn sm" id="lab-add-filter" style="margin-top:6px"></button></div>
        <div id="lab-factor-wrap" hidden><span class="note" id="lab-l-factors"></span><div class="chips" id="lab-factors"></div>
          <label style="max-width:160px;margin-top:6px"><span id="lab-l-top"></span><input id="lab-top" type="number" value="30" min="5" max="100"></label></div>
        <div class="inline" id="lab-hold-wrap">
          <label><span id="lab-l-hold"></span><input id="lab-hold" type="number" value="20" min="1" max="250"></label>
          <label><span id="lab-l-lag"></span><input id="lab-lag" type="number" value="1" min="1" max="10"></label>
        </div>
        <div class="toolbar" style="margin-top:0"><button class="btn primary" id="lab-run"></button>
          <button class="btn" id="lab-reset"></button><span class="note" id="lab-tries"></span></div>
        <p class="note" id="lab-rules" style="margin:0"></p>
      </div>
    </section>
    <section class="card detail" id="lab-result"></section>
  </div>
  <section class="card alerts" id="lab-list" hidden></section>
</div>
<div id="view-portfolio" hidden>
  <div class="cols" style="margin-top:4px">
    <section class="card">
      <h2 id="pf-title"></h2>
      <p class="note" id="pf-help" style="margin:4px 0 8px"></p>
      <textarea id="pf-input" rows="6" style="width:100%;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);font:inherit"></textarea>
      <div class="toolbar" style="margin-top:8px"><button class="btn primary" id="pf-run"></button>
        <button class="btn" id="pf-example"></button><button class="btn" id="pf-watch"></button></div>
      <p class="note" id="pf-what" style="margin:4px 0 0"></p>
      <h2 id="pf-h-saved" style="margin-top:18px"></h2><div id="pf-saved" class="note"></div>
    </section>
    <section class="card detail" id="pf-result"></section>
  </div>
</div>
<div id="view-stocks">
<div class="toolbar">
  <input id="add" autocomplete="off">
  <button class="btn" id="add-btn"></button>
  <input id="filter" class="small" autocomplete="off">
  <button class="btn primary" id="refresh-news"></button>
  <button class="btn" id="refresh-earnings"></button>
</div>
</div>
<div id="view-digest" hidden>
<div class="toolbar">
  <select id="digest-date" class="btn"></select>
  <button class="btn primary" id="make-digest"></button>
  <span class="note" id="digest-note"></span>
</div>
</div>
<div id="view-screen" hidden>
<div class="toolbar">
  <button class="btn primary" id="run-screen"></button>
  <span class="note" id="screen-meta"></span>
</div>
<p class="note" id="screen-test" style="margin:8px 0 0"></p>
</div>
<div id="view-research" hidden>
<div class="toolbar">
  <div class="seg"><button data-market="us" id="mk-us"></button><button data-market="cn" id="mk-cn"></button></div>
  <button class="btn primary" id="run-research"></button>
  <span class="note" id="research-updated"></span>
</div>
<p class="note" id="research-note" style="margin:8px 0 0"></p>
</div>
<div class="status"><div class="progress" id="progress" hidden><div></div></div><span id="status"></span></div>
<section class="card alerts" id="moves" hidden></section>
<section class="card alerts" id="alerts" hidden></section>
<section class="card alerts" id="anns" hidden></section>
<section class="card alerts" id="calendar" hidden></section>
<div class="cols" id="stocks-body">
  <section class="card"><div class="wide"><table id="overview"></table></div></section>
  <section class="card detail" id="detail"></section>
</div>
<div class="cols" id="screen-body" hidden>
  <section class="card"><div class="wide"><table id="screen-table"></table></div></section>
  <section class="card detail" id="screen-detail"></section>
</div>
<iframe id="research-frame" title="research" hidden></iframe>
<iframe id="digest-frame" title="digest" hidden style="width:100%;border:none;display:block;min-height:400px;margin-top:8px"></iframe>
<p class="note" id="disclaimer" style="margin-top:20px"></p>
</div>
"""

JS = r"""
const $ = (s) => document.querySelector(s);
let SC = null, scSelected = null;
let T = {}, S = null, rows = [], selected = null, sortKey = "mood", sortAsc = false, showLow = false, pollTimer = null;
let tab = ["#research", "#digest", "#screen", "#stocks", "#lab", "#portfolio"].includes(location.hash) ? location.hash.slice(1) : "home", market = "us", alerts = [], showAllAlerts = false, cal = {items: []}, anns = [], showAllAnns = false, movesList = [];
try { market = localStorage.getItem("mm_market") || "us"; } catch (e) {}

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const tr = (k, vars) => { let s = T[k] || k; for (const [a, b] of Object.entries(vars || {})) s = s.replace("{" + a + "}", b); return s; };
const num = (v, d = 2, sign = true) => (v === null || v === undefined) ? "—" : (sign && v > 0 ? "+" : "") + Number(v).toFixed(d);

// The page lives on after the program stops (Ctrl+C); say so instead of silently doing nothing.
function showOffline(on) {
  let el = document.getElementById("offline");
  if (on && !el) {
    document.body.insertAdjacentHTML("afterbegin", `<p id="offline" class="err" style="position:sticky;top:0;z-index:9;margin:0;padding:10px 16px;background:var(--bg,#fff);border-bottom:1px solid currentColor">${esc(tr("d_offline"))}</p>`);
  } else if (!on && el) el.remove();
}

async function api(path, body) {
  const opt = body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {};
  let r;
  try { r = await fetch(path, opt); }
  catch (e) { showOffline(true); throw e; }
  showOffline(false);
  const data = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 409) throw new Error(data.error || r.status);
  return data;
}

function moodClass(v) { return v === null || v === undefined ? "none" : v >= 0.15 ? "positive" : v <= -0.15 ? "negative" : "neutral"; }
function chip(v) { return `<span class="chip ${moodClass(v)}">${num(v)}</span>`; }
function sueChip(v) {
  const c = v === null || v === undefined ? "none" : v >= 1 ? "positive" : v <= -1 ? "negative" : "neutral";
  return `<span class="chip ${c}">${num(v, 1)}</span>`;
}
function guidance(g) { return g ? `<span class="badge ${esc(g)}">${esc(tr("g_" + g))}</span>` : "—"; }
function bar(v) {
  if (v === null || v === undefined) return '<div class="bar"><div class="mid"></div></div>';
  const w = Math.abs(v) * 50, left = v >= 0 ? 50 : 50 - w, col = v >= 0 ? "var(--pos)" : "var(--neg)";
  return `<div class="bar"><div class="mid"></div><div class="fill" style="left:${left}%;width:${w}%;background:${col}"></div></div>`;
}
function few(r) { return r.few ? `<span class="few" title="${esc(tr("few"))}">${esc(tr("few_short"))}</span>` : ""; }

function applyText() {
  document.documentElement.lang = S.lang === "zh" ? "zh-CN" : "en";
  document.title = tr("title");
  $("#t-title").textContent = tr("title");
  $("#t-subtitle").textContent = tr("subtitle");
  $("#model").textContent = tr("model") + ": " + S.model;
  $("#daily").textContent = S.daily ? tr(S.daily.ok ? "d_daily_last" : "d_daily_failed", {time: (S.daily.finished || "").replace("T", " ").slice(0, 16)}) : "";
  $("#tip").textContent = tr("d_tip");
  $("#add").placeholder = tr("d_add_ph");
  $("#add-btn").textContent = tr("d_add");
  $("#filter").placeholder = tr("d_search");
  $("#refresh-news").textContent = tr("d_refresh_news");
  $("#refresh-earnings").textContent = tr("d_refresh_earnings");
  $("#disclaimer").textContent = tr("disclaimer");
  $("#tab-stocks").textContent = tr("d_tab_stocks");
  $("#tab-research").textContent = tr("d_tab_research");
  $("#tab-digest").textContent = tr("d_tab_digest");
  $("#tab-screen").textContent = tr("d_tab_screen");
  $("#tab-home").textContent = tr("d_tab_home"); $("#tab-lab").textContent = tr("d_tab_lab");
  $("#home-intro").textContent = tr("d_home_intro");
  for (const k of ["templates", "design"]) $("#lab-h-" + k).textContent = tr("d_lab_h_" + k);
  for (const k of ["type", "market", "name", "filters", "factors", "top", "hold", "lag"]) $("#lab-l-" + k).textContent = tr("d_lab_l_" + k);
  $("#lab-add-filter").textContent = tr("d_lab_add"); $("#lab-run").textContent = tr("d_lab_run");
  $("#lab-reset").textContent = tr("d_lab_reset"); $("#lab-rules").textContent = tr("d_lab_rules");
  $("#pf-title").textContent = tr("d_pf_title"); $("#pf-help").textContent = tr("d_pf_help");
  $("#tab-portfolio").textContent = tr("d_pf_title"); $("#pf-example").textContent = tr("d_pf_example");
  $("#pf-watch").textContent = tr("d_pf_watch"); $("#pf-what").textContent = tr("d_pf_what");
  $("#pf-h-saved").textContent = tr("d_pf_saved");
  $("#pf-input").placeholder = "600519 100, 300750 200, 00700 300, AAPL 50"; $("#pf-run").textContent = tr("d_pf_run");
  $("#run-screen").textContent = tr("d_screen_run");
  $("#make-digest").textContent = tr("d_make_digest");
  $("#digest-note").textContent = tr("d_digest_note");
  $("#mk-us").textContent = tr("d_market_us");
  $("#mk-cn").textContent = tr("d_market_cn");
  $("#run-research").textContent = tr("d_run_research");
  $("#research-note").textContent = tr("d_research_note");
  document.querySelectorAll(".langs button").forEach((b) => b.classList.toggle("on", b.dataset.lang === S.lang));
  let demo = document.getElementById("demo-banner");
  if (S.demo && !demo) {
    document.querySelector(".wrap").insertAdjacentHTML("afterbegin", `<p id="demo-banner" class="note" style="margin:0 0 12px;padding:10px 14px;border-radius:10px;background:var(--neu-bg)"></p>`);
    demo = document.getElementById("demo-banner");
  }
  if (demo) demo.textContent = tr("d_demo_banner", {date: S.demo.as_of});
}

function renderStatus() {
  const j = S.job, prog = $("#progress"), st = $("#status");
  const busy = j.running;
  $("#refresh-news").disabled = busy; $("#refresh-earnings").disabled = busy; $("#run-research").disabled = busy; $("#run-screen").disabled = busy;
  prog.hidden = !busy;
  if (busy) {
    prog.firstElementChild.style.width = (j.total ? 100 * j.done / j.total : 0) + "%";
    const cur = (j.kind || "").startsWith("research_") ? tr("d_tab_research") + " · " + tr("d_market_" + j.kind.slice(9))
      : j.kind === "screen" ? tr("d_tab_screen") : (j.current || "…");
    st.textContent = tr("d_running", {current: cur, done: j.done, total: j.total});
  } else if (j.error) {
    st.innerHTML = `<span class="err">${esc(tr("d_failed", {error: j.error}))}</span>`;
  } else if (j.finished_at) {
    st.textContent = tr("d_finished", {time: j.finished_at.replace("T", " ")});
  } else if (!S.sec_contact && !S.demo && tab === "stocks") {
    st.textContent = tr("d_need_sec");
  } else st.textContent = "";
}

function sortedRows() {
  const f = $("#filter").value.trim().toUpperCase();
  const list = rows.filter((r) => !f || r.ticker.includes(f) || (r.name || "").toUpperCase().includes(f));
  const val = (r) => sortKey === "ticker" ? r.ticker : r[sortKey];
  return list.sort((a, b) => {
    const x = val(a), y = val(b);
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    const c = typeof x === "string" ? x.localeCompare(y) : x - y;
    return sortAsc ? c : -c;
  });
}

function renderOverview() {
  const tbl = $("#overview");
  if (!S.watchlist.length) { tbl.innerHTML = `<tr><td class="empty">${esc(tr("d_empty"))}</td></tr>`; return; }
  const th = (key, label, extra = "") =>
    `<th class="sort ${sortKey === key ? "on" + (sortAsc ? " asc" : "") : ""} ${extra}" data-key="${key}">${esc(label)}</th>`;
  let html = `<thead><tr class="groups"><th></th><th></th><th colspan="3" class="group">${esc(tr("d_news"))}</th>
    <th colspan="3" class="group">${esc(tr("d_earnings"))}</th><th></th></tr><tr>
    ${th("ticker", tr("ticker"))}${th("d1", tr("d_today"))}${th("mood", tr("mood"))}<th class="hide-sm"></th>${th("relevant", tr("relevant"))}
    ${th("e_tone", tr("e_tone"))}${th("e_guidance", tr("e_guidance"), "hide-sm")}${th("sue", "SUE")}<th></th></tr></thead><tbody>`;
  for (const r of sortedRows()) {
    html += `<tr class="row ${r.ticker === selected ? "sel" : ""}" data-tk="${esc(r.ticker)}">
      <td class="tk">${esc(r.ticker)}<small>${esc(r.name)}</small></td>
      <td>${pctChip(r.d1, r.unusual)}</td>
      <td>${chip(r.mood)}${few(r)}</td><td class="hide-sm">${bar(r.mood)}</td>
      <td class="num">${r.relevant} / ${r.headlines}</td>
      <td>${r.e_tone === null ? '<span class="chip none">—</span>' : chip(r.e_tone)}</td>
      <td class="hide-sm">${guidance(r.e_guidance)}</td><td>${sueChip(r.sue)}</td>
      <td><button class="x" title="${esc(tr("d_remove"))}" data-rm="${esc(r.ticker)}">×</button></td></tr>`;
  }
  tbl.innerHTML = html + "</tbody>";
}

function chartSVG(hist) {
  if (!hist.length) return `<p class="note">${esc(tr("d_no_history"))}</p>`;
  const W = 600, H = 150, P = 24, days = (d) => new Date(d + "T00:00:00").getTime() / 864e5;
  const x0 = Math.min(...hist.map((h) => days(h.date))), x1 = Math.max(...hist.map((h) => days(h.date)), x0 + 6);
  const lim = Math.max(0.5, ...hist.map((h) => Math.abs(h.mood)));
  const X = (d) => P + (W - 2 * P) * (days(d) - x0) / (x1 - x0), Y = (v) => H / 2 - (H / 2 - 14) * v / lim;
  const bw = Math.max(3, Math.min(14, (W - 2 * P) / (x1 - x0 + 1) * 0.7));
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img"><line class="zero" x1="${P}" x2="${W - P}" y1="${H / 2}" y2="${H / 2}"/>`;
  for (const h of hist) {
    const y = Y(h.mood), top = Math.min(y, H / 2), hh = Math.max(1, Math.abs(y - H / 2));
    const col = h.mood >= 0 ? "var(--pos)" : "var(--neg)";
    s += `<rect x="${X(h.date) - bw / 2}" y="${top}" width="${bw}" height="${hh}" rx="2" fill="${col}" opacity="${h.n < 3 ? 0.45 : 0.9}">
      <title>${esc(h.date)}: ${num(h.mood)} (${esc(tr("d_n_headlines", {n: h.n}))})</title></rect>`;
  }
  s += `<text x="${P}" y="${H - 2}">${esc(hist[0].date)}</text><text x="${W - P}" y="${H - 2}" text-anchor="end">${esc(hist[hist.length - 1].date)}</text>`;
  s += `<text x="2" y="12">+${lim.toFixed(1)}</text><text x="2" y="${H - 14}">-${lim.toFixed(1)}</text></svg>`;
  return s;
}

function pctChip(v, flag) {
  if (v === null || v === undefined) return '<span class="chip none">—</span>';
  const c = v >= 0.005 ? "positive" : v <= -0.005 ? "negative" : "neutral";
  return `<span class="chip ${c}" ${flag ? `title="${esc(tr("d_unusual"))}"` : ""}>${flag ? "⚡" : ""}${pct(v).replace(/(\.\d)\d%/, "$1%")}</span>`;
}

function spark(vals) {
  if (!vals || vals.length < 2) return "";
  const W = 220, H = 44, lo = Math.min(...vals), hi = Math.max(...vals), r = hi - lo || 1;
  const pts = vals.map((v, i) => `${(W * i / (vals.length - 1)).toFixed(1)},${(H - 4 - (H - 8) * (v - lo) / r).toFixed(1)}`).join(" ");
  const col = vals[vals.length - 1] >= vals[0] ? "var(--pos)" : "var(--neg)";
  return `<svg viewBox="0 0 ${W} ${H}" style="width:220px;height:44px"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/></svg>`;
}

function priceHTML(d) {
  const q = d.price;
  if (!q) return "";
  let h = `<div class="price"><div><b class="close">${q.close.toFixed(2)}</b> <span class="note">${esc(q.date)}</span></div>
    <div class="rets"><span>${esc(tr("d_today"))} ${pctChip(q.d1)}</span><span class="note">${esc(tr("d_vs_market", {x: pct(q.d1_excess)}))}</span>
    <span>${esc(tr("d_1w"))} ${pctChip(q.w1)}</span><span>${esc(tr("d_1m"))} ${pctChip(q.m1)}</span><span>${esc(tr("d_ytd"))} ${pctChip(q.ytd)}</span></div>
    ${spark(q.spark)}</div>`;
  if (q.move) {
    h += `<div class="move"><span>⚡ ${esc(tr("d_move_line", {day: q.move.date, ret: pct(q.move.ret), excess: pct(q.move.excess)}))}</span>
      <button class="btn" data-why="${esc(d.ticker)}" data-day="${esc(q.move.date)}">${esc(tr("d_why"))}</button></div><div id="why-box"></div>`;
  }
  return h;
}

function whyHTML(x) {
  if (x.error) return `<p class="note">${esc(tr("d_why_error", {error: x.error}))}</p>`;
  const ev = x.evidence || [];
  const cite = (t) => esc(t).replace(/\[(\d+)\]/g, (m, n) => ev[n - 1] && ev[n - 1].link ? `<a href="${esc(ev[n - 1].link)}" target="_blank" rel="noopener">[${n}]</a>` : m);
  let h = `<div class="histbox"><p>${cite(x.summary || "")}</p>`;
  if ((x.causes || []).length) h += `<ul class="pts">${x.causes.map((c) => `<li>${cite(c.text)} ${c.evidence.map((n) => ev[n - 1] && ev[n - 1].link ? `<a href="${esc(ev[n - 1].link)}" target="_blank" rel="noopener">[${n}]</a>` : `[${n}]`).join(" ")}</li>`).join("")}</ul>`;
  h += `<p class="note">${esc(tr("d_why_conf", {c: tr("d_conf_" + (x.confidence || "low"))}))}${x.explained ? "" : " · " + esc(tr("d_why_unexplained"))}</p>`;
  if (ev.length) h += `<details><summary>${esc(tr("d_why_evidence", {n: ev.length}))}</summary><ol class="pts">${ev.map((e) =>
    `<li><span class="note">${esc(e.date)} · ${esc(tr("d_kind_" + e.kind))}</span> ${e.link ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}</li>`).join("")}</ol></details>`;
  return h + `<p class="note">${esc(tr("d_why_note"))}</p></div>`;
}

function renderMoves() {
  const box = $("#moves");
  const list = movesList.filter((m) => S.watchlist.includes(m.ticker));
  box.hidden = !list.length || tab !== "stocks";
  if (!list.length) return;
  box.innerHTML = `<h2>${esc(tr("d_moves"))}</h2>` + list.slice(0, 8).map((m) =>
    `<div class="alert" data-tk="${esc(m.ticker)}"><span class="when">${esc(m.day)}</span>
     <span class="tk">${esc(m.ticker)} <small>${esc(m.name)}</small></span>${pctChip(m.ret, true)}
     <span class="hist">${esc(tr("d_vs_market", {x: pct(m.excess)}))}</span>
     <button class="btn" data-why="${esc(m.ticker)}" data-day="${esc(m.day)}" style="padding:5px 10px;font-size:13px">${esc(tr("d_why"))}</button></div>`).join("");
}

function compareHTML(x) {
  if (x.error === "demo") return `<p class="note">${esc(tr("d_demo_na"))}</p>`;
  if (x.error) return `<p class="note">${esc(tr("d_compare_error", {error: x.error}))}</p>`;
  const dir = {better: "positive", worse: "negative", neutral: "neutral"};
  const link = (d) => d.url && /^https?:\/\//.test(d.url) ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.date)}</a>` : esc(d.date);
  let h = `<div class="histbox"><p><b>${esc(x.headline)}</b></p>`;
  if ((x.changes || []).length) h += `<table class="hist"><thead><tr><th>${esc(tr("d_cmp_area"))}</th><th>${link(x.prev)}</th><th>${link(x.now)}</th><th></th></tr></thead><tbody>` +
    x.changes.map((c) => `<tr><td>${esc(tr("d_area_" + c.area))}</td><td class="note">${esc(c.before)}</td><td>${esc(c.now)}</td>
      <td><span class="chip ${dir[c.direction]}">${esc(tr("d_dir_" + c.direction))}</span></td></tr>`).join("") + "</tbody></table>";
  if ((x.new_risks || []).length) h += `<p><b>${esc(tr("d_new_risks"))}</b></p><ul class="pts">${x.new_risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`;
  h += `<p class="note">${esc(tr("d_tone_shift"))} ${chip(x.tone_shift)} · ${esc(tr("d_compare_note"))}</p></div>`;
  return h;
}

async function askCompare(tk) {
  const box = $("#compare-box"), btn = $("#compare-btn");
  if (!box) return;
  btn.disabled = true;
  box.innerHTML = `<p class="note">${esc(tr("d_compare_wait"))}</p>`;
  try { box.innerHTML = compareHTML(await api("/api/compare", {ticker: tk})); }
  catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  btn.disabled = false;
}

async function askWhy(tk, day) {
  if (selected !== tk) { selected = tk; renderOverview(); await loadStock(); }
  $("#detail").scrollIntoView({behavior: "smooth", block: "start"});
  const box = $("#why-box");
  if (!box) return;
  box.innerHTML = `<p class="note">${esc(tr("d_why_wait"))}</p>`;
  try { box.innerHTML = whyHTML(await api("/api/explain", {ticker: tk, day})); }
  catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
}

const pct = (v) => (v === null || v === undefined) ? "—" : (v > 0 ? "+" : "") + (100 * v).toFixed(2) + "%";

function historyHTML(rep, hl) {
  if (!hl) return "";
  let body = "";
  if (hl.market === null) body = `<p class="note">${esc(tr("d_hist_hk"))}</p>`;
  else if (hl.missing) body = `<p class="note">${esc(tr("d_hist_missing"))}</p>`;
  else {
    if (rep && rep.sue_pending) body += `<p class="note">${esc(tr("d_hist_pending"))}</p>`;
    if (hl.sue) body += `<p>${esc(tr("d_hist_sue", {n: hl.sue.n, bucket: hl.sue.bucket, reaction: pct(hl.sue.reaction),
      drift: pct(hl.sue.drift), beat: hl.sue.beat === null ? "—" : Math.round(100 * hl.sue.beat) + "%"}))}</p>`;
    if (hl.tone) body += `<p>${esc(tr("d_hist_tone", {n: hl.tone.n, tone: tr("d_tone_" + hl.tone.bucket),
      reaction: pct(hl.tone.reaction), drift: pct(hl.tone.drift)}))}</p>`;
    if (!body) return "";
    body += `<p class="note">${esc(tr("d_hist_note"))}</p>`;
  }
  return `<h3>${esc(tr("d_hist_title"))}</h3><div class="histbox">${body}</div>`;
}

function renderAlerts() {
  const box = $("#alerts");
  const list = alerts.filter((a) => S.watchlist.includes(a.ticker));
  box.hidden = !list.length || tab !== "stocks";
  if (!list.length) return;
  const shown = showAllAlerts ? list : list.slice(0, 6);
  const more = list.length > 6 ? `<button class="btn" id="alerts-more" style="margin-top:6px;padding:5px 10px;font-size:13px">${
    esc(showAllAlerts ? tr("d_alerts_less") : tr("d_alerts_more", {n: list.length}))}</button>` : "";
  box.innerHTML = `<h2>${esc(tr("d_alerts"))}</h2>` + shown.map((a) => {
    const h = (a.history || {}).sue || (a.history || {}).tone;
    const sue = a.sue === null || a.sue === undefined
      ? `<span class="chip none">${esc(a.sue_pending ? tr("d_sue_pending") : "SUE —")}</span>` : `<span title="SUE">${sueChip(a.sue)}</span>`;
    return `<div class="alert" data-tk="${esc(a.ticker)}"><span class="tk">${esc(a.ticker)} <small>${esc(a.name)}</small></span>
      <span class="when">${esc(a.date || "")}</span>${sue}${a.tone === null || a.tone === undefined ? "" : chip(a.tone)}
      ${guidance(a.guidance)}<span class="hist">${h ? esc(tr("d_alert_hist", {reaction: pct(h.reaction), drift: pct(h.drift)})) : ""}</span></div>`;
  }).join("") + more;
  const btn = $("#alerts-more");
  if (btn) btn.onclick = (e) => { e.stopPropagation(); showAllAlerts = !showAllAlerts; renderAlerts(); };
}

function annLine(a, withName) {
  const imp = a.importance >= 3 ? "imp3" : a.importance >= 2 ? "imp2" : "";
  const score = a.read ? chip(a.read.impact) : (a.direction ? `<span class="chip ${a.direction > 0 ? "positive" : "negative"}">${a.direction > 0 ? "+" : "−"}</span>` : "");
  const title = a.title.includes(":") ? a.title.slice(a.title.indexOf(":") + 1) : a.title;
  const link = /^https?:\/\//.test(a.url || "") ? `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(title)}</a>` : esc(title);
  return `<div class="ann ${imp}"><span class="when">${esc(a.date)}</span>${withName ? `<span class="tk" data-tk="${esc(a.ticker)}">${esc(a.ticker)} <small>${esc(a.name || "")}</small></span>` : ""}
    <span class="badge cat">${esc(a.category_name)}</span>${score}<span class="ann-title">${link}</span>
    ${a.read && a.read.summary ? `<div class="ann-sum">${esc(a.read.summary)}</div>` : ""}</div>`;
}

function renderAnns() {
  const box = $("#anns");
  const list = anns.filter((a) => S.watchlist.includes(a.ticker));
  box.hidden = !list.length || tab !== "stocks";
  if (!list.length) return;
  const shown = showAllAnns ? list : list.slice(0, 6);
  const more = list.length > 6 ? `<button class="btn" id="anns-more" style="margin-top:6px;padding:5px 10px;font-size:13px">${
    esc(showAllAnns ? tr("d_alerts_less") : tr("d_alerts_more", {n: list.length}))}</button>` : "";
  box.innerHTML = `<h2>${esc(tr("d_anns"))}</h2>` + shown.map((a) => annLine(a, true)).join("") + more;
  const btn = $("#anns-more");
  if (btn) btn.onclick = (e) => { e.stopPropagation(); showAllAnns = !showAllAnns; renderAnns(); };
}

function renderCalendar() {
  const box = $("#calendar");
  const list = (cal.items || []).filter((c) => S.watchlist.includes(c.ticker));
  box.hidden = !list.length || tab !== "stocks";
  if (!list.length) return;
  box.innerHTML = `<h2>${esc(tr("d_cal"))}</h2>` + list.map((c) => {
    const when = c.time ? `<span class="badge">${esc(tr("d_cal_" + c.time))}</span>` : "";
    const src = c.source === "estimate" ? `<span class="few" title="${esc(tr("d_cal_est_tip"))}">${esc(tr("d_cal_est"))}</span>`
      : c.changed ? `<span class="few">${esc(tr("d_cal_changed"))}</span>` : "";
    const eps = c.eps_forecast === null || c.eps_forecast === undefined ? ""
      : `<span class="hist">${esc(tr("d_cal_eps", {eps: c.eps_forecast.toFixed(2)}))}</span>`;
    return `<div class="alert" data-tk="${esc(c.ticker)}"><span class="when">${esc(c.date)}</span>
      <span class="tk">${esc(c.ticker)} <small>${esc(c.name)}</small></span>${when}${src}${eps}</div>`;
  }).join("");
}

function earningsHTML(e, eps, fc) {
  let h = `<h3>${esc(tr("e_title"))}</h3>`;
  if (fc) {
    const ch = fc.change_pct === null || fc.change_pct === undefined ? "" : num(fc.change_pct, 0) + "%";
    h += `<p><span class="badge">${esc(tr("e_forecast"))}</span> ${esc(tr("e_forecast_line", {type: fc.type || "", change: ch, period: fc.period || "", date: fc.date || ""}))}</p>`;
    if (fc.reason) h += `<p class="note">${esc(fc.reason)}</p>`;
  }
  if (!e) h += `<p class="note">${esc(S.sec_contact || /\.(SH|SZ|BJ|HK)$/.test(selected || "") ? tr("d_no_earnings") : tr("d_need_sec"))}</p>`;
  else {
    h += `<div class="grid"><div class="kv"><b>${esc(tr("e_release"))}</b>${esc(e.filed)}</div>
      <div class="kv"><b>${esc(tr("e_tone"))}</b>${chip(e.tone)}</div>
      <div class="kv"><b>${esc(tr("e_revenue"))}</b>${esc(e.revenue_growth)}</div>
      <div class="kv"><b>${esc(tr("e_guidance"))}</b>${guidance(e.guidance)}</div></div>
      <p>${esc(e.summary)}</p>`;
    if ((e.key_points || []).length) h += `<b>${esc(tr("e_points"))}</b><ul class="pts">${e.key_points.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if ((e.risks || []).length) h += `<b>${esc(tr("e_risks"))}</b><ul class="pts">${e.risks.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if (e.url && /^https?:\/\//.test(e.url)) h += `<a class="src" href="${esc(e.url)}" target="_blank" rel="noopener">${esc(tr("e_read"))} ↗</a>`;
    h += `<div style="margin-top:10px"><button class="btn" id="compare-btn">${esc(tr("d_compare"))}</button></div><div id="compare-box"></div>`;
  }
  if (eps.length) {
    h += `<details><summary>${esc(tr("e_history"))}</summary><div class="wide"><table class="hist"><thead><tr>
      <th>${esc(tr("e_quarter_end"))}</th><th>${esc(tr("e_eps"))}</th><th>${esc(tr("e_year_ago"))}</th><th>SUE</th><th>${esc(tr("e_filed"))}</th>
      </tr></thead><tbody>${eps.map((q) => `<tr><td class="num">${esc(q.end)}${q.q4 ? "*" : ""}</td><td class="num">${num(q.eps, 2, false)}</td>
      <td class="num">${num(q.year_ago, 2, false)}</td><td>${sueChip(q.sue)}</td><td class="num">${esc(q.filed)}</td></tr>`).join("")}
      </tbody></table></div><p class="note">* ${esc(tr("e_q4"))}</p></details>`;
  }
  return h;
}

function renderDetail(d) {
  const box = $("#detail");
  if (!d) { box.innerHTML = `<p class="empty">${esc(tr("d_select"))}</p>`; return; }
  const minRel = d.min_relevance, heads = d.headlines.filter((h) => showLow || (h.relevance >= minRel && !h.dup));
  const otherLang = d.headlines.some((h) => h.lang && h.lang !== S.lang);
  let h = `<h2>${esc(d.ticker)} · ${esc(d.name)} <a class="back" href="#overview" title="↑">↑</a></h2>${priceHTML(d)}<h3>${esc(tr("d_history"))}</h3>${chartSVG(d.history)}
    <h3>${esc(tr("d_headlines"))} <span class="num">${heads.length} / ${d.headlines.length}</span></h3>
    <label class="toggle"><input type="checkbox" id="low" ${showLow ? "checked" : ""}> ${esc(tr("d_show_low"))}</label>`;
  if (otherLang) h += `<p class="note">${esc(tr("d_other_lang"))}</p>`;
  h += heads.length ? `<ul class="news">${heads.map((x) => {
    const low = x.relevance < minRel || x.dup;
    const title = x.link && /^https?:\/\//.test(x.link) ? `<a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title);
    return `<li class="${low ? "low" : ""}"><div>${chip(x.score)}</div><div>${title}</div><div class="why">${esc(x.reason)}</div>
      <div class="sub">${esc(x.date)} · ${esc(x.source)} · ${esc(tr("relevance"))} ${num(x.relevance, 1, false)}${x.dup ? " · " + esc(tr("dup")) : low ? " · " + esc(tr("low_relevance")) : ""}</div></li>`;
  }).join("")}</ul>` : `<p class="note">${esc(tr("no_news"))}</p>`;
  const annHTML = (d.announcements || []).length
    ? `<h3>${esc(tr("d_anns_stock"))}</h3>` + d.announcements.map((a) => annLine(a, false)).join("") : "";
  box.innerHTML = h + rankHTML(d) + earningsHTML(d.earnings, d.eps, d.forecast) + historyHTML(d.report, d.history_like) + annHTML;
  $("#low").onchange = (e) => { showLow = e.target.checked; renderDetail(d); };
}

async function loadStock() {
  if (!selected) return renderDetail(null);
  try { renderDetail(await api(`/api/stock?ticker=${encodeURIComponent(selected)}&lang=${S.lang}`)); }
  catch (e) { selected = null; renderDetail(null); }
}

async function loadAll() {
  S = await api("/api/state");
  T = await api(`/api/i18n?lang=${S.lang}`);
  applyText(); renderStatus();
  rows = await api(`/api/overview?lang=${S.lang}`);
  try { alerts = await api(`/api/alerts?lang=${S.lang}`); } catch (e) { alerts = []; }
  try { cal = await api("/api/calendar"); } catch (e) { cal = {items: []}; }
  try { anns = await api(`/api/announcements?lang=${S.lang}`); } catch (e) { anns = []; }
  try { movesList = await api("/api/unusual"); } catch (e) { movesList = []; }
  if (selected && !S.watchlist.includes(selected)) selected = null;
  renderOverview(); await loadStock();
  showTab(tab);
  if (S.job.running) startPolling();
}

function showTab(t) {
  tab = t;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  $("#view-stocks").hidden = $("#stocks-body").hidden = t !== "stocks";
  $("#view-research").hidden = $("#research-frame").hidden = t !== "research";
  $("#view-digest").hidden = $("#digest-frame").hidden = t !== "digest";
  $("#view-screen").hidden = $("#screen-body").hidden = t !== "screen";
  $("#view-home").hidden = t !== "home";
  $("#view-lab").hidden = t !== "lab";
  $("#view-portfolio").hidden = t !== "portfolio";
  renderMoves(); renderAlerts(); renderAnns(); renderCalendar();
  history.replaceState(null, "", t === "home" ? location.pathname : "#" + t);
  if (t === "research") loadResearch();
  if (t === "digest") loadDigest();
  if (t === "screen") loadScreen();
  if (t === "home") renderHome();
  if (t === "lab") loadLabTab();
  if (t === "portfolio") loadPortfolioTab();
}

// ---------- screen + evidence scorecards ----------
async function loadScreen() {
  try { SC = await api(`/api/screen?lang=${S.lang}`); } catch (e) { SC = {meta: null, results: [], cards: {}}; }
  renderScreen();
}

function renderScreen() {
  const m = SC.meta, t = SC.test && SC.test.composite;
  $("#screen-meta").textContent = m ? tr("d_screen_meta", {date: m.as_of, n: m.screened, top: m.top, per: m.per_industry || "∞"}) : "";
  let note = t && t.n ? tr("d_screen_test", {x: pct(t.ann_excess), t: num(t.t, 1, false), hit: Math.round(100 * t.hit_rate) + "%"}) : "";
  if (m && m.momentum === false) note += " " + tr("d_screen_nomom");
  $("#screen-test").textContent = note;
  const tbl = $("#screen-table");
  if (!m) { tbl.innerHTML = `<tr><td class="empty">${esc(tr("d_screen_none"))}</td></tr>`; renderCardBox($("#screen-detail"), null); return; }
  let h = `<thead><tr><th>#</th><th>${esc(tr("ticker"))}</th><th>${esc(tr("d_col_score"))}</th><th>${esc(tr("d_col_card"))}</th>
    <th class="hide-sm">${esc(tr("d_col_reasons"))}</th><th></th></tr></thead><tbody>`;
  for (const r of SC.results) {
    const c = SC.cards[r.ticker], followed = S.watchlist.includes(r.ticker);
    h += `<tr class="row sc-row ${r.ticker === scSelected ? "sel" : ""}" data-sc="${esc(r.ticker)}">
      <td class="num">${r.rank}</td>
      <td class="tk">${esc(r.ticker)}<small>${esc(r.name)} · ${esc(r.industry || "")}</small></td>
      <td class="num"><b>${Math.round(r.score)}</b></td>
      <td>${c && c.score !== null && c.score !== undefined ? `<span class="chip ${cardClass(c.score)}" title="${esc(c.label_text)}">${Math.round(c.score)}</span>` : '<span class="chip none">—</span>'}</td>
      <td class="hide-sm reasons">${(r.reasons || []).map(esc).join("<br>")}</td>
      <td>${followed ? `<span class="note">${esc(tr("d_followed"))}</span>` : `<button class="btn sm" data-follow="${esc(r.ticker)}">${esc(tr("d_follow"))}</button>`}</td></tr>`;
  }
  tbl.innerHTML = h + "</tbody>";
  if (!scSelected) renderCardBox($("#screen-detail"), null);
}

function cardClass(v) { return v === null || v === undefined ? "none" : v >= 62 ? "positive" : v <= 38 ? "negative" : "neutral"; }

function renderCardBox(box, tk, card) {
  if (!tk) { box.innerHTML = `<p class="empty">${esc(tr("d_card_pick"))}</p>`; return; }
  let h = `<h2>${esc(tk)}${card && card.name ? " · " + esc(card.name) : ""}</h2>
    <div class="toolbar" style="margin-top:6px"><button class="btn primary" data-card="${esc(tk)}">${esc(tr(card ? "d_card_refresh" : "d_card_make"))}</button>
    ${card ? "" : `<button class="btn" data-card="${esc(tk)}" data-refresh="1">${esc(tr("d_card_refresh"))}</button>`}</div><div class="card-body">`;
  h += card ? cardHTML(card) : "";
  box.innerHTML = h + "</div>";
  if (card) box.querySelector("[data-card]").dataset.refresh = "1";
}

function cardHTML(c) {
  if (c.error) return `<p class="err">${esc(c.error)}</p>`;
  const ev = c.evidence || [];
  const ref = (n) => ev[n - 1] && /^https?:\/\//.test(ev[n - 1].link || "") ? `<a href="${esc(ev[n - 1].link)}" target="_blank" rel="noopener">[${n}]</a>` : `[${n}]`;
  const ov = c.overall || {};
  let h = `<div class="overall"><b>${ov.score === null || ov.score === undefined ? "—" : Math.round(ov.score)}</b>
    <span class="chip ${cardClass(ov.score)}">${esc(ov.label_text || "")}</span><span class="note">${esc(c.day || "")}</span></div>
    <p class="note">${esc(tr("d_card_total"))}</p><table class="dims">`;
  for (const d of c.dimensions || []) {
    const v = d.validated || {}, counted = v.tested && !v.info_only;
    const mark = v.tested ? (v.useful ? tr("d_val_ok") : tr("d_val_ns")) : tr("d_val_no");
    const col = d.score === null || d.score === undefined ? "var(--muted)" : d.score >= 62 ? "var(--pos)" : d.score <= 38 ? "var(--neg)" : "var(--muted)";
    let extra = "";
    if (d.key === "fundamentals" && d.rank) extra = tr("d_rank_line", {rank: d.rank, of: d.of, score: Math.round(d.score), date: (c.screen || {}).as_of || ""});
    else if (d.key === "report" && d.filed) extra = `${d.filed} · ${tr("e_tone")} ${num(d.tone, 1)}${d.guidance ? " · " + tr("g_" + d.guidance) : ""}`;
    else if (d.key === "quality" && d.reason) extra = d.reason + " " + (d.evidence || []).map(ref).join("");
    else if (d.key === "news" && d.n !== undefined) extra = tr("d_n_headlines", {n: d.n});
    else if (d.key === "policy" && d.sw) extra = tr("d_policy_line", {sw: d.sw, n: d.n}) + ((d.items || []).length ? " · " +
      d.items.slice(0, 3).map((x) => `${x.date} ${x.stance === "restrict" ? "▼" : "▲"}${x.strength} ${x.quote}`).join("；") : "");
    else if (d.key === "filings" && d.n) extra = `${d.n} · ${(d.items || []).slice(0, 3).map((a) => a.category_name || "").filter(Boolean).join("、")}`;
    h += `<tr class="${counted ? "" : "ref"}"><td>${esc(d.name)}<small>${esc(mark)}${counted ? "" : " · " + esc(tr("d_card_ref"))}</small>
      <small title="${esc(v.text || "")}">${esc(v.text || "")}</small></td>
      <td class="sc">${d.score === null || d.score === undefined ? (d.key === "policy" && d.sw ? "i" : "—") : Math.round(d.score)}</td>
      <td><div class="meter"><div style="width:${d.score || 0}%;background:${col}"></div></div><small>${extra.includes("<a") ? extra : esc(extra)}</small></td></tr>`;
  }
  h += "</table>";
  const sy = c.synthesis;
  if (sy) {
    if (sy.summary) h += `<p>${esc(sy.summary)}</p>`;
    const list = (title, pts) => pts && pts.length ? `<b>${esc(title)}</b><ul class="pts">${pts.map((p) => `<li>${esc(p.text)} ${p.evidence.map(ref).join("")}</li>`).join("")}</ul>` : "";
    h += list(tr("d_card_pos"), sy.positives) + list(tr("d_card_risk"), sy.risks);
    if ((sy.watch || []).length) h += `<b>${esc(tr("d_card_watch"))}</b><ul class="pts">${sy.watch.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
  }
  if (ev.length) h += `<details><summary>${esc(tr("d_card_evidence", {n: ev.length}))}</summary><ol class="pts">${ev.map((e) =>
    `<li><span class="note">${esc(e.date || "")} · ${esc(tr("d_kind_" + e.kind))}</span> ${/^https?:\/\//.test(e.link || "") ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}</li>`).join("")}</ol></details>`;
  if ((c.refresh_problems || []).length) h += `<p class="note">${esc(tr("d_card_problems", {p: c.refresh_problems.slice(0, 3).join("; ")}))}</p>`;
  return h + `<p class="note">${esc(c.disclaimer || "")}</p>`;
}

async function askCard(tk, refresh, box) {
  const body = box.querySelector(".card-body") || box;
  box.querySelectorAll("[data-card]").forEach((b) => b.disabled = true);
  body.innerHTML = `<p class="note">${esc(tr(refresh ? "d_card_wait_refresh" : "d_card_wait"))}</p>`;
  let card;
  try { card = await api("/api/scorecard", {ticker: tk, refresh: !!refresh}); }
  catch (e) { card = {error: e.message}; }
  if (box.id === "screen-detail") {
    renderCardBox(box, tk, card.error ? null : card);
    if (card.error) box.querySelector(".card-body").innerHTML = cardHTML(card);
    if (!card.error && SC) { SC.cards[tk] = {score: card.overall.score, label_text: card.overall.label_text}; renderScreen(); }
  } else {
    body.innerHTML = cardHTML(card);
    box.querySelectorAll("[data-card]").forEach((b) => { b.disabled = false; b.dataset.refresh = "1"; b.textContent = tr("d_card_refresh"); });
  }
}

async function follow(tk) {
  const names = S.names || {};
  const current = S.watchlist.map((t) => (names[t] && names[t] !== t ? `${t}=${names[t]}` : t));
  const r = (SC && SC.results || []).find((x) => x.ticker === tk);
  S = await api("/api/watchlist", {tickers: [...current, r && r.name ? `${tk}=${r.name}` : tk]});
  rows = await api(`/api/overview?lang=${S.lang}`); renderOverview(); renderScreen();
}

function rankHTML(d) {
  const r = d.screen;
  let h = `<h3>${esc(tr("d_card"))}</h3>`;
  if (r) h += `<p class="note">${r.covered ? esc(tr("d_rank_line", {rank: r.rank, of: r.of, score: Math.round(r.score), date: r.as_of || ""}))
                                        : esc(tr("d_rank_not", {why: r.why || ""}))}</p>`;
  return h + `<div id="stock-card"><div class="toolbar" style="margin-top:6px"><button class="btn" data-card="${esc(d.ticker)}">${esc(tr("d_card_make"))}</button></div><div class="card-body"></div></div>`;
}

async function loadDigest(day) {
  let dates = [];
  try { dates = await api("/api/digests"); } catch (e) {}
  const sel = $("#digest-date");
  sel.innerHTML = dates.map((d) => `<option ${d === day ? "selected" : ""}>${esc(d)}</option>`).join("");
  sel.hidden = !dates.length;
  const f = $("#digest-frame");
  f.onload = () => { try { f.style.height = (f.contentDocument.documentElement.scrollHeight + 20) + "px"; } catch (e) {} };
  f.src = `/digest?date=${encodeURIComponent(day || dates[0] || "")}&lang=${S.lang}&t=${Date.now()}`;
}

// ---------- home: what you can do, with examples that run ----------
const PRESETS = [
  {key: "beat", spec: {type: "earnings", market: "cn", name: "", filters: [{field: "sue", op: ">=", value: 2}], hold_days: 20, entry_lag: 1}},
  {key: "forecast", spec: {type: "forecast", name: "", filters: [{field: "type", op: "in", value: ["预增", "扭亏"]}, {field: "change_pct", op: ">=", value: 50}], hold_days: 20, entry_lag: 1}},
  {key: "policy", spec: {type: "policy", name: "", filters: [{field: "kind", op: "==", value: "new_measure"}, {field: "strength", op: ">=", value: 4}, {field: "escalation", op: "==", value: true}], hold_days: 20, entry_lag: 1}},
  {key: "factor", spec: {type: "factor", name: "", factors: ["sue", "rev_yoy", "np_yoy", "roe", "mom60"], top: 30}},
];
const EXAMPLE_PF = "600519 100, 300750 200, 00700 300, AAPL 50, 000898 5000";

function toast(msg) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 2200);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const a = document.createElement("textarea"); a.value = text; document.body.appendChild(a); a.select();
              try { document.execCommand("copy"); } catch (err) {} a.remove(); }
  toast(tr("d_home_copied"));
}

function parseHoldings(text) {
  const holdings = [];
  for (const part of text.split(/[,，;\n]+/)) {
    const bits = part.trim().split(/\s+/);
    if (bits.length >= 2 && !isNaN(parseFloat(bits[1]))) holdings.push({ticker: bits[0], shares: parseFloat(bits[1]),
      ...(bits[2] && !isNaN(parseFloat(bits[2])) ? {cost: parseFloat(bits[2])} : {})});
    else if (bits.length === 1 && /^[A-Za-z0-9.^-]{1,12}$/.test(bits[0])) holdings.push({ticker: bits[0], weight: 1});
  }
  return holdings;
}

function homeCards() {
  const first = S.watchlist[0], fname = first ? ((S.names || {})[first] || first) : "";
  const mv = movesList.find((m) => S.watchlist.includes(m.ticker));
  return [
    {icon: "📈", key: "daily", items: [
      first ? {label: tr("d_home_ex_stock", {name: fname}), act: "stock", arg: first, ask: tr("d_home_q_stock", {name: fname})}
            : {label: tr("d_home_ex_add"), act: "stocks", ask: tr("d_home_q_watch")},
      mv ? {label: tr("d_home_ex_why", {name: mv.name || mv.ticker, day: mv.day}), act: "why", arg: mv.ticker, arg2: mv.day,
            ask: tr("d_home_q_why", {name: mv.name || mv.ticker})}
         : {label: tr("d_home_ex_watch"), act: "stocks", ask: tr("d_home_q_watch")},
      {label: tr("d_home_ex_digest"), act: "digest", ask: tr("d_home_q_digest")}]},
    {icon: "🔎", key: "screen", items: [
      {label: tr("d_home_ex_screen"), act: "screen", ask: tr("d_home_q_screen")},
      {label: tr("d_home_ex_card"), act: "card", ask: tr("d_home_q_card")}]},
    {icon: "🧪", key: "lab", items: [
      {label: tr("d_preset_beat"), act: "preset", arg: "beat", ask: tr("d_preset_q_beat")},
      {label: tr("d_preset_policy"), act: "preset", arg: "policy", ask: tr("d_preset_q_policy")},
      {label: tr("d_home_ex_design"), act: "lab", ask: tr("d_home_q_lab")}]},
    {icon: "🩺", key: "pf", items: [
      {label: tr("d_home_ex_pf"), act: "pf", ask: tr("d_home_q_pf")},
      S.watchlist.length >= 2 ? {label: tr("d_home_ex_pfwl", {n: Math.min(S.watchlist.length, 20)}), act: "pfwl", ask: tr("d_home_q_pfwl")} : null]},
  ];
}

function renderHome() {
  $("#home-cards").innerHTML = homeCards().map((c, ci) => `<section class="card"><h2><span class="icon">${c.icon}</span>${esc(tr("d_home_" + c.key))}</h2>
    <p class="lead">${esc(tr("d_home_" + c.key + "_lead"))}</p>` +
    c.items.filter(Boolean).map((x, i) => `<div class="ex"><button class="go" data-home="${ci}-${i}">${esc(x.label)}</button>
</div>`).join("") +
    `<div class="home-out" id="home-out-${ci}"></div></section>`).join("");
}

async function homeAction(ci, i) {
  const x = homeCards()[ci].items.filter(Boolean)[i], out = $("#home-out-" + ci);
  if (x.act === "stocks") return showTab("stocks");
  if (x.act === "digest") return showTab("digest");
  if (x.act === "screen") return showTab("screen");
  if (x.act === "lab") return showTab("lab");
  if (x.act === "stock") { showTab("stocks"); selected = x.arg; renderOverview(); await loadStock(); $("#detail").scrollIntoView({behavior: "smooth", block: "start"}); return; }
  if (x.act === "why") { showTab("stocks"); return askWhy(x.arg, x.arg2); }
  if (x.act === "card") {
    showTab("screen"); await loadScreen();
    const r = (SC.results || [])[0];
    if (!r) return;
    scSelected = r.ticker; renderScreen(); const box = $("#screen-detail"); renderCardBox(box, r.ticker);
    return askCard(r.ticker, false, box);
  }
  if (x.act === "preset") return runSpec(PRESETS.find((p) => p.key === x.arg).spec, out);
  if (x.act === "pf" || x.act === "pfwl") {
    showTab("portfolio"); await loadPortfolioTab();
    $("#pf-input").value = x.act === "pf" ? EXAMPLE_PF : S.watchlist.slice(0, 20).join(", ");
    return runPortfolio();
  }
}

// ---------- the portfolio tab ----------
let pfLoaded = false;
async function loadPortfolioTab() {
  let r = {last: "", reports: []};
  try { r = await api("/api/portfolio/reports"); } catch (e) { /* offline */ }
  if (!pfLoaded && r.last && !$("#pf-input").value.trim()) $("#pf-input").value = r.last;
  pfLoaded = true;
  const when = (id) => id.replace(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2}).*$/, "$1-$2-$3 $4:$5");
  $("#pf-saved").innerHTML = r.reports.length ? r.reports.map((id) =>
    `<div><a href="/portfolio/${encodeURIComponent(id)}" target="_blank" rel="noopener">${esc(when(id))}</a></div>`).join("") : esc(tr("d_pf_none"));
  if (!$("#pf-result").innerHTML) $("#pf-result").innerHTML = `<p class="note">${esc(tr("d_pf_empty"))}</p>`;
}

async function runPortfolio() {
  const text = $("#pf-input").value.trim(), box = $("#pf-result");
  if (!text) { box.innerHTML = `<p class="note">${esc(tr("d_pf_format"))}</p>`; return; }
  const holdings = parseHoldings(text);
  if (!holdings.length) { box.innerHTML = `<p class="note">${esc(tr("d_pf_format"))}</p>`; return; }
  const b = $("#pf-run"); b.disabled = true; box.innerHTML = `<p class="note">${esc(tr("d_pf_wait"))}</p>`;
  try {
    const r = await api("/api/portfolio", {holdings, text});
    if (r.error) box.innerHTML = `<p class="note">${esc(r.error === "demo" ? tr("d_demo_refresh") : r.error)}</p>`;
    else {
      const url = `/portfolio/${encodeURIComponent(r.id)}`;
      box.innerHTML = `<h2>${esc(tr("d_pf_result"))}</h2><ul class="pts">${(r.findings || []).map((f) =>
        `<li>${f.level === "warn" ? "⚠️ " : "✓ "}${esc(f.text)}</li>`).join("")}</ul>` +
        ((r.problems || []).length ? `<p class="note">${esc((r.problems || []).join(" · "))}</p>` : "") +
        `<p><a class="btn primary" href="${url}" target="_blank" rel="noopener">${esc(tr("d_pf_open"))}</a></p>`;
      window.open(url, "_blank"); loadPortfolioTab();
    }
  } catch (e) { box.innerHTML = `<p class="note">${esc(e.message)}</p>`; }
  b.disabled = false;
}

// ---------- the lab tab: templates, a form, results ----------
let CAPS = null, labLast = null;
async function loadLabTab() {
  if (!CAPS) { try { CAPS = await api("/api/lab/caps"); } catch (e) { CAPS = {types: {}}; } }
  const avail = PRESETS.filter((p) => CAPS.types[p.spec.type]);
  $("#lab-templates").innerHTML = avail.map((p) => `<button data-preset="${p.key}">${esc(tr("d_preset_" + p.key))}</button>`).join("")
    || `<span class="note">${esc(tr("d_lab_nodata"))}</span>`;
  const types = Object.keys(CAPS.types), sel = $("#lab-type");
  if (!sel.options.length && types.length) {
    sel.innerHTML = types.map((t) => `<option value="${t}">${esc(tr("d_lab_type_" + t))}</option>`).join("");
    fillForm((avail[0] || {spec: {type: types[0], filters: []}}).spec);
  }
  $("#lab-tries").textContent = tr("d_lab_tries", {n: CAPS.tries_since_reset || 0, date: CAPS.holdout_start || "—"});
  if (!labLast) $("#lab-result").innerHTML = `<p class="empty">${esc(tr("d_lab_pick"))}</p>`;
  loadLab();
}

function fieldLabel(f) { return S.lang === "zh" && CAPS.labels_zh && CAPS.labels_zh[f] ? `${CAPS.labels_zh[f]} (${f})` : f; }
function filterRow(f) {
  const type = $("#lab-type").value, fields = Object.entries((CAPS.types[type] || {}).fields || {});
  const ops = CAPS.ops || [">=", "<=", ">", "<", "==", "in"];
  const v = Array.isArray(f.value) ? f.value.join(", ") : (f.value ?? "");
  return `<div class="frow"><select class="f-field">${fields.map(([k, d]) => `<option value="${k}" title="${esc(d)}" ${k === f.field ? "selected" : ""}>${esc(fieldLabel(k))}</option>`).join("")}</select>
    <select class="f-op">${ops.map((o) => `<option ${o === f.op ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>
    <input class="f-value" value="${esc(v)}" autocomplete="off"><button class="x f-rm" title="×">×</button></div>`;
}
function syncTypeUI() {
  const t = $("#lab-type").value;
  $("#lab-market-wrap").hidden = t !== "earnings";
  $("#lab-factor-wrap").hidden = t !== "factor";
  $("#lab-filters-wrap").hidden = t === "factor";
  $("#lab-hold-wrap").hidden = t === "factor";
  const facs = (CAPS.types.factor || {}).factors || [];
  if (!$("#lab-factors").children.length) $("#lab-factors").innerHTML = facs.map((f) =>
    `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" value="${f}" checked> ${esc(fieldLabel(f))}</label>`).join("");
}
function fillForm(spec) {
  $("#lab-type").value = spec.type; syncTypeUI();
  $("#lab-market").value = spec.market || "cn";
  $("#lab-name").value = spec.name || "";
  $("#lab-filters").innerHTML = (spec.filters || []).map(filterRow).join("");
  $("#lab-hold").value = spec.hold_days || 20; $("#lab-lag").value = spec.entry_lag || 1;
  if (spec.type === "factor") {
    document.querySelectorAll("#lab-factors input").forEach((c) => c.checked = (spec.factors || []).includes(c.value));
    $("#lab-top").value = spec.top || 30;
  }
}
function parseValue(op, raw) {
  const one = (x) => { x = x.trim(); if (x === "true") return true; if (x === "false") return false;
                       return x !== "" && !isNaN(Number(x)) ? Number(x) : x; };
  return ["in", "not_in", "between"].includes(op) ? raw.split(/[,，、]/).map(one).filter((x) => x !== "") : one(raw);
}
function readSpec() {
  const type = $("#lab-type").value, spec = {type, name: $("#lab-name").value.trim()};
  if (type === "earnings") spec.market = $("#lab-market").value;
  if (type === "factor") {
    spec.factors = [...document.querySelectorAll("#lab-factors input:checked")].map((c) => c.value);
    spec.top = Number($("#lab-top").value) || 30;
  } else {
    spec.filters = [...document.querySelectorAll("#lab-filters .frow")].map((r) => {
      const op = r.querySelector(".f-op").value;
      return {field: r.querySelector(".f-field").value, op, value: parseValue(op, r.querySelector(".f-value").value)};
    });
    spec.hold_days = Number($("#lab-hold").value) || 20; spec.entry_lag = Number($("#lab-lag").value) || 1;
  }
  return spec;
}

function labResultHTML(r) {
  if (r.error) return `<p class="err">${esc(r.error === "demo" ? tr("d_demo_refresh") : r.error)}</p>`;
  const v = r.verdict || {}, good = ["passes", "confirmed"].includes(v.code);
  const kpi = (l, x) => `<div class="kv"><b>${esc(l)}</b>${x}</div>`;
  let h = `<h2>${esc(r.spec.name || r.description)}</h2><p class="note">${esc(r.phase === "confirm" ? tr("d_lab_holdout") : tr("d_lab_explore"))} · ${esc(r.period)} · ${esc(r.universe)}</p>
    <div class="histbox" style="border-left-color:${good ? "var(--pos)" : "var(--neg)"}"><p>${esc(v.text || "")}</p></div>
    <div class="grid">${kpi(tr("d_lab_k_ann"), pctChip(r.ann_excess))}${kpi("t", num(r.t, 1, false))}${kpi(tr("d_lab_k_trades"), r.trades)}
    ${kpi(tr("d_lab_k_win"), r.per_trade && r.per_trade.win !== null && r.per_trade.win !== undefined ? Math.round(100 * r.per_trade.win) + "%" : "—")}</div>`;
  if ((r.years || []).length) h += `<p class="note">${r.years.map((y) => `${y.year}: ${y.excess === null ? "—" : (y.excess > 0 ? "+" : "") + (100 * y.excess).toFixed(1) + "%"}`).join(" · ")}</p>`;
  h += `<div class="toolbar"><a class="btn primary" href="${esc(r.report_url)}" target="_blank" rel="noopener">${esc(tr("d_lab_open"))}</a>`;
  if (r.phase === "explore" && v.code === "passes") h += `<button class="btn" data-confirm="${esc(r.id)}">${esc(tr("d_lab_confirm"))}</button>`;
  return h + `</div><p class="note">${esc(r.description)}</p>`;
}

async function runSpec(spec, outBox) {
  const box = outBox || $("#lab-result");
  box.innerHTML = `<p class="note">${esc(tr("d_lab_wait"))}</p>`;
  let r;
  try { r = await api("/api/lab/run", {spec}); } catch (e) { r = {error: e.message}; }
  if (outBox) {
    box.innerHTML = r.error ? `<span class="err">${esc(r.error === "demo" ? tr("d_demo_refresh") : r.error)}</span>`
      : `<a href="${esc(r.report_url)}" target="_blank" rel="noopener">${esc(tr("d_lab_open"))}</a> · ${esc((r.verdict || {}).text || "")}`;
    if (!r.error) window.open(r.report_url, "_blank");
  } else { labLast = r; box.innerHTML = labResultHTML(r); }
  CAPS = null;
  return r;
}

async function loadLab() {
  let list = [];
  try { list = await api("/api/lab"); } catch (e) {}
  const box = $("#lab-list");
  box.hidden = !list.length;
  if (!list.length) return;
  const cls = {passes: "positive", confirmed: "positive", no_edge: "negative", failed: "negative", luck_risk: "negative", negative: "negative"};
  box.innerHTML = `<h2>${esc(tr("d_lab_title"))}</h2>` + list.slice(0, 12).map((x) =>
    `<div class="alert" style="cursor:default"><span class="when">${esc((x.time || "").slice(0, 16).replace("T", " "))}</span>
     <span class="chip ${cls[x.verdict] || "neutral"}">${esc(tr("d_lab_" + x.verdict))}</span>
     <span class="hist"><a href="/lab/${encodeURIComponent(x.id)}" target="_blank" rel="noopener">${esc(x.name || x.description)}</a>
     ${x.t === null || x.t === undefined ? "" : " · t=" + Number(x.t).toFixed(1)}${x.phase === "confirm" ? " · " + esc(tr("d_lab_holdout")) : ""}</span></div>`).join("")
    + `<p class="note">${esc(tr("d_lab_note"))}</p>`;
}

function loadResearch() {
  document.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.market === market));
  const when = (S.research || {})[market];
  $("#research-updated").textContent = when ? tr("d_research_updated", {time: when.replace("T", " ")}) : tr("d_research_never");
  const f = $("#research-frame");
  f.onload = () => { try { f.style.height = (f.contentDocument.documentElement.scrollHeight + 20) + "px"; } catch (e) {} };
  f.src = `/research?market=${market}&lang=${S.lang}&t=${Date.now()}`;
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const before = S.job.done;
    S = await api("/api/state"); renderStatus();
    if (S.job.done !== before) { rows = await api(`/api/overview?lang=${S.lang}`); renderOverview(); }
    if (!S.job.running) { clearInterval(pollTimer); pollTimer = null; await loadAll(); }
  }, 1500);
}

function parseEntries(text) {
  const out = [];
  for (let part of text.split(/[,，;\n]+/)) {
    part = part.trim(); if (!part) continue;
    if (part.includes("=")) out.push(part); else out.push(...part.split(/\s+/));
  }
  return out;
}

async function addTickers() {
  const entries = parseEntries($("#add").value);
  if (!entries.length) return;
  const names = S.names || {};
  const current = S.watchlist.map((t) => (names[t] && names[t] !== t ? `${t}=${names[t]}` : t));
  S = await api("/api/watchlist", {tickers: [...current, ...entries]});
  $("#add").value = ""; await loadAll();
}

document.addEventListener("click", async (e) => {
  const rm = e.target.closest("[data-rm]");
  if (rm) {
    e.stopPropagation();
    const names = S.names || {};
    const keep = S.watchlist.filter((t) => t !== rm.dataset.rm).map((t) => (names[t] && names[t] !== t ? `${t}=${names[t]}` : t));
    await api("/api/watchlist", {tickers: keep}); return loadAll();
  }
  const sortTh = e.target.closest("th.sort");
  if (sortTh) {
    const k = sortTh.dataset.key;
    if (sortKey === k) sortAsc = !sortAsc; else { sortKey = k; sortAsc = k === "ticker"; }
    return renderOverview();
  }
  if (e.target.closest("#compare-btn")) return askCompare(selected);
  const hb = e.target.closest("[data-home]");
  if (hb) { const [ci, i] = hb.dataset.home.split("-").map(Number); hb.disabled = true; await homeAction(ci, i); hb.disabled = false; return; }
  const cp = e.target.closest("[data-ask]");
  if (cp) return copyText(cp.dataset.ask);
  const pr = e.target.closest("[data-preset]");
  if (pr) { fillForm(PRESETS.find((p) => p.key === pr.dataset.preset).spec); return; }
  if (e.target.closest(".f-rm")) { e.target.closest(".frow").remove(); return; }
  const cf = e.target.closest("[data-confirm]");
  if (cf) { cf.disabled = true; $("#lab-result").insertAdjacentHTML("beforeend", `<p class="note">${esc(tr("d_lab_wait"))}</p>`);
            let r; try { r = await api("/api/lab/confirm", {id: cf.dataset.confirm}); } catch (err) { r = {error: err.message}; }
            labLast = r; $("#lab-result").innerHTML = labResultHTML(r); CAPS = null; return loadLabTab(); }
  const fb = e.target.closest("[data-follow]");
  if (fb) { e.stopPropagation(); fb.disabled = true; return follow(fb.dataset.follow); }
  const cb = e.target.closest("[data-card]");
  if (cb) { e.stopPropagation(); return askCard(cb.dataset.card, cb.dataset.refresh === "1", cb.closest("#screen-detail") || cb.closest("#stock-card")); }
  const sr = e.target.closest("tr.sc-row");
  if (sr) {
    scSelected = sr.dataset.sc; renderScreen();
    const box = $("#screen-detail");
    renderCardBox(box, scSelected);
    if ((SC.cards || {})[scSelected]) askCard(scSelected, false, box);     // today's card is cached: instant
    if (window.matchMedia("(max-width: 960px)").matches) box.scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const why = e.target.closest("[data-why]");
  if (why) { e.stopPropagation(); return askWhy(why.dataset.why, why.dataset.day); }
  const at = e.target.closest(".ann .tk");
  if (at) {
    selected = at.dataset.tk; renderOverview(); await loadStock();
    $("#detail").scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const al = e.target.closest(".alert");
  if (al) {
    selected = al.dataset.tk; renderOverview(); await loadStock();
    $("#detail").scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const row = e.target.closest("tr.row");
  if (row) {
    selected = row.dataset.tk; renderOverview(); await loadStock();
    // single-column layout (narrow window or phone): bring the details into view
    if (window.matchMedia("(max-width: 960px)").matches) $("#detail").scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const tb = e.target.closest(".tabs button");
  if (tb) return showTab(tb.dataset.tab);
  const mk = e.target.closest(".seg button");
  if (mk) { market = mk.dataset.market; try { localStorage.setItem("mm_market", market); } catch (err) {} return loadResearch(); }
  const lang = e.target.closest(".langs button");
  if (lang) { await api("/api/settings", {lang: lang.dataset.lang}); return loadAll(); }
});
$("#add-btn").onclick = addTickers;
$("#add").onkeydown = (e) => { if (e.key === "Enter") addTickers(); };
$("#filter").oninput = renderOverview;
$("#digest-date").onchange = (e) => loadDigest(e.target.value);
$("#make-digest").onclick = async () => {
  const b = $("#make-digest"); b.disabled = true; $("#digest-note").textContent = tr("d_digest_wait");
  try { const r = await api("/api/digest", {}); await loadDigest(r.date); $("#digest-note").textContent = r.summary; }
  catch (e) { $("#digest-note").textContent = e.message; }
  b.disabled = false;
};
$("#run-research").onclick = async () => {
  const r = await api("/api/refresh", {kind: "research_" + market});
  if (r.message === "demo") return alert(tr("d_demo_refresh"));
  S = await api("/api/state"); renderStatus(); startPolling();
};
$("#pf-run").onclick = runPortfolio;
$("#pf-example").onclick = () => { $("#pf-input").value = EXAMPLE_PF; };
$("#pf-watch").onclick = () => { $("#pf-input").value = S.watchlist.slice(0, 20).join(", "); };
$("#lab-type").onchange = () => { syncTypeUI(); $("#lab-filters").innerHTML = ""; };
$("#lab-add-filter").onclick = () => {
  const fields = Object.keys((CAPS.types[$("#lab-type").value] || {}).fields || {});
  $("#lab-filters").insertAdjacentHTML("beforeend", filterRow({field: fields[0], op: ">=", value: ""}));
};
$("#lab-run").onclick = async () => { const b = $("#lab-run"); b.disabled = true; await runSpec(readSpec()); b.disabled = false; loadLabTab(); };
$("#lab-reset").onclick = async () => { await api("/api/lab/reset", {}); CAPS = null; toast(tr("d_lab_reset_done")); loadLabTab(); };
$("#run-screen").onclick = async () => {
  const r = await api("/api/refresh", {kind: "screen"});
  if (r.message === "demo") return alert(tr("d_demo_refresh"));
  S = await api("/api/state"); renderStatus(); startPolling();
};
for (const kind of ["news", "earnings"]) {
  $("#refresh-" + kind).onclick = async () => {
    const r = await api("/api/refresh", {kind});
    if (r.message === "empty") return alert(tr("d_empty"));
    if (r.message === "demo") return alert(tr("d_demo_refresh"));
    S = await api("/api/state"); renderStatus(); startPolling();
  };
}
loadAll().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="err">${esc(e.message)}</p>`); });
"""

PAGE = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>stockproof</title><style>" + REPORT_CSS + EARNINGS_CSS + DASH_CSS + "</style></head><body>"
        + BODY + "<script>" + JS + "</script></body></html>")
