'use strict';
const $ = id => document.getElementById(id);
let config, dataset = {posts: []};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => value && !Number.isNaN(Date.parse(value)) ? new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)) : '확인 불가';
const day = value => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
function safeURL(value) { try {const u = new URL(value); if(u.hostname.endsWith('heykorean.com')) u.protocol='https:'; return ['https:','http:'].includes(u.protocol) ? u.href : '#';} catch {return '#';} }
function show(view) {
  $('feed-view').hidden = view !== 'feed'; $('settings-view').hidden = view !== 'settings';
  $('view-name').textContent = view === 'feed' ? 'K-Request' : '검색 설정';
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.view === view));
}
document.addEventListener('click', event => {const b=event.target.closest('[data-view]');if(b) show(b.dataset.view);});
const stateKey = p => 'krequest:lead:' + p.id;
const leadState = p => {const value=localStorage.getItem(stateKey(p));return value || (localStorage.getItem('post:'+p.title+' ↗')==='done'?'done':'new');};
function render() {
  const term = $('search').value.trim().toLowerCase(), tier=$('tier').value, state=$('state').value;
  let posts=dataset.posts.filter(p=>(!tier||p.tier===tier)&&(!state||leadState(p)===state)&&(!term||`${p.title} ${p.excerpt}`.toLowerCase().includes(term))&&(!$('source').value||p.source===$('source').value)&&p.score>=Number($('score').value));
  posts.sort((a,b)=>$('sort').value==='score'?b.score-a.score:(Date.parse(b.source_date)||0)-(Date.parse(a.source_date)||0));
  const total=posts.length;
  if(tier==='priority') posts=posts.slice(0,20);
  $('count').textContent=total>posts.length?`${posts.length} / ${total}`:total;
  $('posts').innerHTML=posts.length?posts.map(p=>`<article class="post"><div><div class="post-meta"><span class="channel">${esc(p.source)}</span><span>${esc(p.category||'기존 수집')}</span></div><h3><a href="${esc(safeURL(p.url))}" target="_blank" rel="noopener noreferrer">${esc(p.title)} ↗</a></h3><p>${esc(p.excerpt)}</p><div class="tags"><span class="tag">${esc(p.decision||'재분류 대기')}</span></div><p class="evidence">요청 단서: <b>${esc(p.evidence?.request||'불명확')}</b> · 배송 장벽: <b>${esc(p.evidence?.barrier||'불명확')}</b></p><div class="post-dates">검색엔진 날짜 ${esc(date(p.source_date))} · 최초 발견 ${esc(date(p.first_seen))}<br>검색 요약에는 댓글이 섞일 수 있습니다. 원문에서 작성일과 미해결 요청을 확인하세요.</div><label class="lead-state">처리 상태 <select data-lead="${esc(p.id)}">${[['new','미확인'],['viewed','확인함'],['replied','답변함'],['done','완료'],['irrelevant','무관함']].map(([v,l])=>`<option value="${v}" ${leadState(p)===v?'selected':''}>${l}</option>`).join('')}</select></label></div><div class="rank ${p.tier==='priority'?'high':''}">단서 점수<strong>${Number(p.score)}</strong>/ 100</div></article>`).join(''):`<div class="empty"><h3>조건에 맞는 후보가 없습니다</h3><p>목표 수량을 채우기 위해 오래되거나 무관한 글을 추가하지 않습니다. 날짜·의도 확인함도 살펴보세요.</p></div>`;
  const fresh=dataset.posts.filter(p=>p.tier==='priority'&&day(p.first_seen)===day(new Date())).length;
  $('quality').textContent=`오늘 새 우선 후보 ${fresh} / 목표 10건 · ${fresh<10?`${10-fresh}건 부족`:'목표 후보 수 도달'} · 우선 목록은 최대 20건. 실제 수요 확인 완료 수는 별도입니다.`;
  $('total').textContent=dataset.posts.filter(p=>p.tier==='priority'&&leadState(p)==='new').length;
  $('today').textContent=fresh;
  $('high').textContent=dataset.posts.filter(p=>['viewed','replied','done'].includes(leadState(p))).length;
}
function renderSettings() {
  $('keywords').value=config.keywords.join('\n');$('exclude').value=config.exclude.join('\n');
  $('freshness').value=config.freshness;$('min-score').value=config.min_score;
  renderSources();
  $('budget').textContent=`하루 검색 최대 ${config.max_queries}개 · 재시도 포함 하루 32회 / 월 1,000회 제한. 7일 이내 우선 후보, 8~30일 후속 확인, 날짜 불명확은 별도 검토. 기간을 자동 확장하지 않습니다.`;
  const match=location.hostname.match(/^([^.]+)\.github\.io$/);
  if(match)$('repo').value=`${match[1]}/${location.pathname.split('/').filter(Boolean)[0]||match[1]+'.github.io'}`;
}
function renderSources() {
 $('sources').innerHTML=config.sources.map((s,i)=>`<fieldset class="source-edit" data-source-row="${i}"><label><input type="checkbox" data-field="enabled" ${s.enabled?'checked':''}> 수집 사용</label><label>채널 이름<input data-field="name" value="${esc(s.name)}" required></label><label>도메인 / 커뮤니티 경로<input data-field="domain" value="${esc(s.domain)}" required placeholder="reddit.com/r/kpophelp"></label><label>분야<input data-field="category" value="${esc(s.category||'기타')}"></label><label>이 채널의 검색식 · 한 줄에 하나<textarea data-field="queries" rows="3">${esc((s.queries||config.keywords).join('\n'))}</textarea></label><button type="button" class="button secondary" data-remove-source="${i}">채널 삭제</button></fieldset>`).join('');
}
function readSources(){return [...document.querySelectorAll('[data-source-row]')].map(row=>{const get=k=>row.querySelector(`[data-field="${k}"]`);return {name:get('name').value.trim(),domain:get('domain').value.trim(),category:get('category').value.trim(),enabled:get('enabled').checked,queries:get('queries').value.split('\n').map(v=>v.trim()).filter(Boolean)};});}
document.addEventListener('change',e=>{if(e.target.matches('[data-lead]')){localStorage.setItem('krequest:lead:'+e.target.dataset.lead,e.target.value);render();}});
document.addEventListener('click',e=>{if(e.target.matches('[data-remove-source]')){config.sources=readSources();config.sources.splice(Number(e.target.dataset.removeSource),1);renderSources();}});
$('add-source').addEventListener('click',()=>{config.sources=readSources();if(config.sources.length>=20)return;config.sources.push({name:'새 채널',domain:'',enabled:true,category:'기타',queries:config.keywords});renderSources();});
async function load() {
  $('refresh').disabled = true;
  try {
    const [pr, cr] = await Promise.all([fetch('data/posts.json', {cache:'no-store'}), fetch('data/config.json', {cache:'no-store'})]);
    if (!pr.ok || !cr.ok) throw new Error('수집 결과 또는 설정 파일을 불러오지 못했습니다.');
    dataset = await pr.json(); const fetchedConfig = await cr.json();
    if (!Array.isArray(dataset.posts)) throw new Error('결과 파일 형식이 올바르지 않습니다.');
    if (!config) {config=fetchedConfig;renderSettings();}
    const messages={not_configured:'연결 대기 · 검색 API 키를 설정하면 자동 수집을 시작합니다.',ok:'수집 완료 · 하루 한 번 새로운 수요를 확인합니다.',partial:'일부 검색에 실패했습니다. 성공한 결과와 기존 결과를 함께 표시합니다.',error:'수집에 실패했습니다. 기존 결과를 유지하고 있습니다. GitHub Actions 실행 기록을 확인하세요.'};
    messages.budget_limited='호출 한도 도달 · 기존 결과를 유지합니다. 다음 수집일에 남은 검색 조합부터 이어갑니다.';
    $('status').textContent = (messages[dataset.status] || '수집 상태를 확인하세요.') + (dataset.last_attempt ? ` 최근 시도 ${date(dataset.last_attempt)} KST · 검색 ${dataset.queries}회` : '') + (dataset.usage?.month ? ` · ${dataset.usage.month} API 호출 ${dataset.usage.monthly}/1,000회` : '');
    if (dataset.last_success && Date.now()-Date.parse(dataset.last_success)>30*3600000) $('status').textContent += ' · 30시간 이상 새 수집이 없습니다. 예약 실행을 확인하세요.';
    $('total').textContent = dataset.posts.length;
    $('today').textContent = dataset.posts.filter(p=>day(p.first_seen)===day(new Date())).length;
    $('high').textContent = dataset.posts.filter(p=>p.score>=75).length;
    $('last').textContent = dataset.last_success ? date(dataset.last_success) : '아직 없음';
    const selected=$('source').value;
    $('source').innerHTML='<option value="">전체 채널</option>'+[...new Set(dataset.posts.map(p=>p.source))].map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
    $('source').value=selected; render();
  } catch(e) { $('status').textContent='불러오기 실패 · '+e.message; } finally {$('refresh').disabled=false;}
}
function editedConfig() {
  if (!config) throw new Error('설정을 먼저 불러와 주세요.');
  const lines=id=>[...new Set($(id).value.split('\n').map(s=>s.trim()).filter(Boolean))];
  const c={...config,keywords:lines('keywords'),exclude:lines('exclude'),freshness:$('freshness').value,min_score:Number($('min-score').value),sources:readSources()};
  if(!c.keywords.length || c.keywords.length>30 || [...c.keywords,...c.exclude].some(s=>s.length>200)) throw new Error('검색어는 1~30개, 각 표현은 200자 이하여야 합니다.');
  if(c.sources.some(s=>!s.name||!/^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\/[a-zA-Z0-9_/-]+)?$/.test(s.domain)||!s.queries.length||s.queries.length>30||s.queries.some(q=>q.length>200))) throw new Error('채널 이름, 도메인과 검색식 1~30개를 확인하세요.');
  if(!c.sources.some(s=>s.enabled)) throw new Error('채널을 하나 이상 선택하세요.');
  if(!Number.isInteger(c.min_score)||c.min_score<0||c.min_score>100) throw new Error('관련도는 0~100 정수로 입력하세요.');
  return c;
}
async function github(path, token, options={}) {
  const res=await fetch(`https://api.github.com/repos/${path}`,{...options,headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${token}`,'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}});
  if(!res.ok) throw new Error(`GitHub ${res.status}: ${res.status===409?'설정이 변경되었습니다. 페이지를 새로고침한 뒤 다시 저장하세요.':res.status===401||res.status===403?'토큰과 저장소 권한을 확인하세요.':'저장소와 main 브랜치, Actions 설정을 확인하세요.'}`);
  return res.status===204?null:res.json();
}
$('settings-form').addEventListener('submit',async event=>{
  event.preventDefault(); const button=event.submitter; button.disabled=true; let saved=false;
  try {
    const c=editedConfig(),repo=$('repo').value.trim(),token=$('token').value.trim();
    if(!/^[\w.-]+\/[\w.-]+$/.test(repo)||!token) throw new Error('저장소 주소(owner/repository)와 GitHub 토큰을 입력하세요.');
    $('save-status').textContent='GitHub에 설정을 저장하고 있습니다…';
    const current=await github(`${repo}/contents/config.json?ref=main`,token);
    const bytes=new TextEncoder().encode(JSON.stringify(c,null,2)+'\n');
    await github(`${repo}/contents/config.json`,token,{method:'PUT',body:JSON.stringify({message:'Update monitoring preferences',content:btoa(Array.from(bytes,b=>String.fromCharCode(b)).join('')),sha:current.sha,branch:'main'})});
    config=c;saved=true;
    $('save-status').textContent='설정을 저장했습니다. 수집 실행을 요청하고 있습니다…';
    // The commit starts the push workflow. No second dispatch is needed.
    $('save-status').textContent='저장 완료 · 설정 변경으로 GitHub Actions 수집이 시작됩니다. 완료 후 결과 새로고침을 눌러주세요.';
    $('token').value='';
  } catch(e) {$('save-status').textContent=(saved?'설정은 저장되었습니다. ':'')+e.message;} finally {button.disabled=false;}
});
$('download').addEventListener('click',()=>{try{const c=editedConfig(),url=URL.createObjectURL(new Blob([JSON.stringify(c,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='config.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('save-status').textContent='내려받은 config.json을 GitHub 저장소 루트에 업로드하면 다음 수집에 반영됩니다.';}catch(e){$('save-status').textContent=e.message;}});
['search','source','score','sort','tier','state'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));
$('refresh').addEventListener('click',load);
load();
