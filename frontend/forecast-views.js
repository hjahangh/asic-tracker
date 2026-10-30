/* Monthly and cumulative forecast comparisons, based on real saved plan versions. */
(() => {
  'use strict';
  const MEASURES=[
    {id:'request',name:'Demand / requests',basis:'requested ship-by dates'},
    {id:'expected_ship',name:'Supply',basis:'received or expected inventory dates'},
    {id:'expected_fulfilment',name:'Allocations',basis:'available-to-ship dates'},
    {id:'actual_ship',name:'Shipments',basis:'recorded shipping dates'},
    {id:'actual_fulfilment',name:'Arrivals',basis:'recorded arrival dates'}
  ];
  const COLORS=['#0A60FF','#039DBE','#07182D','#597DA8','#29617E','#738CB1','#087E9A','#405A7B'];
  const monthLabel=(value,long=false)=>{
    if(!/^\d{4}-\d{2}$/.test(String(value||'')))return String(value||'');
    return new Date(value+'-01T12:00:00Z').toLocaleDateString('en-US',{month:long?'long':'short',...(long?{year:'numeric'}:{}),timeZone:'UTC'});
  };
  const versionLabel=v=>{
    if(v.isLive||v.id==='live')return 'Live plan';
    const month=v.month||v.versionMonth||'',stamp=month?`${month.slice(5)}/${month.slice(0,4)}`:'',name=v.name||v.versionName||v.versionLabel||'';
    return stamp+(name&&name!==stamp?' · '+name:'')||name||'Saved version';
  };
  const list=value=>Array.isArray(value)?value:value?[value]:[];
  const mode=c=>c.ui.forecastMode==='cumulative'?'cumulative':'monthly';
  const tab=c=>['summary','program','chart'].includes(c.ui.forecastTab)?c.ui.forecastTab:'summary';
  const measure=c=>MEASURES.find(item=>item.id===c.ui.forecastMeasure)||MEASURES[0];
  const sortedUnique=values=>[...new Set(values.filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b)));
  const fallbackOptions=c=>({asics:c.state.asics||[],projects:c.state.projects||[],categories:sortedUnique((c.state.businessEntities||[]).map(x=>x.name)),phases:sortedUnique((c.state.projects||[]).map(x=>x.phase)),years:[],types:MEASURES});
  function getModel(c){
    try{return window.ForecastEngine.summarize(c.state,{
      asOf:c.referenceDate(),asicId:c.ui.forecastAsicId||'',projectId:c.ui.forecastProjectId||'',
      category:c.ui.forecastCategory||'',phase:c.ui.forecastPhase||'',type:c.ui.forecastMeasure||'request',
      startMonth:c.ui.forecastStart||'',endMonth:c.ui.forecastEnd||'',year:c.ui.forecastYear||'',
      versionIds:list(c.ui.forecastVersionIds),includeLive:c.ui.forecastIncludeLive!==false
    });}catch(error){return {months:[],versions:[],rows:[],programRows:[],options:fallbackOptions(c),error:error.message||'The selected forecast range is invalid.'};}
  }
  const plainVersionLabel=row=>versionLabel({...row,id:row.versionId});
  const priorLabel=(data,row)=>{const prior=(data.availableVersions||data.options?.versions||[]).find(v=>v.id===row.priorVersionId);return prior?versionLabel(prior):row.previousVersionLabel||row.priorVersionName||'the previous saved version';};
  const signed=(c,value)=>value>0?'+'+c.n(value):c.n(value);
  const sourceLabel=(c,row)=>tab(c)==='program'?`${row.projectName||'Unassigned project'} / ${row.asicName}`:row.asicName;
  const valueArray=(row,currentMode,delta)=>delta?(currentMode==='cumulative'?row.cumulativeDelta:row.delta):(currentMode==='cumulative'?row.cumulative:row.values||row.quantity);
  function explanation(c,data,row,index,delta=false){
    const currentMode=mode(c),values=valueArray(row,currentMode,delta)||[],value=values[index],period=monthLabel(data.months[index],true),version=plainVersionLabel(row),label=sourceLabel(c,row),chosen=measure(c);
    if(delta&&value==null)return `${label}. Forecast version ${version}. ${period}. ${row.priorVersionId?'No monthly quantity is recorded in either this version or '+priorLabel(data,row)+', so no monthly delta is shown.':'No earlier saved forecast version exists, so a prior-version delta is not available.'}`;
    if(delta){
      const now=(valueArray(row,currentMode,false)||[])[index]||0,prior=now-value;
      return `${label}. ${period}. ${currentMode==='cumulative'?'Cumulative delta':'Delta from prior'}: ${c.n(now)} in ${version} minus ${c.n(prior)} in ${priorLabel(data,row)} = ${signed(c,value)} units. The previous chronological saved version is used even if it is hidden by the version filter.`;
    }
    if(currentMode==='cumulative')return `${label}. Forecast version ${version}. ${c.n(value||0)} cumulative ${chosen.name.toLowerCase()} units from ${monthLabel(data.cumulativeStart||data.months[0],true)} through ${period}. This adds monthly quantities using ${chosen.basis}; filtering years hides columns without resetting the running total.`;
    return `${label}. Forecast version ${version}. ${period}: ${c.n(value||0)} ${chosen.name.toLowerCase()} units recorded for this month, using ${chosen.basis}.${row.present&&!row.present[index]?' No matching quantity was recorded in this cell.':''}`;
  }
  function cell(c,data,row,index,delta=false){
    const value=(valueArray(row,mode(c),delta)||[])[index],tip=explanation(c,data,row,index,delta);
    const absent=!delta&&mode(c)==='monthly'&&row.present&&!row.present[index];
    const text=value==null||absent?'—':delta?signed(c,value):c.n(value);
    const tone=delta&&value!=null?(value>0?' forecast-increase':value<0?' forecast-decrease':' forecast-no-change'):'';
    return `<span class="forecast-value${tone}">${c.tip(text,tip)}</span>`;
  }
  function filterBar(c,data){
    const {ui,esc,options}=c,o=data.options||fallbackOptions(c),selectedVersions=list(ui.forecastVersionIds),allVersions=(data.availableVersions||c.state.forecastVersions||[]).filter(v=>v.id!=='live');
    const years=(o.years||[]).map(year=>({id:String(year),name:String(year)}));
    const advanced=[ui.forecastCategory,ui.forecastPhase,ui.forecastProjectId,ui.forecastYear,selectedVersions.length,ui.forecastIncludeLive===false].filter(Boolean).length;
    const active=ui.forecastAsicId||ui.forecastCategory||ui.forecastPhase||ui.forecastProjectId||ui.forecastYear||ui.forecastStart||ui.forecastEnd||selectedVersions.length||ui.forecastIncludeLive===false||ui.forecastMeasure&&ui.forecastMeasure!=='request';
    return `<div class="forecast-filters"><div class="toolbar forecast-filter-bar"><div class="control"><label for="forecast-asic">ASIC</label><select id="forecast-asic" aria-label="Filter forecast ASIC" data-filter="forecastAsicId">${options(o.asics||[],ui.forecastAsicId||'','All ASICs')}</select></div><div class="control"><label for="forecast-measure">Demand / supply</label><select id="forecast-measure" aria-label="Filter forecast measure" data-filter="forecastMeasure">${options(MEASURES,ui.forecastMeasure||'request')}</select></div><div class="control forecast-period-control"><label for="forecast-start">From</label><input id="forecast-start" aria-label="Forecast start month" type="month" data-filter="forecastStart" value="${esc(ui.forecastStart||data.startMonth||data.cumulativeStart||data.months[0]||'')}"></div><div class="control forecast-period-control"><label for="forecast-end">Through</label><input id="forecast-end" aria-label="Forecast end month" type="month" data-filter="forecastEnd" value="${esc(ui.forecastEnd||data.endMonth||data.months[data.months.length-1]||'')}"></div>${active?'<button type="button" class="filter-reset" data-action="clear-forecast-filters">Clear filters</button>':''}</div><details class="request-basis forecast-more-filters" ${advanced?'open':''}><summary>${c.icon('search')}More filters${advanced?' · '+c.metric(advanced,'Number of active advanced forecast filters.'):''}</summary><div class="forecast-advanced-grid"><div class="field"><label for="forecast-category">Category / business entity</label><select id="forecast-category" aria-label="Filter forecast category" data-filter="forecastCategory">${options(o.categories||[],ui.forecastCategory||'','All categories')}</select><small>Uses the business-entity label stored in each version.</small></div><div class="field"><label for="forecast-phase">Engineering phase</label><select id="forecast-phase" aria-label="Filter forecast engineering phase" data-filter="forecastPhase">${options(o.phases||[],ui.forecastPhase||'','All phases')}</select></div><div class="field"><label for="forecast-project">Program / project</label><select id="forecast-project" aria-label="Filter forecast project" data-filter="forecastProjectId">${options(o.projects||[],ui.forecastProjectId||'','All programs')}</select></div><div class="field"><label for="forecast-year">Year of period</label><select id="forecast-year" aria-label="Filter forecast year" data-filter="forecastYear">${options(years,ui.forecastYear||'','All years')}</select><small>Hides other years; cumulative totals retain their starting point.</small></div><div class="field forecast-version-filter"><label for="forecast-versions">Saved versions</label><select id="forecast-versions" aria-label="Filter forecast versions" data-filter="forecastVersionIds" multiple size="${Math.min(4,Math.max(2,allVersions.length))}">${allVersions.map(v=>`<option value="${esc(v.id)}" ${selectedVersions.includes(v.id)?'selected':''}>${esc(versionLabel(v))}</option>`).join('')}</select><small>No selection includes all saved versions. Use ⌘ / Ctrl to select several.</small></div><label class="forecast-checkbox"><input type="checkbox" data-filter="forecastIncludeLive" aria-label="Include live forecast plan" ${ui.forecastIncludeLive!==false?'checked':''}><span>Include live plan<small>Current records remain separate from saved versions.</small></span></label></div></details></div>`;
  }
  function tableGroups(c,rows){
    const groups=new Map();
    rows.forEach(row=>{const key=tab(c)==='program'?JSON.stringify([row.asicId,row.projectId||'']):row.asicId;
      if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);
    });
    return [...groups.values()];
  }
  function matrix(c,data,rows,{quantityOnly=false,id='forecast-matrix'}={}){
    if(!rows.length||!data.months.length)return `<div class="empty forecast-empty"><h2>No matching forecast records</h2><p>Change the filters or save a version after adding requests, supply or allocations.</p></div>`;
    const groups=tableGroups(c,rows),columns=data.months,years=[];
    columns.forEach(month=>{const year=month.slice(0,4);if(years.length&&years[years.length-1].year===year)years[years.length-1].count++;else years.push({year,count:1});});
    const cumulative=mode(c)==='cumulative',sections=quantityOnly?[false]:[false,true],caption=`${tab(c)==='program'?'Forecast by program':'Forecast summary'} — ${cumulative?'cumulative':'monthly'} ${measure(c).name.toLowerCase()}`;
    let body='';
    groups.forEach((group,groupIndex)=>{
      const first=group[0],labelId=`${id}-label-${groupIndex}`;
      sections.forEach((delta,sectionIndex)=>{
        const measureId=`${id}-measure-${groupIndex}-${sectionIndex}`;
        group.forEach((row,versionIndex)=>{
          const versionId=`${id}-version-${groupIndex}-${sectionIndex}-${versionIndex}`,metricLabel=delta?(cumulative?'Cumulative delta':'Delta from prior'):(cumulative?'Cumulative qty':'Quantity');
          const line=columns.map((month,index)=>`<td class="num${month.endsWith('-01')?' forecast-year-start':''}" headers="${labelId} ${measureId} ${versionId} ${id}-month-${index}">${cell(c,data,row,index,delta)}</td>`).join('');
          body+=`<tr class="${versionIndex%2?'forecast-stripe ':''}${sectionIndex&&versionIndex===0?'forecast-section-start ':''}${groupIndex&&sectionIndex===0&&versionIndex===0?'forecast-group-start':''}">${sectionIndex===0&&versionIndex===0?`<th id="${labelId}" scope="rowgroup" rowspan="${group.length*sections.length}" class="forecast-label-col">${tab(c)==='program'?'<strong>'+c.esc(first.projectName||'Unassigned project')+'</strong><span class="table-secondary">'+c.esc(first.asicName)+'</span>':'<strong>'+c.esc(first.asicName)+'</strong>'}</th>`:''}${versionIndex===0?`<th id="${measureId}" scope="rowgroup" rowspan="${group.length}" class="forecast-measure-col">${c.esc(metricLabel)}</th>`:''}<th id="${versionId}" scope="row" class="forecast-version-col">${c.tip(plainVersionLabel(row),row.versionId==='live'?'Current live records; this row changes as the workspace is edited.':'Saved forecast version '+plainVersionLabel(row)+'. Its captured quantities and labels do not change when the live workspace is edited.')}</th>${line}</tr>`;
        });
      });
    });
    return `<div class="forecast-matrix-scroll" role="region" aria-label="${c.esc(caption)}" tabindex="0"><table class="forecast-matrix${tab(c)==='program'?' forecast-program-matrix':''}" style="min-width:${Math.max(840,columns.length*76+(tab(c)==='program'?474:424))}px"><caption class="forecast-sr-only">${c.esc(caption)}. Columns are period months; rows compare frozen forecast versions and differences from the previous saved version.</caption><thead><tr class="forecast-year-header"><th rowspan="2" class="forecast-label-col" scope="col">${tab(c)==='program'?'Program / ASIC':'ASIC'}</th><th rowspan="2" class="forecast-measure-col" scope="col">Measure</th><th rowspan="2" class="forecast-version-col" scope="col">Forecast version</th>${years.map(y=>`<th scope="colgroup" colspan="${y.count}">${c.esc(y.year)}</th>`).join('')}</tr><tr class="forecast-month-header">${columns.map((month,index)=>`<th id="${id}-month-${index}" scope="col" class="${month.endsWith('-01')?'forecast-year-start':''}">${c.esc(monthLabel(month))}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
  }
  function chart(c,data){
    if(!data.rows.length||!data.months.length)return matrix(c,data,[]);
    const versions=new Map();
    data.rows.forEach(row=>{
      if(!versions.has(row.versionId))versions.set(row.versionId,{id:row.versionId,label:plainVersionLabel(row),values:data.months.map(()=>0)});
      const series=versions.get(row.versionId),values=valueArray(row,mode(c),false)||[];
      values.forEach((value,index)=>{series.values[index]+=value||0;});
    });
    const all=[...versions.values()],series=all.slice(-8),width=1000,height=330,left=65,right=23,top=23,bottom=52,max=Math.max(1,...series.flatMap(row=>row.values)),upper=max<=5?Math.ceil(max):Math.ceil(max/5)*5;
    const x=index=>left+index*(width-left-right)/Math.max(1,data.months.length-1),y=value=>height-bottom-value/upper*(height-top-bottom);
    const ticks=[0,1,2,3,4].map(i=>upper*i/4),step=Math.max(1,Math.ceil(data.months.length/12));
    const lines=series.map((row,seriesIndex)=>{
      const color=COLORS[seriesIndex%COLORS.length],dash=seriesIndex>3?' stroke-dasharray="6 3"':'',path=row.values.map((v,i)=>(i?'L':'M')+x(i).toFixed(2)+','+y(v).toFixed(2)).join(' ');
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.4"${dash} stroke-linejoin="round"/>${row.values.map((value,index)=>{const explanation=`${row.label}. ${monthLabel(data.months[index],true)}. ${c.n(value)} ${mode(c)==='cumulative'?'cumulative ':''}${measure(c).name.toLowerCase()} units across the selected ASICs and programs.${mode(c)==='cumulative'?' Running total starts '+monthLabel(data.cumulativeStart||data.months[0],true)+'.':''}`;return `<circle class="forecast-chart-point" cx="${x(index).toFixed(2)}" cy="${y(value).toFixed(2)}" r="4" fill="white" stroke="${color}" stroke-width="2" tabindex="0" data-tip="${c.esc(explanation)}" aria-label="${c.esc(explanation)}"><title>${c.esc(explanation)}</title></circle>`;}).join('')}`;
    }).join('');
    return `<div class="forecast-chart-wrap"><svg class="forecast-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="forecast-chart-title forecast-chart-description"><title id="forecast-chart-title">${mode(c)==='cumulative'?'Cumulative':'Monthly'} forecast comparison</title><desc id="forecast-chart-description">Each line is one forecast version, summed across the selected ASICs and programs. Point values are available on hover and keyboard focus. A detailed table follows the chart.</desc>${ticks.map(value=>`<line x1="${left}" y1="${y(value)}" x2="${width-right}" y2="${y(value)}" stroke="#DCE6F0" stroke-dasharray="3 4"/><text x="${left-10}" y="${y(value)+4}" text-anchor="end">${c.esc(c.n(Math.round(value)))}</text>`).join('')}${lines}${data.months.map((month,index)=>index%step===0||index===data.months.length-1?`<text x="${x(index)}" y="${height-24}" text-anchor="middle">${c.esc(monthLabel(month))}<tspan x="${x(index)}" dy="15">${c.esc(month.slice(0,4))}</tspan></text>`:'').join('')}</svg><div class="forecast-chart-legend">${series.map((row,index)=>`<span><i style="background:${COLORS[index%COLORS.length]}"></i>${c.esc(row.label)}</span>`).join('')}</div>${all.length>8?'<p class="forecast-chart-note">Showing the latest eight matching versions. Narrow the version filter to compare older plans. CSV export includes all matching versions.</p>':''}</div><details class="forecast-chart-data"><summary>View chart data by ASIC</summary>${matrix(c,data,data.rows,{quantityOnly:true,id:'forecast-chart-table'})}</details>`;
  }
  function history(c){
    const versions=(c.state.forecastVersions||[]).slice().sort((a,b)=>String(b.month).localeCompare(String(a.month))||String(b.createdAt).localeCompare(String(a.createdAt)));
    if(!versions.length)return '';
    return `<details class="request-basis forecast-history"><summary>${c.icon('calendar')}Saved versions · ${c.metric(versions.length,'Number of frozen forecast versions saved in this workspace.')}</summary><p>Versions keep the captured quantities and labels. A newer plan does not overwrite earlier versions.</p><div class="forecast-history-list">${versions.map(v=>`<div class="forecast-history-row"><div><strong>${c.esc(versionLabel(v))}</strong><span class="table-secondary">Saved ${c.esc(v.createdAt?c.date(v.createdAt.slice(0,10)):'date unknown')}${v.note?' · '+c.esc(v.note):''}</span></div>${c.btn('Delete version','delete-forecast-version','trash',`data-id="${c.esc(v.id)}"`,'small')}</div>`).join('')}</div><p class="forecast-history-note">Deleting a version changes the prior-version baseline for later comparisons. A recovery point is saved.</p></details>`;
  }
  function render(c){
    const data=getModel(c),rows=tab(c)==='program'?data.programRows||[]:data.rows||[],currentMode=mode(c),hasHistory=(c.state.forecastVersions||[]).length>0;
    const tabs=[['summary','Forecast Summary'],['program','By Program'],['chart','Summary Chart']];
    const toolbar=`<div class="forecast-view-toolbar"><div class="forecast-tabs" role="tablist" aria-label="Forecast views">${tabs.map(([id,label])=>`<button type="button" role="tab" id="forecast-tab-${id}" aria-selected="${tab(c)===id}" aria-controls="forecast-view-panel" class="${tab(c)===id?'active':''}" data-action="forecast-tab" data-tab="${id}">${label}</button>`).join('')}</div><div class="forecast-mode-switch" role="group" aria-label="Forecast quantity mode">${[['monthly','Monthly'],['cumulative','Cumulative']].map(([id,label])=>`<button type="button" class="${currentMode===id?'active':''}" aria-pressed="${currentMode===id}" data-action="forecast-mode" data-mode="${id}">${label}</button>`).join('')}</div></div>`;
    const header=c.title('Planning','Forecasts','Compare monthly plans, cumulative quantities and changes from earlier versions.',c.btn('Save forecast version','new-forecast-version','plus','','primary'));
    const badge=!hasHistory&&c.ui.forecastIncludeLive!==false?`<div class="forecast-live-notice">${c.icon('info')}<div><strong>Live plan</strong><span>Save a version to begin a forecast history and compare how plans change over time.</span></div></div>`:'';
    const error=data.error?`<div class="error-box">${c.esc(data.error)}</div>`:data.notice?`<div class="notice">${c.icon('info')}${c.esc(data.notice)}</div>`:'';
    const content=data.error?'':!data.rows.length&&!data.programRows?.length&&!(c.state.events||[]).length?`<section class="panel forecast-empty-panel"><div class="empty entity-empty forecast-empty">${c.icon('chart')}<h2>No forecast data yet</h2><p>Add requests, supply or allocations, then save the plan as a forecast version.</p><div class="onboarding-actions">${c.btn('New request','new-request','plus','','primary')}${c.btn('Add inventory','new-supply','box')}</div></div></section>`:`<section id="forecast-view-panel" role="tabpanel" aria-labelledby="forecast-tab-${tab(c)}" class="panel forecast-matrix-panel"><div class="forecast-panel-heading"><div><h2>${tab(c)==='program'?'Forecast by Program':tab(c)==='chart'?'Forecast Summary Chart':'Forecast Summary'}${tab(c)!=='chart'?' · '+(currentMode==='cumulative'?'Cumulative Qty':'Qty'):''}</h2><p>${c.esc(measure(c).name)} · ${data.months.length?c.esc(monthLabel(data.months[0],true)+' – '+monthLabel(data.months[data.months.length-1],true)):'No period months'}</p></div><button type="button" class="btn small" data-action="export-forecast" ${!rows.length?'disabled':''}>${c.icon('download')}Export CSV</button></div>${tab(c)==='chart'?chart(c,data):matrix(c,data,rows)}<div class="forecast-table-note"><span>Hover over or focus a value for its calculation.</span><span>— = no recorded monthly quantity or no prior version.</span></div></section>`;
    const cumulativeStart=data.cumulativeStart||data.months[0];
    const basis=`<details class="request-basis forecast-basis"><summary>${c.icon('info')}How forecast comparisons work</summary><p>Monthly values group ${c.esc(measure(c).name.toLowerCase())} by ${c.esc(measure(c).basis)}. Cumulative quantities add those monthly values${cumulativeStart?' from '+c.esc(monthLabel(cumulativeStart,true)):''}; totals continue across December and January. A year filter hides columns without changing the running total.</p><p>Demand uses total requested quantity, rather than remaining open units. Supply uses recorded receipts and incoming entries, rather than the current on-hand balance. Requests and Supply show current availability.</p><p>Delta from prior compares each version with the immediately earlier saved version, even if that prior version is hidden by a filter. A first version has no baseline. ${c.ui.forecastIncludeLive!==false?'The live plan compares with the latest saved version. ':''}Category means the business entity stored in the version; By Program groups records by project. Forecast coverage and explicit allocations remain separate.</p></details>`;
    return `<div class="forecast-page">${header}${toolbar}${filterBar(c,data)}${badge}${error}${content}${history(c)}${basis}</div>`;
  }
  function captureForm(c){
    c.setEditing('');
    c.openDrawer('Save forecast version','Capture the complete live plan before it changes.',`<form id="forecast-version-form"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div><div class="forecast-capture-note">${c.icon('calendar')}<p>This saves current requests, supply, allocations, shipments and arrivals across the workspace. Page filters do not limit what is captured.</p></div><div class="form-grid">${c.field('Forecast version month','forecastMonth',c.referenceDate().slice(0,7),'month',false,true,'Version month labels the current records; it does not reconstruct that historical month. One saved version per month: choose another month or delete the existing version.')}${c.field('Version name (optional)','forecastName','','text',false,false,'For example, October operating plan.')}<div class="field full"><label for="f-forecastNote">Note</label><textarea id="f-forecastNote" name="forecastNote" placeholder="What changed in this plan?"></textarea><small>Optional. Quantities and labels are frozen in the saved version.</small></div></div></div>${c.formFoot('Save forecast version')}</form>`);
  }
  function exportReport(c){
    const data=getModel(c),rows=tab(c)==='program'?data.programRows||[]:data.rows||[],out=[];
    rows.forEach(row=>[false,true].forEach(delta=>{
      const values=valueArray(row,mode(c),delta)||[];
      out.push([row.asicName,row.projectName||'',delta?(mode(c)==='cumulative'?'Cumulative delta':'Delta from prior'):(mode(c)==='cumulative'?'Cumulative qty':'Quantity'),plainVersionLabel(row),row.versionMonth||'',row.priorVersionId?priorLabel(data,row):'',...data.months.map((_,index)=>values[index]==null||!delta&&mode(c)==='monthly'&&row.present&&!row.present[index]?'':values[index])]);
    }));
    return {name:'forecast-'+tab(c)+'-'+mode(c),headers:['ASIC','Program / project','Measure','Forecast version','Version month','Prior version',...data.months],rows:out};
  }
  window.ForecastViews={render,captureForm,exportReport,getModel};
})();
