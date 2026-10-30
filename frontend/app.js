/* Shared ASIC Tracker UI; persistence and authority are provided by the Python API. */
(async () => {
  'use strict';
  const T = window.Tracker;
  const $ = s => document.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = value => Number(value || 0).toLocaleString('en-US');
  const usd = value => value == null ? 'Price missing' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:0,maximumFractionDigits:2}).format(value);
  const tip=(text,explanation)=>`<span class="metric" tabindex="0" data-tip="${esc(explanation)}" aria-label="${esc(text)}. ${esc(explanation)}">${esc(text)}</span>`;
  const metric=(value,explanation,format='number')=>tip(format==='usd'?usd(value):n(value),explanation);
  const date = value => value ? new Date(value.slice(0,10)+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}) : '—';
  const shortDate = value => value ? new Date(value.slice(0,10)+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'}) : '—';
  const id = prefix => prefix + '-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)+Math.random().toString(36).slice(2));
  const icons = {
    chip:'M8 5V2m8 3V2M8 22v-3m8 3v-3M5 8H2m3 8H2m20-8h-3m3 8h-3M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z M9 9h6v6H9Z',
    grid:'M3 3h7v7H3Zm11 0h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z',
    folder:'M3 7V5a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
    events:'M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4',
    chart:'M4 3v17h17M8 15l4-5 4 2 5-7',
    database:'M20 5c0 2-4 3-8 3S4 7 4 5s4-3 8-3 8 1 8 3ZM4 5v14c0 2 4 3 8 3s8-1 8-3V5M4 12c0 2 4 3 8 3s8-1 8-3',
    search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
    chevron:'m9 5 7 7-7 7',plus:'M12 5v14M5 12h14',download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    calendar:'M4 5h16v16H4ZM8 2v6m8-6v6M4 10h16',help:'M9.2 9a3 3 0 1 1 5.3 2c-1.3.7-2.5 1.4-2.5 3m0 3v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    arrow:'M4 12h16m-5-5 5 5-5 5',check:'m5 12 4 4L19 6',close:'m6 6 12 12M6 18 18 6',edit:'m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14l-1 7Z',
    trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',warn:'m12 3 10 18H2L12 3Zm0 6v5m0 3v.1',
    truck:'M2 5h12v12H2ZM14 9h4l4 4v4h-8M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm12 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
    box:'m3 7 9-5 9 5v10l-9 5-9-5V7Zm0 0 9 5 9-5m-9 5v10M7 4.8l9 5',clock:'M12 7v5l3 2m7-2a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    refresh:'M20 8a8 8 0 0 0-14-4L3 7m0-5v5h5M4 16a8 8 0 0 0 14 4l3-3m0 5v-5h-5',info:'M12 11v6m0-10v.1m10 4.9a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    target:'M12 8a4 4 0 1 1-4 4m14 0a10 10 0 1 1-10-10M12 12l9-9m-6 0h6v6',shield:'m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Zm-4 10 3 3 5-6',
    upload:'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',user:'M19 21v-3a7 7 0 0 0-14 0v3m11-14a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'
  };
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[name] || icons.box}"/></svg>`;
  const typeIcon = type => ({expected_ship:'box',request:'target',expected_fulfilment:'calendar',actual_ship:'truck',actual_fulfilment:'check'}[type]);
  const typeTone = type => ({expected_ship:'gray',request:'blue',expected_fulfilment:'',actual_ship:'amber',actual_fulfilment:''}[type]);
  const pill = (text,tone='') => `<span class="pill ${tone}">${esc(text)}</span>`;
  let state;
  $('#app').innerHTML='<div class="shared-loading" role="status">Loading shared workspace…</div>';
  try{state=await ApiStore.bootstrap();ApiStore.installReadModels();}
  catch(error){ApiStore.renderBootError(error);return;}
  state.projectFamilies=state.projectFamilies||[];state.forecastVersions=state.forecastVersions||[];
  const canEdit=()=>['editor','admin'].includes(ApiStore.user?.role);
  const isAdmin=()=>ApiStore.user?.role==='admin';
  function isWriteAction(action){return /^(new-|edit-|delete-|confirm-delete-|transfer-|allocate-|receive-|record-)/.test(action)||['create-snapshot','confirm-reset','confirm-import','confirm-restore','reset-demo','import-backup','restore-snapshot'].includes(action);}
  function canAction(action){
    if(!isWriteAction(action))return true;
    if(!canEdit()||ApiStore.needsReload)return false;
    if(/^(delete-|confirm-delete-)/.test(action)||['new-project-family','edit-project-family','confirm-reset','confirm-import','confirm-restore','reset-demo','import-backup','restore-snapshot'].includes(action))return isAdmin();
    return true;
  }
  function renderConnection(){
    const target=$('#connection-status');if(!target)return;
    target.classList.toggle('problem',ApiStore.needsReload||!!ApiStore.lastError);
    target.innerHTML=`<span>${ApiStore.busy?'Updating the shared workspace…':ApiStore.needsReload?'A newer or unconfirmed server revision must be loaded before saving.':ApiStore.lastError?esc(ApiStore.lastError):'Shared revision '+n(ApiStore.revision)}</span>${ApiStore.needsReload?btn('Load latest','reload-workspace','refresh'):btn('Refresh data','reload-workspace','refresh')}${ApiStore.hasDraft?btn('Download unsaved draft','download-unsaved-draft','download'):''}<span class="identity">${esc(ApiStore.user.display_name||ApiStore.user.subject)} · ${esc(ApiStore.user.role)}${ApiStore.user.auth_mode==='development'?' · <span class="environment">Development authentication</span>':''}</span>`;
    const drawer=$('#drawer'),existing=drawer?.querySelector('.shared-draft-actions');
    if(ApiStore.needsReload&&drawer?.open){
      if(!existing){const notice=document.createElement('div');notice.className='shared-draft-actions notice';notice.innerHTML='<p>Load the latest workspace before saving. Download this draft to keep a copy. Loading latest closes this form.</p><div>'+btn('Download unsaved draft','download-unsaved-draft','download')+btn('Load latest','reload-workspace','refresh')+'</div>';drawer.querySelector('.drawer-head')?.after(notice);}
    }else existing?.remove();
  }
  function applyPermissions(){
    document.querySelectorAll('button[data-action]').forEach(button=>{
      if(!button.hasAttribute('data-base-disabled'))button.dataset.baseDisabled=button.disabled?'true':'false';
      const restricted=!canAction(button.dataset.action);
      button.dataset.restricted=String(restricted);button.disabled=button.dataset.baseDisabled==='true'||restricted||ApiStore.busy;
      if(restricted)button.title=ApiStore.needsReload?'Load the latest server revision before changing records.':'Your role does not permit this action.';
    });
    document.querySelectorAll('form button[type="submit"]').forEach(button=>{button.disabled=!canEdit()||ApiStore.busy||ApiStore.needsReload;});
  }
  const source = () => state.source || null;
  const referenceDate = () => T.todayPacific();
  const defaultCutoff = () => {const d=new Date(referenceDate()+'T12:00:00Z');return new Date(Date.UTC(d.getUTCFullYear(),Math.ceil((d.getUTCMonth()+1)/3)*3,0,12)).toISOString().slice(0,10);};
  const phases = () => [...new Set([...state.projects.map(p=>p.phase),...state.events.map(e=>e.phase),'Prototype','Pilot','Production','Buffer'].filter(Boolean))].sort();
  const eventPhase = e => e.phase || lookupP(e.projectId)?.phase || 'Unspecified';
  const eventMPN = e => e.mpn || lookupA(e.asicId)?.mpns[0] || 'Unspecified';
  const subtypeOptions = () => [...new Set([...state.asics.map(a=>a.subtype),'Switch ASIC','Network processor','Security ASIC','Controller','Timing ASIC','Memory controller','Other'].filter(Boolean))].sort();
  const ui = {page:['overview','asics','projects','business-entities','funding-sources','project-families','requests','allocations','supply','events','forecasts','reports','recovery'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'asics',asicId:'',parentId:'',projectId:'',phase:'',cutoff:defaultCutoff(),query:'',type:'',report:'shortage',quarter:T.quarterOf(defaultCutoff()),funding:'',entity:'',pivotRow:'phase',pivotCol:'asic',pivotMeasure:'demand',projectEntityId:'',projectAsicId:'',projectEpm:'',projectPlatform:'',requestAsicId:'',requestProjectId:'',requestStatus:'',allocationAsicId:'',allocationProjectId:'',supplyAsicId:'',forecastTab:'summary',forecastMode:'monthly',forecastAsicId:'',forecastProjectId:'',forecastCategory:'',forecastPhase:'',forecastMeasure:'request',forecastStart:'',forecastEnd:'',forecastYear:'',forecastVersionIds:[],forecastIncludeLive:true};
  let modalType = 'request', editing = null, lastExport = null, requestCreatedAt = '', allocationCreatedAt = '', allocationDraftId = '';
  const names = {overview:'Overview',asics:'ASIC library',projects:'Projects',requests:'Requests',allocations:'Allocations',supply:'Supply',events:'Event ledger',forecasts:'Forecasts',reports:'Reports',recovery:'Data & recovery','business-entities':'Business entities','funding-sources':'Funding sources','project-families':'Project families'};
  const lookupA = key => state.asics.find(x=>x.id===key);
  const lookupP = key => state.projects.find(x=>x.id===key);
  const filters = () => ({asicId:ui.asicId,parentId:ui.parentId,projectId:ui.projectId,phase:ui.phase,cutoff:ui.cutoff});
  const scopedSupply = () => Boolean(ui.parentId || ui.projectId || ui.phase);
  const options = (items,selected,placeholder) => `${placeholder !== undefined ? `<option value="">${esc(placeholder)}</option>` : ''}${items.map(x=>{const value=typeof x==='string'?x:x.id;return `<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(typeof x==='string'?x:x.name)}</option>`;}).join('')}`;
  const parentOptions = () => state.projects.filter(p=>!p.parentId);
  const btn = (label,action,ic='',extra='',cls='') => `<button type="button" class="btn ${cls}" data-action="${action}" ${extra}>${ic?icon(ic):''}${label}</button>`;
  const textBtn = (label,action,extra='') => `<button class="text-btn" data-action="${action}" ${extra}>${label}${icon('arrow')}</button>`;
  const empty = label => `<div class="empty">${icon('search')}${esc(label)}</div>`;
  function table(headers,rows,footer='') {
    return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th ${String(h).startsWith('#')?'class="num"':''}>${esc(String(h).replace(/^#/,''))}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>${rows.length?'':empty('No records match these filters.')}${footer?`<div class="table-footer">${footer}</div>`:''}`;
  }
  function shell() {
    $('#app').innerHTML=`<div class="layout"><aside class="sidebar"><div class="brand"><div class="brand-mark">${icon('chip')}</div>ASIC Tracker</div><p class="workspace-label">WORKSPACE</p><nav class="nav" aria-label="Main navigation">${[['overview','grid'],['asics','chip'],['projects','folder'],['requests','target'],['supply','box'],['allocations','calendar'],['business-entities','grid'],['funding-sources','database'],['project-families','folder'],['events','events'],['forecasts','chart'],['reports','chart']].map(([page,ic])=>`<button data-action="navigate" data-page="${page}" ${ui.page===page?'class="active" aria-current="page"':''}>${icon(ic)}${names[page]}${page==='asics'?`<span class="count">${state.asics.length}</span>`:''}</button>`).join('')}</nav><div class="nav-divider"></div><nav class="nav" aria-label="Administration"><button data-action="navigate" data-page="recovery" ${ui.page==='recovery'?'class="active" aria-current="page"':''}>${icon('database')}Data & recovery</button></nav><div class="sidebar-bottom"><div class="local-card"><div class="local-title"><i class="dot"></i>Shared MongoDB</div></div></div></aside><div class="main-wrap"><header class="topbar"><div class="breadcrumb">Operations workspace ${icon('chevron')}<strong id="crumb">${names[ui.page]}</strong></div><div class="top-actions"><div class="search-wrap"><label class="global-search">${icon('search')}<input id="global-search" aria-label="Search workspace" placeholder="Search workspace…" autocomplete="off"><span class="keyhint">⌘ K</span></label><div id="search-results" class="search-results hidden"></div></div><span class="top-divider"></span><span class="top-date">${icon('calendar')} &nbsp;${date(referenceDate())}</span><button class="icon-button" aria-label="Workspace guide" data-action="guide">${icon('help')}</button></div></header><div id="connection-status" class="connection-status" role="status"></div><main id="content" class="content"></main></div></div>`;
    renderPage();
  }
  function title(eyebrow,heading,sub,actions='') {
    return `<div class="page-title-row"><div><p class="eyebrow">${eyebrow}</p><h1>${heading}</h1><p class="subtitle">${sub}</p></div><div class="page-title-actions">${actions || '<span class="demo-badge"><i class="dot"></i>'+ (source()?'IMPORTED DATA':'SHARED WORKSPACE')+'</span>'}</div></div>`;
  }
  function reportScope(){return 'Through '+date(ui.cutoff)+(ui.asicId?'; ASIC '+lookupA(ui.asicId)?.name:'; all ASICs')+(ui.projectId?'; project '+lookupP(ui.projectId)?.name:'; all projects')+(ui.parentId?'; parent '+lookupP(ui.parentId)?.name:'')+(ui.phase?'; phase '+ui.phase:'');}
  function filterBar(full=false,financial=false){
    const supply=ui.report==='supply',advanced=[!supply&&ui.parentId,!supply&&ui.phase,financial&&ui.funding,financial&&ui.entity].filter(Boolean).length;
    const quarters=[...new Set([T.quarterOf(defaultCutoff()),...state.events.map(e=>T.quarterOf(e.date))])].sort().concat('all');
    return `<div class="toolbar report-filter-bar"><div class="control"><select aria-label="Filter ASIC" data-filter="asicId">${options(state.asics,ui.asicId,'All ASICs')}</select></div>${!supply?'<div class="control"><select aria-label="Filter project" data-filter="projectId">'+options(state.projects,ui.projectId,'All projects')+'</select></div>':''}<div class="control"><label for="cutoff">Through</label><input id="cutoff" aria-label="Report cutoff date" type="date" data-filter="cutoff" value="${ui.cutoff}" min="0001-01-01" max="9999-12-31"></div>${financial?'<div class="control"><select aria-label="Financial quarter" data-filter="quarter">'+options(quarters.map(q=>({id:q,name:q==='all'?'All quarters':q})),ui.quarter)+'</select></div>':''}${[ui.asicId,ui.projectId,ui.parentId,ui.phase,financial&&ui.funding,financial&&ui.entity].some(Boolean)?'<button class="filter-reset" data-action="clear-filters">Clear filters</button>':''}</div>${!supply?`<details class="request-basis report-more-filters" ${advanced?'open':''}><summary>${icon('search')}More filters${advanced?' · '+metric(advanced,'Number of active parent-project, engineering-phase, and financial entity filters.'):''}</summary><div class="toolbar"><div class="control"><select aria-label="Filter parent project" data-filter="parentId">${options(parentOptions(),ui.parentId,'All parent projects')}</select></div><div class="control"><select aria-label="Filter engineering phase" data-filter="phase">${options(phases(),ui.phase,'All engineering phases')}</select></div>${financial?'<div class="control"><select aria-label="Filter funding source" data-filter="funding">'+options(state.fundingSources,ui.funding,'All funding sources')+'</select></div><div class="control"><select aria-label="Filter business entity" data-filter="entity">'+options(state.businessEntities,ui.entity,'All business entities')+'</select></div>':''}</div></details>`:''}`;
  }
  function kpi(label,value,unit,caption,ic,warning=false) {return `<article class="kpi ${warning?'warning':''}"><div class="kpi-top"><span class="kpi-label">${label}</span><span class="kpi-icon">${icon(ic)}</span></div><div class="kpi-value">${value}<small>${unit}</small></div><div class="kpi-bottom"><i class="tiny-dot"></i>${caption}</div></article>`;}
  function reportChart() {
    const weeks=T.weekly(state,{...filters()}).slice(-9);
    if (!weeks.length) return empty('Select a later date to see the planning timeline.');
    const series=['demand','allocation','supply'];
    const points=weeks.map(w=>{const end=new Date(w.week+'T12:00:00Z');end.setUTCDate(end.getUTCDate()+6);return T.stats(state,{...filters(),cutoff:[end.toISOString().slice(0,10),ui.cutoff].sort()[0]});});
    const max=Math.max(100,...points.flatMap(p=>series.filter(s=>!scopedSupply()||s!=='supply').map(s=>p[s]))), upper=Math.ceil(max/5000)*5000;
    const W=620,H=205,left=43,right=16,top=12,bottom=30;
    const x=i=>left+i*(W-left-right)/Math.max(1,weeks.length-1),y=v=>H-bottom-v/upper*(H-top-bottom);
    const colors={demand:'#02c8ff',allocation:'#0a60ff',supply:'#8b9db7'};
    const path=key=>points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p[key]).toFixed(1)).join(' ');
    return `<svg class="line-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative demand, allocation and unallocated supply by week"><defs><linearGradient id="chartfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0a60ff" stop-opacity=".14"/><stop offset="1" stop-color="#0a60ff" stop-opacity="0"/></linearGradient></defs>${[0,1,2,3].map(i=>{const val=upper*i/3;return `<line x1="${left}" y1="${y(val)}" x2="${W-right}" y2="${y(val)}" stroke="#e7edf5" stroke-dasharray="3 4"/><text x="${left-10}" y="${y(val)+3}" text-anchor="end">${val===0?'0':(val/1000).toFixed(val%1000?1:0)+'k'}</text>`;}).join('')}<path d="${path('allocation')} L${x(weeks.length-1)},${H-bottom} L${left},${H-bottom}Z" fill="url(#chartfill)"/>${series.filter(s=>s!=='supply'||!scopedSupply()).map(s=>`<path d="${path(s)}" fill="none" stroke="${colors[s]}" stroke-width="2.1" ${s==='supply'?'stroke-dasharray="4 5"':''} stroke-linejoin="round"/>${points.map((p,i)=>`<circle cx="${x(i)}" cy="${y(p[s])}" r="3" fill="white" stroke="${colors[s]}" stroke-width="1.8"><title>${weeks[i].label} · ${s}: ${n(p[s])}</title></circle>`).join('')}`).join('')}${weeks.map((w,i)=>`<text x="${x(i)}" y="${H-8}" text-anchor="middle">${esc(w.label)}</text>`).join('')}</svg>`;
  }
  function completeness() {
    const issues=[];
    state.asics.forEach(a=>{if(T.priceAt(a,ui.cutoff)===null)issues.push({text:a.historicalPriceUnknown?`${a.name} has no verified historical price`:`${a.name} is missing a unit price`,hint:a.historicalPriceUnknown?'Current catalog price is not used for past events':'Financial values are incomplete',action:'edit-asic',id:a.id});if(!a.mpns.length)issues.push({text:`${a.name} has no MPN`,hint:'Primary MPN pivot uses “Unspecified”',action:'edit-asic',id:a.id});});
    return issues;
  }
  function sourceBanner(){return '';}
  function renderOverview(){
    const asOf=referenceDate(),inventory=T.supplySummary(state,{asOf,asicId:ui.asicId}),requests=T.requestAvailability(state,{asOf}).filter(r=>!ui.asicId||r.asicId===ui.asicId);
    const onHand=inventory.reduce((v,r)=>v+r.onHandQty,0),open=requests.reduce((v,r)=>v+r.remainingQty,0),risk=requests.filter(r=>['late','shortfall'].includes(r.status)).length;
    const summary=(label,value,explanation,tone='')=>`<div class="summary-item ${tone}"><span>${label}</span><strong>${metric(value,explanation)}</strong></div>`;
    const rows=state.asics.filter(a=>!ui.asicId||a.id===ui.asicId).map(a=>{
      const stock=inventory.find(r=>r.asicId===a.id)||{receivedQty:0,shippedQty:0,onHandQty:0,reservedQty:0,freeQty:0},demand=requests.filter(r=>r.asicId===a.id),openRows=demand.filter(r=>r.remainingQty>0),units=openRows.reduce((v,r)=>v+r.remainingQty,0),atRisk=openRows.filter(r=>['late','shortfall'].includes(r.status)).length;
      return `<tr><td><button class="text-btn" data-action="view-asic" data-id="${esc(a.id)}">${esc(a.name)}</button></td><td class="num">${metric(stock.onHandQty,`${n(stock.receivedQty)} received inventory units − ${n(stock.shippedQty)} completed shipment units, with each ASIC balance held at a minimum of zero = ${n(stock.onHandQty)} on hand as of ${date(asOf)}.`)}</td><td class="num">${metric(stock.freeQty,`${n(stock.onHandQty)} on hand − ${n(stock.reservedQty)} on-hand units reserved by open allocations = ${n(stock.freeQty)} free to allocate. Incoming supply and tentative request ordering are not on-hand stock.`)}</td><td class="num">${metric(units,`Sum of requested quantities minus matched completed shipments for ${n(openRows.length)} open ${a.name} requests = ${n(units)} open units.`)}</td><td>${!openRows.length?pill('No open requests','gray'):atRisk?`<button type="button" class="pill amber overview-request-link" data-action="asic-requests" data-id="${esc(a.id)}" aria-label="Needs attention: view requests for ${esc(a.name)}">Needs attention</button>`:pill('On time','blue')}${openRows.length?'<span class="table-secondary">'+metric(atRisk,`${n(atRisk)} of ${n(openRows.length)} open ${a.name} requests have late or insufficient recorded supply.`)+' at risk</span>':''}</td><td>${btn('View inventory','asic-supply','box',`data-id="${esc(a.id)}"`,'small')}</td></tr>`;
    });
    return title('Workspace','Overview','Inventory and open requests as of '+date(asOf)+'.',btn('Add inventory','new-supply','plus',ui.asicId?`data-id="${esc(ui.asicId)}"`:'','primary'))+`<div class="summary-strip">${summary('On hand',onHand,`Sum of each selected ASIC's received inventory minus completed shipments, bounded at zero per ASIC = ${n(onHand)} units as of ${date(asOf)}.`)}${summary('Open demand',open,`${n(open)} requested units remain after matched completed shipments across the selected ASICs. This includes future requests and excludes already shipped units.`)}${summary('Requests at risk',risk,`${n(risk)} requests for the selected ASICs have late or insufficient supply when allocations and competing requests are considered.`,risk?'warning':'')}</div><div class="toolbar"><div class="control"><select aria-label="Filter ASIC" data-filter="asicId">${options(state.asics,ui.asicId,'All ASICs')}</select></div>${ui.asicId?'<button class="filter-reset" data-action="clear-filters">Clear filter</button>':''}</div><section class="panel workflow-list overview-list">${table(['ASIC','#On hand','#Free to allocate','#Open units','Requests',''],rows,`<span>${metric(rows.length,`${n(rows.length)} ASICs match the current ASIC filter.`)} ASICs</span>`)}</section>`;
  }
  function renderAsics(){return EntityViews.renderAsics(entityContext());}
  function renderProjects(){return EntityViews.renderProjects(entityContext());}
  function eventRows(events){
    return events.map(e=>{
      const activity=e.type==='expected_ship'?(e.supplyStatus==='available'?'Inventory received':e.supplyStatus==='incoming'?'Incoming supply':T.eventLabel(e.type)):T.eventLabel(e.type);
      const dateBasis=e.type==='request'?'Requested arrival date stored on this request.':e.type==='expected_fulfilment'?'Planned arrival date stored on this allocation.':e.type==='actual_ship'?'Recorded actual shipping date.':e.type==='actual_fulfilment'?'Recorded actual arrival date.':'Available or expected availability date stored on this supply entry.';
      return `<tr><td>${tip(date(e.date),dateBasis)}</td><td>${pill(activity,typeTone(e.type))}</td><td><strong>${esc(lookupA(e.asicId)?.name||'Unknown ASIC')}</strong><span class="table-secondary">${esc(lookupP(e.projectId)?.name||'Shared supply')}</span></td><td class="num">${metric(e.qty,`${n(e.qty)} units recorded on this ${activity.toLowerCase()} entry. This is an individual event quantity, not a stock balance.`)}</td><td>${btn('View details','view-event','info',`data-id="${esc(e.id)}"`,'small')}</td></tr>`;
    });
  }
  function viewEvent(eventId){
    const e=state.events.find(x=>x.id===eventId);if(!e)return;
    if(e.type==='request'){RequestViews.viewRequest(entityContext(),eventId);return;}
    const dateBasis=e.type==='expected_fulfilment'?'Planned arrival date of this allocation.':e.type==='actual_ship'?'Actual shipping date recorded on this event.':e.type==='actual_fulfilment'?'Actual arrival date recorded on this event.':'Supply availability date recorded on this entry.';
    const details=[['Activity',esc(T.eventLabel(e.type))],['Date',tip(date(e.date),dateBasis)],['ASIC',esc(lookupA(e.asicId)?.name||'Unknown ASIC')],['Project',esc(lookupP(e.projectId)?.name||'Shared supply')],['Quantity',metric(e.qty,`${n(e.qty)} units recorded on this ${T.eventLabel(e.type).toLowerCase()} entry.`)+' units']];
    if(e.type==='actual_ship')details.push(['Estimated arrival',e.eta?tip(date(e.eta),'Estimated arrival entered for this actual shipment; it does not establish confirmed receipt.'):'Not recorded']);
    if(e.type==='expected_fulfilment')details.push(['Available to ship',tip(date(T.allocationShipBy(state,e)),'Available-to-ship date entered on the allocation, or planned arrival minus project/ASIC transit days for older records.')]);
    openDrawer('Event details','Recorded activity',`<div class="drawer-body"><div class="info-grid">${details.map(([label,value])=>`<div><small>${esc(label)}</small><strong>${value}</strong></div>`).join('')}</div>${e.note?'<p class="form-section">Note</p><p class="request-detail-note">'+esc(e.note)+'</p>':''}${e.imported?'<details class="request-basis"><summary>'+icon('info')+'Source details</summary><p>'+esc(e.sourceSheet||'Imported worksheet')+' · row '+tip(e.sourceRow||'Unknown','Worksheet row stored with this imported event.')+' · '+esc(e.sourceCell||'Row-based record')+'</p></details>':''}</div>`,`<div class="drawer-footer">${btn('Delete event','delete-event','trash',`data-id="${esc(e.id)}"`,'danger')}${btn('Edit event','edit-event','edit',`data-id="${esc(e.id)}"`,'primary')}</div>`);
  }
  function pendingDemandTable(){return '';}
  function renderEvents(){
    const list=state.events.filter(e=>T.matchesEvent(state,e,{asicId:ui.asicId,projectId:ui.projectId,type:ui.type})&&[lookupA(e.asicId)?.name,lookupP(e.projectId)?.name,eventMPN(e),eventPhase(e),T.eventLabel(e.type),e.note].join(' ').toLowerCase().includes(ui.query.toLowerCase())).sort((a,b)=>b.date.localeCompare(a.date)||b.id.localeCompare(a.id));
    return title('Activity','Event ledger','Review recorded requests, inventory, allocations, and shipments.',btn('Record event','new-event','plus','','primary'))+`<div class="toolbar"><input class="table-search" aria-label="Search events" data-search="query" placeholder="Search activity…" value="${esc(ui.query)}"><div class="control"><select aria-label="Filter event type" data-filter="type">${options(T.TYPES.map(t=>({id:t,name:T.eventLabel(t)})),ui.type,'All activities')}</select></div><div class="control"><select aria-label="Filter ASIC" data-filter="asicId">${options(state.asics,ui.asicId,'All ASICs')}</select></div><div class="control"><select aria-label="Filter project" data-filter="projectId">${options(state.projects,ui.projectId,'All projects')}</select></div><div class="secondary-actions">${btn('Export CSV','export-events','download','','small')}</div></div><section class="panel workflow-list event-list">${table(['Date','Activity','ASIC / project','#Quantity',''],eventRows(list),`<span>${metric(list.length,`${n(list.length)} event records match the current search, activity, ASIC, and project filters.`)} recorded events</span>`)}</section>`;
  }
  function aggregateRows(measure) {
    const eventTypes={demand:'request',allocation:'expected_fulfilment',supply:'expected_ship'},groups=new Map();
    state.events.filter(e=>e.type===eventTypes[measure]&&T.matchesEvent(state,e,filters())).forEach(e=>{const key=e.asicId+'|'+e.projectId+'|'+eventMPN(e)+'|'+eventPhase(e);const p=lookupP(e.projectId),a=lookupA(e.asicId);if(!groups.has(key))groups.set(key,{asic:a.name,mpn:eventMPN(e),project:p?.name||'Unallocated supply',parent:p?T.parentName(state,p.id):'—',phase:eventPhase(e),quantity:0});groups.get(key).quantity+=e.qty;});
    return [...groups.values()].sort((a,b)=>a.asic.localeCompare(b.asic)||a.project.localeCompare(b.project));
  }
  function reportContent(){
    const f=filters(),scope=reportScope();
    if(ui.report==='shortage'){
      const rows=T.weekly(state,f),s=T.stats(state,f);lastExport={name:'cumulative-shortage'+(rows.notice?'-latest-5300-weeks':''),headers:['ISO week','Week beginning','Demand in week','Allocation in week','Cumulative balance'],rows:rows.map(w=>[T.isoWeek(w.week),w.week,w.demand,w.allocation,w.balance])};
      let previous=rows.openingBalance||0;
      const rendered=rows.map(w=>{const prior=previous;previous=w.balance;return `<tr><td>${tip(T.isoWeek(w.week),'ISO calendar week beginning '+date(w.week)+'. Weeks start Monday.')}</td><td class="num">${metric(w.demand,`Sum of request quantities dated in this ISO week, limited by the cutoff. Requests use requested arrival dates. ${scope}.`)}</td><td class="num">${metric(w.allocation,`Sum of allocation quantities with planned arrival dates in this ISO week, limited by the cutoff. ${scope}.`)}</td><td class="num ${w.balance<0?'negative':'positive'}">${metric(w.balance,`${n(prior)} prior balance + ${n(w.allocation)} allocations − ${n(w.demand)} demand = ${n(w.balance)} cumulative units. ${scope}.`)}</td><td>${w.balance<0?pill('Shortage','amber'):pill(w.balance?'Surplus':'Balanced','blue')}</td></tr>`;});
      return `${rows.notice?'<div class="notice">'+icon('info')+esc(rows.notice)+'</div>':''}<div class="summary-strip report-summary-strip"><div class="summary-item"><span>Requested</span><strong>${metric(s.demand,`Sum of request quantities with arrival dates through the cutoff. ${scope}.`)}</strong></div><div class="summary-item"><span>Allocated</span><strong>${metric(s.allocation,`Sum of allocation quantities with planned arrival dates through the cutoff. ${scope}.`)}</strong></div><div class="summary-item ${s.balance<0?'warning':''}"><span>Balance</span><strong>${metric(s.balance,`${n(s.allocation)} allocated − ${n(s.demand)} requested = ${n(s.balance)} units. This planning balance is not on-hand inventory. ${scope}.`)}</strong></div></div>${table(['ISO week','#Demand','#Allocated','#Balance','Status'],rendered,'<span>Planning balance = cumulative allocation − cumulative demand</span>')}`;
    }
    if(['demand','allocation','supply'].includes(ui.report)){
      const rows=aggregateRows(ui.report),total=rows.reduce((sum,r)=>sum+r.quantity,0),sourceName={demand:'request',allocation:'expected fulfilment allocation',supply:'supply'}[ui.report];
      lastExport={name:ui.report+'-summary',headers:['ASIC','MPN','Project','Parent project','Eng phase','Quantity'],rows:rows.map(r=>[r.asic,r.mpn,r.project,r.parent,r.phase,r.quantity])};
      const sourceNote=ui.report==='demand'?'Requests are dated by requested arrival.':ui.report==='allocation'?'Allocations are dated by planned arrival.':'Incoming and received supply entries are included; shipments are not subtracted. This is activity, not an on-hand balance.';
      return `<div class="summary-strip report-summary-strip"><div class="summary-item"><span>Total ${esc(ui.report)}</span><strong>${metric(total,`Sum of ${sourceName} event quantities matching this report. ${sourceNote} ${scope}.`)}</strong></div><div class="summary-item"><span>Through</span><strong>${tip(date(ui.cutoff),'Include event records dated on or before this report cutoff.')}</strong></div></div>${table(['ASIC / MPN','Project','#Quantity'],rows.map(r=>`<tr><td><strong>${esc(r.asic)}</strong><span class="table-secondary">${esc(r.mpn)}</span></td><td>${esc(r.project)}${r.parent&&r.parent!=='—'&&r.parent!==r.project?'<span class="table-secondary">Parent: '+esc(r.parent)+'</span>':''}${r.phase&&r.phase!=='Unspecified'?'<span class="table-secondary">'+esc(r.phase)+'</span>':''}</td><td class="num">${metric(r.quantity,`Sum of ${sourceName} quantities for ${r.asic}, MPN ${r.mpn}, project ${r.project}, phase ${r.phase}. ${sourceNote} ${scope}.`)}</td></tr>`),`<span>${metric(rows.length,`${n(rows.length)} distinct ASIC, MPN, project, and engineering-phase groups match the current report filters.`)} groups</span>`)}`;
    }
    if(ui.report==='financial'){
      const rows=T.financial(state,{...f,quarter:ui.quarter,funding:ui.funding,entity:ui.entity}),missing=rows.filter(r=>r.missingPrice).length,req=rows.reduce((v,r)=>v+r.requestedKnownValue,0),ship=rows.reduce((v,r)=>v+r.shippedKnownValue,0),financialScope=scope+'; quarter '+(ui.quarter==='all'?'all':ui.quarter)+(ui.funding?'; funding '+(state.fundingSources.find(e=>e.id===ui.funding)?.name||ui.funding):'')+(ui.entity?'; business entity '+(state.businessEntities.find(e=>e.id===ui.entity)?.name||ui.entity):'');
      const requestedUnknown=rows.some(r=>r.requestedValue===null),shippedUnknown=rows.some(r=>r.shippedValue===null);
      const valueTip=(r,kind)=>`Sum of each ${kind==='requested'?'request':'actual shipment'} event quantity × its verified price effective in that event's quarter for ${r.asicName} / ${r.projectName}. ${r[kind+'Value']===null?'Some matching events have no verified historical price; this full value is unknown. ':''}${financialScope}.`;
      lastExport={name:'financial-'+ui.quarter,headers:['ASIC','Project','Parent project','Funding source','Business entity','Requested units','Requested USD','Shipped units','Shipped USD','Data completeness'],rows:rows.map(r=>[r.asicName,r.projectName,r.parentName,r.funding,r.entity,r.requested,r.requestedValue??'PRICE MISSING',r.shipped,r.shippedValue??'PRICE MISSING',r.missingPrice?'Incomplete':'Complete'])};
      return `${missing?'<div class="notice">'+icon('info')+metric(missing,`${n(missing)} ASIC/project groups contain events without verified historical prices in the current financial filters.`)+' groups have missing prices. Totals show verified values only.</div>':''}<div class="summary-strip report-summary-strip"><div class="summary-item"><span>Requested value${requestedUnknown?' · known':''}</span><strong>${requestedUnknown&&req===0?tip('Unverified','No verified requested value is available for the matching events.'):metric(req,`Sum of verified request event quantity × historical event-quarter price across the matching rows. Unknown event prices are omitted. ${financialScope}.`,'usd')}</strong></div><div class="summary-item"><span>Shipped value${shippedUnknown?' · known':''}</span><strong>${shippedUnknown&&ship===0?tip('Unverified','No verified shipped value is available for the matching events.'):metric(ship,`Sum of verified actual-shipment quantity × historical event-quarter price across matching rows. Unknown event prices are omitted. ${financialScope}.`,'usd')}</strong></div></div>${table(['ASIC / project','#Requested units','#Requested value','#Shipped units','#Shipped value'],rows.map(r=>`<tr><td><strong>${esc(r.asicName)}</strong><span class="table-secondary">${tip(r.projectName,`Project: ${r.projectName}; parent: ${r.parentName}; funding: ${r.funding||'not assigned'}; business entity: ${r.entity||'not assigned'}.`)}</span></td><td class="num">${metric(r.requested,`Sum of requested event units for ${r.asicName} / ${r.projectName}. ${financialScope}.`)}</td><td class="num ${r.requestedValue==null?'negative':''}">${metric(r.requestedValue,valueTip(r,'requested'),'usd')}</td><td class="num">${metric(r.shipped,`Sum of actual-shipment event units for ${r.asicName} / ${r.projectName}. ${financialScope}.`)}</td><td class="num ${r.shippedValue==null?'negative':''}">${metric(r.shippedValue,valueTip(r,'shipped'),'usd')}</td></tr>`),'<span>USD · verified price effective in each event’s quarter</span>')}`;
    }
    return renderPivot();
  }
  function renderPivot(){
    const dimensions=[{id:'phase',name:'Engineering phase'},{id:'asic',name:'ASIC'},{id:'mpn',name:'MPN'}],fieldValue=(e,key)=>key==='phase'?eventPhase(e):key==='asic'?lookupA(e.asicId)?.name:eventMPN(e),type={demand:'request',allocation:'expected_fulfilment',shipped:'actual_ship'}[ui.pivotMeasure],scope=reportScope();
    const events=state.events.filter(e=>e.type===type&&T.matchesEvent(state,e,filters())),rowKeys=[...new Set(events.map(e=>fieldValue(e,ui.pivotRow)))].sort(),colKeys=[...new Set(events.map(e=>fieldValue(e,ui.pivotCol)))].sort(),get=(r,c)=>events.filter(e=>fieldValue(e,ui.pivotRow)===r&&fieldValue(e,ui.pivotCol)===c).reduce((v,e)=>v+e.qty,0),rowName=dimensions.find(d=>d.id===ui.pivotRow).name,colName=dimensions.find(d=>d.id===ui.pivotCol).name;
    lastExport={name:'pivot-'+ui.pivotMeasure,headers:[rowName,...colKeys,'Total'],rows:rowKeys.map(r=>[r,...colKeys.map(c=>get(r,c)),colKeys.reduce((v,c)=>v+get(r,c),0)])};
    return `<div class="toolbar report-pivot-controls"><div class="control"><label>Rows</label><select aria-label="Pivot rows" data-filter="pivotRow">${options(dimensions,ui.pivotRow)}</select></div><div class="control"><label>Columns</label><select aria-label="Pivot columns" data-filter="pivotCol">${options(dimensions,ui.pivotCol)}</select></div><div class="control"><label>Measure</label><select aria-label="Pivot measure" data-filter="pivotMeasure">${options([{id:'demand',name:'Demand quantity'},{id:'allocation',name:'Allocation quantity'},{id:'shipped',name:'Shipped quantity'}],ui.pivotMeasure)}</select></div></div>${table([rowName,...colKeys.map(c=>'#'+c),'#Total'],lastExport.rows.map(r=>`<tr>${r.map((v,i)=>`<td ${i?'class="num"':''}>${i?metric(v,i===r.length-1?`Sum of ${T.eventLabel(type)} quantities for ${rowName} ${r[0]} across all displayed columns. ${scope}.`:`Sum of ${T.eventLabel(type)} quantities where ${rowName} is ${r[0]} and ${colName} is ${colKeys[i-1]}. Each event quantity is counted once in this cell. ${scope}.`):'<strong>'+esc(v)+'</strong>'}</td>`).join('')}</tr>`),`<span>Total ${esc(ui.pivotMeasure)}: ${metric(events.reduce((v,e)=>v+e.qty,0),`Sum of all ${n(events.length)} filtered ${T.eventLabel(type)} event quantities; equals the sum of all pivot cells. ${scope}.`)} units</span>`)}`;
  }
  function renderReports(){
    const reports={shortage:'Cumulative shortage',demand:'Demand',allocation:'Allocations',supply:'Supply entries',financial:'Financial',pivot:'Pivot builder'};
    return title('Analysis','Reports','Choose a report and the records to include.',btn('Export CSV','export-report','download','','primary'))+`<div class="toolbar"><div class="control"><label for="report-type">Report</label><select id="report-type" aria-label="Report type" data-filter="report">${options(Object.entries(reports).map(([id,name])=>({id,name})),ui.report)}</select></div></div>`+`<div class="secondary-actions">${btn('Forecast summary','navigate','chart','data-page="forecasts"')}</div>`+filterBar(true,ui.report==='financial')+`<section class="panel workflow-list report-list"><div class="table-head"><h2>${reports[ui.report]}</h2></div>${reportContent()}</section>`;
  }
  function auditDetail(entry){
    try{const change=JSON.parse(entry.detail);if(!change.after&&!change.before)return tip(entry.detail,'Detail text recorded in this audit entry.');const records=Array.isArray(change.after)?change.after:[change.after||change.before],summary=records.map(r=>r?.type?esc(T.eventLabel(r.type)+' · '+(lookupA(r.asicId)?.name||r.asicId))+' · '+metric(r.qty,`${n(r.qty)} units stored in the recorded ${change.after?'after-change':'before-change'} event.`)+' units'+(r.projectId?' · '+esc(lookupP(r.projectId)?.name||r.projectId):''):esc(r?.name||'Record removed')).join('; ');return `<span>${summary}</span><details class="audit-changes"><summary>Field changes</summary><pre>${esc(JSON.stringify(change,null,2))}</pre></details>`;}catch{return tip(entry.detail,'Detail text recorded in this audit entry.');}
  }
  function renderRecovery(){
    const snaps=state.snapshots.slice().sort((a,b)=>b.date.localeCompare(a.date)),stamp=value=>T.isDate(value)?date(value):new Date(value).toLocaleString('en-US',{timeZone:'America/Los_Angeles',month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'});
    const rows=snaps.map(s=>{const a=s.data.asics.length,p=s.data.projects.length,e=s.data.events.length,b=(s.data.businessEntities||[]).length,f=(s.data.fundingSources||[]).length,v=(s.data.forecastVersions||[]).length,g=(s.data.projectFamilies||[]).length,total=a+p+e+b+f+v+g;return `<tr><td><strong>${esc(s.label)}</strong></td><td>${tip(stamp(s.date)+' PT','Recovery point creation timestamp: '+s.date+'. Displayed in Pacific time.')}</td><td class="num">${metric(total,`${n(a)} ASICs + ${n(p)} projects + ${n(e)} events + ${n(b)} business entities + ${n(f)} funding sources + ${n(v)} forecast versions + ${n(g)} project families = ${n(total)} core records in this recovery point. Audit entries and nested snapshot metadata are excluded.`)}</td><td>${btn('Restore','restore-snapshot','refresh',`data-id="${esc(s.id)}"`,'small')}</td></tr>`;});
    const auditRows=state.audit.slice().reverse().slice(0,60).map(a=>`<tr><td>${tip(stamp(a.date)+' PT','Audit timestamp: '+a.date+'. Displayed in Pacific time.')}</td><td>${pill(a.action,'gray')}<span class="audit-actor">${esc(a.actor||a.actorSubject||'Legacy / unknown actor')}</span></td><td class="audit-detail">${auditDetail(a)}</td></tr>`);
    return title('Workspace','Data & recovery','Export a backup or restore a saved recovery point.',btn('Export JSON','export-backup','download','','primary'))+`${state.storageNotice?'<div class="notice">'+icon('warn')+esc(state.storageNotice)+'</div>':''}<div class="toolbar">${btn('Import backup','import-backup','upload')}${btn('Save recovery point','create-snapshot','plus')}<span class="filter-note">Shared MongoDB</span></div><section class="panel workflow-list recovery-list"><div class="table-head"><h2>Recovery points</h2><span>${metric(snaps.length,`${n(snaps.length)} saved full-workspace recovery points in MongoDB.`)}</span></div>${table(['Name','Created','#Records',''],rows)}</section><details class="request-basis recovery-audit"><summary>${icon('events')}Audit log · ${metric(state.audit.length,`${n(state.audit.length)} saved audit records. The latest ${n(Math.min(60,state.audit.length))} are shown here; JSON backups include the full history.`)}</summary>${table(['When','Action','Details'],auditRows)}</details><details class="request-basis recovery-advanced"><summary>${icon('database')}Advanced</summary><p>Clearing the workspace keeps the previous records in a recovery point.</p><div class="settings-actions">${btn('Clear workspace','reset-demo','refresh','','danger')}</div></details>`;
  }
  function renumberPartRows(){const labels={partMpn:'MPN',partCpn:'CPN',partPlid:'PLID',partAssembly:'Component Assembly Description',partSubtype:'Component sub-Type'};document.querySelectorAll('.part-row').forEach((row,i)=>{Object.entries(labels).forEach(([name,label])=>row.querySelector('[name='+name+']')?.setAttribute('aria-label',label+' row '+(i+1)));row.querySelector('[data-action=remove-part]')?.setAttribute('aria-label','Remove part row '+(i+1));});}
  function entityContext(){return {state,ui,icon,esc,n,usd,metric,tip,date,pill,btn,textBtn,title,table,empty,options,field,selectField,formFoot,noteField,openDrawer,lookupA,lookupP,T,referenceDate,isAdmin,setEditing:value=>{editing=value;}};}
  function renderMasters(kind){return EntityViews.renderMasters(entityContext(),kind);}
  function masterForm(kind,recordId=''){EntityViews.masterForm(entityContext(),kind,recordId);}
  function confirmEntityDeletion(kind,recordId){
    const impact=T.deletionImpact(state,kind,recordId);if(!impact.exists)return;
    if(impact.families){toast('Reassign dependent project families before deleting this entity.',true);return;}
    if(kind==='projectFamily'&&impact.projects){toast('Reassign this family’s projects before deleting the family.',true);return;}
    let effect='';
    if(kind==='asic')effect=`${n(impact.events)} dependent event${impact.events===1?'':'s'} will be removed and the ASIC will be unlinked from ${n(impact.projects)} project${impact.projects===1?'':'s'}.`;
    else if(kind==='project')effect=`${n(impact.events)} project event${impact.events===1?'':'s'} will be removed. ${n(impact.children)} child project${impact.children===1?'':'s'} will be kept and detached from this parent.`;
    else if(kind==='projectFamily')effect='This unused family will be removed. Its current state is retained in a recovery point.';
    else effect=`The association will be cleared from ${n(impact.projects)} project${impact.projects===1?'':'s'}. Those projects and their events will be kept.`;
    openDrawer('Delete '+esc(impact.name)+'?','A recovery point will preserve the current workspace.',`<div class="drawer-body"><p class="setting-description">${effect}</p></div>`,`<div class="drawer-footer">${btn('Cancel','close-drawer')}${btn('Delete entity','confirm-delete-entity','trash',`data-kind="${kind}" data-id="${esc(recordId)}"`,'danger')}</div>`);
  }
  async function deleteEntity(kind,recordId){
    const before=T.clone(state),impact=T.deletionImpact(state,kind,recordId);if(!impact.exists)return;
    snapshot('Before deleting '+impact.name,false);T.deleteEntity(state,kind,recordId);audit('Delete entity',`${kind}: ${impact.name}. Dependent events removed: ${impact.events}; project associations cleared: ${impact.projects}; child projects detached: ${impact.children}.`);
    if(!await commit(before))return;
    Object.assign(ui,{asicId:'',projectId:'',parentId:'',funding:'',entity:'',projectEntityId:'',projectAsicId:'',projectEpm:'',projectPlatform:''});
    $('#toasts').innerHTML='';closeDrawer();renderPage();toast(impact.name+' deleted. A recovery point is saved.');
  }
  function emptyOverview(){return title('Workspace','Overview','Start with ASICs, projects, and inventory.',btn('Add ASIC','new-asic','plus','','primary'))+`<section class="panel onboarding-panel"><div class="panel-body"><h2>Your workspace is ready for data</h2><p class="subtitle">Add your ASICs, create projects, and record inventory on the Supply page.</p><div class="onboarding-actions">${btn('Add project','new-project','folder')}${btn('Supply','navigate','box','data-page="supply"')}</div></div></section>`;}
  function renderPage() {
    if(ui.projectEpm&&!state.projects.some(p=>p.manager===ui.projectEpm))ui.projectEpm='';
    if(ui.projectPlatform&&!state.projects.some(p=>p.platform===ui.projectPlatform))ui.projectPlatform='';
    if(ui.projectEntityId&&!state.businessEntities.some(e=>e.id===ui.projectEntityId))ui.projectEntityId='';
    if(ui.projectAsicId&&!lookupA(ui.projectAsicId))ui.projectAsicId='';
    MetricTips.hide();
    if(ui.supplyAsicId&&!lookupA(ui.supplyAsicId))ui.supplyAsicId='';
    if(ui.allocationAsicId&&!lookupA(ui.allocationAsicId))ui.allocationAsicId='';
    if(ui.allocationProjectId&&!lookupP(ui.allocationProjectId))ui.allocationProjectId='';
    if(ui.requestAsicId&&!lookupA(ui.requestAsicId))ui.requestAsicId='';
    if(ui.requestProjectId&&!lookupP(ui.requestProjectId))ui.requestProjectId='';
    if(ui.asicId&&!lookupA(ui.asicId))ui.asicId='';
    if(ui.projectId&&!lookupP(ui.projectId))ui.projectId='';
    if(ui.parentId&&!lookupP(ui.parentId))ui.parentId='';
    $('#crumb').textContent=names[ui.page];
    const count=document.querySelector('.nav .count');if(count)count.textContent=state.asics.length;
    document.querySelectorAll('[data-action="navigate"]').forEach(b=>{b.classList.toggle('active',b.dataset.page===ui.page);if(b.closest('nav'))b.setAttribute('aria-current',b.dataset.page===ui.page?'page':'false');});
    $('#content').innerHTML=({overview:()=>state.asics.length?renderOverview():emptyOverview(),asics:renderAsics,projects:renderProjects,requests:()=>RequestViews.renderRequests(entityContext()),allocations:()=>AllocationViews.renderAllocations(entityContext()),supply:()=>SupplyViews.renderSupply(entityContext()),'business-entities':()=>renderMasters('businessEntity'),'funding-sources':()=>renderMasters('fundingSource'),'project-families':()=>FamilyViews.render(entityContext()),events:renderEvents,forecasts:()=>ForecastViews.render(entityContext()),reports:renderReports,recovery:renderRecovery}[ui.page]||renderOverview)();
    document.title=names[ui.page]+' · ASIC Tracker';renderConnection();applyPermissions();
  }
  function navigate(page) {ui.page=page;ui.query='';location.hash=page;renderPage();window.scrollTo(0,0);}
  function audit(action,detail){state.audit.push({id:id('log'),date:new Date().toISOString(),action,detail});}
  async function persist(operation='edit'){
    const reason=state.audit[state.audit.length-1]?.action||'Update workspace';
    try{const saving=ApiStore.save(state,{operation,reason});renderConnection();applyPermissions();state=await saving;renderConnection();applyPermissions();return true;}
    catch(error){renderConnection();applyPermissions();toast(error.message,true);return false;}
  }
  async function commit(before,operation='edit'){if(await persist(operation))return true;state=before;renderPage();if($('#drawer')?.open&&$('#form-errors'))formError([ApiStore.lastError||'The change could not be saved.']);return false;}
  function toast(message,error=false,undo=null){const el=document.createElement('div');el.className='toast'+(error?' error':'');el.append(document.createTextNode(message));if(undo){const button=document.createElement('button');button.textContent='Undo';button.onclick=async()=>{button.disabled=true;try{await undo();}catch(error){toast(error.message,true);}finally{el.remove();}};el.append(button);}$('#toasts').append(el);setTimeout(()=>el.remove(),undo?12000:5500);}
  function snapshot(label){const snap={id:id('snapshot'),date:new Date().toISOString(),label,data:T.clone({asics:state.asics,projects:state.projects,businessEntities:state.businessEntities,fundingSources:state.fundingSources,projectFamilies:state.projectFamilies,events:state.events,audit:state.audit,forecastVersions:state.forecastVersions||[],...(state.source?{source:state.source}:{}),...(state.pendingRequests?{pendingRequests:state.pendingRequests}:{})})};state.snapshots.push(snap);state.snapshots=state.snapshots.slice(-30);return snap.id;}
  function openDrawer(heading,sub,body,footer='',opts={}){MetricTips.hide();const d=$('#drawer');d.classList.toggle('entity-drawer',!!opts.wide);d.innerHTML=`<div class="drawer-head"><div><h2>${heading}</h2><p class="subtitle">${sub}</p></div><button class="icon-button" data-action="close-drawer" aria-label="Close dialog">${icon('close')}</button></div>${body}${footer}`;if(!d.open)d.showModal();const focus=d.querySelector('input:not([type=hidden]),select');if(focus)focus.focus();applyPermissions();}
  const closeDrawer=()=>{MetricTips.hide();$('#drawer').close();};
  const field=(label,name,value='',type='text',full=false,required=false,hint='')=>`<div class="field ${full?'full':''}"><label for="f-${name}">${label}${required?'<span class="required">*</span>':''}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''} ${type==='number'?'min="0" step="1"':''}>${hint?`<small>${hint}</small>`:''}</div>`;
  const selectField=(label,name,items,value='',full=false,required=false,placeholder='Select…')=>`<div class="field ${full?'full':''}"><label for="f-${name}">${label}${required?'<span class="required">*</span>':''}</label><select id="f-${name}" name="${name}" ${required?'required':''}>${options(items,value,placeholder)}</select></div>`;
  const noteField=value=>`<div class="field full"><label for="f-note">Note</label><textarea id="f-note" name="note" placeholder="Add context for the team…">${esc(value||'')}</textarea><small>Optional. All other event fields are required.</small></div>`;
  const formFoot=(label='Save record')=>`<div class="drawer-footer">${btn('Cancel','close-drawer')}<button class="btn primary" type="submit">${icon('check')}${label}</button></div>`;
  function formError(errors){const box=$('#form-errors');if(box){box.textContent=errors.join('\n');box.classList.remove('hidden');box.scrollIntoView({block:'nearest'});}}
  function asicForm(asicId=''){EntityViews.asicForm(entityContext(),asicId);}
  function viewAsic(asicId){EntityViews.viewAsic(entityContext(),asicId);}
  function projectForm(projectId=''){EntityViews.projectForm(entityContext(),projectId);}
  function supplyForm(eventId='',asicId=''){SupplyViews.supplyForm(entityContext(),eventId,asicId);}
  function requestForm(eventId=''){requestCreatedAt=state.events.find(e=>e.id===eventId)?.createdAt||new Date().toISOString();RequestViews.requestForm(entityContext(),eventId);refreshRequestPreview();}
  function requestDraft(){
    const form=$('#request-form');if(!form)return null;
    const v=Object.fromEntries(new FormData(form).entries()),shipDays=Number(v.requestShipDays),shipBy=String(v.requestedShipDate||'');
    if(!T.isDate(shipBy)||!Number.isSafeInteger(shipDays)||shipDays<0)return null;
    const arrival=new Date(shipBy+'T12:00:00Z');arrival.setUTCDate(arrival.getUTCDate()+shipDays);
    if(!Number.isFinite(+arrival))return null;
    const old=state.events.find(e=>e.id===editing),draft={...old,id:editing||'request-preview',type:'request',asicId:v.requestAsicId||'',projectId:v.requestProjectId||'',qty:Number(v.requestQty),date:arrival.toISOString().slice(0,10),shipDays,requestedShipDate:shipBy,note:String(v.requestNote||'').trim(),createdAt:old?.createdAt||requestCreatedAt};
    if(old&&!old.createdAt)delete draft.createdAt;return draft;
  }
  function refreshRequestPreview(){const box=$('#request-availability-preview');if(!box)return;const draft=requestDraft();box.innerHTML=RequestViews.availabilityPreview(entityContext(),draft);}
  function applyRequestLeadDefaults(){const project=lookupP($('#f-requestProjectId')?.value),asic=$('#f-requestAsicId')?.value,days=$('[name=requestShipDays]');if(days)days.value=project?.leadTimes?.[asic]??project?.leadDays??0;}
  const priorShipmentIds=()=>state.events.filter(e=>e.type==='actual_ship'&&e.date<=referenceDate()).map(e=>e.id);
  const canonicalAllocationRequest=e=>T.resolveRequest(state,e)?.id||'';
  const transitDays=(projectId,asicId)=>lookupP(projectId)?.leadTimes?.[asicId]??lookupP(projectId)?.leadDays??0;
  function arrivalFromShip(shipBy,days){if(!T.isDate(shipBy)||!Number.isSafeInteger(days)||days<0)return '';const day=new Date(shipBy+'T12:00:00Z');day.setUTCDate(day.getUTCDate()+days);return Number.isFinite(+day)?day.toISOString().slice(0,10):'';}
  function allocationForm(eventId='',requestEventId=''){allocationCreatedAt=state.events.find(e=>e.id===eventId)?.createdAt||new Date().toISOString();allocationDraftId=eventId||id('event');AllocationViews.allocationForm(entityContext(),eventId,requestEventId);refreshAllocationPreview();}
  function transferForm(eventId){allocationCreatedAt=new Date().toISOString();allocationDraftId=id('event');AllocationViews.transferForm(entityContext(),eventId);refreshTransferPreview();}
  function allocationRequestItems(projectId,asicId){return T.requestAvailability(state,{asOf:referenceDate()}).filter(r=>r.projectId===projectId&&r.asicId===asicId).map(r=>({id:r.eventId,name:'REQ–'+r.eventId.replace(/^event-/,'').slice(-8).toUpperCase()+' · '+n(r.remainingQty)+' open · ship by '+date(r.shipBy)}));}
  function refreshAllocationRequestOptions(transfer=false){const form=$(transfer?'#allocation-transfer-form':'#allocation-form');if(!form)return;const project=form.querySelector('[name='+ (transfer?'toProjectId':'allocationProjectId')+']')?.value,asic=transfer?state.events.find(e=>e.id===form.querySelector('[name=allocationId]')?.value)?.asicId:form.querySelector('[name=allocationAsicId]')?.value,sel=form.querySelector('[name='+(transfer?'toRequestId':'allocationRequestId')+']');if(sel){const current=sel.value;sel.innerHTML=options(allocationRequestItems(project,asic),current,'Project pool (no specific request)');}}
  function allocationDraft(){const form=$('#allocation-form');if(!form)return null;const v=Object.fromEntries(new FormData(form).entries()),old=state.events.find(e=>e.id===editing),sameSchedule=old&&v.availableShipDate===T.allocationShipBy(state,old),days=sameSchedule?(old.shipDays??transitDays(v.allocationProjectId,v.allocationAsicId)):transitDays(v.allocationProjectId,v.allocationAsicId),arrival=sameSchedule?old.date:arrivalFromShip(v.availableShipDate,days);if(!arrival)return null;const record={...old,id:old?.id||allocationDraftId,type:'expected_fulfilment',asicId:v.allocationAsicId||'',projectId:v.allocationProjectId||'',requestId:v.allocationRequestId||'',qty:Number(v.allocationQty),availableShipDate:v.availableShipDate,date:arrival,shipDays:days,eta:old?.eta||'',note:String(v.allocationNote||'').trim(),...(old?{}:{priorShipmentIds:priorShipmentIds()}),createdAt:old?.createdAt||allocationCreatedAt,updatedAt:new Date().toISOString()};if(old&&!old.createdAt)delete record.createdAt;if(sameSchedule&&!Object.hasOwn(old,'shipDays'))delete record.shipDays;if(sameSchedule&&!Object.hasOwn(old,'availableShipDate'))delete record.availableShipDate;if(old?.asicId&&old.asicId!==record.asicId)record.mpn=lookupA(record.asicId)?.mpns[0]||'';if(old?.projectId&&old.projectId!==record.projectId)record.phase=lookupP(record.projectId)?.phase||'';return record;}
  function refreshAllocationPreview(){const box=$('#allocation-preview');if(box)box.innerHTML=AllocationViews.allocationPreview(entityContext(),allocationDraft());}
  function transferDraft(){
    const form=$('#allocation-transfer-form');if(!form)return {errors:['Choose an allocation to reallocate.']};
    const v=Object.fromEntries(new FormData(form).entries()),source=state.events.find(e=>e.id===v.allocationId&&e.type==='expected_fulfilment'),errors=[];
    if(!source)return {errors:['This allocation is no longer available.']};
    const sourceRow=T.allocationRows(state,{asOf:referenceDate()}).find(r=>r.eventId===source.id),qty=Number(v.transferQty),project=lookupP(v.toProjectId),requestId=v.toRequestId||'',shipBy=v.transferShipDate,days=transitDays(v.toProjectId,source.asicId),arrival=arrivalFromShip(shipBy,days);
    if(!Number.isSafeInteger(qty)||qty<=0||qty>(sourceRow?.remainingQty||0))errors.push('Move a positive whole number no greater than the unshipped allocation.');
    if(!isAdmin()&&qty===source.qty)errors.push('Moving all units from an allocation with no shipments removes the source allocation and requires an administrator. Move part of the allocation or ask an administrator to complete the full move.');
    if(!project)errors.push('Select a destination project.');
    if(!arrival||!T.isDate(arrival))errors.push('Choose a valid available-to-ship date.');
    if(requestId&&!state.events.some(e=>e.type==='request'&&e.id===requestId&&e.asicId===source.asicId&&e.projectId===v.toProjectId))errors.push('The destination request must match the ASIC and project.');
    if(v.toProjectId===source.projectId&&requestId===canonicalAllocationRequest(source))errors.push('Choose a different project or request. Use Edit to change only the date or quantity.');
    if(errors.length)return {errors};
    const target={id:allocationDraftId,type:'expected_fulfilment',asicId:source.asicId,projectId:v.toProjectId,requestId,qty,availableShipDate:shipBy,date:arrival,shipDays:days,eta:'',note:String(v.transferNote||'').trim(),priorShipmentIds:priorShipmentIds(),createdAt:allocationCreatedAt,updatedAt:new Date().toISOString()};
    const reduced={...source,qty:source.qty-qty,updatedAt:new Date().toISOString()},events=state.events.filter(e=>e.id!==source.id);
    if(reduced.qty)events.push(reduced);events.push(target);
    return {errors:[],source,reduced:reduced.qty?reduced:null,target,projected:{...state,events}};
  }
  function refreshTransferPreview(){const box=$('#transfer-preview');if(!box)return;const draft=transferDraft();box.innerHTML=draft.errors.length?'<div class="allocation-preview-placeholder">'+icon('info')+'<p>'+draft.errors.map(esc).join('<br>')+'</p></div>':AllocationViews.transferPreview(entityContext(),draft.projected);}
  function lineItem(e={},index=0){return `<div class="line-item"><div class="field"><label>ASIC <span class="required">*</span></label><select name="lineAsic" aria-label="ASIC line ${index+1}" required>${options(state.asics,e.asicId||'','Select ASIC…')}</select></div><div class="field qty-field"><label>Quantity <span class="required">*</span></label><input name="lineQty" aria-label="Quantity line ${index+1}" type="number" min="1" step="1" value="${e.qty||''}" required></div>${modalType==='request'?`<div class="field qty-field"><label>Transit days <span class="required">*</span></label><input name="lineDays" aria-label="Transit days line ${index+1}" type="number" min="0" step="1" value="${e.shipDays??7}" required></div>`:''}<button class="icon-button" aria-label="Remove line ${index+1}" type="button" data-action="remove-line">${icon('close')}</button></div>`;}
  function eventForm(eventId='',type='request'){
    const e=state.events.find(x=>x.id===eventId)||{date:referenceDate(),projectId:ui.projectId,asicId:ui.asicId};editing=eventId;modalType=e.type||type;
    openDrawer(eventId?'Edit event':'Record an event','Record a shipment or arrival. Use Supply, Requests, or Allocations for planning.',`<form id="event-form"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div>${eventId?`<div class="notice info">${icon(typeIcon(modalType))}${T.eventLabel(modalType)} · Changes are recorded in the audit log.</div>`:`<div class="type-options">${T.TYPES.map(t=>`<button type="button" data-action="choose-type" data-type="${t}" class="${t===modalType?'active':''}">${icon(typeIcon(t))}${T.eventLabel(t)}</button>`).join('')}</div>`}<div class="form-grid">${field(modalType==='request'?(e.imported?'Imported request date':'Requested arrival date'):modalType==='expected_fulfilment'?'Expected arrival date':modalType==='actual_fulfilment'?'Actual arrival date':'Ship date','date',e.date,'date',false,true,e.imported?esc(e.dateBasis||'Date recorded in the source worksheet'):'')}${modalType==='actual_ship'?field('Estimated arrival date','eta',e.eta||'','date',false,true,'Required for shipments. An estimate does not establish confirmed receipt.'):''}${modalType!=='expected_ship'?selectField('Project','projectId',state.projects,e.projectId,true,true):'<div class="notice info" style="grid-column:1/-1;margin:0">'+icon('info')+'Expected ship events represent unallocated supply, available across projects.</div>'}<div class="field full"><label>${modalType==='request'?'ASIC line items':'ASIC & quantity'}</label><div id="line-items" class="line-items">${lineItem(e)}</div>${modalType==='request'&&!eventId?'<button type="button" class="text-btn" data-action="add-line" style="margin-top:8px">'+icon('plus')+'Add ASIC line</button>':''}</div>${modalType!=='expected_ship'?selectField('Engineering phase','eventPhase',phases(),e.phase||lookupP(e.projectId)?.phase||'',true,false,'Use project phase'):''}${noteField(e.note)}</div>${e.imported?'<div class="notice info" style="margin-top:18px">'+icon('info')+'Imported from '+esc(e.sourceSheet||'worksheet')+' · row '+esc(e.sourceRow||'unknown')+'. Source MPN: '+esc(eventMPN(e))+'.</div>':''}${modalType==='actual_ship'?'<div class="field" style="margin-top:18px"><label for="f-allocationId">Link and align an allocation (optional)</label><select id="f-allocationId" name="allocationId"><option value="">Keep allocation dates unchanged</option></select><small>A request-specific allocation links this shipment to that request. A project-pool allocation keeps project FIFO matching. Only the selected allocation moves to this shipment’s ETA.</small></div>':''}</div>${formFoot(eventId?'Save changes':'Record event')}</form>`);
    if(!eventId)applyLeadDefaults();
    refreshAllocationOptions();
  }
  function applyLeadDefaults(){const p=lookupP($('#f-projectId')?.value);if(!p)return;document.querySelectorAll('.line-item').forEach(row=>{const days=row.querySelector('[name=lineDays]'),asic=row.querySelector('[name=lineAsic]').value;if(days)days.value=p.leadTimes?.[asic]??p.leadDays??0;});}
  function refreshAllocationOptions(){const sel=$('#f-allocationId');if(!sel)return;const project=$('#f-projectId')?.value,asic=$('[name=lineAsic]')?.value,previous=sel.value;sel.innerHTML=options(state.events.filter(e=>e.type==='expected_fulfilment'&&e.projectId===project&&e.asicId===asic).map(e=>({id:e.id,name:date(e.date)+' · '+n(e.qty)+' units'})),previous,'Keep allocation dates unchanged');}
  function guide(){openDrawer('Workspace guide','A quick guide to the planning workspace.',`<div class="drawer-body"><h2>Start with your records</h2><p class="subtitle">Add ASICs and projects. Business entities and funding sources are assigned to project families; projects inherit both. ASIC details include the DD_Lists part-number columns.</p><h2>Supply</h2><p class="subtitle">Add <strong>Available</strong> inventory when units are received, or <strong>Incoming</strong> supply with an expected date. Receive all or part of an incoming entry when it arrives; the remaining quantity stays incoming. Overdue incoming entries need a new date or receipt before they can cover requests.</p><p class="subtitle">On hand is received inventory minus completed shipments. Free to allocate is on hand minus inventory held by open allocations.</p><h2>Requests and allocations</h2><p class="subtitle">Create requests with a quantity and ship-by date. Allocations reserve stock for a project or request; other requests use the remaining supply in ship-by order. Edit an allocation or move unshipped units with Reallocate. The preview shows affected requests before saving.</p><h2>Read the numbers</h2><p class="subtitle">Hover over a number or date, or focus it with the keyboard, to see its source or calculation. Lists show the essentials; View details and More filters reveal additional information.</p><h2>Forecast versions</h2><p class="subtitle">Forecasts shows monthly and cumulative quantities, changes from the prior saved version, program breakdowns, and comparison charts. Save a forecast version to freeze the current plan. Live plan reflects current records; screenshot examples are not preloaded history. Demand uses ship-by months, supply uses availability months, and allocations use available-to-ship months.</p><h2>Reports and recovery</h2><p class="subtitle">Choose a report type and cutoff. Demand and allocation reports use arrival dates; planning balance is cumulative allocation minus demand, separate from inventory. Financial reports use verified prices effective in each event’s quarter.</p><p class="subtitle">Data & recovery exports portable backups and restores saved points. Changes are saved to the shared MongoDB workspace and checked by the Python API. Edits, reallocations, and deletions retain recovery protection.</p></div>`);}
  function download(filename,contents,mime){const url=URL.createObjectURL(new Blob([contents],{type:mime})),a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);toast(filename+' exported.');}
  function csvReport(report){const cell=value=>{let v=String(value??'');if(typeof value==='string'&&/^(?:\s*[=+\-@]|[\t\r])/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};download('asic-tracker-'+report.name+'.csv','\uFEFF'+[report.headers,...report.rows].map(r=>r.map(cell).join(',')).join('\r\n'),'text/csv;charset=utf-8');}
  function confirmDialog(heading,message,action,extra=''){openDrawer(heading,'Your current data will be saved as a recovery point.',`<div class="drawer-body"><p class="setting-description">${message}</p></div>`,`<div class="drawer-footer">${btn('Cancel','close-drawer')}${btn('Continue',action,'check',extra,'primary')}</div>`);}
  async function restoreSnapshot(snapshotId){const before=T.clone(state);const s=state.snapshots.find(x=>x.id===snapshotId);if(!s)return;const recovery=snapshot('Before restore',false),snaps=state.snapshots;if(!Object.hasOwn(s.data,'source'))delete state.source;if(!Object.hasOwn(s.data,'pendingRequests'))state.pendingRequests=[];Object.assign(state,T.clone(s.data),{forecastVersions:T.clone(s.data.forecastVersions||[]),projectFamilies:T.clone(s.data.projectFamilies||[])});state.snapshots=snaps;state.version=2;audit('Restore','Restored “'+s.label+'”. Prior state retained as '+recovery);if(!await commit(before,'restore'))return;$('#toasts').innerHTML='';closeDrawer();renderPage();toast('Workspace restored. The previous state is saved in recovery points.');}
  document.addEventListener('click',async event=>{
    const b=event.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;
    if(ApiStore.busy){event.preventDefault();return;}
    if(!canAction(action)){event.preventDefault();toast(ApiStore.needsReload?'Load the latest shared workspace before changing records.':'Your role does not permit this action.',true);return;}
    if(action==='reload-workspace'){
      try{const loading=ApiStore.load();renderConnection();applyPermissions();state=await loading;window.pendingBackup=null;closeDrawer();shell();toast('Latest shared workspace loaded.');}catch(error){toast(error.message,true);renderConnection();applyPermissions();}return;
    }else if(action==='download-unsaved-draft'){ApiStore.exportDraft();return;}
    else if(action==='navigate')navigate(b.dataset.page);
    else if(action==='new-project-family')FamilyViews.form(entityContext());
    else if(action==='edit-project-family')FamilyViews.form(entityContext(),b.dataset.id);
    else if(action==='delete-project-family')confirmEntityDeletion('projectFamily',b.dataset.id);
    else if(action==='new-event')eventForm('','actual_ship');
    else if(action==='new-forecast-version')ForecastViews.captureForm(entityContext());
    else if(action==='forecast-tab'){ui.forecastTab=['summary','program','chart'].includes(b.dataset.tab)?b.dataset.tab:'summary';renderPage();}
    else if(action==='forecast-mode'){ui.forecastMode=b.dataset.mode==='cumulative'?'cumulative':'monthly';renderPage();}
    else if(action==='clear-forecast-filters'){Object.assign(ui,{forecastAsicId:'',forecastProjectId:'',forecastCategory:'',forecastPhase:'',forecastMeasure:'request',forecastStart:'',forecastEnd:'',forecastYear:'',forecastVersionIds:[],forecastIncludeLive:true});renderPage();}
    else if(action==='export-forecast'){try{csvReport(ForecastViews.exportReport(entityContext()));}catch(error){toast(error.message,true);}}
    else if(action==='delete-forecast-version'){const version=(state.forecastVersions||[]).find(v=>v.id===b.dataset.id);if(version)confirmDialog('Delete '+esc(version.name)+'?','This saved forecast version will be removed. Current requests, supply, and allocations are kept. A recovery point retains the version.','confirm-delete-forecast-version',`data-id="${esc(version.id)}"`);}
    else if(action==='confirm-delete-forecast-version'){const version=(state.forecastVersions||[]).find(v=>v.id===b.dataset.id);if(!version)return;const before=T.clone(state);snapshot('Before deleting forecast '+version.name,false);state.forecastVersions=state.forecastVersions.filter(v=>v.id!==version.id);audit('Delete forecast version',JSON.stringify({id:version.id,month:version.month,name:version.name,lineCount:version.lines.length}));if(!await commit(before))return;ui.forecastVersionIds=ui.forecastVersionIds.filter(id=>id!==version.id);closeDrawer();renderPage();toast('Forecast version removed. A recovery point was saved.');}

    else if(action==='new-supply')supplyForm('',b.dataset.id||'');
    else if(action==='edit-supply')supplyForm(b.dataset.id);
    else if(action==='receive-supply')SupplyViews.receiveForm(entityContext(),b.dataset.id);
    else if(action==='view-supply')SupplyViews.viewSupply(entityContext(),b.dataset.id);
    else if(action==='asic-supply'){ui.supplyAsicId=b.dataset.id;closeDrawer();navigate('supply');}
    else if(action==='asic-requests'){Object.assign(ui,{requestAsicId:b.dataset.id,requestProjectId:'',requestStatus:'',query:''});closeDrawer();navigate('requests');}
    else if(action==='clear-supply-filters'){ui.supplyAsicId='';ui.query='';renderPage();}
    else if(action==='new-allocation')allocationForm();
    else if(action==='edit-allocation')allocationForm(b.dataset.id);
    else if(action==='transfer-allocation')transferForm(b.dataset.id);
    else if(action==='allocate-request')allocationForm('',b.dataset.id);
    else if(action==='request-allocations'){const request=state.events.find(e=>e.id===b.dataset.id);if(request){ui.allocationAsicId=request.asicId;ui.allocationProjectId=request.projectId;closeDrawer();navigate('allocations');}}
    else if(action==='clear-allocation-filters'){Object.assign(ui,{allocationAsicId:'',allocationProjectId:'',query:''});renderPage();}
    else if(action==='new-request')requestForm();
    else if(action==='edit-request')requestForm(b.dataset.id);
    else if(action==='view-request')RequestViews.viewRequest(entityContext(),b.dataset.id);
    else if(action==='record-supply')supplyForm();
    else if(action==='clear-request-filters'){Object.assign(ui,{requestAsicId:'',requestProjectId:'',requestStatus:'',query:''});renderPage();}
    else if(action==='edit-event'){if(state.events.find(e=>e.id===b.dataset.id)?.type==='request')requestForm(b.dataset.id);else if(state.events.find(e=>e.id===b.dataset.id)?.type==='expected_fulfilment')allocationForm(b.dataset.id);else if(state.events.find(e=>e.id===b.dataset.id)?.type==='expected_ship')supplyForm(b.dataset.id);else eventForm(b.dataset.id);}
    else if(action==='view-event')viewEvent(b.dataset.id);
    else if(action==='choose-type'){if(b.dataset.type==='request')requestForm();else if(b.dataset.type==='expected_fulfilment')allocationForm();else if(b.dataset.type==='expected_ship')supplyForm();else eventForm('',b.dataset.type);}
    else if(action==='new-asic')asicForm();
    else if(action==='edit-asic')asicForm(b.dataset.id);
    else if(action==='view-asic')viewAsic(b.dataset.id);
    else if(action==='new-project')projectForm();
    else if(action==='edit-project')projectForm(b.dataset.id);
    else if(action==='new-business-entity')masterForm('businessEntity');
    else if(action==='edit-business-entity')masterForm('businessEntity',b.dataset.id);
    else if(action==='new-funding-source')masterForm('fundingSource');
    else if(action==='edit-funding-source')masterForm('fundingSource',b.dataset.id);
    else if(action==='delete-asic')confirmEntityDeletion('asic',b.dataset.id);
    else if(action==='delete-project')confirmEntityDeletion('project',b.dataset.id);
    else if(action==='delete-business-entity')confirmEntityDeletion('businessEntity',b.dataset.id);
    else if(action==='delete-funding-source')confirmEntityDeletion('fundingSource',b.dataset.id);
    else if(action==='confirm-delete-entity')await deleteEntity(b.dataset.kind,b.dataset.id);
    else if(action==='add-part'){const list=$('#part-rows');list.insertAdjacentHTML('beforeend',EntityViews.partRow(entityContext(),{},list.children.length));renumberPartRows();list.lastElementChild?.querySelector('[name=partMpn]')?.focus();}
    else if(action==='remove-part'){b.closest('.part-row').remove();renumberPartRows();}
    else if(action==='clear-project-filters'){Object.assign(ui,{projectEntityId:'',projectAsicId:'',projectEpm:'',projectPlatform:'',query:''});renderPage();}
    else if(action==='close-drawer')closeDrawer();
    else if(action==='guide')guide();
    else if(action==='add-line'){const list=$('#line-items');list.insertAdjacentHTML('beforeend',lineItem({},list.children.length));applyLeadDefaults();}
    else if(action==='remove-line'){const list=$('#line-items');if(list.children.length>1)b.closest('.line-item').remove();else toast('Keep at least one ASIC line.',true);}
    else if(action==='project-report'){ui.projectId=b.dataset.id;ui.parentId='';ui.asicId='';ui.phase='';ui.report='shortage';navigate('reports');}
    else if(action==='report-tab'){ui.report=b.dataset.report;if(ui.report==='supply'){ui.projectId='';ui.parentId='';ui.phase='';}renderPage();}
    else if(action==='clear-filters'){Object.assign(ui,{asicId:'',parentId:'',projectId:'',phase:'',funding:'',entity:''});renderPage();}
    else if(action==='export-report')csvReport(lastExport);
    else if(action==='export-overview'){csvReport({name:'overview',headers:['ASIC','Demand','Allocation','Expected supply','Balance'],rows:state.asics.filter(a=>!ui.asicId||a.id===ui.asicId).map(a=>{const s=T.stats(state,{...filters(),asicId:a.id});return [a.name,s.demand,s.allocation,scopedSupply()?'Unallocated':s.supply,s.balance];})});}
    else if(action==='export-events'){const list=state.events.filter(e=>T.matchesEvent(state,e,{asicId:ui.asicId,projectId:ui.projectId,type:ui.type})&&[lookupA(e.asicId)?.name,lookupP(e.projectId)?.name,eventMPN(e),eventPhase(e),T.eventLabel(e.type),e.note].join(' ').toLowerCase().includes(ui.query.toLowerCase()));csvReport({name:'events',headers:['ID','Type','Date','ASIC','MPN','Project','Engineering phase','Quantity','Ship duration days','ETA','Source sheet','Source row','Note'],rows:list.map(e=>[e.id,T.eventLabel(e.type),e.date,lookupA(e.asicId)?.name,eventMPN(e),lookupP(e.projectId)?.name||'',eventPhase(e),e.qty,e.shipDays??'',e.eta||'Unknown',e.sourceSheet||'',e.sourceRow||'',e.note||''])});}
    else if(action==='export-backup')download('asic-tracker-backup-'+referenceDate()+'.json',JSON.stringify(state,null,2),'application/json');
    else if(action==='import-backup')$('#backup-file').click();
    else if(action==='create-snapshot'){const before=T.clone(state);snapshot('Manual · '+new Date().toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles',hour:'numeric',minute:'2-digit'})+' PT',false);audit('Snapshot','Manual full-workspace snapshot created.');if(!await commit(before))return;renderPage();toast('Recovery point created.');}
    else if(action==='restore-snapshot')confirmDialog('Restore this snapshot?','The selected snapshot will replace ASICs, projects, business entities, funding sources, project families, events, and forecast versions. Audit history is retained. Your current workspace will remain available as a recovery point.','confirm-restore',`data-id="${b.dataset.id}"`);
    else if(action==='confirm-restore')await restoreSnapshot(b.dataset.id);
    else if(action==='reset-demo')confirmDialog('Clear this workspace?','All current records will be cleared. A recovery point keeps them available for restore.','confirm-reset');
    else if(action==='confirm-reset'){const before=T.clone(state);snapshot('Before clearing workspace',false);const snaps=state.snapshots;state=T.freshSeed();state.snapshots=snaps;audit('Reset','Cleared the workspace. Previous records retained in a recovery point.');if(!await commit(before,'reset'))return;$('#toasts').innerHTML='';closeDrawer();renderPage();toast('Workspace cleared.');}
    else if(action==='delete-event'||action==='delete-request'||action==='delete-allocation'||action==='delete-supply'){const before=T.clone(state);const removed=state.events.find(e=>e.id===b.dataset.id);if(!removed)return;snapshot(removed.type==='request'?'Before request deletion':removed.type==='expected_fulfilment'?'Before allocation deletion':removed.type==='expected_ship'?'Before inventory deletion':'Before event deletion',false);state.events=state.events.filter(e=>e.id!==removed.id);audit(removed.type==='request'?'Delete request':removed.type==='expected_fulfilment'?'Delete allocation':removed.type==='expected_ship'?'Delete inventory':'Delete event',JSON.stringify(removed));if(!await commit(before))return;closeDrawer();renderPage();toast((removed.type==='request'?'Request':removed.type==='expected_fulfilment'?'Allocation':removed.type==='expected_ship'?'Inventory entry':'Event')+' removed. A recovery point was saved.',false,async()=>{if(ApiStore.busy||ApiStore.needsReload){toast('Load the latest workspace before restoring a deleted record.',true);return;}if(state.events.some(e=>e.id===removed.id)){toast('This event has already been restored.');return;}if(!lookupA(removed.asicId)||(removed.projectId&&!lookupP(removed.projectId))){toast('Restore the matching workspace before undoing this deletion.',true);return;}const undoBefore=T.clone(state);state.events.push(removed);audit('Undo deletion','Restored event '+removed.id);if(!await commit(undoBefore))return;renderPage();});}
    else if(action==='confirm-import'){const before=T.clone(state);const pending=window.pendingBackup;if(!pending)return;snapshot('Before backup import',false);const snaps=state.snapshots;state=T.clone(pending);state.projectFamilies=state.projectFamilies||[];state.forecastVersions=state.forecastVersions||[];state.snapshots=[...state.snapshots,...snaps].filter((s,i,arr)=>arr.findIndex(x=>x.id===s.id)===i).slice(-30);audit('Import','Imported validated JSON backup. Previous workspace retained in recovery points.');if(!await commit(before,'import'))return;$('#toasts').innerHTML='';window.pendingBackup=null;closeDrawer();renderPage();toast('Backup imported successfully.');}
  });
  document.addEventListener('change',event=>{
    const el=event.target;if(el.dataset.filter){if(el.dataset.filter==='cutoff'&&!T.isDate(el.value)){toast('Choose a valid cutoff date.',true);return;}if(['forecastStart','forecastEnd'].includes(el.dataset.filter)){
      const value=el.value;
      if(value&&!ForecastEngine.validMonth(value)){toast('Choose a valid forecast month.',true);el.value=ui[el.dataset.filter];return;}
      const start=el.dataset.filter==='forecastStart'?value:ui.forecastStart,end=el.dataset.filter==='forecastEnd'?value:ui.forecastEnd;
      if(start&&end){try{ForecastEngine.monthRange(start,end);}catch(error){toast(error.message,true);el.value=ui[el.dataset.filter];return;}}
    }
    ui[el.dataset.filter]=el.dataset.filter==='forecastVersionIds'?Array.from(el.selectedOptions).map(option=>option.value).filter(Boolean):el.type==='checkbox'?el.checked:el.value;if(el.dataset.filter==='report'&&ui.report==='supply'){ui.projectId='';ui.parentId='';ui.phase='';}if(ui.page==='reports'&&ui.report==='supply'&&['parentId','projectId','phase'].includes(el.dataset.filter)){ui[el.dataset.filter]='';toast('Supply is unallocated. Filter by ASIC and cutoff instead.');}renderPage();}
    if(el.id==='f-projectFamilyId'){const panel=$('#project-inheritance');if(panel)panel.innerHTML=FamilyViews.inheritance(entityContext(),el.value);}
    if(el.id==='f-projectId'||el.name==='lineAsic'){applyLeadDefaults();refreshAllocationOptions();}
    if(el.closest('#request-form')){if(el.id==='f-requestProjectId'||el.id==='f-requestAsicId')applyRequestLeadDefaults();refreshRequestPreview();}
    if(el.closest('#allocation-form')){if(['allocationAsicId','allocationProjectId'].includes(el.name))refreshAllocationRequestOptions();refreshAllocationPreview();}
    if(el.closest('#allocation-transfer-form')){if(el.name==='toProjectId')refreshAllocationRequestOptions(true);refreshTransferPreview();}
  });
  document.addEventListener('input',event=>{
    const el=event.target;if(el.closest('#request-form'))refreshRequestPreview();if(el.closest('#allocation-form'))refreshAllocationPreview();if(el.closest('#allocation-transfer-form'))refreshTransferPreview();if(el.dataset.search){const pos=el.selectionStart;ui.query=el.value;renderPage();const fresh=document.querySelector('[data-search]');fresh.focus();fresh.setSelectionRange(pos,pos);}
    if(el.id==='global-search'){const q=el.value.trim().toLowerCase(),box=$('#search-results');if(!q){box.classList.add('hidden');return;}const found=[...state.asics.filter(a=>[a.name,...a.mpns,...a.cpns].join(' ').toLowerCase().includes(q)).map(a=>({name:a.name,id:a.id,action:'view-asic',kind:'ASIC'})),...state.projects.filter(p=>[p.name,p.key,p.manager].join(' ').toLowerCase().includes(q)).map(p=>({name:p.name,id:p.id,action:'edit-project',kind:'Project'}))].slice(0,7);box.innerHTML=found.length?found.map(x=>`<button data-action="${x.action}" data-id="${x.id}">${esc(x.name)}<small>${x.kind}</small></button>`).join(''):'<div class="empty" style="padding:18px">No matching ASICs or projects.</div>';box.classList.remove('hidden');}
  });
  document.addEventListener('click',e=>{if(!e.target.closest('.search-wrap'))$('#search-results')?.classList.add('hidden');});
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();$('#global-search').focus();}if(e.key==='Escape')$('#search-results')?.classList.add('hidden');});
  document.addEventListener('submit',async event=>{
    if(!['asic-form','project-form','project-family-form','master-form','request-form','allocation-form','allocation-transfer-form','supply-form','supply-receive-form','forecast-version-form','event-form'].includes(event.target.id))return;event.preventDefault();if(ApiStore.busy||ApiStore.needsReload||!canEdit()){toast('Your change cannot be saved until access and the shared revision are current.',true);return;}if(event.target.id==='project-family-form'&&!isAdmin()){toast('Only administrators can edit project families.',true);return;}const form=event.target,d=new FormData(form),v=Object.fromEntries(d.entries()),errors=[],before=T.clone(state);let detail='',action='';
    if(form.id==='forecast-version-form'){
      let record;
      try{record=ForecastEngine.capture(state,{id:id('forecast'),month:String(v.forecastMonth||''),name:String(v.forecastName||'').trim(),note:String(v.forecastNote||'').trim(),createdAt:new Date().toISOString()});}
      catch(error){formError([error.message]);return;}
      state.forecastVersions=(state.forecastVersions||[]).concat(record);
      action='Save forecast version';detail=JSON.stringify({id:record.id,month:record.month,name:record.name,lineCount:record.lines.length});
    }else if(form.id==='asic-form'){
      const old=lookupA(editing),price=String(v.price||'').trim()===''?null:Number(v.price),quarter=String(v.priceQuarter||'').trim(),confirmPrice=!old||d.has('confirmPrice');
      const values=name=>d.getAll(name).map(value=>String(value).trim());const mpns=values('partMpn'),cpns=values('partCpn'),plids=values('partPlid'),assemblies=values('partAssembly'),subtypes=values('partSubtype'),partIds=values('partId');
      const parts=mpns.map((mpn,i)=>({...old?.parts?.find(part=>part.id===partIds[i]),id:partIds[i]||id('part'),mpn,cpn:cpns[i]||'',plid:plids[i]||'',assembly:assemblies[i]||'',subtype:subtypes[i]||''})).filter(r=>[r.mpn,r.cpn,r.plid,r.assembly,r.subtype].some(Boolean));
      if(price!==null&&(!Number.isFinite(price)||price<0))errors.push('Unit price must be a nonnegative number.');if(confirmPrice&&price!==null&&!/^\d{4}-Q[1-4]$/.test(quarter))errors.push('Use an effective quarter such as 2026-Q4.');
      const unique=key=>[...new Set(parts.map(r=>r[key]).filter(Boolean))],keepLegacy=old&&!(old.parts||[]).length&&!parts.length;const record={...old,id:editing||id('asic'),name:v.name.trim(),owner:v.owner.trim(),marketing:String(v.marketing||'').trim(),parts,mpns:keepLegacy?T.clone(old.mpns||[]):unique('mpn'),cpns:keepLegacy?T.clone(old.cpns||[]):unique('cpn'),plid:keepLegacy?old.plid||'':unique('plid').join(', '),assembly:keepLegacy?old.assembly||'':unique('assembly').join(' | '),subtype:keepLegacy?old.subtype||'':unique('subtype').join(' | '),description:String(v.description||'').trim(),price,priceHistory:T.clone(old?.priceHistory||[])};
      if(confirmPrice&&price!==null&&quarter){record.historicalPriceUnknown=false;const existing=record.priceHistory.find(h=>h.quarter===quarter);if(existing)existing.price=price;else record.priceHistory.push({quarter,price});}
      if(old&&d.has('confirmPrice')&&price===null)errors.push('Enter a unit price before confirming its effective quarter.');
      if(old)state.asics=state.asics.map(a=>a.id===old.id?record:a);else state.asics.push(record);action=old?'Edit ASIC':'Create ASIC';detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='project-form'){
      const old=lookupP(editing),asicIds=d.getAll('asicIds'),leadTimes=T.clone(old?.leadTimes||{});asicIds.forEach(a=>{leadTimes[a]=Number(v['lead-'+a]);});
      const record={...old,...(old?{}:{leadDays:7}),id:editing||id('project'),name:v.name.trim(),manager:v.manager.trim(),scpm:String(v.scpm||'').trim(),parentId:v.parentId||'',key:String(v.key||'').trim(),projectFamilyId:v.projectFamilyId||'',prototype:v.prototype===''?null:v.prototype==='true',platform:String(v.platform||'').trim(),phase:old?.phase||'',summary:String(v.summary||'').trim(),asicIds,leadTimes};
      if(old)state.projects=state.projects.map(p=>p.id===old.id?record:p);else state.projects.push(record);action=old?'Edit project':'Create project';detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='project-family-form'){
      const old=state.projectFamilies.find(f=>f.id===editing),record={...old,id:editing||id('family'),name:String(v.name||'').trim(),businessEntityId:v.businessEntityId||'',fundingSourceId:v.fundingSourceId||'',description:String(v.description||'').trim()};
      if(old)state.projectFamilies=state.projectFamilies.map(f=>f.id===old.id?record:f);else state.projectFamilies.push(record);
      action=old?'Edit project family':'Create project family';detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='master-form'){
      const kind=v.masterKind,key=kind==='businessEntity'?'businessEntities':kind==='fundingSource'?'fundingSources':'';
      if(!key){formError(['Unknown entity type.']);return;}
      const old=state[key].find(r=>r.id===(v.masterId||editing)),record={...old,id:old?.id||id(kind),name:String(v.name||'').trim(),description:String(v.description||'').trim()};
      if(old)state[key]=state[key].map(r=>r.id===old.id?record:r);else state[key].push(record);
      const fieldId=kind==='businessEntity'?'businessEntityId':'fundingSourceId',fieldLabel=kind==='businessEntity'?'entity':'funding';state.projects.filter(p=>p[fieldId]===record.id).forEach(p=>{p[fieldLabel]=record.name;});
      action=(old?'Edit ':'Create ')+(kind==='businessEntity'?'business entity':'funding source');detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='supply-form'){
      const old=state.events.find(e=>e.id===editing&&e.type==='expected_ship'),status=v.supplyStatus;
      if(status==='available'&&v.supplyDate>referenceDate())errors.push('Available inventory needs a date on or before today. Use Incoming for a future delivery.');
      const record={...old,id:old?.id||id('event'),type:'expected_ship',asicId:v.supplyAsicId||'',projectId:'',qty:Number(v.supplyQty),date:v.supplyDate,supplyStatus:status,supplyReference:String(v.supplyReference||'').trim(),note:String(v.supplyNote||'').trim(),shipDays:old?.shipDays??0,eta:old?.eta||'',requestId:old?.requestId||'',createdAt:old?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()};
      if(old&&!old.createdAt)delete record.createdAt;
      if(old){snapshot('Before changing inventory',false);state.events=state.events.map(e=>e.id===old.id?record:e);}else state.events.push(record);
      action=old?'Edit inventory':'Add inventory';detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='supply-receive-form'){
      const old=state.events.find(e=>e.id===v.supplyEventId&&e.type==='expected_ship'),row=T.supplyRows(state,{asOf:referenceDate()}).find(r=>r.eventId===v.supplyEventId),qty=Number(v.receiveQty);
      if(!old||row?.status!=='incoming'){formError(['Choose an incoming inventory entry to receive.']);return;}
      if(!Number.isSafeInteger(qty)||qty<=0||qty>old.qty)errors.push('Received quantity must be a positive whole number no greater than the incoming quantity.');
      if(!T.isDate(v.receiveDate)||v.receiveDate>referenceDate())errors.push('Receipt date must be a valid date on or before today.');
      if(errors.length){formError(errors);return;}
      snapshot('Before receiving inventory',false);
      const received={...old,id:qty===old.qty?old.id:id('event'),qty,date:v.receiveDate,supplyStatus:'available',note:String(v.receiveNote||'').trim()||old.note||'',updatedAt:new Date().toISOString()};
      state.events=state.events.filter(e=>e.id!==old.id);if(qty<old.qty)state.events.push({...old,qty:old.qty-qty,updatedAt:new Date().toISOString()});state.events.push(received);
      action='Receive inventory';detail=JSON.stringify({before:old,after:state.events.filter(e=>e.id===old.id||e.id===received.id)});
    }else if(form.id==='allocation-form'){
      const old=state.events.find(e=>e.id===editing&&e.type==='expected_fulfilment'),record=allocationDraft();
      if(!record){formError(['Choose a valid available-to-ship date.']);return;}
      const shipped=old?T.allocationRows(state,{asOf:referenceDate()}).find(r=>r.eventId===old.id)?.shippedQty||0:0;
      if(record.qty<shipped)errors.push('Quantity cannot be less than the '+n(shipped)+' units already shipped.');
      if(shipped&&old&&(old.asicId!==record.asicId||old.projectId!==record.projectId||canonicalAllocationRequest(old)!==canonicalAllocationRequest(record)))errors.push('Already shipped units must stay assigned. Use Reallocate to move only the unshipped quantity.');
      if(record.requestId&&!T.resolveRequest(state,record)&&!(old&&record.requestId===old.requestId&&record.asicId===old.asicId&&record.projectId===old.projectId))errors.push('The selected request must match the ASIC and project.');
      if(old){snapshot('Before changing allocation',false);state.events=state.events.map(e=>e.id===old.id?record:e);}else state.events.push(record);
      action=old?'Change allocation':'Create allocation';detail=JSON.stringify({before:old||null,after:record});
    }else if(form.id==='allocation-transfer-form'){
      const draft=transferDraft();if(draft.errors.length){formError(draft.errors);return;}
      snapshot('Before reallocating ASICs',false);state.events=draft.projected.events;
      action='Reallocate ASICs';detail=JSON.stringify({before:draft.source,after:[draft.reduced,draft.target].filter(Boolean)});
    }else if(form.id==='request-form'){
      const old=state.events.find(e=>e.id===editing),draft=requestDraft();
      if(!draft){formError(['Enter a valid ship-by date and a nonnegative whole number of transit days.']);return;}
      const record={...draft,id:old?.id||id('event'),requestId:old?.requestId||id('request'),eta:old?.eta||'',createdAt:old?.createdAt||requestCreatedAt,updatedAt:new Date().toISOString()};
      if(old&&!old.createdAt)delete record.createdAt;
      if(!T.isDate(record.date))errors.push('The calculated arrival date is outside the supported date range.');
      if(old)state.events=state.events.map(e=>e.id===old.id?record:e);else state.events.push(record);
      action=old?'Edit request':'Create request';detail=JSON.stringify({before:old||null,after:record});
    }else{
      const old=state.events.find(e=>e.id===editing),requestId=old?.requestId||id('request'),asics=d.getAll('lineAsic'),qtys=d.getAll('lineQty'),days=d.getAll('lineDays');
      if(new Set(asics).size!==asics.length)errors.push('Use one line per ASIC; combine repeated ASIC quantities.');
      const records=asics.map((asicId,i)=>({...(old||{}),id:editing||id('event'),type:modalType,date:v.date,asicId,...(old?.asicId&&old.asicId!==asicId?{mpn:lookupA(asicId)?.mpns[0]||''}:{}),projectId:modalType==='expected_ship'?'':v.projectId,qty:Number(qtys[i]),shipDays:modalType==='request'?Number(days[i]):old?.shipDays??0,eta:modalType==='actual_ship'?v.eta:old?.eta||'',note:v.note.trim(),...(v.eventPhase!==undefined?{phase:v.eventPhase}:{}),...(old?.etaUnknown?{etaUnknown:!v.eta}:{}),requestId:modalType==='request'?requestId:old?.requestId||'',createdAt:old?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()}));
      if(old&&!old.createdAt)records.forEach(record=>delete record.createdAt);
      if(old)state.events=state.events.map(e=>e.id===old.id?records[0]:e);else state.events.push(...records);
      let alignedAllocation=null;
      if(modalType==='actual_ship'&&v.allocationId&&!v.eta)errors.push('Enter an ETA before aligning an expected fulfilment.');
      if(modalType==='actual_ship'&&v.allocationId&&v.eta){const e=records[0],related=state.events.find(x=>x.id===v.allocationId&&x.type==='expected_fulfilment'&&x.asicId===e.asicId&&x.projectId===e.projectId);if(related){const prior=T.clone(related);e.requestId=T.resolveRequest(state,related)?.id||'';related.date=e.eta;related.availableShipDate=e.date;related.updatedAt=new Date().toISOString();alignedAllocation={before:prior,after:T.clone(related)};}else errors.push('Select an allocation for the same ASIC and project.');}
      action=old?'Edit event':'Create event';detail=JSON.stringify({before:old||null,after:records,alignedAllocation});
    }
    T.inheritFamilyLinks(state);errors.push(...T.validateState(state));if(errors.length){state=before;formError([...new Set(errors)].slice(0,8));return;}audit(action,detail);if(!await commit(before))return;closeDrawer();renderPage();toast(action+' saved.');
  });
  $('#backup-file').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;try{if(file.size>32*1024*1024)throw new Error('Backup is too large. Maximum supported file size is 32 MiB; the server may enforce a lower limit for the complete import request.');const parsed=JSON.parse(await file.text());parsed.projectFamilies=parsed.projectFamilies||[];T.inheritFamilyLinks(parsed);const errors=T.validateState(parsed);if(errors.length)throw new Error(errors.slice(0,5).join(' '));window.pendingBackup=parsed;confirmDialog('Import this backup?',`Validated ${parsed.asics.length} ASICs, ${parsed.projects.length} projects, and ${parsed.events.length} events, plus ${(parsed.forecastVersions||[]).length} forecast versions. Continuing will replace the workspace with this backup.`,'confirm-import');}catch(error){toast('Import rejected: '+error.message,true);}});
  window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if(names[page]&&ui.page!==page){ui.page=page;ui.query='';renderPage();}});
  shell();
})().catch(error=>window.ApiStore.renderBootError(error));
