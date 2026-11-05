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
.peers { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 10px; } .peer { font-size:13px; white-space:nowrap; }
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
.khit { fill:transparent; cursor:pointer; } .khit:hover { fill:rgba(120,120,128,.14); } .khit.on { fill:rgba(58,91,217,.18); }
.askbar { display:flex; gap:8px; margin:14px 0 0; }
.askbar input { flex:1; min-width:0; font:inherit; font-size:16px; padding:11px 14px; border:1px solid var(--line); border-radius:12px; background:var(--card); color:var(--text); }
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
<form id="ask-form" class="askbar" autocomplete="off"><input id="ask-input" maxlength="500"><button class="btn primary" id="ask-go" type="submit"></button></form>
<div id="ask-out" class="note" style="margin:6px 0 0"></div>
<nav class="tabs"><button data-tab="home" id="tab-home"></button><button data-tab="stocks" id="tab-stocks"></button><button data-tab="digest" id="tab-digest"></button><button data-tab="team" id="tab-team"></button><button data-tab="screen" id="tab-screen"></button><button data-tab="money" id="tab-money"></button><button data-tab="paper" id="tab-paper"></button><button data-tab="lab" id="tab-lab"></button><button data-tab="portfolio" id="tab-portfolio"></button><button data-tab="research" id="tab-research"></button></nav>
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
<div id="view-team" hidden>
<section class="card">
  <h2 id="team-h"></h2>
  <p class="note" id="team-lead"></p>
  <textarea id="team-input" rows="3" style="width:100%;box-sizing:border-box;font:inherit;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text)"></textarea>
  <div class="toolbar" style="margin-top:8px"><button class="btn primary" id="team-go"></button><span id="team-ex"></span></div>
  <div id="team-out"></div>
</section>
<section class="card" style="margin-top:12px"><h2 id="team-hist-h"></h2><div id="team-hist"></div></section>
</div>
<div id="view-paper" hidden>
<section class="card">
  <h2 id="pp-h"></h2>
  <p class="note" id="pp-lead"></p>
  <div class="toolbar"><input id="pp-name" class="btn" style="width:160px"><input id="pp-cash" class="btn" style="width:120px" value="1000000">
    <button class="btn primary" id="pp-new"></button><button class="btn" id="pp-run"></button><span class="note" id="pp-msg"></span></div>
  <div id="pp-accounts"></div>
</section>
<section class="card" style="margin-top:12px" id="pp-detail-card" hidden><div id="pp-detail"></div></section>
<section class="card" style="margin-top:12px"><h2 id="al-h"></h2>
  <div class="toolbar"><button class="btn" id="al-check"></button><span class="note" id="al-meta"></span></div>
  <div id="al-list"></div></section>
</div>
<div id="view-money" hidden>
<div class="toolbar">
  <div class="seg" id="mm-cats"></div>
  <button class="btn" id="mm-download" hidden></button>
  <span class="note" id="mm-meta"></span>
</div>
<div class="cols" style="margin-top:12px">
  <section class="card" id="mm-body"></section>
  <section class="card detail" id="mm-detail"></section>
</div>
<section class="card" id="mm-margin" style="margin-top:12px"></section>
</div>
<div id="view-screen" hidden>
<div class="toolbar">
  <button class="btn primary" id="run-screen"></button>
  <button class="btn" id="run-breakouts"></button>
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
<section class="card" id="breakouts" hidden></section>
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
let T = {}, S = null, rows = [], selected = location.hash.startsWith("#stock=") ? decodeURIComponent(location.hash.slice(7)) : null, sortKey = "mood", sortAsc = false, showLow = false, pollTimer = null;
let tab = location.hash.startsWith("#stock=") ? "stocks" : ["#research", "#digest", "#screen", "#stocks", "#lab", "#portfolio"].includes(location.hash) ? location.hash.slice(1) : "home", market = "us", alerts = [], showAllAlerts = false, cal = {items: []}, anns = [], showAllAnns = false, movesList = [];
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
  $("#tab-money").textContent = tr("d_tab_money");
  $("#ask-input").placeholder = tr("d_ask_placeholder"); $("#ask-go").textContent = tr("d_ask_go");
  $("#tab-paper").textContent = tr("d_tab_paper"); $("#pp-h").textContent = tr("d_pp_h"); $("#pp-lead").textContent = tr("d_pp_lead");
  $("#pp-name").placeholder = tr("d_pp_name"); $("#pp-new").textContent = tr("d_pp_new"); $("#pp-run").textContent = tr("d_pp_run");
  $("#al-h").textContent = tr("d_al_h"); $("#al-check").textContent = tr("d_al_check");
  $("#tab-team").textContent = tr("d_tab_team"); $("#team-h").textContent = tr("d_team_page_h"); $("#team-lead").textContent = tr("d_team_page_lead");
  $("#team-input").placeholder = tr("d_team_placeholder"); $("#team-go").textContent = tr("d_team_go"); $("#team-hist-h").textContent = tr("d_team_hist"); $("#mm-download").textContent = tr("d_mm_download");
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
  $("#run-breakouts").textContent = tr("d_brk_run");
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
      : j.kind === "screen" ? tr("d_tab_screen") : j.kind === "moneymap" ? tr("d_tab_money") : j.kind === "etf" ? tr("d_etf_title")
      : j.kind === "margin" ? tr("d_margin_title") : j.kind.startsWith("forecast") ? tr("d_fc_h") : j.kind === "ntresearch" ? tr("d_nt_h") : j.kind === "moneyhistory" ? tr("d_mm_hist_title") : (j.current || "…");
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
  return `<span class="chip ${c}" ${flag ? `title="${esc(tr("d_unusual"))}"` : ""}>${flag ? "⚡" : ""}${pct1(v)}</span>`;
}

function spark(vals) {
  if (!vals || vals.length < 2) return "";
  const W = 220, H = 44, lo = Math.min(...vals), hi = Math.max(...vals), r = hi - lo || 1;
  const pts = vals.map((v, i) => `${(W * i / (vals.length - 1)).toFixed(1)},${(H - 4 - (H - 8) * (v - lo) / r).toFixed(1)}`).join(" ");
  const col = vals[vals.length - 1] >= vals[0] ? "var(--pos)" : "var(--neg)";
  return `<svg viewBox="0 0 ${W} ${H}" style="width:220px;height:44px"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/></svg>`;
}

// ---------- candlestick chart + technical facts ----------
function candleSVG(c, zh) {
  const n = c.dates.length; if (n < 2) return "";
  const W = 760, PH = 230, VH = 56, PAD = 46, top = 8;
  const hasOHLC = c.high.some((x) => x != null);
  const hi = c.dates.map((_, i) => c.high[i] ?? c.close[i]), lo = c.dates.map((_, i) => c.low[i] ?? c.close[i]);
  let ymax = Math.max(...hi.filter((x) => x != null)), ymin = Math.min(...lo.filter((x) => x != null));
  (c.zones || []).forEach((z) => { if (z.high > ymax && z.low < ymax * 1.08) ymax = z.high; if (z.low < ymin && z.high > ymin * 0.92) ymin = z.low; });
  const pad = (ymax - ymin) * 0.05 || 1; ymax += pad; ymin -= pad;
  const step = (W - PAD) / n, bw = Math.max(1.5, step * 0.62);
  const x = (i) => i * step + step / 2, y = (v) => top + (PH - top) * (ymax - v) / (ymax - ymin);
  const up = zh ? "#d23c3c" : "#1f8a4c", down = zh ? "#1f8a4c" : "#d23c3c";
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = ymin + (ymax - ymin) * k / 4, yy = y(v);
    g += `<line x1="0" x2="${W - PAD}" y1="${yy}" y2="${yy}" stroke="var(--line)" stroke-width="0.6"/><text x="${W - PAD + 4}" y="${yy + 3}" font-size="10" fill="var(--muted)">${v.toFixed(v < 10 ? 2 : 1)}</text>`; }
  const di = Object.fromEntries(c.dates.map((d, i) => [d, i]));
  (c.zones || []).forEach((z) => { if (z.high < ymin || z.low > ymax) return;
    const x0 = z.since && z.since > c.dates[0] ? (di[z.since] != null ? x(di[z.since]) : x(c.dates.findIndex((d) => d >= z.since))) : 0;
    const col = z.kind === "resistance" ? "#d23c3c" : z.kind === "support" ? "#1f8a4c" : "#888";
    g += `<rect x="${Math.max(0, x0)}" width="${Math.max(2, W - PAD - Math.max(0, x0))}" y="${y(Math.min(z.high, ymax))}" height="${Math.max(2, y(Math.max(z.low, ymin)) - y(Math.min(z.high, ymax)))}" fill="${col}" opacity="0.12"><title>${z.low} – ${z.high} · ${z.touches}× · ${esc(tr("ta_since", {d: z.since}))}</title></rect>`; });
  for (let i = 0; i < n; i++) { const cl = c.close[i]; if (cl == null) continue;
    const op = c.open[i] ?? (i ? c.close[i - 1] : cl), col = cl >= op ? up : down;
    if (hasOHLC && c.high[i] != null) {
      g += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(c.high[i])}" y2="${y(c.low[i])}" stroke="${col}" stroke-width="1"/>`;
      const y1 = y(Math.max(op, cl)), h = Math.max(1, y(Math.min(op, cl)) - y1);
      g += `<rect x="${x(i) - bw / 2}" y="${y1}" width="${bw}" height="${h}" fill="${cl >= op ? (zh ? col : "var(--card)") : col}" stroke="${col}" stroke-width="1"><title>${c.dates[i]} O ${op} H ${c.high[i]} L ${c.low[i]} C ${cl}</title></rect>`;
    } }
  if (!hasOHLC) g += `<polyline fill="none" stroke="var(--text)" stroke-width="1.4" points="${c.close.map((v, i) => v == null ? "" : `${x(i)},${y(v)}`).join(" ")}"/>`;
  [["ma5", "#e3a008"], ["ma20", "#3b6fd8"], ["ma60", "#9b59b6"]].forEach(([k, col]) => {
    const pts = c[k].map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(" ");
    if (pts) g += `<polyline fill="none" stroke="${col}" stroke-width="1.1" points="${pts}"/>`; });
  const vmax = Math.max(...c.volume.filter((v) => v != null), 1);
  for (let i = 0; i < n; i++) { const v = c.volume[i]; if (v == null) continue;
    const hgt = (VH - 6) * v / vmax, col = (c.close[i] ?? 0) >= (c.open[i] ?? c.close[i]) ? up : down;
    g += `<rect x="${x(i) - bw / 2}" y="${PH + VH - hgt}" width="${bw}" height="${hgt}" fill="${col}" opacity="0.5"/>`; }
  const idx = Object.fromEntries(c.dates.map((d, i) => [d, i]));
  (c.signals || []).forEach((s) => { const i = idx[s.date]; if (i == null) return;
    const dir = s.direction || (s.bullish ? "bullish" : "bearish"); if (dir === "neutral") return;
    const bull = dir === "bullish", yy = bull ? y(lo[i]) + 12 : y(hi[i]) - 12, col = bull ? up : down;
    g += `<text x="${x(i)}" y="${yy}" font-size="11" text-anchor="middle" fill="${col}">${bull ? "▲" : "▼"}<title>${s.date} ${esc(tr("ta_" + s.kind))}</title></text>`; });
  for (let i = 0; i < n; i++) if (c.close[i] != null) g += `<rect class="khit" data-kday="${c.dates[i]}" x="${x(i) - step / 2}" y="0" width="${step}" height="${PH + VH}"/>`;
  [0, Math.floor(n / 2), n - 1].forEach((i) => { g += `<text x="${Math.min(Math.max(x(i), 30), W - PAD - 30)}" y="${PH + VH + 14}" font-size="10" text-anchor="middle" fill="var(--muted)">${c.dates[i]}</text>`; });
  const legend = `<div class="note" style="display:flex;gap:12px;flex-wrap:wrap"><span style="color:#e3a008">— MA5</span><span style="color:#3b6fd8">— MA20</span><span style="color:#9b59b6">— MA60</span><span><span style="background:#1f8a4c33;padding:0 6px">&nbsp;</span> ${esc(tr("ta_support"))}</span><span><span style="background:#d23c3c33;padding:0 6px">&nbsp;</span> ${esc(tr("ta_resistance"))}</span><span>▲▼ ${esc(tr("ta_signals"))}</span></div>`;
  return `<svg class="kchart" viewBox="0 0 ${W} ${PH + VH + 18}" style="width:100%;height:auto;display:block">${g}</svg>${legend}<p class="note">${esc(tr("d_day_hint"))}</p><div id="day-box"></div>`;
}

