/* Shared, revision-protected workspace transport. No browser-storage fallback. */
(() => {
  'use strict';
  let revision=null,user=null,busy=false,needsReload=false,lastError='',failedDraft=null,currentState=null,availability=null;
  class ApiError extends Error {
    constructor(message,status=0,code='request_failed'){super(message);this.name='ApiError';this.status=status;this.code=code;}
  }
  const clone=value=>JSON.parse(JSON.stringify(value));
  const messageOf=data=>{
    const detail=data?.detail??data;
    if(typeof detail==='string')return detail;
    if(Array.isArray(detail))return detail.map(item=>item.msg||item.message||'Invalid value').join('\n');
    if(detail?.message)return detail.message+(Array.isArray(detail.errors)?'\n'+detail.errors.join('\n'):'');
    return data?.message||'The server could not complete this request.';
  };
  async function request(path,options={}){
    let response;
    try{response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options,
      headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});}
    catch{throw new ApiError('The shared server could not be reached.');}
    let data;
    try{data=await response.json();}catch{throw new ApiError('The server returned an unreadable response. Load the latest workspace to confirm whether the change was saved.',0,'unreadable_response');}
    if(!response.ok){const code=data?.detail?.code||data?.code||(response.status===409?'revision_conflict':'request_failed');throw new ApiError(messageOf(data),response.status,code);}
    return data;
  }
  function validateEnvelope(envelope){
    if(!envelope||!Number.isSafeInteger(envelope.revision)||envelope.revision<0||!envelope.state||typeof envelope.state!=='object')throw new ApiError('The server returned an invalid workspace.');
    const state=envelope.state;
    state.projectFamilies=state.projectFamilies||[];state.forecastVersions=state.forecastVersions||[];
    window.Tracker.inheritFamilyLinks(state);
    const errors=window.Tracker.validateState(state);
    if(errors.length)throw new ApiError('The server workspace could not be validated: '+errors.slice(0,3).join(' '));
    return state;
  }
  async function updateAvailability(){
    if(!currentState)return;
    const asOf=window.Tracker.todayPacific();
    try{
      const data=await request('/api/availability?as_of='+encodeURIComponent(asOf));
      availability=data.revision===revision&&data.asOf===asOf?data:null;
    }catch{availability=null;}
  }
  async function load(){
    if(busy)throw new ApiError('A shared workspace operation is already in progress.');
    busy=true;document.body.classList.add('is-saving');document.body.setAttribute('aria-busy','true');
    try{
      const envelope=await request('/api/workspace');
      const state=validateEnvelope(envelope);
      revision=envelope.revision;currentState=state;needsReload=false;lastError='';availability=null;
      await updateAvailability();return state;
    }finally{busy=false;document.body.classList.remove('is-saving');document.body.removeAttribute('aria-busy');}
  }
  async function bootstrap(){
    user=await request('/api/me');
    if(!['viewer','editor','admin'].includes(user.role))throw new ApiError('Your account does not have an application role.',403);
    return load();
  }
  async function save(state,{operation='edit',reason='Update workspace'}={}){
    if(busy)throw new ApiError('A change is already being saved.');
    if(needsReload)throw new ApiError('Load the latest shared workspace before saving another change.',409,'revision_conflict');
    if(!Number.isSafeInteger(revision))throw new ApiError('Load the workspace before saving.');
    const payload={revision,state:clone(state),reason,operation};
    busy=true;lastError='';availability=null;document.body.classList.add('is-saving');document.body.setAttribute('aria-busy','true');
    try{
      const envelope=await request('/api/workspace',{method:'PUT',headers:{'If-Match':'"'+revision+'"'},body:JSON.stringify(payload)});
      const saved=validateEnvelope(envelope);
      revision=envelope.revision;currentState=saved;failedDraft=null;availability=null;
      await updateAvailability();return saved;
    }catch(error){
      failedDraft=payload;lastError=error.message;
      // A stale revision or an unconfirmed response must be reconciled by a read.
      if(error.status===409||error.status===0||error.status>=500)needsReload=true;
      throw error;
    }finally{busy=false;document.body.classList.remove('is-saving');document.body.removeAttribute('aria-busy');}
  }
  function exportDraft(){
    if(!failedDraft)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(failedDraft,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='asic-tracker-unsaved-draft.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function cacheFor(state,options={}){
    if(state!==currentState||!availability||((options.asOf||window.Tracker.todayPacific())!==availability.asOf))return null;
    return availability;
  }
  function installReadModels(){
    const T=window.Tracker;
    for(const [method,key] of [['requestAvailability','requests'],['allocationRows','allocations'],['supplyRows','supply'],['supplySummary','inventory']]){
      const preview=T[method];
      T[method]=(state,options={})=>{
        const cached=cacheFor(state,options);
        if(!cached||!Array.isArray(cached[key]))return preview(state,options);
        return clone(cached[key].filter(row=>!options.asicId||row.asicId===options.asicId));
      };
    }
  }
  function renderBootError(error){
    const app=document.getElementById('app');app.replaceChildren();
    const section=document.createElement('section');section.className='connection-error';
    const heading=document.createElement('h1');heading.textContent=error.status===401?'Sign-in required':'Cannot load the shared workspace';
    const message=document.createElement('p');message.textContent=error.message;
    const help=document.createElement('p');help.textContent='Contact the hosting team if access or service configuration needs attention.';
    const retry=document.createElement('button');retry.className='btn primary';retry.textContent='Try again';retry.onclick=()=>location.reload();
    section.append(heading,message,help,retry);app.append(section);
  }
  window.ApiStore={bootstrap,load,save,installReadModels,renderBootError,exportDraft,
    get user(){return user;},get revision(){return revision;},get busy(){return busy;},
    get needsReload(){return needsReload;},get lastError(){return lastError;},get hasDraft(){return !!failedDraft;}};
})();
