"use strict";
var dom={form:document.getElementById("research-form"),ticker:document.getElementById("ticker"),reportType:document.getElementById("report-type"),timeframe:document.getElementById("timeframe"),btnSubmit:document.getElementById("btn-submit"),btnText:document.getElementById("btn-text"),btnSpinner:document.getElementById("btn-spinner"),status:document.getElementById("status"),statusText:document.getElementById("status-text"),progressBar:document.getElementById("progress-bar"),errorPanel:document.getElementById("error-panel"),errorMessage:document.getElementById("error-message"),btnRetry:document.getElementById("btn-retry"),results:document.getElementById("results"),metaBar:document.getElementById("meta-bar"),reportTabs:document.getElementById("report-tabs"),reportContent:document.getElementById("report-content"),btnAbout:document.getElementById("btn-about"),aboutModal:document.getElementById("about-modal"),btnCloseAbout:document.getElementById("btn-close-about")};
var currentReports=[],activeTabIndex=0,isLoading=false;
document.addEventListener("DOMContentLoaded",function(){if(typeof mermaid!=="undefined"){mermaid.initialize({startOnLoad:false,theme:"neutral",securityLevel:"strict"})}});
dom.form.addEventListener("submit",function(e){e.preventDefault();if(!isLoading)runResearch()});
dom.btnRetry.addEventListener("click",function(){if(!isLoading)runResearch()});
dom.btnAbout.addEventListener("click",function(){dom.aboutModal.showModal()});
dom.btnCloseAbout.addEventListener("click",function(){dom.aboutModal.close()});
dom.aboutModal.addEventListener("click",function(e){if(e.target===dom.aboutModal)dom.aboutModal.close()});

// Contact dialog + form (vanilla, mailto-based)
if(dom.btnContact)dom.btnContact.addEventListener("click",function(){if(dom.contactModal&&typeof dom.contactModal.showModal==="function"){dom.contactModal.showModal()}else{var el=document.getElementById("contact-section");if(el)el.scrollIntoView({behavior:"smooth"})}});
if(dom.btnCloseContact)dom.btnCloseContact.addEventListener("click",function(){dom.contactModal.close()});
if(dom.contactModal)dom.contactModal.addEventListener("click",function(e){if(e.target===dom.contactModal)dom.contactModal.close()});
if(dom.contactForm)dom.contactForm.addEventListener("submit",function(e){
    e.preventDefault();
    var name=document.getElementById("contact-name").value.trim();
    var email=document.getElementById("contact-email").value.trim();
    var msg=document.getElementById("contact-message").value.trim();
    if(!name||!email||!msg)return;
    var subject=encodeURIComponent("ra.devinfo.dev contact from "+name);
    var body=encodeURIComponent("From: "+name+" <"+email+">\n\n"+msg);
    window.location.href="mailto:nrupalakolkar@gmail.com?subject="+subject+"&body="+body;
});

