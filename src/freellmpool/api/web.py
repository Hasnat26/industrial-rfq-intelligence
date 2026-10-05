"""Minimal browser UI for the procurement SaaS MVP.

The UI deliberately stays dependency-free: FastAPI serves one HTML document and the
browser talks to the authenticated JSON API. This keeps the first customer workflow
small while reusing the existing domain and review endpoints.
"""

from __future__ import annotations

from fastapi.responses import HTMLResponse

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Industrial RFQ Intelligence</title>
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17202a;background:#f5f7fa}
*{box-sizing:border-box}body{margin:0}.shell{max-width:1400px;margin:auto;padding:24px}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}
h1,h2,h3{margin:0 0 10px}h1{font-size:24px}h2{font-size:18px}.muted{color:#65717e}
.card{background:white;border:1px solid #dfe5eb;border-radius:10px;padding:18px;box-shadow:0 1px 2px #00000008;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.layout{display:grid;grid-template-columns:300px 1fr;gap:16px}
label{display:block;font-size:12px;font-weight:700;margin:10px 0 5px}
input,select,textarea{width:100%;border:1px solid #cbd5df;border-radius:7px;padding:9px;background:white}
textarea{min-height:90px;resize:vertical}button{border:0;border-radius:7px;padding:9px 13px;background:#1f5eff;color:white;font-weight:700;cursor:pointer}
button.secondary{background:#e9eef4;color:#17202a}button.danger{background:#b42318}button:disabled{opacity:.5;cursor:not-allowed}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.stack>*+*{margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px;border-bottom:1px solid #e7ebef;text-align:left;vertical-align:top}th{background:#f8fafc}
.badge{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;background:#eef2f6}
.ok{background:#dff7e8;color:#116329}.warn{background:#fff3cd;color:#7a5700}.bad{background:#ffe2e0;color:#9b1c15}.blue{background:#e3efff;color:#164c91}
.hidden{display:none}.notice{padding:10px;border-radius:7px;background:#eef5ff;margin-bottom:12px}.error{background:#fff0ef;color:#8b1e16}
#toast{position:fixed;right:20px;bottom:20px;max-width:420px;z-index:5}.small{font-size:12px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="shell">
<header><div><h1>Industrial RFQ Intelligence</h1><div class="muted">Evidence-aware procurement decision support</div></div><div id="session"></div></header>

<section id="auth" class="card">
<h2>Sign in</h2>
<div class="grid">
<div><label>Email</label><input id="email" type="email" placeholder="engineer@example.com"></div>
<div><label>Password</label><input id="password" type="password" placeholder="Minimum 8 characters"></div>
</div>
<div class="actions"><button onclick="login()">Sign in</button><button class="secondary" onclick="register()">Create account</button></div>
<p class="small muted">The browser stores only the bearer token in session storage. It is sent to this API origin only.</p>
</section>

<section id="workspace" class="hidden">
<div class="layout">
<aside>
<div class="card">
<h2>Workspace</h2>
<label>Organization</label><select id="org" onchange="loadProjects()"></select>
<div class="actions"><button class="secondary" onclick="createOrg()">New organization</button></div>
<label>Project</label><select id="project" onchange="loadPackages()"></select>
<div class="actions"><button class="secondary" onclick="createProject()">New project</button></div>
<label>Package</label><select id="package" onchange="loadReview()"></select>
<div class="actions"><button onclick="createPackage()">New package</button><button class="secondary" onclick="logout()">Sign out</button></div>
</div>
<div class="card">
<h2>Engineering workflow</h2>
<div class="small muted">AI extracts and structures. Deterministic rules compare. Evidence explains. Engineers decide.</div>
<div id="gate" class="notice">Select a procurement package.</div>
</div>
</aside>

<main>
<div id="review" class="card">
<h2>Review</h2><p class="muted">Select a package to load its technical comparison and evidence register.</p>
</div>
<div id="actions" class="card hidden">
<h2>Package actions</h2>
<div class="actions">
<button onclick="downloadReport()">Download Markdown report</button>
<button class="secondary" onclick="getRfq()">View generated RFQ</button>
<button class="secondary" id="lockBtn" onclick="lockTechnical()">Lock technical bid</button>
<button class="secondary" id="openBtn" onclick="openCommercial()">Open commercial evaluation</button>
</div>
</div>
<div id="epcCard" class="card hidden"><h2>EPC workflow</h2><div id="epcWorkflow" class="small muted"></div><div id="commercialView" style="margin-top:12px"></div><div id="decisionView" style="margin-top:12px"></div><div id="auditView" style="margin-top:12px"></div></div>
<div id="batchCard" class="card hidden">
<h2>Upload vendor quotations</h2>
<p class="small muted">Upload 1–5 quotation files together. Files are matched to vendors in the same order.</p>
<div class="grid">
<div><label>Vendor names (one per line)</label><textarea id="batchVendors" placeholder="Vendor A&#10;Vendor B&#10;Vendor C"></textarea></div>
<div><label>Quotation files</label><input id="batchFiles" type="file" multiple accept=".pdf,.txt,.md"><label>Revision for all files</label><input id="batchRevision" value="R1"></div>
</div>
<div class="actions"><button onclick="uploadBatch()">Analyze quotations</button></div>
</div>
<div id="offerCard" class="card hidden">
<h2>Add vendor offer</h2>
<div class="grid">
<div><label>Vendor</label><input id="vendorName"></div>
<div><label>Revision</label><input id="revision" value="R1"></div>
<div><label>Price</label><input id="price"></div>
<div><label>Currency</label><input id="currency" value="USD"></div>
</div>
<div class="actions"><button onclick="addOffer()">Add offer</button></div>
</div>
<div id="claimCard" class="card hidden">
<h2>Add verified technical claim</h2>
<div class="grid">
<div><label>Offer</label><select id="claimOffer"></select></div>
<div><label>Parameter</label><input id="claimParameter" placeholder="Rated voltage"></div>
<div><label>Value</label><input id="claimValue" placeholder="415 V"></div>
<div><label>Claim status</label><select id="claimStatus"><option>VERIFIED</option><option>PARTIALLY VERIFIED</option><option>UNVERIFIED</option><option>INFERENCE</option><option>ASSUMPTION</option><option>CONTRADICTED</option></select></div>
</div>
<label>Evidence</label><input id="claimEvidence" placeholder="Vendor quotation p.1">
<div class="actions"><button onclick="addClaim()">Save claim</button></div>
</div>
</main>
</div>
</section>
</div>
<div id="toast"></div>
<script>
const $=id=>document.getElementById(id);
const tokenKey="rfq_token";
let token=sessionStorage.getItem(tokenKey), currentPackage=null, offers=[], workflow=null, commercial=null, decision=null, engineeringSummary=null, audit=[];

function headers(json=true){const h={};if(token)h.Authorization="Bearer "+token;if(json)h["Content-Type"]="application/json";return h}
async function api(path,opt={}){
  const isForm=typeof FormData!=="undefined" && opt.body instanceof FormData;
  opt.headers={...headers(opt.body!==undefined&&!isForm),...(opt.headers||{})};
  const r=await fetch(path,opt);if(!r.ok){let d="Request failed";try{d=(await r.json()).detail||d}catch{};throw Error(d)}return r}
function toast(msg,bad=false){$("toast").innerHTML='<div class="card '+(bad?'error':'')+'">'+esc(msg)+'</div>';setTimeout(()=>$("toast").innerHTML="",3500)}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function badge(v){let c=v==="COMPLIANT"||v==="VERIFIED"||v==="ACCEPTED"?"ok":v==="UNVERIFIED"||v==="CLARIFICATION_REQUIRED"?"warn":v==="REJECTED"||v==="CONTRADICTED"||v==="DEVIATION"?"bad":"blue";return '<span class="badge '+c+'">'+esc(v)+'</span>'}

async function login(){try{const r=await api("/auth/login",{method:"POST",body:JSON.stringify({email:$("email").value,password:$("password").value})});const d=await r.json();token=d.access_token;sessionStorage.setItem(tokenKey,token);await start()}catch(e){toast(e.message,true)}}
async function register(){try{await api("/auth/register",{method:"POST",body:JSON.stringify({email:$("email").value,password:$("password").value})});toast("Account created. Sign in.");}catch(e){toast(e.message,true)}}
function logout(){sessionStorage.removeItem(tokenKey);token=null;$("workspace").classList.add("hidden");$("auth").classList.remove("hidden");$("session").innerHTML=""}
async function start(){try{const r=await api("/auth/me");const me=await r.json();$("auth").classList.add("hidden");$("workspace").classList.remove("hidden");$("session").innerHTML='<span class="small">'+esc(me.email)+'</span>';const o=$("org");o.innerHTML=me.organizations.map(x=>'<option value="'+x.organization_id+'">'+esc(x.name)+'</option>').join("");if(!me.organizations.length){o.innerHTML='<option value="">No organization</option>';await createOrg()}else await loadProjects()}catch(e){logout();toast(e.message,true)}}
async function createOrg(){const name=prompt("Organization name");if(!name)return;try{await api("/organizations",{method:"POST",body:JSON.stringify({name})});await start();toast("Organization created")}catch(e){toast(e.message,true)}}
async function loadProjects(){const oid=$("org").value;if(!oid)return;try{const r=await api("/projects?organization_id="+oid);const xs=await r.json();$("project").innerHTML=xs.map(x=>'<option value="'+x.id+'">'+esc(x.name)+(x.code?" ("+esc(x.code)+")":"")+'</option>').join("");if(xs.length)await loadPackages();else {$("package").innerHTML="";clearReview()}}catch(e){toast(e.message,true)}}
async function createProject(){const oid=Number($("org").value);if(!oid)return;const name=prompt("Project name");if(!name)return;const code=prompt("Project code (optional)")||null;try{await api("/projects",{method:"POST",body:JSON.stringify({organization_id:oid,name,code})});await loadProjects();toast("Project created")}catch(e){toast(e.message,true)}}
async function loadPackages(){const pid=$("project").value;if(!pid)return;try{const r=await api("/packages?project_id="+pid);const xs=await r.json();$("package").innerHTML=xs.map(x=>'<option value="'+x.id+'">'+esc(x.name)+" — "+esc(x.category)+'</option>').join("");if(xs.length)await loadReview();else clearReview()}catch(e){toast(e.message,true)}}
async function createPackage(){const pid=Number($("project").value);if(!pid)return toast("Create a project first",true);const name=prompt("Package name");if(!name)return;const category=(prompt("Category: MOTOR, VFD, PLC, INSTRUMENTATION, VALVE or SWITCHGEAR","MOTOR")||"MOTOR").toUpperCase();const mode=(prompt("Mode: STANDARD or PROJECT_EPC","PROJECT_EPC")||"PROJECT_EPC").toUpperCase();const raw=prompt('Requirements JSON, e.g. [{"tag":"R-01","parameter":"Rated voltage","required_value":"415 V"}]','[{"tag":"R-01","parameter":"Rated voltage","required_value":"415 V"}]');let requirements=[];try{requirements=JSON.parse(raw||"[]")}catch{return toast("Invalid requirements JSON",true)}try{await api("/packages",{method:"POST",body:JSON.stringify({project_id:pid,name,category,mode,requirements})});await loadPackages();toast("Package created")}catch(e){toast(e.message,true)}}
function clearReview(){workflow=null;commercial=null;decision=null;engineeringSummary=null;audit=[];$("epcCard").classList.add("hidden");$("review").innerHTML='<h2>Review</h2><p class="muted">Select a procurement package.</p>';$("actions").classList.add("hidden");$("offerCard").classList.add("hidden");$("batchCard").classList.add("hidden");$("claimCard").classList.add("hidden");$("gate").textContent="Select a procurement package."}
async function loadReview(){const id=$("package").value;if(!id)return clearReview();try{const [p,c,e,o,w,a,s]=await Promise.all([api("/packages/"+id+"/rfq"),api("/packages/"+id+"/comparison"),api("/packages/"+id+"/evidence"),api("/packages/"+id+"/offers"),api("/packages/"+id+"/workflow"),api("/packages/"+id+"/audit"),api("/packages/"+id+"/engineering-decision-summary")]);const rfq=await p.json(),cmp=await c.json(),ev=await e.json();offers=await o.json();workflow=await w.json();audit=await a.json();engineeringSummary=await s.json();commercial=null;decision=null;if(cmp.commercial_open){try{commercial=await (await api("/packages/"+id+"/commercial-comparison")).json()}catch{}}try{decision=await (await api("/packages/"+id+"/decision")).json()}catch{}currentPackage={rfq,cmp,ev};renderReview();renderOffers();renderEpc();$("actions").classList.remove("hidden");$("offerCard").classList.remove("hidden");$("batchCard").classList.remove("hidden");$("claimCard").classList.remove("hidden");$("epcCard").classList.remove("hidden");$("lockBtn").disabled=cmp.technical_locked;$("openBtn").disabled=!cmp.technical_locked||cmp.commercial_open;$("gate").innerHTML=(cmp.technical_locked?"Technical bid locked":"Technical bid open")+" · "+(cmp.commercial_open?"Commercial evaluation open":"Commercial evaluation locked");}catch(e){toast(e.message,true)}}
function renderReview(){const {rfq,cmp,ev}=currentPackage;const rows=cmp.rows;const counts={COMPLIANT:0,DEVIATION:0,UNVERIFIED:0};rows.forEach(x=>counts[x.status]=(counts[x.status]||0)+1);let summaryHtml="";if(engineeringSummary){summaryHtml='<h3>Engineering decision summary</h3><div class="notice"><b>'+badge(engineeringSummary.status)+'</b><ul>'+engineeringSummary.decision_basis.map(x=>'<li>'+esc(x)+'</li>').join("")+'</ul></div><div style="overflow:auto"><table><thead><tr><th>Vendor</th><th>Disposition</th><th>Score</th><th>Evidence</th><th>Compliant</th><th>Deviation</th><th>Major</th><th>Conflict</th><th>Missing</th></tr></thead><tbody>'+engineeringSummary.vendor_profiles.map(x=>'<tr><td>'+esc(x.vendor)+'</td><td>'+badge(x.disposition)+'</td><td>'+x.technical_score.toFixed(2)+'</td><td>'+x.evidence_coverage_pct.toFixed(2)+'%</td><td>'+x.compliant_count+'</td><td>'+x.deviation_count+'</td><td>'+x.major_deviation_count+'</td><td>'+x.conflict_count+'</td><td>'+x.missing_evidence_count+'</td></tr>').join("")+'</tbody></table></div>'+(engineeringSummary.review_actions.length?'<p class="small"><b>Required review:</b> '+engineeringSummary.review_actions.map(x=>esc(x)).join(" · ")+'</p>':'');}$("review").innerHTML='<h2>'+esc(rfq.title)+'</h2><p class="muted">'+esc(rfq.category)+' · '+esc(rfq.mode)+' · Package '+rfq.package_id+'</p><div class="grid"><div class="card"><b>Requirements</b><div>'+rfq.requirements.length+'</div></div><div class="card"><b>Compliant</b><div>'+counts.COMPLIANT+'</div></div><div class="card"><b>Deviations</b><div>'+counts.DEVIATION+'</div></div><div class="card"><b>Evidence rows</b><div>'+ev.rows.length+'</div></div></div>'+summaryHtml+'<h3>Technical compliance matrix</h3><div style="overflow:auto"><table><thead><tr><th>Vendor</th><th>Parameter</th><th>Required</th><th>Offered</th><th>Status</th></tr></thead><tbody>'+rows.map(x=>'<tr><td>'+esc(x.vendor)+'</td><td>'+esc(x.parameter)+'</td><td>'+esc(x.required)+'</td><td>'+esc(x.offered||"—")+'</td><td>'+badge(x.status)+'</td></tr>').join("")+'</tbody></table></div><h3 style="margin-top:20px">Evidence register</h3><div style="overflow:auto"><table><thead><tr><th>Vendor</th><th>Field</th><th>Value</th><th>Status</th><th>Source</th></tr></thead><tbody>'+ev.rows.map(x=>'<tr><td>'+esc(x.vendor)+'</td><td>'+esc(x.field)+'</td><td>'+esc(x.value)+'</td><td>'+badge(x.claim_status)+'</td><td>'+esc(x.source||"—")+(x.page?" p."+x.page:"")+'</td></tr>').join("")+'</tbody></table></div>'}

function renderOffers(){$("claimOffer").innerHTML=offers.map(x=>'<option value="'+x.id+'">'+esc(x.vendor_name)+' · '+esc(x.technical_revision)+'</option>').join("")}
async function uploadBatch(){
  const id=$("package").value, files=[...$("batchFiles").files];
  const vendors=$("batchVendors").value.split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean);
  const revision=$("batchRevision").value.trim()||"R1";
  if(!id)return toast("Select a package first",true);
  if(!files.length)return toast("Select at least one quotation file",true);
  if(files.length>5)return toast("Upload a maximum of 5 quotation files",true);
  if(vendors.length!==files.length)return toast("Vendor names and files must match one-to-one",true);
  const entries=vendors.map(v=>({vendor_name:v,technical_revision:revision}));
  const form=new FormData();form.append("entries",JSON.stringify(entries));
  files.forEach(f=>form.append("files",f));
  try{
    await api("/packages/"+id+"/quotations/batch",{method:"POST",body:form});
    $("batchVendors").value="";$("batchFiles").value="";
    await loadReview();toast("Quotations uploaded and analyzed");
  }catch(e){toast(e.message,true)}
}
async function addOffer(){try{const id=$("package").value;await api("/packages/"+id+"/offers",{method:"POST",body:JSON.stringify({vendor_name:$("vendorName").value,technical_revision:$("revision").value,price:$("price").value||null,currency:$("currency").value||null})});await loadReview();toast("Offer added")}catch(e){toast(e.message,true)}}
async function addClaim(){try{const id=$("claimOffer").value;await api("/offers/"+id+"/claims",{method:"POST",body:JSON.stringify({parameter:$("claimParameter").value,value:$("claimValue").value,evidence:$("claimEvidence").value,claim_status:$("claimStatus").value})});await loadReview();toast("Claim saved")}catch(e){toast(e.message,true)}}
async function lockTechnical(){try{await api("/packages/"+$("package").value+"/technical-lock",{method:"POST"});await loadReview();toast("Technical bid locked")}catch(e){toast(e.message,true)}}
async function openCommercial(){try{await api("/packages/"+$("package").value+"/commercial-open",{method:"POST"});await loadReview();toast("Commercial evaluation opened")}catch(e){toast(e.message,true)}}
async function downloadReport(){try{const r=await api("/packages/"+$("package").value+"/report/markdown");const b=await r.blob();const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="rfq-review-package-"+$("package").value+".md";a.click();URL.revokeObjectURL(a.href)}catch(e){toast(e.message,true)}}
async function getRfq(){if(!currentPackage)return;const r=await api("/packages/"+$("package").value+"/rfq");const d=await r.json();alert(d.title+"\n\n"+d.requirements.map(x=>x.tag+": "+x.parameter+" = "+x.required_value).join("\n"))}
if(token)start();
</script>
</body>
</html>
"""


def web_app() -> HTMLResponse:
    """Return the dependency-free procurement review application."""
    return HTMLResponse(APP_HTML)
