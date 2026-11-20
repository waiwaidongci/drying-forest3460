import {session} from '../stores/session.js';import {monitorApi} from '../api/research.js';import {esc,formObject,localTime} from '../utils/format.js';import {action,toast,bind} from '../hooks/actions.js';
export const monitorState={planId:null,active:false};
const llrText=v=>(v>=0?'+':'')+Number(v).toFixed(3);
function furnaceRow(f){
  const checked=f.checked_seq?'第'+f.checked_seq+'件 · '+esc(f.checked_piece):'尚未计入';
  const waiting=f.done?'清单已核完':f.buffered.length?'缺第'+f.next_seq+'件 · 已暂存序号 '+f.buffered.join('、'):'待报第'+f.next_seq+'件';
  const state=f.alarmed?'<span class="status failed">已报警</span>':f.done?'<span class="status completed">已核完</span>':'<span class="status running">监控中</span>';
  const alarm=f.alarmed?'第'+f.alarm_seq+'件 · '+esc(f.alarm_piece):'—';
  return '<tr><td><strong>'+esc(f.name)+'</strong></td><td>'+f.counted+' / '+f.total+'</td><td>'+checked+'</td><td>'+waiting+'</td><td>'+f.inaccurate_count+' / '+f.counted+'</td><td>'+llrText(f.llr)+'</td><td>'+state+'</td><td>'+alarm+'</td></tr>';
}
function statusTable(plan){
  return '<div class="table-wrap"><table><thead><tr><th>炉</th><th>已计入/清单</th><th>核对到</th><th>等待</th><th>失准/计入</th><th>对数似然比</th><th>状态</th><th>首次报警试件</th></tr></thead><tbody>'+plan.furnaces.map(furnaceRow).join('')+'</tbody></table></div>';
}
function alarmBanner(plan){
  const alarms=plan.furnaces.filter(f=>f.alarmed);
  if(!alarms.length)return '';
  return alarms.map(f=>'<div class="failure"><strong>'+esc(f.name)+' 预测失准已报警</strong><p>首次报警试件：第'+f.alarm_seq+'件 · '+esc(f.alarm_piece)+'（'+esc(localTime(f.alarmed_at))+'）。对数似然比达到界限 '+plan.alarm_boundary+'，后续实测继续计入；更正留痕不改变本次报警。</p></div>').join('');
}
function planOptions(plans,id){return plans.map(p=>'<option value="'+p.id+'" '+(p.id==id?'selected':'')+'>'+esc(p.name)+(p.alarmed_count?' · 已报警'+p.alarmed_count+'炉':'')+'</option>').join('')}
function furnaceOptions(plan){return plan.furnaces.map(f=>'<option value="'+f.id+'" data-next="'+(f.done?'':f.next_seq)+'">'+esc(f.name)+(f.alarmed?' · 已报警':f.done?' · 已核完':' · 待报第'+f.next_seq+'件')+'</option>').join('')}
const createSheet='<details><summary>新建监控方案</summary><form id="plan-form"><label>方案名称<input name="name" required value="十二月炉序失准监控"></label><div class="parameter-fields"><label>误报上限 α<input name="alpha" type="number" step="any" min="0" max="1" required value="0.1"></label><label>失准阈值 分钟<input name="threshold_minutes" type="number" step="any" min="0" required value="8"></label></div><label>各炉有序试件清单（每行：炉名,试件编号,预计分钟）<textarea name="lines" rows="6" required placeholder="1#炉,HX-M1-001,83.5&#10;1#炉,HX-M1-002,79.2&#10;2#炉,HX-M2-001,88.1"></textarea></label><p class="fine">行顺序即清单顺序；报警界限 = 炉数 ÷ 误报上限，首次达到即报警。</p><button type="submit">开测并冻结清单 →</button></form></details>';
export async function monitorPage(){
  const plans=await monitorApi.plans();
  if(!monitorState.planId&&plans.length)monitorState.planId=plans[0].id;
  const plan=monitorState.planId?await monitorApi.get(monitorState.planId):null;
  monitorState.active=!!(plan&&plan.furnaces.some(f=>!f.done));
  const heading='<section class="page-heading"><p class="eyebrow">07 / FURNACE WATCH</p><h1>哪台炉的预测先失准，尽早看见。</h1><p>开测定下误报上限与各炉有序试件清单；实测按清单顺序计入，失准率三成对一成的似然比累乘，首次达到炉数÷误报上限即报警。乱序补报有缺号只等该炉；已计入的更正留痕，报警仍按当时读数。</p></section>';
  if(!plan)return heading+(session.writable?'<section class="config-sheet"><h2>还没有监控方案</h2><p>开测时在此定下误报上限和各炉有序试件预测清单。</p>'+createSheet+'</section>':'<div class="empty"><strong>还没有监控方案。</strong><p>由负责人或分析师开测后，这里会显示各炉核对进度。</p></div>');
  const corrections=await monitorApi.corrections(plan.id);
  const meta='<p class="file-note">误报上限 α = '+plan.alpha+' · 失准阈值 '+plan.threshold_minutes+' 分钟 · '+plan.furnace_count+' 台炉 · 报警界限 炉数÷误报上限 = '+plan.alarm_ratio+'（对数 '+plan.alarm_boundary+'） · 开测人 '+esc(plan.created_by)+'</p>';
  const main='<section><label>监控方案<select id="plan-select">'+planOptions(plans,plan.id)+'</select></label>'+meta+alarmBanner(plan)+'<h2>各炉核对进度 <small>自动刷新 · 缺号只等该炉</small></h2>'+statusTable(plan)+'<h2>更正留痕 <small>已计入读数的更正只留痕，不改报警</small></h2>'+(corrections.length?'<div class="table-wrap"><table><thead><tr><th>北京时间</th><th>炉</th><th>序号</th><th>试件</th><th>读数更正</th><th>原因</th><th>操作人</th></tr></thead><tbody>'+corrections.map(c=>'<tr><td>'+esc(localTime(c.created_at))+'</td><td>'+esc(c.furnace)+'</td><td>第'+c.seq+'件</td><td>'+esc(c.piece_id)+'</td><td>'+c.old_minutes+' → '+c.new_minutes+' 分钟</td><td>'+esc(c.reason)+'</td><td>'+esc(c.actor)+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty"><strong>暂无更正记录。</strong></div>')+'</section>';
  const aside=session.writable?'<aside class="entry-sheet"><h2>上报实测</h2><form id="reading-form"><label>炉<select name="furnace_id" id="reading-furnace">'+furnaceOptions(plan)+'</select></label><label>清单序号<input name="seq" id="reading-seq" type="number" min="1" required value="'+(plan.furnaces.find(f=>!f.done)?.next_seq||1)+'"></label><label>实测时长 分钟<input name="actual_minutes" type="number" step="any" min="0" required></label><button type="submit">上报实测 →</button></form><details><summary>更正已计入读数</summary><form id="correction-form"><label>炉<select name="furnace_id">'+furnaceOptions(plan)+'</select></label><label>清单序号<input name="seq" type="number" min="1" required></label><label>更正后时长 分钟<input name="corrected_minutes" type="number" step="any" min="0" required></label><label>更正原因<input name="reason" required placeholder="仪表复校后读数更正"></label><button type="submit">留痕更正</button></form></details>'+createSheet+'</aside>':'<aside class="entry-sheet"><h2>阅读权限</h2><p>当前可查看各炉核对进度与首次报警试件。实测上报与更正由负责人或分析师完成。</p></aside>';
  return heading+'<div class="split">'+main+aside+'</div>';
}
function parsePlan(form){
  const data=formObject(form),furnaces=[],byName={};
  for(const line of data.lines.split(/\n+/)){
    if(!line.trim())continue;
    const parts=line.split(/[,，]/).map(s=>s.trim());
    if(parts.length!==3||!parts[0]||!parts[1])throw Error('清单行格式应为：炉名,试件编号,预计分钟');
    const minutes=Number(parts[2]);
    if(!Number.isFinite(minutes)||minutes<=0)throw Error('预计分钟必须为正数：'+line);
    if(!byName[parts[0]]){byName[parts[0]]={name:parts[0],predictions:[]};furnaces.push(byName[parts[0]])}
    byName[parts[0]].predictions.push({piece_id:parts[1],predicted_minutes:minutes});
  }
  if(!furnaces.length)throw Error('请至少录入一台炉的试件清单');
  return {name:data.name.trim(),alpha:Number(data.alpha),threshold_minutes:Number(data.threshold_minutes),furnaces};
}
export function bindMonitor(refresh){
  bind('#plan-select','change',async e=>{monitorState.planId=Number(e.target.value);await refresh()});
  bind('#reading-furnace','change',async e=>{const next=e.target.selectedOptions[0]?.dataset.next;if(next)document.getElementById('reading-seq').value=next});
  action('#reading-form',async form=>{
    const data=formObject(form);
    const r=await monitorApi.reading(monitorState.planId,{furnace_id:Number(data.furnace_id),seq:Number(data.seq),actual_minutes:Number(data.actual_minutes)});
    await refresh();
    if(r.alarm)toast(r.alarm.furnace+' 第'+r.alarm.seq+'件首次报警：'+r.alarm.piece,true);
    else toast(r.message);
  });
  action('#correction-form',async form=>{
    const data=formObject(form);
    const r=await monitorApi.correct(monitorState.planId,{furnace_id:Number(data.furnace_id),seq:Number(data.seq),corrected_minutes:Number(data.corrected_minutes),reason:data.reason});
    await refresh();toast(r.message);
  });
  action('#plan-form',async form=>{
    const plan=await monitorApi.create(parsePlan(form));
    monitorState.planId=plan.id;await refresh();toast('监控方案已开测，清单已冻结');
  });
}
