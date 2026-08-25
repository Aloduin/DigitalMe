# ruff: noqa: E501
"""Dependency-free browser prototype for the current archive slice."""

PROTOTYPE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DigitalMe Memory Engine</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#0b1020; color:#e8edf7; }
    * { box-sizing: border-box; }
    body { margin:0; background:radial-gradient(circle at 15% 0,#18264c 0,#0b1020 42%); }
    header, main { width:min(1180px, calc(100% - 32px)); margin:auto; }
    header { padding:42px 0 24px; display:flex; justify-content:space-between; gap:20px; align-items:end; }
    h1 { margin:0; font-size:clamp(28px,5vw,52px); letter-spacing:-.04em; }
    h2 { margin:0 0 14px; font-size:18px; }
    p { color:#aebbd2; }
    .badge { color:#73e0c1; border:1px solid #286b62; border-radius:999px; padding:7px 11px; }
    main { display:grid; grid-template-columns:1fr 1.3fr; gap:18px; padding-bottom:48px; }
    .card { background:rgba(18,27,52,.88); border:1px solid #293658; border-radius:18px; padding:20px; box-shadow:0 16px 50px #03071255; }
    .wide { grid-column:1 / -1; }
    .toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
    button, select, input::file-selector-button { border:1px solid #435176; border-radius:10px; background:#202c4c; color:#f2f5fb; padding:9px 12px; cursor:pointer; }
    button:hover { background:#2a3a63; }
    input { max-width:100%; color:#aebbd2; }
    .list { display:grid; gap:9px; max-height:440px; overflow:auto; margin-top:14px; }
    .row { width:100%; text-align:left; padding:13px; border:1px solid #303f66; border-radius:12px; background:#111a33; }
    .row strong, .row span { display:block; }
    .row span, .meta { color:#91a1bd; font-size:13px; margin-top:5px; }
    .messages { display:grid; gap:12px; max-height:650px; overflow:auto; }
    .message { border-left:3px solid #5a77bd; padding:11px 14px; background:#10182e; border-radius:4px 12px 12px 4px; white-space:pre-wrap; overflow-wrap:anywhere; }
    .message.user { border-color:#73e0c1; }
    .message.secret { border-color:#f3a65a; }
    .status { min-height:22px; color:#73e0c1; }
    .empty { color:#8290ab; padding:18px 0; }
    @media (max-width:800px) { main { grid-template-columns:1fr; } .wide { grid-column:auto; } header { align-items:start; flex-direction:column; } }
  </style>
</head>
<body>
  <header>
    <div><div class="badge">Local-first prototype</div><h1>DigitalMe</h1><p>从真实对话回看你的数字经历。</p></div>
    <button id="refresh">刷新数据</button>
  </header>
  <main>
    <section class="card">
      <h2>导入 ChatGPT</h2>
      <p>选择官方导出的 ZIP。文件仅发送到本机服务。</p>
      <div class="toolbar"><input id="archive" type="file" accept=".zip,application/zip"><button id="upload">开始导入</button></div>
      <p id="upload-status" class="status" aria-live="polite"></p>
    </section>
    <section class="card">
      <h2>最近任务</h2><div id="jobs" class="list"></div>
    </section>
    <section class="card">
      <div class="toolbar"><h2>历史 Sessions</h2><select id="source"><option value="">全部来源</option><option value="chatgpt">ChatGPT</option><option value="codex">Codex</option></select></div>
      <div id="session-count" class="meta"></div><div id="sessions" class="list"></div>
    </section>
    <section class="card">
      <h2 id="detail-title">选择一个 Session</h2><div id="detail-meta" class="meta"></div><div id="messages" class="messages"><div class="empty">脱敏消息会显示在这里。</div></div>
    </section>
  </main>
  <script>
    const byId = (id) => document.getElementById(id);
    const node = (tag, text, className) => { const value=document.createElement(tag); if(text!==undefined)value.textContent=text; if(className)value.className=className; return value; };
    async function api(path, options) { const response=await fetch(path, options); if(!response.ok){ let detail=response.statusText; try{detail=(await response.json()).detail||detail;}catch{} throw new Error(detail); } return response.json(); }
    function renderJobs(items) { const root=byId('jobs'); root.replaceChildren(); if(!items.length){root.append(node('div','暂无导入任务','empty'));return;} for(const item of items){ const row=node('div',undefined,'row'); row.append(node('strong',item.kind+' · '+item.status),node('span',(item.source_type||'unknown')+' · '+(item.stage||'-'))); root.append(row); } }
    function renderSessions(payload) { byId('session-count').textContent=`共 ${payload.total} 条`; const root=byId('sessions'); root.replaceChildren(); if(!payload.items.length){root.append(node('div','暂无 Session','empty'));return;} for(const item of payload.items){ const row=node('button',undefined,'row'); row.type='button'; row.append(node('strong',item.title||'(untitled)'),node('span',`${item.source_type} · ${item.message_count} messages · ${item.source_updated_at||'-'}`)); row.addEventListener('click',()=>loadDetail(item.id)); root.append(row); } }
    async function loadDetail(id) { const detail=await api('/api/v1/sessions/'+encodeURIComponent(id)); byId('detail-title').textContent=detail.title||'(untitled)'; byId('detail-meta').textContent=`${detail.source_type} · schema v${detail.schema_version}`; const root=byId('messages'); root.replaceChildren(); if(!detail.messages.length){root.append(node('div','此 Session 没有可显示消息','empty'));return;} for(const item of detail.messages){ const box=node('article',undefined,`message ${item.role||''} ${item.sensitivity||''}`); box.append(node('strong',`${item.role||'unknown'} · ${item.sensitivity}`),node('div',item.redacted_text===null?'[尚未生成脱敏视图]':item.redacted_text)); root.append(box); } }
    async function refresh() { try { const source=byId('source').value; const query=source?'?limit=100&source_type='+encodeURIComponent(source):'?limit=100'; const [sessions,jobs]=await Promise.all([api('/api/v1/sessions'+query),api('/api/v1/jobs?limit=10')]); renderSessions(sessions); renderJobs(jobs.items); } catch(error) { byId('upload-status').textContent='加载失败：'+error.message; } }
    async function upload() { const file=byId('archive').files[0]; if(!file){byId('upload-status').textContent='请先选择 ZIP 文件。';return;} byId('upload-status').textContent='正在上传并导入…'; try { const result=await api('/api/v1/ingest/chatgpt',{method:'POST',headers:{'Content-Type':'application/zip'},body:file}); byId('upload-status').textContent='已创建任务 '+result.job_id; await refresh(); } catch(error) { byId('upload-status').textContent='导入失败：'+error.message; } }
    byId('refresh').addEventListener('click',refresh); byId('source').addEventListener('change',refresh); byId('upload').addEventListener('click',upload); refresh();
  </script>
</body>
</html>"""
