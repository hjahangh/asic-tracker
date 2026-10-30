/* Hover and keyboard explanations for displayed values. */
(() => {
  'use strict';
  let active=null,box=null;
  function hide(){if(active)active.removeAttribute('aria-describedby');active=null;if(box){box.hidden=true;box.textContent='';}}
  function show(target){
    if(!target?.dataset.tip)return;
    if(active&&active!==target)active.removeAttribute('aria-describedby');
    active=target;
    if(!box){box=document.createElement('div');box.id='metric-tooltip';box.className='metric-tooltip';box.setAttribute('role','tooltip');}
    const host=target.closest('dialog')||document.body;
    if(box.parentElement!==host)host.append(box);
    box.textContent=target.dataset.tip;box.hidden=false;target.setAttribute('aria-describedby',box.id);
    box.style.left='8px';box.style.top='8px';
    const anchor=target.getBoundingClientRect(),rect=box.getBoundingClientRect();
    const left=Math.max(8,Math.min(anchor.left+anchor.width/2-rect.width/2,window.innerWidth-rect.width-8));
    let top=anchor.bottom+9;if(top+rect.height>window.innerHeight-8)top=Math.max(8,anchor.top-rect.height-9);
    box.style.left=left+'px';box.style.top=top+'px';
  }
  document.addEventListener('pointerover',e=>{const target=e.target.closest?.('[data-tip]');if(target&&target!==active)show(target);});
  document.addEventListener('pointerout',e=>{if(active&&e.target.closest?.('[data-tip]')===active&&!active.contains(e.relatedTarget))hide();});
  document.addEventListener('focusin',e=>{const target=e.target.closest?.('[data-tip]');if(target)show(target);});
  document.addEventListener('focusout',e=>{if(active&&e.target.closest?.('[data-tip]')===active)hide();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
  document.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);
  window.MetricTips={hide};
})();
