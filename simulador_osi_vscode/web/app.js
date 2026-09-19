const $ = (id) => document.getElementById(id);

const state = {
  topology: null,
  scenarios: [],
  defaults: {},
  result: null,
  index: -1,
  timer: null,
  lastLogical: null,
  lastPhysical: null,
};

const OSI_LAYERS = [
  [7, 'Aplicação'], [6, 'Apresentação'], [5, 'Sessão'], [4, 'Transporte'],
  [3, 'Rede'], [2, 'Enlace'], [1, 'Física']
];
const TCPIP_LAYERS = [
  [[7,6,5], 'Aplicação'], [[4], 'Transporte'], [[3], 'Internet'], [[2], 'Enlace'], [[1], 'Física']
];

async function api(url, options={}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.erro || `Erro HTTP ${response.status}`);
  return data;
}

function showError(message) {
  const box = $('errorBox');
  box.textContent = message;
  box.classList.remove('hidden');
}
function clearError() { $('errorBox').classList.add('hidden'); }

function bytesOf(text) { return new TextEncoder().encode(text || '').length; }
function pct(v) { return `${(v * 100).toFixed(1).replace('.', ',')}%`; }

function pairKey(a,b) { return [a,b].sort().join('::'); }
function edgeId(a,b) { return `edge-${pairKey(a,b).replaceAll(':','-')}`; }

