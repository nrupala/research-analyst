"use strict";
var dom={form:document.getElementById("research-form"),ticker:document.getElementById("ticker"),reportType:document.getElementById("report-type"),timeframe:document.getElementById("timeframe"),btnSubmit:document.getElementById("btn-submit"),btnText:document.getElementById("btn-text"),btnSpinner:document.getElementById("btn-spinner"),status:document.getElementById("status"),statusText:document.getElementById("status-text"),progressBar:document.getElementById("progress-bar"),errorPanel:document.getElementById("error-panel"),errorMessage:document.getElementById("error-message"),btnRetry:document.getElementById("btn-retry"),results:document.getElementById("results"),metaBar:document.getElementById("meta-bar"),reportTabs:document.getElementById("report-tabs"),reportContent:document.getElementById("report-content"),btnAbout:document.getElementById("btn-about"),aboutModal:document.getElementById("about-modal"),btnCloseAbout:document.getElementById("btn-close-about"),modeSingle:document.getElementById("mode-single"),modeCompare:document.getElementById("mode-compare"),compareForm:document.getElementById("compare-form"),compareTickers:document.getElementById("compare-tickers"),compareTimeframe:document.getElementById("compare-timeframe"),compareError:document.getElementById("compare-error"),btnCompare:document.getElementById("btn-compare"),btnCompareText:document.getElementById("btn-compare-text"),btnCompareSpinner:document.getElementById("btn-compare-spinner"),btnGetApp:document.getElementById("btn-getapp"),getappModal:document.getElementById("getapp-modal"),btnCloseGetapp:document.getElementById("btn-close-getapp")};
var currentReports=[],activeTabIndex=0,isLoading=false,currentMode="single";
document.addEventListener("DOMContentLoaded",function(){if(typeof mermaid!=="undefined"){mermaid.initialize({startOnLoad:false,theme:"neutral",securityLevel:"strict",flowchart:{useMaxWidth:true,htmlLabels:true},sequence:{useMaxWidth:true},gantt:{useMaxWidth:true}})}});
dom.form.addEventListener("submit",function(e){e.preventDefault();if(!isLoading)runResearch()});
dom.btnRetry.addEventListener("click",function(){if(!isLoading)runResearch()});
dom.btnAbout.addEventListener("click",function(){dom.aboutModal.showModal()});
dom.btnCloseAbout.addEventListener("click",function(){dom.aboutModal.close()});
dom.aboutModal.addEventListener("click",function(e){if(e.target===dom.aboutModal)dom.aboutModal.close()});
if(dom.btnGetApp)dom.btnGetApp.addEventListener("click",function(){if(dom.getappModal&&typeof dom.getappModal.showModal==="function")dom.getappModal.showModal()});
if(dom.btnCloseGetapp)dom.btnCloseGetapp.addEventListener("click",function(){dom.getappModal.close()});
if(dom.getappModal)dom.getappModal.addEventListener("click",function(e){if(e.target===dom.getappModal)dom.getappModal.close()});

// ---- v0.2.0 comparative: mode toggle (Single vs Compare) ----
function setMode(mode){
    currentMode=mode==="compare"?"compare":"single";
    var compare=currentMode==="compare";
    if(dom.form)dom.form.hidden=compare;
    if(dom.compareForm)dom.compareForm.hidden=!compare;
    if(dom.modeSingle){dom.modeSingle.classList.toggle("mode-btn--active",!compare);dom.modeSingle.setAttribute("aria-selected",compare?"false":"true")}
    if(dom.modeCompare){dom.modeCompare.classList.toggle("mode-btn--active",compare);dom.modeCompare.setAttribute("aria-selected",compare?"true":"false")}
    hideError();hideResults();hideCompareError()
}
if(dom.modeSingle)dom.modeSingle.addEventListener("click",function(){setMode("single")});
if(dom.modeCompare)dom.modeCompare.addEventListener("click",function(){setMode("compare")});
if(dom.compareForm)dom.compareForm.addEventListener("submit",function(e){e.preventDefault();if(!isLoading)runCompare()});

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
    currentMode="single";
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
    addExportToolbar();
    updateExportFooter()
}

