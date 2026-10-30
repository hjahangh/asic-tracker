/* Inventory views and receipt forms for the local workspace. */
(() => {
  'use strict';
  const HEADERS=['ASIC','#On hand','#Reserved','#Free to allocate','#Incoming','Actions'];
  const total=(rows,key)=>rows.reduce((sum,row)=>sum+(Number(row[key])||0),0);
  const rowsOf=c=>c.T.supplyRows(c.state,{asOf:c.referenceDate()});
  const summariesOf=c=>c.T.supplySummary(c.state,{asOf:c.referenceDate()});
  const number=(c,value,copy)=>c.metric(value,copy);
  const onHandCopy=(c,row)=>`${c.n(row.receivedQty)} units recorded as available minus ${c.n(row.shippedQty)} completed shipments for this ASIC. The displayed on-hand balance is ${c.n(row.onHandQty)}; it cannot be negative.`;
  const reservedCopy=(c,row)=>`${c.n(row.reservedQty)} on-hand units are held by open allocations. Reservations against incoming supply are excluded from this number.`;
  const freeCopy=(c,row)=>`${c.n(row.onHandQty)} on hand minus ${c.n(row.reservedQty)} reserved by open allocations = ${c.n(row.freeQty)} units free to allocate. Unallocated requests do not reduce inventory.`;
  const incomingCopy=(c,row)=>`${c.n(row.incomingQty)} units across incoming entries for this ASIC. ${c.n(row.overdueQty)} are overdue; overdue incoming entries need a new date or receipt confirmation before they support availability.`;
  function headers(c){return '<div class="table-scroll"><table><thead><tr>'+HEADERS.map(h=>'<th'+(h.startsWith('#')?' class="num"':'')+'>'+c.esc(h.replace(/^#/,''))+'</th>').join('')+'</tr></thead><tbody></tbody></table></div>';}
  function summaryStrip(c,rows){
    const count=rows.length,onHand=total(rows,'onHandQty'),reserved=total(rows,'reservedQty'),free=total(rows,'freeQty');
    const item=(label,value,copy)=>'<div class="summary-item"><span>'+label+'</span><strong>'+number(c,value,copy)+'</strong><small>units</small></div>';
    return `<div class="summary-strip supply-summary">${item('On hand',onHand,`Sum of on-hand balances across ${c.n(count)} matching ASICs: ${c.n(onHand)} units. Each ASIC balance is recorded available inventory minus completed shipments, floored at zero.`)}${item('Reserved',reserved,`Sum of on-hand inventory held by open allocations across the ${c.n(count)} matching ASICs: ${c.n(reserved)} units. Future incoming reservations are excluded.`)}${item('Free to allocate',free,`${c.n(onHand)} on hand minus ${c.n(reserved)} reserved = ${c.n(free)} units free across the matching ASICs.`)}</div>`;
  }
  function basis(c){return `<details class="supply-basis request-basis"><summary>${c.icon('info')}How inventory is counted</summary><p>On hand is available inventory minus completed shipments. Reserved units are held by open allocations; the rest are free to allocate. Requests alone do not reduce inventory.</p><p>Incoming inventory is shown separately. Confirm a receipt when it becomes available, or receive part of an entry and keep the remainder incoming. An overdue incoming entry needs its date updated or its receipt confirmed before it supports request availability.</p></details>`;}
  function renderSupply(c){
    const {state,ui,esc,btn,title,options,table}=c,query=(ui.query||'').trim().toLowerCase();
    const all=summariesOf(c),list=all.filter(row=>{
      const asic=c.lookupA(row.asicId);
      return (!ui.supplyAsicId||row.asicId===ui.supplyAsicId)&&[asic?.name,...(asic?.mpns||[])].join(' ').toLowerCase().includes(query);
    }).sort((a,b)=>(c.lookupA(a.asicId)?.name||'').localeCompare(c.lookupA(b.asicId)?.name||''));
    const rows=list.map(row=>{
      const asic=c.lookupA(row.asicId),attr=`data-id="${esc(row.asicId)}"`;
      return `<tr><td><strong>${esc(asic?.name||'Unknown ASIC')}</strong></td><td class="num">${number(c,row.onHandQty,onHandCopy(c,row))}</td><td class="num">${number(c,row.reservedQty,reservedCopy(c,row))}</td><td class="num"><strong>${number(c,row.freeQty,freeCopy(c,row))}</strong></td><td class="num">${number(c,row.incomingQty,incomingCopy(c,row))}${row.overdueQty?'<span class="table-secondary negative">'+number(c,row.overdueQty,`${c.n(row.overdueQty)} incoming units have an expected date before ${c.date(c.referenceDate())} and are not confirmed received.`)+' overdue</span>':''}</td><td>${btn('View inventory','view-supply','box',attr,'small')}</td></tr>`;
    });
    const empty=`<div class="empty entity-empty supply-empty">${c.icon('box')}<h2>Your inventory starts here</h2><p>Add an ASIC, then record inventory as it arrives or enter an expected incoming quantity.</p>${btn('Add ASIC','new-asic','chip','','primary')}</div>`;
    return title('Inventory','Supply','Track inventory and incoming ASICs.',btn('Add inventory','new-supply','plus','','primary'))+
      summaryStrip(c,list)+
      `<div class="toolbar supply-filter-bar"><input class="table-search" aria-label="Search supply" data-search="query" placeholder="Search ASIC or MPN…" value="${esc(ui.query||'')}"><div class="control"><select aria-label="Filter supply ASIC" data-filter="supplyAsicId">${options(state.asics,ui.supplyAsicId||'','All ASICs')}</select></div>${ui.supplyAsicId||query?'<button class="filter-reset" data-action="clear-supply-filters">Clear filters</button>':''}</div>`+
      `<section class="panel entity-list supply-list">${!state.asics.length?headers(c)+empty:table(HEADERS,rows,`<span>${number(c,list.length,`${c.n(list.length)} ASICs match the current supply filters, out of ${c.n(all.length)} ASICs in the inventory summary.`)} ASIC${list.length===1?'':'s'}</span><span>Hover over a number for its calculation</span>`)}</section>`+basis(c);
  }
  function supplyForm(c,eventId='',asicId=''){
    const old=c.state.events.find(e=>e.id===eventId&&e.type==='expected_ship');
    c.setEditing(old?.id||'');
    if(!c.state.asics.length){c.openDrawer('Add inventory','Create an ASIC first.',`<div class="drawer-body"><p class="setting-description">Inventory needs an ASIC from your library.</p>${c.btn('Add ASIC','new-asic','chip','','primary')}</div>`,`<div class="drawer-footer">${c.btn('Close','close-drawer')}</div>`);return;}
    const row=old&&rowsOf(c).find(r=>r.eventId===old.id),status=old?.supplyStatus||row?.status||'available',date=old?.date||c.referenceDate();
    c.openDrawer(old?'Edit inventory':'Add inventory','Record a receipt or an incoming quantity.',
      `<form id="supply-form"><input type="hidden" name="supplyEventId" value="${c.esc(old?.id||'')}"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div><div class="form-grid">${c.selectField('ASIC','supplyAsicId',c.state.asics,old?.asicId||asicId||c.ui.supplyAsicId||'',true,true,'Select ASIC…')}<div class="field"><label for="f-supplyQty">Quantity<span class="required">*</span></label><input id="f-supplyQty" name="supplyQty" type="number" min="1" step="1" value="${c.esc(old?.qty||'')}" required><small>Units in this entry, not a replacement stock balance.</small></div>${c.selectField('Inventory type','supplyStatus',[{id:'available',name:'Available inventory'},{id:'incoming',name:'Incoming inventory'}],status,false,true)}${c.field('Inventory date','supplyDate',date,'date',false,true,'Available inventory: receipt date. Incoming inventory: expected date.')}${c.field('Reference','supplyReference',old?.supplyReference||'','text',false,false,'Optional delivery or purchase reference.')}<div class="field full"><label for="f-supplyNote">Note</label><textarea id="f-supplyNote" name="supplyNote" placeholder="Add context for this inventory entry…">${c.esc(old?.note||'')}</textarea><small>Optional.</small></div></div></div>${c.formFoot(old?'Save inventory':'Add inventory')}</form>`);
  }
  function receiveForm(c,eventId){
    const event=c.state.events.find(e=>e.id===eventId&&e.type==='expected_ship'),row=rowsOf(c).find(r=>r.eventId===eventId);if(!event||!row)return;
    c.setEditing(eventId);
    if(row.status!=='incoming'){c.openDrawer('Inventory already available','This entry has already been counted as available.',`<div class="drawer-body"><p class="setting-description">Edit this inventory entry to correct its quantity or date.</p></div>`,`<div class="drawer-footer">${c.btn('Close','close-drawer')}${c.btn('Edit inventory','edit-supply','edit',`data-id="${c.esc(eventId)}"`,'primary')}</div>`);return;}
    c.openDrawer('Receive inventory','Confirm the quantity that has become available.',
      `<form id="supply-receive-form"><input type="hidden" name="supplyEventId" value="${c.esc(eventId)}"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div><div class="supply-receive-source"><strong>${c.esc(c.lookupA(event.asicId)?.name||'Unknown ASIC')}</strong><p>${number(c,event.qty,`${c.n(event.qty)} units are recorded in this incoming entry before this receipt.`)} units incoming${event.supplyReference?' · '+c.esc(event.supplyReference):''}</p></div><div class="form-grid"><div class="field"><label for="f-receiveQty">Quantity received<span class="required">*</span></label><input id="f-receiveQty" name="receiveQty" type="number" min="1" max="${event.qty}" step="1" value="${event.qty}" required><small>Up to ${number(c,event.qty,'The maximum receipt is the current incoming quantity of this entry.')} units.</small></div>${c.field('Available date','receiveDate',c.referenceDate(),'date',false,true,'Use the actual receipt date, today or earlier.')}<div class="field full"><label for="f-receiveNote">Note</label><textarea id="f-receiveNote" name="receiveNote" placeholder="Optional receipt note…"></textarea></div></div><p class="subtitle">A partial receipt keeps the remaining units incoming. Receiving the full entry updates it without adding duplicate supply.</p></div>${c.formFoot('Receive inventory')}</form>`);
  }
  function viewSupply(c,asicId){
    const asic=c.lookupA(asicId);if(!asic)return;
    const summary=summariesOf(c).find(r=>r.asicId===asicId)||{asicId,receivedQty:0,shippedQty:0,onHandQty:0,reservedQty:0,freeQty:0,incomingQty:0,overdueQty:0,stockGapQty:0};
    const lots=rowsOf(c).filter(r=>r.asicId===asicId).sort((a,b)=>b.date.localeCompare(a.date)||a.eventId.localeCompare(b.eventId));
    const rows=lots.map(row=>{
      const event=c.state.events.find(e=>e.id===row.eventId)||{},available=row.status==='available',attr=`data-id="${c.esc(row.eventId)}"`;
      const type=row.overdue?c.pill('Overdue','amber'):c.pill(available?'Available':'Incoming',available?'blue':'gray');
      const date=c.tip(c.date(row.date),available?'Recorded receipt date used to count this entry as available.':'Expected availability date recorded for this incoming entry.');
      const balance=available?`${number(c,row.onHandQty,`${c.n(row.qty)} received units less ${c.n(row.consumedQty)} units consumed by completed shipments = ${c.n(row.onHandQty)} units on hand in this entry.`)} on hand<span class="table-secondary">${number(c,row.reservedQty,`${c.n(row.reservedQty)} on-hand units from this entry are held by open allocations.`)} reserved · ${number(c,row.freeQty,`${c.n(row.onHandQty)} on hand minus ${c.n(row.reservedQty)} reserved = ${c.n(row.freeQty)} free units from this entry.`)} free</span>`:'Awaiting receipt';
      return `<tr><td>${date}${event.supplyReference?'<span class="table-secondary">'+c.esc(event.supplyReference)+'</span>':''}${event.note?'<details class="supply-entry-note"><summary>Note</summary><p>'+c.esc(event.note)+'</p></details>':''}</td><td>${type}</td><td class="num">${number(c,row.qty,available?`${c.n(row.qty)} units were recorded as available in this inventory entry.`:`${c.n(row.qty)} units are expected in this incoming inventory entry.`)}</td><td>${balance}</td><td><div class="row-actions">${c.btn('Edit','edit-supply','edit',attr,'small')}${!available?c.btn('Receive','receive-supply','check',attr,'small'):''}${c.btn('Delete','delete-supply','trash',attr,'small danger')}</div></td></tr>`;
    });
    const gap=summary.stockGapQty?`<p class="notice">${c.icon('info')}${number(c,summary.stockGapQty,`${c.n(summary.shippedQty)} completed shipments exceed ${c.n(summary.receivedQty)} recorded available units by ${c.n(summary.stockGapQty)} units.`)} shipped units have no matching recorded receipt. Add missing inventory history to reconcile the balance.</p>`:'';
    c.openDrawer(c.esc(asic.name),'Inventory entries',`<div class="drawer-body">${summaryStrip(c,[summary])}${gap}<section class="panel supply-entry-list">${c.table(['Inventory date','Type','#Quantity','Balance','Actions'],rows,lots.length?'<span>'+number(c,lots.length,`${c.n(lots.length)} recorded supply entries for this ASIC.`)+' inventory entries</span>':'')}</section>${!lots.length?'<p class="subtitle">No inventory entries yet. Add an available receipt or an incoming quantity.</p>':''}${basis(c)}</div>`,`<div class="drawer-footer">${c.btn('Close','close-drawer')}${c.btn('Add inventory','new-supply','plus',`data-id="${c.esc(asicId)}"`,'primary')}</div>`,{wide:true});
  }
  window.SupplyViews={renderSupply,supplyForm,receiveForm,viewSupply};
})();
