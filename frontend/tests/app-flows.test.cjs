/* Exercise the real application event handlers with a minimal DOM adapter. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const frontend=path.resolve(__dirname,'..');
const plain=value=>JSON.parse(JSON.stringify(value));

function element(){
  const classes=new Set(),attributes=new Map(),events=new Map();
  return {innerHTML:'',textContent:'',open:false,children:[],dataset:{},disabled:false,events,
    classList:{add:(...names)=>names.forEach(name=>classes.add(name)),remove:(...names)=>names.forEach(name=>classes.delete(name)),toggle(name,on){if(on)classes.add(name);else classes.delete(name);}},
    setAttribute:(name,value)=>attributes.set(name,value),removeAttribute:name=>attributes.delete(name),hasAttribute:name=>attributes.has(name),
    querySelector:()=>null,querySelectorAll:()=>[],addEventListener(name,fn){events.set(name,fn);},append(...children){this.children.push(...children);},after(){},remove(){},click(){},focus(){},setSelectionRange(){},scrollIntoView(){},
    showModal(){this.open=true;},close(){this.open=false;}};
}
function sample(T){
  const state=T.freshSeed();
  state.businessEntities=[{id:'be',name:'Business',description:''}];
  state.fundingSources=[{id:'fund',name:'Funding',description:''}];
  state.projectFamilies=[{id:'family',name:'Family',businessEntityId:'be',fundingSourceId:'fund',description:''}];
  state.asics=[{id:'a',name:'ASIC',owner:'Owner',parts:[],mpns:[],cpns:[],price:null,priceHistory:[]}];
  state.projects=[{id:'p',name:'Project',manager:'EPM',projectFamilyId:'family',asicIds:['a'],leadTimes:{a:0},leadDays:0}];
  state.events=[
    {id:'supply',type:'expected_ship',asicId:'a',projectId:'',date:'2026-10-01',qty:100,supplyStatus:'available'},
    {id:'first',type:'request',asicId:'a',projectId:'p',date:'2026-11-10',requestedShipDate:'2026-11-10',shipDays:0,qty:30,requestId:'first-alias'},
    {id:'second',type:'request',asicId:'a',projectId:'p',date:'2026-11-11',requestedShipDate:'2026-11-11',shipDays:0,qty:30,requestId:'second-alias'}];
  return T.inheritFamilyLinks(state);
}
async function application(setup=()=>{},page='business-entities',now){
  const listeners=new Map(),elements=new Map(),forms=new Map(),saved=[],downloads=[];
  for(const selector of ['#app','#drawer','#toasts','#backup-file','#crumb','#content','#connection-status','#search-results','#global-search','#form-errors','[data-search]'])elements.set(selector,element());
  const document={body:element(),querySelector:selector=>forms.get(selector)||elements.get(selector)||null,querySelectorAll:()=>[],
    createElement:()=>element(),createTextNode:text=>({textContent:text}),addEventListener(name,fn){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(fn);}};
  const RuntimeDate=now?class extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return Date.parse(now);}}:Date;
  const sandbox={document,console,Intl,Date:RuntimeDate,Blob,crypto,location:{hash:'#'+page},setTimeout:()=>0,clearTimeout(){},
    URL:{createObjectURL(blob){downloads.push(blob);return 'blob:test';},revokeObjectURL(){}},
    FormData:class {constructor(form){this.values=form.values;}entries(){return this.values[Symbol.iterator]();}getAll(name){return this.values.filter(([key])=>key===name).map(([,value])=>value);}has(name){return this.values.some(([key])=>key===name);}},
    addEventListener(){},scrollTo(){},MetricTips:{hide(){}}};
  sandbox.window=sandbox;vm.createContext(sandbox);
  for(const name of ['data.js','forecast-engine.js','entity-views.js','family-views.js','request-views.js','allocation-views.js','supply-views.js','forecast-views.js'])vm.runInContext(fs.readFileSync(path.join(frontend,name),'utf8'),sandbox,{filename:name});
  const T=sandbox.Tracker,state=sample(T);setup(state,T);
  assert.deepEqual(plain(T.validateState(state)),[],'Initial fixture is valid.');
  sandbox.ApiStore={user:{role:'admin',subject:'test-admin',auth_mode:'development'},busy:false,needsReload:false,lastError:'',hasDraft:false,revision:0,
    async bootstrap(){return state;},installReadModels(){},async save(next,options){saved.push({state:plain(next),options});this.revision++;return plain(next);},renderBootError(error){throw error;}};
  await vm.runInContext(fs.readFileSync(path.join(frontend,'app.js'),'utf8'),sandbox,{filename:'app.js'});
  async function click(action,extra={}){const button={dataset:{action,...extra}};const event={target:{closest:selector=>selector==='[data-action]'?button:null},preventDefault(){}};for(const fn of listeners.get('click')||[])await fn(event);}
  function form(id,values){const result={id,values:Object.entries(values).flatMap(([name,value])=>(Array.isArray(value)?value:[value]).map(item=>[name,String(item)]))};forms.set('#'+id,result);return result;}
  async function submit(form){for(const fn of listeners.get('submit')||[])await fn({target:form,preventDefault(){}});}
  async function search(value){const target={dataset:{search:'query'},value,selectionStart:value.length,closest:()=>null};for(const fn of listeners.get('input')||[])await fn({target});}
  async function filter(name,value){const target={dataset:{filter:name},value,type:'select-one',closest:()=>null};for(const fn of listeners.get('change')||[])await fn({target});}
  async function backup(file){await elements.get('#backup-file').events.get('change')({target:{files:[file],value:'selected'}});}
  return {T,state,saved,downloads,click,form,submit,search,filter,backup,filenames:()=>document.body.children.filter(child=>child.download).map(child=>child.download),pendingBackup:()=>sandbox.pendingBackup,content:()=>elements.get('#content').innerHTML,errors:()=>elements.get('#form-errors').textContent,drawer:()=>elements.get('#drawer').innerHTML};
}

test('editing a linked shipment preserves its request assignment and completed credit',async()=>{
  const h=await application(state=>state.events.push({id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:20,requestId:'second-alias'}));
  await h.click('edit-event',{id:'ship'});
  await h.submit(h.form('event-form',{date:'2026-10-20',eta:'2026-10-21',projectId:'p',lineAsic:'a',lineQty:'20',eventPhase:'',note:'Corrected note',allocationId:''}));
  assert.equal(h.saved.length,1,h.errors());
  const after=h.saved[0].state,shipment=after.events.find(e=>e.id==='ship');
  assert.equal(shipment.requestId,'second-alias');
  const rows=h.T.requestAvailability(after,{asOf:'2026-10-29'});
  assert.equal(rows.find(r=>r.eventId==='first').shippedQty,0);
  assert.equal(rows.find(r=>r.eventId==='second').shippedQty,20);
});

test('editing a timestamp-less legacy request preserves historical FIFO completion',async()=>{
  const h=await application(state=>state.events.push({id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:20,requestId:''}));
  const form=h.form('request-form',{requestProjectId:'p',requestAsicId:'a',requestQty:'30',requestedShipDate:'2026-11-10',requestShipDays:'0',requestNote:'Corrected note'});
  await h.click('edit-request',{id:'first'});await h.submit(form);
  assert.equal(h.saved.length,1,h.errors());
  const after=h.saved[0].state,request=after.events.find(e=>e.id==='first');
  assert.equal(Object.hasOwn(request,'createdAt'),false);
  assert.equal(h.T.requestAvailability(after,{asOf:'2026-10-29'}).find(r=>r.eventId==='first').shippedQty,20);
});

for(const reference of ['second-alias','historical-reference'])test('editing an existing allocation preserves legacy reference '+reference,async()=>{
  const h=await application(state=>state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',availableShipDate:'2026-11-01',qty:10,requestId:reference}));
  const form=h.form('allocation-form',{allocationAsicId:'a',allocationProjectId:'p',allocationRequestId:reference,allocationQty:'12',availableShipDate:'2026-11-01',allocationNote:'Quantity correction'});
  await h.click('edit-allocation',{id:'allocation'});await h.submit(form);
  assert.equal(h.saved.length,1,h.errors());
  assert.equal(h.saved[0].state.events.find(e=>e.id==='allocation').requestId,reference);
  assert.equal(h.saved[0].state.events.find(e=>e.id==='allocation').qty,12);
});

for(const explicitDispatch of [true,false])test('allocation note edits preserve stored arrival and transit after project-default changes: explicit dispatch '+explicitDispatch,async()=>{
  const h=await application(state=>{
    state.projects[0].leadTimes.a=3;
    state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-10',qty:10,requestId:'second-alias',shipDays:9,eta:'2026-11-09',...(explicitDispatch?{availableShipDate:'2026-11-01'}:{})});
  });
  const form=h.form('allocation-form',{allocationAsicId:'a',allocationProjectId:'p',allocationRequestId:'second-alias',allocationQty:'12',availableShipDate:explicitDispatch?'2026-11-01':'2026-11-07',allocationNote:'Corrected note'});
  await h.click('edit-allocation',{id:'allocation'});await h.submit(form);
  assert.equal(h.saved.length,1,h.errors());const record=h.saved[0].state.events.find(e=>e.id==='allocation');
  assert.equal(record.date,'2026-11-10');assert.equal(record.shipDays,9);assert.equal(record.eta,'2026-11-09');
  assert.equal(Object.hasOwn(record,'availableShipDate'),explicitDispatch);
});

test('an explicit allocation dispatch-date edit recalculates arrival from current transit defaults',async()=>{
  const h=await application(state=>{state.projects[0].leadTimes.a=3;state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-10',availableShipDate:'2026-11-01',qty:10,shipDays:9,requestId:'second-alias'});});
  const form=h.form('allocation-form',{allocationAsicId:'a',allocationProjectId:'p',allocationRequestId:'second-alias',allocationQty:'10',availableShipDate:'2026-11-02',allocationNote:'Rescheduled'});
  await h.click('edit-allocation',{id:'allocation'});await h.submit(form);
  assert.equal(h.saved.length,1,h.errors());const record=h.saved[0].state.events.find(e=>e.id==='allocation');
  assert.equal(record.date,'2026-11-05');assert.equal(record.shipDays,3);
});

test('ordinary inventory and request edits preserve hidden legacy event metadata',async()=>{
  const inventory=await application(state=>Object.assign(state.events[0],{shipDays:4,eta:'2026-10-15',requestId:'historical-reference'}));
  await inventory.click('edit-supply',{id:'supply'});
  await inventory.submit(inventory.form('supply-form',{supplyAsicId:'a',supplyQty:'100',supplyDate:'2026-10-01',supplyStatus:'available',supplyReference:'',supplyNote:'Updated note'}));
  assert.equal(inventory.saved.length,1,inventory.errors());const lot=inventory.saved[0].state.events.find(e=>e.id==='supply');
  assert.equal(lot.shipDays,4);assert.equal(lot.eta,'2026-10-15');assert.equal(lot.requestId,'historical-reference');assert.equal(Object.hasOwn(lot,'createdAt'),false);
  const request=await application(state=>state.events.find(e=>e.id==='first').eta='2026-11-12');
  const form=request.form('request-form',{requestProjectId:'p',requestAsicId:'a',requestQty:'30',requestedShipDate:'2026-11-10',requestShipDays:'0',requestNote:'Updated note'});
  await request.click('edit-request',{id:'first'});await request.submit(form);
  assert.equal(request.saved.length,1,request.errors());assert.equal(request.saved[0].state.events.find(e=>e.id==='first').eta,'2026-11-12');
});

test('renaming a business entity preserves its archive and compatibility metadata',async()=>{
  const h=await application(state=>Object.assign(state.businessEntities[0],{archivedAt:'2026-01-01T12:00:00Z',externalReference:'BE-legacy'}));
  await h.click('edit-business-entity',{id:'be'});
  await h.submit(h.form('master-form',{masterKind:'businessEntity',masterId:'be',name:'Business renamed',description:'Updated description'}));
  assert.equal(h.saved.length,1,h.errors());
  assert.equal(h.saved[0].state.businessEntities[0].archivedAt,'2026-01-01T12:00:00Z');
  assert.equal(h.saved[0].state.businessEntities[0].externalReference,'BE-legacy');
});

for(const leadDays of [0,null,undefined])test('project note edits retain legacy transit defaults: '+String(leadDays),async()=>{
  const h=await application(state=>{
    delete state.projects[0].leadTimes;
    if(leadDays===undefined)delete state.projects[0].leadDays;else state.projects[0].leadDays=leadDays;
  },'projects');
  await h.click('edit-project',{id:'p'});
  assert.match(h.drawer(),/name="lead-a"[^>]*value="0"/);
  await h.submit(h.form('project-form',{name:'Project',manager:'EPM',projectFamilyId:'family',prototype:'',summary:'Corrected note',asicIds:['a'],'lead-a':'0'}));
  assert.equal(h.saved.length,1,h.errors());const record=h.saved[0].state.projects[0];
  assert.equal(Object.hasOwn(record,'leadDays'),leadDays!==undefined);
  assert.equal(record.leadDays,leadDays);assert.equal(record.leadTimes.a,0);
  await h.click('new-request');assert.match(h.drawer(),/name="requestShipDays"[^>]*value="0"/);
});

test('project edits retain valid transit settings for currently unassociated ASICs',async()=>{
  const h=await application(state=>{state.asics.push({...state.asics[0],id:'b',name:'Other ASIC'});state.projects[0].leadTimes.b=12;},'projects');
  await h.click('edit-project',{id:'p'});
  await h.submit(h.form('project-form',{name:'Project',manager:'EPM',projectFamilyId:'family',prototype:'',summary:'Corrected note',asicIds:['a'],'lead-a':'0'}));
  assert.equal(h.saved.length,1,h.errors());assert.deepEqual(h.saved[0].state.projects[0].leadTimes,{a:0,b:12});
});

test('new projects retain the explicit seven-day transit default',async()=>{
  const h=await application(()=>{},'projects');await h.click('new-project');
  assert.match(h.drawer(),/name="lead-a"[^>]*value="7"/);
  await h.submit(h.form('project-form',{name:'New Project',manager:'EPM',projectFamilyId:'family',prototype:'',summary:'New',asicIds:['a'],'lead-a':'7'}));
  assert.equal(h.saved.length,1,h.errors());const record=h.saved[0].state.projects.find(p=>p.id!=='p');
  assert.equal(record.leadDays,7);assert.equal(record.leadTimes.a,7);
});

test('ASIC note edits preserve compatibility metadata on the same detailed part ID',async()=>{
  const extra={sourceRow:17,archivedAt:'2026-01-01T12:00:00Z'};
  const h=await application(state=>{state.asics[0].parts=[{id:'part-a',mpn:'MPN',cpn:'CPN',plid:'PLID',assembly:'Assembly',subtype:'Subtype',extra}];},'asics');
  await h.click('edit-asic',{id:'a'});
  await h.submit(h.form('asic-form',{name:'ASIC',owner:'Owner',marketing:'',description:'Corrected note',price:'',priceQuarter:'2026-Q4',partId:'part-a',partMpn:'MPN',partCpn:'CPN',partPlid:'PLID',partAssembly:'Assembly',partSubtype:'Subtype'}));
  assert.equal(h.saved.length,1,h.errors());assert.deepEqual(h.saved[0].state.asics[0].parts[0].extra,extra);
});

test('recording a shipment against a dedicated allocation credits its matching request',async()=>{
  const h=await application(state=>state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',availableShipDate:'2026-11-01',qty:30,requestId:'second-alias'}));
  await h.click('new-event');
  await h.submit(h.form('event-form',{date:'2026-10-20',eta:'2026-10-21',projectId:'p',lineAsic:'a',lineQty:'20',eventPhase:'',note:'Shipped against chosen allocation',allocationId:'allocation'}));
  assert.equal(h.saved.length,1,h.errors());
  const after=h.saved[0].state,shipment=after.events.find(e=>e.type==='actual_ship');
  assert.equal(shipment.requestId,'second');
  const requests=h.T.requestAvailability(after,{asOf:'2026-10-29'}),allocation=h.T.allocationRows(after,{asOf:'2026-10-29'})[0];
  assert.equal(requests.find(r=>r.eventId==='first').shippedQty,0);
  assert.equal(requests.find(r=>r.eventId==='second').shippedQty,20);
  assert.equal(allocation.shippedQty,20);assert.equal(allocation.remainingQty,10);
});

test('a new shipment aligned with an unresolved historical allocation retains project FIFO semantics',async()=>{
  const h=await application(state=>state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',availableShipDate:'2026-11-01',qty:30,requestId:'historical-missing-request'}));
  await h.click('new-event');await h.submit(h.form('event-form',{date:'2026-10-20',eta:'2026-10-21',projectId:'p',lineAsic:'a',lineQty:'20',eventPhase:'',note:'Project pool shipment',allocationId:'allocation'}));
  assert.equal(h.saved.length,1,h.errors());const after=h.saved[0].state;
  assert.equal(after.events.find(e=>e.type==='actual_ship').requestId,'');
  assert.equal(after.events.find(e=>e.id==='allocation').requestId,'historical-missing-request');
  assert.equal(h.T.requestAvailability(after,{asOf:'2026-10-29'}).find(e=>e.eventId==='first').shippedQty,20);
});

for(const detailedParts of [false,true])test('editing legacy ASIC catalog metadata does not invent or erase unmapped variants: parts field '+detailedParts,async()=>{
  const h=await application(state=>{
    Object.assign(state.asics[0],{mpns:['LEGACY-MPN'],cpns:['LEGACY-CPN'],plid:'Legacy PLID',assembly:'Legacy assembly',subtype:'Legacy subtype'});
    if(!detailedParts)delete state.asics[0].parts;
  },'asics');
  await h.search('legacy-cpn');assert.match(h.content(),/>ASIC</);
  await h.click('edit-asic',{id:'a'});assert.match(h.drawer(),/Legacy catalog fields are retained/);
  await h.submit(h.form('asic-form',{name:'ASIC renamed',owner:'Owner',marketing:'',description:'Corrected note',price:'',priceQuarter:'2026-Q4',partId:'',partMpn:'',partCpn:'',partPlid:'',partAssembly:'',partSubtype:''}));
  assert.equal(h.saved.length,1,h.errors());const record=h.saved[0].state.asics[0];
  assert.deepEqual(record.mpns,['LEGACY-MPN']);assert.deepEqual(record.cpns,['LEGACY-CPN']);
  assert.equal(record.plid,'Legacy PLID');assert.equal(record.assembly,'Legacy assembly');assert.equal(record.subtype,'Legacy subtype');
  assert.deepEqual(record.parts,[]);
});

test('restoring a recovery point clears optional source metadata absent from that capture',async()=>{
  const h=await application((state,T)=>{
    const data=T.clone(state);delete data.snapshots;delete data.pendingRequests;
    state.snapshots=[{id:'snapshot',label:'Earlier workspace',date:'2026-10-01',data}];
    state.source={name:'Later imported workbook'};state.pendingRequests=[{id:'later-compatibility-data'}];
  });
  await h.click('confirm-restore',{id:'snapshot'});assert.equal(h.saved.length,1,h.errors());
  assert.equal(Object.hasOwn(h.saved[0].state,'source'),false);
  assert.deepEqual(h.saved[0].state.pendingRequests,[]);
  assert.equal(h.saved[0].options.operation,'restore');
});

test('date-only recovery dates retain their recorded calendar day',async()=>{
  const h=await application((state,T)=>{const data=T.clone(state);delete data.snapshots;state.snapshots=[{id:'snapshot',label:'Recovery',date:'2026-01-01',data}];},'recovery');
  assert.match(h.content(),/Jan 1, 2026/);assert.doesNotMatch(h.content(),/Dec 31, 2025/);
});

test('backup reader permits valid files above the obsolete 10 MB cap but bounds unsupported files',async()=>{
  const h=await application();
  await h.backup({size:11*1024*1024,text:async()=>JSON.stringify(h.state)});
  assert.ok(h.pendingBackup());assert.match(h.drawer(),/Import this backup/);
  const rejected=await application();let read=false;
  await rejected.backup({size:32*1024*1024+1,text:async()=>{read=true;throw new Error('Unsupported file must not be read');}});
  assert.equal(read,false);assert.equal(rejected.pendingBackup(),undefined);
});

test('request references choose an exact event ID before a colliding alias, scoped by ASIC/project',async()=>{
  const h=await application(state=>{
    state.events.find(e=>e.id==='first').requestId='second';
    state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',availableShipDate:'2026-11-01',qty:10,requestId:'second'},
      {id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:5,requestId:'second'});
  });
  const requests=h.T.requestAvailability(h.state,{asOf:'2026-10-29'}),first=requests.find(r=>r.eventId==='first'),second=requests.find(r=>r.eventId==='second');
  assert.equal(first.shippedQty,0);assert.equal(first.allocatedQty,0);
  assert.equal(second.shippedQty,5);assert.equal(second.allocatedQty,5);
  assert.equal(h.T.resolveRequest(h.state,{asicId:'a',projectId:'p',requestId:'second'}).id,'second');
});

test('scarce supply follows actual timestamp chronology across offsets and UTC/Pacific day boundaries',async()=>{
  const cases=[['2026-10-27T11:00:00-07:00','2026-10-27T12:00:00Z','second'],['2026-10-28T02:00:00Z','2026-10-27T23:00:00-07:00','first'],['2026-10-27','2026-10-28T02:00:00Z','first']];
  for(const [createdFirst,createdSecond,winner] of cases){
    const h=await application(state=>{
      state.events.find(e=>e.id==='supply').qty=30;
      for(const [id,createdAt] of [['first',createdFirst],['second',createdSecond]])Object.assign(state.events.find(e=>e.id===id),{createdAt,date:'2026-11-10',requestedShipDate:'2026-11-10'});
    });
    const rows=h.T.requestAvailability(h.state,{asOf:'2026-10-29'});
    assert.equal(rows.find(r=>r.eventId===winner).availableByShipBy,30,createdFirst+' vs '+createdSecond);
  }
});

test('planner ID ties use the same codepoint order as the Python authority',async()=>{
  const h=await application(state=>{
    state.events.find(e=>e.id==='supply').qty=30;
    const first=state.events.find(e=>e.id==='first'),second=state.events.find(e=>e.id==='second');
    Object.assign(first,{id:'a',requestId:'alias-a',date:'2026-11-10',requestedShipDate:'2026-11-10'});
    Object.assign(second,{id:'B',requestId:'alias-B',date:'2026-11-10',requestedShipDate:'2026-11-10'});
  });
  const rows=h.T.requestAvailability(h.state,{asOf:'2026-10-29'});
  assert.equal(rows.find(r=>r.eventId==='B').availableByShipBy,30);assert.equal(rows.find(r=>r.eventId==='a').availableByShipBy,0);
});

test('explicit surplus shipment units can fulfill their dedicated commitment without overstating request credit',async()=>{
  for(const baseline of [false,true]){
    const h=await application(state=>{
      state.events=state.events.filter(e=>e.id!=='second');state.events.find(e=>e.id==='first').qty=20;
      state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',availableShipDate:'2026-11-01',qty:100,requestId:'first',...(baseline?{priorShipmentIds:['ship']}:{})},
        {id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:100,requestId:'first'});
    });
    const allocation=h.T.allocationRows(h.state,{asOf:'2026-10-29'})[0],request=h.T.requestAvailability(h.state,{asOf:'2026-10-29'})[0];
    assert.equal(request.shippedQty,20);assert.equal(allocation.shippedQty,baseline?0:100);assert.equal(allocation.remainingQty,baseline?100:0);
  }
});

test('surplus shipment handling preserves unlinked FIFO and other alias-matched request credit',async()=>{
  const unlinked=await application(state=>{
    state.events=state.events.filter(e=>e.id!=='second');state.events.find(e=>e.id==='first').qty=20;
    state.events.push({id:'allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',qty:100,requestId:'first'},
      {id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:100,requestId:''});
  });
  assert.equal(unlinked.T.allocationRows(unlinked.state,{asOf:'2026-10-29'})[0].shippedQty,20);
  const shared=await application(state=>{
    Object.assign(state.events.find(e=>e.id==='first'),{qty:20,requestId:'shared'});Object.assign(state.events.find(e=>e.id==='second'),{qty:60,requestId:'shared'});
    state.events.push({id:'dedicated',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',qty:100,requestId:'first'},
      {id:'pool',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'2026-11-01',qty:60,requestId:''},
      {id:'ship',type:'actual_ship',asicId:'a',projectId:'p',date:'2026-10-20',eta:'2026-10-21',qty:100,requestId:'shared'});
  });
  const rows=shared.T.allocationRows(shared.state,{asOf:'2026-10-29'});
  assert.equal(rows.find(r=>r.eventId==='dedicated').shippedQty,40);assert.equal(rows.find(r=>r.eventId==='pool').shippedQty,60);
  assert.equal(rows.reduce((sum,row)=>sum+row.shippedQty,0),100);
});

test('legacy pending-request compatibility entries cannot crash entity deletion',async()=>{
  const h=await application();h.state.pendingRequests=[null,7,'Legacy',{}, {asicId:'a'}, {projectId:'p'}];
  h.T.deleteEntity(h.state,'asic','a');assert.deepEqual(plain(h.state.pendingRequests),[null,7,'Legacy',{}, {projectId:'p'}]);
  h.T.deleteEntity(h.state,'project','p');assert.deepEqual(plain(h.state.pendingRequests),[null,7,'Legacy',{}]);
});

test('calendar validation and ISO week numbering agree with supported four-digit years',async()=>{
  const h=await application();assert.equal(h.T.isDate('0000-01-01'),false);
  assert.equal(h.T.isDate('0001-01-01'),true);assert.equal(h.T.isoWeek('0001-01-01'),'0001-W01');
  assert.equal(h.T.isoWeek('0099-01-01'),'0099-W01');
});

test('bounded weekly reports retain the requested final period and carry earlier history',async()=>{
  const h=await application();
  h.state.events=[{id:'old-request',type:'request',asicId:'a',projectId:'p',date:'0001-01-01',shipDays:0,qty:10},
    {id:'future-allocation',type:'expected_fulfilment',asicId:'a',projectId:'p',date:'9999-12-31',qty:20}];
  const rows=h.T.weekly(h.state,{cutoff:'9999-12-31'});
  assert.equal(rows.length,5300);assert.equal(rows.at(-1).week,'9999-12-27');
  assert.equal(rows.openingBalance,-10);assert.equal(rows.at(-1).balance,10);
  assert.match(rows.notice,/5,300 weeks/);assert.ok(rows.every(row=>h.T.isDate(row.week)));
  assert.equal(h.T.stats(h.state,{cutoff:'9999-12-31'}).balance,rows.at(-1).balance);
});

test('default pricing quarter and backup filenames use the workspace Pacific date',async()=>{
  const h=await application(()=>{},'business-entities','2026-04-01T02:00:00Z');
  await h.click('edit-asic',{id:'a'});assert.match(h.drawer(),/id="f-priceQuarter"[^>]*value="2026-Q1"/);
  await h.click('export-backup');assert.deepEqual(h.filenames(),['asic-tracker-backup-2026-03-31.json']);
});

test('client planner retains all frozen legacy parity cases without mutating input',async()=>{
  const fixture=JSON.parse(fs.readFileSync(path.join(frontend,'../backend/tests/fixtures/planner-parity.json'),'utf8'));
  const h=await application();assert.equal(fixture.cases.length,122);
  for(const item of fixture.cases){
    const state={events:[],projects:[],asics:[],...plain(item.state)},before=plain(state);
    assert.deepEqual(plain(h.T[item.method](state,item.options)),item.expected,item.suite+' '+item.index+' '+item.method);
    assert.deepEqual(state,before,'Input unchanged for '+item.method);
  }
});

test('every page and report renders with a complete shared workspace',async()=>{
  const pages=['overview','asics','projects','requests','allocations','supply','business-entities','funding-sources','project-families','events','forecasts','reports','recovery'];
  for(const page of pages){const h=await application(()=>{},page);assert.match(h.content(),/<(?:div|section)/,page);}
  const reports=await application(()=>{},'reports');
  for(const report of ['shortage','demand','allocation','supply','financial','pivot']){await reports.filter('report',report);assert.match(reports.content(),/report-list/,report);}
  const forecasts=await application(()=>{},'forecasts');
  for(const tab of ['summary','program','chart']){await forecasts.click('forecast-tab',{tab});for(const mode of ['monthly','cumulative']){await forecasts.click('forecast-mode',{mode});assert.match(forecasts.content(),/Forecast/);}}
});

test('CSV export neutralizes formula-like text and preserves numeric negative deltas',async()=>{
  const h=await application((state,T)=>{
    state.asics[0].name='=HYPERLINK("https://example.invalid")';
    const line={asicId:'a',asicName:state.asics[0].name,projectId:'p',projectName:'Project',category:'Business',phase:'Unspecified',type:'request',month:'2026-11',qty:10};
    state.forecastVersions=[{id:'v1',month:'2026-09',name:'Prior',createdAt:'2026-09-01',lines:[line]},{id:'v2',month:'2026-10',name:'Current',createdAt:'2026-10-01',lines:[{...line,qty:5}]}];
  },'forecasts');
  await h.click('export-forecast');assert.equal(h.downloads.length,1);
  const csv=await h.downloads[0].text();
  assert.match(csv,/"'=HYPERLINK/);
  assert.match(csv,/"-5"/);assert.doesNotMatch(csv,/"'-5"/);
});
