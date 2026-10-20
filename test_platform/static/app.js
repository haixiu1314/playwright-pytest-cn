'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHTML;
const state = {page:'overview', modules:[], runs:[], reports:[], config:null, active:null, token:'', doc:null, caseIndex:-1, steps:[], runId:null, historyTab:'runs', env:null};
const labels = {passed:'通过',failed:'失败',error:'错误',running:'执行中',queued:'准备中',stopping:'停止中',cancelled:'已停止',interrupted:'意外中断',skipped:'全部跳过',no_tests:'无匹配用例',api:'接口测试',web:'Web 测试',workflow:'联动测试'};
const badge = status => `<span class="badge ${e(status)}">${e(labels[status] || status)}</span>`;
const stamp = value => value ? e(value.replace('T',' ').slice(0,19)) : '—';
const button = (text, action, extra='', cls='') => `<button class="button ${cls}" data-action="${action}" ${extra}>${text}</button>`;
function toast(message, error=false) { const target=$('#toast'); target.textContent=message; target.className=error?'error':''; target.style.display='block'; clearTimeout(toast.timer); toast.timer=setTimeout(()=>target.style.display='none',5000); }
async function api(path, method='GET', body) {
  const response = await fetch(path,{method,headers:{'Content-Type':'application/json','X-Platform-Token':state.token},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || '操作失败');
  return data;
}
function modal(title, body, foot='') {
  $('#modal-content').innerHTML=`<div class="modal-head"><h2 id="modal-title">${e(title)}</h2><button class="icon-button" data-action="close" aria-label="关闭">×</button></div><div class="modal-body">${body}</div>${foot?`<div class="modal-foot">${foot}</div>`:''}`;
  if(!$('#dialog').open) $('#dialog').showModal();
}
function closeModal(){ $('#dialog').close(); state.runId=null; }
function heading(title, description, actions=''){return `<div class="page-title"><div><h1>${title}</h1><p>${description}</p></div><div class="actions">${actions}</div></div>`;}
function metric(title,value,note,icon){return `<div class="metric"><div class="metric-label">${title}<span class="metric-icon">${icon}</span></div><b>${e(value)}</b><small>${note}</small></div>`;}
function empty(title, text){return `<div class="empty"><b>${title}</b>${text}</div>`;}
function runRows(runs){return runs.length?`<div class="table-wrap"><table><thead><tr><th>执行任务</th><th>目标环境</th><th>模块 / 范围</th><th>状态</th><th>操作</th></tr></thead><tbody>${runs.map(run=>`<tr><td>${e(run.id)}<small>${stamp(run.created)}</small></td><td>${e(run.payload.environment)}</td><td>${e(run.payload.modules.join('、'))}<small>${e({all:'全部',api:'接口',web:'Web',workflows:'联动'}[run.payload.scope])}</small></td><td>${badge(run.status)}</td><td>${button('查看详情','run-detail',`data-id="${e(run.id)}"`,'small link')}${run.report_id?`<a class="button small link" href="/reports/${encodeURIComponent(run.report_id)}/report.html" target="_blank" rel="noopener">报告 ↗</a>`:''}</td></tr>`).join('')}</tbody></table></div>`:empty('还没有执行记录','添加用例后，点击「开始测试」执行你的第一次测试。');}
function renderOverview(){
  const total=state.modules.reduce((sum,row)=>sum+row.count,0), last=state.reports[0];
  return heading('让每一次回归，更轻松','管理测试用例，连接本地或线上环境，一次验证多个业务模块。',button('管理模块 →','navigate','data-target="modules"'))+
    `<section class="hero"><div><h2>${state.active?'测试任务正在执行':'你的测试工作空间已就绪'}</h2><p>${state.active?'可在执行详情中查看日志，完成后自动生成中文报告。':'环境配置一次，接口与页面用例持续复用。'}</p></div><span class="hero-icon">◈</span></section>`+
    `<div class="cards">${metric('业务模块',new Set(state.modules.map(m=>m.id)).size,'按业务组织，批量执行','▦')}${metric('测试用例',total,'包含 YAML 与现有 Python 用例','✓')}${metric('目标环境',Object.keys(state.config.data.environments).length,'本地 · 测试 · 线上','◎')}${metric('最近通过率',last?.pass_rate || '—','以实际执行的普通用例统计','↗')}</div>`+
    `<section class="panel"><div class="panel-head"><h2>最近执行<span class="inline-count">${state.runs.length} 次任务</span></h2>${button('查看全部 →','navigate','data-target="history"','small link')}</div>${runRows(state.runs.slice(0,5))}</section>`+
    `<div class="grid-2"><section class="panel"><div class="panel-head"><h2>快速准备</h2><span class="muted">01 → 02 → 03</span></div><div class="panel-body help">先配置目标环境，再按业务模块添加接口或页面用例。选中多个模块即可批量回归。${button('配置环境 →','navigate','data-target="environments"','small link')}</div></section><section class="panel"><div class="panel-head"><h2>已有用例继续使用</h2><span class="badge">兼容</span></div><div class="panel-body help">现有 Python 用例会自动出现在模块列表中。新增普通用例可直接填写表单，复杂流程可使用步骤配置。${button('查看使用指南 →','navigate','data-target="help"','small link')}</div></section></div>`;
}
function renderModules(){
  return heading('模块与用例','按业务模块组织接口、页面和联动场景，选择一次，批量回归。',button('公共流程','shared')+button('＋ 新建模块','module-new','','primary'))+
    `<div class="searchbar"><input id="module-search" placeholder="搜索模块名称或标识" aria-label="搜索模块"><span class="muted">${state.modules.length} 个模块来源</span></div><div class="module-grid">${state.modules.map((row,index)=>`<article class="module-card" data-module-search="${e((row.name+' '+row.id).toLowerCase())}"><div class="module-top"><span class="module-symbol">${row.source==='python'?'Py':'▦'}</span><span class="badge">${row.source==='python'?'Python 扩展':row.enabled?'已启用':'已停用'}</span></div><div><h2>${e(row.name)}</h2><p>${e(row.id)}</p></div><div class="actions">${row.source==='python'?'<span class="badge">现有业务用例</span>':`${row.api?badge('api'):''}${row.web?badge('web'):''}${row.workflow?badge('workflow'):''}`}<span class="muted">${row.count} 条用例</span></div><div class="actions">${row.source==='yaml'?button('管理用例','module-edit',`data-index="${index}"`,'small'):button('使用说明','python-help','','small')}${button('运行模块','run-one',`data-module="${e(row.id)}"`,'small link')}</div></article>`).join('') || `<div class="panel">${empty('从第一个业务模块开始','点击「新建模块」，然后在页面中添加接口或 Web 用例。')}</div>`}</div>`;
}
function renderEnvironments(){
  const data=state.config.data, names=Object.keys(data.environments);
  if(!names.includes(state.env)) state.env=data.default_environment || names[0];
  const target=data.environments[state.env];
  return heading('环境配置','每套系统保存一组服务地址，切换模块时无需重复修改域名。',button('＋ 新建环境','env-new'))+
    `<div class="env-list">${names.map(name=>`<button class="env-tab ${name===state.env?'active':''}" data-action="env-select" data-name="${e(name)}">${e(name)}${name===data.default_environment?' · 默认':''}</button>`).join('')}</div>`+
    `<section class="panel"><div class="panel-head"><h2>${e(state.env)} <span class="inline-count">目标服务</span></h2><span class="badge">${target.allow_write?'允许业务写入':'只读保护'}</span></div><form id="env-form"><div class="panel-body"><div class="form-grid"><label class="field wide">Web 页面地址<input name="web_base_url" type="url" value="${e(target.web_base_url)}" placeholder="http://127.0.0.1:3000"><small>填写前端地址；具体页面路径由用例填写。</small></label><label class="field wide">接口服务地址<input name="api_base_url" type="url" value="${e(target.api_base_url)}" placeholder="http://127.0.0.1:8000"><small>填写后端地址；接口用例只需要相对路径。</small></label><label class="field wide">额外允许的来源<textarea name="allowed_origins" placeholder="每行一个，例如 https://cdn.example.com">${e((target.allowed_origins||[]).join('\n'))}</textarea></label></div><div class="check-group"><label class="check"><input type="checkbox" name="allow_write" ${target.allow_write?'checked':''}>允许创建、修改、删除业务数据</label><label class="check"><input type="checkbox" name="verify_tls" ${target.verify_tls!==false?'checked':''}>校验 HTTPS 证书</label><label class="check"><input type="checkbox" name="is_default" ${data.default_environment===state.env?'checked':''}>设为默认环境</label></div><div class="notice warning">production 环境默认仅执行显式只读用例。线上写入还需要在启动测试时明确勾选允许写入。被测项目需提前启动。</div><div class="actions"><button class="button primary" type="submit">保存环境</button>${button('删除此环境','env-delete','','danger')}</div></div></form></section>`;
}
function renderHistory(){
  let content;
  if(state.historyTab==='runs') content=runRows(state.runs);
  else content=state.reports.length?`<div class="table-wrap"><table><thead><tr><th>报告</th><th>环境</th><th>结果</th><th>通过率</th><th>操作</th></tr></thead><tbody>${state.reports.map(report=>`<tr><td>${e(report.id)}<small>${stamp(report.started_at)}</small></td><td>${e(report.environment)}</td><td><span class="badge passed">通过 ${report.summary.passed||0}</span> <span class="badge failed">失败 ${(report.summary.failed||0)+(report.summary.error||0)}</span> <span class="badge skipped">跳过 ${report.summary.skipped||0}</span></td><td>${e(report.pass_rate)}</td><td><a class="button small" href="${e(report.url)}" target="_blank" rel="noopener">打开中文报告 ↗</a></td></tr>`).join('')}</tbody></table></div>`:empty('暂无报告','执行测试后自动生成；已有正式报告也会在此列出。');
  return heading('执行与报告','查看执行进度、失败原因与历史报告，保留每一次验证依据。',button('刷新','refresh'))+`<div class="actions history-tabs">${button('执行任务','history-tab','data-tab="runs"',state.historyTab==='runs'?'primary':'')}${button('全部报告','history-tab','data-tab="reports"',state.historyTab==='reports'?'primary':'')}</div><section class="panel">${content}</section>`;
}
function renderHelp(){return heading('从这里开始','不必为每个普通接口新建 Python 文件，在平台中组织并复用你的业务用例。')+`<section class="panel"><div class="panel-body help"><h3>日常操作</h3><ol><li>在「环境配置」中填写本地或线上项目的前端与后端地址。</li><li>在「模块与用例」中新建业务模块，例如用户、订单、商品。</li><li>点击「管理用例 → 新增用例」，选择接口测试或 Web 测试，填写操作和预期结果。</li><li>点击「开始测试」，勾选一个或多个模块，再选择环境与测试范围。</li><li>在「执行与报告」中查看日志、通过/失败结果和中文报告。</li></ol><h3>接口用例怎么填</h3><p>填写相对路径、请求方法、请求头、请求体和断言。例如 GET <code>/api/items</code>，断言 HTTP 状态码 200，以及业务字段 <code>{"code": 0}</code>。JSON 字段路径支持 <code>data.items[0].id</code>。正确的业务断言须根据你的接口文档填写。</p><h3>Web 用例怎么填</h3><p>依次添加「打开页面 → 填写输入框 → 点击 → 验证文字」等步骤。定位优先选择 test_id、标签、角色。至少包含一个验证步骤；只打开页面不算验证业务通过。</p><h3>公共登录和复杂流程</h3><p>「公共流程」保存共享变量和登录步骤。用例的「高级配置」支持 before、steps、extract、cleanup、use，支持接口与页面联动。凭证建议通过 <code>\u0024{ENV:变量名}</code> 从 .env 读取。高级用法详见项目 docs 目录的《多模块快速测试》。</p><h3>已有 Python 用例</h3><p>平台会自动发现 tests 下已有 Python 用例，支持选择模块执行；平台不直接编辑或删除这些业务代码。复杂认证、上传下载、特殊定位等可以继续由执行引擎扩展。</p><h3>结果与停止</h3><p>无匹配用例、全部跳过不会显示为业务通过。停止任务先请求中断，超时后终止任务进程树；中断可能导致业务数据清理不完整，需要检查目标项目。平台每次执行一个任务，避免共享环境同时写入。</p><h3>启动和关闭</h3><p>双击 <code>start-platform.cmd</code>，浏览器打开 <code>http://127.0.0.1:8765</code>。保留启动窗口；按 Ctrl+C 关闭。平台仅供本机使用，目前未提供多用户账号和远程管理服务。关闭浏览器页签不会停止后台任务。</p></div></section>`;}
function render(){
  const title={overview:'工作台',modules:'模块与用例',environments:'环境配置',history:'执行与报告',help:'使用指南'};
  $('#breadcrumb').textContent=title[state.page];
  $$('nav button').forEach(node=>node.classList.toggle('active',node.dataset.page===state.page));
  $('#main').innerHTML=({overview:renderOverview,modules:renderModules,environments:renderEnvironments,history:renderHistory,help:renderHelp}[state.page])();
}
async function refresh(full=false){
  if(full){const data=await api('/api/bootstrap'); Object.assign(state,{token:data.token,config:data.config,modules:data.modules,active:data.active}); if(data.module_error) toast('用例配置错误：'+data.module_error,true);}
  const [runs,reports]=await Promise.all([api('/api/runs'),api('/api/reports')]); state.runs=runs.runs;state.active=runs.active;state.reports=reports;
  render();
}
function openRun(selected){
  if(state.active){showRun(state.active); return;}
  const unique=[...new Map(state.modules.map(row=>[row.id,row])).values()];
  if(!unique.length){toast('请先新建模块并添加用例',true);return;}
  modal('开始测试',`<form id="run-form"><div class="form-grid"><label class="field">目标环境<select name="environment">${Object.keys(state.config.data.environments).map(name=>`<option ${name===state.config.data.default_environment?'selected':''}>${e(name)}</option>`).join('')}</select></label><label class="field">测试范围<select name="scope"><option value="all">全部测试</option><option value="api">接口测试</option><option value="web">Web 测试</option><option value="workflows">接口与页面联动</option></select></label><label class="field wide">标签筛选（可选）<input name="tags" placeholder="例如 smoke，多个标签用逗号分隔"></label></div><div class="section-label">选择业务模块 <label class="check"><input id="select-all" type="checkbox" ${selected?'':'checked'}>全选 / 取消全选</label></div><div class="module-picks">${unique.map(row=>`<label class="module-pick"><input type="checkbox" name="modules" value="${e(row.id)}" ${!selected||selected===row.id?'checked':''}><span>${e(row.name)}</span><small>${e(row.id)}</small></label>`).join('')}</div><div class="check-group"><label class="check"><input type="checkbox" name="headed">显示浏览器窗口</label><label class="check"><input type="checkbox" name="read_only">仅运行只读用例</label><label class="check"><input type="checkbox" name="allow_write">明确允许线上写入</label></div><div class="notice warning">请确认目标环境。测试将向被测项目发送实际请求；生产环境默认只读，写入需同时在环境中允许。未启用的用例会跳过。</div></form>`,button('取消','close')+'<button form="run-form" class="button primary" type="submit">启动测试 →</button>');
}
async function showRun(id){
  state.runId=id;
  const run=await api('/api/runs/'+encodeURIComponent(id));
  if(state.runId!==id)return;
  const running=['queued','running','stopping'].includes(run.status);
  const sum=run.result?.summary;
  modal('执行详情',`<div class="actions"><strong>${e(run.id)}</strong><span id="run-status">${badge(run.status)}</span></div><p class="muted">${e(run.payload.environment)} · ${e(run.payload.modules.join('、'))} · ${stamp(run.created)}</p><div id="run-summary" class="result-strip">${sum?Object.entries(sum).map(([key,value])=>`<span class="badge ${e(key)}">${e(labels[key]||key)} ${value}</span>`).join(''):''}</div><div id="run-notice" class="muted">${e(run.result?.notice || (running?'任务正在执行，日志自动更新。':run.status==='cancelled'?'任务已停止，请检查被测系统的数据清理情况。':'任务已结束。'))}</div><h3 class="section-label">执行日志</h3><pre id="run-log" class="log">${e(run.log || '正在准备执行……')}</pre><div id="run-error" class="error-text"></div>`,`${running?button('停止任务','run-stop',`data-id="${e(id)}"`,'danger'):''}${run.report_id?`<a class="button primary" target="_blank" rel="noopener" href="/reports/${encodeURIComponent(run.report_id)}/report.html">打开中文报告 ↗</a>`:''}${button('关闭','close')}`);
  state.runId=id;
  $('#run-log').scrollTop=$('#run-log').scrollHeight;
}
async function openModule(file){state.doc=await api('/api/module?file='+encodeURIComponent(file)); renderModuleEditor();}
function captureDocMeta(){const form=$('#module-meta'); if(form){state.doc.data.name=form.elements.name.value;state.doc.data.enabled=form.elements.enabled.checked;}}
function renderModuleEditor(){
  const doc=state.doc, data=doc.data;
  modal('管理用例 · '+(data.name||data.module),`<form id="module-meta"><div class="form-grid"><label class="field">模块名称<input name="name" value="${e(data.name||data.module)}" required></label><label class="field">模块标识<input value="${e(data.module)}" disabled></label></div><div class="check-group"><label class="check"><input type="checkbox" name="enabled" ${data.enabled!==false?'checked':''}>启用此模块</label></div></form><div class="panel-head"><h2>测试用例 <span class="inline-count">${(data.cases||[]).length} 条</span></h2>${button('＋ 新增用例','case-new','','primary small')}</div>${data.cases?.length?`<div class="table-wrap"><table><thead><tr><th>用例名称</th><th>范围</th><th>操作</th></tr></thead><tbody>${data.cases.map((c,i)=>`<tr><td>${e(c.name||c.id)}<small>${e(c.id)}${c.enabled===false?' · 未启用':''}</small></td><td>${badge(c.type || (c.request?'api':(c.steps||[]).some(s=>s.api)?(c.steps||[]).some(s=>s.web)?'workflow':'api':'web'))}</td><td>${button('编辑','case-edit',`data-index="${i}"`,'small link')}${button('复制','case-copy',`data-index="${i}"`,'small link')}${button('删除','case-delete',`data-index="${i}"`,'small link')}</td></tr>`).join('')}</tbody></table></div>`:empty('此模块还没有用例','新增接口或 Web 用例，填写操作与预期结果。')}`,
    button('高级模块配置','module-raw')+button('删除模块','module-delete','','danger')+button('保存模块','module-save','','primary'));
}
async function saveDoc(payload){state.doc=await api('/api/module','PUT',{file:state.doc.file,revision:state.doc.revision,...payload}); await refresh(true);toast('已保存');}
function rawEditor(shared=false){const doc=state.doc; modal(shared?'公共变量与流程':'高级模块配置',`<p class="muted">保存前自动检查语法、断言、变量提取与流程引用。凭证建议通过环境变量读取。</p><textarea id="raw-text" class="code wide-code" aria-label="YAML 配置">${e(doc.text)}</textarea>`,button('取消',shared?'close':'module-back')+button('校验并保存','raw-save',shared?'data-shared="true"':'','primary'));}
function openNewModule(){modal('新建业务模块',`<form id="new-module-form" class="form-grid"><label class="field">模块标识<input name="module" required placeholder="例如 orders"><small>中文、字母、数字、下划线或短横线。</small></label><label class="field">模块名称<input name="name" required placeholder="例如 订单管理"></label></form>`,button('取消','close')+'<button class="button primary" type="submit" form="new-module-form">创建模块</button>');}
function isSimple(c){
  if(c.before?.length||c.cleanup?.length||c.extract||c.variables||c.type==='workflow')return false;
  if(c.request)return !c.request.extract&&!c.request.expect&&!c.request.data&&!c.request.form&&!c.request.params&&!Object.keys(c.expect||{}).some(k=>!['status','json','max_ms'].includes(k));
  return c.steps?.every(s=>s.web&&!s.when_defined&&Object.keys(s).length===1);
}
function openCase(index=-1, forceAdvanced=false){
  captureDocMeta();state.caseIndex=index;
  const current=index>=0?state.doc.data.cases[index]:{id:'',name:'',access:'write',enabled:true,tags:[]};
  state.editOriginal=structuredClone(current);
  const advanced=forceAdvanced || (index>=0&&!isSimple(current));
  if(advanced){modal('高级用例配置',`<p class="muted">使用 JSON 对象编辑完整用例，支持 before、steps、cleanup、extract。格式与 YAML 数据结构一致。</p><textarea class="code wide-code" id="advanced-case" aria-label="完整用例 JSON">${e(JSON.stringify(current,null,2))}</textarea>`,button('返回','module-back')+button('保存用例','case-advanced-save','','primary')); return;}
  const kind=current.request?'api':current.steps?'web':'api';
  state.caseKind=kind;state.steps=structuredClone(current.steps||[{web:{action:'goto',path:'/'}},{web:{action:'assert_title',value:''}}]);
  modal(index<0?'新增测试用例':'编辑测试用例',`<form id="case-form"><div class="form-grid"><label class="field">用例名称<input name="name" value="${e(current.name)}" required placeholder="例如 查询列表成功"></label><label class="field">用例标识<input name="id" value="${e(current.id)}" required placeholder="例如 list_success"></label><label class="field">访问类型<select name="access"><option value="write" ${current.access!=='readonly'?'selected':''}>写入场景（默认）</option><option value="readonly" ${current.access==='readonly'?'selected':''}>只读场景</option></select></label><label class="field">标签<input name="tags" value="${e((current.tags||[]).join(','))}" placeholder="smoke,regression"></label></div><div class="check-group"><label class="check"><input type="checkbox" name="enabled" ${current.enabled!==false?'checked':''}>启用用例</label></div><div class="section-label">测试类型</div><div class="case-switch"><button type="button" class="button ${kind==='api'?'active':''}" data-action="case-kind" data-kind="api">接口测试</button><button type="button" class="button ${kind==='web'?'active':''}" data-action="case-kind" data-kind="web">Web 测试</button></div><div id="api-fields" ${kind==='web'?'hidden':''}><div class="form-grid"><label class="field">请求方法<select name="method">${['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'].map(m=>`<option ${m===(current.request?.method||'GET')?'selected':''}>${m}</option>`).join('')}</select></label><label class="field">接口路径<input name="path" value="${e(current.request?.path||'')}" placeholder="/api/items"></label><label class="field wide">请求头 JSON<textarea class="code" name="headers" placeholder='{"Authorization":"Bearer ..."}'>${e(JSON.stringify(current.request?.headers||{},null,2))}</textarea></label><label class="field wide">请求体 JSON（可留空）<textarea class="code" name="body" placeholder='{"name":"测试数据"}'>${current.request&&'json' in current.request?e(JSON.stringify(current.request.json,null,2)):''}</textarea></label><label class="field">预期 HTTP 状态码<input name="status" type="number" min="100" max="599" value="${e(current.expect?.status??200)}"></label><label class="field">耗时上限（毫秒，可留空）<input name="max_ms" type="number" min="1" value="${e(current.expect?.max_ms??'')}"></label><label class="field wide">业务字段断言 JSON<textarea name="expected" class="code" placeholder='{"code":0,"data.id":1}'>${e(JSON.stringify(current.expect?.json||{},null,2))}</textarea><small>键为响应 JSON 路径，值为预期结果；按实际业务填写。</small></label></div></div><div id="web-fields" ${kind==='api'?'hidden':''}><p class="muted">按顺序组合页面操作，至少添加一个验证步骤。</p><div id="step-list"></div>${button('＋ 添加步骤','step-add','','small')}</div></form>`,button('高级配置','case-to-advanced')+button('返回模块','module-back')+'<button class="button primary" form="case-form" type="submit">保存用例</button>');
  renderSteps();
}
const actions={goto:'打开页面',fill:'填写输入框',click:'点击元素',check:'勾选',uncheck:'取消勾选',select:'选择下拉选项',press:'按键',assert_text:'验证文字',assert_title:'验证标题',assert_url:'验证地址',assert_visible:'验证可见',assert_hidden:'验证隐藏',assert_value:'验证输入值'};
function renderSteps(){
  $('#step-list').innerHTML=state.steps.map((entry,i)=>{const s=entry.web;const target=['test_id','label','role','selector','text'].find(k=>k in s)||'test_id';return `<div class="step-row" data-step="${i}"><span class="step-number">${i+1}</span><select data-step-field="action" aria-label="步骤${i+1}动作">${Object.entries(actions).map(([key,name])=>`<option value="${key}" ${key===s.action?'selected':''}>${name}</option>`).join('')}</select><select data-step-field="target-kind" aria-label="步骤${i+1}定位方式">${[['test_id','test_id'],['label','标签'],['role','角色'],['selector','CSS'],['text','文字']].map(([key,name])=>`<option value="${key}" ${key===target?'selected':''}>${name}</option>`).join('')}</select><input data-step-field="target" aria-label="步骤${i+1}定位内容" placeholder="定位内容；角色可填 button|保存" value="${e(s[target]===undefined?'':target==='role'?s.role+(s.name?'|'+s.name:''):s[target])}"><input data-step-field="value" aria-label="步骤${i+1}值" placeholder="路径 / 输入值 / 预期文字" value="${e(s.path??s.value??s.key??(s.action==='assert_text'?s.text:'')??'')}"><div class="step-actions">${button('↑','step-up',`data-index="${i}"`,'small')}${button('×','step-remove',`data-index="${i}"`,'small')}</div></div>`;}).join('');
}
function captureSteps(){
  state.steps=$$('.step-row').map(row=>{const val=key=>$(`[data-step-field="${key}"]`,row).value, action=val('action'), s={action};
    if(['goto','assert_url'].includes(action))s.path=val('value');
    else if(action==='assert_text')s.text=val('value');
    else if(action==='assert_title')s.value=val('value');
    else {const key=val('target-kind'); if(key==='role'){const [role,...name]=val('target').split('|');s.role=role;if(name.length)s.name=name.join('|');}else s[key]=val('target');if(['fill','select','assert_value'].includes(action))s.value=val('value');if(action==='press')s.key=val('value');}
    return {web:s};
  });
}
function jsonField(form,name,empty={}){const value=form.elements[name].value.trim();if(!value)return empty;let result;try{result=JSON.parse(value);}catch{throw new Error(`${{headers:'请求头',body:'请求体',expected:'业务字段断言'}[name]||name}不是有效的 JSON`);}if(name!=='body'&&(!result||typeof result!=='object'||Array.isArray(result)))throw new Error('请求头与业务字段断言应填写 JSON 对象，例如 {"code": 0}');return result;}
function buildCase(){
  const form=$('#case-form'),v=name=>form.elements[name].value.trim();
  const c={...state.editOriginal,id:v('id'),name:v('name'),access:v('access'),tags:v('tags').replaceAll('，',',').split(',').map(s=>s.trim()).filter(Boolean),enabled:form.elements.enabled.checked};
  delete c.type;delete c.request;delete c.expect;delete c.steps;
  if(state.caseKind==='api'){
    if(!v('path'))throw new Error('请填写接口路径');
    c.request={method:v('method'),path:v('path'),headers:jsonField(form,'headers')};
    if(v('body'))c.request.json=jsonField(form,'body');
    c.expect={};if(v('status'))c.expect.status=Number(v('status'));const fields=jsonField(form,'expected');if(Object.keys(fields).length)c.expect.json=fields;if(v('max_ms'))c.expect.max_ms=Number(v('max_ms'));
  }else {captureSteps();c.steps=state.steps;}
  return c;
}
async function saveCase(c){
  if(!c||typeof c!=='object'||Array.isArray(c))throw new Error('用例必须为 JSON 对象');
  const data=structuredClone(state.doc.data);data.cases=data.cases||[];
  if(data.cases.some((row,i)=>row.id===c.id&&i!==state.caseIndex))throw new Error('用例标识重复，请换一个');
  if(state.caseIndex<0)data.cases.push(c);else data.cases[state.caseIndex]=c;
  await saveDoc({data});renderModuleEditor();
}
document.addEventListener('input',event=>{if(event.target.id==='module-search'){$$('[data-module-search]').forEach(card=>card.hidden=!card.dataset.moduleSearch.includes(event.target.value.toLowerCase()));}});
document.addEventListener('change',event=>{if(event.target.id==='select-all')$$('input[name="modules"]').forEach(node=>node.checked=event.target.checked);});
document.addEventListener('click',async event=>{
  const node=event.target.closest('[data-action],[data-page]');if(!node)return;
  event.preventDefault();const a=node.dataset.action;
  try{
    if(node.dataset.page){state.page=node.dataset.page;render();return;}
    if(a==='navigate'){state.page=node.dataset.target;render();}
    else if(a==='close')closeModal();
    else if(a==='refresh'){await refresh(true);toast('已刷新');}
    else if(a==='run-open')openRun();
    else if(a==='run-one')openRun(node.dataset.module);
    else if(a==='run-detail')await showRun(node.dataset.id);
    else if(a==='run-stop'){if(confirm('停止后可能需要检查业务数据清理情况。确定停止此任务？')){await api('/api/runs/'+node.dataset.id+'/stop','POST',{});toast('正在停止');await showRun(node.dataset.id);}}
    else if(a==='history-tab'){state.historyTab=node.dataset.tab;render();}
    else if(a==='module-new')openNewModule();
    else if(a==='module-edit')await openModule(state.modules[Number(node.dataset.index)].file);
    else if(a==='module-back')renderModuleEditor();
    else if(a==='module-save'){captureDocMeta();await saveDoc({data:state.doc.data});renderModuleEditor();}
    else if(a==='module-raw')rawEditor();
    else if(a==='shared'){state.doc=await api('/api/module?file=_shared.yaml');rawEditor(true);}
    else if(a==='raw-save'){await saveDoc({text:$('#raw-text').value});if(node.dataset.shared)closeModal();else renderModuleEditor();}
    else if(a==='module-delete'){if(confirm('确定删除此 YAML 模块及其中用例？现有 Python 用例不会被删除。')){await api('/api/module','DELETE',{file:state.doc.file,revision:state.doc.revision});closeModal();await refresh(true);toast('已删除模块');}}
    else if(a==='case-new')openCase();
    else if(a==='case-edit')openCase(Number(node.dataset.index));
    else if(a==='case-copy'){captureDocMeta();const c=structuredClone(state.doc.data.cases[Number(node.dataset.index)]);c.id+='_copy_'+Date.now().toString().slice(-5);c.name=(c.name||c.id)+'（副本）';state.caseIndex=-1;await saveCase(c);}
    else if(a==='case-delete'){if(confirm('确定删除这条用例？')){captureDocMeta();const data=structuredClone(state.doc.data);data.cases.splice(Number(node.dataset.index),1);await saveDoc({data});renderModuleEditor();}}
    else if(a==='case-kind'){state.caseKind=node.dataset.kind;$('#api-fields').hidden=state.caseKind!=='api';$('#web-fields').hidden=state.caseKind!=='web';$$('.case-switch button').forEach(b=>b.classList.toggle('active',b===node));}
    else if(a==='case-to-advanced'){const c=buildCase();modal('高级用例配置',`<p class="muted">编辑完整用例 JSON；支持公共流程、变量提取与清理步骤。</p><textarea id="advanced-case" class="code wide-code" aria-label="完整用例 JSON">${e(JSON.stringify(c,null,2))}</textarea>`,button('返回模块','module-back')+button('保存用例','case-advanced-save','','primary'));}
    else if(a==='case-advanced-save'){let data;try{data=JSON.parse($('#advanced-case').value);}catch{throw new Error('完整用例不是有效的 JSON');}await saveCase(data);}
    else if(a==='step-add'){captureSteps();state.steps.push({web:{action:'assert_text',text:''}});renderSteps();}
    else if(a==='step-remove'){captureSteps();state.steps.splice(Number(node.dataset.index),1);renderSteps();}
    else if(a==='step-up'){captureSteps();const i=Number(node.dataset.index);if(i>0)[state.steps[i-1],state.steps[i]]=[state.steps[i],state.steps[i-1]];renderSteps();}
    else if(a==='python-help')toast('此模块来自 tests 下已有 Python 代码，可直接选择执行；复杂业务代码在原文件维护。');
    else if(a==='env-select'){state.env=node.dataset.name;render();}
    else if(a==='env-new'){modal('新建目标环境',`<form id="new-env-form"><label class="field">环境名称<input name="name" required placeholder="例如 demo 或 project_b"></label><div class="notice">创建后填写前端与后端地址，再保存环境。</div></form>`,button('取消','close')+'<button form="new-env-form" type="submit" class="button primary">添加环境</button>');}
    else if(a==='env-delete'){if(Object.keys(state.config.data.environments).length===1)throw new Error('至少保留一个环境');if(confirm(`确定删除环境 ${state.env}？`)){const environments=structuredClone(state.config.data.environments);delete environments[state.env];state.config=await api('/api/config','PUT',{revision:state.config.revision,environments,default_environment:state.config.data.default_environment===state.env?Object.keys(environments)[0]:state.config.data.default_environment});state.env=null;render();toast('已删除环境');}}
  }catch(error){toast(error.message,true);}
});
document.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target;const formId=form.getAttribute('id');const submit=$(`button[form="${formId}"][type="submit"]`)||$('button[type="submit"]',form);if(submit)submit.disabled=true;
  try{
    if(formId==='run-form'){
      const value={environment:form.elements.environment.value,scope:form.elements.scope.value,modules:$$('input[name="modules"]:checked',form).map(n=>n.value),tags:form.elements.tags.value,...Object.fromEntries(['headed','read_only','allow_write'].map(k=>[k,form.elements[k].checked]))};
      const run=await api('/api/runs','POST',value);state.active=run.id;await refresh();await showRun(run.id);
    }else if(formId==='new-module-form'){
      const id=form.elements.module.value.trim(),name=form.elements.name.value.trim();
      const doc=await api('/api/module','PUT',{file:id+'.yaml',data:{module:id,name,enabled:true,cases:[]}});state.doc=doc;await refresh(true);renderModuleEditor();toast('模块已创建，请添加用例');
    }else if(formId==='case-form')await saveCase(buildCase());
    else if(formId==='env-form'){
      const environments=structuredClone(state.config.data.environments),target={...environments[state.env]};
      ['web_base_url','api_base_url'].forEach(k=>target[k]=form.elements[k].value.trim());target.allowed_origins=form.elements.allowed_origins.value.split('\n').map(x=>x.trim()).filter(Boolean);target.allow_write=form.elements.allow_write.checked;target.verify_tls=form.elements.verify_tls.checked;environments[state.env]=target;
      state.config=await api('/api/config','PUT',{revision:state.config.revision,environments,default_environment:form.elements.is_default.checked?state.env:state.config.data.default_environment});render();toast('环境已保存');
    }else if(formId==='new-env-form'){
      const name=form.elements.name.value.trim();if(name in state.config.data.environments)throw new Error('同名环境已存在');const environments={...state.config.data.environments,[name]:{web_base_url:'',api_base_url:'',allow_write:false,verify_tls:true,allowed_origins:[]}};
      state.config=await api('/api/config','PUT',{revision:state.config.revision,environments,default_environment:state.config.data.default_environment});state.env=name;closeModal();render();toast('环境已添加，请填写服务地址');
    }
  }catch(error){toast(error.message,true);}finally{if(submit)submit.disabled=false;}
});
let polling=false;
setInterval(async()=>{
  if(polling||!state.token)return;polling=true;
  try{
    const data=await api('/api/runs');const changed=JSON.stringify(state.runs)!==JSON.stringify(data.runs);state.runs=data.runs;state.active=data.active;
    if(changed){state.reports=await api('/api/reports');if(['overview','history'].includes(state.page))render();}
    if(state.runId&&$('#dialog').open){
      const run=await api('/api/runs/'+state.runId);const log=$('#run-log');
      if(log){const atBottom=log.scrollHeight-log.scrollTop-log.clientHeight<60;log.textContent=run.log||'正在准备执行……';if(atBottom)log.scrollTop=log.scrollHeight;$('#run-status').innerHTML=badge(run.status);if(!['queued','running','stopping'].includes(run.status)&&!$('#modal-content').dataset.finished){const id=state.runId;await showRun(id);$('#modal-content').dataset.finished='true';}}
    }
  }catch(error){if(state.runId&&$('#run-error'))$('#run-error').textContent=error.message;}
  finally{polling=false;}
},1800);
$('#dialog').addEventListener('close',()=>{state.runId=null;delete $('#modal-content').dataset.finished;});
refresh(true).catch(error=>{$('#main').innerHTML=`<div class="panel">${empty('无法加载工作空间',e(error.message))}</div>`;toast(error.message,true);});