function techHTML(t) {
  if (!t) return "";
  const zh = S.lang === "zh", tr_ = t.trend || {};
  const zl = (z) => z ? `${z.low.toFixed(2)} – ${z.high.toFixed(2)}（${esc(tr("ta_touches", {n: z.touches}))}，${pct(z.distance)}）` : "—";
  let h = `<h3>${esc(tr("ta_title"))}</h3>${candleSVG(t.chart, zh)}`;
  if (!t.has_ohlc) h += `<p class="note">${esc(tr("ta_no_ohlc"))}</p>`;
  h += `<table class="hist"><tbody>
    <tr><td>${esc(tr("ta_trend"))}</td><td>${esc(tr("ta_trend_" + (tr_.state || "mixed")))}${tr_.rsi != null ? ` · RSI ${tr_.rsi.toFixed(0)}` : ""}${t.from_high_52w != null ? ` · ${esc(tr("ta_from_high", {x: pct(t.from_high_52w)}))}` : ""}</td></tr>
    <tr><td>${esc(tr("ta_support"))}</td><td>${zl(t.nearest_support)}</td></tr>
    <tr><td>${esc(tr("ta_resistance"))}</td><td>${zl(t.nearest_resistance)}</td></tr></tbody></table>`;
  if ((t.signals || []).length) h += `<ul class="pts">${t.signals.map((s) => `<li>${s.direction === "neutral" ? "●" : s.bullish ? "▲" : "▼"} <b>${esc(s.date)}</b> ${esc(tr("ta_" + s.kind))} <span class="note">— ${esc(s.rule)}</span></li>`).join("")}</ul>`;
  else h += `<p class="note">${esc(tr("ta_no_signals"))}</p>`;
  return h + `<p class="note">${esc(t.note)}</p>`;
}

function priceHTML(d) {
  const q = d.price;
  if (!q) return "";
  let h = `<div class="price"><div><b class="close">${q.close.toFixed(2)}</b> <span class="note">${esc(q.date)}</span></div>
    <div class="rets"><span>${esc(tr("d_today"))} ${pctChip(q.d1)}</span><span class="note">${esc(tr("d_vs_market", {x: pct(q.d1_excess)}))}</span>
    <span>${esc(tr("d_1w"))} ${pctChip(q.w1)}</span><span>${esc(tr("d_1m"))} ${pctChip(q.m1)}</span><span>${esc(tr("d_ytd"))} ${pctChip(q.ytd)}</span></div>
    ${spark(q.spark)}</div>`;
  if (!q.move) h += `<div class="move"><span class="note">${esc(tr("why_any_day", {day: q.date}))}</span>
      <button class="btn" data-why="${esc(d.ticker)}" data-day="${esc(q.date)}">${esc(tr("d_why"))}</button>
      <button class="btn primary" data-team="${esc(d.ticker)}">${esc(tr("d_team"))}</button></div><div id="why-box"></div><div id="team-box"></div>`;
  if (q.move) {
    h += `<div class="move"><span>⚡ ${esc(tr("d_move_line", {day: q.move.date, ret: pct(q.move.ret), excess: pct(q.move.excess)}))}</span>
      <button class="btn" data-why="${esc(d.ticker)}" data-day="${esc(q.move.date)}">${esc(tr("d_why"))}</button>
      <button class="btn primary" data-team="${esc(d.ticker)}">${esc(tr("d_team"))}</button></div><div id="why-box"></div><div id="team-box"></div>`;
  }
  return h;
}

