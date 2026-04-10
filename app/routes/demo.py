from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lisser Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d0d14;color:#d4d4e0;min-height:100vh}

header{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-bottom:1px solid #2a2a40;padding:16px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
.logo{display:flex;align-items:center}
.logo-text h1{font-size:17px;font-weight:700;color:#fff}
.logo-text p{font-size:11px;color:#5566aa;margin-top:1px}
.header-right{display:flex;align-items:center;gap:14px}
#statusText{font-size:12px;color:#5566aa;max-width:280px;text-align:right}
.sync-btn{background:linear-gradient(135deg,#6c63ff,#4f46e5);color:#fff;border:none;padding:9px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .2s,transform .1s;white-space:nowrap}
.sync-btn:hover:not(:disabled){opacity:.88;transform:translateY(-1px)}
.sync-btn:active:not(:disabled){transform:translateY(0)}
.sync-btn:disabled{opacity:.35;cursor:default;transform:none}

main{padding:28px 32px;max-width:880px}

.stats{display:flex;gap:12px;margin-bottom:28px}
.stat-card{flex:1;background:#1a1a2e;border:1px solid #2a2a40;border-radius:12px;padding:16px 20px}
.stat-label{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:#5566aa;margin-bottom:6px}
.stat-value{font-size:30px;font-weight:700;color:#fff}
.stat-card.s-new .stat-value{color:#4dde99}
.stat-card.s-soon .stat-value{color:#f6a031}
.stat-card.s-overdue .stat-value{color:#e89030}

.section{margin-bottom:22px}
.section-header{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.dot{width:7px;height:7px;border-radius:50%}
.dot.new{background:#4dde99}
.dot.soon{background:#f6a031}
.dot.overdue{background:#e89030}
.section-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:#8888bb}

.cards{display:flex;flex-direction:column;gap:6px}
.card{background:#1a1a2e;border:1px solid #2a2a40;border-radius:10px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;transition:border-color .15s}
.card:hover{border-color:#3a3a58}
.card.new{border-left:3px solid #4dde99}
.card.soon{border-left:3px solid #f6a031}
.card.overdue{border-left:3px solid #e89030}
.card-left{flex:1;min-width:0}
.card-name{font-size:14px;font-weight:600;color:#e0e0f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-course{font-size:11px;color:#55558a;margin-top:2px}
.card-due{font-size:12px;color:#66669a;white-space:nowrap;margin-left:16px}
.card-due.overdue{color:#e89030;font-weight:600}
.card-due.soon{color:#f6a031}
.empty{color:#33334a;font-size:13px;font-style:italic;padding:10px 0}

.spinner{display:inline-block;width:11px;height:11px;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:spin .65s linear infinite;vertical-align:middle;margin-right:5px}
@keyframes spin{to{transform:rotate(360deg)}}

.skeleton{height:46px;background:#1a1a2e;border-radius:10px;border:1px solid #2a2a40;animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-text">
      <h1>Listserv Bot</h1>
      <p>Alpha Eta</p>
    </div>
  </div>
  <div class="header-right">
    <span id="statusText"></span>
    <button class="sync-btn" id="syncBtn" onclick="syncAndRefresh()">&#x21BB; Sync &amp; Refresh</button>
  </div>
</header>

<main>
  <div class="stats">
    <div class="stat-card s-new">
      <div class="stat-label">Newly Assigned</div>
      <div class="stat-value" id="countNew">&ndash;</div>
    </div>
    <div class="stat-card s-soon">
      <div class="stat-label">Due Soon</div>
      <div class="stat-value" id="countSoon">&ndash;</div>
    </div>
    <div class="stat-card s-overdue">
      <div class="stat-label">Overdue</div>
      <div class="stat-value" id="countOverdue">&ndash;</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><div class="dot new"></div><div class="section-title">Newly Assigned &mdash; last 24h</div></div>
    <div class="cards" id="newlyAssigned"><div class="skeleton"></div></div>
  </div>

  <div class="section">
    <div class="section-header"><div class="dot soon"></div><div class="section-title">Due Soon &mdash; next 72h</div></div>
    <div class="cards" id="dueSoon"><div class="skeleton"></div></div>
  </div>

  <div class="section">
    <div class="section-header"><div class="dot overdue"></div><div class="section-title">Overdue</div></div>
    <div class="cards" id="overdue"><div class="skeleton"></div></div>
  </div>
</main>

<script>
function esc(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}

function renderCards(id, items, cls){
  const el=document.getElementById(id);
  if(!items||!items.length){el.innerHTML='<div class="empty">(none)</div>';return}
  const icons={overdue:'&#9888; ',soon:'&#9200; ',new:''};
  el.innerHTML=items.map(a=>`
    <div class="card ${cls}">
      <div class="card-left">
        <div class="card-name">${esc(a.name)}</div>
        ${a.course?`<div class="card-course">${esc(a.course)}</div>`:''}
      </div>
      ${a.due_formatted?`<div class="card-due ${cls==='new'?'':cls}">${icons[cls]||''}${esc(a.due_formatted)}</div>`:''}
    </div>`).join('');
}

async function loadReport(){
  try{
    const r=await fetch('/report/json');
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    document.getElementById('countNew').textContent=d.newly_assigned.length;
    document.getElementById('countSoon').textContent=d.due_soon.length;
    document.getElementById('countOverdue').textContent=d.overdue.length;
    renderCards('newlyAssigned',d.newly_assigned,'new');
    renderCards('dueSoon',d.due_soon,'soon');
    renderCards('overdue',d.overdue,'overdue');
    document.getElementById('statusText').textContent='Updated '+d.generated_at;
  }catch(e){
    document.getElementById('statusText').textContent='Failed to load';
    console.error(e);
  }
}

async function syncAndRefresh(){
  const btn=document.getElementById('syncBtn');
  btn.disabled=true;
  btn.innerHTML='<span class="spinner"></span>Syncing\u2026';
  document.getElementById('statusText').textContent='Syncing with Gmail\u2026';
  try{
    const r=await fetch('/sync',{method:'POST'});
    const d=await r.json();
    const msg=d.error?('Error: '+d.error):`Synced \u2014 ${d.new_messages??0} new messages, ${d.new_events??0} new events`;
    document.getElementById('statusText').textContent=msg;
    await loadReport();
  }catch(e){
    document.getElementById('statusText').textContent='Sync failed: '+e.message;
  }
  btn.disabled=false;
  btn.innerHTML='&#x21BB; Sync &amp; Refresh';
}

loadReport();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def demo_page():
    return _HTML