async function runResearch(){
    var ticker=dom.ticker.value.trim().toUpperCase();
    if(!ticker){dom.ticker.focus();return}
    if(!/^[A-Z0-9.\-]{1,10}$/.test(ticker)){showError("Invalid ticker.");return}
    setLoading(true);hideError();hideResults();
    currentReports=[];
    showStatus("Fetching data for "+ticker+"...",10);
    try{
        showStatus("Running analysis engines...",30);
        var resp=await fetch("/api/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ticker:ticker,report_type:dom.reportType.value||null,timeframe:dom.timeframe.value})});
        showStatus("Generating reports...",70);
        if(!resp.ok){var err=await resp.json().catch(function(){return{detail:resp.statusText}});throw new Error(err.detail||"HTTP "+resp.status)}
        var data=await resp.json();
        showStatus("Rendering...",90);
        currentReports=data.reports_markdown||[];
        renderMetaBar(data);
        renderTabs(data.reports||[]);
        await renderReport(0);
        showResults();
        showStatus("Complete",100);
        setTimeout(function(){dom.status.hidden=true},1500);
    }catch(err){showError(err.message||"Research pipeline failed.")}finally{setLoading(false)}
}

function setLoading(v){isLoading=v;dom.btnSubmit.disabled=v;dom.btnText.hidden=v;dom.btnSpinner.hidden=!v;if(v)dom.status.hidden=false}
function showStatus(t,pct){dom.status.hidden=false;dom.statusText.textContent=t;dom.progressBar.style.width=pct+"%"}
function showError(m){dom.errorPanel.hidden=false;dom.errorMessage.textContent=m;dom.status.hidden=true}
function hideError(){dom.errorPanel.hidden=true}
function hideResults(){dom.results.hidden=true}
function showResults(){dom.results.hidden=false}

function renderMetaBar(data){
    var m=data.metadata||{};
    var items=[["Ticker",data.ticker],["Company",data.company_name],["Type",data.security_type],["Reports",(data.reports||[]).length],["Time",(m.processing_time_seconds||0).toFixed(1)+"s"],["Sources",(m.data_sources||[]).length]];
    dom.metaBar.innerHTML=items.map(function(p){return'<div class="meta-bar__item"><span class="meta-bar__label">'+esc(p[0])+':</span> '+esc(String(p[1]))+'</div>'}).join("")
}

function renderTabs(reports){
    dom.reportTabs.innerHTML="";
    reports.forEach(function(r,i){
        var btn=document.createElement("button");
        btn.className="tab"+(i===0?" tab--active":"");
        btn.setAttribute("role","tab");
        btn.textContent=r.report_type||"Report "+(i+1);
        btn.addEventListener("click",function(){
            document.querySelectorAll(".tab").forEach(function(t){t.classList.remove("tab--active")});
            btn.classList.add("tab--active");
            renderReport(i)
        });
        dom.reportTabs.appendChild(btn)
    })
}

async function renderReport(idx){
    activeTabIndex=idx;
    dom.reportContent.innerHTML='<p class="status__text">Rendering report...</p>';
    var md=currentReports[idx]||"*No report content.*";
    var html=mdToHTML(md);
    dom.reportContent.innerHTML=html;
    await new Promise(function(r){requestAnimationFrame(r)});
    renderPlotlyCharts();
    await renderMermaidDiagrams();
    addDownloadButton()
}

function renderPlotlyCharts(){
    if(typeof Plotly==="undefined")return;
    var divs=document.querySelectorAll(".plotly-chart-data");
    divs.forEach(function(div,i){
        var raw=div.getAttribute("data-plotly");
        if(!raw)return;
        try{
            var data=JSON.parse(raw);
            var chartId="plotly-r-"+Date.now()+"-"+i;
            var chartDiv=document.createElement("div");
            chartDiv.id=chartId;chartDiv.style.width="100%";chartDiv.style.marginBottom="1rem";
            div.parentNode.insertBefore(chartDiv,div);
            Plotly.newPlot(chartId,data.traces,data.layout,{responsive:true,displayModeBar:true});
            div.style.display="none"
        }catch(e){console.warn("Plotly render failed:",e);div.textContent="Chart could not be rendered.";div.style.color="#94a3b8";div.style.display="block"}
    })
}

async function renderMermaidDiagrams(){
    if(typeof mermaid==="undefined")return;
    var divs=document.querySelectorAll(".mermaid-data");
    for(var i=0;i<divs.length;i++){
        var el=divs[i];
        var encoded=el.getAttribute("data-mermaid");
        if(!encoded)continue;
        try{
            var syntax=atob(encoded);
            var id="mm-r-"+Date.now()+"-"+i;
            var result=await mermaid.render(id,syntax);
            var rendered=document.createElement("div");
            rendered.className="mermaid-diagram";
            rendered.innerHTML=result.svg;
            el.parentNode.insertBefore(rendered,el.nextSibling);
            el.style.display="none"
        }catch(e){
            console.warn("Mermaid render failed:",e);
            try{el.textContent=atob(encoded)}catch(x){}
            el.style.display="block";el.style.whiteSpace="pre";el.style.fontFamily="monospace";
            el.style.fontSize="0.8rem";el.style.color="#64748b";el.style.padding="1rem";
            el.style.background="#f1f5f9";el.style.borderRadius="8px"
        }
    }
}

function addDownloadButton(){
    var existing=document.getElementById("btn-download-report");
    if(existing)existing.remove();
    var md=currentReports[activeTabIndex];
    if(!md)return;
    var btn=document.createElement("button");
    btn.id="btn-download-report";btn.className="btn btn--secondary";
    btn.textContent="Download Report (.md)";btn.style.marginBottom="1rem";
    btn.addEventListener("click",function(){
        var blob=new Blob([md],{type:"text/markdown;charset=utf-8"});
        var url=URL.createObjectURL(blob);
        var a=document.createElement("a");a.href=url;
        a.download=(dom.ticker.value.trim().toUpperCase()||"report")+"_research_report.md";
        document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url)
    });
    dom.reportContent.parentNode.insertBefore(btn,dom.reportContent)
}

