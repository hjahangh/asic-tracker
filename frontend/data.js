/* ASIC Tracker calculation and validation library. Persistence lives in api-store.js. */
(function () {
  'use strict';
  const VERSION = 2;
  function todayPacific() {
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const p=Object.fromEntries(parts.map(x=>[x.type,x.value])); return p.year+'-'+p.month+'-'+p.day;
  }
  function entityName(state,project) { return state.businessEntities.find(x=>x.id===project.businessEntityId)?.name || project.entity || ''; }
  function fundingName(state,project) { return state.fundingSources.find(x=>x.id===project.fundingSourceId)?.name || project.funding || ''; }
  const TYPES = ['expected_ship', 'request', 'expected_fulfilment', 'actual_ship', 'actual_fulfilment'];
  const labels = {expected_ship:'Expected ship',request:'Request by',expected_fulfilment:'Expected fulfilment',actual_ship:'Actual ship',actual_fulfilment:'Actual fulfilment'};
  const clone = value => JSON.parse(JSON.stringify(value));
  const dateOf = date => new Date(date + 'T12:00:00Z');
  const stamp = date => date.toISOString().slice(0, 10);
  const isDate = date => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(+dateOf(date)) && stamp(dateOf(date)) === date;
  function monday(date) {
    const d = dateOf(date); if (!Number.isFinite(+d)) return '';
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return stamp(d);
  }
  function isoWeek(date) {
    const d = dateOf(date); if (!Number.isFinite(+d)) return '';
    d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
    const year = d.getUTCFullYear();
    const jan4 = new Date(Date.UTC(year, 0, 4, 12));
    const firstThursday = new Date(jan4); firstThursday.setUTCDate(jan4.getUTCDate() + 3 - ((jan4.getUTCDay() + 6) % 7));
    const week = Math.round((d - firstThursday) / 604800000) + 1;
    return `${year}-W${String(week).padStart(2, '0')}`;
  }
  function quarterOf(date) { return `${date.slice(0, 4)}-Q${Math.ceil(Number(date.slice(5, 7)) / 3)}`; }
  function requestShipBy(event) {
    if (isDate(event.requestedShipDate)) return event.requestedShipDate;
    if (!isDate(event.date)) return '';
    const days=Number.isInteger(event.shipDays)&&event.shipDays>=0?event.shipDays:0;
    const value=dateOf(event.date); value.setUTCDate(value.getUTCDate()-days);
    return Number.isFinite(+value)?stamp(value):'';
  }
  function allocationShipBy(state,event) {
    if (isDate(event.availableShipDate)) return event.availableShipDate;
    if (!isDate(event.date)) return '';
    const project=(state.projects||[]).find(p=>p.id===event.projectId);
    const configured=project?.leadTimes?.[event.asicId]??project?.leadDays??0;
    const days=Number.isInteger(configured)&&configured>=0?configured:0;
    const value=dateOf(event.date);value.setUTCDate(value.getUTCDate()-days);
    return Number.isFinite(+value)?stamp(value):'';
  }
  function creationDate(createdAt) {
    if (!createdAt||isDate(createdAt)) return createdAt||'';
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(createdAt));
    const values=Object.fromEntries(parts.map(p=>[p.type,p.value]));
    return values.year+'-'+values.month+'-'+values.day;
  }
  function allocationPlan(state,{asOf=todayPacific()}={}) {
    if (!isDate(asOf)) throw new Error('Availability needs a valid as-of date.');
    const order=(a,b)=>a.shipBy.localeCompare(b.shipBy)||String(a.createdAt||'').localeCompare(String(b.createdAt||''))||a.eventId.localeCompare(b.eventId);
    const requests=state.events.filter(e=>e.type==='request').map(e=>({eventId:e.id,requestId:e.requestId||e.id,asicId:e.asicId,projectId:e.projectId,qty:e.qty,shipBy:requestShipBy(e),arrivalDate:e.date,createdAt:e.createdAt||'',shippedQty:0,shippedByShipBy:0,lastShippedDate:null,remainingQty:e.qty,availableByShipBy:0,shortfallQty:e.qty,expectedAvailableDate:null,status:'shortfall',allocatedQty:0,allocatedAvailableByShipBy:0})).sort(order);
    const allocations=state.events.filter(e=>e.type==='expected_fulfilment').map(e=>{
      const request=e.requestId?requests.find(r=>r.asicId===e.asicId&&r.projectId===e.projectId&&(r.eventId===e.requestId||r.requestId===e.requestId)):null;
      return {eventId:e.id,requestId:e.requestId||'',asicId:e.asicId,projectId:e.projectId,qty:e.qty,shipBy:allocationShipBy(state,e),arrivalDate:e.date,createdAt:e.createdAt||'',shippedQty:0,remainingQty:e.qty,reservedSupplyQty:0,unbackedQty:e.qty,boundRequestId:request?.eventId||'',lots:[]};
    }).sort(order);
    const requestCreated=new Map(requests.map(r=>[r.eventId,creationDate(r.createdAt)]));
    const allocationCreated=new Map(allocations.map(r=>[r.eventId,creationDate(r.createdAt)]));
    const allocationBaselines=new Map(state.events.filter(e=>e.type==='expected_fulfilment').map(e=>[e.id,new Set(e.priorShipmentIds||[])]));
    // Completed units keep their creation order even when future availability dates change.
    const creditAllocations=allocations.slice().sort((a,b)=>String(a.createdAt||'').localeCompare(String(b.createdAt||''))||a.eventId.localeCompare(b.eventId));
    // Only completed shipments consume stock. Explicit links are credited before general project FIFO.
    const shipments=state.events.filter(e=>e.type==='actual_ship'&&e.date<=asOf).slice().sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id));
    const shipmentCredits=new Map();
    const creditRequestShipment=shipment=>{
      let uncredited=shipment.qty;const credits=[];
      const candidates=requests.filter(r=>r.asicId===shipment.asicId&&r.projectId===shipment.projectId&&(shipment.requestId?(r.requestId===shipment.requestId||r.eventId===shipment.requestId):requestCreated.get(r.eventId)<=shipment.date));
      for (const row of candidates) {
        const quantity=Math.min(uncredited,row.remainingQty);if (!quantity) continue;
        row.shippedQty+=quantity;row.remainingQty-=quantity;uncredited-=quantity;
        credits.push({eventId:row.eventId,qty:quantity});
        if (shipment.date<=row.shipBy) row.shippedByShipBy+=quantity;
        if (!row.lastShippedDate||shipment.date>row.lastShippedDate) row.lastShippedDate=shipment.date;
        if (!uncredited) break;
      }
      shipmentCredits.set(shipment.id,credits);
    };
    const completed=shipments.filter(e=>e.requestId).concat(shipments.filter(e=>!e.requestId));
    completed.forEach(creditRequestShipment);
    // The same completed units reduce their allocation commitments, not a second physical stock pool.
    for (const shipment of completed) {
      let uncredited=shipment.qty;
      for (const credit of shipmentCredits.get(shipment.id)||[]) {
        let remainingCredit=credit.qty;
        const candidates=creditAllocations.filter(a=>a.asicId===shipment.asicId&&a.projectId===shipment.projectId&&a.boundRequestId===credit.eventId&&!allocationBaselines.get(a.eventId).has(shipment.id)&&(shipment.requestId||allocationCreated.get(a.eventId)<=shipment.date));
        for (const allocation of candidates) {
          const quantity=Math.min(remainingCredit,allocation.remainingQty);if (!quantity) continue;
          allocation.shippedQty+=quantity;allocation.remainingQty-=quantity;uncredited-=quantity;remainingCredit-=quantity;
          if (!remainingCredit) break;
        }
      }
      const general=creditAllocations.filter(a=>a.asicId===shipment.asicId&&a.projectId===shipment.projectId&&!a.boundRequestId&&!allocationBaselines.get(a.eventId).has(shipment.id)&&allocationCreated.get(a.eventId)<=shipment.date);
      for (const allocation of general) {
        const quantity=Math.min(uncredited,allocation.remainingQty);if (!quantity) continue;
        allocation.shippedQty+=quantity;allocation.remainingQty-=quantity;uncredited-=quantity;
        if (!uncredited) break;
      }
    }
    const supply=state.events.filter(e=>e.type==='expected_ship').slice().sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id)).map(e=>({eventId:e.id,asicId:e.asicId,qty:e.qty,date:e.date,status:e.supplyStatus==='incoming'?'incoming':e.date<=asOf?'available':'incoming',overdue:e.supplyStatus==='incoming'&&e.date<asOf,consumedQty:0,onHandQty:0,reservedQty:0,freeQty:0,reference:e.supplyReference||'',note:e.note||''}));
    const supplyById=new Map(supply.map(row=>[row.eventId,row])),pools=new Map();
    // Explicit overdue incoming lots remain unconfirmed and cannot establish a known readiness date.
    supply.filter(row=>!row.overdue).forEach(row=>{
      if (!pools.has(row.asicId)) pools.set(row.asicId,[]);
      pools.get(row.asicId).push({eventId:row.eventId,sourceDate:row.date,date:row.date<asOf?asOf:row.date,qty:row.qty,onHand:row.status==='available'&&row.date<=asOf});
    });
    pools.forEach(pool=>pool.sort((a,b)=>a.date.localeCompare(b.date)||Number(b.onHand)-Number(a.onHand)||a.sourceDate.localeCompare(b.sourceDate)||a.eventId.localeCompare(b.eventId)));
    const shippedByAsic=new Map();shipments.forEach(e=>shippedByAsic.set(e.asicId,(shippedByAsic.get(e.asicId)||0)+e.qty));
    for (const [asicId,pool] of pools) {
      let consumed=shippedByAsic.get(asicId)||0;
      // Completed shipments deplete confirmed receipts first; any stock gap conservatively reduces future supply.
      const consumptionOrder=pool.filter(lot=>lot.onHand).concat(pool.filter(lot=>!lot.onHand));
      for (const lot of consumptionOrder) {const quantity=Math.min(consumed,lot.qty);lot.qty-=quantity;consumed-=quantity;supplyById.get(lot.eventId).consumedQty+=quantity;if (!consumed) break;}
    }
    supply.forEach(row=>{if(row.status==='available'&&row.date<=asOf)row.onHandQty=row.qty-row.consumedQty;});
    // Reserve physical supply before unallocated demand. Allocation promises never create additional units.
    for (const allocation of allocations) {
      let needed=allocation.remainingQty;
      for (const lot of pools.get(allocation.asicId)||[]) {
        const quantity=Math.min(needed,lot.qty);if (!quantity) continue;
        lot.qty-=quantity;needed-=quantity;
        allocation.lots.push({date:[lot.date,allocation.shipBy,asOf].sort().pop(),qty:quantity});
        if(lot.onHand)supplyById.get(lot.eventId).reservedQty+=quantity;
        allocation.reservedSupplyQty+=quantity;if (!needed) break;
      }
      allocation.unbackedQty=needed;
    }
    // Inventory free-to-allocate excludes explicit commitments, not the tentative request queue.
    supply.forEach(row=>{row.freeQty=row.onHandQty-row.reservedQty;});
    const reservedForRequest=new Map(requests.map(r=>[r.eventId,[]]));
    // Specific request allocations are assigned first; project allocations use the remaining demand in deadline order.
    for (const allocation of allocations.filter(a=>a.boundRequestId).concat(allocations.filter(a=>!a.boundRequestId))) {
      let unassigned=allocation.remainingQty;
      const candidates=requests.filter(r=>r.asicId===allocation.asicId&&r.projectId===allocation.projectId&&(!allocation.boundRequestId||allocation.boundRequestId===r.eventId));
      for (const row of candidates) {
        const quantity=Math.min(unassigned,row.remainingQty-row.allocatedQty);if (!quantity) continue;
        row.allocatedQty+=quantity;unassigned-=quantity;
        let toReserve=quantity;
        for (const lot of allocation.lots) {
          const reserved=Math.min(toReserve,lot.qty);if (!reserved) continue;
          lot.qty-=reserved;toReserve-=reserved;
          reservedForRequest.get(row.eventId).push({date:lot.date,qty:reserved});
          if (lot.date<=row.shipBy) row.allocatedAvailableByShipBy+=reserved;
          if (!toReserve) break;
        }
        if (!unassigned) break;
      }
      // Any excess remains reserved to this project, including when there are no open matching requests.
    }
    for (const row of requests) {
      if (!row.remainingQty) {row.shortfallQty=0;row.status='shipped';continue;}
      let needed=row.remainingQty,lastDate=null;
      const lots=reservedForRequest.get(row.eventId).concat(pools.get(row.asicId)||[]);
      for (const lot of lots) {
        const quantity=Math.min(needed,lot.qty);if (!quantity) continue;
        lot.qty-=quantity;needed-=quantity;
        if (!lastDate||lot.date>lastDate) lastDate=lot.date;
        if (lot.date<=row.shipBy) row.availableByShipBy+=quantity;
        if (!needed) break;
      }
      row.shortfallQty=row.remainingQty-row.availableByShipBy;
      row.expectedAvailableDate=needed?null:lastDate;
      row.status=needed?'shortfall':lastDate<=row.shipBy?'on-time':'late';
    }
    return {requests,allocations:allocations.map(({boundRequestId,lots,...allocation})=>allocation),supply};
  }
  function requestAvailability(state,options={}) {return allocationPlan(state,options).requests;}
  function allocationRows(state,options={}) {return allocationPlan(state,options).allocations;}
  function supplyRows(state,options={}) {return allocationPlan(state,options).supply.filter(row=>!options.asicId||row.asicId===options.asicId);}
  function supplySummary(state,options={}) {
    const asOf=options.asOf??todayPacific(),plan=allocationPlan(state,{asOf});
    const ids=new Set([...(state.asics||[]).map(a=>a.id),...state.events.map(e=>e.asicId)]);
    const summaries=new Map([...ids].filter(Boolean).map(asicId=>[asicId,{asicId,receivedQty:0,shippedQty:0,onHandQty:0,reservedQty:0,freeQty:0,incomingQty:0,overdueQty:0,stockGapQty:0}]));
    plan.supply.forEach(row=>{
      const summary=summaries.get(row.asicId);
      if(row.status==='available'&&row.date<=asOf)summary.receivedQty+=row.qty;
      else summary.incomingQty+=row.qty;
      if(row.overdue)summary.overdueQty+=row.qty;
      summary.onHandQty+=row.onHandQty;summary.reservedQty+=row.reservedQty;summary.freeQty+=row.freeQty;
    });
    state.events.filter(e=>e.type==='actual_ship'&&e.date<=asOf).forEach(e=>{summaries.get(e.asicId).shippedQty+=e.qty;});
    summaries.forEach(summary=>{summary.stockGapQty=Math.max(0,summary.shippedQty-summary.receivedQty);});
    return [...summaries.values()].filter(row=>!options.asicId||row.asicId===options.asicId);
  }
  function priceAt(asic, date) {
    if (!asic || asic.historicalPriceUnknown === true) return null;
    const quarter = quarterOf(date);
    const applicable = (asic.priceHistory || []).filter(x => /^\d{4}-Q[1-4]$/.test(x.quarter) && x.quarter <= quarter && typeof x.price === 'number' && Number.isFinite(x.price) && x.price >= 0).sort((a, b) => b.quarter.localeCompare(a.quarter));
    if (applicable.length) return applicable[0].price;
    if ((asic.priceHistory || []).length) return null;
    return typeof asic.price === 'number' && Number.isFinite(asic.price) && asic.price >= 0 ? asic.price : null;
  }
  function ancestors(state, projectId) {
    const ids = []; let current = state.projects.find(p => p.id === projectId);
    while (current && !ids.includes(current.id)) { ids.push(current.id); current = state.projects.find(p => p.id === current.parentId); }
    return ids;
  }
  function parentName(state, projectId) {
    const ids = ancestors(state, projectId); const root = state.projects.find(p => p.id === ids[ids.length - 1]);
    return root ? root.name : 'Unallocated';
  }
  function matchesEvent(state, event, filters = {}) {
    if (filters.asicId && filters.asicId !== event.asicId) return false;
    if (filters.projectId && filters.projectId !== event.projectId) return false;
    if (filters.parentId && !ancestors(state, event.projectId).includes(filters.parentId)) return false;
    if (filters.cutoff && event.date > filters.cutoff) return false;
    if (filters.type && event.type !== filters.type) return false;
    const p = (filters.phase || filters.funding || filters.entity) ? state.projects.find(p => p.id === event.projectId) : null;
    if (filters.phase && (event.phase || (p && p.phase)) !== filters.phase) return false;
    if (filters.funding && (!p || (p.fundingSourceId !== filters.funding && fundingName(state,p) !== filters.funding))) return false;
    if (filters.entity && (!p || (p.businessEntityId !== filters.entity && entityName(state,p) !== filters.entity))) return false;
    return true;
  }
  function stats(state, filters = {}) {
    const result = {demand:0,allocation:0,supply:0,shipped:0,fulfilled:0,balance:0};
    const measures = {request:'demand',expected_fulfilment:'allocation',expected_ship:'supply',actual_ship:'shipped',actual_fulfilment:'fulfilled'};
    state.events.filter(e => matchesEvent(state, e, filters)).forEach(e => { if (measures[e.type]) result[measures[e.type]] += Number(e.qty) || 0; });
    result.balance = result.allocation - result.demand;
    return result;
  }
  function weekly(state, filters = {}) {
    const cutoff = filters.cutoff || todayPacific();
    const matching = state.events.filter(e => matchesEvent(state, e, {...filters, cutoff}));
    if (!matching.length && !filters.start) return [];
    const start = monday(filters.start || matching.map(e => e.date).sort()[0]);
    const end = monday(cutoff);
    if (!start || !end || start > end) return [];
    const measures = {request:'demand',expected_fulfilment:'allocation',expected_ship:'supply',actual_ship:'shipped',actual_fulfilment:'fulfilled'};
    let balance = 0; const buckets = new Map();
    matching.forEach(e => {
      if (e.date < start) { balance += e.type === 'expected_fulfilment' ? e.qty : e.type === 'request' ? -e.qty : 0; return; }
      const week = monday(e.date);
      if (!buckets.has(week)) buckets.set(week,{demand:0,allocation:0,supply:0,shipped:0,fulfilled:0});
      const measure = measures[e.type]; if (measure) buckets.get(week)[measure] += e.qty;
    });
    const rows = [];
    for (let day = dateOf(start), count = 0; stamp(day) <= end && count < 5300; day.setUTCDate(day.getUTCDate() + 7), count++) {
      const week = stamp(day);
      const weekStats = buckets.get(week) || {demand:0,allocation:0,supply:0,shipped:0,fulfilled:0};
      balance += weekStats.allocation - weekStats.demand;
      rows.push({week,label:day.toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'}),...weekStats,balance});
    }
    return rows;
  }
  function financial(state, filters = {}) {
    const quarter = filters.quarter || quarterOf(todayPacific());
    const grouped = new Map();
    state.events.filter(e => ['request','actual_ship'].includes(e.type) && (!quarter || quarter === 'all' || quarterOf(e.date) === quarter) && matchesEvent(state,e,filters)).forEach(e => {
      const key = `${e.asicId}|${e.projectId}`; const a = state.asics.find(a => a.id === e.asicId); const p = state.projects.find(p => p.id === e.projectId);
      if (!grouped.has(key)) grouped.set(key,{asicId:e.asicId,asicName:a ? a.name : 'Unknown ASIC',projectId:e.projectId,projectName:p ? p.name : 'Unassigned',parentName:parentName(state,e.projectId),funding:p ? fundingName(state,p) : '',entity:p ? entityName(state,p) : '',requested:0,requestedValue:0,requestedKnownValue:0,shipped:0,shippedValue:0,shippedKnownValue:0,missingPrice:false,missingPriceCount:0,missingPriceQty:0});
      const row = grouped.get(key); const price = e.unitPriceVerified === true && typeof e.unitPrice === 'number' && Number.isFinite(e.unitPrice) && e.unitPrice >= 0 ? e.unitPrice : priceAt(a,e.date); const prefix = e.type === 'request' ? 'requested' : 'shipped';
      row[prefix] += e.qty; if (price === null) { row[prefix+'Value'] = null; row.missingPrice = true; row.missingPriceCount++; row.missingPriceQty += e.qty; } else { row[prefix+'KnownValue'] += e.qty * price; if (row[prefix+'Value'] !== null) row[prefix+'Value'] += e.qty * price; }
    });
    return [...grouped.values()].sort((a,b) => a.asicName.localeCompare(b.asicName) || a.projectName.localeCompare(b.projectName));
  }
  const isRecord = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]+$/.test(value) && !['__proto__','prototype','constructor'].includes(value);
  const validTimestamp = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value) && isDate(value.slice(0,10)) && Number.isFinite(Date.parse(value));
  function textFields(record,fields,label,errors) {
    fields.forEach(field=>{if(record[field]!==undefined && typeof record[field]!=='string')errors.push(`${label}: ${field} must be text.`);});
  }
  function validateMaster(records,label,errors) {
    const ids=new Set(),names=new Set();
    records.forEach((r,i)=>{
      if(!isRecord(r)){errors.push(`${label} ${i+1} is invalid.`);return;}
      if(!validId(r.id)||ids.has(r.id))errors.push(`${label} ${i+1} needs a unique valid ID.`);ids.add(r.id);
      const name=typeof r.name==='string'?r.name.trim().toLowerCase():'';
      if(!name||names.has(name))errors.push(`${label} ${i+1} needs a unique name.`);names.add(name);
      textFields(r,['description'],`${label} ${i+1}`,errors);
    });
    return ids;
  }
  function validateCore(state) {
    const errors=[];
    if(!isRecord(state))return ['Backup must contain an object.'];
    if(state.version!==VERSION)errors.push(`Unsupported backup version. Expected version ${VERSION}.`);
    for(const key of ['asics','projects','events','businessEntities','fundingSources','audit'])if(!Array.isArray(state[key]))errors.push(`${key} must be an array.`);
    if(errors.length)return errors;
    const asicIds=validateMaster(state.asics,'ASIC',errors);
    const projectIds=validateMaster(state.projects,'Project',errors);
    const businessIds=validateMaster(state.businessEntities,'Business entity',errors);
    const fundingIds=validateMaster(state.fundingSources,'Funding source',errors);
    if(!Array.isArray(state.projectFamilies)){
      if(state.projects.length)errors.push('Project families are required. Map legacy projects to a family before importing this backup.');
      else if(state.projectFamilies!==undefined)errors.push('projectFamilies must be an array.');
    }
    const families=Array.isArray(state.projectFamilies)?state.projectFamilies:[];
    const familyIds=validateMaster(families,'Project family',errors);
    families.forEach(family=>{
      if(!isRecord(family))return;
      if(!businessIds.has(family.businessEntityId))errors.push(`${family.name||'Family'} needs an existing business entity.`);
      if(!fundingIds.has(family.fundingSourceId))errors.push(`${family.name||'Family'} needs an existing funding source.`);
    });
    state.asics.forEach((a,i)=>{
      if(!isRecord(a))return;
      const label=typeof a.name==='string'?a.name:`ASIC ${i+1}`;
      if(typeof a.owner!=='string'||!a.owner.trim())errors.push(`${label} needs a supply chain owner.`);
      textFields(a,['marketing','plid','assembly','subtype','description'],label,errors);
      if(a.price!==null&&a.price!==undefined&&(typeof a.price!=='number'||!Number.isFinite(a.price)||a.price<0))errors.push(`${label}: price must be nonnegative or blank.`);
      for(const key of ['mpns','cpns'])if(!Array.isArray(a[key])||a[key].some(v=>typeof v!=='string'||!v.trim())||new Set(a[key]).size!==a[key].length)errors.push(`${label}: ${key} must contain unique text values.`);
      if(!Array.isArray(a.priceHistory)||a.priceHistory.some(h=>!isRecord(h)||!/^\d{4}-Q[1-4]$/.test(h.quarter)||typeof h.price!=='number'||!Number.isFinite(h.price)||h.price<0))errors.push(`${label}: price history is invalid.`);
      else if(new Set(a.priceHistory.map(h=>h.quarter)).size!==a.priceHistory.length)errors.push(`${label}: price history contains duplicate quarters.`);
      if(a.parts!==undefined&&!Array.isArray(a.parts))errors.push(`${label}: parts must be an array.`);
      if(Array.isArray(a.parts)){
        const partIds=new Set(),mpns=new Set();
        a.parts.forEach((part,index)=>{
          const partLabel=`${label}, part ${index+1}`;
          if(!isRecord(part)){errors.push(`${partLabel} is invalid.`);return;}
          if(!validId(part.id)||partIds.has(part.id))errors.push(`${partLabel} needs a unique valid ID.`);partIds.add(part.id);
          textFields(part,['mpn','cpn','plid','assembly','subtype'],partLabel,errors);
          const mpn=typeof part.mpn==='string'?part.mpn.trim():'';
          const hasOther=['cpn','plid','assembly','subtype'].some(k=>typeof part[k]==='string'&&part[k].trim());
          if(hasOther&&!mpn)errors.push(`${partLabel} needs an MPN when other part details are entered.`);
          if(mpn){const key=mpn.toLowerCase();if(mpns.has(key))errors.push(`${label}: part MPNs must be unique.`);mpns.add(key);}
        });
      }
    });
    state.projects.forEach((p,i)=>{
      if(!isRecord(p))return;
      const label=typeof p.name==='string'?p.name:`Project ${i+1}`;
      if(typeof p.manager!=='string'||!p.manager.trim())errors.push(`${label} needs an EPM.`);
      if(!familyIds.has(p.projectFamilyId))errors.push(`${label} needs an existing project family. Map legacy projects before import.`);
      const family=families.find(f=>f.id===p.projectFamilyId);
      if(family&&(p.businessEntityId!==family.businessEntityId||p.fundingSourceId!==family.fundingSourceId))errors.push(`${label}: ownership must be inherited from its project family.`);
      textFields(p,['scpm','parentId','projectFamilyId','key','businessEntityId','fundingSourceId','entity','funding','platform','phase','summary'],label,errors);
      if(p.prototype!==undefined&&p.prototype!==null&&typeof p.prototype!=='boolean')errors.push(`${label}: prototype must be yes, no, or unspecified.`);
      if(p.businessEntityId&&!businessIds.has(p.businessEntityId))errors.push(`${label}: business entity does not exist.`);
      if(p.fundingSourceId&&!fundingIds.has(p.fundingSourceId))errors.push(`${label}: funding source does not exist.`);
      for(const field of ['location','shippingLocation','actualShippingLocation','shipLocation'])if(Object.prototype.hasOwnProperty.call(p,field))errors.push(`${label}: shipping location is not supported in this workspace.`);
      if(!Array.isArray(p.asicIds)||p.asicIds.some(id=>!asicIds.has(id))||new Set(p.asicIds).size!==p.asicIds.length)errors.push(`${label}: associated ASICs must be unique existing ASIC IDs.`);
      if(p.leadTimes!==undefined&&(!isRecord(p.leadTimes)||Object.entries(p.leadTimes).some(([id,days])=>!asicIds.has(id)||!Number.isInteger(days)||days<0)))errors.push(`${label}: per-ASIC lead times are invalid.`);
      if(p.leadDays!==undefined&&p.leadDays!==null&&(!Number.isInteger(p.leadDays)||p.leadDays<0))errors.push(`${label}: lead time must be a nonnegative whole number.`);
      if(p.parentId&&!projectIds.has(p.parentId))errors.push(`${label}: parent project does not exist.`);
      const seen=new Set([p.id]);let current=state.projects.find(x=>isRecord(x)&&x.id===p.parentId);
      while(current){if(seen.has(current.id)){errors.push(`${label}: parent hierarchy contains a cycle.`);break;}seen.add(current.id);current=state.projects.find(x=>isRecord(x)&&x.id===current.parentId);}
    });
    const eventIds=new Set();
    state.events.forEach((e,i)=>{
      const label=`Event ${i+1}`;
      if(!isRecord(e)){errors.push(`${label} is invalid.`);return;}
      if(!validId(e.id)||eventIds.has(e.id))errors.push(`${label} needs a unique valid ID.`);eventIds.add(e.id);
      if(!TYPES.includes(e.type))errors.push(`${label} has an unsupported type.`);
      if(!isDate(e.date))errors.push(`${label} needs a valid date.`);
      if(!asicIds.has(e.asicId))errors.push(`${label} needs an existing ASIC.`);
      if(!Number.isSafeInteger(e.qty)||e.qty<=0)errors.push(`${label} quantity must be a positive whole number.`);
      textFields(e,['projectId','eta','note','requestId','createdAt','updatedAt','phase','mpn'],label,errors);
      if(e.type!=='expected_ship'&&!projectIds.has(e.projectId))errors.push(`${label} needs an existing project.`);
      if(e.type==='expected_ship'&&e.projectId)errors.push(`${label}: expected supply must be unallocated.`);
      if(e.type==='expected_ship'&&e.supplyStatus!==undefined&&!['available','incoming'].includes(e.supplyStatus))errors.push(`${label}: supply status must be available or incoming.`);
      if(e.type==='expected_ship'&&e.supplyReference!==undefined&&typeof e.supplyReference!=='string')errors.push(`${label}: supply reference must be text.`);
      if(e.type==='request'&&(!Number.isInteger(e.shipDays)||e.shipDays<0))errors.push(`${label} needs a nonnegative ship duration.`);
      if(e.type==='request'&&e.requestedShipDate!==undefined&&(!isDate(e.requestedShipDate)||e.requestedShipDate>e.date))errors.push(`${label}: requested ship date must be a valid date on or before the requested arrival date.`);
      if(e.type==='expected_fulfilment'&&e.priorShipmentIds!==undefined&&(!Array.isArray(e.priorShipmentIds)||e.priorShipmentIds.some(value=>!validId(value))||new Set(e.priorShipmentIds).size!==e.priorShipmentIds.length))errors.push(`${label}: prior shipment IDs must be unique valid IDs.`);
      if(e.type==='expected_fulfilment'&&e.availableShipDate!==undefined&&(!isDate(e.availableShipDate)||e.availableShipDate>e.date))errors.push(`${label}: available ship date must be a valid date on or before the expected arrival date.`);
      if(e.shipDays!==undefined&&(!Number.isInteger(e.shipDays)||e.shipDays<0))errors.push(`${label}: ship duration must be a nonnegative whole number.`);
      if(e.eta&&!isDate(e.eta))errors.push(`${label}: ETA is invalid.`);
      if(e.type==='actual_ship'&&(!isDate(e.eta)||e.eta<e.date))errors.push(`${label} needs an ETA on or after its ship date.`);
      if(e.createdAt!==undefined&&!validTimestamp(e.createdAt))errors.push(`${label}: creation timestamp is invalid.`);
      if(e.updatedAt!==undefined&&!validTimestamp(e.updatedAt))errors.push(`${label}: update timestamp is invalid.`);
      if(e.unitPriceVerified!==undefined&&typeof e.unitPriceVerified!=='boolean')errors.push(`${label}: unitPriceVerified must be a boolean.`);
      if(e.unitPriceVerified===true&&(typeof e.unitPrice!=='number'||!Number.isFinite(e.unitPrice)||e.unitPrice<0))errors.push(`${label}: verified unit price is invalid.`);
    });
    const auditIds=new Set();
    state.audit.forEach((entry,i)=>{
      if(!isRecord(entry)||!validId(entry.id)||auditIds.has(entry.id)||!validTimestamp(entry.date)||typeof entry.action!=='string'||!entry.action.trim()||typeof entry.detail!=='string')errors.push(`Audit entry ${i+1} is invalid.`);
      if(isRecord(entry))auditIds.add(entry.id);
    });
    if(state.forecastVersions!==undefined){
      if(!Array.isArray(state.forecastVersions))errors.push('forecastVersions must be an array.');
      else if(state.forecastVersions.length){
        if(!window.ForecastEngine)errors.push('Forecast history validation is unavailable. Reload the workspace.');
        else errors.push(...window.ForecastEngine.validateVersions(state.forecastVersions));
      }
    }
    if(state.pendingRequests!==undefined&&!Array.isArray(state.pendingRequests))errors.push('pendingRequests must be an array.');
    return errors;
  }
  function validateState(state){
    const errors=validateCore(state);
    if(!isRecord(state))return errors;
    if(!Array.isArray(state.snapshots)){errors.push('snapshots must be an array.');return errors;}
    const objects=[state],seen=new Set();
    while(objects.length){const value=objects.pop();if(!value||typeof value!=='object'||seen.has(value))continue;seen.add(value);for(const key of Object.keys(value)){if(['__proto__','constructor'].includes(key)||(key==='prototype'&&value[key]!==null&&typeof value[key]!=='boolean'))errors.push('Backup contains a reserved object key.');if(value[key]&&typeof value[key]==='object')objects.push(value[key]);}}
    const snapshotIds=new Set();
    state.snapshots.forEach((s,i)=>{
      if(!isRecord(s)||!validId(s.id)||snapshotIds.has(s.id)||!validTimestamp(s.date)||typeof s.label!=='string'||!s.label.trim()||!isRecord(s.data))errors.push(`Snapshot ${i+1} is invalid.`);
      else{const nested=validateCore({...s.data,version:VERSION});if(nested.length)errors.push(`Snapshot ${i+1}: ${nested[0]}`);}
      if(isRecord(s))snapshotIds.add(s.id);
    });
    return [...new Set(errors)];
  }
  function freshSeed(){return {version:VERSION,asics:[],projects:[],events:[],businessEntities:[],fundingSources:[],projectFamilies:[],audit:[],snapshots:[],pendingRequests:[],forecastVersions:[]};}
  function inheritFamilyLinks(state){
    const families=new Map((state.projectFamilies||[]).map(f=>[f.id,f]));
    for(const project of state.projects||[]){
      const family=families.get(project.projectFamilyId);if(!family)continue;
      project.businessEntityId=family.businessEntityId;project.fundingSourceId=family.fundingSourceId;
      project.entity=(state.businessEntities||[]).find(e=>e.id===family.businessEntityId)?.name||'';
      project.funding=(state.fundingSources||[]).find(e=>e.id===family.fundingSourceId)?.name||'';
    }
    return state;
  }
  function deletionImpact(state,kind,id){
    const collection={asic:'asics',project:'projects',businessEntity:'businessEntities',fundingSource:'fundingSources',projectFamily:'projectFamilies'}[kind];
    if(!collection)throw new Error('Unsupported entity type.');
    const item=state[collection].find(x=>x.id===id);
    const impact={kind,id,name:item?.name||'',exists:!!item,events:0,projects:0,families:0,children:0,parts:0};
    if(!item)return impact;
    if(kind==='asic'){impact.events=state.events.filter(e=>e.asicId===id).length;impact.projects=state.projects.filter(p=>p.asicIds.includes(id)).length;impact.parts=(item.parts||[]).length;}
    if(kind==='project'){impact.events=state.events.filter(e=>e.projectId===id).length;impact.children=state.projects.filter(p=>p.parentId===id).length;}
    if(kind==='businessEntity'){impact.projects=state.projects.filter(p=>p.businessEntityId===id).length;impact.families=(state.projectFamilies||[]).filter(f=>f.businessEntityId===id).length;}
    if(kind==='fundingSource'){impact.projects=state.projects.filter(p=>p.fundingSourceId===id).length;impact.families=(state.projectFamilies||[]).filter(f=>f.fundingSourceId===id).length;}
    if(kind==='projectFamily')impact.projects=state.projects.filter(p=>p.projectFamilyId===id).length;
    return impact;
  }
  function deleteEntity(state,kind,id){
    const impact=deletionImpact(state,kind,id);if(!impact.exists)return impact;
    if(impact.families)throw new Error("Reassign dependent project families before deleting this entity.");
    if(kind==='projectFamily'&&impact.projects)throw new Error("Reassign this family’s projects before deleting the family.");
    if(kind==='asic'){
      state.asics=state.asics.filter(a=>a.id!==id);state.events=state.events.filter(e=>e.asicId!==id);
      state.projects.forEach(p=>{p.asicIds=p.asicIds.filter(a=>a!==id);if(p.leadTimes)delete p.leadTimes[id];});
      if(state.pendingRequests)state.pendingRequests=state.pendingRequests.filter(r=>r.asicId!==id);
    }else if(kind==='project'){
      state.projects=state.projects.filter(p=>p.id!==id);state.events=state.events.filter(e=>e.projectId!==id);
      state.projects.forEach(p=>{if(p.parentId===id)p.parentId='';});
      if(state.pendingRequests)state.pendingRequests=state.pendingRequests.filter(r=>r.projectId!==id);
    }else if(kind==='projectFamily'){state.projectFamilies=state.projectFamilies.filter(f=>f.id!==id);
    }else if(kind==='businessEntity'){
      state.businessEntities=state.businessEntities.filter(x=>x.id!==id);
      state.projects.forEach(p=>{if(p.businessEntityId===id){p.businessEntityId='';p.entity='';}});
    }else if(kind==='fundingSource'){
      state.fundingSources=state.fundingSources.filter(x=>x.id!==id);
      state.projects.forEach(p=>{if(p.fundingSourceId===id){p.fundingSourceId='';p.funding='';}});
    }
    return impact;
  }
  window.Tracker={VERSION,TYPES,clone,freshSeed,inheritFamilyLinks,stats,weekly,financial,priceAt,parentName,matchesEvent,isoWeek,monday,quarterOf,isDate,todayPacific,requestShipBy,requestAvailability,allocationShipBy,allocationRows,supplyRows,supplySummary,validateState,deletionImpact,deleteEntity,entityName,fundingName,eventLabel:type=>labels[type]||type,calculations:(state,filters={})=>({...stats(state,filters),weekly:weekly(state,filters),financial:financial(state,filters)})};
})();
