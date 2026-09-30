"use strict";
const $ = (id) => document.getElementById(id);
const ui = {data:null, seq:0, sourceSeq:0, pending:false, sourceReturn:null};
const labels = {changed:"변경",added:"추가",removed:"삭제",unchanged:"변경 없음",
  upcoming_no_action:"발효 예정 · 기록 불가",awaiting_assignment:"발효됨 · 배정 대기",
  pending_read:"읽음 확인 대기",read_acknowledged:"읽음 확인됨 · 원문 점검 별도",
  assessed_self_check:"원문 조항 점검 기록됨"};
function node(tag, cls, value) {
  const e=document.createElement(tag);
  if(cls)e.className=cls;
  if(value!==undefined)e.textContent=value;
  return e;
}
function clear(id){$(id).replaceChildren();}
function scope(){return {as_of:$("as-of").value,role:$("role").value,site:$("site").value};}
function query(fields){return new URLSearchParams(fields).toString();}
function message(value){$("status").textContent=value;}
async function api(path, options) {
  const response=await fetch(path,options);
  let data;
  try{data=await response.json();}catch{throw new Error("응답 형식 오류");}
  if(!response.ok)throw new Error(data.error||"요청 실패");
  return data;
}
function sourceButton(revision,clauseId) {
  const b=node("button","source-button",revision+" 원문 · "+clauseId);
  b.type="button";b.addEventListener("click",()=>openSource(revision,clauseId,b));
  return b;
}
async function openSource(revision,clauseId,button) {
  const turn=++ui.sourceSeq, context=scope(), seq=ui.seq;
  ui.sourceReturn=button;
  $("source-title").textContent=revision+" · "+clauseId;
  $("source-meta").textContent="원문을 확인하고 있습니다.";
  $("source-text").textContent="";
  $("source-hash").textContent="";
  $("source-dialog").showModal();
  try {
    const data=await api("/api/source?"+query({...context,revision,clause_id:clauseId}));
    if(turn!==ui.sourceSeq||seq!==ui.seq)return;
    $("source-meta").textContent=data.state+" · "+data.site+" · 발효 "+(data.effective_at||"없음");
    $("source-text").textContent=data.clause.text;
    $("source-hash").textContent="SHA-256 "+data.source_hash;
  } catch(error) {
    if(turn===ui.sourceSeq&&seq===ui.seq)$("source-meta").textContent="원문을 확인할 수 없습니다: "+error.message;
  }
}
$("source-close").addEventListener("click",()=>$("source-dialog").close());
$("source-dialog").addEventListener("close",()=>{
  ui.sourceSeq++;
  if(ui.sourceReturn&&ui.sourceReturn.isConnected)ui.sourceReturn.focus();
  ui.sourceReturn=null;
});
function renderDiff(data) {
  clear("diff-rows");
  const changed=data.diff.filter(r=>r.kind!=="unchanged").length;
  $("diff-count").textContent=changed+"개 변경·추가·삭제";
  for(const row of data.diff){
    const wrapper=node("article","diff-row");
    const label=node("div","diff-label");
    label.append(node("strong","",row.clause_id),node("span","chip "+row.kind,labels[row.kind]));
    const pair=node("div","pair");
    for(const [revision,item,cls] of [["A",row.before,"before"],["B",row.after,"after"]]){
      const cell=node("div","clause "+cls);
      cell.append(node("p",item?"":"empty",item?item.text:"해당 판에 없음"));
      if(item)cell.append(sourceButton(revision,row.clause_id));
      pair.append(cell);
    }
    wrapper.append(label,pair);$("diff-rows").append(wrapper);
  }
}
function renderBriefings(data) {
  clear("briefings");
  const entries=data.mapping.affected;
  $("briefing-count").textContent=entries.length+"개";
  if(!entries.length)$("briefings").append(node("p","help","해당 역할의 변경 브리핑이 없습니다."));
  for(const b of entries){
    const card=node("article","brief-card");
    card.append(node("h3","",b.briefing_id),
      node("p","","바뀐 조항: "+b.changed_clause_ids.join(", ")),
      node("p","","의존 질문: "+(b.question_ids.join(", ")||"없음")));
    $("briefings").append(card);
  }
}
function payloadFor(item) {
  return {...scope(),briefing_id:item.briefing_id,fingerprint:item.fingerprint,
          request_id:crypto.randomUUID()};
}
async function submit(kind,item,answer) {
  if(ui.pending)return;
  const turn=ui.seq, payload=payloadFor(item);
  if(answer!==undefined)payload.answer=answer;
  ui.pending=true;renderQueue(ui.data);
  try{
    const receipt=await api(kind==="ack"?"/api/ack":"/api/assess",{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if(turn!==ui.seq)return;
    message(receipt.kind==="read_acknowledged"?"읽음 확인을 기록했습니다. 역량 인증은 아닙니다.":"원문 조항 선택 점검을 별도로 기록했습니다.");
    await load(false);
  }catch(error){
    if(turn===ui.seq)message("기록 결과를 단정할 수 없습니다: "+error.message+". 이력을 새로 확인한 뒤 다시 시도하세요.");
  }finally{
    ui.pending=false;
    if(ui.data)renderQueue(ui.data);
  }
}
function renderQueue(data) {
  clear("queue");
  $("queue-count").textContent=data.queue.length+"개";
  if(!data.queue.length)$("queue").append(node("p","help","이 역할에 연결된 새 브리핑이 없습니다."));
  for(const item of data.queue){
    const card=node("article","queue-card");
    card.append(node("h3","",item.briefing_id),node("p","",labels[item.status]||item.status),
      node("p","","원문 의존: "+item.clause_ids.join(", ")));
    const actions=node("div","actions");
    if(item.status==="pending_read"){
      const button=node("button","action primary","읽음 확인 기록");
      button.disabled=ui.pending||!item.ack_allowed;
      button.addEventListener("click",()=>submit("ack",item));
      actions.append(button);
    }else if(item.status==="read_acknowledged"){
      const select=node("select","answer");
      select.setAttribute("aria-label",item.briefing_id+" 변경 원문 조항 선택");
      select.append(node("option","","변경 원문 조항 선택"));
      select.firstChild.value="";
      for(const clauseId of item.changed_clause_ids){
        const option=node("option","",clauseId);option.value=clauseId;select.append(option);
      }
      const button=node("button","action","원문 조항 점검 기록");
      button.disabled=ui.pending;
      button.addEventListener("click",()=>{
        if(!select.value){message("먼저 변경 원문 조항을 선택하세요.");select.focus();return;}
        submit("assess",item,select.value);
      });
      card.append(select);actions.append(button);
    }
    card.append(actions);$("queue").append(card);
  }
}
async function exportReceipt(receipt,button) {
  const turn=ui.seq, context=scope();
  button.disabled=true;
  try{
    const data=await api("/api/export/"+encodeURIComponent(receipt.receipt_id)+"?"+query(context));
    if(turn!==ui.seq)return;
    const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob), a=node("a");
    a.href=url;a.download="fictional-sop-"+receipt.receipt_id+".json";a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    message("현재 원문·역할·발효 맥락에서 검증한 영수증을 내려받았습니다.");
  }catch(error){if(turn===ui.seq)message("내보내기 거절: "+error.message);}
  finally{if(turn===ui.seq)button.disabled=false;}
}
function renderHistory(data) {
  clear("history");
  if(!data.history.length)$("history").append(node("li","","이 역할의 확인 이력이 없습니다."));
  for(const receipt of data.history){
    const item=node("li");
    item.append(node("strong","",receipt.revision+" · "+receipt.briefing_id+" · "+receipt.kind),
      node("span","meta",receipt.at+" · "+receipt.origin+
        (receipt.current_binding?" · 현재 원문 결합":" · 과거 판 / 맥락 이력")));
    const matching=data.queue.find(q=>q.briefing_id===receipt.briefing_id&&q.ack_allowed&&
      q.fingerprint===receipt.fingerprint);
    if(receipt.current_binding&&matching){
      const button=node("button","export-button","현재 맥락 JSON 내보내기");
      button.addEventListener("click",()=>exportReceipt(receipt,button));item.append(button);
    }
    $("history").append(item);
  }
}
function render(data){
  ui.data=data;
  $("current-revision").textContent=data.current_revision||"없음";
  $("current-note").textContent=data.current_revision==="A"?
    "A가 현재 적용됩니다. B의 승인·출판은 미래 발효를 앞당기지 않습니다.":
    data.current_revision==="B"?"B가 현재 적용됩니다. 배정과 확인은 별도 상태입니다.":"발효된 판이 없습니다.";
  $("upcoming-revision").textContent=(data.upcoming_revision||"예정 판 없음")+" · C 반려";
  $("upcoming-note").textContent=data.upcoming_revision?
    "B 발효: 2026-10-02 00:00 UTC · 반려 C는 지침이 아닙니다.":
    "반려 C는 지침이 아닙니다.";
  $("coverage-state").textContent=data.mapping.complete?"선언된 의존 관계 확인":"의존 관계 미확인";
  renderDiff(data);renderBriefings(data);renderQueue(data);renderHistory(data);
}
async function load(announce=true){
  const turn=++ui.seq, context=scope();
  ui.sourceSeq++;
  if($("source-dialog").open)$("source-dialog").close();
  ui.data=null;
  for(const id of ["diff-rows","briefings","queue","history"])clear(id);
  if(announce)message("선택한 맥락의 원문을 다시 확인하고 있습니다.");
  try{
    const data=await api("/api/state?"+query(context));
    if(turn!==ui.seq)return;
    render(data);
    if(announce)message(data.current_revision+" 적용 · "+context.role+" · "+context.as_of);
  }catch(error){
    if(turn!==ui.seq)return;
    $("current-revision").textContent="조회 불가";
    $("upcoming-revision").textContent="—";
    $("coverage-state").textContent="미확인";
    message("조회 범위 오류: "+error.message+". 이전 화면의 원문·확인 버튼을 비웠습니다.");
  }
}
for(const id of ["as-of","role","site"])$(id).addEventListener("change",()=>load());
load();