function renderPlotlyCharts(){
    if(typeof Plotly==="undefined")return;
    var isMobile=window.matchMedia&&window.matchMedia("(max-width: 640px)").matches;
    var divs=document.querySelectorAll(".plotly-chart-data");
    divs.forEach(function(div,i){
        var raw=div.getAttribute("data-plotly");
        if(!raw)return;
        try{
            var data=JSON.parse(raw);
            var layout=data.layout||{};
            // Fluid charts/maps: fill the column and let Plotly own sizing rather
            // than honoring any fixed width/height the server baked in.
            layout.autosize=true;delete layout.width;
            if(!layout.height)layout.height=isMobile?300:420;
            layout.margin=layout.margin||(isMobile?{l:40,r:12,t:30,b:34}:{l:52,r:18,t:38,b:42});
            layout.font=layout.font||{family:"Inter, system-ui, -apple-system, sans-serif"};
            if(isMobile&&layout.legend)layout.legend.orientation="h";
            var chartId="plotly-r-"+Date.now()+"-"+i;
            var chartDiv=document.createElement("div");
            chartDiv.id=chartId;chartDiv.className="ra-chart";chartDiv.style.width="100%";chartDiv.style.marginBottom="1rem";
            div.parentNode.insertBefore(chartDiv,div);
            var config={responsive:true,displayModeBar:true,displaylogo:false,scrollZoom:false,modeBarButtonsToRemove:["lasso2d","select2d"],toImageButtonOptions:{format:"png",scale:2}};
            Plotly.newPlot(chartId,data.traces,layout,config);
            // Container width can change without a window resize (tab switches,
            // orientation, dialogs). ResizeObserver keeps charts/maps crisp and fitted.
            if(typeof ResizeObserver!=="undefined"){var ro=new ResizeObserver(function(){try{Plotly.Plots.resize(chartDiv)}catch(e){}});ro.observe(chartDiv)}
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

// ---- v0.2.0 export: MD / HTML / PDF (client-side, no server) ----
var BMC_URL="https://buymeacoffee.com/nrupalakolt";
var PREPARED_URL="https://ra.devinfo.dev";

function reportDateStr(){
    try{return new Date().toLocaleDateString("en-US",{year:"numeric",month:"long",day:"numeric"})}
    catch(e){return new Date().toISOString().slice(0,10)}
}
function tickerSlug(){
    if(currentMode==="compare"){
        var ts=parseTickers(dom.compareTickers?dom.compareTickers.value:"");
        return(ts.join("-").replace(/[^A-Z0-9.\-]/g,""))||"comparison"
    }
    return(dom.ticker.value.trim().toUpperCase()||"report").replace(/[^A-Z0-9.\-]/g,"")
}
function reportFileBase(){return tickerSlug()+(currentMode==="compare"?"_comparative_report":"_research_report")}

function footerMarkdown(){
    return"\n\n---\n\nReport prepared on "+PREPARED_URL+" \u00b7 "+reportDateStr()+"\n\n[Buy Me a Coffee]("+BMC_URL+")\n"
}
function footerHTML(){
    return'<div class="export-footer">'+
        '<div>Report prepared on <a href="'+PREPARED_URL+'">'+PREPARED_URL+'</a> \u00b7 '+esc(reportDateStr())+'</div>'+
        '<div><a href="'+BMC_URL+'" target="_blank" rel="noopener noreferrer">Buy Me a Coffee</a></div>'+
    '</div>'
}
function updateExportFooter(){
    var ef=document.getElementById("export-footer");
    if(ef)ef.innerHTML=footerHTML()
}
function downloadBlob(content,type,filename){
    var blob=new Blob([content],{type:type});
    var url=URL.createObjectURL(blob);
    var a=document.createElement("a");a.href=url;a.download=filename;
    document.body.appendChild(a);a.click();document.body.removeChild(a);
    setTimeout(function(){URL.revokeObjectURL(url)},1500)
}
function exportMD(){
    var md=currentReports[activeTabIndex];
    if(!md)return;
    downloadBlob(md+footerMarkdown(),"text/markdown;charset=utf-8",reportFileBase()+".md")
}
async function exportHTML(){
    var src=dom.reportContent;
    if(!src)return;
    var clone=src.cloneNode(true);
    clone.querySelectorAll(".plotly-chart-data,.mermaid-data,.modebar,.modebar-container,script").forEach(function(n){n.remove()});
    var cssText="";
    try{var r=await fetch("/style.css");if(r.ok)cssText=await r.text()}catch(e){}
    var doc="<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"+
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"+
        "<title>"+esc(tickerSlug())+" Research Report</title>\n"+
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n"+
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap\">\n"+
        "<style>\n"+cssText+"\nbody{background:#fff;color:#0f172a;max-width:960px;margin:0 auto;padding:24px;}\n.report{border:none;box-shadow:none;padding:0;}\n</style>\n"+
        "</head>\n<body>\n<div class=\"report\">"+clone.innerHTML+"</div>\n"+footerHTML()+"\n</body>\n</html>\n";
    downloadBlob(doc,"text/html;charset=utf-8",reportFileBase()+".html")
}
function exportPDF(){
    updateExportFooter();
    setTimeout(function(){window.print()},60)
}
function addExportToolbar(){
    var existing=document.getElementById("export-toolbar");
    if(existing)existing.remove();
    if(!currentReports[activeTabIndex])return;
    var bar=document.createElement("div");
    bar.id="export-toolbar";bar.className="export-toolbar";
    var defs=[["Download MD",exportMD],["Download HTML",exportHTML],["Download PDF",exportPDF]];
    defs.forEach(function(d){
        var b=document.createElement("button");
        b.type="button";b.className="btn btn--secondary";b.textContent=d[0];
        b.addEventListener("click",d[1]);
        bar.appendChild(b)
    });
    dom.reportContent.parentNode.insertBefore(bar,dom.reportContent)
}

// ---- v0.2.0 comparative: multi-ticker input, validation, /api/compare ----
var COMPARE_MIN=2,COMPARE_MAX=5;

function parseTickers(raw){
    var seen={},out=[];
    (raw||"").split(/[\s,]+/).forEach(function(t){
        var u=t.trim().toUpperCase();
        if(u&&!Object.prototype.hasOwnProperty.call(seen,u)){seen[u]=1;out.push(u)}
    });
    return out
}
function showCompareError(msg){if(dom.compareError){dom.compareError.hidden=false;dom.compareError.textContent=msg}}
function hideCompareError(){if(dom.compareError){dom.compareError.hidden=true;dom.compareError.textContent=""}}
function setCompareLoading(v){
    isLoading=v;
    if(dom.btnCompare)dom.btnCompare.disabled=v;
    if(dom.btnCompareText)dom.btnCompareText.hidden=v;
    if(dom.btnCompareSpinner)dom.btnCompareSpinner.hidden=!v;
    if(v)dom.status.hidden=false
}
// The server markdown is a standalone artifact ending with its own
// "Report prepared on ..." line. Strip that trailer so the shared UI export
// footer (footerMarkdown/footerHTML) is appended exactly once, identical to
// the single-ticker exports. Disclaimer + compliance lines are kept.
function stripPreparedOnTrailer(md){
    if(!md)return"";
    var lines=md.split("\n");
    while(lines.length){
        var last=lines[lines.length-1].trim();
        if(last===""||last==="---"||/^\*?report prepared on/i.test(last)){lines.pop()}
        else break
    }
    return lines.join("\n")
}
async function runCompare(){
    hideCompareError();
    var tickers=parseTickers(dom.compareTickers?dom.compareTickers.value:"");
    if(tickers.length<COMPARE_MIN||tickers.length>COMPARE_MAX){
        showCompareError("Enter between "+COMPARE_MIN+" and "+COMPARE_MAX+" distinct tickers (you entered "+tickers.length+").");
        return
    }
    var bad=tickers.filter(function(t){return!/^[A-Z0-9.\-]{1,10}$/.test(t)});
    if(bad.length){showCompareError("Invalid ticker(s): "+bad.join(", ")+".");return}
    currentMode="compare";
    setCompareLoading(true);hideError();hideResults();
    currentReports=[];activeTabIndex=0;
    var tf=(dom.compareTimeframe&&dom.compareTimeframe.value)||"1Y";
    showStatus("Comparing "+tickers.join(", ")+"...",15);
    try{
        showStatus("Running per-ticker analysis...",40);
        var resp=await fetch("/api/compare",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tickers:tickers,timeframe:tf})});
        showStatus("Ranking & aligning metrics...",75);
        if(!resp.ok){var err=await resp.json().catch(function(){return{detail:resp.statusText}});throw new Error(err.detail||"HTTP "+resp.status)}
        var data=await resp.json();
        showStatus("Rendering comparison...",90);
        currentReports=[stripPreparedOnTrailer(data.report_markdown||"")];
        renderCompareMetaBar(data);
        renderCompareTabs(data);
        await renderReport(0);
        showResults();
        showStatus("Complete",100);
        setTimeout(function(){dom.status.hidden=true},1500)
    }catch(err){showError(err.message||"Comparative pipeline failed.")}finally{setCompareLoading(false)}
}
function renderCompareMetaBar(data){
    data=data||{};
    var rep=data.report||{};
    var analyzed=data.tickers||rep.tickers||[];
    var requested=rep.requested_tickers||analyzed;
    var errs=rep.errors||[];
    var items=[["Mode","Comparison"],["Tickers",analyzed.join(", ")||"none"],["Count",analyzed.length]];
    if(requested.length!==analyzed.length)items.push(["Requested",requested.join(", ")]);
    if(errs.length)items.push(["Excluded",errs.length]);
    dom.metaBar.innerHTML=items.map(function(p){return'<div class="meta-bar__item"><span class="meta-bar__label">'+esc(p[0])+':</span> '+esc(String(p[1]))+'</div>'}).join("")
}
function renderCompareTabs(data){
    dom.reportTabs.innerHTML="";
    data=data||{};
    var analyzed=data.tickers||(data.report&&data.report.tickers)||[];
    var btn=document.createElement("button");
    btn.className="tab tab--active";btn.type="button";btn.setAttribute("role","tab");
    btn.textContent=analyzed.length?"Comparison — "+analyzed.join(" vs "):"Comparison";
    dom.reportTabs.appendChild(btn)
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