function whyHTML(x) {
  if (x.error) return `<p class="note">${esc(tr("d_why_error", {error: x.error}))}</p>`;
  const ev = x.evidence || [];
  const cite = (t) => esc(t).replace(/\[(\d+)\]/g, (m, n) => ev[n - 1] && ev[n - 1].link ? `<a href="${esc(ev[n - 1].link)}" target="_blank" rel="noopener">[${n}]</a>` : m);
  let h = `<div class="histbox">`;
  const a = x.attribution;
  if (a) {
    const row = (label, v, extra) => `<tr><td>${esc(label)}</td><td style="text-align:right">${pctChip(v)}</td><td class="note">${esc(extra || "")}</td></tr>`;
    h += `<table class="hist"><tbody>${row(tr("why_total"), a.ret, "")}${row(tr("why_market"), a.market_part, tr("why_market_note", {r: pct1(a.market_ret), b: a.beta_market}))}` +
      (a.industry_part != null ? row(tr("why_industry"), a.industry_part, tr("why_industry_note", {n: a.industry, r: pct1(a.industry_ret)})) : "") +
      row(tr("why_own"), a.own_part, a.own_z != null ? tr("why_own_note", {z: Math.abs(a.own_z).toFixed(1)}) : "") + `</tbody></table>`;
  }
  const pe = x.peers;
  if (pe && (pe.peers || []).length) {
    h += `<p class="note" style="margin:10px 0 4px">${esc(tr("why_peers", {n: pe.industry, m: pct(pe.median), up: pe.up, down: pe.down, k: pe.n}))}${pe.rank ? " · " + esc(tr("why_peers_rank", {r: pe.rank, k: pe.n + 1})) : ""}</p>` +
      `<div class="peers">${pe.peers.map((p) => `<span class="peer" data-tk="${esc(p.ticker)}">${esc(p.name || p.ticker)} ${pctChip(p.ret)}</span>`).join("")}</div>`;
  }
  h += `<p>${cite(x.summary || "")}</p>`;
  if ((x.causes || []).length) h += `<ul class="pts">${x.causes.map((c) => `<li>${cite(c.text)} ${c.evidence.map((n) => ev[n - 1] && ev[n - 1].link ? `<a href="${esc(ev[n - 1].link)}" target="_blank" rel="noopener">[${n}]</a>` : `[${n}]`).join(" ")}</li>`).join("")}</ul>`;
  h += `<p class="note">${esc(tr("d_why_conf", {c: tr("d_conf_" + (x.confidence || "low"))}))}${x.explained ? "" : " · " + esc(tr("d_why_unexplained"))}</p>`;
  if (ev.length) h += `<details><summary>${esc(tr("d_why_evidence", {n: ev.length}))}</summary><ol class="pts">${ev.map((e) =>
    `<li><span class="note">${esc(e.date)} · ${esc(tr("d_kind_" + e.kind))}${e.timing && e.timing.startsWith("background") ? " · " + esc(tr("why_background")) : ""}${e.source ? " · " + esc(e.source) : ""}</span> ${e.link ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}</li>`).join("")}</ol></details>`;
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

const STANCE_CLS = {bullish: "positive", bearish: "negative", neutral: "neutral", no_view: "neutral"};
function teamHTML(x) {
  if (x.error) return `<p class="err">${esc(x.error === "demo" ? tr("d_demo_refresh") : x.error)}</p>`;
  const R = x.roles || {}, ev = x.evidence || {}, f = x.final || {};
  const cite = (refs) => (refs || []).map((r) => ev[r] && ev[r].link ? `<a href="${esc(ev[r].link)}" target="_blank" rel="noopener">[${esc(r)}]</a>` : `<span class="note" title="${esc(ev[r] ? ev[r].title + " — " + ev[r].text : "")}">[${esc(r)}]</span>`).join("");
  const pts = (list) => (list || []).length ? `<ul class="pts">${list.map((p) => `<li>${esc(p.text)} ${cite(p.evidence)}</li>`).join("")}</ul>` : "";
  let h = `<div class="histbox"><h3>${esc(tr("d_team_title"))} · ${esc(x.day || "")}${x.cached ? " · " + esc(tr("d_team_cached")) : ""}</h3>
    <p><span class="chip ${STANCE_CLS[f.stance] || "neutral"}">${esc(tr("d_stance_" + f.stance))}</span>
    <span class="chip neutral">${esc(tr("d_conf_" + f.confidence))}</span>
    <span class="note">${esc(tr("d_team_horizon", {n: f.horizon_days}))}${x.price != null ? " · " + esc(tr("d_team_price", {p: x.price, d: x.price_date})) : ""}</span></p>
    <p>${esc(f.summary || "")}</p>${pts(f.reasons)}`;
  if (f.cap_note) h += `<p class="note" style="color:var(--neg)">⚠ ${esc(f.cap_note)}</p>`;
  if ((f.plan || []).length) h += `<h3>${esc(tr("d_team_plan"))}</h3><ul class="pts">${f.plan.map((p) => `<li>${esc(p.if)}${p.level != null ? ` <b>(${esc(p.level)})</b>` : ""} → ${esc(p.then)}</li>`).join("")}</ul>`;
  if ((f.risks || []).length) h += `<h3>${esc(tr("d_team_risks"))}</h3>${pts(f.risks)}`;
  if ((f.would_change_view || []).length) h += `<p class="note">${esc(tr("d_team_change"))}：${esc(f.would_change_view.join("；"))}</p>`;
  h += `<details><summary>${esc(tr("d_team_details"))}</summary>`;
  for (const [k, a] of Object.entries(x.analysts || {})) {
    h += `<p><b>${esc(R[k] || k)}</b> <span class="chip ${STANCE_CLS[a.view] || "neutral"}">${esc(tr("d_stance_" + a.view))}</span></p>${pts(a.points)}`;
    const v = (x.validated || {})[k] || [];
    if (v.length) h += `<p class="note">${esc(v.map((y) => (y.dim ? y.dim + ": " : "") + (y.text || "")).join(" · "))}</p>`;
  }
  h += `<p><b>${esc(R.bull || "bull")}</b></p>${pts((x.bull || {}).case)}<p class="note">${esc((x.bull || {}).other_side_weakest || "")}</p>`;
  h += `<p><b>${esc(R.bear || "bear")}</b></p>${pts((x.bear || {}).case)}<p class="note">${esc((x.bear || {}).other_side_weakest || "")}</p></details>`;
  const tr_ = (x.track_record || {}).summary;
  if (tr_) h += `<p class="note">${esc(tr("d_team_record", {n: tr_.calls, s: tr_.scored, h: tr_.hit_rate != null ? Math.round(100 * tr_.hit_rate) + "%" : "—"}))} ${esc(tr_.note || "")}
    <button class="btn sm" data-record="1">${esc(tr("d_rec_show"))}</button></p><div id="record-box"></div>`;
  if (x.call_id) h += `<p>${["bullish", "bearish"].includes(f.stance) ? `<button class="btn sm" data-paperteam="${esc(x.call_id)}">${esc(tr("d_pp_from_team"))}</button> ` : ""}<button class="btn sm" data-share="team|${esc(x.call_id)}">${esc(tr("d_card_make"))}</button></p>`;
  return h + `<p class="note">${esc(x.disclaimer || "")}</p></div>`;
}

function teamExamples() {
  const first = S.watchlist[0], fname = first ? ((S.names || {})[first] || first) : "科大讯飞";
  return [tr("d_team_ex1", {name: fname}), tr("d_team_ex2"), tr("d_team_ex3")];
}

async function loadTeamTab() {
  $("#team-ex").innerHTML = teamExamples().map((q, i) => `<button class="btn sm" data-teamex="${i}">${esc(q)}</button>`).join(" ");
  let r; try { r = await api(`/api/team/record?lang=${S.lang}`); } catch (e) { r = null; }
  const rows = (r && r.recent) || [];
  $("#team-hist").innerHTML = (rows.length ? `<table><tbody>` + rows.map((c) => `<tr class="team-row" data-callid="${esc(c.id)}" style="cursor:pointer">
      <td class="num">${esc(c.day)}</td><td class="tk">${esc(c.ticker)}<small>${esc(c.name || "")}</small></td>
      <td class="note">${esc(c.question || tr("d_team_noq"))}</td>
      <td><span class="chip ${STANCE_CLS[c.stance] || "neutral"}">${esc(tr("d_stance_" + c.stance))}</span></td>
      <td>${c.excess == null ? `<span class="note">${esc(c.counted ? tr("d_rec_pending") : tr("d_rec_notcounted"))}</span>` : `${pctChip(c.excess)} ${c.hit ? "✓" : "✗"}`}</td></tr>`).join("") + `</tbody></table>`
    : `<p class="empty">${esc(tr("d_team_none"))}</p>`) + (r ? recordHTML({summary: r.summary, recent: []}) : "");
}

async function runTeamText(text) {
  const out = $("#team-out"), btn = $("#team-go");
  if (!text.trim()) return;
  btn.disabled = true;
  out.innerHTML = `<p class="note">${esc(tr("d_team_wait"))}</p>`;
  let r; try { r = await api("/api/team", {text}); } catch (e) { r = {error: e.message}; }
  btn.disabled = false;
  out.innerHTML = (r.question ? `<p class="note">${esc(tr("d_team_q"))}：${esc(r.question)}</p>` : "") + teamHTML(r);
  const det = out.querySelector("details"); if (det) det.open = true;
  loadTeamTab();
}

async function askTeam(tk) {
  const box = $("#team-box");
  if (!box) return;
  box.innerHTML = `<p class="note">${esc(tr("d_team_wait"))}</p>`;
  try { box.innerHTML = teamHTML(await api("/api/team", {ticker: tk})); }
  catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
}

// ---------- paper trading + alerts ----------
let PP = null, ppSel = null;
const money = (v) => v == null ? "—" : Math.round(v).toLocaleString();
function navSVG(nav) {
  if (!nav || nav.length < 2) return "";
  const W = 640, H = 160, xs = (i) => 30 + i * (W - 40) / (nav.length - 1);
  const vals = nav.flatMap((r) => [r[1], r[2]]).filter((v) => v != null), lo = Math.min(...vals), hi = Math.max(...vals), sp = (hi - lo) || 0.01;
  const ys = (v) => 10 + (H - 30) * (1 - (v - lo) / sp);
  const line = (k, col) => `<polyline fill="none" stroke="${col}" stroke-width="2" points="${nav.filter((r) => r[k] != null).map((r) => xs(nav.indexOf(r)) + "," + ys(r[k])).join(" ")}"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">${line(2, "var(--muted, #999)")}${line(1, "var(--accent)")}
    <text x="30" y="${H - 4}" font-size="11" fill="currentColor">${esc(nav[0][0])}</text><text x="${W - 80}" y="${H - 4}" font-size="11" fill="currentColor">${esc(nav[nav.length - 1][0])}</text></svg>
    <p class="note"><span style="color:var(--accent)">━</span> ${esc(tr("d_pp_nav"))} · <span style="color:#999">━</span> ${esc(tr("d_pp_bench"))}</p>`;
}
async function loadPaper(id) {
  if (id !== undefined) ppSel = id;
  try { PP = await api("/api/paper" + (ppSel ? "?id=" + encodeURIComponent(ppSel) : "")); } catch (e) { PP = {accounts: []}; }
  const A = PP.accounts || [];
  $("#pp-accounts").innerHTML = A.length ? `<table><thead><tr><th>${esc(tr("d_pp_acct"))}</th><th>${esc(tr("d_pp_value"))}</th><th>${esc(tr("d_pp_ret"))}</th><th>${esc(tr("d_pp_bench"))}</th><th>${esc(tr("d_pp_excess"))}</th><th>${esc(tr("d_pp_dd"))}</th><th></th></tr></thead><tbody>` +
    A.map((a) => `<tr class="pp-row" data-pp="${esc(a.id)}" style="cursor:pointer"><td class="tk">${esc(a.name)}<small>${esc(a.kind === "strategy" ? tr("d_pp_strategy") : tr("d_pp_manual"))} · ${esc(tr("d_pp_since", {d: a.start_day}))}</small></td>
      <td class="num">${money(a.value)}</td><td>${pctChip(a["return"])}</td><td>${a.benchmark_return == null ? "—" : pctChip(a.benchmark_return)}</td>
      <td>${a.excess == null ? "—" : pctChip(a.excess)}</td><td class="num">${pct1(a.max_drawdown)}</td><td class="note">${a.pending ? esc(tr("d_pp_pending", {n: a.pending})) : ""}</td></tr>`).join("") + `</tbody></table>`
    : `<p class="empty">${esc(tr("d_pp_none"))}</p>`;
  const card = $("#pp-detail-card"), d = PP.detail;
  card.hidden = !d;
  if (!d) return;
  const ac = d.account;
  let h = `<h2>${esc(ac.name)} <small class="note">${esc(ac.id)} · ${esc(d.as_of)}</small></h2>${ac.note ? `<p class="note">${esc(ac.note)}</p>` : ""}
    <div class="grid"><div class="kv"><b>${esc(tr("d_pp_value"))}</b>${money(d.value)}</div><div class="kv"><b>${esc(tr("d_pp_cash"))}</b>${money(d.cash)}</div>
    <div class="kv"><b>${esc(tr("d_pp_ret"))}</b>${pctChip(d["return"])}</div><div class="kv"><b>${esc(tr("d_pp_excess"))}</b>${d.excess == null ? "—" : pctChip(d.excess)}</div>
    <div class="kv"><b>${esc(tr("d_pp_costs"))}</b>${money(d.costs_paid)}</div></div>${navSVG(d.nav)}`;
  h += `<div class="toolbar"><input id="pp-tk" class="btn" style="width:120px" placeholder="${esc(tr("d_pp_tk"))}"><input id="pp-val" class="btn" style="width:110px" placeholder="${esc(tr("d_pp_val"))}">
    <input id="pp-sh" class="btn" style="width:90px" placeholder="${esc(tr("d_pp_sh"))}"><button class="btn primary" data-ppo="buy">${esc(tr("d_pp_buy"))}</button><button class="btn" data-ppo="sell">${esc(tr("d_pp_sell"))}</button></div>`;
  if ((d.holdings || []).length) h += `<h3>${esc(tr("d_pp_hold"))}</h3><table><tbody>${d.holdings.map((x) => `<tr><td class="tk">${esc(x.ticker)}</td><td class="num">${x.shares}</td><td class="num">${esc(x.price)}</td><td class="num">${money(x.value)}</td></tr>`).join("")}</tbody></table>`;
  const O = (d.orders || []).slice().reverse();
  if (O.length) h += `<h3>${esc(tr("d_pp_orders"))}</h3><table><tbody>${O.map((o) => `<tr><td class="num">${esc(o.created_day)}</td><td>${esc(o.side === "buy" ? tr("d_pp_buy") : tr("d_pp_sell"))}</td><td class="tk">${esc(o.ticker)}</td>
      <td>${o.status ? esc(o.status === "filled" ? tr("d_pp_filled", {d: o.fill_day, n: o.filled, p: o.price}) : tr("d_pp_cancelled")) : `<span class="note">${esc(tr("d_pp_wait"))}</span>`}</td><td class="note">${esc(o.reason || "")} ${esc(o.source && o.source !== "manual" ? o.source : "")}</td></tr>`).join("")}</tbody></table>`;
  const g = PP.gap;
  if (g) h += `<div class="histbox"><h3>${esc(tr("d_pp_gap_h"))}</h3><p>${esc(tr("d_pp_gap", {n: g.round_trips, m: g.missed_entries}))}${g.avg_gap != null ? " · " + esc(tr("d_pp_gap_v", {a: pct1(g.avg_backtest_rule), b: pct1(g.avg_paper), c: pct1(g.avg_gap)})) : ""}</p>
    ${g.lab_backtest_ann_excess != null ? `<p class="note">${esc(tr("d_pp_gap_lab", {a: pct1(g.lab_backtest_ann_excess)}))}</p>` : ""}<p class="note">${esc(g.note)}</p></div>`;
  $("#pp-detail").innerHTML = h + `<p class="note">${esc(d.rules)}</p><p><button class="btn sm" data-share="paper|${esc(ac.id)}">${esc(tr("d_card_make"))}</button></p>`;
}
async function ppAct(body) {
  const msg = $("#pp-msg");
  let r; try { r = await api("/api/paper", body); } catch (e) { r = {error: e.message}; }
  msg.textContent = r.error ? r.error : (body.action === "run" ? tr("d_pp_ran", {f: r.processed.filled, c: r.processed.cancelled, w: r.processed.waiting}) : tr("d_pp_ok"));
  if (r.id && ["new", "strategy"].includes(body.action)) ppSel = r.id;
  return r;
}
async function loadPxAlerts(check) {
  let r; try { r = check ? await api("/api/pxalerts", {}) : await api("/api/pxalerts"); } catch (e) { r = {recent: [], error: e.message}; }
  $("#al-meta").textContent = r.error ? r.error : (check ? tr("d_al_meta", {n: (r.new || []).length, w: (r.watching || []).length}) + " " + (r.note || "") : tr("d_al_cli"));
  const R = r.recent || [];
  $("#al-list").innerHTML = R.length ? `<ul class="pts">${R.map((a) => `<li><span class="note">${esc(a.created_at.slice(5, 16).replace("T", " "))}</span> ${esc(a.text)}</li>`).join("")}</ul>` : `<p class="empty">${esc(tr("d_al_none"))}</p>`;
}
$("#pp-new").onclick = async () => { await ppAct({action: "new", name: $("#pp-name").value, cash: Number($("#pp-cash").value) || 1000000}); loadPaper(); };
$("#pp-run").onclick = async () => { $("#pp-msg").textContent = tr("d_pp_running"); await ppAct({action: "run"}); loadPaper(); };
$("#al-check").onclick = () => { $("#al-meta").textContent = "…"; loadPxAlerts(true); };
document.addEventListener("click", async (e) => {
  const row = e.target.closest("tr.pp-row");
  if (row) return loadPaper(row.dataset.pp);
  const o = e.target.closest("[data-ppo]");
  if (o && ppSel) { await ppAct({action: o.dataset.ppo, account: ppSel, ticker: $("#pp-tk").value, value: Number($("#pp-val").value) || 0, shares: Number($("#pp-sh").value) || 0}); return loadPaper(); }
  const pe = e.target.closest("[data-paperexp]");
  if (pe) { const r = await ppAct({action: "strategy", exp_id: pe.dataset.paperexp}); if (r.error) { pe.insertAdjacentHTML("afterend", ` <span class="err">${esc(r.error)}</span>`); return; } showTab("paper"); return; }
  const pt = e.target.closest("[data-paperteam]");
  if (pt) {
    let A = []; try { A = (await api("/api/paper")).accounts.filter((a) => a.kind === "manual"); } catch (err) {}
    let aid = A.length ? A[A.length - 1].id : (await ppAct({action: "new", name: tr("d_pp_team_acct")})).id;
    const r = await ppAct({action: "from_team", account: aid, call_id: pt.dataset.paperteam, value: 100000});
    pt.insertAdjacentHTML("afterend", ` <span class="note">${esc(r.error || tr("d_pp_team_ok", {a: (A.length ? A[A.length - 1].name : tr("d_pp_team_acct"))}))}</span>`);
    return;
  }
});

// ---------- one-sentence entry ----------
async function askOne(text) {
  text = (text || "").trim();
  if (!text) return;
  const out = $("#ask-out");
  out.textContent = "…";
  let r; try { r = await api("/api/ask", {text}); } catch (e) { out.textContent = e.message; return; }
  const how = {rules: tr("d_ask_rules"), llm: tr("d_ask_llm"), default: tr("d_ask_default")}[r.how] || "";
  out.innerHTML = `→ ${esc(tr("d_ask_as"))}<b>${esc(S.lang === "zh" ? r.label : r.label_en)}</b>${r.ticker ? " · " + esc(r.ticker) : ""} <span class="note">(${esc(how)})</span>` +
    (r.argv ? ` · <code>stockproof ${esc(r.argv.map((a) => /^[\w.\-]+$/.test(a) ? a : '"' + a + '"').join(" "))}</code>` : "");
  const tk = r.ticker, a = r.args || {};
  const follow = async () => { if (tk && !S.watchlist.includes(tk)) S = await api("/api/watchlist", {tickers: [...S.watchlist, tk]}); };
  const map = {
    forecast: {act: "stock", arg: tk}, team: {act: "teamtext", arg: text}, team_record: {act: "teamtab"}, day: {act: "day", arg: tk, date: a.date},
    why: {act: "why", arg: tk}, technical: {act: "stock", arg: tk}, compare: {act: "stock", arg: tk}, scorecard: {act: "stock", arg: tk},
    nt_research: {act: "ntsec"}, smart_money: {act: "holders", arg: tk}, moneymap: {act: "money", arg: a.category || "national"},
    etf: {act: "money", arg: "national"}, margin: {act: "margin"}, breakouts: {act: "breakouts"},
    calendar: {act: "stocks"}, digest: {act: "digest"}, screen: {act: "screen"}, lab: {act: "lab"},
    portfolio: (a.holdings || []).length ? {act: "pftext", arg: a.holdings.map((h) => h.ticker + " " + h.shares).join(", ")} : {act: "pftab"},
    paper: {act: "paper"}, alerts: {act: "alerts"},
    paper_order: {act: "paperorder", arg: tk, side: a.side, value: a.value, shares: a.shares}, menu: {act: "home"},
  };
  const x = map[r.intent] || {act: "home"};
  if (["why", "stock"].includes(x.act)) await follow();
  if (x.act === "home") return showTab("home");
  if (x.act === "stocks") return showTab("stocks");
  if (x.act === "ntsec") { showTab("money"); setTimeout(() => { const b = $("#nt-sec"); if (b) b.scrollIntoView({behavior: "smooth"}); }, 1500); return; }
  if (x.act === "pftab") { showTab("portfolio"); return loadPortfolioTab(); }
  if (x.act === "day") { await follow(); showTab("stocks"); selected = tk; renderOverview(); await loadStock(); setTimeout(() => { showDay(tk, x.date); const b = $("#day-box"); if (b) b.scrollIntoView({behavior: "smooth", block: "center"}); }, 300); return; }
  return doAct(x, out);
}
$("#ask-form").onsubmit = (e) => { e.preventDefault(); askOne($("#ask-input").value); };

// ---------- shareable cards ----------
async function shareCard(kind, id, btn) {
  const url = `/card/${kind}/${encodeURIComponent(id)}.svg?lang=${S.lang}`;
  const box = document.createElement("div");
  box.className = "histbox"; box.style.marginTop = "8px";
  box.innerHTML = `<img src="${url}" style="width:100%;max-width:720px;border:1px solid var(--line);border-radius:10px;background:#fff" alt="">
    <div class="toolbar"><button class="btn primary" data-pngdl="${esc(url)}" data-name="stockproof-${esc(kind)}-${esc(id)}.png">${esc(tr("d_card_png"))}</button>
    <a class="btn" href="${url}" target="_blank" rel="noopener">${esc(tr("d_card_open"))}</a></div><p class="note">${esc(tr("d_card_note"))}</p>`;
  btn.insertAdjacentElement("afterend", box); btn.disabled = true;
}
async function svgToPng(url, name) {
  const svg = await (await fetch(url)).text();
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  await img.decode();
  const c = document.createElement("canvas"); c.width = 2400; c.height = 1350;
  c.getContext("2d").drawImage(img, 0, 0, 2400, 1350);
  c.toBlob((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); }, "image/png");
}
document.addEventListener("click", (e) => {
  const sc = e.target.closest("[data-share]");
  if (sc) { const [k, id] = sc.dataset.share.split("|"); return shareCard(k, id, sc); }
  const dl = e.target.closest("[data-pngdl]");
  if (dl) return svgToPng(dl.dataset.pngdl, dl.dataset.name);
});

