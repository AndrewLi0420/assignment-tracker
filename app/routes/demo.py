from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YaduBot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d0d14;color:#d4d4e0;min-height:100vh}

header{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-bottom:1px solid #2a2a40;padding:16px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
.logo-text h1{font-size:17px;font-weight:700;color:#fff}
.logo-text p{font-size:11px;color:#5566aa;margin-top:1px}
.header-right{display:flex;align-items:center;gap:14px}
#statusText{font-size:12px;color:#5566aa;max-width:280px;text-align:right}
.sync-btn{background:linear-gradient(135deg,#6c63ff,#4f46e5);color:#fff;border:none;padding:9px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .2s,transform .1s;white-space:nowrap}
.sync-btn:hover:not(:disabled){opacity:.88;transform:translateY(-1px)}
.sync-btn:active:not(:disabled){transform:translateY(0)}
.sync-btn:disabled{opacity:.35;cursor:default;transform:none}

main{padding:28px 32px;max-width:860px}

.stats{display:flex;gap:12px;margin-bottom:28px}
.stat-card{flex:1;background:#1a1a2e;border:1px solid #2a2a40;border-radius:12px;padding:16px 20px}
.stat-label{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:#5566aa;margin-bottom:6px}
.stat-value{font-size:30px;font-weight:700;color:#fff}
.stat-card.s-soon .stat-value{color:#f6a031}
.stat-card.s-overdue .stat-value{color:#e05252}
.stat-card.s-all .stat-value{color:#7b8cde}

/* Thread groups */
.thread-group{margin-bottom:20px;border:1px solid #2a2a40;border-radius:12px;overflow:hidden;background:#13131f}
.thread-header{padding:11px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a40;font-size:12px;font-weight:700;color:#9999cc;text-transform:uppercase;letter-spacing:.5px;display:flex;align-items:center;gap:8px}
.thread-header .pill{font-size:10px;font-weight:600;padding:2px 7px;border-radius:20px;background:#2a2a40;color:#7777aa}
.bullet-list{padding:10px 16px;display:flex;flex-direction:column;gap:4px}
.bullet-item{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e1e30;transition:opacity .2s}
.bullet-item:last-child{border-bottom:none}
.bullet-item.done{opacity:.38}
.bullet-dot{flex-shrink:0;width:6px;height:6px;border-radius:50%;background:#44446a}
.bullet-dot.overdue{background:#e05252}
.bullet-dot.due_soon{background:#f6a031}
.bullet-dot.active{background:#5577dd}
.bullet-name{flex:1;font-size:14px;color:#d8d8ee;line-height:1.4}
.bullet-name.done{text-decoration:line-through;color:#55558a}
.bullet-due{font-size:11px;white-space:nowrap;color:#55558a;margin-left:4px}
.bullet-due.overdue{color:#e05252;font-weight:600}
.bullet-due.due_soon{color:#f6a031;font-weight:500}
.done-btn{flex-shrink:0;width:22px;height:22px;border-radius:50%;border:1.5px solid #3a3a55;background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:border-color .15s,background .15s;color:transparent;font-size:12px}
.done-btn:hover{border-color:#5577dd;background:#1e1e38}
.done-btn.checked{border-color:#3a6a3a;background:#1e381e;color:#4caf50}

.empty-state{color:#33334a;font-size:13px;font-style:italic;padding:20px 0 8px}

.spinner{display:inline-block;width:11px;height:11px;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:spin .65s linear infinite;vertical-align:middle;margin-right:5px}
@keyframes spin{to{transform:rotate(360deg)}}
.skeleton{height:80px;background:#1a1a2e;border-radius:12px;border:1px solid #2a2a40;animation:pulse 1.4s ease-in-out infinite;margin-bottom:12px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>

<header>
  <div class="logo-text">
    <h1>YaduBot</h1>
    <p>Alpha Eta Assignment Tracker</p>
  </div>
  <div class="header-right">
    <span id="statusText"></span>
    <button class="sync-btn" id="syncBtn" onclick="syncAndRefresh()">&#x21BB; Sync &amp; Refresh</button>
  </div>
</header>

<main>
  <div class="stats">
    <div class="stat-card s-soon">
      <div class="stat-label">Due Soon</div>
      <div class="stat-value" id="countSoon">&ndash;</div>
    </div>
    <div class="stat-card s-overdue">
      <div class="stat-label">Overdue</div>
      <div class="stat-value" id="countOverdue">&ndash;</div>
    </div>
    <div class="stat-card s-all">
      <div class="stat-label">All Active</div>
      <div class="stat-value" id="countAll">&ndash;</div>
    </div>
  </div>

  <div id="threadContainer">
    <div class="skeleton"></div>
    <div class="skeleton"></div>
    <div class="skeleton"></div>
  </div>
</main>

<script>
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}

function renderThreads(threads){
  const el=document.getElementById('threadContainer');
  if(!threads||!threads.length){
    el.innerHTML='<div class="empty-state">No active assignments found.</div>';
    return;
  }
  el.innerHTML=threads.map(t=>{
    const items=t.assignments||[];
    const title=esc(t.thread_subject||(t.thread_id||'Unknown Thread'));
    const bullets=items.map(a=>{
      const st=a.status==='overdue'?'overdue':a.status==='due_soon'?'due_soon':'active';
      const dueLabel=a.due_at_estimated
        ?(a.due_formatted?`~${esc(a.due_formatted)}`:'')
        :(a.due_formatted?esc(a.due_formatted):'');
      const dueCls=a.status==='overdue'?'overdue':a.status==='due_soon'?'due_soon':'';
      return `<div class="bullet-item" id="row-${a.id}">
        <button class="done-btn" onclick="toggleDone(${a.id},this)" title="Mark as done">&#10003;</button>
        <div class="bullet-dot ${st}"></div>
        <div class="bullet-name">${esc(a.name)}</div>
        ${dueLabel?`<div class="bullet-due ${dueCls}">${dueLabel}</div>`:''}
      </div>`;
    }).join('');
    return `<div class="thread-group">
      <div class="thread-header">${title}<span class="pill">${items.length}</span></div>
      <div class="bullet-list">${bullets}</div>
    </div>`;
  }).join('');
}

async function toggleDone(id, btn){
  const row=document.getElementById('row-'+id);
  const isDone=btn.classList.contains('checked');
  // Optimistic UI
  btn.classList.toggle('checked',!isDone);
  row.classList.toggle('done',!isDone);
  row.querySelector('.bullet-name').classList.toggle('done',!isDone);
  try{
    await fetch(`/assignments/${id}/${isDone?'uncomplete':'complete'}`,{method:'POST'});
  }catch(e){
    // revert on failure
    btn.classList.toggle('checked',isDone);
    row.classList.toggle('done',isDone);
    row.querySelector('.bullet-name').classList.toggle('done',isDone);
  }
}

async function loadReport(){
  try{
    const r=await fetch('/report/json');
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    document.getElementById('countSoon').textContent=d.due_soon.length;
    document.getElementById('countOverdue').textContent=d.overdue.length;
    document.getElementById('countAll').textContent=(d.due_soon.length+d.overdue.length+(d.upcoming||[]).length);
    renderThreads(d.threads||[]);
    document.getElementById('statusText').textContent='Updated '+d.generated_at;
  }catch(e){
    document.getElementById('statusText').textContent='Failed to load';
    console.error(e);
  }
}

async function syncAndRefresh(){
  const btn=document.getElementById('syncBtn');
  btn.disabled=true;
  let totalMessages=0,totalEvents=0,batch=0;
  const MAX_BATCHES=30;
  try{
    while(batch<MAX_BATCHES){
      batch++;
      btn.innerHTML=`<span class="spinner"></span>Syncing batch ${batch}\u2026`;
      document.getElementById('statusText').textContent=`Scanning emails (batch ${batch})\u2026`;
      let r,d;
      try{
        const controller=new AbortController();
        const tid=setTimeout(()=>controller.abort(),25000);
        r=await fetch('/sync',{method:'POST',signal:controller.signal});
        clearTimeout(tid);
      }catch(fe){
        document.getElementById('statusText').textContent=`Batch ${batch} timed out, retrying\u2026`;
        await new Promise(res=>setTimeout(res,2000));
        batch--;
        continue;
      }
      if(!r.ok){const t=await r.text();throw new Error(t.slice(0,120));}
      d=await r.json();
      if(d.error){document.getElementById('statusText').textContent='Error: '+d.error;break;}
      totalMessages+=d.new_messages??0;
      totalEvents+=d.new_events??0;
      const remaining=d.remaining??0;
      if(remaining<=0&&(d.new_messages??0)===0){
        document.getElementById('statusText').textContent=`Done \u2014 ${totalMessages} new emails, ${totalEvents} assignments found`;
        break;
      }
      document.getElementById('statusText').textContent=`Batch ${batch} done \u2014 ${remaining} emails remaining\u2026`;
    }
    await loadReport();
  }catch(e){
    document.getElementById('statusText').textContent='Sync failed: '+e.message;
    await loadReport();
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