function svgEl(tag, attrs={}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

function deviceCenter(name) {
  const p = state.topology.dispositivos[name].posicao;
  return {x:p[0], y:p[1]};
}

function renderMap() {
  const svg = $('networkMap');
  svg.innerHTML = '';
  if (!state.topology) return;

  // Labels das três redes locais.
  const labels = [
    {text:'Rede A  10.0.1.0/24', x:38, y:42},
    {text:'Rede B  10.0.2.0/24', x:430, y:370},
    {text:'Rede C  10.0.3.0/24', x:815, y:42},
  ];
  labels.forEach(l => {
    const t = svgEl('text',{x:l.x,y:l.y,class:'network-label'}); t.textContent=l.text; svg.appendChild(t);
  });

  for (const e of state.topology.enlaces) {
    const a = deviceCenter(e.a), b = deviceCenter(e.b);
    const line = svgEl('line', {
      x1:a.x, y1:a.y, x2:b.x, y2:b.y,
      class:'net-edge', id:edgeId(e.a,e.b),
      'data-a':e.a, 'data-b':e.b
    });
    svg.appendChild(line);
    if (e.tipo === 'wan') {
      const tx = (a.x+b.x)/2, ty=(a.y+b.y)/2 - 8;
      const t=svgEl('text',{x:tx,y:ty,class:'net-edge-label','text-anchor':'middle'});
      t.textContent=`custo ${e.custo} · ${e.ia}/${e.ib}`; svg.appendChild(t);
    }
  }

  for (const [name, dev] of Object.entries(state.topology.dispositivos)) {
    const {x,y}=deviceCenter(name);
    const interfaces=Object.entries(dev.interfaces);
    const h=58 + interfaces.length*11;
    const g=svgEl('g',{class:`device ${dev.tipo}`,id:`device-${name}`});
    g.appendChild(svgEl('rect',{x:x-64,y:y-h/2,width:128,height:h}));
    const nameText=svgEl('text',{x,y:y-h/2+19,class:'name'}); nameText.textContent=name; g.appendChild(nameText);
    const type=svgEl('text',{x,y:y-h/2+34,class:'meta'}); type.textContent=dev.tipo==='host'?'computador':'roteador'; g.appendChild(type);
    let yy=y-h/2+48;
    for (const [iname,i] of interfaces) {
      const t=svgEl('text',{x,y:yy,class:'iface'}); t.textContent=`${iname}: ${i.ip}`; g.appendChild(t); yy+=11;
    }
    svg.appendChild(g);
  }
  applyMapState();
}

function clearSyntheticLink() {
  const s=$('synthetic-active-link'); if(s) s.remove();
}

function applyMapState(event=null) {
  if (!state.topology) return;
  document.querySelectorAll('.net-edge').forEach(e=>e.classList.remove('active','down','path'));
  document.querySelectorAll('.device').forEach(e=>e.classList.remove('active'));
  clearSyntheticLink();

  if (state.result?.cenario==='C4') {
    const down=$(edgeId('R1','R4')); if(down) down.classList.add('down');
  }

  const paths = state.result?.caminhos ? Object.values(state.result.caminhos) : (state.result?.caminho ? [state.result.caminho] : []);
  for (const path of paths) {
    for(let i=0;i<path.length-1;i++) {
      const edge=$(edgeId(path[i],path[i+1]));
      if(edge && !edge.classList.contains('down')) edge.classList.add('path');
    }
  }
  if (!event) return;
  const dg=$(`device-${event.dispositivo}`); if(dg) dg.classList.add('active');
  if(event.enlace && event.enlace.length===2) {
    const [a,b]=event.enlace;
    const edge=$(edgeId(a,b));
    if(edge) edge.classList.add('active');
    else {
      const ca=deviceCenter(a), cb=deviceCenter(b);
      const line=svgEl('line',{x1:ca.x,y1:ca.y,x2:cb.x,y2:cb.y,class:'net-edge active',id:'synthetic-active-link'});
      $('networkMap').insertBefore(line,$('networkMap').firstChild);
    }
  }
}

function involvedDevices() {
  if(!state.result) return [];
  if(state.result.caminhos) {
    const all=[]; Object.values(state.result.caminhos).forEach(p=>p.forEach(d=>{if(!all.includes(d)) all.push(d)})); return all;
  }
  return state.result.caminho || [];
}

function renderStacks(activeEvent=null) {
  const container=$('stacks'); container.innerHTML='';
  const mode=$('stackMode').value;
  for(const name of involvedDevices()) {
    const dev=state.topology.dispositivos[name];
    const card=document.createElement('div'); card.className='stack-card';
    const h=document.createElement('h3');
    h.innerHTML=`<span>${name}</span><small>${dev.tipo==='host'?'7 camadas':'3 camadas'}</small>`; card.appendChild(h);
    if(mode==='osi') {
      const layers=dev.tipo==='host'?OSI_LAYERS:OSI_LAYERS.filter(([n])=>n<=3);
      for(const [n,label] of layers) {
        const d=document.createElement('div'); d.className='layer'; d.textContent=`${n} ${label}`;
        if(activeEvent && activeEvent.dispositivo===name && activeEvent.camada===n) {
          d.classList.add('active'); if(n===3 && dev.tipo==='router') d.classList.add('route-active');
        }
        card.appendChild(d);
      }
    } else {
      const groups=dev.tipo==='host'?TCPIP_LAYERS:TCPIP_LAYERS.filter(([nums])=>nums.some(n=>n<=3) && !nums.some(n=>n>3));
      for(const [nums,label] of groups) {
        const d=document.createElement('div'); d.className='layer'; d.textContent=label;
        if(activeEvent && activeEvent.dispositivo===name && nums.includes(activeEvent.camada)) {
          d.classList.add('active'); if(activeEvent.camada===3 && dev.tipo==='router') d.classList.add('route-active');
        }
        card.appendChild(d);
      }
    }
    container.appendChild(card);
  }
}

function renderPdu(event) {
  const c=$('pduBlocks'); c.innerHTML=''; c.classList.remove('empty-state');
  if(!event || !event.blocos?.length) {
    c.classList.add('empty-state'); c.textContent='Nenhuma unidade de dados desenhada neste passo.'; return;
  }
  for(const block of event.blocos) {
    const d=document.createElement('div');
    d.className=`pdu-block ${block.kind || ''}`;
    d.innerHTML=`<span>${block.label}</span><small>${block.bytes} B</small>`;
    c.appendChild(d);
  }
}

function renderEvent(event) {
  if(!event) return;
  if(event.logicos) state.lastLogical=event.logicos;
  if(event.fisicos) state.lastPhysical=event.fisicos;
  $('currentStep').textContent=`Passo ${event.passo}/${state.result.eventos.length}`;
  $('pduName').textContent=`${event.unidade} - ${event.tamanho} B - ${event.dispositivo}/L${event.camada}`;
  renderPdu(event);
  $('logicalPair').textContent=state.lastLogical?`${state.lastLogical.origem} → ${state.lastLogical.destino}`:'-';
  $('physicalPair').textContent=state.lastPhysical?`${state.lastPhysical.origem} → ${state.lastPhysical.destino}`:'-';
  $('eventDetail').innerHTML=`<strong>${event.dispositivo} · L${event.camada} · ${event.acao}</strong><br>${event.descricao}${event.quadro?` · ${event.quadro}`:''}${event.pacote?` · ${event.pacote}`:''}`;
  $('logArea').textContent=state.result.eventos.slice(0,state.index+1).map(e=>e.linha).join('\n');
  $('logArea').scrollTop=$('logArea').scrollHeight;
  renderStacks(event);
  applyMapState(event);
}

function renderSummary() {
  const r=state.result; if(!r) return;
  $('metricUseful').textContent=`${r.dados_uteis} B`;
  $('metricTx').textContent=`${r.total_transmitido} B`;
  $('metricEfficiency').textContent=pct(r.eficiencia);
  $('metricOverhead').textContent=pct(r.overhead);
  $('c1Tx').textContent=`${r.comparacao.C1.transmitido} B`;
  $('c1Eff').textContent=pct(r.comparacao.C1.eficiencia);
  $('c2Tx').textContent=`${r.comparacao.C2.transmitido} B`;
  $('c2Eff').textContent=pct(r.comparacao.C2.eficiencia);
  let note=r.observacao || '';
  if(r.segmentos) note += `${note?' ':''}Cargas dos segmentos: ${r.segmentos.join(', ')} B.`;
  note += ` Entrega final: ${r.entregue?'concluída':'não concluída'}.`;
  $('resultNote').textContent=note;
}

function renderRouting() {
  const c=$('routingTables'); c.innerHTML='';
  if(!state.result?.tabelas_encaminhamento) return;
  for(const [router, rows] of Object.entries(state.result.tabelas_encaminhamento)) {
    const card=document.createElement('div'); card.className='routing-card';
    card.innerHTML=`<h3>${router}</h3><table><thead><tr><th>Rede</th><th>Via</th><th>Custo</th><th>Int.</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.rede}</td><td>${r.via}</td><td>${r.custo}</td><td>${r.interface}</td></tr>`).join('')}</tbody></table>`;
    c.appendChild(card);
  }
}

function resetReplay() {
  pause(); state.index=-1; state.lastLogical=null; state.lastPhysical=null;
  $('currentStep').textContent=`Passo 0/${state.result?.eventos?.length || 0}`;
  $('pduName').textContent='Cenário carregado. Pressione Passo ou Executar.';
  $('pduBlocks').innerHTML='Carregue um cenário e avance os passos.'; $('pduBlocks').classList.add('empty-state');
  $('logicalPair').textContent='-'; $('physicalPair').textContent='-'; $('eventDetail').textContent='-'; $('logArea').textContent='';
  renderStacks(); applyMapState();
}

function step() {
  if(!state.result) return;
  pause();
  if(state.index < state.result.eventos.length-1) {
    state.index++; renderEvent(state.result.eventos[state.index]);
  }
}
function play() {
  if(!state.result || state.index>=state.result.eventos.length-1) return;
  pause();
  const tick=()=>{
    if(state.index>=state.result.eventos.length-1) { state.timer=null; return; }
    state.index++; renderEvent(state.result.eventos[state.index]);
    state.timer=setTimeout(tick,Number($('speed').value));
  }; tick();
}
function pause() { if(state.timer){clearTimeout(state.timer);state.timer=null;} }

async function loadScenario() {
  clearError(); pause();
  const c=$('scenario').value;
  const opcoes={mensagem:$('message').value};
  if(c==='C5') opcoes.destino_ip='10.0.9.10';
  try {
    $('loadBtn').disabled=true; $('loadBtn').textContent='Carregando...';
    state.topology=await api('/api/topology');
    state.result=await api('/api/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cenario:c,opcoes})});
    renderMap();
    const paths=state.result.caminhos?Object.values(state.result.caminhos):[state.result.caminho];
    $('pathSummary').textContent=`Caminho: ${paths.filter(Boolean).map(p=>p.join(' → ')).join(' | ')}`;
    renderSummary(); renderRouting(); resetReplay();
  } catch(e) { showError(e.message); }
  finally { $('loadBtn').disabled=false; $('loadBtn').textContent='Carregar cenário'; }
}

function scenarioChanged() {
  const c=$('scenario').value;
  const sc=state.scenarios.find(x=>x.id===c); if(!sc) return;
  $('scenarioTitle').textContent=sc.nome; $('scenarioDescription').textContent=sc.descricao;
  if(c==='C7') $('message').value=state.defaults.mensagem_100;
  else if(c==='C3') $('message').value='Dois fluxos independentes com portas de origem distintas';
  else $('message').value=state.defaults.mensagem_42;
  const hints={C1:'1 quadro',C2:'4 quadros · 11,4%',C3:'2 fluxos',C4:'rota por R2',C5:'sem rota',C6:'erro em R4-R3',C7:'40 + 40 + 24 B'};
  $('scenarioHint').textContent=hints[c] || '';
  const endpoints={
    C1:['H1','navegador / 5210','H2','navegador2 / 5211'],
    C2:['H1','navegador / 5210','H4','servidorWeb / 443'],
    C3:['H1 + H2','5210 + 5310','H4','servidorWeb / 443'],
    C4:['H1','navegador / 5210','H4','servidorWeb / 443'],
    C5:['H1','navegador / 5210','10.0.9.10','servidorWeb / 443'],
    C6:['H1','navegador / 5210','H4','servidorWeb / 443'],
    C7:['H1','navegador / 5210','H4','servidorWeb / 443']
  };
  const ep=endpoints[c] || ['-','-','-','-'];
  $('originValue').textContent=ep[0]; $('sourceProcessValue').textContent=ep[1];
  $('destinationValue').textContent=ep[2]; $('destinationProcessValue').textContent=ep[3];
  $('messageBytes').textContent=`${bytesOf($('message').value)} B úteis`;
}

function saveLog() {
  if(!state.result) return;
  const text=state.result.eventos.map(e=>e.linha).join('\r\n')+`\r\n\r\nDados úteis: ${state.result.dados_uteis} B\r\nTransmitidos: ${state.result.total_transmitido} B\r\nEficiência: ${pct(state.result.eficiencia)}\r\nSobrecarga: ${pct(state.result.overhead)}\r\n`;
  const blob=new Blob([text],{type:'text/plain;charset=utf-8'}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=`registro_${state.result.cenario}.txt`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function shutdown() {
  if(!confirm('Encerrar o servidor local do Simulador OSI?')) return;
  try { await api('/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); } catch(_) {}
  $('serverStatus').textContent='servidor encerrado'; $('serverStatus').classList.remove('ok');
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
}

async function init() {
  try {
    const [topology,sc]=await Promise.all([api('/api/topology'),api('/api/scenarios')]);
    state.topology=topology; state.scenarios=sc.cenarios; state.defaults=sc;
    for(const s of state.scenarios) { const o=document.createElement('option'); o.value=s.id; o.textContent=s.nome; $('scenario').appendChild(o); }
    $('scenario').value='C2'; scenarioChanged(); renderMap();
    $('message').addEventListener('input',()=>{$('messageBytes').textContent=`${bytesOf($('message').value)} B úteis`;});
    $('scenario').addEventListener('change',scenarioChanged);
    $('stackMode').addEventListener('change',()=>renderStacks(state.index>=0?state.result.eventos[state.index]:null));
    $('loadBtn').addEventListener('click',loadScenario); $('stepBtn').addEventListener('click',step); $('playBtn').addEventListener('click',play); $('pauseBtn').addEventListener('click',pause);
    $('resetBtn').addEventListener('click',resetReplay); $('saveLogBtn').addEventListener('click',saveLog); $('shutdownBtn').addEventListener('click',shutdown);
    const shortcut=async (c)=>{ $('scenario').value=c; scenarioChanged(); await loadScenario(); };
    $('failLinkBtn').addEventListener('click',()=>shortcut('C4'));
    $('bitErrorBtn').addEventListener('click',()=>shortcut('C6'));
    $('unreachableBtn').addEventListener('click',()=>shortcut('C5'));
    await loadScenario();
  } catch(e) { showError(e.message); $('serverStatus').textContent='erro de inicialização'; $('serverStatus').classList.remove('ok'); }
}

init();