// ---------- click a candle: that day ----------
let dayTk = null, dayDate = null;
async function showDay(tk, date) {
  const box = $("#day-box"); if (!box) return;
  dayTk = tk; dayDate = date;
  document.querySelectorAll(".khit.on").forEach((r) => r.classList.remove("on"));
  const hit = document.querySelector(`.khit[data-kday="${date}"]`); if (hit) hit.classList.add("on");
  box.innerHTML = `<p class="note">…</p>`;
  let r; try { r = await api(`/api/day?ticker=${encodeURIComponent(tk)}&date=${date}&lang=${S.lang}`); } catch (e) { r = {error: e.message}; }
  if (dayDate !== date) return;
  if (r.error) { box.innerHTML = `<p class="err">${esc(r.error)}</p>`; return; }
  const num = (v) => v == null ? "—" : Number(v).toFixed(v < 1 ? 3 : 2);
  let h = `<div class="histbox"><h3>${esc(r.date)} <span class="note">${esc(tr("d_day_keys"))}</span></h3>
    <div class="grid"><div class="kv"><b>${esc(tr("d_day_ohlc"))}</b>${num(r.open)} / ${num(r.high)} / ${num(r.low)} / ${num(r.close)}</div>
    <div class="kv"><b>${esc(tr("d_today"))}</b>${r.ret == null ? "—" : pctChip(r.ret)}</div>
    <div class="kv"><b>${esc(tr("d_day_excess"))}</b>${r.excess == null ? "—" : pctChip(r.excess)}</div>
    <div class="kv"><b>${esc(tr("d_day_vol"))}</b>${r.vol_ratio == null ? "—" : r.vol_ratio + "×"}</div></div>
    <ul class="pts">${(r.facts || []).map((f) => `<li>${esc(f)}</li>`).join("")}${(r.signals || []).map((s) => `<li>${s.bullish ? "▲" : "▼"} ${esc(tr("ta_" + s.kind))} <span class="note">— ${esc(s.rule)}</span></li>`).join("")}</ul>`;
  const ev = r.evidence || [];
  h += ev.length ? `<h3>${esc(tr("d_day_ev"))}</h3><ul class="pts">${ev.map((e) => `<li><span class="note">${esc(e.date)} · ${esc(tr("d_day_k_" + e.kind) || e.kind)}</span> ${e.link ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}${e.note ? ` <span class="note">— ${esc(e.note)}</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="note">${esc(tr("d_day_noev"))}</p>`;
  (r.team_calls || []).forEach((c) => { h += `<p class="note">🧠 ${esc(tr("d_day_team", {s: tr("d_stance_" + c.stance), id: c.id}))}</p>`; });
  (r.paper_fills || []).forEach((f) => { h += `<p class="note">📒 ${esc(tr("d_day_fill", {a: f.account, side: f.side === "buy" ? tr("d_pp_buy") : tr("d_pp_sell"), n: f.shares, p: f.price}))}</p>`; });
  const af = Object.entries(r.after || {});
  if (af.length) h += `<p>${esc(tr("d_day_after"))} ${af.map(([n, v]) => `${esc(tr("d_day_nd", {n}))} ${pctChip(v)}`).join(" · ")}</p><p class="note">${esc(r.after_note)}</p>`;
  h += `<div class="toolbar"><button class="btn" data-why="${esc(tk)}" data-day="${esc(r.date)}">${esc(tr("d_why"))}</button></div></div>`;
  box.innerHTML = h;
}
document.addEventListener("click", (e) => {
  const k = e.target.closest(".khit");
  if (k && selected) showDay(selected, k.dataset.kday);
});
document.addEventListener("keydown", (e) => {
  if (!dayDate || !["ArrowLeft", "ArrowRight"].includes(e.key) || /INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
  const all = [...document.querySelectorAll(".khit")].map((r) => r.dataset.kday), i = all.indexOf(dayDate);
  const j = i + (e.key === "ArrowLeft" ? -1 : 1);
  if (i >= 0 && j >= 0 && j < all.length) { e.preventDefault(); showDay(dayTk, all[j]); }
});

// ---------- 3/6/12-month forecast on the stock page ----------
async function loadForecast(tk) {
  const box = $("#fc-box"); if (!box) return;
  let r; try { r = await api(`/api/forecast?ticker=${encodeURIComponent(tk)}&lang=${S.lang}`); } catch (e) { box.innerHTML = ""; return; }
  if (selected !== tk) return;
  const job = (kind) => `<button class="btn sm" data-fcjob="${kind}">${esc(tr(kind === "forecast" ? "d_fc_run" : "d_fc_dl"))}</button>`;
  if (r.need_run) { box.innerHTML = `<h3>${esc(tr("d_fc_h"))}</h3><p class="note">${esc(tr("d_fc_need"))}</p><p>${job("forecast")} ${job("forecast_download")}</p>`; return; }
  const v = r.stock;
  let h = `<h3>${esc(tr("d_fc_h"))} <span class="note">${esc(tr("d_fc_asof", {d: (v && v.as_of) || r.made}))}</span></h3>`;
  if (!v) h += `<p class="note">${esc(tr("d_fc_none"))}</p>`;
  else h += `<table><tbody>${v.horizons.map((x) => `<tr><td><b>${esc(tr("d_fc_" + x.horizon))}</b></td>
      <td class="num">${esc(tr("d_fc_pct", {p: Math.round(100 * x.pct)}))}</td><td>${x.expected == null ? "—" : pctChip(x.expected)}</td>
      <td><span class="chip ${x.reliable ? "positive" : "neutral"}">${esc(tr(x.reliable ? "d_fc_ok" : "d_fc_weak"))}</span></td></tr>`).join("")}</tbody></table>
      <p class="note">${esc(tr("d_fc_explain"))}</p>`;
  h += `<details><summary>${esc(tr("d_fc_track"))}</summary><ul class="pts">${(r.summary || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <p>${r.universe === "all" ? "" : job("forecast_download")} ${job("forecast")}</p></details>`;
  box.innerHTML = h;
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-fcjob]");
  if (!b) return;
  const x = await api("/api/refresh", {kind: b.dataset.fcjob});
  if (x.message === "demo") return alert(tr("d_demo_refresh"));
  S = await api("/api/state"); renderStatus(); startPolling();
});

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
// one decimal, rounded the same way as the Python side (quotes.fmt_pct), so the "why" table and the AI's text agree
function pct1(v) { if (v === null || v === undefined) return "—"; const x = Math.round(1000 * v) / 10; return (x > 0 ? "+" : "") + x.toFixed(1) + "%"; }

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
  let h = `<h2>${esc(d.ticker)} · ${esc(d.name)} <a class="back" href="#overview" title="↑">↑</a></h2>${priceHTML(d)}${techHTML(d.technical)}${!/\.(SH|SZ|BJ)$/.test(d.ticker) ? `<p class="note">${esc(tr(/\.HK$/.test(d.ticker) ? "d_bm_hk" : "d_bm_us"))}</p>` : `<div id="fc-box" class="histbox" style="margin-top:10px"></div><details class="bigmoney" ontoggle="if(this.open)loadStockMoney('${esc(d.ticker)}')"><summary><b>${esc(tr("d_bm_title"))}</b> <span class="note">${esc(tr("d_bm_sub"))}</span></summary><div id="stock-money"></div></details>`}<h3>${esc(tr("d_history"))}</h3>${chartSVG(d.history)}
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
  if ($("#fc-box")) loadForecast(d.ticker);
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
  $("#breakouts").hidden = t !== "screen" || !BRK;
  $("#view-home").hidden = t !== "home";
  $("#view-lab").hidden = t !== "lab";
  $("#view-money").hidden = t !== "money";
  $("#view-team").hidden = t !== "team";
  $("#view-paper").hidden = t !== "paper";
  $("#view-portfolio").hidden = t !== "portfolio";
  renderMoves(); renderAlerts(); renderAnns(); renderCalendar();
  history.replaceState(null, "", t === "home" ? location.pathname : "#" + t);
  if (t === "research") loadResearch();
  if (t === "digest") loadDigest();
  if (t === "screen") { loadScreen(); loadBreakouts(); }
  if (t === "home") renderHome();
  if (t === "lab") loadLabTab();
  if (t === "money") { loadMoney(); loadMargin(); }
  if (t === "team") loadTeamTab();
  if (t === "paper") { loadPaper(); loadPxAlerts(); }
  if (t === "portfolio") loadPortfolioTab();
}

// ---------- screen + evidence scorecards ----------
// ---------- smart-money map ----------
let MM = null, mmCat = "national", mmSel = null;
const yi = (v) => v === null || v === undefined ? "—" : (S.lang === "zh" ? (v >= 0 ? "+" : "") + (v / 1e8).toFixed(1) + "亿"
  : (v >= 0 ? "+" : "") + (v / 1e9).toFixed(2) + "B");
async function loadMoney() {
  try { MM = await api(`/api/moneymap?category=${mmCat}&lang=${S.lang}`); } catch (e) { MM = {error: e.message}; }
  renderMoney();
}

function renderMoney() {
  const cats = (MM && MM.categories) || {national: "国家队", social: "社保/养老金", northbound: "北向", insurance: "险资", qfii: "QFII", fund: "公募"};
  $("#mm-cats").innerHTML = Object.entries(cats).map(([k, v]) => `<button data-mmcat="${esc(k)}" class="${k === mmCat ? "on" : ""}">${esc(v.replace(/（.*）/, ""))}</button>`).join("");
  const body = $("#mm-body"), dl = $("#mm-download");
  dl.hidden = !(MM && MM.need_download);
  if (!MM) { body.innerHTML = ""; return; }
  if (MM.error) { body.innerHTML = `<p class="err">${esc(MM.error)}</p>`; return; }
  if (MM.need_download) { $("#mm-meta").textContent = ""; body.innerHTML = `<p class="empty">${esc(tr("d_mm_need", {q: MM.quarter}))}</p>`; renderMoneyDetail(); return; }
  const c = MM.counts || {}, q = MM.quarter || "";
  $("#mm-meta").textContent = tr("d_mm_meta", {q: `${q.slice(0, 4)}-${q.slice(4, 6)}-${q.slice(6)}`, n: MM.reported_companies});
  let h = `<h2>${esc(MM.label || mmCat)}</h2><div class="grid">
    <div class="kv"><b>${esc(tr("d_mm_stocks"))}</b>${MM.stocks || 0}</div>
    <div class="kv"><b>${esc(tr("d_mm_new"))}</b>${c.new || 0}</div><div class="kv"><b>${esc(tr("d_mm_add"))}</b>${c.add || 0}</div>
    <div class="kv"><b>${esc(tr("d_mm_reduce"))}</b>${c.reduce || 0}</div>
    <div class="kv"><b>${esc(tr("d_mm_net"))}</b>${esc(yi(MM.net_value_change))}</div>
    ${MM.exit_counts ? `<div class="kv"><b>${esc(tr("d_mm_exits_k"))}</b>${(MM.exit_counts.inferred || 0) + (MM.exit_counts.possible || 0)}</div>
    <div class="kv"><b>${esc(tr("d_mm_inferred_k"))}</b>${esc(yi(MM.inferred_reduction))}</div>` : ""}</div>`;
  const ht = MM.history_test;
  if (ht && (ht.new || ht.add)) {
    const one = (k) => ht[k] ? `${tr("d_mm_" + k)}：${tr("d_mm_ht_one", {a: pct1(ht[k].ann), t: ht[k].t != null ? ht[k].t.toFixed(1) : "—", n: ht[k].events, b: pct1(ht[k].ann_2x)})}` : "";
    const good = [ht.new, ht.add].some((x) => x && x.ann > 0 && x.t >= 2);
    h += `<div class="verdict ${good ? "passes" : "no_edge"}" style="margin:10px 0"><b>${esc(tr("d_mm_ht_title", {h: ht.hold_days}))}</b><br>${esc([one("new"), one("add")].filter(Boolean).join("；"))}<br><span class="note">${esc(tr(good ? "d_mm_ht_good" : "d_mm_ht_bad", {d: ht.holdout_start}))} ${esc(tr("d_nt_vs_index"))}</span></div>`;
  }
  if (mmCat === "national") h += `<div id="mm-etf"></div>`;
  const inds = MM.industries || [];
  if (inds.length) {
    const mx = Math.max(...inds.map((i) => Math.abs(i.value_change))) || 1;
    h += `<h3>${esc(tr("d_mm_by_ind"))}</h3><div>` + inds.map((i) => {
      const w = 45 * Math.abs(i.value_change) / mx, pos = i.value_change >= 0;
      return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:13px"><span style="width:110px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(i.industry)}</span>
        <span style="flex:1;position:relative;height:14px"><span style="position:absolute;left:${pos ? 50 : 50 - w}%;width:${w}%;height:14px;border-radius:3px;background:${pos ? "var(--pos)" : "var(--neg)"};opacity:.75"></span>
        <span style="position:absolute;left:50%;top:-2px;bottom:-2px;border-left:1px solid var(--line)"></span></span>
        <span class="num" style="width:76px;text-align:right">${esc(yi(i.value_change))}</span><span class="note" style="width:56px">${esc(tr("d_mm_n", {n: i.stocks}))}</span></div>`;
    }).join("") + `</div>`;
  }
  const table = (key, title) => {
    const list = MM[key] || [];
    if (!list.length) return "";
    return `<h3>${esc(title)}</h3><div class="wide"><table><tbody>` + list.map((x) => {
      const followed = S.watchlist.includes(x.ticker);
      return `<tr class="mm-row ${x.ticker === mmSel ? "sel" : ""}" data-mm="${esc(x.ticker)}" style="cursor:pointer">
        <td class="tk">${esc(x.ticker)}<small>${esc(x.name)} · ${esc(x.industry || "")}</small></td>
        <td class="num">${esc(yi(x.value_change))}</td><td class="hide-sm note">${esc(tr("d_mm_public", {d: x.public}))}</td>
        <td>${followed ? `<span class="note">${esc(tr("d_followed"))}</span>` : `<button class="btn sm" data-follow="${esc(x.ticker)}">${esc(tr("d_follow"))}</button>`}</td></tr>`;
    }).join("") + `</tbody></table></div>`;
  };
  h += table("new", tr("d_mm_t_new")) + table("added", tr("d_mm_t_added")) + table("reduced", tr("d_mm_t_reduced"));
  const ex = MM.exits || [];
  if (ex.length) {
    h += `<h3>${esc(tr("d_mm_t_exits", {q: MM.previous_quarter || ""}))}</h3><div class="wide"><table><tbody>` + ex.map((x) =>
      `<tr class="mm-row" data-mm="${esc(x.ticker)}" style="cursor:pointer"><td class="tk">${esc(x.ticker)}<small>${esc(x.name)} · ${esc(x.holder)}</small></td>
       <td><span class="chip ${x.confidence === "inferred" ? "negative" : "neutral"}">${esc(tr("d_mm_conf_" + x.confidence))}</span></td>
       <td class="num">${x.confidence === "inferred" ? esc(yi(x.value_change)) : "—"}</td></tr>`).join("") + `</tbody></table></div>`;
  } else if (!MM.previous_quarter) h += `<p class="note">${esc(tr("d_mm_no_prev"))}</p>`;
  setTimeout(() => { if (mmCat === "national") loadEtf(); }, 0);
  body.innerHTML = h + `<p class="note">${esc(MM.confidence_note || "")}</p><p class="note">${esc(MM.limits || "")}</p><p class="note">${esc(tr("d_mm_untested"))}</p>`;
  renderMoneyDetail();
}

