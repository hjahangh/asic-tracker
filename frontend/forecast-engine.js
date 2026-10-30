/* Frozen forecast versions and monthly comparison read models. */
(function () {
  'use strict';
  const TYPES=['request','expected_ship','expected_fulfilment','actual_ship','actual_fulfilment'];
  const TYPE_LABELS={request:'Demand',expected_ship:'Supply',expected_fulfilment:'Allocation',actual_ship:'Shipments',actual_fulfilment:'Arrivals'};
  const ALIASES={demand:'request',supply:'expected_ship',allocation:'expected_fulfilment',shipped:'actual_ship',shipment:'actual_ship',arrived:'actual_fulfilment',arrival:'actual_fulfilment'};
  const SHORT_MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const MAX_MONTHS=120,MAX_VERSIONS=120,MAX_LINES=50000;
  const isRecord=value=>!!value&&typeof value==='object'&&!Array.isArray(value);
  const validId=value=>typeof value==='string'&&/^[A-Za-z0-9_-]+$/.test(value)&&!['__proto__','prototype','constructor'].includes(value);
  const validMonth=value=>typeof value==='string'&&/^[0-9]{4}-(?:0[1-9]|1[0-2])$/.test(value)&&value.slice(0,4)!=='0000';
  const validDate=value=>typeof value==='string'&&window.Tracker.isDate(value);
  const validTimestamp=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value)&&validDate(value.slice(0,10))&&Number.isFinite(Date.parse(value));
  const monthNumber=value=>Number(value.slice(0,4))*12+Number(value.slice(5,7))-1;
  const fromMonthNumber=value=>String(Math.floor(value/12)).padStart(4,'0')+'-'+String(value%12+1).padStart(2,'0');
  const addMonths=(month,amount)=>{
    const index=monthNumber(month)+amount;
    if(!validMonth(month)||!Number.isInteger(amount)||index<12||index>119999)throw new Error('Forecast month must be within years 0001 through 9999.');
    return fromMonthNumber(index);
  };
  const monthLabel=month=>validMonth(month)?SHORT_MONTHS[Number(month.slice(5,7))-1]+' '+month.slice(0,4):'';
  const versionLabel=month=>validMonth(month)?month.slice(5,7)+'/'+month.slice(0,4):'';
  const today=()=>window.Tracker.todayPacific();
  const orderVersions=(a,b)=>a.month.localeCompare(b.month)||a.createdAt.localeCompare(b.createdAt)||a.id.localeCompare(b.id);
  const strings=value=>Array.isArray(value)?value.map(String).filter(Boolean):value===undefined||value===null||value===''?[]:[String(value)];
  function monthRange(start,end){
    if(!validMonth(start)||!validMonth(end)||start>end)throw new Error('Choose a valid forecast month range.');
    const count=monthNumber(end)-monthNumber(start)+1;
    if(count>MAX_MONTHS)throw new Error('Choose a forecast range of at most '+MAX_MONTHS+' months.');
    return Array.from({length:count},(_,index)=>addMonths(start,index));
  }
  function validateVersions(versions){
    if(versions===undefined)return [];
    if(!Array.isArray(versions))return ['forecastVersions must be an array.'];
    if(versions.length>MAX_VERSIONS)return ['Keep at most '+MAX_VERSIONS+' saved forecast versions.'];
    const errors=[],ids=new Set(),months=new Set();
    versions.forEach((version,index)=>{
      const label='Forecast version '+(index+1);
      if(!isRecord(version)){errors.push(label+' is invalid.');return;}
      if(!validId(version.id)||version.id==='live'||ids.has(version.id))errors.push(label+' needs a unique valid ID.');
      ids.add(version.id);
      if(!validMonth(version.month))errors.push(label+' needs a valid YYYY-MM version month.');
      if(months.has(version.month))errors.push(label+' month already has a saved version. Choose another month or delete the existing version.');
      months.add(version.month);
      if(typeof version.name!=='string'||!version.name.trim())errors.push(label+' needs a display name.');
      if(!validTimestamp(version.createdAt))errors.push(label+' needs a valid creation timestamp.');
      if(version.note!==undefined&&typeof version.note!=='string')errors.push(label+' note must be text.');
      if(!Array.isArray(version.lines)){errors.push(label+' lines must be an array.');return;}
      if(version.lines.length>MAX_LINES){errors.push(label+' has too many forecast lines.');return;}
      version.lines.forEach((line,lineIndex)=>{
        const lineLabel=label+', line '+(lineIndex+1);
        if(!isRecord(line)){errors.push(lineLabel+' is invalid.');return;}
        if(!validId(line.asicId))errors.push(lineLabel+' needs an ASIC ID.');
        if(typeof line.projectId!=='string'||(line.projectId&&!validId(line.projectId)))errors.push(lineLabel+' has an invalid project ID.');
        if(line.type!=='expected_ship'&&!line.projectId)errors.push(lineLabel+' needs a project ID for this measure.');
        if(line.type==='expected_ship'&&line.projectId)errors.push(lineLabel+' supply must remain unallocated.');
        if(!TYPES.includes(line.type))errors.push(lineLabel+' has an unsupported measure.');
        if(!validMonth(line.month))errors.push(lineLabel+' needs a valid YYYY-MM period.');
        if(!Number.isSafeInteger(line.qty)||line.qty<0)errors.push(lineLabel+' quantity must be a nonnegative safe whole number.');
        for(const key of ['asicName','projectName','category','phase'])if(typeof line[key]!=='string'||!line[key].trim())errors.push(lineLabel+' '+key+' must be nonblank text.');
        if(line.sourceEventId!==undefined&&!validId(line.sourceEventId))errors.push(lineLabel+' source event ID is invalid.');
      });
    });
    return [...new Set(errors)];
  }
  function captureLines(state){
    const T=window.Tracker;
    return (state.events||[]).filter(event=>TYPES.includes(event.type)).map(event=>{
      const asic=(state.asics||[]).find(item=>item.id===event.asicId);
      const project=(state.projects||[]).find(item=>item.id===event.projectId);
      const business=(state.businessEntities||[]).find(item=>item.id===project?.businessEntityId);
      let period=event.date;
      if(event.type==='request')period=T.requestShipBy(event);
      else if(event.type==='expected_fulfilment')period=T.allocationShipBy(state,event);
      if(!validDate(period))throw new Error('Cannot capture forecast: event '+String(event.id||'')+' has no valid period date.');
      const text=(value,fallback)=>typeof value==='string'&&value.trim()?value.trim():fallback;
      const category=text(business?.name,text(project?.entity,'Unassigned'));
      const phase=text(event.phase,text(project?.phase,'Unspecified'));
      return {asicId:event.asicId,asicName:asic?.name||'Unknown ASIC',projectId:event.projectId||'',projectName:project?.name||(event.type==='expected_ship'?'Unallocated supply':'Unknown project'),category,phase,type:event.type,month:period.slice(0,7),qty:event.qty,...(validId(event.id)?{sourceEventId:event.id}:{})};
    });
  }
  function capture(state,{id,month,name,createdAt,note=''}={}){
    const version={id,month,name:typeof name==='string'&&name.trim()?name.trim():versionLabel(month),createdAt,note,lines:captureLines(state)};
    const errors=validateVersions([version]);
    if(errors.length)throw new Error(errors.slice(0,3).join(' '));
    return version;
  }
  function safeAdd(left,right){
    const value=left+right;
    if(!Number.isSafeInteger(value))throw new Error('Forecast quantity exceeds the safe whole-number limit.');
    return value;
  }
  function summarize(state,filters={}){
    const stored=state.forecastVersions===undefined?[]:state.forecastVersions;
    const errors=validateVersions(stored);
    if(errors.length)throw new Error(errors.slice(0,3).join(' '));
    const saved=stored.slice().sort(orderVersions);
    if(filters.asOf&&!validDate(filters.asOf))throw new Error('Choose a valid forecast as-of date.');
    const asOf=validDate(filters.asOf)?filters.asOf:today();
    const sourceVersions=saved.slice();
    if(filters.includeLive===true||(!saved.length&&filters.includeLive!==false)){
      const live={id:'live',month:asOf.slice(0,7),name:'Live plan',createdAt:asOf+'T23:59:59Z',note:'Current recorded plan; not a saved forecast version.',lines:captureLines(state),isLive:true};
      sourceVersions.push(live);
    }
    // A live plan compares to the latest saved version even when its month is
    // the same or an earlier backfill label. Saved versions use chronological order.
    const metadata=sourceVersions.map((version,index)=>{
      const prior=version.isLive?saved[saved.length-1]:saved[index-1];
      return {id:version.id,month:version.month,name:version.name,createdAt:version.createdAt,note:version.note||'',isLive:!!version.isLive,priorVersionId:prior?.id||null,priorVersionName:prior?.name||null};
    });
    const selectedIds=new Set(strings(filters.versionIds?.length?filters.versionIds:filters.versionId));
    const versions=metadata.filter(version=>!selectedIds.size||selectedIds.has(version.id)||(version.isLive&&filters.includeLive!==false));
    const activeType=ALIASES[filters.type||filters.measure]||filters.type||filters.measure||'request';
    if(!TYPES.includes(activeType))throw new Error('Choose a valid forecast demand/supply measure.');
    const selectedCategory=new Set(strings(filters.categories?.length?filters.categories:filters.category));
    const selectedPhase=new Set(strings(filters.phases?.length?filters.phases:filters.phase));
    const matches=line=>(!filters.asicId||line.asicId===filters.asicId)&&(!filters.projectId||line.projectId===filters.projectId)&&(!selectedCategory.size||selectedCategory.has(line.category))&&(!selectedPhase.size||selectedPhase.has(line.phase))&&line.type===activeType;
    const filtered=new Map(sourceVersions.map(version=>[version.id,version.lines.filter(matches)]));
    const allLines=sourceVersions.flatMap(version=>version.lines);
    const allMatching=sourceVersions.flatMap(version=>filtered.get(version.id));
    const periods=allMatching.map(line=>line.month).sort();
    const requestedStart=filters.startMonth||filters.start||'',requestedEnd=filters.endMonth||filters.end||'';
    if(requestedStart&&!validMonth(requestedStart))throw new Error('Choose a valid forecast start month.');
    if(requestedEnd&&!validMonth(requestedEnd))throw new Error('Choose a valid forecast end month.');
    const naturalStart=periods[0]||asOf.slice(0,7);
    let start=requestedStart||(requestedEnd&&requestedEnd<naturalStart?requestedEnd:naturalStart);
    const minimumEnd=fromMonthNumber(Math.min(monthNumber(start)+17,119999));
    let end=requestedEnd||[periods[periods.length-1]||start,minimumEnd].sort().pop();
    let notice='';
    if(start>end)throw new Error('Forecast start month must be on or before the end month.');
    if(monthNumber(end)-monthNumber(start)+1>MAX_MONTHS){
      if(requestedStart&&requestedEnd)throw new Error('Choose a forecast range of at most '+MAX_MONTHS+' months.');
      if(requestedStart)end=addMonths(start,MAX_MONTHS-1);else start=addMonths(end,1-MAX_MONTHS);
      notice='The default forecast horizon is limited to '+MAX_MONTHS+' months. Choose a narrower start and end month to inspect another period.';
    }
    const completeMonths=monthRange(start,end);
    const selectedYears=new Set(strings(filters.years?.length?filters.years:filters.year));
    const months=completeMonths.filter(month=>!selectedYears.size||selectedYears.has(month.slice(0,4)));
    const indices=months.map(month=>completeMonths.indexOf(month));
    const neededIds=new Set(versions.flatMap(version=>[version.id,version.priorVersionId].filter(Boolean)));
    const relevantLines=sourceVersions.filter(version=>neededIds.has(version.id)).flatMap(version=>filtered.get(version.id));
    function makeRows(byProgram){
      const groups=new Map();
      const key=line=>line.asicId+(byProgram?'\u001f'+line.projectId:'');
      relevantLines.forEach(line=>groups.set(key(line),{asicId:line.asicId,asicName:line.asicName,...(byProgram?{projectId:line.projectId,projectName:line.projectName}:{})}));
      const sums=new Map(),labelsByVersion=new Map();
      for(const version of sourceVersions){
        const buckets=new Map(),labels=new Map();
        for(const line of filtered.get(version.id)){
          const groupKey=key(line);
          if(!buckets.has(groupKey))buckets.set(groupKey,new Map());
          if(!labels.has(groupKey))labels.set(groupKey,{asicName:line.asicName,...(byProgram?{projectName:line.projectName}:{})});
          const bucket=buckets.get(groupKey),existing=bucket.get(line.month)||0;
          bucket.set(line.month,safeAdd(existing,line.qty));
        }
        sums.set(version.id,buckets);labelsByVersion.set(version.id,labels);
      }
      const rows=[];
      const orderedGroups=[...groups.entries()].sort((a,b)=>a[1].asicName.localeCompare(b[1].asicName)||(a[1].projectName||'').localeCompare(b[1].projectName||'')||a[0].localeCompare(b[0]));
      for(const [groupKey,group] of orderedGroups){
        for(const version of versions){
          const current=sums.get(version.id)?.get(groupKey)||new Map();
          const prior=version.priorVersionId?sums.get(version.priorVersionId)?.get(groupKey)||new Map():null;
          let cumulative=0,priorCumulative=0;
          const values=[],present=[],cumulativeValues=[],delta=[],cumulativeDelta=[];
          for(const month of completeMonths){
            const value=current.get(month)||0,previous=prior?.get(month)||0;
            cumulative=safeAdd(cumulative,value);priorCumulative=safeAdd(priorCumulative,previous);
            values.push(value);present.push(current.has(month));cumulativeValues.push(cumulative);
            delta.push(!prior||(!current.has(month)&&!prior.has(month))?null:value-previous);
            cumulativeDelta.push(prior?cumulative-priorCumulative:null);
          }
          const select=array=>indices.map(index=>array[index]);
          const selectedValues=select(values);
          const rowLabels=labelsByVersion.get(version.id)?.get(groupKey)||labelsByVersion.get(version.priorVersionId)?.get(groupKey)||group;
          rows.push({...group,...rowLabels,versionId:version.id,versionMonth:version.month,versionName:version.name,versionLabel:version.name,isLive:version.isLive,priorVersionId:version.priorVersionId,priorVersionName:version.priorVersionName,previousVersionLabel:version.priorVersionName,values:selectedValues,quantity:selectedValues,present:select(present),cumulative:select(cumulativeValues),delta:select(delta),cumulativeDelta:select(cumulativeDelta)});
        }
      }
      return rows;
    }
    const asics=new Map((state.asics||[]).map(item=>[item.id,{id:item.id,name:item.name}]));
    const projects=new Map((state.projects||[]).map(item=>[item.id,{id:item.id,name:item.name}]));
    allLines.forEach(line=>{if(!asics.has(line.asicId))asics.set(line.asicId,{id:line.asicId,name:line.asicName});if(line.projectId&&!projects.has(line.projectId))projects.set(line.projectId,{id:line.projectId,name:line.projectName});});
    const options={asics:[...asics.values()].sort((a,b)=>a.name.localeCompare(b.name)),projects:[...projects.values()].sort((a,b)=>a.name.localeCompare(b.name)),categories:[...new Set(allLines.map(line=>line.category))].sort(),phases:[...new Set(allLines.map(line=>line.phase))].sort(),years:[...new Set(completeMonths.concat(allLines.map(line=>line.month)).map(month=>Number(month.slice(0,4))))].sort((a,b)=>a-b),types:TYPES.map(id=>({id,name:TYPE_LABELS[id]})),versions:metadata};
    return {months,monthColumns:months.map(month=>({id:month,year:Number(month.slice(0,4)),month:Number(month.slice(5,7)),label:monthLabel(month),shortLabel:SHORT_MONTHS[Number(month.slice(5,7))-1]})),versions,availableVersions:metadata,rows:makeRows(false),programRows:makeRows(true),options,cumulativeStart:start,startMonth:start,endMonth:end,type:activeType,measure:activeType,notice,basis:'Monthly demand uses requested ship-by dates; supply uses recorded availability dates; allocations use available-to-ship dates. Cumulative values begin at '+monthLabel(start)+' and include hidden-year months. Delta compares the previous saved version, including when hidden by the version filter.'};
  }
  window.ForecastEngine={MAX_MONTHS,MAX_VERSIONS,MAX_LINES,TYPES,TYPE_LABELS,validMonth,monthLabel,versionLabel,monthRange,addMonths,validateVersions,capture,summarize};
})();
