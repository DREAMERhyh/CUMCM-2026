"use strict";
// Rendering and input orchestration only. All localization is performed in Python.
const $ = id => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const COLORS = ["#2877b5", "#d88727", "#258b73", "#8c62b4", "#b45876", "#527e91"];
let result = null;
let dirty = false;
let busy = false;
const fmt = (v, digits=2) => v == null ? "—" : Number(v).toFixed(digits);

function message(text, error=false) { $("message").textContent=text; $("message").className=error?"error":""; }
function markDirty() { dirty=true; $("dirty").hidden=false; }
function numericInput(value, label, min, max) {
  const input=document.createElement("input"); input.type="number"; input.step="any";
  input.value=value??""; input.setAttribute("aria-label",label);
  if(min!=null)input.min=min; if(max!=null)input.max=max;
  return input;
}
function appendCell(row, element) { const cell=row.insertCell(); cell.append(element); }
function sourceRow(s, index) {
  const row=$("sources").tBodies[0].insertRow();
  ["channel","x","y","radius"].forEach(key=>appendCell(row,numericInput(s[key],`G${index+1} ${key}`, key==="channel"?1:key==="radius"?1000:null,key==="channel"?20:key==="radius"?1500:null)));
  const remove=document.createElement("button"); remove.textContent="×"; remove.className="remove"; remove.setAttribute("aria-label",`删除 G${index+1}`);
  remove.onclick=()=>{if($("sources").tBodies[0].rows.length<=1)return message("至少保留一个干扰源。",true);row.remove();syncChannels();markDirty();};
  appendCell(row,remove);
}
function detectorRow(d, index) {
  const row=$("detectors").tBodies[0].insertRow(); row.insertCell().textContent=`S${index+1}`;
  ["x","y","error_deg"].forEach(key=>appendCell(row,numericInput(d[key],`S${index+1} ${key}`,key==="error_deg"?-1:null,key==="error_deg"?1:null)));
  const remove=document.createElement("button"); remove.textContent="×";remove.className="remove";remove.setAttribute("aria-label",`删除 S${index+1}`);
  remove.onclick=()=>{if($("detectors").tBodies[0].rows.length<=1)return message("至少保留一个检测点。",true);row.remove();renumberDetectors();markDirty();};appendCell(row,remove);
}
function renumberDetectors(){Array.from($("detectors").tBodies[0].rows).forEach((row,i)=>{row.cells[0].textContent=`S${i+1}`;row.querySelectorAll("input").forEach((e,j)=>e.setAttribute("aria-label",`S${i+1} ${["x","y","error_deg"][j]}`));row.querySelector("button").setAttribute("aria-label",`删除 S${i+1}`);});}
function syncChannels(preferred=$("active").value) {
  const channels=Array.from($("sources").tBodies[0].rows).map(r=>r.querySelector("input").value);
  $("active").replaceChildren(...channels.map((c,i)=>{const o=document.createElement("option");o.value=c;o.textContent=`${c} · G${i+1}`;return o;}));
  if(channels.includes(String(preferred)))$("active").value=preferred;
}
function populate(scene) {
  $("sources").tBodies[0].replaceChildren();$("detectors").tBodies[0].replaceChildren();
  scene.sources.forEach(sourceRow);scene.detectors.forEach(detectorRow);syncChannels(scene.active_channel);
  $("seed").value=scene.seed;$("source-count").value=scene.sources.length;$("detector-count").value=scene.detectors.length;
  dirty=false;$("dirty").hidden=true;
}
function value(input, optional=false) {
  if(!input.value.trim()){if(optional)return null;throw Error(`${input.getAttribute("aria-label")||"输入"}不能为空。`);}
  if(!Number.isFinite(Number(input.value)))throw Error("请输入有限数值。");return Number(input.value);
}
function readScene() {
  const sources=Array.from($("sources").tBodies[0].rows).map(row=>{const i=row.querySelectorAll("input");return {channel:value(i[0]),x:value(i[1]),y:value(i[2]),radius:value(i[3])};});
  const detectors=Array.from($("detectors").tBodies[0].rows).map(row=>{const i=row.querySelectorAll("input");return {x:value(i[0]),y:value(i[1]),error_deg:value(i[2],true)};});
  return {seed:value($("seed")),active_channel:Number($("active").value),sources,detectors};
}
async function request(path, data) {
  const response=await fetch(path,data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  const body=await response.json();if(!response.ok)throw Error(body.error||"计算失败。");return body;
}
async function run(action, replace=false) {
  if(busy)return;busy=true;document.querySelectorAll("button,input,select").forEach(b=>b.disabled=true);
  try { const next=await action();result=next;if(replace)populate(next.scene);dirty=false;$("dirty").hidden=true;render();message("计算完成 · 当前结果对应已核验的输入参数。"); }
  catch(error){message(error.message,true);}
  finally{busy=false;document.querySelectorAll("button,input,select").forEach(b=>b.disabled=false);}
}

function element(tag, attrs={}, text=null) {
  const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));if(text!=null)e.textContent=text;return e;
}
function draw(svg, bounds, local=false) {
  svg.replaceChildren();svg.setAttribute("xmlns",NS);
  svg.append(element("rect",{width:640,height:640,fill:"white"}));
  const pad=58,size=524;
  const width=Math.max(bounds[2]-bounds[0],bounds[3]-bounds[1]);
  const cx=(bounds[0]+bounds[2])/2,cy=(bounds[1]+bounds[3])/2;
  const xmin=cx-width/2,ymin=cy-width/2,xmax=cx+width/2,ymax=cy+width/2;
  const scale=size/width, X=x=>pad+(x-xmin)*scale, Y=y=>pad+(ymax-y)*scale;
  const defs=element("defs"),clip=element("clipPath",{id:`clip-${svg.id}`});clip.append(element("rect",{x:pad,y:pad,width:size,height:size}));defs.append(clip);svg.append(defs);
  const grid=element("g"),plot=element("g",{"clip-path":`url(#clip-${svg.id})`});
  const textStyle={"font-family":"Arial, Microsoft YaHei, sans-serif","font-size":12,fill:"#65768a"};
  const text=(parent,x,y,t,attrs={})=>parent.append(element("text",{x,y,...textStyle,...attrs},t));
  const line=(parent,p,q,attrs={})=>parent.append(element("line",{x1:X(p[0]),y1:Y(p[1]),x2:X(q[0]),y2:Y(q[1]),stroke:"#bac5d0","stroke-width":1,...attrs}));
  const rough=width/5,base=10**Math.floor(Math.log10(rough)),step=[1,2,5,10].map(n=>n*base).find(v=>v>=rough);
  for(let x=Math.ceil(xmin/step)*step;x<=xmax+step*1e-8;x+=step){line(grid,[x,ymin],[x,ymax],{stroke:"#edf0f4"});text(svg,X(x),pad+size+22,fmt(x,step<1?2:0),{"text-anchor":"middle"});}
  for(let y=Math.ceil(ymin/step)*step;y<=ymax+step*1e-8;y+=step){line(grid,[xmin,y],[xmax,y],{stroke:"#edf0f4"});text(svg,pad-9,Y(y)+4,fmt(y,step<1?2:0),{"text-anchor":"end"});}
  svg.append(grid);svg.append(plot);
  plot.append(element("circle",{cx:X(0),cy:Y(0),r:1800*scale,fill:local?"none":"#f8fafc",stroke:"#aebdca","stroke-width":1.3,"stroke-dasharray":"6 5"}));
  // Grid remains visible above the very light domain fill.
  if(!local){plot.append(grid.cloneNode(true));}
  if(xmin<=0&&xmax>=0)line(plot,[0,ymin],[0,ymax],{stroke:"#93a5b5","stroke-width":1.2});
  if(ymin<=0&&ymax>=0)line(plot,[xmin,0],[xmax,0],{stroke:"#93a5b5","stroke-width":1.2});
  svg.append(element("rect",{x:pad,y:pad,width:size,height:size,fill:"none",stroke:"#dce3e9"}));
  text(svg,320,628,"x / m（东）",{"text-anchor":"middle","font-size":13});text(svg,20,28,"y / m（北）",{"font-size":13});
  const region=result.region;
  const points=region.status==="bounded"?region.vertices:region.display_polygon;
  if(points.length>=3)plot.append(element("polygon",{points:points.map(p=>`${X(p[0])},${Y(p[1])}`).join(" "),fill:"#9c82c9","fill-opacity":.22,stroke:"#8063af","stroke-width":1.6}));
  // A positive ray is truncated only for the viewport; never extended backwards.
  function ray(position, angle, color, dashed=false) {
    const t=angle*Math.PI/180,u=[Math.cos(t),Math.sin(t)];
    const length=Math.hypot(position[0]-cx,position[1]-cy)+width*2;
    line(plot,position,[position[0]+length*u[0],position[1]+length*u[1]],{stroke:color,"stroke-width":dashed?1:1.45,"stroke-dasharray":dashed?"5 5":"none",opacity:dashed?.6:.9});
  }
  result.observations.forEach((o,i)=>{if(o.status!=="direction")return;const color=COLORS[i%COLORS.length];ray(o.position,o.bearing_deg,color);if($("wedges").checked){ray(o.position,o.bearing_deg-1,color,true);ray(o.position,o.bearing_deg+1,color,true);}});
  if(region.diameter_pair){line(plot,...region.diameter_pair,{stroke:"#5e478e","stroke-width":2.5});
    region.diameter_pair.forEach(p=>plot.append(element("circle",{cx:X(p[0]),cy:Y(p[1]),r:3,fill:"#5e478e"})));}
  if($("circle").checked&&region.diameter_circle){const c=region.diameter_circle;plot.append(element("circle",{cx:X(c.center[0]),cy:Y(c.center[1]),r:c.radius*scale,fill:"none",stroke:"#5e478e","stroke-width":1.4,"stroke-dasharray":"7 4"}));}
  function point(p,label,color,square=false) {
    if(square)plot.append(element("rect",{x:X(p[0])-4.5,y:Y(p[1])-4.5,width:9,height:9,fill:color,stroke:"white","stroke-width":1.5}));
    else plot.append(element("circle",{cx:X(p[0]),cy:Y(p[1]),r:4.8,fill:color,stroke:"white","stroke-width":1.6}));
    text(plot,X(p[0])+8,Y(p[1])-9,label,{fill:color,"font-size":13,"font-weight":600,"paint-order":"stroke",stroke:"white","stroke-width":3,"stroke-linejoin":"round"});
  }
  if($("truth").checked)result.scene.sources.forEach((s,i)=>{if(!local||s.channel===result.scene.active_channel)point([s.x,s.y],`G${i+1}`,s.channel===result.scene.active_channel?"#ce4e53":"#a68a8b",true);});
  result.observations.forEach((o,i)=>point(o.position,`S${i+1}`,COLORS[i%COLORS.length]));
  if(local&&region.status==="bounded")region.vertices.forEach((p,i)=>{
    plot.append(element("circle",{cx:X(p[0]),cy:Y(p[1]),r:2.7,fill:"#8063af"}));
    const px=X(p[0]),py=Y(p[1]);text(plot,px+(px<320?-8:8),py+(py<320?-9:17),`V${i+1}`,{"text-anchor":px<320?"end":"start",fill:"#7654a5","font-size":12,"paint-order":"stroke",stroke:"white","stroke-width":3});
  });
  if(!local&&xmin<=0&&xmax>=0&&ymin<=0&&ymax>=0)text(plot,X(0)+6,Y(0)+16,"O");
  text(svg,pad,30,local?"Bearing intersection / detail":"Source domain: R = 1800 m",{"font-size":13,fill:"#344e65"});
  if(local&&region.status!=="bounded"){
    const caption=region.status==="empty"?"交会区域为空":region.bearing_count?"区域无界，暂不能计算有限直径":"没有有效示向度";
    svg.append(element("rect",{x:92,y:286,width:456,height:56,rx:5,fill:"white","fill-opacity":.95,stroke:"#e1e7ed"}));text(svg,320,320,caption,{"text-anchor":"middle","font-size":16});
  }
}
function render() {
  if(!result)return;
  const r=result.region;
  $("bearing-count").textContent=`${r.bearing_count} / ${result.observations.length}`;
  $("region-status").textContent={bounded:r.vertices.length===1?"单点":r.vertices.length===2?"线段":"有界多边形",unbounded:"无界",empty:"空集"}[r.status];
  $("diameter").textContent=r.status==="unbounded"?"∞":fmt(r.diameter,3);
  $("audit").textContent=result.audit.truth_in_region==null?"无有效观测":result.audit.truth_in_region?"通过":"未通过";
  $("audit").className=result.audit.truth_in_region?"status-good":"status-warn";
  $("observations").replaceChildren(...result.observations.map((o,i)=>{const row=document.createElement("tr");[`S${i+1}`,fmt(o.distance),fmt(o.true_bearing_deg,3),fmt(o.bearing_deg,3),fmt(o.error_deg,4)].forEach(t=>row.insertCell().textContent=t);row.cells[0].style.color=COLORS[i%COLORS.length];return row;}));
  $("vertex-info").textContent=r.status==="bounded"?`顶点数 ${r.vertices.length}；面积 ${fmt(r.area,3)} m²；直径 ${fmt(r.diameter,6)} m。`:`当前区域${r.status==="empty"?"为空":"无界"}，没有可报告的有限多边形直径。`;
  $("vertices").textContent=r.vertices.map((p,i)=>`V${i+1} = (${fmt(p[0],6)}, ${fmt(p[1],6)})`).join("\n");
  $("geometry-note").textContent=r.status==="bounded"?"显示的是纯测向扇区交集；圆形分布区域仅作背景。紫色粗线连接直径端点。":"浅紫色只显示扇区交集在当前画幅中的部分；画幅裁剪不会用于直径计算。";
  $("circle-note").textContent=r.diameter_circle?`以区域直径为直径、以直径端点中点为圆心的圆：${r.diameter_circle.covers?"覆盖本例区域，但不代表对所有形状都成立。":`不能覆盖本例区域，最大超出 ${fmt(r.diameter_circle.excess,6)} m。`}`:"增加不同位置的有效观测，可以进一步约束定位区域。";
  const entries=[["#ce4e53","干扰源真值"],...result.observations.map((_,i)=>[COLORS[i%COLORS.length],`S${i+1}`]),["#9c82c9","定位区域"],["#5e478e","直径"]];
  $("legend").replaceChildren(...entries.filter((_,i)=>i!==0||$("truth").checked).map(([color,name])=>{const span=document.createElement("span"),dot=document.createElement("i");dot.style.background=color;span.append(dot,document.createTextNode(name));return span;}));
  draw($("global-plot"),result.bounds);
  let bounds=result.bounds;
  if(r.status==="bounded"){
    const xs=r.vertices.map(p=>p[0]),ys=r.vertices.map(p=>p[1]);
    const cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2;
    let width=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),10)*1.65;
    if($("circle").checked&&r.diameter_circle)width=Math.max(width,r.diameter_circle.radius*3);
    bounds=[cx-width/2,cy-width/2,cx+width/2,cy+width/2];
  }
  draw($("local-plot"),bounds,true);
}
function download(text, name, type) {const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportSVG(id,name) {
  if(!result)return;if(dirty)return message("输入已修改，请先计算，再导出与输入一致的图形。",true);
  const copy=$(id).cloneNode(true);copy.setAttribute("width","1000");copy.setAttribute("height","1000");
  const desc=element("desc",{},`B题全向测向定位；种子 ${result.scene.seed}；频道 ${result.scene.active_channel}；纯角度交会；单位米。`);copy.prepend(desc);
  download('<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(copy),name,"image/svg+xml;charset=utf-8");
}
$("sources").addEventListener("input",()=>{syncChannels();markDirty();});$("detectors").addEventListener("input",markDirty);$("seed").addEventListener("input",markDirty);
$("active").onchange=()=>{markDirty();run(()=>request("/api/calculate",readScene()));};
$("calculate").onclick=()=>run(()=>request("/api/calculate",readScene()));
$("demo").onclick=()=>run(()=>request("/api/demo"),true);
$("generate").onclick=()=>run(()=>request("/api/generate",{seed:value($("seed")),source_count:value($("source-count")),detector_count:value($("detector-count")),mode:$("mode").value}),true);
$("add-source").onclick=()=>{const rows=$("sources").tBodies[0].rows;if(rows.length>=20)return message("最多 20 个不同频道的源。",true);const used=Array.from(rows).map(r=>Number(r.querySelector("input").value));const c=Array.from({length:20},(_,i)=>i+1).find(c=>!used.includes(c));sourceRow({channel:c,x:0,y:0,radius:1250},rows.length);syncChannels();markDirty();};
$("add-detector").onclick=()=>{const count=$("detectors").tBodies[0].rows.length;if(count>=64)return message("当前实验窗口最多支持 64 个检测点。",true);detectorRow({x:0,y:0,error_deg:null},count);markDirty();};
for(const id of ["truth","wedges","circle"])$(id).onchange=render;
$("export-global").onclick=()=>exportSVG("global-plot","b_global.svg");$("export-local").onclick=()=>exportSVG("local-plot","b_localization.svg");
$("export-result").onclick=()=>{if(!result)return;if(dirty)return message("输入已修改，请先重新计算。",true);download(JSON.stringify(result,null,2),"b_result.json","application/json");};
$("save").onclick=()=>{try{download(JSON.stringify(readScene(),null,2),"b_scene.json","application/json");}catch(e){message(e.message,true);}};
$("import").onclick=()=>$("file").click();$("file").onchange=async()=>{const file=$("file").files[0];if(!file)return;await run(async()=>{const data=JSON.parse(await file.text());return request("/api/calculate",data.scene||data);},true);$("file").value="";};
run(()=>request("/api/demo"),true);