async function loadMargin() {
  const box = $("#mm-margin");
  if (!box) return;
  let r; try { r = await api(`/api/margin?lang=${S.lang}`); } catch (e) { r = {}; }
  const btn = `<button class="btn sm" id="margin-update">${esc(tr("d_etf_update"))}</button>`;
  const ex = Object.entries(r || {}).filter(([, x]) => x && x.available);
  let h = `<h2>${esc(tr("d_margin_title"))}</h2>`;
  if (!ex.length) h += `<p class="note">${esc(tr("d_margin_need"))} ${btn}</p>`;
  else {
    h += ex.map(([k, x]) => {
      const d = x.daily || [], vals = d.map((p) => p[1]), lo = Math.min(...vals), hi = Math.max(...vals);
      const W = 240, H = 40, pts = d.map((p, i) => `${(i * W / Math.max(d.length - 1, 1)).toFixed(1)},${(H - 4 - (H - 8) * (p[1] - lo) / ((hi - lo) || 1)).toFixed(1)}`).join(" ");
      const name = (n) => `${n[0]}${S.names && S.names[n[0]] ? " " + S.names[n[0]] : ""} ${yi(n[1])}`;
      return `<p><b>${esc(tr("d_margin_" + k))}</b> ${esc(tr("d_margin_line", {a: x.from, b: x.to, v: yi(x.balance).replace("+", ""), c: yi(x.change), p: pct1(x.change_pct)}))}
        ${x.list_changes ? `<span class="note">${esc(tr("d_margin_excl", {n: x.list_changes}))}</span>` : ""}</p>
        <svg viewBox="0 0 ${W} ${H}" style="width:240px;height:40px"><polyline points="${pts}" fill="none" stroke="${x.change >= 0 ? "var(--pos)" : "var(--neg)"}" stroke-width="2"/></svg>
        <p class="note">${esc(tr("d_margin_add"))}：${esc((x.top_add || []).slice(0, 6).map(name).join("，"))}<br>${esc(tr("d_margin_cut"))}：${esc((x.top_cut || []).slice(0, 6).map(name).join("，"))}</p>`;
    }).join("") + `<p class="note">${esc(tr("d_margin_note"))} ${btn}</p>`;
  }
  let q = 0; try { q = (await api("/api/moneyhistory")).quarters || 0; } catch (e) { q = 0; }
  if (q < 8) h += `<h3>${esc(tr("d_mm_hist_title"))}</h3><p class="note">${esc(tr("d_mm_hist_need", {n: q}))} <button class="btn sm" id="mm-hist">${esc(tr("d_mm_hist_btn"))}</button></p>`;
  else h += await ntResearchHTML();
  box.innerHTML = h;
  const job = (kind) => async () => {
    const x = await api("/api/refresh", {kind});
    if (x.message === "demo") return alert(tr("d_demo_refresh"));
    S = await api("/api/state"); renderStatus(); startPolling();
  };
  const b1 = $("#margin-update"); if (b1) b1.onclick = job("margin");
  const b2 = $("#mm-hist"); if (b2) b2.onclick = job("moneyhistory");
  const b3 = $("#nt-run"); if (b3) b3.onclick = job("ntresearch");
}

