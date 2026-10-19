#!/usr/bin/env python3
"""
spa_html.py — Paso 5: genera propuesta_montaje.html, la propuesta de montaje revisable en el navegador.

Mismo patrón que el informe de verificación de AutoSync: la herramienta propone, tú revisas en el
HTML (marcar/quitar planos, cambiar la toma, la etapa, el orden, desde qué segundo y cuántos beats),
tus decisiones se guardan en el navegador y se exportan a un JSON que `spa_aplicar.py` convierte
en vídeo borrador + XML para Premiere.

    python spa_html.py                 # -> propuesta_montaje.html (usa los vídeos locales)
    python spa_html.py --estatico docs # -> docs/index.html + docs/img (solo miniaturas, sin vídeos)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import BASE, CACHE, load_json  # noqa: E402
HERE = BASE   # las rutas relativas del HTML (tomas/, cache/frames/, salida/) cuelgan de la carpeta del proyecto

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TEMPLATE = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITULO__</title>
<style>
:root{color-scheme:light dark;--bg:#f4f6f9;--fg:#1b2430;--mut:#5b6877;--card:#fff;--line:#d8dee6;--acc:#2563eb;--on:#eaf2ff;--ok:#16a34a;--warn:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#0e1218;--fg:#e7ebf0;--mut:#98a4b1;--card:#161b23;--line:#29303b;--acc:#6ea4ff;--on:#142540;--ok:#4ade80;--warn:#fbbf24}}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:12px 20px}
h1{margin:0;font-size:19px}h2{margin:0;font-size:16px}h3{margin:0;font-size:14px}
.sub{color:var(--mut);margin:2px 0 8px}
.kpis{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
.kpi{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:3px 10px;font-size:13px}
.kpi b{font-variant-numeric:tabular-nums}
.kpi.warn{border-color:var(--warn);color:var(--warn)}
#timeline{display:flex;height:26px;border-radius:6px;overflow:hidden;border:1px solid var(--line);margin:8px 0;background:var(--bg)}
#timeline .seg{height:100%;border-right:1px solid rgba(255,255,255,.55);cursor:pointer;min-width:2px}
#timeline .seg:hover{filter:brightness(1.15)}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.btn{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:6px 12px;font:inherit;cursor:pointer}
.btn:hover{border-color:var(--acc)}.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
.btn.small{padding:2px 8px;font-size:12px}
.btn:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.toolbar label{display:inline-flex;gap:4px;align-items:center;color:var(--mut)}
#estado{color:var(--mut);font-size:12px;margin-left:auto}
main{max-width:1250px;margin:0 auto;padding:16px 20px 60px}
details.ayuda{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;margin-bottom:14px}
details.ayuda summary{cursor:pointer;font-weight:600}
code{background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:12.5px}
#borrador{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:16px;display:flex;gap:16px;flex-wrap:wrap}
#borrador video{width:420px;max-width:100%;border-radius:8px;background:#000}
#borrador .txt{flex:1;min-width:240px}
.acto{margin:18px 0}
.acto>header{position:static;display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-left-width:8px;border-radius:9px;padding:7px 12px;background:var(--card)}
.acto>header .n{margin-left:auto;color:var(--mut);font-size:13px}
.vacio{color:var(--mut);padding:10px 14px}
.card{display:grid;grid-template-columns:300px 1fr 230px;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;margin-top:8px;opacity:.72}
.card.on{opacity:1;border-color:var(--acc);box-shadow:0 0 0 1px var(--acc) inset}
.card.flash{animation:fl 1.2s}@keyframes fl{0%{background:var(--on)}100%{background:var(--card)}}
.media{position:relative}.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:2px}.thumbs img{width:100%;display:block;border-radius:3px;background:#000;aspect-ratio:16/9;object-fit:cover}
.thumbs.uno{grid-template-columns:1fr}.media video{width:100%;border-radius:6px;background:#000}.media .btn{margin-top:6px}
.info .meta,.muted{color:var(--mut);font-size:12.5px}.info .res{margin:4px 0 6px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 8px;font-size:11.5px;margin-left:6px;color:var(--mut)}
.badge.man{border-color:var(--warn);color:var(--warn)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.chip{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:14px;padding:1px 10px;font-size:12.5px;cursor:pointer}
.chip[aria-pressed=true]{border-color:var(--acc);background:var(--on);font-weight:600}
.ctl{display:flex;flex-direction:column;gap:7px;font-size:13px}.ctl label{display:flex;flex-direction:column;gap:2px;color:var(--mut)}
.ctl .inc{flex-direction:row;align-items:center;gap:8px;color:var(--fg);font-weight:600;font-size:14px}
.ctl select,.ctl input[type=range]{width:100%}.ctl select{font:inherit;padding:3px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.ctl .mv{display:flex;gap:6px}
@media(max-width:980px){.card{grid-template-columns:1fr}}
</style></head><body>
<header>
  <h1>__TITULO__</h1>
  <div class="sub" id="sub"></div>
  <div class="kpis" id="kpis"></div>
  <div id="timeline" role="list" aria-label="Línea de tiempo propuesta"></div>
  <div class="toolbar">
    <button class="btn primary" id="export">⬇ Descargar decisiones</button>
    <button class="btn" id="copy">Copiar JSON</button>
    <button class="btn" id="reset">Restablecer propuesta</button>
    <label><input type="checkbox" id="f-inc"> solo los que entran</label>
    <label><input type="checkbox" id="f-rep"> solo con tomas repetidas</label>
    <span id="estado"></span>
  </div>
</header>
<main>
  <details class="ayuda"><summary>Cómo se usa</summary>
    <ol>
      <li>El programa agrupó las <b>tomas repetidas</b> (mismo plano grabado varias veces) y propuso un orden según tu historia: llegada → ambiente → espejo → pasadizo → sube a la camilla → piedras → vapor → mascarilla → cremas → cierre.</li>
      <li>Revisa cada etapa. Marca <b>«En el spot»</b> los planos que quieres, cambia la <b>toma</b> si otra salió mejor, ajusta <b>desde qué segundo</b> y <b>cuántos beats</b> dura, o muévelo de etapa/orden.</li>
      <li>Pulsa <b>Descargar decisiones</b> y ejecuta <code>python spa_aplicar.py "ruta\decisiones_spot_spa.json"</code>: genera <code>salida\borrador.mp4</code> y <code>salida\spot.xml</code> (para Premiere).</li>
      <li>Tus cambios se guardan solos en este navegador. «Restablecer propuesta» vuelve a la versión automática.</li>
    </ol>
  </details>
  <section id="borrador" hidden>
    <video id="vb" controls preload="metadata"></video>
    <div class="txt"><h2>Cómo quedaría (borrador)</h2>
      <p class="muted">Video armado con <b>__BORRADOR_TXT__</b>, con los cortes sobre los beats de la música (__MUSICA__). Está hecho con los proxies de baja resolución, solo para ver el ritmo y el orden. Si cambias algo aquí, descarga las decisiones y regenéralo con <code>spa_aplicar.py</code>.</p></div>
  </section>
  <div id="actos"></div>
</main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const P=JSON.parse(document.getElementById('payload').textContent);
const ACT=Object.fromEntries(P.actos.map(a=>[a.id,a]));
const PL=Object.fromEntries(P.planos.map(p=>[p.id,p]));
const SPB=P.musica.spb||60/P.musica.bpm, KEY='spa-montaje:'+P.hash, LIMITE=120;
const $=(s,r=document)=>r.querySelector(s);
const h=(tag,attrs={},...kids)=>{const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==false&&v!=null)e.setAttribute(k,v===true?'':v)}for(const c of kids.flat())if(c!=null)e.append(c.nodeType?c:document.createTextNode(c));return e};
const initState=()=>{const st={planos:{}};P.planos.forEach((p,i)=>{st.planos[p.id]={acto:p.acto,incluir:p.incluir,toma:p.toma,inicio_s:p.inicio_s,beats:p.beats,orden:i}});return st};
let state=(()=>{try{const o=JSON.parse(localStorage.getItem(KEY)||'null');if(o&&o.planos)return o}catch(e){}return initState()})();
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(state));$('#estado').textContent='Cambios guardados en este navegador'}catch(e){$('#estado').textContent='No se pudo guardar aquí: descarga las decisiones'}};
const tomaOf=id=>{const p=PL[id],s=state.planos[id];return p.tomas.find(t=>t.nombre===s.toma)||p.tomas[0]};
const lenOf=id=>state.planos[id].beats*SPB;
const maxInicio=id=>Math.max(0,tomaOf(id).duracion_s-lenOf(id)-0.05);
const idsEn=a=>Object.keys(state.planos).filter(i=>state.planos[i].acto===a).sort((x,y)=>state.planos[x].orden-state.planos[y].orden);
const entran=()=>{const o=[];for(const a of P.actos){if(a.id==='descartar')continue;for(const i of idsEn(a.id))if(state.planos[i].incluir)o.push(i)}return o};
const total=()=>entran().reduce((s,i)=>s+lenOf(i),0);
const fmt=s=>`${Math.floor(s/60)}:${String(Math.round(s%60)).padStart(2,'0')}`;

function renderHead(){
  const r=P.resumen,t=total(),n=entran().length;
  $('#sub').textContent=`${r.clips} clips → ${r.planos} planos distintos · ${r.agrupados} clips agrupados como tomas repetidas (${r.grupos_repetidos} planos con varias tomas)`;
  $('#kpis').replaceChildren(
    h('span',{class:'kpi'},'Planos en el spot: ',h('b',{},n)),
    h('span',{class:'kpi'+(t>LIMITE?' warn':'')},'Duración: ',h('b',{},`${t.toFixed(0)} s (${fmt(t)})`),` · límite ${fmt(LIMITE)}`),
    h('span',{class:'kpi'},'Música: ',h('b',{},P.musica.nombre),` · ~${Math.round(60/SPB)} BPM`));
  const tl=$('#timeline');tl.replaceChildren();
  for(const i of entran()){const a=ACT[state.planos[i].acto];
    tl.append(h('div',{class:'seg',role:'listitem',style:`width:${lenOf(i)/Math.max(t,1)*100}%;background:${a.color}`,title:`${i} · ${tomaOf(i).stem} · ${lenOf(i).toFixed(1)} s · ${a.titulo}`,onclick:()=>goTo(i)}))}
}
function goTo(i){const c=document.getElementById('card-'+i);if(!c)return;c.scrollIntoView({behavior:'smooth',block:'center'});c.classList.remove('flash');void c.offsetWidth;c.classList.add('flash')}

function cardEl(id){
  const p=PL[id],s=state.planos[id],t=tomaOf(id),L=lenOf(id);
  const card=h('article',{class:'card'+(s.incluir?' on':''),id:'card-'+id});
  const media=h('div',{class:'media'});
  const fr=[...new Set(t.frames)];const grid=h('div',{class:'thumbs'+(fr.length===1?' uno':'')},fr.map(f=>h('img',{src:f,loading:'lazy',alt:`Fotograma de ${t.stem}`})));
  media.append(grid);
  if(!P.sin_video){media.append(h('button',{class:'btn small',type:'button',onclick:()=>{
    const v=h('video',{controls:true,autoplay:true,muted:true,preload:'metadata',src:`${t.rel}#t=${s.inicio_s.toFixed(2)},${(s.inicio_s+L).toFixed(2)}`});
    v.onerror=()=>media.replaceChildren(grid,h('p',{class:'muted'},'El vídeo no está disponible en esta copia.'));
    media.replaceChildren(v,h('button',{class:'btn small',type:'button',onclick:()=>refresh(id)},'Cerrar vídeo'))}},'▶ Ver desde el segundo '+s.inicio_s.toFixed(1)))}
  const info=h('div',{class:'info'},
    h('h3',{},`${id} · ${t.stem}`,
      h('span',{class:'badge'},p.tomas.length>1?`${p.tomas.length} tomas`:'1 toma'),
      p.ajuste_manual?h('span',{class:'badge man',title:'Etapa corregida a mano tras ver los fotogramas'},'etapa ajustada'):null),
    h('p',{class:'meta'},`${t.duracion_s.toFixed(0)} s · nota IA ${t.nota}/10`+(p.acto_ia&&p.acto_ia!==s.acto?` · IA pensó: ${(ACT[p.acto_ia]||{titulo:p.acto_ia}).titulo}`:'')),
    h('p',{class:'res'},p.resumen||'(sin descripción)'),
    p.tomas.length>1?h('div',{},h('span',{class:'muted'},'Tomas repetidas — elige cuál usar:'),
      h('div',{class:'chips'},p.tomas.map(x=>h('button',{class:'chip',type:'button','aria-pressed':String(x.nombre===s.toma),onclick:()=>{s.toma=x.nombre;s.inicio_s=Math.min(s.inicio_s,maxInicio(id));changed(id)}},`${x.stem} · ${x.duracion_s.toFixed(0)} s`)))):null);
  const sel=(opts,val,fn)=>{const e=h('select',{},opts.map(([v,l])=>h('option',{value:v},l)));e.value=val;e.onchange=()=>fn(e.value);return e};
  const rng=h('input',{type:'range',min:0,max:maxInicio(id).toFixed(2),step:0.1,value:Math.min(s.inicio_s,maxInicio(id)).toFixed(1),'aria-label':'Desde el segundo'});
  const lab=h('span',{},`${Math.min(s.inicio_s,maxInicio(id)).toFixed(1)} s`);
  rng.oninput=()=>{s.inicio_s=parseFloat(rng.value);lab.textContent=`${s.inicio_s.toFixed(1)} s`};
  rng.onchange=()=>changed(id);
  const ids=idsEn(s.acto),k=ids.indexOf(id);
  const ctl=h('div',{class:'ctl'},
    h('label',{class:'inc'},h('input',{type:'checkbox',checked:s.incluir,onchange:e=>{s.incluir=e.target.checked;changed(id,true)}}),'En el spot'),
    h('label',{},'Etapa',sel(P.actos.map(a=>[a.id,a.titulo]),s.acto,v=>{s.acto=v;s.orden=Math.max(...Object.values(state.planos).map(x=>x.orden))+1;changed(id,true)})),
    h('label',{},'Duración',sel([2,4,6,8].map(b=>[b,`${b} beats · ${(b*SPB).toFixed(1)} s`]),s.beats,v=>{s.beats=+v;s.inicio_s=Math.min(s.inicio_s,maxInicio(id));changed(id)})),
    h('label',{},h('span',{},'Desde el segundo: ',lab),rng),
    h('div',{class:'mv'},h('button',{class:'btn small',type:'button',disabled:k<=0,onclick:()=>move(id,-1)},'▲ subir'),h('button',{class:'btn small',type:'button',disabled:k>=ids.length-1,onclick:()=>move(id,1)},'▼ bajar')));
  card.append(media,info,ctl);return card}
function move(id,d){const ids=idsEn(state.planos[id].acto),k=ids.indexOf(id),o=ids[k+d];if(!o)return;const a=state.planos[id],b=state.planos[o];[a.orden,b.orden]=[b.orden,a.orden];save();renderAll()}
function changed(id,structural){save();if(structural){renderAll()}else{const c=document.getElementById('card-'+id);if(c)c.replaceWith(cardEl(id));renderHead();renderActHeads()}}
function refresh(id){const c=document.getElementById('card-'+id);if(c)c.replaceWith(cardEl(id))}
function actHead(a){const ids=idsEn(a.id),inc=ids.filter(i=>state.planos[i].incluir),d=inc.reduce((s,i)=>s+lenOf(i),0);
  return h('header',{style:`border-left-color:${a.color}`},h('h2',{},a.titulo),h('span',{class:'n'},a.id==='descartar'?`${ids.length} planos`:`${inc.length} de ${ids.length} planos · ${d.toFixed(1)} s`+(a.presupuesto_s?` (presupuesto ${a.presupuesto_s} s)`:'')))}
function renderActHeads(){for(const a of P.actos){const s=document.getElementById('acto-'+a.id);if(s)s.firstElementChild.replaceWith(actHead(a))}}
function renderAll(){
  renderHead();
  const soloInc=$('#f-inc').checked,soloRep=$('#f-rep').checked,root=$('#actos');root.replaceChildren();
  for(const a of P.actos){
    let ids=idsEn(a.id);if(soloInc)ids=ids.filter(i=>state.planos[i].incluir);if(soloRep)ids=ids.filter(i=>PL[i].tomas.length>1);
    const sec=h('section',{class:'acto',id:'acto-'+a.id},actHead(a));
    if(!ids.length)sec.append(h('p',{class:'vacio'},a.id==='descartar'?'Nada descartado.':'Sin planos con este filtro en esta etapa. Puedes mover planos aquí con su selector «Etapa».'));
    ids.forEach(i=>sec.append(cardEl(i)));
    if(a.id==='descartar'&&ids.length){const d=h('details',{},h('summary',{},`Ver ${ids.length} planos descartados`));d.append(...sec.querySelectorAll('.card'));sec.append(d)}
    root.append(sec)}}
function decisiones(){return{version:1,origen:'html',generado:new Date().toISOString(),duracion_s:+total().toFixed(2),
  orden:entran().map(i=>({plano:i,toma:state.planos[i].toma,inicio_s:+state.planos[i].inicio_s.toFixed(2),beats:state.planos[i].beats,acto:state.planos[i].acto}))}}
$('#export').onclick=()=>{const b=new Blob([JSON.stringify(decisiones(),null,2)],{type:'application/json'}),a=h('a',{href:URL.createObjectURL(b),download:'decisiones_spot_spa.json'});document.body.append(a);a.click();a.remove();$('#estado').textContent='Decisiones descargadas'};
$('#copy').onclick=async()=>{const t=JSON.stringify(decisiones(),null,2);try{await navigator.clipboard.writeText(t);$('#estado').textContent='JSON copiado'}catch(e){const x=h('textarea',{},t);document.body.append(x);x.select();document.execCommand('copy');x.remove();$('#estado').textContent='JSON copiado'}};
$('#reset').onclick=()=>{if(confirm('¿Volver a la propuesta automática? Se pierden tus cambios en este navegador.')){state=initState();save();renderAll()}};
$('#f-inc').onchange=$('#f-rep').onchange=renderAll;
if(!P.sin_video&&P.borrador){const vb=$('#vb');vb.src=P.borrador;vb.onloadedmetadata=()=>{$('#borrador').hidden=false}}
renderAll();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--propuesta", type=Path, default=CACHE / "propuesta.json")
    ap.add_argument("--out", type=Path, default=HERE / "propuesta_montaje.html")
    ap.add_argument("--borrador", default="salida/borrador.mp4")
    ap.add_argument("--estatico", type=Path, help="carpeta de salida para versión sin vídeos (GitHub)")
    ap.add_argument("--decisiones", type=Path, help="decisiones_spot_spa.json descargado del HTML: pasa a ser el estado inicial")
    args = ap.parse_args()

    P = json.loads(args.propuesta.read_text(encoding="utf-8"))
    P["origen"] = "propuesta automática"
    if args.decisiones:
        dec = json.loads(args.decisiones.read_text(encoding="utf-8-sig"))["orden"]
        pos = {d["plano"]: i for i, d in enumerate(dec)}
        act_ids = [a["id"] for a in P["actos"]]
        for p in P["planos"]:
            d = dec[pos[p["id"]]] if p["id"] in pos else None
            p["incluir"] = d is not None
            if d:
                p.update(toma=d["toma"], inicio_s=d["inicio_s"], beats=d["beats"], acto=d["acto"])
        P["planos"].sort(key=lambda p: (act_ids.index(p["acto"]), 0 if p["id"] in pos else 1,
                                       pos.get(p["id"], p["orden_rodaje"])))
        P["origen"] = "decisiones del autor"
    P["musica"]["nombre"] = Path(P["musica"]["ruta"]).name.split("_Media_")[0].replace("YTDown.com_YouTube_", "")[:60]
    del P["musica"]["ruta"]  # no publicar rutas locales
    P["hash"] = hashlib.sha1(json.dumps([(p["id"], p["acto"], p["incluir"], p["toma"], p["inicio_s"], p["beats"])
                                         for p in P["planos"]]).encode()).hexdigest()[:10]
    P["sin_video"] = bool(args.estatico)
    P["borrador"] = None if args.estatico else args.borrador

    out = args.out
    if args.estatico:
        dst = args.estatico
        if dst.exists():
            shutil.rmtree(dst)
        (dst / "img").mkdir(parents=True)
        out = dst / "index.html"
        copied = set()
        for p in P["planos"]:
            for t in p["tomas"]:
                keep = t["frames"] if t["nombre"] == p["toma"] else t["frames"][:1]
                new = []
                for f in keep:
                    name = Path(f).name
                    if name not in copied:
                        shutil.copy2(HERE / f, dst / "img" / name)
                        copied.add(name)
                    new.append(f"img/{name}")
                t["frames"] = new + new[-1:] * (6 - len(new)) if len(new) < 6 else new
                t.pop("ruta", None)
                t["rel"] = ""
    else:
        for p in P["planos"]:
            for t in p["tomas"]:
                t.pop("ruta", None)   # rutas absolutas no hacen falta en la página

    title = P["proyecto"]
    html = (TEMPLATE.replace("__TITULO__", title)
            .replace("__MUSICA__", P["musica"]["nombre"])
            .replace("__BORRADOR_TXT__", "tus decisiones" if args.decisiones else "la propuesta inicial")
            .replace("__PAYLOAD__", json.dumps(P, ensure_ascii=False).replace("</", "<\\/")))
    out.write_text(html, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"OK -> {out}  ({kb:.0f} KB, {len(P['planos'])} planos)")


if __name__ == "__main__":
    main()