function mdToHTML(md){
    var h=md;
    var preserved=[];
    h=h.replace(/<div class="(?:plotly-chart-data|mermaid-data)"[^>]*>(?:<\/div>)?/g,function(match){preserved.push(match);return"___PRESERVED_"+(preserved.length-1)+"___"});
    h=h.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    h=h.replace(/```(\w*)\n([\s\S]*?)```/g,function(_,lang,code){return'<pre><code class="language-'+(lang||"text")+'">'+code.trim()+"</code></pre>"});
    h=h.replace(/^#### (.+)$/gm,"<h4>$1</h4>");
    h=h.replace(/^### (.+)$/gm,"<h3>$1</h3>");
    h=h.replace(/^## (.+)$/gm,"<h2>$1</h2>");
    h=h.replace(/^# (.+)$/gm,"<h1>$1</h1>");
    h=h.replace(/^---$/gm,"<hr>");
    h=h.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
    h=h.replace(/\*(.+?)\*/g,"<em>$1</em>");
    h=h.replace(/`([^`]+)`/g,"<code>$1</code>");
    h=h.replace(/^(\|.+\|)\n(\|[-|: ]+\|)\n((?:\|.+\|\n?)*)/gm,function(_,hdr,sep,body){var ths=hdr.split("|").filter(function(c){return c.trim()}).map(function(c){return"<th>"+c.trim()+"</th>"}).join("");var rows=body.trim().split("\n").map(function(row){var tds=row.split("|").filter(function(c){return c.trim()}).map(function(c){return"<td>"+c.trim()+"</td>"}).join("");return"<tr>"+tds+"</tr>"}).join("");return"<table><thead><tr>"+ths+"</tr></thead><tbody>"+rows+"</tbody></table>"});
    h=h.replace(/^- (.+)$/gm,"<li>$1</li>");
    h=h.replace(/(<li>[\s\S]*?<\/li>(?:\n|$))+/g,function(m){return"<ul>"+m+"</ul>"});
    h=h.replace(/\n\n+/g,"</p><p>");h="<p>"+h+"</p>";
    h=h.replace(/<p>\s*<\/p>/g,"");
    h=h.replace(/<p>(<h[1-4]>)/g,"$1");h=h.replace(/(<\/h[1-4]>)<\/p>/g,"$1");
    h=h.replace(/<p>(<hr>)<\/p>/g,"$1");
    h=h.replace(/<p>(<table>)/g,"$1");h=h.replace(/(<\/table>)<\/p>/g,"$1");
    h=h.replace(/<p>(<ul>)/g,"$1");h=h.replace(/(<\/ul>)<\/p>/g,"$1");
    h=h.replace(/<p>(<pre>)/g,"$1");h=h.replace(/(<\/pre>)<\/p>/g,"$1");
    h=h.replace(/<p>(<div)/g,"$1");h=h.replace(/(<\/div>)<\/p>/g,"$1");
    for(var i=0;i<preserved.length;i++){h=h.replace("___PRESERVED_"+i+"___",preserved[i])}
    return h
}

function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML}