async function ntResearchHTML() {
  let r; try { r = await api(`/api/ntresearch?lang=${S.lang}`); } catch (e) { return ""; }
  let h = `<h3 id="nt-sec">${esc(tr("d_nt_h"))}</h3>`;
  if (r.need_run) return h + `<p class="note">${esc(tr("d_nt_need"))} <button class="btn sm primary" id="nt-run">${esc(tr("d_nt_run"))}</button></p>`;
  h += `<div class="verdict no_edge" style="margin:8px 0"><ul class="pts" style="margin:0">${(r.summary || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  const s = r.signals, act = {new: "d_mm_new", add: "d_mm_add", reduce: "d_mm_reduce", exit: "d_nt_exit"};
  const label = (k) => (r.kind_labels || {})[k] || k;
  h += `<details><summary>${esc(tr("d_nt_table", {n: s.n_tests, b: s.bar}))}</summary><table><thead><tr><th>${esc(tr("d_nt_who"))}</th><th>${esc(tr("d_nt_act"))}</th><th>n</th><th>${esc(tr("d_nt_diff"))}</th><th>t</th></tr></thead><tbody>` +
    s.tests.slice().sort((a, b) => Math.abs(b.t || 0) - Math.abs(a.t || 0)).map((t) => `<tr><td>${esc(label(t.kind))}</td><td>${esc(tr(act[t.action]))}</td><td class="num">${t.n}</td><td>${pctChip(t.diff)}</td><td class="num">${t.t == null ? "—" : t.t.toFixed(2)}${t.passes ? " ✓" : ""}</td></tr>`).join("") +
    `</tbody></table><p class="note">${esc(tr("d_nt_table_note", {a: s.period[0], b: s.period[1]}))}</p></details>`;
  const e = r.etf;
  if (e && e.available) h += `<details><summary>${esc(tr("d_nt_etf", {n: e.rescue.n, m: e.redemption.n}))}</summary><p class="note">${esc(tr("d_nt_etf_ep"))}${esc(e.rescue.episodes.join("、") || "—")}；${esc(tr("d_nt_etf_red"))}${esc(e.redemption.episodes.join("、") || "—")}</p>
    <p class="note">${esc(tr("d_nt_etf_gap", {a: e.share_days, b: e.trading_days}))} <button class="btn sm" id="nt-run">${esc(tr("d_nt_fill"))}</button></p></details>`;
  const p = r.predict;
  if (p && p.latest_picks) h += `<details><summary>${esc(tr("d_nt_pred", {q: p.latest_quarter}))}</summary><table><tbody>${p.latest_picks.slice(0, 12).map((x) => `<tr><td class="tk">${esc(x.ticker)}<small>${esc(x.name || "")}</small></td><td class="num">${Math.round(100 * x.prob)}%</td></tr>`).join("")}</tbody></table>
    <p class="note">${esc(tr("d_nt_pred_note"))}</p></details>`;
  return h + `<p class="note">${esc(tr("d_nt_made", {d: r.made}))} ${r.etf && r.etf.available ? "" : `<button class="btn sm" id="nt-run">${esc(tr("d_nt_run"))}</button>`}</p>`;
}

function recordHTML(r) {
  const s = (r && r.summary) || {};
  let h = `<p>${esc(tr("d_team_record", {n: s.calls || 0, s: s.scored || 0, h: s.hit_rate != null ? Math.round(100 * s.hit_rate) + "%" : "—"}))}${s.decaying ? " ⚠ " + esc(tr("d_rec_decay")) : ""}</p><p class="note">${esc(s.note || "")}</p>`;
  const rows = (r && r.recent) || [];
  if (rows.length) h += `<table><tbody>` + rows.map((c) => `<tr><td class="num">${esc(c.day)}</td><td class="tk">${esc(c.ticker)}</td>
    <td><span class="chip ${STANCE_CLS[c.stance] || "neutral"}">${esc(tr("d_stance_" + c.stance))}</span></td><td class="note">${esc(tr("d_conf_" + c.confidence))} · ${c.horizon}d</td>
    <td>${c.excess == null ? `<span class="note">${esc(tr("d_rec_pending"))}</span>` : `${pctChip(c.excess)} ${c.hit ? "✓" : "✗"}`}</td></tr>`).join("") + `</tbody></table>`;
  return h;
}

async function loadEtf() {
  const box = $("#mm-etf");
  if (!box) return;
  let r; try { r = await api(`/api/etfflows?lang=${S.lang}`); } catch (e) { r = {error: e.message}; }
  const btn = `<button class="btn sm" id="etf-update">${esc(tr("d_etf_update"))}</button>`;
  if (r.need_download || r.error) {
    box.innerHTML = `<h3>${esc(tr("d_etf_title"))}</h3><p class="note">${esc(tr("d_etf_need"))} ${btn}</p>`;
  } else {
    const d = r.daily || [], mx = Math.max(...d.map((x) => Math.abs(x.net_creation || 0))) || 1;
    const W = 600, H = 90, bw = W / Math.max(d.length, 1);
    const bars = d.map((x, i) => {
      const v = x.net_creation || 0, hh = Math.abs(v) / mx * (H / 2 - 4), y = v >= 0 ? H / 2 - hh : H / 2;
      const col = x.flag ? "var(--accent)" : v >= 0 ? "var(--pos)" : "var(--neg)";
      return `<rect x="${(i * bw + 1).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${Math.max(0.5, hh).toFixed(1)}" fill="${col}" opacity="${x.flag ? 1 : 0.6}"><title>${esc(x.date)} ${esc(yi(v))}${x.csi300 != null ? " · CSI300 " + (100 * x.csi300).toFixed(2) + "%" : ""}</title></rect>`;
    }).join("");
    const flags = (r.flagged_days || []).map((x) => `<li>${esc(x.date)} · ${esc(yi(x.net_creation))} · ${esc(tr("d_etf_csi", {r: x.csi300 != null ? (100 * x.csi300).toFixed(2) + "%" : "—"}))}</li>`).join("");
    box.innerHTML = `<h3>${esc(tr("d_etf_title"))}</h3>
      <p class="note">${esc(tr("d_etf_sum", {a: r.from, b: r.to, n: yi(r.net_creation), d: yi(r.down_day_creation)}))}${r.stale ? " · " + esc(tr("d_etf_stale")) : ""} ${btn}</p>
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:120px"><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="var(--line)"/>${bars}</svg>
      ${flags ? `<p><b>${esc(tr("d_etf_flagged"))}</b></p><ul class="pts">${flags}</ul>` : `<p class="note">${esc(tr("d_etf_none"))}</p>`}
      <p class="note">${esc(r.rule || "")} ${esc(r.caveat || "")}</p>`;
  }
  const b = $("#etf-update");
  if (b) b.onclick = async () => {
    const x = await api("/api/refresh", {kind: "etf"});
    if (x.message === "demo") return alert(tr("d_demo_refresh"));
    S = await api("/api/state"); renderStatus(); startPolling();
  };
}

async function renderMoneyDetail(tk) {
  const box = $("#mm-detail");
  if (tk === undefined) { if (!mmSel) { box.innerHTML = `<p class="empty">${esc(tr("d_mm_pick"))}</p>`; } return; }
  mmSel = tk;
  box.innerHTML = `<p class="note">${esc(tr("d_lab_wait"))}</p>`;
  let r; try { r = await api(`/api/smartmoney?ticker=${encodeURIComponent(tk)}&lang=${S.lang}`); } catch (e) { r = {error: e.message}; }
  if (r.error) { box.innerHTML = `<p class="err">${esc(r.error)}</p>`; return; }
  box.innerHTML = `<h2>${esc(tk)}${r.name ? " · " + esc(r.name) : ""}</h2>` + smartMoneyHTML(r);
}

// who holds it, who is trading it: shared by the money tab and the stock page
function bigMoneySignals(r) {
  const out = [], kinds = new Set((r.holders || []).map((x) => x.category).filter(Boolean));
  const lab = (k) => { const x = (r.holders || []).find((h) => h.category === k); return x && x.label ? x.label.replace(/（.*）/, "") : k; };
  if (kinds.size) out.push(tr("d_bm_holders", {k: [...kinds].map(lab).join("、")}));
  else out.push(tr("d_bm_noholders"));
  const adds = (r.holders || []).filter((x) => x.category && ["new", "add"].includes(x.action)).length;
  const cuts = (r.holders || []).filter((x) => x.category && x.action === "reduce").length + (r.exits || []).length;
  if (adds || cuts) out.push(tr("d_bm_flow", {a: adds, c: cuts}));
  const lhb = r.dragon_tiger || [];
  if (lhb.length) {
    const inst = lhb.reduce((s, x) => s + (x.inst_net || 0), 0);
    out.push(tr("d_bm_lhb", {n: lhb.length, v: yi(inst)}));
  }
  if (r.main_force) out.push(tr("d_bm_main", {d: r.main_force.days, v: yi(r.main_force.net), p: r.main_force.positive_days}));
  if (r.margin && r.margin.available) out.push(tr("d_bm_margin", {p: pct1(r.margin.change_pct)}));
  return out;
}

function smartMoneyHTML(r) {
  const act = {new: tr("d_mm_new"), add: tr("d_mm_add"), reduce: tr("d_mm_reduce"), same: tr("d_mm_same")};
  let h = `<ul class="pts">${bigMoneySignals(r).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>${r.summary ? `<p class="note">${esc(r.summary)}</p>` : ""}`;
  if ((r.exits || []).length) h += `<h3>${esc(tr("d_mm_t_exits", {q: r.previous_quarter || ""}))}</h3><table><tbody>` + r.exits.map((x) =>
    `<tr><td><span class="chip neutral">${esc((x.label || "").replace(/（.*）/, ""))}</span> ${esc(x.display)}</td>
     <td><span class="chip ${x.confidence === "inferred" ? "negative" : "neutral"}">${esc(tr("d_mm_conf_" + x.confidence))}</span></td>
     <td class="note">${x.confidence === "inferred" ? esc(tr("d_mm_sold", {n: (x.sold_at_least / 1e4).toFixed(0)})) : ""}${x.now_at_most ? " " + esc(tr("d_mm_cap", {n: (x.now_at_most / 1e4).toFixed(0)})) : ""}</td></tr>`).join("") + `</tbody></table>`;
  if ((r.holders || []).length) h += `<h3>${esc(tr("d_mm_top10"))}</h3><table><tbody>` + r.holders.map((x) =>
    `<tr><td>${x.label ? `<span class="chip neutral">${esc(x.label.replace(/（.*）/, ""))}</span> ` : ""}${esc(x.display || x.holder)}</td>
     <td class="note">${esc(act[x.action] || x.action || "")}${x.change_pct != null ? " " + (x.change_pct > 0 ? "+" : "") + Number(x.change_pct).toFixed(1) + "%" : ""}</td></tr>`).join("") + `</tbody></table>`;
  const lhb = r.dragon_tiger || [];
  if (lhb.length) h += `<h3>${esc(tr("d_mm_lhb"))}</h3><table><tbody>` + lhb.map((x) =>
    `<tr><td class="num">${esc(x.day)}</td><td>${pctChip(x.pct / 100)}</td><td class="note">${esc(x.note || x.reason || "")}${x.inst_net != null ? " · " + esc(tr("d_mm_inst", {v: yi(x.inst_net)})) : ""}</td></tr>`).join("") + `</tbody></table>`;
  const mg = r.margin;
  if (mg && mg.available) h += `<p class="note">${esc(tr("d_mm_margin", {a: mg.from, b: mg.to, v: yi(mg.balance).replace("+", ""), c: yi(mg.change), p: pct1(mg.change_pct)}))}</p>`;
  else if (mg && mg.note) h += `<p class="note">${esc(mg.note)}</p>`;
  if (r.main_force) h += `<p class="note">${esc(tr("d_mm_mainforce", {d: r.main_force.days, v: yi(r.main_force.net), p: r.main_force.positive_days}))} ${esc(r.main_force.note || "")}</p>`;
  return h + `<p class="note">${esc(tr("d_bm_caveat"))}</p>`;
}

async function loadStockMoney(tk) {
  const box = $("#stock-money"); if (!box || box.dataset.tk === tk) return;
  box.dataset.tk = tk;
  box.innerHTML = `<p class="note">${esc(tr("d_lab_wait"))}</p>`;
  let r; try { r = await api(`/api/smartmoney?ticker=${encodeURIComponent(tk)}&lang=${S.lang}`); } catch (e) { r = {error: e.message}; }
  if (selected !== tk) return;
  box.innerHTML = r.error ? `<p class="note">${esc(r.error)}</p>` : smartMoneyHTML(r) + `<p><a href="#" data-gomoney="${esc(tk)}">${esc(tr("d_bm_more"))}</a></p>`;
}
document.addEventListener("click", (e) => {
  const g = e.target.closest("[data-gomoney]");
  if (g) { e.preventDefault(); showTab("money"); setTimeout(() => renderMoneyDetail(g.dataset.gomoney), 400); }
});

let BRK = null;
async function loadBreakouts() {
  try { const r = await api(`/api/breakouts?lang=${S.lang}`); BRK = r && r.hits ? r : null; } catch (e) { BRK = null; }
  renderBreakouts();
}

function renderBreakouts(msg) {
  const box = $("#breakouts");
  box.hidden = tab !== "screen" || (!BRK && !msg);
  if (msg) { box.innerHTML = `<p class="note">${esc(msg)}</p>`; return; }
  if (!BRK) return;
  const b = BRK;
  let h = `<h2>${esc(tr("d_brk_title"))} · ${esc(b.day)}</h2><p class="note">${esc(tr("d_brk_count", {up: b.breakouts, down: b.breakdowns, n: b.candidates}))}${b.stale ? " · " + esc(b.stale) : ""}</p>`;
  if (!b.hits.length) h += `<p class="empty">${esc(tr("d_brk_none"))}</p>`;
  else {
    h += `<div class="wide"><table><tbody>` + b.hits.map((x) => {
      const followed = S.watchlist.includes(x.ticker);
      const zone = x.zone && x.zone[0] != null ? `${Number(x.zone[0]).toFixed(2)}–${Number(x.zone[1]).toFixed(2)}` : "";
      return `<tr><td style="color:${x.kind === "breakout" ? "var(--pos)" : "var(--neg)"}">${x.kind === "breakout" ? "▲" : "▼"} ${esc(tr("ta_" + x.kind))}</td>
        <td class="tk">${esc(x.ticker)}<small>${esc(x.name)}</small></td><td>${pctChip(x.pct)}</td>
        <td class="hide-sm note">${esc(tr(x.kind === "breakout" ? "ta_resistance" : "ta_support"))} ${esc(zone)}${x.touches ? " · " + esc(tr("ta_touches", {n: x.touches})) : ""}${x.zones_crossed > 1 ? " · " + esc(tr("d_brk_multi", {n: x.zones_crossed})) : ""}${x.vol_ratio ? " · " + esc(tr("d_brk_vol", {v: Number(x.vol_ratio).toFixed(1)})) : ""}</td>
        <td>${followed ? `<span class="note">${esc(tr("d_followed"))}</span>` : `<button class="btn sm" data-follow="${esc(x.ticker)}">${esc(tr("d_follow"))}</button>`}</td></tr>`;
    }).join("") + `</tbody></table></div>`;
  }
  box.innerHTML = h + `<p class="note">${esc(b.how || "")}</p><p class="note">${esc(b.note || "")}</p>`;
}

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
    {icon: "🤖", key: "team", items: [
      first ? {label: tr("d_home_ex_team", {name: fname}), act: "team", arg: first} : {label: tr("d_home_ex_add"), act: "stocks"},
      {label: tr("d_home_ex_teamtab"), act: "teamtab"},
      {label: tr("d_home_ex_record"), act: "record"}]},
    {icon: "📒", key: "paper", items: [
      {label: tr("d_home_ex_paper"), act: "paper"},
      {label: tr("d_home_ex_paperlab"), act: "lab"},
      {label: tr("d_home_ex_alerts"), act: "alerts"}]},
    {icon: "💰", key: "money", items: [
      {label: tr("d_home_ex_mm"), act: "money", arg: "national"},
      {label: tr("d_home_ex_etf"), act: "money", arg: "national"},
      {label: tr("d_home_ex_margin"), act: "margin"}]},
    {icon: "🔎", key: "screen", items: [
      {label: tr("d_home_ex_screen"), act: "screen", ask: tr("d_home_q_screen")},
      {label: tr("d_home_ex_brk"), act: "breakouts"},
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
  return doAct(homeCards()[ci].items.filter(Boolean)[i], $("#home-out-" + ci));
}

async function doAct(x, out) {
  if (x.act === "stocks") return showTab("stocks");
  if (x.act === "digest") return showTab("digest");
  if (x.act === "screen") return showTab("screen");
  if (x.act === "lab") return showTab("lab");
  if (x.act === "team") { showTab("stocks"); selected = x.arg; renderOverview(); await loadStock(); $("#detail").scrollIntoView({behavior: "smooth", block: "start"}); return askTeam(x.arg); }
  if (x.act === "teamtab") return showTab("team");
  if (x.act === "record") { out.innerHTML = `<p class="note">${esc(tr("d_lab_wait"))}</p>`; out.innerHTML = recordHTML(await api(`/api/team/record?lang=${S.lang}`)); return; }
  if (x.act === "money") { mmCat = x.arg; showTab("money"); return; }
  if (x.act === "paper") return showTab("paper");
  if (x.act === "teamtext") { showTab("team"); $("#team-input").value = x.arg; return runTeamText(x.arg); }
  if (x.act === "holders") { showTab("money"); setTimeout(() => { renderMoneyDetail(x.arg); const b = $("#mm-detail"); if (b) b.scrollIntoView({behavior: "smooth"}); }, 600); return; }
  if (x.act === "pftext") { showTab("portfolio"); await loadPortfolioTab(); $("#pf-input").value = x.arg; return runPortfolio(); }
  if (x.act === "paperorder") {
    let A = []; try { A = (await api("/api/paper")).accounts.filter((a) => a.kind === "manual"); } catch (e) {}
    const aid = A.length ? A[A.length - 1].id : (await api("/api/paper", {action: "new", name: tr("d_pp_default")})).id;
    const r = await api("/api/paper", {action: x.side, account: aid, ticker: x.arg, value: x.value || 0, shares: x.shares || 0});
    if (out) out.textContent = r.error ? r.error : tr("d_ask_paper_ok", {a: A.length ? A[A.length - 1].name : tr("d_pp_default")});
    ppSel = aid; return showTab("paper");
  }
  if (x.act === "alerts") { showTab("paper"); return loadPxAlerts(true); }
  if (x.act === "margin") { showTab("money"); setTimeout(() => { const m = $("#mm-margin"); if (m) m.scrollIntoView({behavior: "smooth"}); }, 800); return; }
  if (x.act === "breakouts") { showTab("screen"); setTimeout(() => $("#run-breakouts").click(), 300); return; }
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
  const rob = [r.stress, r.walk_forward].filter((x) => x && x.text && !(v.warnings || []).includes(x.text));
  if (rob.length) h += rob.map((x) => `<p class="note" style="color:${["fragile", "fades"].includes(x.code) ? "var(--neg)" : "inherit"}">${["fragile", "fades"].includes(x.code) ? "⚠ " : "✓ "}${esc(x.text)}</p>`).join("");
  if ((r.years || []).length) h += `<p class="note">${r.years.map((y) => `${y.year}: ${y.excess === null ? "—" : (y.excess > 0 ? "+" : "") + (100 * y.excess).toFixed(1) + "%"}`).join(" · ")}</p>`;
  h += `<div class="toolbar"><a class="btn primary" href="${esc(r.report_url)}" target="_blank" rel="noopener">${esc(tr("d_lab_open"))}</a>`;
  if (r.phase === "explore" && v.code === "passes") h += `<button class="btn" data-confirm="${esc(r.id)}">${esc(tr("d_lab_confirm"))}</button>`;
  if (r.id) h += `<button class="btn" data-share="lab|${esc(r.id)}">${esc(tr("d_card_make"))}</button>`;
  if (r.id && ["earnings", "forecast", "smart_money"].includes(r.spec.type)) h += `<button class="btn" data-paperexp="${esc(r.id)}">${esc(tr("d_pp_from_lab"))}</button>`;
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
    if (!S.job.running) { clearInterval(pollTimer); pollTimer = null; await loadAll(); if (tab === "money") { loadMoney(); loadMargin(); } }
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
  if (fb) { e.stopPropagation(); fb.disabled = true; await follow(fb.dataset.follow); if (tab === "money") renderMoney(); return; }
  const mc = e.target.closest("[data-mmcat]");
  if (mc) { mmCat = mc.dataset.mmcat; mmSel = null; return loadMoney(); }
  const mr = e.target.closest("tr.mm-row");
  if (mr) {
    document.querySelectorAll("tr.mm-row").forEach((x) => x.classList.toggle("sel", x === mr));
    await renderMoneyDetail(mr.dataset.mm);
    if (window.matchMedia("(max-width: 960px)").matches) $("#mm-detail").scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
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
  const tex = e.target.closest("[data-teamex]");
  if (tex) { const q = teamExamples()[+tex.dataset.teamex]; $("#team-input").value = q; return runTeamText(q); }
  const trow = e.target.closest("tr.team-row");
  if (trow) {
    const r = await api(`/api/team/call?id=${encodeURIComponent(trow.dataset.callid)}`);
    const out = $("#team-out");
    out.innerHTML = (r.question ? `<p class="note">${esc(tr("d_team_q"))}：${esc(r.question)}</p>` : "") + teamHTML(r);
    const det = out.querySelector("details"); if (det) det.open = true;
    out.scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const rb = e.target.closest("[data-record]");
  if (rb) { e.stopPropagation(); const b = $("#record-box"); if (b) b.innerHTML = recordHTML(await api(`/api/team/record?lang=${S.lang}`)); return; }
  const teamBtn = e.target.closest("[data-team]");
  if (teamBtn) { e.stopPropagation(); return askTeam(teamBtn.dataset.team); }
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
$("#team-go").onclick = () => runTeamText($("#team-input").value);
$("#team-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runTeamText($("#team-input").value); });
$("#mm-download").onclick = async () => {
  const r = await api("/api/refresh", {kind: "moneymap"});
  if (r.message === "demo") return alert(tr("d_demo_refresh"));
  S = await api("/api/state"); renderStatus(); startPolling();
};
$("#run-breakouts").onclick = async () => {
  const btn = $("#run-breakouts"); btn.disabled = true;
  renderBreakouts(tr("d_brk_wait"));
  let r;
  try { r = await api("/api/breakouts", {lang: S.lang}); } catch (e) { r = {error: e.message}; }
  btn.disabled = false;
  if (r.message === "demo") { renderBreakouts(); return alert(tr("d_demo_refresh")); }
  if (r.error) return renderBreakouts(r.error);
  BRK = r; renderBreakouts();
};
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
