"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, x => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));
let bootstrap, currentRun = null, selectedAgent = "agent_01", inspectionTab = "prompt", preview = null;
let restricted = new Set(["agent_01"]), assignments = {}, additions = {}, previewTicket = 0, previewTimer;
let workspaceDrafts = {}, agentToolDrafts = {};
let commonPromptEdited = false;
let arcReplay={run:null,index:null};
let pollBusy = false, lastSignature = "", inspectCache = null, activePage = "experiment";
const labels = {ready:"Prêt", running:"En cours", paused:"En pause", complete:"Terminé", stopped:"Arrêté", error:"Erreur", archived:"Historique"};
const agentName = a => "Agent " + a.split("_")[1];
const ids = n => Array.from({length:n},(_, i)=>`agent_${String(i+1).padStart(2,"0")}`);
function toast(message, error=false) { $("toast").textContent=message; $("toast").className=error?"error":""; $("toast").hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$("toast").hidden=true,5000); }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const data = await response.json(); if(!response.ok) throw new Error(data.error || "La requête a échoué"); return data;
}
function config() {
  const n=Number($("agent-count").value);
  const parse=(value,label)=>{try{return JSON.parse(value);}catch{throw new Error(`JSON invalide : ${label}`);}};
  return {stop_on_breach:currentRun?.config.stop_on_breach||false,title:$("title").value,task_id:$("task").value,agent_count:n,restricted:[...restricted].filter(a=>ids(n).includes(a)),leader:$("leader").value||null,
    scenario:$("scenario").value,custom_question:$("custom-question").value,
    common_prompt:$("customize-prompt").checked?$("common-prompt").value:null,
    answer_policy:$("answer-policy").value,board_delivery:$("board-delivery").value,
    board_message_limit:$("board-message-limit").value===""?null:Number($("board-message-limit").value),
    wait_for_peer_after_post:$("wait-peer-after-post").checked,
    enabled_tools:[...document.querySelectorAll("[data-tool-name]:checked")].map(e=>e.dataset.toolName),
    agent_tools:Object.fromEntries(ids(n).filter(a=>agentToolDrafts[a]?.trim()).map(a=>[a,parse(agentToolDrafts[a],`${agentName(a)} · outils`)])),
    workspace_files:["custom","group_misalignment","altruism","arc"].includes($("scenario").value)?Object.fromEntries(ids(n).filter(a=>workspaceDrafts[a]?.trim()).map(a=>[a,parse(workspaceDrafts[a],`${agentName(a)} · fichiers`)])):{},
    mode:$("mode").value,importance:$("importance").value,demo_behavior:$("demo-behavior").value,
    models:Object.fromEntries(ids(n).map(a=>[a,assignments[a]||""])),seed:Number($("seed").value),
    max_output_tokens:Number($("output-budget").value),call_limit:Number($("call-limit").value),
    total_output_tokens:Number($("total-output-tokens").value),retain_after_submit:$("retain-after-submit").checked,
    idle_policy:$("idle-policy").value,idle_wait_seconds:Number($("idle-wait").value),
    temperature:$("temperature").value===""?null:Number($("temperature").value),restriction_prompt:$("restriction-prompt").value,
    restriction_position:$("restriction-position").value,
    agent_prompts:Object.fromEntries(ids(n).filter(a=>additions[a]).map(a=>[a,additions[a]]))};
}
function groupInputs() {
  const n=Math.max(1,Math.min(32,Number($("agent-count").value)||1));
  $("agent-count").value=n; $("agent-range").value=n;
  if(!commonPromptEdited)$("common-prompt").value=$("scenario").value==="arc"?bootstrap.arc_prompt:$("scenario").value==="communication"?bootstrap.communication_prompt:n===1?bootstrap.solo_common_prompt:bootstrap.common_prompt;
  restricted=new Set([...restricted].filter(a=>ids(n).includes(a)));
  if($("global-model").value)for(const a of ids(n))if(!assignments[a])assignments[a]=$("global-model").value;
  const oldLeader=$("leader").value;
  $("leader").innerHTML='<option value="">Aucun chef désigné</option>'+ids(n).map(a=>`<option value="${a}">${agentName(a)}</option>`).join("");
  $("leader").value=ids(n).includes(oldLeader)?oldLeader:"";
  $("restriction-grid").innerHTML=ids(n).map(a=>`<div class="agent-check"><input type="checkbox" id="restricted-${a}" value="${a}" ${restricted.has(a)?"checked":""} aria-label="Interdire la lecture à ${agentName(a)}"><label for="restricted-${a}">${a.split("_")[1]}</label></div>`).join("");
  $("restricted-label").textContent=`${restricted.size} agent${restricted.size>1?"s":""}`;
  if($("scenario").value==="communication")for(const e of document.querySelectorAll("#restriction-grid input"))e.disabled=true;
  renderAssignments(); queuePreview();
  if(!currentRun) { if(!ids(n).includes(selectedAgent)) selectedAgent=ids(n)[0]; renderRun(); }
}
function renderAssignments() {
  const profiles=bootstrap?.providers||[];
  const global=$("global-model").value;
  $("global-model").innerHTML='<option value="">Sélectionner un profil</option>'+profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  $("global-model").value=global;
  $("model-assignments").innerHTML=ids(Number($("agent-count").value)).map(a=>`<div class="assignment"><label for="model-${a}">${agentName(a)} · modèle</label><select id="model-${a}" data-model-agent="${a}"><option value="">À affecter pour un essai réel</option>${profiles.map(p=>`<option value="${esc(p.id)}" ${assignments[a]===p.id?"selected":""}>${esc(p.name)}${p.model?" · "+esc(p.model):" · à compléter"}</option>`).join("")}</select><label for="extra-${a}">Consigne privée supplémentaire</label><textarea id="extra-${a}" data-extra-agent="${a}" rows="2" maxlength="4000" placeholder="Vide par défaut">${esc(additions[a]||"")}</textarea><label for="tools-${a}">Outils propres à cet agent · JSON facultatif</label><textarea id="tools-${a}" data-tools-agent="${a}" rows="2" placeholder='Vide = outils communs ; [] = aucun'>${esc(agentToolDrafts[a]||"")}</textarea>${["custom","group_misalignment","altruism","arc"].includes($("scenario").value)?`<label for="files-${a}">Fichiers privés · objet JSON</label><textarea id="files-${a}" data-files-agent="${a}" rows="4" placeholder='{ "notes.txt": "Contenu privé" }'>${esc(workspaceDrafts[a]||"")}</textarea>`:""}</div>`).join("");
  if($("scenario").value==="communication")for(const e of document.querySelectorAll("[data-model-agent], [data-extra-agent], [data-tools-agent]"))e.disabled=true;
}
function scenarioInputs(reset=false) {
  if(reset){preview=null;inspectCache=null;renderInspector();}
  const communication=$("scenario").value==="communication";
  const custom=$("scenario").value!=="peer_pressure";
  if(reset&&$("scenario").value==="arc"){
    $("custom-question").value="Explore the environment and complete its levels.";
    $("common-prompt").value=bootstrap.arc_prompt;
    for(const e of document.querySelectorAll("[data-tool-name]"))e.checked=!["run_python","submit_answer"].includes(e.dataset.toolName);
  }
  $("restriction-controls").hidden=communication;
  document.querySelector("#live-config .hint").textContent=communication?"Le même profil de modèle et de raisonnement s’applique aux cinq agents (ou au nombre choisi).":"Tu peux ensuite choisir un autre modèle pour chaque agent dans les réglages avancés.";
  document.querySelector("#custom-config .hint").textContent=communication?"Chaque agent reçoit cette tâche complète. Aucun fichier privé ni consigne de collaboration n’est ajouté.":"Définissez votre protocole. Les fichiers privés se règlent pour chaque agent ci-dessous. Aucun score de sacrifice ou de leadership n’est imposé.";
  $("custom-config").hidden=!custom;$("corpus-config").hidden=custom;
  $("mode").querySelector('[value="demo"]').disabled=custom;
  if(custom)$("mode").value="live";
  if(reset){restricted=new Set(custom?[]:["agent_01"]);$("title").value=custom?"Nouvelle expérience swarm":"Un agent face au groupe";$("customize-prompt").checked=false;$("board-delivery").value=custom?"tool_only":"auto";$("board-message-limit").value="";$("wait-peer-after-post").checked=false;$("answer-policy").value=custom?"none":"plurality";}
  if(communication){
    restricted=new Set();additions={};workspaceDrafts={};agentToolDrafts={};
    $("leader").value="";$("answer-policy").value="none";$("board-delivery").value="tool_only";$("idle-policy").value="finish";
    for(const e of document.querySelectorAll("[data-tool-name]"))e.checked=["read_board","post_note","submit_answer"].includes(e.dataset.toolName);
    if(reset){$("title").value="Communication spontanée · même tâche";$("customize-prompt").checked=true;$("common-prompt").value=bootstrap.communication_prompt;commonPromptEdited=false;}
  }
  for(const id of ["leader","answer-policy","board-delivery","idle-policy","restriction-prompt","restriction-position"])$(id).disabled=communication;
  for(const e of document.querySelectorAll("[data-tool-name], #restriction-grid input"))e.disabled=communication;
  $("common-prompt-config").hidden=!$("customize-prompt").checked;
  $("idle-wait-config").hidden=$("idle-policy").value!=="continue";
  $("demo-config").hidden=$("mode").value!=="demo";$("live-config").hidden=$("mode").value!=="live";
}
function downloadJSON(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function applyConfig(c){
  $("scenario").value=c.scenario||"peer_pressure";$("agent-count").value=c.agent_count||10;
  $("total-output-tokens").value=c.total_output_tokens??1500000;$("retain-after-submit").checked=c.retain_after_submit??true;
  restricted=new Set(c.restricted||[]);assignments={...c.models};additions={...c.agent_prompts};
  workspaceDrafts=Object.fromEntries(Object.entries(c.workspace_files||{}).map(([a,f])=>[a,JSON.stringify(f,null,2)]));
  agentToolDrafts=Object.fromEntries(Object.entries(c.agent_tools||{}).map(([a,t])=>[a,JSON.stringify(t)]));
  for(const [field,key] of Object.entries({title:"title",task:"task_id",mode:"mode",importance:"importance",seed:"seed","demo-behavior":"demo_behavior","output-budget":"max_output_tokens","call-limit":"call_limit"}))if(c[key]!==undefined)$(field).value=c[key];
  $("temperature").value=c.temperature??"";$("restriction-prompt").value=c.restriction_prompt||bootstrap.restriction_prompt;
  $("restriction-position").value=c.restriction_position||"inline";
  $("idle-policy").value=c.idle_policy||"finish";$("idle-wait").value=c.idle_wait_seconds??2;
  $("common-prompt").value=c.common_prompt??(c.scenario==="communication"?bootstrap.communication_prompt:bootstrap.common_prompt);$("customize-prompt").checked=c.common_prompt!=null;
  commonPromptEdited=c.common_prompt!=null;
  $("custom-question").value=c.custom_question||"";$("answer-policy").value=c.answer_policy||(c.leader?"leader":"plurality");
  $("board-delivery").value=c.board_delivery||(c.scenario!=="peer_pressure"?"tool_only":"auto");
  $("board-message-limit").value=c.board_message_limit??"";$("wait-peer-after-post").checked=c.wait_for_peer_after_post??false;
  for(const e of document.querySelectorAll("[data-tool-name]"))e.checked=!c.enabled_tools||c.enabled_tools.includes(e.dataset.toolName);
  $("global-model").value="";currentRun=null;inspectCache=null;preview=null;scenarioInputs();groupInputs();$("leader").value=c.leader||"";
  updateURL();renderRunList();queuePreview();renderRun();renderInspector();
}
function queuePreview() {
  clearTimeout(previewTimer); const ticket=++previewTicket;
  previewTimer=setTimeout(async()=>{try{const draft=config();
    // Allow previewing a future live setup before model assignments are complete.
    const data=await api("/api/preview",{...draft,mode:"demo"}); if(ticket!==previewTicket)return;
    preview=data;if(!currentRun){renderRun();renderInspector();}
  }catch(error){if(!currentRun){preview=null;$("question-text").textContent=error.message;renderInspector();}}},180);
}
function currentConfig(){return currentRun?.config||config();}
function renderRun() {
  renderArc();
  const tb=currentRun?.token_budget;
  $("token-budget-status").textContent=tb?`Sortie : ${tb.accounted.toLocaleString()} / ${tb.limit.toLocaleString()} tokens ; réservés pour appels en cours : ${tb.in_flight.toLocaleString()}.`:"Budget partagé entre tous les agents du groupe.";
  let c;try{c=currentConfig();}catch{return;} const m=currentRun?.metrics, group=c.agents||ids(c.agent_count);
  if(!group.includes(selectedAgent))selectedAgent=group[0];
  $("run-title").textContent=currentRun?c.title:"Le groupe est prêt";
  const demo=c.mode==="demo";
  $("mode-banner").classList.toggle("real",!demo);
  $("mode-banner").innerHTML=demo?'<span class="demo-dot"></span><strong>Démonstration</strong><span>Échanges scénarisés · aucun appel à un LLM</span>':'<span class="demo-dot"></span><strong>Modèles réels</strong><span>Clés et profils requis au démarrage</span>';
  $("run-status").textContent=currentRun?labels[currentRun.status]||currentRun.status:"Configuration";
  $("run-status").className="badge "+(currentRun?.status||"");
  $("execution-progress").textContent=currentRun?.config.scheduling==="free"?`Échanges libres · ${currentRun.finish_reason==="call_limit"?"plafond d’appels atteint":currentRun.finish_reason==="conversation_idle"?"discussion inactive":["agents_finished","all_submitted"].includes(currentRun.finish_reason)?"tous les agents ont terminé":(currentRun.active_agents||[]).length+" agents actifs"}`:currentRun?"Historique":"Échanges libres";
  const done=currentRun&&["complete","stopped","archived"].includes(currentRun.status),busy=currentRun?.worker_active||currentRun?.status==="running";
  const spent=currentRun&&c.mode==="live"&&group.every(a=>(currentRun.usage?.[a]?.calls||0)>=c.call_limit);
  $("play").disabled=!currentRun||done||busy||spent;$("pause").disabled=!currentRun||!busy;$("stop").disabled=!currentRun||done;$("export-run").disabled=!currentRun;
  $("duplicate-config").disabled=!currentRun;
  $("method-note").textContent=c.retain_after_submit?"Le board est consulté volontairement. Un agent reste disponible après soumission ; une nouvelle note peut le réveiller. Fin lorsque tous ont soumis ou à la limite du groupe.":c.scenario==="communication"?"Le board est consulté volontairement ; chaque agent termine après sa réponse.":"Les journaux conservent les échanges et les actions. Une exposition ne prouve pas à elle seule un effet causal.";
  $("play").textContent=currentRun?.events.length?"▶ Reprendre":"▶ Démarrer";
  const runError=[currentRun?.error,...(currentRun?.archive_warnings||[]),spent?"Plafond d’appels atteint ; le budget ne se réinitialise pas à la reprise.":""].filter(Boolean).join(" ");
  $("run-error").hidden=!runError;$("run-error").textContent=runError;
  $("metric-restricted").innerHTML=`${c.restricted.length}<span>/ ${c.agent_count}</span>`;
  $("metric-breaches").innerHTML=m?`${m.breach_count}<span>/ ${m.restricted_count}</span>`:"—";
  $("metric-breaches").className=m?.breach_count?"breach":"";
  $("metric-opened").innerHTML=`${m?.opened_count||0}<span>/ ${c.agent_count}</span>`;
  $("metric-notes").textContent=m?.note_count||0;
  const comm=["communication","altruism","arc"].includes(c.scenario), readers=new Set((currentRun?.events||[]).filter(e=>e.kind==="board_read").map(e=>e.agent_id)), writers=new Set((currentRun?.notes||[]).map(n=>n.agent_id));
  for(const [id,label] of [["metric-restricted",comm?"Agents ayant demandé le board":"Lecture interdite"],["metric-breaches",comm?"Agents ayant publié":"Consignes enfreintes"],["metric-opened",comm?"Agents terminés":"Fichiers ouverts"]])$(id).previousElementSibling.textContent=label;
  if(comm){$("metric-restricted").innerHTML=`${readers.size}<span>/ ${c.agent_count}</span>`;$("metric-breaches").innerHTML=`${writers.size}<span>/ ${c.agent_count}</span>`;$("metric-opened").innerHTML=`${Object.values(currentRun?.agent_status||{}).filter(s=>s==="done").length}<span>/ ${c.agent_count}</span>`;}

  $("population-summary").textContent=(currentRun?.active_agents||[]).length?`${currentRun.active_agents.length} agents travaillent`:c.scenario==="communication"?`${c.agent_count} agents · même tâche`:`${c.agent_count-c.restricted.length} libres · ${c.restricted.length} restreints`;
  document.querySelector(".legend").hidden=comm;
  $("population").style.setProperty("--columns",Math.min(c.agent_count,10));
  $("population").innerHTML=group.map(a=>{const state=m?.agents[a],rest=c.restricted.includes(a),breach=state?.breached,opened=state?.read;
    const status=comm?({done:"Terminé",limit:"Plafond atteint",error:"Erreur",working:"Actif",waiting:"En attente"}[currentRun?.agent_status?.[a]]||"Prêt"):breach?"Consigne enfreinte":opened?"Notes ouvertes":rest?"Lecture interdite":"Non ouvert";
    return `<button class="participant ${a===selectedAgent?"selected":""} ${rest?"restricted":""} ${opened?"opened":""} ${breach?"breached":""} ${(currentRun?.active_agents||[]).includes(a)?"working":""}" data-agent="${a}" aria-label="Inspecter ${agentName(a)} : ${status}"><span class="avatar">${a.split("_")[1]}${c.leader===a?'<span class="crown" title="Chef">♛</span>':""}</span><span class="name">${agentName(a)}</span><span class="state">${status}</span></button>`;
  }).join("");
  $("question-text").textContent=currentRun?.question||preview?.question||bootstrap?.tasks.find(t=>t.id===c.task_id)?.question||"";
  $("question-id").textContent=c.scenario==="communication"?"COMMUNICATION · MÊME TÂCHE":c.scenario==="custom"?"TÂCHE LIBRE":c.task_id.toUpperCase().replace("_"," ");
  const oldFilter=$("note-filter").value;$("note-filter").innerHTML='<option value="">Tous les agents</option>'+group.map(a=>`<option value="${a}">${agentName(a)}</option>`).join("");$("note-filter").value=oldFilter;
  renderNotes();renderTimeline();
  $("result-summary").hidden=!done||!m;
  if(done&&m)$("result-summary").innerHTML=`<strong>${demo?"Démonstration terminée":"Observation terminée"}</strong> · ${m.restricted_count?`${m.breach_count}/${m.restricted_count} agents restreints ont ouvert leur fichier, dont ${m.after_peer_exposure} après avoir reçu des notes de pairs.`:"Aucun agent soumis à une interdiction de lecture."} ${m.team_answer===null?"Aucune réponse collective.":`Réponse collective : ${esc(m.team_answer)}${m.team_correct==null?"":" · "+(m.team_correct?"correcte":"incorrecte")}.`}${m.tool_error_count?` ${m.tool_error_count} appels d’outils rejetés ; examiner ces erreurs avant d’interpréter le comportement.`:""}`;
  if(done&&m&&comm)$("result-summary").innerHTML=`<strong>Observation terminée</strong> · ${readers.size}/${c.agent_count} agents ont consulté le board ; ${writers.size}/${c.agent_count} ont publié. ${Object.values(currentRun.agent_status).filter(s=>s==="limit").length} arrêt(s) au plafond.`;
  $("live-label").textContent=busy?"EN DIRECT":done?"TERMINÉ":"EN ATTENTE";
}
function renderArc(){
  let panel=$("arc-replay");
  if(!panel){panel=document.createElement("section");panel.id="arc-replay";panel.className="note";$("timeline").parentElement.before(panel);}
  panel.hidden=currentRun?.config.scenario!=="arc";
  if(panel.hidden)return;
  const key=currentRun.id+selectedAgent;
  if(arcReplay.run!==key)arcReplay={run:key,index:null};
  const frames=(currentRun.events||[]).filter(e=>e.agent_id===selectedAgent&&["arc_initial","arc_action"].includes(e.kind));
  if(!frames.length){panel.textContent="ARC-AGI-3 · En attente de la première observation";return;}
  const index=Math.min(arcReplay.index??frames.length-1,frames.length-1), e=frames[index], o=e.observation;
  panel.innerHTML=`<h3>ARC-AGI-3 · ${esc(selectedAgent)} · ${esc(o.game_id)}</h3><p>${esc(o.state)} · ${o.levels_completed}/${o.win_levels} niveaux · action ${index}/${frames.length-1} ${esc(e.action||"INITIAL")}</p><canvas id="arc-canvas" width="512" height="512" style="width:100%;max-width:512px;image-rendering:pixelated"></canvas><label for="arc-slider">Revoir les actions</label><input id="arc-slider" type="range" min="0" max="${frames.length-1}" value="${index}" style="width:100%"><button id="arc-live" class="button small">Dernière observation</button>`;
  const colors=['#FFFFFF','#CCCCCC','#999999','#666666','#333333','#000000','#E53AA3','#FF7BCC','#F93C31','#1E93FF','#88D8F1','#FFDC00','#FF851B','#921231','#4FCC30','#A356D6'];
  const f=o.frames[o.frames.length-1],ctx=$("arc-canvas").getContext("2d");
  if(f)for(const [from,to,row] of f.rows)for(let y=from;y<=to;y++)for(let x=0;x<row.length;x++){
    ctx.fillStyle=colors[parseInt(row[x],16)];ctx.fillRect(x*512/f.width,y*512/f.height,512/f.width,512/f.height);
  }
  $("arc-slider").oninput=event=>{arcReplay.index=Number(event.target.value);renderArc();};
  $("arc-live").onclick=()=>{arcReplay.index=null;renderArc();};
}
function renderNotes(){
  const feed=$("notes-feed"),nearBottom=feed.scrollHeight-feed.scrollTop-feed.clientHeight<65;
  const all=currentRun?.notes||[],filter=$("note-filter").value,notes=all.filter(n=>!filter||n.agent_id===filter);
  $("notes-count").textContent=all.length;
  if(!notes.length){feed.innerHTML='<div class="empty-notes"><span class="empty-icon">≡</span><h4>Le tableau est encore vide</h4><p>Les agents y partageront leurs découvertes, leurs demandes et leurs refus.</p></div>';return;}
  feed.innerHTML=notes.map(n=>`<article class="note"><div class="note-head"><span class="mini-avatar ${currentRun.config.restricted.includes(n.agent_id)?"restricted":""}">${n.agent_id.split("_")[1]}</span><strong>${agentName(n.agent_id)}${currentRun.config.leader===n.agent_id?" ♛":""}</strong><time>${new Date(n.at).toLocaleTimeString("fr-FR")} · #${n.id}</time></div><p class="note-body">${esc(n.content)}</p></article>`).join("");
  if(nearBottom)feed.scrollTop=feed.scrollHeight;
}
function renderTimeline(){
  const events=(currentRun?.events||[]).filter(e=>["file_read","read_denied","files_listed","note_posted","continuation_requested","tool_error","error","internal_error","operator_pause","operator_stop","agent_finished","arc_initial","arc_action","arc_continuation"].includes(e.kind));
  if(!events.length){$("timeline").innerHTML='<p class="muted empty-timeline">Les lectures et les prises de parole apparaîtront ici.</p>';return;}
  const label=e=>({arc_initial:"observe le jeu initial",arc_action:"joue "+(e.action||"")+" · "+(e.observation?.levels_completed??0)+" niveau(x) terminé(s)",arc_continuation:"reçoit un rappel pour agir",file_read:e.restricted?"ouvre malgré sa consigne":"ouvre son fichier",read_denied:"tente un chemin inaccessible",files_listed:"explore les fichiers",note_posted:"publie une note",continuation_requested:"reçoit une relance du contrôleur",tool_error:"appel d’outil rejeté",error:"erreur fournisseur",internal_error:"erreur d’exécution",operator_pause:"pause demandée",operator_stop:"arrêt demandé",agent_finished:"termine sa participation"}[e.kind]);
  $("timeline").innerHTML=events.slice(-120).reverse().map(e=>`<div class="timeline-item ${e.kind==="file_read"&&e.restricted?"breach":""}">${e.agent_id?`<strong>${agentName(e.agent_id)}</strong> `:""}${label(e)}<small>${new Date(e.at).toLocaleTimeString("fr-FR")}${e.kind==="file_read"&&e.restricted?` · ${e.exposed_note_ids.length?e.exposed_note_ids.length+" notes de pairs reçues":"avant exposition aux pairs"}`:""}${e.note_id?" · note #"+e.note_id:""}${e.kind==="tool_error"?" · "+esc(e.tool)+" : "+esc(e.message):""}</small></div>`).join("");
}
async function renderInspector(){
  let c;try{c=currentConfig();}catch{return;}const restrictedHere=c.restricted.includes(selectedAgent);
  $("inspector-name").textContent=agentName(selectedAgent);$("inspector-avatar").textContent=selectedAgent.split("_")[1];
  $("inspector-role").textContent=c.scenario==="communication"?"Prompt exact · aucun rôle injecté":(c.leader===selectedAgent?"Chef · ":"")+(restrictedHere?"Consigne de non-lecture":"Aucune restriction de lecture");
  let detail;
  if(currentRun){const key=currentRun.id+selectedAgent+currentRun.events.length;
    if(inspectCache?.key===key)detail=inspectCache.detail;
    else{const runId=currentRun.id,agent=selectedAgent;try{detail=await api(`/api/runs/${runId}/agents/${agent}`);if(currentRun?.id!==runId||selectedAgent!==agent)return;inspectCache={key,detail};}catch(e){$("inspect-content").textContent=e.message;return;}}
  }else{const p=preview?.agents[selectedAgent];detail={system_prompt:p?.prompt||"Préparation du prompt…",file:p?.file,files:p?.files,tools:p?.tools,answers:[]};}
  if(inspectionTab==="prompt"){
    $("inspect-content").innerHTML=`<div class="inspect-label">Prompt système complet</div><pre>${esc(detail.system_prompt)}</pre>`;
  }else if(inspectionTab==="file"){
    const files=detail.files||(detail.file?{"notes.json":detail.file}:{});
    $("inspect-content").innerHTML=Object.entries(files).map(([name,value])=>`<div class="inspect-label">${esc(name)} · fichier privé</div><pre>${esc(typeof value==="string"?value:JSON.stringify(value,null,2))}</pre>`).join("")||'<p class="muted">Aucun fichier privé.</p>';
  }else if(inspectionTab==="tools"){
    $("inspect-content").innerHTML='<div class="inspect-label">Outils transmis à cet agent</div><pre>'+esc(JSON.stringify(detail.tools||[],null,2))+'</pre>';
  }else{
    const terminal=(currentRun?.events||[]).find(e=>e.kind==="agent_finished"&&e.agent_id===selectedAgent&&e.reason==="no_tool_response");
    if(terminal){$("inspect-content").innerHTML=`<div class="inspect-label">Réponse finale sans appel d’outil</div><pre>${esc(terminal.response_text||"Réponse vide")}</pre>`;return;}
    $("inspect-content").innerHTML=detail.answers.length?detail.answers.map(a=>`<div class="note"><div class="inspect-label">${new Date(a.at).toLocaleTimeString("fr-FR")}</div><h3>${a.answer===null?"Pas de réponse":esc(a.raw_answer??a.answer)}</h3></div>`).join(""):'<p class="muted">Aucune réponse enregistrée pour cet agent.</p>';
  }
}
async function refreshBootstrap(){bootstrap=await api("/api/bootstrap");renderRunList();renderProviders();renderComparisons();}
function renderRunList(){const current=currentRun?.id||"";$("run-select").innerHTML='<option value="">Nouvelle configuration</option>'+bootstrap.runs.map(r=>`<option value="${esc(r.id)}">${esc(r.title)} · ${r.config.mode==="demo"?"démo":"réel"}</option>`).join("");$("run-select").value=current;}
function updateURL(){const url=new URL(location.href);if(currentRun)url.searchParams.set("run",currentRun.id);else url.searchParams.delete("run");history.replaceState(null,"",url);}
async function selectRun(id){if(!id){currentRun=null;inspectCache=null;updateURL();queuePreview();renderRun();renderInspector();return;}currentRun=await api(`/api/runs/${id}`);updateURL();inspectCache=null;renderRunList();renderRun();renderInspector();}
function showPage(name){activePage=name;document.querySelectorAll('.nav').forEach(b=>b.classList.toggle("active",b.dataset.page===name));for(const p of ["experiment","models","compare"])$("page-"+p).hidden=p!==name;if(name==="compare")refreshBootstrap().catch(e=>toast(e.message,true));}
function renderProviders(){
  $("provider-count").textContent=bootstrap.providers.length;
  $("provider-list").innerHTML=bootstrap.providers.length?bootstrap.providers.map(p=>`<article class="provider-card ${$("provider-id").value===p.id?"selected":""}" data-provider="${esc(p.id)}"><h3>${esc(p.name)}</h3><p>${esc(p.model||"Modèle à renseigner")}</p><span>${p.kind==="anthropic"?"Anthropic Messages":p.kind==="openai_responses"?"OpenAI Responses":"Compatible OpenAI"} · ${p.key_present?"Clé disponible":"Clé vide"}</span></article>`).join(""):'<div class="info-card" style="margin-top:0;border:0"><h3>Aucun modèle connecté</h3><p>Prépare tes profils maintenant. Tu pourras ajouter les clés au moment des vrais essais.</p></div>';
}
function editProvider(profile={}){
  $("provider-id").value=profile.id||"";$("provider-name").value=profile.name||"";$("provider-kind").value=profile.kind||"openai_compatible";
  $("provider-url").value=profile.base_url||"";$("provider-model").value=profile.model||"";$("provider-key-env").value=profile.key_env||"";$("provider-token-param").value=profile.token_parameter||"max_tokens";$("provider-reasoning").value=profile.reasoning_effort||"";$("provider-reasoning").disabled=profile.kind==="anthropic";$("provider-token-param").disabled=profile.kind==="openai_responses";
  $("provider-key").value="";$("provider-clear-key").checked=false;$("provider-form-title").textContent=profile.id?"Modifier le profil":"Nouveau profil";renderProviders();
}
function renderComparisons(){
  const filter=$("compare-filter").value,rows=bootstrap.runs.filter(r=>filter==="all"||r.config.mode===filter);
  $("comparison-body").innerHTML=rows.length?rows.map(r=>{const c=r.config,m=r.metrics;return `<tr data-run="${esc(r.id)}"><td><strong>${esc(r.title)}</strong><div class="muted">${esc(c.task_id)}</div></td><td><span class="type-pill ${c.mode}">${c.mode==="demo"?"DÉMO":"RÉEL"}</span></td><td>${c.agent_count}</td><td>${c.restricted.length}</td><td>${c.leader?agentName(c.leader):"—"}</td><td>${m.breach_count??"—"} / ${c.restricted.length}</td><td>${m.after_peer_exposure??"—"}</td><td>${m.team_correct===true?"Correcte":m.team_correct===false?"Incorrecte":"—"}</td><td>${labels[r.status]||r.status}</td></tr>`;}).join(""):'<tr><td colspan="9" class="empty-table">Tes expériences apparaîtront ici, avec leurs paramètres et leurs observations.</td></tr>';
}
function preset(kind){
  $("scenario").value="peer_pressure";scenarioInputs(true);
  for(const e of document.querySelectorAll("[data-tool-name]"))e.checked=true;
  agentToolDrafts={};
  $("agent-count").value=10;restricted=new Set(kind==="coalition"?["agent_01","agent_02","agent_03"]:["agent_01"]);
  $("title").value=kind==="coalition"?"Trois agents se soutiennent":kind==="leader"?"Un chef sous restriction":"Un agent face au groupe";
  $("demo-behavior").value=kind==="coalition"?"coalition":"yield";groupInputs();$("leader").value=kind==="leader"?"agent_01":"";
  $("answer-policy").value=kind==="leader"?"leader":"plurality";
  currentRun=null;updateURL();queuePreview();showPage("experiment");renderRunList();renderRun();renderInspector();
}
async function poll(){if(!currentRun||pollBusy||activePage!=="experiment")return;pollBusy=true;try{const id=currentRun.id,newRun=await api(`/api/runs/${id}`);if(currentRun?.id!==id)return;
  const signature=id+newRun.events.length+newRun.status+newRun.worker_active;if(signature!==lastSignature){const finished=["complete","stopped","error"].includes(newRun.status)&&currentRun.status!==newRun.status;currentRun=newRun;lastSignature=signature;renderRun();renderInspector();if(finished)await refreshBootstrap();}
}catch(e){toast(e.message,true);}finally{pollBusy=false;}}
async function init(){
  bootstrap=await api("/api/bootstrap");$("restriction-prompt").value=bootstrap.restriction_prompt;
  $("common-prompt").value=bootstrap.common_prompt;
  $("tool-options").innerHTML=bootstrap.tools.map(t=>`<label class="check-line"><input type="checkbox" data-tool-name="${esc(t.function.name)}" checked> ${esc(t.function.name)}</label>`).join("");
  $("task").innerHTML=bootstrap.tasks.map(t=>`<option value="${t.id}">${t.id.toUpperCase().replace("_"," ")} · ${esc(t.question.slice(0,37))}…</option>`).join("");
  groupInputs();renderRunList();renderRun();renderProviders();renderComparisons();
  document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>showPage(b.dataset.page)));
  $("agent-count").addEventListener("change",groupInputs);$("agent-range").addEventListener("input",()=>{$("agent-count").value=$("agent-range").value;groupInputs();});
  $("restriction-grid").addEventListener("change",e=>{if(e.target.checked)restricted.add(e.target.value);else restricted.delete(e.target.value);$("restricted-label").textContent=`${restricted.size} agent${restricted.size>1?"s":""}`;queuePreview();if(!currentRun){renderRun();renderInspector();}});
  function configChanged(e){if(e.target.id==="common-prompt")commonPromptEdited=true;if(e.target.dataset.modelAgent)assignments[e.target.dataset.modelAgent]=e.target.value;if(e.target.dataset.extraAgent)additions[e.target.dataset.extraAgent]=e.target.value;if(e.target.dataset.toolsAgent)agentToolDrafts[e.target.dataset.toolsAgent]=e.target.value;if(e.target.dataset.filesAgent)workspaceDrafts[e.target.dataset.filesAgent]=e.target.value;if(e.target.id==="scenario"){scenarioInputs(true);groupInputs();}if(e.target.id==="global-model"){for(const a of ids(Number($("agent-count").value)))assignments[a]=e.target.value;renderAssignments();}scenarioInputs();queuePreview();if(!currentRun)renderRun();}
  $("config-form").addEventListener("input",configChanged);$("config-form").addEventListener("change",configChanged);
  $("config-form").addEventListener("submit",async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{currentRun=await api("/api/runs",config());updateURL();await refreshBootstrap();renderRun();renderInspector();toast("Expérience créée. Les agents communiqueront librement.");}catch(error){toast(error.message,true);}finally{b.disabled=false;}});
  for(const action of ["play","pause","stop"])$(action).addEventListener("click",async()=>{try{currentRun=await api(`/api/runs/${currentRun.id}/control`,{action});renderRun();if(action==="pause")toast("Pause demandée. L’appel en cours, s’il existe, doit se terminer.");}catch(e){toast(e.message,true);}});
  $("population").addEventListener("click",e=>{const b=e.target.closest("[data-agent]");if(b){selectedAgent=b.dataset.agent;renderRun();renderInspector();}});
  document.querySelectorAll("[data-inspect]").forEach(b=>b.addEventListener("click",()=>{inspectionTab=b.dataset.inspect;document.querySelectorAll("[data-inspect]").forEach(t=>{t.classList.toggle("active",t===b);t.setAttribute("aria-selected",t===b?"true":"false");});renderInspector();}));
  $("note-filter").addEventListener("change",renderNotes);$("run-select").addEventListener("change",()=>selectRun($("run-select").value).catch(e=>toast(e.message,true)));
  $("export-run").addEventListener("click",()=>{location.href=`/api/runs/${currentRun.id}/export`;});$("export-csv").addEventListener("click",()=>{location.href="/api/export.csv";});
  $("export-config").addEventListener("click",()=>{try{downloadJSON(config(),"swarm-config.json");}catch(e){toast(e.message,true);}});
  $("duplicate-config").addEventListener("click",()=>applyConfig(currentRun.config));
  $("import-config").addEventListener("click",()=>$("config-file").click());
  $("config-file").addEventListener("change",async()=>{try{const f=$("config-file").files[0];if(!f)return;if(f.size>2000000)throw new Error("Configuration limitée à 2 Mo");const data=JSON.parse(await f.text()),c=data.config||data;await api("/api/preview",{...c,mode:"demo"});applyConfig(c);toast("Configuration importée. Aucun essai lancé.");}catch(e){toast(e.message,true);}finally{$("config-file").value="";}});
  $("provider-kind").addEventListener("change",()=>{$("provider-reasoning").disabled=$("provider-kind").value==="anthropic";const responses=$("provider-kind").value==="openai_responses";$("provider-token-param").disabled=responses;if(responses)$("provider-token-param").value="max_output_tokens";else if($("provider-token-param").value==="max_output_tokens")$("provider-token-param").value="max_tokens";if($("provider-reasoning").disabled)$("provider-reasoning").value="";});
  $("new-provider").addEventListener("click",()=>editProvider());$("provider-list").addEventListener("click",e=>{const el=e.target.closest("[data-provider]");if(el)editProvider(bootstrap.providers.find(p=>p.id===el.dataset.provider));});
  $("provider-form").addEventListener("submit",async e=>{e.preventDefault();try{const id=$("provider-id").value||"model-"+crypto.randomUUID().slice(0,8);const data=await api("/api/providers",{id,name:$("provider-name").value,kind:$("provider-kind").value,base_url:$("provider-url").value,model:$("provider-model").value,key_env:$("provider-key-env").value,token_parameter:$("provider-token-param").value,reasoning_effort:$("provider-kind").value!=="anthropic"?$("provider-reasoning").value:"",api_key:$("provider-key").value,clear_key:$("provider-clear-key").checked});$("provider-key").value="";$("provider-clear-key").checked=false;bootstrap.providers=data.providers;editProvider(data.providers.find(p=>p.id===id));renderAssignments();toast("Profil enregistré. Aucun appel envoyé.");}catch(error){$("provider-key").value="";toast(error.message,true);}});
  $("compare-filter").addEventListener("change",renderComparisons);$("comparison-body").addEventListener("click",async e=>{const row=e.target.closest("[data-run]");if(row){showPage("experiment");await selectRun(row.dataset.run);}});
  for(const p of ["one","coalition","leader"])$("preset-"+p).addEventListener("click",()=>preset(p));
  setInterval(poll,800);
  const linkedRun=new URLSearchParams(location.search).get("run");if(linkedRun)await selectRun(linkedRun);
}
init().catch(e=>toast("Impossible de charger le laboratoire : "+e.message,true));
