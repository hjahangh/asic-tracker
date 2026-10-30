/* Run with: node --test frontend/tests/*.test.cjs (Node 22 or later). */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const frontend = path.resolve(__dirname, '..');
const plain = value => JSON.parse(JSON.stringify(value));
const response = (data, status=200) => ({ok:status>=200&&status<300,status,json:async()=>plain(data)});

function context(fetch=async()=>{throw new Error('Unexpected HTTP request');}) {
  const classes=new Set();
  const sandbox={window:{},fetch,console,Intl,Date,URL,Blob,setTimeout,clearTimeout,
    document:{body:{classList:{add:value=>classes.add(value),remove:value=>classes.delete(value)},setAttribute(){},removeAttribute(){}}}};
  vm.createContext(sandbox);
  for(const name of ['data.js','forecast-engine.js','api-store.js'])vm.runInContext(fs.readFileSync(path.join(frontend,name),'utf8'),sandbox,{filename:name});
  return {sandbox,T:sandbox.window.Tracker,store:sandbox.window.ApiStore,classes};
}
function familyState(T) {
  const state=T.freshSeed();
  state.businessEntities=[{id:'business-a',name:'Business A',description:''}];
  state.fundingSources=[{id:'funding-a',name:'Funding A',description:''}];
  state.projectFamilies=[{id:'family-a',name:'Family A',businessEntityId:'business-a',fundingSourceId:'funding-a',description:''}];
  state.projects=[{id:'project-a',name:'Project A',manager:'Owner A',projectFamilyId:'family-a',prototype:true,asicIds:[],leadTimes:{}}];
  return T.inheritFamilyLinks(state);
}
function serverHarness() {
  let revision=4,workspace,mode='ok',putCount=0,pendingPut=null;
  const result=context(async(url,options={})=>{
    if(url==='/api/me')return response({subject:'synthetic-admin',display_name:'Test admin',role:'admin',auth_mode:'development'});
    if(url.startsWith('/api/availability'))return response({revision,asOf:result.T.todayPacific(),requests:[{eventId:'server-row',asicId:'asic-a'}],allocations:[],supply:[],inventory:[]});
    if(url==='/api/workspace'&&options.method==='PUT'){
      putCount++;
      const body=JSON.parse(options.body);
      assert.equal(options.credentials,'same-origin');
      assert.equal(options.headers['If-Match'],'"'+body.revision+'"');
      if(mode==='conflict')return response({detail:{code:'revision_conflict',message:'Another user saved first.'}},409);
      if(mode==='network')throw new Error('Connection closed');
      if(mode==='unreadable')return {ok:true,status:200,json:async()=>{throw new Error('bad JSON');}};
      if(mode==='invalid')return response({detail:{message:'Invalid data.'}},422);
      if(mode==='pending')await new Promise(resolve=>pendingPut=resolve);
      workspace=body.state;revision++;workspace.audit=[{id:'server-audit',date:'2026-10-29T20:00:00Z',action:body.reason,detail:'Canonical server audit',actor:'synthetic-admin'}];
      return response({revision,state:workspace});
    }
    if(url==='/api/workspace')return response({revision,state:workspace});
    throw new Error('Unexpected '+url);
  });
  workspace=result.T.freshSeed();
  return {...result,setMode:value=>mode=value,setState:value=>workspace=value,get puts(){return putCount;},release:()=>pendingPut()};
}

test('family ownership is inherited; legacy projects need an explicit family map',()=>{
  const {T}=context(),state=familyState(T);
  assert.deepEqual(plain(T.validateState(state)),[]);
  assert.equal(state.projects[0].businessEntityId,'business-a');
  assert.equal(state.projects[0].funding,'Funding A');
  const legacy=plain(state);delete legacy.projectFamilies;delete legacy.projects[0].projectFamilyId;
  assert.match(T.validateState(legacy).join(' '),/Map legacy projects|map legacy projects/);
  const changed=plain(state);changed.projects[0].fundingSourceId='other';
  assert.match(T.validateState(changed).join(' '),/ownership must be inherited/);
});

test('families with projects and organization entities with families cannot be deleted',()=>{
  const {T}=context(),state=familyState(T);
  assert.throws(()=>T.deleteEntity(state,'projectFamily','family-a'),/project/i);
  assert.throws(()=>T.deleteEntity(state,'businessEntity','business-a'),/famil/i);
  assert.throws(()=>T.deleteEntity(state,'fundingSource','funding-a'),/famil/i);
  state.projects=[];T.deleteEntity(state,'projectFamily','family-a');
  T.deleteEntity(state,'businessEntity','business-a');
  assert.equal(state.projectFamilies.length,0);assert.equal(state.businessEntities.length,0);
});

test('family mappings are required inside recovery snapshots as well',()=>{
  const {T}=context(),state=familyState(T),old=plain(state);delete old.projectFamilies;
  state.snapshots=[{id:'snapshot-a',date:'2026-10-29T20:00:00Z',label:'Legacy snapshot',data:old}];
  assert.match(T.validateState(state).join(' '),/Snapshot 1:.*famil/i);
});

