/* Family ownership is authoritative; projects inherit its business/funding links. */
(() => {
  'use strict';
  const name=(items,id)=>items.find(item=>item.id===id)?.name||'Not assigned';
  function render(c){
    const query=c.ui.query.trim().toLowerCase(),all=c.state.projectFamilies;
    const families=all.filter(f=>[f.name,f.description,name(c.state.businessEntities,f.businessEntityId),name(c.state.fundingSources,f.fundingSourceId)].join(' ').toLowerCase().includes(query));
    const rows=families.map(f=>`<tr><td><strong>${c.esc(f.name)}</strong>${f.description?'<span class="table-secondary">'+c.esc(f.description)+'</span>':''}</td><td>${c.esc(name(c.state.businessEntities,f.businessEntityId))}</td><td>${c.esc(name(c.state.fundingSources,f.fundingSourceId))}</td><td class="num">${c.metric(c.state.projects.filter(p=>p.projectFamilyId===f.id).length,'Projects assigned to this family inherit its business entity and funding source.')}</td><td>${c.btn('Edit','edit-project-family','edit',`data-id="${c.esc(f.id)}"`,'small')}</td></tr>`);
    const ready=c.state.businessEntities.length&&c.state.fundingSources.length;
    return c.title('Master data','Project families','Each family has one business entity and funding source. Its projects inherit both.',c.btn('Add family','new-project-family','plus',ready?'':'disabled','primary'))+
      `${!ready?'<div class="notice">'+c.icon('info')+'Onboard a business entity and funding source before creating a project family.</div>':''}<div class="toolbar"><input class="table-search" aria-label="Search project families" data-search="query" placeholder="Search families…" value="${c.esc(c.ui.query)}"></div><section class="panel entity-list">${c.table(['Project family','Business entity','Funding source','#Projects','Actions'],rows,`<span>${c.metric(families.length,'Number of project families matching the current search.')} of ${c.metric(all.length,'Total project families in this workspace.')} project families</span>`)}</section>`;
  }
  function form(c,familyId=''){
    const family=c.state.projectFamilies.find(item=>item.id===familyId)||{name:'',businessEntityId:'',fundingSourceId:'',description:''};
    c.setEditing(familyId);
    c.openDrawer(familyId?'Edit project family':'Add project family','Projects inherit these ownership links.',`<form id="project-family-form"><div class="drawer-body"><div id="form-errors" class="error-box hidden"></div><div class="form-grid">${c.field('Family name','name',family.name,'text',true,true)}${c.selectField('Business entity','businessEntityId',c.state.businessEntities,family.businessEntityId,true,true)}${c.selectField('Funding source','fundingSourceId',c.state.fundingSources,family.fundingSourceId,true,true)}<div class="field full"><label for="f-description">Description</label><textarea id="f-description" name="description">${c.esc(family.description||'')}</textarea></div></div><p class="subtitle">Changing ownership updates the inherited links for every project in this family. Saved forecast versions retain their captured labels.</p></div>${familyId?c.formFoot('Save family').replace('<div class="drawer-footer">','<div class="drawer-footer">'+c.btn('Delete family','delete-project-family','trash',`data-id="${c.esc(familyId)}"`,'danger')):c.formFoot('Add family')}</form>`);
  }
  function inheritance(c,familyId){
    const family=c.state.projectFamilies.find(item=>item.id===familyId);
    if(!family)return '<p class="subtitle">Select a family to view its business entity and funding source.</p>';
    return `<div class="info-grid"><div><small>Inherited business entity</small><strong>${c.esc(name(c.state.businessEntities,family.businessEntityId))}</strong></div><div><small>Inherited funding source</small><strong>${c.esc(name(c.state.fundingSources,family.fundingSourceId))}</strong></div></div>`;
  }
  window.FamilyViews={render,form,inheritance};
})();
