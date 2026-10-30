/* Request entry and a concise availability list. */
(() => {
  'use strict';
  const HEADERS=['Request','Project','#Quantity','Ship by','Availability','Actions'];
  const STATUS={
    'on-time':{label:'On time',tone:'blue',icon:'check'},
    late:{label:'Late',tone:'amber',icon:'clock'},
    shortfall:{label:'Needs supply',tone:'amber',icon:'warn'},
    shipped:{label:'Shipped',tone:'blue',icon:'truck'}
  };
  const reference=event=>'REQ–'+String(event.id||event.eventId||'').replace(/^event-/,'').slice(-8).toUpperCase();
  const checkRows=c=>c.T.requestAvailability(c.state,{asOf:c.referenceDate()});
  const config=row=>STATUS[row.status]||STATUS.shortfall;
  const m=(c,value,explanation)=>c.metric?c.metric(value,explanation):`<span class="metric" tabindex="0" data-tooltip="${c.esc(explanation)}">${c.n(value)}</span>`;
  const t=(c,text,explanation)=>c.tip?c.tip(text,explanation):`<span class="metric" tabindex="0" data-tooltip="${c.esc(explanation)}">${c.esc(text)}</span>`;
  const openTip=(c,r)=>`${c.n(r.qty)} requested − ${c.n(r.shippedQty)} already shipped = ${c.n(r.remainingQty)} open units.`;
  const readyTip=(c,r)=>`${c.n(r.availableByShipBy)} of ${c.n(r.remainingQty)} open units have recorded supply by ${c.date(r.shipBy)}, after completed shipments, explicit allocations, and earlier ship-by requests. Of these, ${c.n(r.allocatedAvailableByShipBy||0)} are backed by this request's allocations.`;
  const gapTip=(c,r)=>`${c.n(r.remainingQty)} open − ${c.n(r.availableByShipBy)} covered by the ship-by date = ${c.n(r.shortfallQty)} units short by that date.`;
  const expectedTip=(c,r)=>`Earliest date recorded supply can cover all ${c.n(r.remainingQty)} open units, after shipment consumption, allocation reservations, and earlier requests. It cannot precede today.`;
  function emptyHeaders(c){return `<div class="table-scroll"><table><thead><tr>${HEADERS.map(h=>`<th${h.startsWith('#')?' class="num"':''}>${c.esc(h.replace(/^#/,''))}</th>`).join('')}</tr></thead><tbody></tbody></table></div>`;}
  function basis(c){return `<details class="request-basis"><summary>${c.icon('info')}How availability works</summary><p>Recorded inventory and incoming supply cover requests after shipments and explicit allocations. The remaining supply follows ship-by order. Overdue incoming entries need an updated date or receipt before they can cover a request.</p><p>Hover over a number for its source or calculation. Availability on the ship-by date counts as on time.</p></details>`;}
  function summary(c,row){
    const status=config(row);
    if(row.status==='shipped')return `<div class="request-availability-result shipped">${c.icon(status.icon)}<div><strong>Request shipped</strong><p>${m(c,row.shippedQty,`${c.n(row.shippedQty)} completed shipment units are matched to this request by its link, or by project and ASIC in ship-by order.`)} units shipped.</p></div></div>`;
    const expected=row.expectedAvailableDate?t(c,c.date(row.expectedAvailableDate),expectedTip(c,row)):'Date unknown';
    return `<div class="request-availability-result ${c.esc(row.status)}">${c.icon(status.icon)}<div><strong>${c.esc(status.label)} · ${expected}</strong><p>${m(c,row.availableByShipBy,readyTip(c,row))} of ${m(c,row.remainingQty,openTip(c,row))} open units covered by ${t(c,c.date(row.shipBy),'The requested latest shipping date. For older requests, requested arrival minus transit days gives this date.')}.</p>${row.shortfallQty?'<p>'+m(c,row.shortfallQty,gapTip(c,row))+' units short by the deadline.</p>':''}${row.allocatedQty?'<p>'+m(c,row.allocatedQty,`${c.n(row.allocatedQty)} open allocation units are assigned to this request; this is a commitment, not additional inventory.`)+' open units allocated.</p>':''}</div></div>`;
  }
  function listEmpty(c){const missing=!c.state.asics.length||!c.state.projects.length;return `<div class="empty entity-empty request-empty">${c.icon('target')}<h2>No requests yet</h2><p>${missing?'Add an ASIC and a project, then create a request.':'Create a request with a quantity and ship-by date.'}</p><div class="onboarding-actions">${!c.state.asics.length?c.btn('Add ASIC','new-asic','chip'):''}${!c.state.projects.length?c.btn('Add project','new-project','folder'):''}${c.btn('New request','new-request','plus','','primary')}</div></div>`;}
  function renderRequests(c){
    const {state,ui,esc,n,date,btn,title,table,options,pill}=c,all=checkRows(c),query=(ui.query||'').trim().toLowerCase();
    const list=all.filter(r=>{const event=state.events.find(e=>e.id===r.eventId)||{};return (!ui.requestAsicId||r.asicId===ui.requestAsicId)&&(!ui.requestProjectId||r.projectId===ui.requestProjectId)&&(!ui.requestStatus||r.status===ui.requestStatus)&&[reference(event),c.lookupA(r.asicId)?.name,c.lookupP(r.projectId)?.name,event.note].join(' ').toLowerCase().includes(query);}).sort((a,b)=>a.shipBy.localeCompare(b.shipBy)||a.eventId.localeCompare(b.eventId));
    const rows=list.map(r=>{
      const event=state.events.find(e=>e.id===r.eventId)||{},status=config(r),attr=`data-id="${esc(r.eventId)}"`;
      const expected=r.status==='shipped'?'Completed':r.expectedAvailableDate?'Ready '+t(c,date(r.expectedAvailableDate),expectedTip(c,r)):'Availability date unknown';
      const coverage=r.status==='shipped'?m(c,r.shippedQty,`${n(r.shippedQty)} completed shipment units matched to this request.`)+' shipped':m(c,r.availableByShipBy,readyTip(c,r))+' / '+m(c,r.remainingQty,openTip(c,r))+' open units covered';
      return `<tr><td><button class="text-btn request-reference" data-action="view-request" ${attr}>${esc(reference(event))}</button><span class="table-secondary">${esc(c.lookupA(r.asicId)?.name||'Unknown ASIC')}</span></td><td><strong>${esc(c.lookupP(r.projectId)?.name||'Unknown project')}</strong></td><td class="num">${m(c,r.qty,`${n(r.qty)} units entered on this request. ${n(r.shippedQty)} have shipped and ${n(r.remainingQty)} remain open.`)}</td><td>${t(c,date(r.shipBy),'The requested latest shipping date. For older requests, requested arrival minus transit days gives this date.')}</td><td>${pill(status.label,status.tone)}<span class="table-secondary">${expected}</span><span class="table-secondary request-coverage">${coverage}</span>${r.shortfallQty?'<span class="table-secondary negative">'+m(c,r.shortfallQty,gapTip(c,r))+' short by deadline</span>':''}</td><td>${btn('View details','view-request','info',attr,'small')}</td></tr>`;
    });
    const counts={open:all.filter(r=>r.status!=='shipped').length,onTime:all.filter(r=>r.status==='on-time').length,risk:all.filter(r=>['late','shortfall'].includes(r.status)).length};
    const stat=(label,value,explanation,tone='')=>`<div class="summary-item ${tone}"><span>${label}</span><strong>${m(c,value,explanation)}</strong></div>`;
    const active=ui.requestAsicId||ui.requestProjectId||ui.requestStatus||query;
    return title('Demand','Requests','Track quantities, ship-by dates, and availability.',btn('New request','new-request','plus','','primary'))+
      `<div class="summary-strip">${stat('Open',counts.open,`${n(counts.open)} of ${n(all.length)} workspace requests still have units to ship. List filters do not change this total.`)}${stat('On time',counts.onTime,`${n(counts.onTime)} workspace requests have enough recorded supply by their ship-by dates. List filters do not change this total.`)}${stat('At risk',counts.risk,`${n(counts.risk)} workspace requests have late or insufficient supply. List filters do not change this total.`,counts.risk?'warning':'')}</div>`+
      `<div class="toolbar request-filter-bar"><input class="table-search" aria-label="Search requests" data-search="query" placeholder="Search requests…" value="${esc(ui.query||'')}"><div class="control"><select data-filter="requestAsicId" aria-label="Filter request ASIC">${options(state.asics,ui.requestAsicId||'','All ASICs')}</select></div><div class="control"><select data-filter="requestProjectId" aria-label="Filter request project">${options(state.projects,ui.requestProjectId||'','All projects')}</select></div><div class="control"><select data-filter="requestStatus" aria-label="Filter request availability">${options(Object.entries(STATUS).map(([id,v])=>({id,name:v.label})),ui.requestStatus||'','All availability')}</select></div>${active?'<button class="filter-reset" data-action="clear-request-filters">Clear filters</button>':''}<div class="secondary-actions">${btn('Supply','navigate','box','data-page="supply"','small')}${btn('Allocations','navigate','calendar','data-page="allocations"','small')}</div></div>`+
      `<section class="panel workflow-list request-list">${all.length?table(HEADERS,rows,`<span>${m(c,list.length,`${n(list.length)} requests match the current search and filters.`)} of ${m(c,all.length,`${n(all.length)} saved request records in this workspace.`)} requests</span>`):emptyHeaders(c)+listEmpty(c)}</section>`+basis(c);
  }
  function availabilityPreview(c,draft){
    const valid=draft&&c.T.isDate(draft.requestedShipDate)&&c.lookupA(draft.asicId)&&c.lookupP(draft.projectId)&&Number.isSafeInteger(draft.qty)&&draft.qty>0&&Number.isInteger(draft.shipDays)&&draft.shipDays>=0;
    if(!valid)return `<div class="request-preview-placeholder">${c.icon('calendar')}<div><strong>Check availability</strong><p>Select an ASIC and project, then enter quantity and ship-by date.</p></div></div>`;
    const projected={...c.state,events:c.state.events.filter(e=>e.id!==draft.id).concat(draft)},row=c.T.requestAvailability(projected,{asOf:c.referenceDate()}).find(r=>r.eventId===draft.id);if(!row)return '';
    return summary(c,row)+`<p class="request-arrival-preview">Requested arrival: <strong>${t(c,c.date(row.arrivalDate),`${c.date(row.shipBy)} ship-by date + ${c.n(draft.shipDays)} transit days = ${c.date(row.arrivalDate)} requested arrival.`)}</strong> · ${m(c,draft.shipDays,'Transit days entered on this request; the initial value comes from the project’s ASIC-specific lead time or project default.')} transit days</p>`;
  }
  function requestForm(c,eventId='') {
    const old=c.state.events.find(e=>e.id===eventId&&e.type==='request');
    c.setEditing(old?.id||'');
    if(!c.state.asics.length||!c.state.projects.length){
      c.openDrawer('Create a request','Set up the ASIC and project before requesting supply.',`<div class="drawer-body"><div class="notice info">${c.icon('info')}A request needs an ASIC and a project so its demand can be tracked.</div><div class="onboarding-actions">${!c.state.asics.length?c.btn('Add ASIC','new-asic','chip','','primary'):''}${!c.state.projects.length?c.btn('Add project','new-project','folder','','primary'):''}</div></div>`,`<div class="drawer-footer">${c.btn('Close','close-drawer')}</div>`);return;
    }
    const projectId=old?.projectId||c.ui.requestProjectId||'',asicId=old?.asicId||c.ui.requestAsicId||'';
    const project=c.lookupP(projectId);
    const shipDays=old?.shipDays??project?.leadTimes?.[asicId]??project?.leadDays??0;
    const shipBy=old?c.T.requestShipBy(old):c.referenceDate();
    const draft={...old,id:old?.id||'request-preview',type:'request',projectId,asicId,qty:old?.qty||0,shipDays,requestedShipDate:shipBy,date:old?.date||shipBy};
    const {esc,field,selectField,openDrawer}=c;
    openDrawer(old?'Edit request':'New request','Set when these ASICs need to leave the supply pool.',
      `<form id="request-form"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div><div class="form-grid">${selectField('Project','requestProjectId',c.state.projects,projectId,true,true,'Select project…')}${selectField('ASIC','requestAsicId',c.state.asics,asicId,true,true,'Select ASIC…')}<div class="field"><label for="f-requestQty">Quantity<span class="required">*</span></label><input id="f-requestQty" name="requestQty" type="number" min="1" step="1" value="${old?esc(old.qty):''}" required></div>${field('Ship by','requestedShipDate',shipBy,'date',false,true,'The latest date the ASICs should be available to ship.')}${field('Transit days','requestShipDays',shipDays,'number',false,true,'Used to calculate the requested arrival date.')}<div class="field full"><label for="f-requestNote">Note</label><textarea id="f-requestNote" name="requestNote" placeholder="Add context for this request…">${esc(old?.note||'')}</textarea><small>Optional.</small></div></div><div id="request-availability-preview" class="request-availability-preview" aria-live="polite">${availabilityPreview(c,draft)}</div>${basis(c)}</div>${c.formFoot(old?'Save request':'Create request')}</form>`);
  }
  function viewRequest(c,eventId){
    const event=c.state.events.find(e=>e.id===eventId&&e.type==='request');if(!event)return;const row=checkRows(c).find(r=>r.eventId===eventId);if(!row)return;
    const {esc,n,date,btn,openDrawer}=c;
    const values=[['ASIC',esc(c.lookupA(event.asicId)?.name||'Unknown ASIC')],['Project',esc(c.lookupP(event.projectId)?.name||'Unknown project')],['Requested',m(c,event.qty,`${n(event.qty)} units entered on this request.`)+' units'],['Ship by',t(c,date(row.shipBy),'Latest shipping date requested; older requests use arrival minus transit days.')],['Requested arrival',t(c,date(row.arrivalDate),`${date(row.shipBy)} ship by + ${n(event.shipDays)} transit days = ${date(row.arrivalDate)} requested arrival.`)],['Transit',m(c,event.shipDays,'Transit days stored on this request, initially copied from the project/ASIC lead time.')+' days'],['Shipped',m(c,row.shippedQty,`${n(row.shippedQty)} completed shipment units matched by request link or by ASIC/project in ship-by order.`)+' units'],['Open',m(c,row.remainingQty,openTip(c,row))+' units'],['Allocated (open)',m(c,row.allocatedQty||0,`${n(row.allocatedQty||0)} open allocation units assigned to this request; ${n(row.allocatedAvailableByShipBy||0)} are backed by supply by its deadline.`)+' units']];
    openDrawer(esc(reference(event)),'Request details',`<div class="drawer-body"><div class="info-grid">${values.map(([label,value])=>'<div><small>'+esc(label)+'</small><strong>'+value+'</strong></div>').join('')}</div><p class="form-section">Availability</p>${summary(c,row)}${event.note?'<p class="form-section">Note</p><p class="request-detail-note">'+esc(event.note)+'</p>':''}${basis(c)}</div>`,`<div class="drawer-footer">${row.remainingQty?btn(row.allocatedQty?'Change allocation':'Allocate ASICs',row.allocatedQty?'request-allocations':'allocate-request','calendar',`data-id="${esc(eventId)}"`):''}${btn('Delete request','delete-request','trash',`data-id="${esc(eventId)}"`,'danger')}${btn('Edit request','edit-request','edit',`data-id="${esc(eventId)}"`,'primary')}</div>`);
  }
  window.RequestViews={renderRequests,requestForm,availabilityPreview,viewRequest};
})();