test('prototype boolean survives validation; unsafe object keys are rejected',()=>{
  const {T}=context(),state=familyState(T);
  for(const value of [true,false,null]){state.projects[0].prototype=value;assert.deepEqual(plain(T.validateState(state)),[]);}
  state.projects[0].prototype='true';assert.match(T.validateState(state).join(' '),/prototype must/);
  const unsafe=JSON.parse('{"__proto__": {"polluted":true}}');state.source=unsafe;
  assert.match(T.validateState(state).join(' '),/reserved object key/);
});

test('bootstrap fails closed when the API is unavailable or has no authorized role',async()=>{
  const offline=context();await assert.rejects(offline.store.bootstrap(),/could not be reached/);
  assert.equal(offline.store.revision,null);
  const forbidden=context(async()=>response({subject:'test',role:'none'}));
  await assert.rejects(forbidden.store.bootstrap(),/application role/);
});

test('successful save uses the loaded revision and replaces state with the canonical server result',async()=>{
  const h=serverHarness(),state=await h.store.bootstrap();
  state.businessEntities.push({id:'business-a',name:'Business A',description:''});
  const saved=await h.store.save(state,{reason:'Create business entity',operation:'edit'});
  assert.equal(h.store.revision,5);assert.equal(saved.audit[0].actor,'synthetic-admin');
  assert.notEqual(saved,state);assert.equal(h.store.busy,false);assert.equal(h.classes.has('is-saving'),false);
});

test('409 keeps a downloadable draft and blocks further writes until an explicit reload',async()=>{
  const h=serverHarness(),state=await h.store.bootstrap();h.setMode('conflict');
  await assert.rejects(h.store.save(state),/Another user saved first/);
  assert.equal(h.store.needsReload,true);assert.equal(h.store.hasDraft,true);
  await assert.rejects(h.store.save(state),/Load the latest/);assert.equal(h.puts,1);
  h.setMode('ok');await h.store.load();assert.equal(h.store.needsReload,false);
  await h.store.save(state);assert.equal(h.puts,2);
});

test('unconfirmed network and unreadable responses require a reload without an automatic retry',async()=>{
  for(const mode of ['network','unreadable']){
    const h=serverHarness(),state=await h.store.bootstrap();h.setMode(mode);
    await assert.rejects(h.store.save(state));assert.equal(h.store.needsReload,true);assert.equal(h.puts,1);
  }
});

test('server validation failure preserves a draft while allowing a corrected submission',async()=>{
  const h=serverHarness(),state=await h.store.bootstrap();h.setMode('invalid');
  await assert.rejects(h.store.save(state),/Invalid data/);
  assert.equal(h.store.needsReload,false);assert.equal(h.store.hasDraft,true);
  h.setMode('ok');await h.store.save(state);assert.equal(h.store.hasDraft,false);
});

test('a second save cannot race an in-flight shared transaction',async()=>{
  const h=serverHarness(),state=await h.store.bootstrap();h.setMode('pending');
  const saving=h.store.save(state);assert.equal(h.store.busy,true);
  await assert.rejects(h.store.save(state),/already being saved/);assert.equal(h.puts,1);
  h.release();await saving;assert.equal(h.store.busy,false);
});

test('server availability is used for a matching canonical state; draft previews remain local',async()=>{
  const h=serverHarness(),state=await h.store.bootstrap();h.store.installReadModels();
  const rows=h.T.requestAvailability(state);assert.equal(rows[0].eventId,'server-row');
  rows[0].eventId='mutated';assert.equal(h.T.requestAvailability(state)[0].eventId,'server-row');
  assert.equal(h.T.requestAvailability(h.T.clone(state)).length,0);
  assert.equal(h.T.requestAvailability(state,{asOf:'2026-01-01'}).length,0);
  assert.equal(h.T.requestAvailability(state,{asicId:'other'}).length,0);
});

test('reload and save cannot race each other',async()=>{
  let defer=false,release;
  const h=context(async url=>{
    if(url==='/api/me')return response({subject:'test',role:'editor'});
    if(url.startsWith('/api/availability'))return response({revision:1,asOf:h.T.todayPacific(),requests:[],allocations:[],supply:[],inventory:[]});
    if(defer)await new Promise(resolve=>release=resolve);
    return response({revision:1,state:h.T.freshSeed()});
  });
  const state=await h.store.bootstrap();defer=true;const loading=h.store.load();
  await assert.rejects(h.store.save(state),/already being saved/);
  await assert.rejects(h.store.load(),/already in progress/);
  release();await loading;assert.equal(h.store.busy,false);
});

test('availability from another workspace revision cannot replace current estimates',async()=>{
  const h=context(async url=>url==='/api/me'?response({subject:'test',role:'viewer'}):url==='/api/workspace'?response({revision:1,state:h.T.freshSeed()}):response({revision:2,asOf:h.T.todayPacific(),requests:[{eventId:'stale'}],allocations:[],supply:[],inventory:[]}));
  const state=await h.store.bootstrap();h.store.installReadModels();
  assert.equal(h.T.requestAvailability(state).length,0);
});

test('all browser JavaScript compiles and active source has no local-storage authority',()=>{
  for(const name of fs.readdirSync(frontend).filter(name=>name.endsWith('.js'))){
    const source=fs.readFileSync(path.join(frontend,name),'utf8');
    assert.doesNotThrow(()=>new vm.Script(source,{filename:name}));
    assert.doesNotMatch(source,/\blocalStorage\b|\bT\.(?:load|save)\(/);
  }
});
