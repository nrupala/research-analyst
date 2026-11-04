// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use strict";
var dom={form:document.getElementById("research-form"),ticker:document.getElementById("ticker"),reportType:document.getElementById("report-type"),timeframe:document.getElementById("timeframe"),btnSubmit:document.getElementById("btn-submit"),btnText:document.getElementById("btn-text"),btnSpinner:document.getElementById("btn-spinner"),status:document.getElementById("status"),statusText:document.getElementById("status-text"),progressBar:document.getElementById("progress-bar"),errorPanel:document.getElementById("error-panel"),errorMessage:document.getElementById("error-message"),btnRetry:document.getElementById("btn-retry"),results:document.getElementById("results"),metaBar:document.getElementById("meta-bar"),reportTabs:document.getElementById("report-tabs"),reportContent:document.getElementById("report-content"),btnAbout:document.getElementById("btn-about"),aboutModal:document.getElementById("about-modal"),btnCloseAbout:document.getElementById("btn-close-about"),modeSingle:document.getElementById("mode-single"),modeCompare:document.getElementById("mode-compare"),compareForm:document.getElementById("compare-form"),compareTickers:document.getElementById("compare-tickers"),compareTimeframe:document.getElementById("compare-timeframe"),compareError:document.getElementById("compare-error"),btnCompare:document.getElementById("btn-compare"),btnCompareText:document.getElementById("btn-compare-text"),btnCompareSpinner:document.getElementById("btn-compare-spinner"),btnGetApp:document.getElementById("btn-getapp"),getappModal:document.getElementById("getapp-modal"),btnCloseGetapp:document.getElementById("btn-close-getapp"),resolveCandidates:document.getElementById("resolve-candidates")};
var currentReports=[],activeTabIndex=0,isLoading=false,currentMode="single",activeTicker="";
var quantCache={ticker:"",data:null,error:"",discountRate:""};
// ---- v0.2.2: first-use disclaimer acknowledgment gate ----
function initDisclaimerGate() {
  const gate = document.getElementById('ra-disclaimer-gate');
  if (!gate) return; // shim-safe
  gate.hidden = true; // fail-safe default: stay hidden unless we explicitly decide to show
  
  try {
    fetch('/api/disclaimer').then(async (res) => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const {version, full} = await res.json();
      
      if (window.localStorage.getItem('ra_disclaimer_ack') === version) {
        return; // already acknowledged
      }
      
      const body = document.getElementById('ra-gate-body');
      if (body) body.textContent = full;
      
      gate.hidden = false;
      document.getElementById('ra-gate-accept')?.addEventListener('click', () => {
        try {
          window.localStorage.setItem('ra_disclaimer_ack', version);
          gate.hidden = true;
        } catch (e) {
          console.warn('Failed to persist disclaimer ack:', e);
        }
      });
    }).catch((e) => {
      console.warn('Disclaimer gate failed:', e);
    });
  } catch (e) {
    console.warn('Disclaimer gate initialization failed:', e);
  }
}

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
    var raw=dom.ticker.value.trim();
    if(!raw){dom.ticker.focus();return}
    // Name-like input (whitespace or lowercase letters) resolves first via /api/resolve.
    // Bare or suffixed tickers (AAPL, RELIANCE.NS) skip resolve and research directly.
    if(/\s/.test(raw)||/[a-z]/.test(raw)){return resolveThenResearch(raw)}
    var ticker=raw.toUpperCase();
    if(!/^[A-Z0-9.\-]{1,20}$/.test(ticker)){showError("Enter a valid ticker (e.g. AAPL or RELIANCE.NS) or a company name.");return}
    return runResearchTicker(ticker);
}
async function resolveThenResearch(query){
    currentMode="single";
    hideCandidates();setLoading(true);hideError();hideResults();
    showStatus("Looking up \""+query+"\"...",8);
    var res;
    try{
        var r=await fetch("/api/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query})});
        if(!r.ok){var e=await r.json().catch(function(){return{detail:r.statusText}});throw new Error(e.detail||"HTTP "+r.status)}
        res=await r.json();
    }catch(err){setLoading(false);showError("Lookup failed: "+(err.message||"could not reach the resolver."));return}
    if(res&&res.status==="resolved"&&res.resolved&&res.resolved.symbol){return runResearchTicker(res.resolved.symbol)}
    if(res&&res.status==="ambiguous"&&Array.isArray(res.candidates)&&res.candidates.length){setLoading(false);showCandidates(query,res.candidates);return}
    setLoading(false);showError((res&&res.note)?res.note:("No match for \""+query+"\". Try the ticker directly, e.g. RELIANCE.NS."))
}
async function runResearchTicker(ticker){
    currentMode="single";
    hideCandidates();setLoading(true);hideError();hideResults();
    currentReports=[];
    quantCache={ticker:"",data:null,error:"",discountRate:""};
    showStatus("Fetching data for "+ticker+"...",10);
    try{
        showStatus("Running analysis engines...",30);
        var resp=await fetch("/api/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ticker:ticker,report_type:dom.reportType.value||null,timeframe:dom.timeframe.value})});
        showStatus("Generating reports...",70);
        if(!resp.ok){var err=await resp.json().catch(function(){return{detail:resp.statusText}});throw new Error(err.detail||"HTTP "+resp.status)}
        var data=await resp.json();
        showStatus("Rendering...",90);
        currentReports=data.reports_markdown||[];
        activeTicker=(data.ticker||ticker||"").trim();
        renderMetaBar(data);
        renderTabs(data.reports||[]);
        await renderReport(0);
        showResults();
        showStatus("Complete",100);
        setTimeout(function(){dom.status.hidden=true},1500);
    }catch(err){showError(err.message||"Research pipeline failed.")}finally{setLoading(false)}
}
function hideCandidates(){if(dom.resolveCandidates){dom.resolveCandidates.hidden=true;dom.resolveCandidates.innerHTML=""}}
function showCandidates(query,candidates){
    var list=candidates.slice(0,5);
    if(!dom.resolveCandidates){
        var names=list.map(function(c){return c.symbol+" ("+(c.name||"")+")"}).join(", ");
        showError("Multiple matches for \""+query+"\": "+names+". Enter the exact ticker.");
        return
    }
    var box=dom.resolveCandidates;box.innerHTML="";
    var h=document.createElement("p");h.className="resolve-candidates__title";h.textContent="Multiple matches for \""+query+"\" \u2014 pick one:";box.appendChild(h);
    list.forEach(function(c){
        var b=document.createElement("button");b.type="button";b.className="resolve-candidate";
        var head=c.symbol+(c.name?" \u00b7 "+c.name:"");
        var tail=[];if(c.market_name||c.market)tail.push(c.market_name||c.market);if(c.currency)tail.push(c.currency);
        b.textContent=head+(tail.length?"  ("+tail.join(", ")+")":"");
        b.addEventListener("click",function(){runResearchTicker(c.symbol)});
        box.appendChild(b)
    });
    box.hidden=false
}

function setLoading(v){isLoading=v;dom.btnSubmit.disabled=v;dom.btnText.hidden=v;dom.btnSpinner.hidden=!v;if(v)dom.status.hidden=false}
function showStatus(t,pct){dom.status.hidden=false;dom.statusText.textContent=t;dom.progressBar.style.width=pct+"%"}
function showError(m){dom.errorPanel.hidden=false;dom.errorMessage.textContent=m;dom.status.hidden=true}
function hideError(){dom.errorPanel.hidden=true}
function hideResults(){dom.results.hidden=true}
function showResults(){dom.results.hidden=false}

function renderMetaBar(data){
    var m=data.metadata||{};
    var items=[["Ticker",data.ticker],["Company",data.company_name],["Type",data.security_type],["Reports",(data.reports||[]).length],["Time",(m.processing_time_seconds||0).toFixed(1)+"s"]];
    // Issue #66: reader-visible freshness state (never a silent stale cache).
    var fresh=m.sla_state||"fresh";
    var freshLabel=fresh+(m.data_as_of?(" · as of "+m.data_as_of):"");
    if(m.cache_hit){freshLabel+=" · cached"}
    items.push(["Freshness",freshLabel]);
    if(m.stale_warning){items.push(["⚠️ Stale",m.stale_warning])}
    dom.metaBar.innerHTML=items.map(function(p){return'<div class="meta-bar__item"><span class="meta-bar__label">'+esc(p[0])+':</span> '+esc(String(p[1]))+'</div>'}).join("")
    // Issue #74: enumerate every source — never a bare count.
    renderSourceList(m)
}

function renderSourceList(m){
    var recs=m.source_records||[];
    var names=(m.data_sources||[]);
    var list=recs.length?recs.map(function(r){return{name:r.name,url:r.url}}):names.map(function(n){return{name:n,url:null}});
    if(!list.length)return;
    var old=document.getElementById("sources-list");if(old)old.remove();
    var box=document.createElement("div");box.id="sources-list";box.className="sources-list";
    var h=document.createElement("h3");h.className="sources-list__title";h.textContent="Data Sources ("+list.length+")";box.appendChild(h);
    var ul=document.createElement("ol");ul.className="sources-list__items";
    list.forEach(function(s){
        var li=document.createElement("li");
        if(s.url){var a=document.createElement("a");a.href=s.url;a.target="_blank";a.rel="noopener";a.textContent=s.name;li.appendChild(a)}
        else{li.textContent=s.name}
        ul.appendChild(li)
    });
    box.appendChild(ul);
    dom.metaBar.after(box)
}

function renderTabs(reports){
    dom.reportTabs.innerHTML="";
    reports.forEach(function(r,i){
        var btn=document.createElement("button");
        btn.type="button";
        btn.id="report-tab-"+i;
        btn.className="tab"+(i===0?" tab--active":"");
        btn.setAttribute("role","tab");
        btn.setAttribute("aria-selected",i===0?"true":"false");
        btn.setAttribute("aria-controls","report-content");
        btn.tabIndex=i===0?0:-1;
        btn.textContent=humanReportType(r.report_type)||("Report "+(i+1));
        btn.addEventListener("click",function(){activateReportTab(i)});
        dom.reportTabs.appendChild(btn)
    });
    if(!reports.length){dom.reportTabs.style.display="none"}else{dom.reportTabs.style.display=""}
    if(reports.length){appendQuantTab();dom.reportContent.setAttribute("aria-labelledby","report-tab-0")}
}

// Index of the Quant tab within [role="tab"], or -1 when absent.
function quantTabIndex(){
    var tabs=dom.reportTabs.querySelectorAll('[role="tab"]');
    for(var i=0;i<tabs.length;i++){if(tabs[i].id==="report-tab-quant")return i}
    return -1;
}

// The Quant tab: same ARIA tab pattern as the report tabs, so the generic
// arrow-key navigation picks it up with no extra wiring.
function appendQuantTab(){
    var q=document.createElement("button");
    q.type="button";q.id="report-tab-quant";q.className="tab";
    q.setAttribute("role","tab");q.setAttribute("aria-selected","false");
    q.setAttribute("aria-controls","report-content");q.tabIndex=-1;
    q.textContent="Quant";
    q.addEventListener("click",function(){var i=quantTabIndex();if(i>=0)activateReportTab(i)});
    dom.reportTabs.appendChild(q);
}

// Activate one report tab: the visual class and the ARIA state stay in lockstep.
function activateReportTab(i){
    var tabs=dom.reportTabs.querySelectorAll('[role="tab"]');
    var isQuant=tabs[i]&&tabs[i].id==="report-tab-quant";
    tabs.forEach(function(t,j){
        var on=j===i;
        t.classList.toggle("tab--active",on);
        t.setAttribute("aria-selected",on?"true":"false");
        t.tabIndex=on?0:-1;
    });
    if(isQuant){renderQuantTab();return}
    renderReport(i);
}

// Keep the tabpanel labelled by whichever tab is active (and focusable).
function syncTabPanel(){
    dom.reportContent.setAttribute("tabindex","0");
    var tab=null;
    var qi=quantTabIndex();
    if(qi>=0&&activeTabIndex===qi){tab=dom.reportTabs.querySelector("#report-tab-quant")}
    tab=tab||dom.reportTabs.querySelector("#report-tab-"+activeTabIndex)||dom.reportTabs.querySelector("#report-tab-compare");
    if(tab){dom.reportContent.setAttribute("aria-labelledby",tab.id)}
}

function humanReportType(t){
    if(!t)return null;
    var map={comprehensive:"Comprehensive",tactical:"Tactical / Near-Term",long_term:"Long-Term",longterm:"Long-Term"};
    return map[t]||t.replace(/_/g," ").replace(/\b\w/g,function(c){return c.toUpperCase()});
}

function renderEmptyState(){
    dom.reportContent.innerHTML=
        '<div class="empty-state" role="status">'+
        '<div class="empty-state__icon" aria-hidden="true">\u2316</div>'+
        '<h3 class="empty-state__title">No report to display</h3>'+
        '<p class="empty-state__body">Enter a ticker above (e.g. AAPL, RELIANCE.NS, SPY) and run a report, or choose a different report type.</p>'+
        "</div>"
}

async function renderReport(idx){
    activeTabIndex=idx;
    if(!currentReports[idx]){renderEmptyState();return}
    dom.reportContent.innerHTML='<p class="status__text">Rendering report...</p>';
    var md=currentReports[idx]||"*No report content.*";
    var html=mdToHTML(md);
    dom.reportContent.innerHTML=html;
    syncTabPanel();
    await new Promise(function(r){requestAnimationFrame(r)});
    addExportToolbar();
    updateExportFooter()
}

// ---- Quant tab: fetches /api/research/quant and renders the engine phases
// as tables with formulas in captions/footnotes. Research/education only. ----
function qfmt(v,pct){
    if(v===null||v===undefined||!isFinite(v))return"n/a";
    var x=pct?v*100:v;
    return x.toFixed(2)+(pct?"%":"");
}
function qtable(head,rows,caption){
    var h='<div class="table-scroll"><table><caption>'+esc(caption)+'</caption><thead><tr>'+
        head.map(function(c){return"<th>"+esc(c)+"</th>"}).join("")+'</tr></thead><tbody>'+
        rows.map(function(r){return"<tr>"+r.map(function(c){return"<td>"+c+"</td>"}).join("")+"</tr>"}).join("")+
        "</tbody></table></div>";
    return h;
}
function qlist(items){
    return"<ul>"+items.map(function(i){return"<li>"+esc(i)+"</li>"}).join("")+"</ul>";
}

// Quant Lab Phase 1: chart panel scaffold. The figure div carries the
// accessible name (chart + default view); the view line under it names the
// default view and is rewritten by renderPlotlyCharts() as the reader
// zooms / toggles series (PLAYBOOK rule 31). The note line carries
// panel-missing, caption and not-available text. Tables remain the
// accessible artefact — panels are additive, never a replacement.
function qchartPanel(id,viewName,ariaLabel){
    return '<div class="quant-chart-panel"><div class="quant-chart" id="qchart-'+id+'" role="img" aria-label="'+esc(ariaLabel)+'"></div>'+
        '<p class="quant-chart-view" id="qchart-'+id+'-view">Default view: '+esc(viewName)+'</p>'+
        '<p class="quant-chart-note" id="qchart-'+id+'-note" hidden></p></div>';
}
function qchartChips(f){
    var chips=[];
    (f.altman_missing||[]).forEach(function(m){chips.push("Altman input missing: "+m)});
    (f.beneish_missing||[]).forEach(function(m){chips.push("Beneish input missing: "+m)});
    if(!chips.length)return"";
    return '<p class="quant-chart-chips">'+chips.map(function(c){return '<span class="quant-chip">'+esc(c)+"</span>"}).join(" ")+"</p>";
}
function qchartNotAvailable(a){
    var fields=[["debt_interest_coverage","interest coverage"],["incremental_roic_average","incremental ROIC"],
        ["operating_tax_rate_latest","operating tax rate"],["dividend_payout_on_earnings","dividend payout on earnings"],
        ["dividend_payout_on_fcf","dividend payout on FCF"],["debt_net_debt_to_ebit","net debt / EBIT"],
        ["buyback_shares_cagr","buyback shares CAGR"]];
    var missing=fields.filter(function(fd){return a[fd[0]]===null||a[fd[0]]===undefined}).map(function(fd){return fd[1]});
    if(!missing.length)return"";
    return '<p class="quant-chart-note">Not available: '+esc(missing.join(", "))+" — missing stays missing, never zero-filled.</p>";
}

async function renderQuantTab(){
    activeTabIndex=quantTabIndex();
    syncTabPanel();
    var t=(activeTicker||"").trim();
    if(!t){dom.reportContent.innerHTML='<p class="status__text">Run a report first, then open the Quant tab.</p>';return}
    if(quantCache.ticker===t&&quantCache.data){renderQuantData(quantCache.data);return}
    dom.reportContent.innerHTML='<p class="status__text">Computing quant engine...</p>';
    try{
        var url="/api/research/quant?ticker="+encodeURIComponent(t);
        if(quantCache.discountRate){url+="&discount_rate="+encodeURIComponent(quantCache.discountRate)}
        var resp=await fetch(url);
        if(!resp.ok){var err=await resp.json().catch(function(){return{detail:resp.statusText}});throw new Error(err.detail||"HTTP "+resp.status)}
        var data=await resp.json();
        quantCache={ticker:t,data:data,error:"",discountRate:quantCache.discountRate};
        renderQuantData(data);
    }catch(e){
        quantCache={ticker:t,data:null,error:e.message||"Quant request failed",discountRate:quantCache.discountRate};
        dom.reportContent.innerHTML='<p class="status__text">Quant engine unavailable: '+esc(quantCache.error)+'</p>';
    }
}

function renderQuantData(data){
    data=data||{};
    var cur=data.currency||"";
    var h='<h2>Quantitative Engine — '+esc(data.ticker||"")+'</h2>';
    h+='<p class="status__text">Research and education only — computed quantities from reported financial statements, not investment advice.</p>';
    h+='<p class="status__text">Periods: '+esc((data.periods||[]).join(", ")||"n/a")+'</p>';
    if(data.statements_source){h+='<p class="status__text">Statements: '+esc(data.statements_source)+'</p>'}
    // Discount-rate assumption (analyst input; implied-growth rows need it).
    h+='<form id="quant-dr-form" class="quant-dr"><label for="quant-dr">Discount rate (for implied-growth inversions, as a decimal):</label> '+
        '<input id="quant-dr" type="number" step="0.001" min="0" max="1" value="'+esc(quantCache.discountRate||"")+'" placeholder="e.g. 0.09"> '+
        '<button type="submit">Apply</button></form>';
    h+='<p class="quant-chart-note" id="qchart-vendor-note" hidden></p>';

    var t=data.trends||{};
    h+='<h3>Growth &amp; Margins</h3>'+qchartPanel("trends","Full statement window — margins and YoY growth, linear scale","Trends chart — full statement window, margins and YoY growth, linear scale")+
        '<p class="status__text">Revenue CAGR '+qfmt(t.revenue_cagr,true)+" · EPS CAGR "+qfmt(t.eps_cagr,true)+
        " · FCF CAGR "+qfmt(t.fcf_cagr,true)+" · latest YoY revenue growth "+qfmt(t.yoy_revenue_growth_latest,true)+
        " · latest gross margin "+qfmt(t.gross_margin_latest,true)+" · latest net margin "+qfmt(t.net_margin_latest,true)+".</p>"+
        qtable(["Metric","Value","Formula"],
        [["Revenue CAGR",qfmt(t.revenue_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Diluted EPS CAGR",qfmt(t.eps_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Free cash flow CAGR",qfmt(t.fcf_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Latest YoY revenue growth",qfmt(t.yoy_revenue_growth_latest,true),"rev_t / rev_t−1 − 1"],
         ["Latest gross margin",qfmt(t.gross_margin_latest,true),"gross_profit / revenue"],
         ["Latest net margin",qfmt(t.net_margin_latest,true),"net_income / revenue"]],
        "Compound growth and margins over the statement window.");

    var d=data.dupont||{},dl=d.latest||{},attr=d.attribution||{};
    var drows=(d.rows||[]).map(function(r){return[r.period,qfmt(r.roe,true),qfmt(r.net_margin,true),qfmt(r.asset_turnover),qfmt(r.leverage)]});
    h+='<h3>DuPont ROE Decomposition</h3>'+qchartPanel("dupont","Full statement window — ROE and its components, linear scale","DuPont chart — full statement window, ROE and its components, linear scale")+
        qchartPanel("dupont-waterfall","Latest period vs prior period — ROE attribution, linear scale","DuPont attribution waterfall — latest period vs prior period, linear scale")+
        qtable(["Period","ROE","Net margin","Asset turnover","Leverage"],drows,
        "ROE = net margin × asset turnover × leverage; averages are (current + prior) / 2.");
    if(attr.roe_change_pp!==null&&attr.roe_change_pp!==undefined){
        h+='<p class="status__text">ROE change: '+attr.roe_change_pp.toFixed(1)+'pp — margin '+
            (attr.margin_contribution_pp||0).toFixed(1)+'pp, turnover '+(attr.turnover_contribution_pp||0).toFixed(1)+
            'pp, leverage '+(attr.leverage_contribution_pp||0).toFixed(1)+'pp.</p>';
    }

    var f=data.forensics||{};
    h+='<h3>Forensic Screens</h3>';
    h+='<p class="status__text">Altman Z and Beneish M are statistical screens, not verdicts. A flag means “look closer”, never “this company will fail / is fraudulent”.</p>';
    h+=qchartPanel("forensics","Latest period — forensic screens against printed thresholds","Forensic screens chart — latest period, screens against printed thresholds")+qchartChips(f);
    h+=qtable(["Screen","Value","Reading"],
        [["Altman Z-score",qfmt(f.altman_z),(f.altman_zone||"n/a")+" — safe > 2.99, grey 1.81–2.99, distress < 1.81"],
         ["Beneish M-score",qfmt(f.beneish_m),f.beneish_flag===null||f.beneish_flag===undefined?"n/a":(f.beneish_flag?"FLAGGED (M > −1.78)":"not flagged")],
         ["Sloan accruals ratio",qfmt(f.sloan_accruals),"(net_income − operating_cash_flow) / total_assets"],
         ["Cash conversion",qfmt(f.cash_conversion,true),"operating_cash_flow / net_income"]],
        "Earnings-quality screens; zones and thresholds shown with each value.");

    var v=data.valuation||{};
    h+='<h3>Valuation Checks</h3>'+qchartPanel("valuation","Assumption grid — discount rate × perpetual growth, base cell marked","DCF sensitivity heatmap — discount rate by perpetual growth, base cell marked")+qtable(["Metric","Value","Formula"],
        [["Graham number",qfmt(v.graham_number)+" "+cur,"√(22.5 × EPS × BVPS)"],
         ["Lynch fair value (PEG = 1)",qfmt(v.lynch_fair_value)+" "+cur,"EPS × EPS-growth-%"],
         ["Implied explicit-stage growth",qfmt(v.implied_explicit_stage_growth,true),"reverse DCF bisection: constant g over 5 explicit years + Gordon terminal, solved for current EV"],
         ["Implied perpetual growth",qfmt(v.implied_perpetual_growth,true),"Gordon algebra: g = (EV×r − FCF) / (EV + FCF)"]],
        "Two distinct implied-growth models — never a bare “implied growth”.");

    var a=data.allocation||{};
    h+='<h3>Capital Allocation</h3>'+qchartPanel("allocation","Latest period — capital allocation ratios, linear scale","Capital allocation chart — latest period, allocation ratios, linear scale")+qchartNotAvailable(a)+qtable(["Metric","Value","Formula"],
        [["Average incremental ROIC",qfmt(a.incremental_roic_average,true),"ΔNOPAT / Δinvested capital (operating tax rate t = tax_expense / (ebit − interest_expense))"],
         ["Operating tax rate (latest)",qfmt(a.operating_tax_rate_latest,true),"t = tax_expense / (ebit − interest_expense)"],
         ["Dividend payout on earnings",qfmt(a.dividend_payout_on_earnings,true),"dividends_paid / net_income"],
         ["Dividend payout on FCF",qfmt(a.dividend_payout_on_fcf,true),"dividends_paid / free_cash_flow"],
         ["Net debt",qfmt(a.debt_net_debt_latest)+" "+cur,"total_debt − cash"],
         ["Net debt / EBIT",qfmt(a.debt_net_debt_to_ebit),"net_debt / ebit"],
         ["Buyback: shares CAGR",qfmt(a.buyback_shares_cagr,true),"share-count CAGR, first → last"]],
        "Incremental ROIC is n/a when tax/interest inputs are missing — missing stays missing.");

    if(data.missing_inputs&&data.missing_inputs.length){
        h+='<h3>Missing inputs</h3>'+qlist(data.missing_inputs);
    }
    if(data.assumptions&&data.assumptions.length){
        h+='<h3>Assumptions</h3>'+qlist(data.assumptions);
    }
    if(data.expected_value){
        h+=qchartPanel("expected","Scenario contributions — expected value marked","Scenario contributions chart — expected value marked");
    }
    if(data.expected_value&&data.expected_value.reason){
        h+='<p class="status__text">Expected value: '+esc(data.expected_value.reason)+'</p>';
    }
    dom.reportContent.innerHTML=h;
    var form=document.getElementById("quant-dr-form");
    if(form){form.addEventListener("submit",function(e){
        e.preventDefault();
        var inp=document.getElementById("quant-dr");
        quantCache.discountRate=inp&&inp.value?inp.value:"";
        quantCache.data=null;quantCache.ticker="";
        renderQuantTab();
    })}
    renderPlotlyCharts(data);
}

// Phase F: the report body's charts AND diagrams are server-rendered static
// SVG — nothing to instantiate there. renderMermaidDiagrams stays a named
// no-op for export/print stripping hooks.
function renderMermaidDiagrams(){
    return
}

// ---- Quant Lab Phase 1: in-house chart layer over the quant payload ----
// Our engine computes, these builders emit the figure spec, and the
// vendored Plotly.js partial bundle (ui/vendor/, MIT, same-origin — never
// a CDN, never Plotly's hosted anything) renders it as SVG. Builders are
// pure payload → spec functions: they never mutate the payload, never
// invent a value, and pass nulls through as null — no zero-fill, no
// forward-fill, no bridging (connectgaps is false on every scatter and
// rangebreaks appear nowhere). The tables remain the artefact; a figure
// that cannot be built or rendered degrades to a named note, panel by
// panel, and the tables stand exactly as before.
var QUANT_BRASS = "#b08d2f";
var QUANT_INK = "#0f172a";
var QUANT_INK_2 = "#334155";
var QUANT_INK_3 = "#64748b";
var QUANT_INK_4 = "#94a3b8";
var AIMLDS_INK_BRASS_TEMPLATE = {
    layout: {
        font: {color: QUANT_INK, size: 12},
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
        colorway: [QUANT_BRASS, QUANT_INK_2, QUANT_INK_3, QUANT_INK_4, QUANT_INK],
        xaxis: {gridcolor: "#e2e8f0", linecolor: QUANT_INK, zerolinecolor: QUANT_INK_4},
        yaxis: {gridcolor: "#e2e8f0", linecolor: QUANT_INK, zerolinecolor: QUANT_INK_4},
        hovermode: "x unified"
    },
    data: {
        scatter: [{line: {width: 2}, marker: {size: 6}}],
        bar: [{marker: {line: {width: 0}}}]
    }
};
function qchartLayout(extra){
    var L = {template: AIMLDS_INK_BRASS_TEMPLATE, margin: {l: 58, r: 18, t: 12, b: 42},
        hovermode: "x unified", showlegend: true,
        legend: {orientation: "h", x: 0, y: 1.15}};
    if(extra){for(var k in extra){L[k] = extra[k]}}
    return L;
}
function qchartConfig(){
    // No toImage: a current-view PNG export is excluded in Phase 1 (spec
    // §7) — export stays with the app's own report export, where the
    // tables are the artefact.
    return {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["toImage"]};
}
function qprov(periods, unit, source){
    return (periods || []).map(function(p){ return [p, unit, source] });
}
function qstmtSource(data){
    return data.statements_source || "reported financial statements";
}

function buildTrendsFigure(data){
    var t = data.trends || {};
    var periods = data.periods || [];
    var ms = t.margin_series || {}, ys = t.yoy_series || {};
    var gross = ms.gross || [], net = ms.net || [], yoy = ys.revenue || [];
    var hasValue = [gross, net, yoy].some(function(arr){
        return arr.some(function(val){ return val !== null && val !== undefined });
    });
    if(!periods.length || !hasValue){
        return {figure: null, note: "Trend series unavailable — no per-period values in payload; the table below is complete."};
    }
    var src = qstmtSource(data);
    var traces = [
        {type: "bar", name: "YoY revenue growth", x: periods, y: yoy,
            marker: {color: QUANT_INK_3},
            customdata: qprov(periods, "YoY growth (fraction)", src),
            hovertemplate: "%{y:.1%} · %{customdata[1]} · %{customdata[2]}<extra>YoY revenue growth</extra>"},
        {type: "scatter", mode: "lines+markers", name: "Gross margin", x: periods, y: gross,
            connectgaps: false, line: {color: QUANT_BRASS, width: 2.5},
            customdata: qprov(periods, "margin (fraction of revenue)", src),
            hovertemplate: "%{y:.1%} · %{customdata[1]} · %{customdata[2]}<extra>Gross margin</extra>"},
        {type: "scatter", mode: "lines+markers", name: "Net margin", x: periods, y: net,
            connectgaps: false, line: {color: QUANT_INK_2},
            customdata: qprov(periods, "margin (fraction of revenue)", src),
            hovertemplate: "%{y:.1%} · %{customdata[1]} · %{customdata[2]}<extra>Net margin</extra>"}
    ];
    var layout = qchartLayout({
        xaxis: {type: "category", showspikes: true, spikemode: "across", spikecolor: QUANT_INK_4, title: {text: "Fiscal period"}},
        yaxis: {tickformat: ".0%", title: {text: "Fraction of revenue / growth"}}
    });
    return {figure: {data: traces, layout: layout, config: qchartConfig()}, note: null};
}

function buildDupontFigure(data){
    var d = data.dupont || {};
    var rows = d.rows || [];
    if(!rows.length){
        return {figure: null, note: "DuPont panel unavailable — decomposition not in payload; the table below is complete."};
    }
    var periods = rows.map(function(r){ return r.period });
    var col = function(key){ return rows.map(function(r){ return (r[key] === null || r[key] === undefined) ? null : r[key] }) };
    var src = "computed by RA";
    var traces = [
        {type: "scatter", mode: "lines+markers", name: "ROE", x: periods, y: col("roe"), connectgaps: false,
            line: {color: QUANT_BRASS, width: 2.5}, customdata: qprov(periods, "ROE (fraction)", src),
            hovertemplate: "%{y:.1%} · %{customdata[1]} · %{customdata[2]}<extra>ROE</extra>"},
        {type: "scatter", mode: "lines+markers", name: "Net margin", x: periods, y: col("net_margin"), connectgaps: false,
            line: {color: QUANT_INK_2}, customdata: qprov(periods, "margin (fraction)", src),
            hovertemplate: "%{y:.1%} · %{customdata[1]} · %{customdata[2]}<extra>Net margin</extra>"},
        {type: "scatter", mode: "lines+markers", name: "Asset turnover", x: periods, y: col("asset_turnover"), connectgaps: false, yaxis: "y2",
            line: {color: QUANT_INK_3}, customdata: qprov(periods, "turnover (× revenue / avg assets)", src),
            hovertemplate: "%{y:.2f} · %{customdata[1]} · %{customdata[2]}<extra>Asset turnover</extra>"},
        {type: "scatter", mode: "lines+markers", name: "Leverage", x: periods, y: col("leverage"), connectgaps: false, yaxis: "y2",
            line: {color: QUANT_INK_4}, customdata: qprov(periods, "leverage (× avg assets / avg equity)", src),
            hovertemplate: "%{y:.2f} · %{customdata[1]} · %{customdata[2]}<extra>Leverage</extra>"}
    ];
    var layout = qchartLayout({
        xaxis: {type: "category", showspikes: true, spikemode: "across", spikecolor: QUANT_INK_4, title: {text: "Fiscal period"}},
        yaxis: {tickformat: ".0%", title: {text: "ROE / margin"}},
        yaxis2: {overlaying: "y", side: "right", title: {text: "Turnover / leverage (×)"}, gridcolor: "rgba(0,0,0,0)"}
    });
    return {figure: {data: traces, layout: layout, config: qchartConfig()}, note: null};
}

function buildDupontWaterfall(data){
    var d = data.dupont || {};
    var attr = d.attribution || {};
    var rows = d.rows || [];
    var latest = d.latest || (rows.length ? rows[rows.length - 1] : {});
    var latestRoe = (latest.roe === null || latest.roe === undefined) ? null : latest.roe;
    var parts = [attr.margin_contribution_pp, attr.turnover_contribution_pp, attr.leverage_contribution_pp];
    var complete = attr.roe_change_pp !== null && attr.roe_change_pp !== undefined && latestRoe !== null &&
        parts.every(function(p){ return p !== null && p !== undefined });
    if(!complete){
        // Conditional by design (§3.2): no figure and no note — the table
        // area already carries the state.
        return {figure: null, note: null};
    }
    var start = latestRoe - attr.roe_change_pp / 100;
    var m = parts[0] / 100, tu = parts[1] / 100, lv = parts[2] / 100;
    var pp = function(x){ return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "pp" };
    var periodLabel = latest.period || "latest";
    var labels = ["Prior ROE", "Margin", "Turnover", "Leverage", "Latest ROE"];
    var trace = {type: "waterfall", name: "ROE attribution", orientation: "v",
        x: labels, y: [start, m, tu, lv, latestRoe],
        measure: ["absolute", "relative", "relative", "relative", "total"],
        text: [qfmt(start, true), pp(m), pp(tu), pp(lv), qfmt(latestRoe, true)], textposition: "outside",
        connector: {line: {color: QUANT_INK_4}},
        increasing: {marker: {color: QUANT_BRASS}},
        decreasing: {marker: {color: QUANT_INK_3}},
        totals: {marker: {color: QUANT_INK}},
        customdata: labels.map(function(){ return [periodLabel, "ROE (fraction)", "computed by RA"] }),
        hovertemplate: "%{text} · %{customdata[1]} · %{customdata[2]}<extra>%{x}</extra>"};
    var layout = qchartLayout({showlegend: false, hovermode: "closest",
        xaxis: {type: "category", title: {text: "Attribution step"}},
        yaxis: {tickformat: ".0%", title: {text: "ROE"}}});
    return {figure: {data: [trace], layout: layout, config: qchartConfig()}, note: null};
}
function buildForensicsFigure(data){
    var f = data.forensics || {};
    var periods = data.periods || [];
    var latestPeriod = periods.length ? periods[periods.length - 1] : "latest";
    var defs = [
        {key: "altman_z", label: "Altman Z-score", fmt: function(v){ return v.toFixed(2) }},
        {key: "beneish_m", label: "Beneish M-score", fmt: function(v){ return v.toFixed(2) }},
        {key: "sloan_accruals", label: "Sloan accruals ratio", fmt: function(v){ return v.toFixed(3) }},
        {key: "cash_conversion", label: "Cash conversion", fmt: function(v){ return v.toFixed(2) }}
    ];
    var present = defs.filter(function(df){ return f[df.key] !== null && f[df.key] !== undefined });
    var missing = defs.filter(function(df){ return f[df.key] === null || f[df.key] === undefined })
        .map(function(df){ return df.label });
    if(!present.length){
        return {figure: null, note: "Forensic screens unavailable — screens not in payload; the table below is complete."};
    }
    // One panel, one row per screen, each row on its own axis: the four
    // scales are incompatible, and the threshold geometry (bands, flag
    // line, reference line) belongs to each screen's own axis. Bars and
    // printed thresholds — no gauge dials (a verdict needle is a verdict).
    var traces = [], shapes = [], annotations = [];
    var layout = qchartLayout({showlegend: false, hovermode: "closest",
        height: 120 * present.length + 30,
        grid: {rows: present.length, cols: 1, pattern: "independent", roworder: "top to bottom"}});
    present.forEach(function(df, i){
        var n = i + 1, xs = n === 1 ? "x" : "x" + n, ys = n === 1 ? "y" : "y" + n;
        var val = f[df.key];
        traces.push({type: "bar", orientation: "h", name: df.label, x: [val], y: [""],
            xaxis: xs, yaxis: ys, marker: {color: QUANT_BRASS},
            text: [df.fmt(val)], textposition: "outside",
            customdata: [[latestPeriod, df.label, "computed by RA"]],
            hovertemplate: "%{text} · %{customdata[1]} · %{customdata[2]}<extra></extra>"});
        var xa = {title: {text: df.label}, zerolinecolor: QUANT_INK_4};
        if(df.key === "altman_z"){
            var hi = Math.max(6, val * 1.15);
            xa.range = [0, hi];
            [[0, 1.81, "rgba(185,28,28,0.10)", "distress < 1.81"],
             [1.81, 2.99, "rgba(100,116,139,0.12)", "grey 1.81–2.99"],
             [2.99, hi, "rgba(176,141,47,0.14)", "safe > 2.99"]].forEach(function(b){
                shapes.push({type: "rect", xref: xs, yref: ys + " domain", x0: b[0], x1: b[1], y0: 0, y1: 1,
                    fillcolor: b[2], line: {width: 0}, layer: "below"});
                annotations.push({x: (b[0] + b[1]) / 2, y: 0.06, xref: xs, yref: ys + " domain",
                    text: b[3], showarrow: false, font: {size: 10, color: QUANT_INK_2}});
            });
        }
        if(df.key === "beneish_m"){
            xa.range = [Math.min(-4, val - 0.4), Math.max(0.4, val + 0.4)];
            shapes.push({type: "line", xref: xs, yref: ys + " domain", x0: -1.78, x1: -1.78, y0: 0, y1: 1,
                line: {color: "#b91c1c", width: 2, dash: "dash"}});
            annotations.push({x: -1.78, y: 1, xref: xs, yref: ys + " domain", yanchor: "bottom",
                text: "flag threshold (M > −1.78)", showarrow: false, xanchor: "left",
                font: {size: 10, color: "#b91c1c"}});
        }
        if(df.key === "sloan_accruals"){
            var s = Math.max(0.1, Math.abs(val) * 1.4);
            xa.range = [-s, s];
            xa.zerolinewidth = 2;
            xa.zerolinecolor = QUANT_INK;
        }
        if(df.key === "cash_conversion"){
            xa.range = [0, Math.max(2, val * 1.2)];
            shapes.push({type: "line", xref: xs, yref: ys + " domain", x0: 1, x1: 1, y0: 0, y1: 1,
                line: {color: QUANT_INK_2, width: 2, dash: "dash"}});
            annotations.push({x: 1, y: 1, xref: xs, yref: ys + " domain", yanchor: "bottom",
                text: "cash = earnings", showarrow: false, xanchor: "left",
                font: {size: 10, color: QUANT_INK_2}});
        }
        layout[n === 1 ? "xaxis" : "xaxis" + n] = xa;
        layout[n === 1 ? "yaxis" : "yaxis" + n] = {visible: false};
    });
    layout.shapes = shapes;
    layout.annotations = annotations;
    var note = missing.length
        ? "Not available: " + missing.join(", ") + " — see Missing inputs below; missing stays missing."
        : null;
    return {figure: {data: traces, layout: layout, config: qchartConfig()}, note: note};
}

function qnearestIndex(values, target){
    var best = 0, bd = Infinity;
    values.forEach(function(v, i){ var d = Math.abs(v - target); if(d < bd){ bd = d; best = i } });
    return best;
}
function qaxisStep(values){
    var diffs = [];
    for(var i = 1; i < values.length; i++){ var d = Math.abs(values[i] - values[i - 1]); if(d > 0) diffs.push(d) }
    return diffs.length ? Math.min.apply(null, diffs) : 0.005;
}

function buildValuationHeatmap(data){
    var v = data.valuation || {};
    var s = v.sensitivity;
    if(!s || !s.values || !s.values.length || !s.rows || !s.cols){
        return {figure: null, note: "Sensitivity grid unavailable — grid not in payload; the table below is complete."};
    }
    var cur = data.currency || "";
    var rows = s.rows.values, cols = s.cols.values, base = s.base || {};
    var text = s.values.map(function(row){
        return row.map(function(c){ return (c === null || c === undefined) ? "n/a" : c.toFixed(2) });
    });
    var trace = {type: "heatmap", z: s.values, x: cols, y: rows, text: text, texttemplate: "%{text}",
        colorscale: [[0, "#f1f5f9"], [1, QUANT_BRASS]], showscale: true,
        colorbar: {title: {text: (cur ? cur + " " : "") + "/ share"}},
        customdata: rows.map(function(){ return cols.map(function(){ return ["DCF sensitivity grid", "model value per share", "computed by RA"] }) }),
        hovertemplate: "discount %{y:.2%} · perpetual growth %{x:.2%} → %{z:.2f} " + cur + "/share · %{customdata[2]}<extra></extra>"};
    var shapes = [], annotations = [];
    if(base.discount_rate !== null && base.discount_rate !== undefined &&
       base.perpetual_growth !== null && base.perpetual_growth !== undefined){
        var bi = qnearestIndex(rows, base.discount_rate), bj = qnearestIndex(cols, base.perpetual_growth);
        var rs = qaxisStep(rows), cs = qaxisStep(cols);
        shapes.push({type: "rect", xref: "x", yref: "y",
            x0: cols[bj] - cs / 2, x1: cols[bj] + cs / 2, y0: rows[bi] - rs / 2, y1: rows[bi] + rs / 2,
            line: {color: QUANT_INK, width: 2}, fillcolor: "rgba(0,0,0,0)"});
        annotations.push({x: cols[bj], y: rows[bi], xref: "x", yref: "y", text: "assumption used",
            showarrow: true, arrowhead: 2, ax: 0, ay: -30, font: {size: 11, color: QUANT_INK}});
    }
    var layout = qchartLayout({showlegend: false, hovermode: "closest", shapes: shapes, annotations: annotations,
        xaxis: {tickformat: ".1%", title: {text: "Perpetual growth (terminal assumption)"}},
        yaxis: {tickformat: ".1%", title: {text: "Discount rate"}}});
    var caption = "Computed model output over assumed inputs — not observed market data.";
    if(base.explicit_growth !== null && base.explicit_growth !== undefined){
        caption += " Explicit-stage growth held at the implied value " + qfmt(base.explicit_growth, true) + " over 5 years.";
    }
    (data.assumptions || []).filter(function(x){ return /discount rate/i.test(x) }).forEach(function(x){
        caption += " " + x;
    });
    return {figure: {data: [trace], layout: layout, config: qchartConfig()}, note: null, caption: caption};
}
function buildExpectedFigure(data){
    var ev = data.expected_value || {};
    if(ev.expected === null || ev.expected === undefined || !ev.contributions || !ev.contributions.length){
        // Spec §10 resolution (2026-11-03): the live contributions payload
        // is scenario value × probability per scenario — it carries no
        // low/high outputs, so a tornado would require fabricating them.
        // Phase 1 renders the contributions themselves; the tornado waits
        // for a payload that carries tornado rows. When expected is null
        // there is no figure and the payload's reason line stands alone.
        return {figure: null, note: null};
    }
    var cur = data.currency || "";
    var labels = ev.contributions.map(function(c){ return String(c.label) }).reverse();
    var vals = ev.contributions.map(function(c){ return c.contribution }).reverse();
    var trace = {type: "bar", orientation: "h", name: "Scenario contribution",
        y: labels, x: vals,
        marker: {color: vals.map(function(x){ return x >= 0 ? QUANT_BRASS : QUANT_INK_3 })},
        customdata: labels.map(function(l){ return [l, "contribution (" + (cur || "value") + ")", "computed by RA"] }),
        hovertemplate: "%{customdata[0]}: %{x:.2f} · %{customdata[1]} · %{customdata[2]}<extra></extra>"};
    var layout = qchartLayout({showlegend: false, hovermode: "closest",
        shapes: [{type: "line", xref: "x", yref: "paper", x0: ev.expected, x1: ev.expected, y0: 0, y1: 1,
            line: {color: QUANT_INK, width: 2, dash: "dash"}}],
        annotations: [{x: ev.expected, y: 1, xref: "x", yref: "paper", yanchor: "bottom",
            text: "expected value " + ev.expected.toFixed(2), showarrow: false,
            font: {size: 11, color: QUANT_INK}}],
        xaxis: {title: {text: "Contribution to expected value" + (cur ? " (" + cur + ")" : "")}},
        yaxis: {title: {text: "Scenario"}}});
    return {figure: {data: [trace], layout: layout, config: qchartConfig()}, note: null};
}

function buildAllocationFigure(data){
    var a = data.allocation || {};
    var periods = data.periods || [];
    var latestPeriod = periods.length ? periods[periods.length - 1] : "latest";
    var src = qstmtSource(data);
    var fields = [
        {key: "dividend_payout_on_earnings", label: "Dividend payout on earnings", pct: true, prov: src},
        {key: "dividend_payout_on_fcf", label: "Dividend payout on FCF", pct: true, prov: src},
        {key: "debt_net_debt_to_ebit", label: "Net debt / EBIT", pct: false, prov: src},
        {key: "debt_interest_coverage", label: "Interest coverage", pct: false, prov: src},
        {key: "buyback_shares_cagr", label: "Buyback: shares CAGR", pct: true, prov: src},
        {key: "incremental_roic_average", label: "Avg incremental ROIC", pct: true, prov: "computed by RA"},
        {key: "operating_tax_rate_latest", label: "Operating tax rate (latest)", pct: true, prov: "computed by RA"}
    ];
    var present = fields.filter(function(fd){ return a[fd.key] !== null && a[fd.key] !== undefined });
    if(!present.length){
        return {figure: null, note: "Allocation panel unavailable — ratios not in payload; the table below is complete."};
    }
    var ordered = present.slice().reverse();
    var trace = {type: "bar", orientation: "h", name: "Capital allocation (latest)",
        y: ordered.map(function(fd){ return fd.label }),
        x: ordered.map(function(fd){ return a[fd.key] }),
        marker: {color: QUANT_BRASS},
        text: ordered.map(function(fd){ return qfmt(a[fd.key], fd.pct) }), textposition: "outside",
        customdata: ordered.map(function(fd){ return [latestPeriod, fd.pct ? "ratio (fraction)" : "ratio (×)", fd.prov] }),
        hovertemplate: "%{y}: %{text} · %{customdata[1]} · %{customdata[2]}<extra></extra>"};
    var layout = qchartLayout({showlegend: false, hovermode: "closest",
        xaxis: {title: {text: "Ratio (latest period)"}}});
    return {figure: {data: [trace], layout: layout, config: qchartConfig()}, note: null};
}

var QUANT_PANEL_VIEWS = {
    "trends": "Full statement window — margins and YoY growth, linear scale",
    "dupont": "Full statement window — ROE and its components, linear scale",
    "dupont-waterfall": "Latest period vs prior period — ROE attribution, linear scale",
    "forensics": "Latest period — forensic screens against printed thresholds",
    "valuation": "Assumption grid — discount rate × perpetual growth, base cell marked",
    "allocation": "Latest period — capital allocation ratios, linear scale",
    "expected": "Scenario contributions — expected value marked"
};
function buildQuantChartSpecs(data){
    data = data || {};
    var builders = [
        ["trends", buildTrendsFigure], ["dupont", buildDupontFigure],
        ["dupont-waterfall", buildDupontWaterfall], ["forensics", buildForensicsFigure],
        ["valuation", buildValuationHeatmap], ["allocation", buildAllocationFigure],
        ["expected", buildExpectedFigure]
    ];
    return builders.map(function(pair){
        var built = pair[1](data);
        return {id: pair[0], viewName: QUANT_PANEL_VIEWS[pair[0]], templateName: "aimlds_ink_brass",
            periods: data.periods || [], figure: built.figure, note: built.note || null,
            caption: built.caption || null};
    });
}

// The period/scale line under each figure (PLAYBOOK rule 31): the default
// view by name, updated from the live graph state when the reader zooms
// or hides a series — a changed view is always labelled as changed.
function quantViewLine(spec, gd){
    var hidden = [];
    ((gd && gd.data) || []).forEach(function(tr){
        if(tr.visible === "legendonly" || tr.visible === false) hidden.push(tr.name);
    });
    var win = null;
    var lay = (gd && gd.layout) || {};
    if(lay.xaxis && lay.xaxis.range && spec.periods && spec.periods.length){
        // Category axis: category i occupies [i − 0.5, i + 0.5], so the
        // visible index span is the range shifted by half a category.
        var r0 = Math.max(0, Math.floor(lay.xaxis.range[0] + 0.5));
        var r1 = Math.min(spec.periods.length - 1, Math.ceil(lay.xaxis.range[1] - 0.5));
        if(r0 > 0 || r1 < spec.periods.length - 1) win = spec.periods[r0] + " – " + spec.periods[r1];
    }
    if(!win && !hidden.length) return "Default view: " + spec.viewName;
    var s = "View: " + (win ? "window " + win : "full window");
    if(hidden.length) s += " · hidden: " + hidden.join(", ");
    return s + " · (default: " + spec.viewName + ")";
}

function renderPlotlyCharts(data){
    var specs = buildQuantChartSpecs(data || {});
    var vendorEl = document.getElementById("qchart-vendor-note");
    var P = (typeof window !== "undefined" && window.Plotly) ? window.Plotly : null;
    if(!P){
        // Vendor-failed (§1.1): every table stands exactly as today; one
        // named line says charts are unavailable. No retry, no fallback.
        var anyFigure = false;
        specs.forEach(function(spec){
            var el = document.getElementById("qchart-" + spec.id);
            var viewEl = document.getElementById("qchart-" + spec.id + "-view");
            if(el) el.hidden = true;
            if(viewEl) viewEl.hidden = true;
            if(spec.figure) anyFigure = true;
            if(!spec.figure && spec.note){
                var n = document.getElementById("qchart-" + spec.id + "-note");
                if(n){ n.textContent = spec.note; n.hidden = false }
            }
        });
        if(anyFigure && vendorEl){
            vendorEl.textContent = "Charts unavailable — data tables below are complete.";
            vendorEl.hidden = false;
        }
        return;
    }
    if(vendorEl) vendorEl.hidden = true;
    specs.forEach(function(spec){
        var el = document.getElementById("qchart-" + spec.id);
        var noteEl = document.getElementById("qchart-" + spec.id + "-note");
        var viewEl = document.getElementById("qchart-" + spec.id + "-view");
        if(!el) return;
        if(!spec.figure){
            el.hidden = true;
            if(viewEl) viewEl.hidden = true;
            if(noteEl && spec.note){ noteEl.textContent = spec.note; noteEl.hidden = false }
            return;
        }
        var caption = spec.caption || spec.note;
        if(noteEl && caption){ noteEl.textContent = caption; noteEl.hidden = false }
        var degrade = function(){
            el.hidden = true;
            if(viewEl) viewEl.hidden = true;
            if(noteEl){
                noteEl.textContent = "Chart failed to render — data tables below are complete.";
                noteEl.hidden = false;
            }
        };
        try{
            var p = P.newPlot(el, spec.figure.data, spec.figure.layout, spec.figure.config);
            var attach = function(gd){
                if(gd && typeof gd.on === "function"){
                    var upd = function(){ if(viewEl) viewEl.textContent = quantViewLine(spec, gd) };
                    gd.on("plotly_relayout", upd);
                    gd.on("plotly_restyle", upd);
                }
            };
            if(p && typeof p.then === "function"){ p.then(attach).catch(degrade) }
            else attach(el);
        }catch(e){ degrade() }
    });
}

// ---- Phase G: on-demand interactive chart view. Plotly comes from the
// vendored same-origin partial bundle (ui/vendor/, loaded with the page);
// ensurePlotly only remains as the resolver for callers that predate the
// vendored load, and its fallback path points at the same vendored file —
// no CDN anywhere (Quant Lab Phase 1 removed the last external script). ----
var raPlotlyPromise = null;
function ensurePlotly(){
    if (typeof window.Plotly !== "undefined") return Promise.resolve(window.Plotly);
    if (raPlotlyPromise) return raPlotlyPromise;
    raPlotlyPromise = new Promise(function(resolve, reject){
        var s = document.createElement("script");
        s.src = "/vendor/plotly-2.32.0.min.js";
        s.onload = function(){ resolve(window.Plotly); };
        s.onerror = function(){ reject(new Error("Plotly failed to load")); };
        document.head.appendChild(s);
    });
    return raPlotlyPromise;
}

function buildInteractiveFigure(data){
    var fig = {traces: [], layout: {}};
    var sym = data.currency === "INR" ? "\u20B9" : data.currency === "EUR" ? "\u20AC" : "$";
    if (data.type === "financial_trends") {
        fig.traces.push({x: data.periods, y: data.revenue_b, name: "Revenue (" + sym + "B)", type: "bar", yaxis: "y"});
        for (var k in data.margins_pct) {
            fig.traces.push({x: data.periods, y: data.margins_pct[k], name: k + " margin %", type: "scatter", mode: "lines+markers", yaxis: "y2"});
        }
        fig.layout = {title: data.ticker + " — Revenue & Margin Trends", yaxis: {title: "Revenue (" + sym + "B)"}, yaxis2: {title: "Margin %", overlaying: "y", side: "right"}};
    } else if (data.type === "scenario") {
        var labels = data.scenarios.map(function(s){ return s.label; });
        fig.traces.push({y: labels, x: data.scenarios.map(function(s){ return s.high - s.low; }), base: data.scenarios.map(function(s){ return s.low; }), type: "bar", orientation: "h", text: data.scenarios.map(function(s){ return sym + s.low.toLocaleString() + " \u2013 " + sym + s.high.toLocaleString(); }), textposition: "inside"});
        fig.layout = {title: "Scenario-Based Valuation Range", xaxis: {title: "Price (" + sym + ")"}, barmode: "overlay"};
    } else if (data.type === "peers") {
        var w = 0.25, x = data.tickers.map(function(_, i){ return i; });
        fig.traces.push({x: x.map(function(v){ return v - w; }), y: data.gross_margin_pct, name: "Gross margin %", type: "bar"});
        fig.traces.push({x: x, y: data.op_margin_pct, name: "Operating margin %", type: "bar"});
        fig.traces.push({x: x.map(function(v){ return v + w; }), y: data.roe_pct, name: "ROE %", type: "bar"});
        fig.layout = {title: "Peer Comparison", xaxis: {tickvals: x, ticktext: data.tickers}, barmode: "group"};
    } else if (data.type === "risks") {
        fig.traces.push({x: data.risks.map(function(r){ return r.probability; }), y: data.risks.map(function(r){ return r.impact; }), text: data.risks.map(function(r){ return r.title; }), mode: "markers+text", type: "scatter", textposition: "top center", marker: {size: data.risks.map(function(r){ return 120 + r.probability * r.impact * 30; }), opacity: 0.7}});
        fig.layout = {title: "Risk Matrix", xaxis: {tickvals: [1,2,3], ticktext: ["Low","Medium","High"]}, yaxis: {tickvals: [1,2,3,4], ticktext: ["Low","Medium","High","Critical"]}};
    } else if (data.type === "dividends") {
        fig.traces.push({x: data.years, y: data.dps, name: "DPS (" + sym + ")", type: "bar"});
        fig.layout = {title: data.ticker + " — Dividend Per Share by Year"};
    }
    fig.layout.height = 420;
    return fig;
}

function openInteractiveView(button){
    var encoded = button.getAttribute("data-interactive");
    if (!encoded) return;
    var data;
    try { data = JSON.parse(atob(encoded)); } catch(e) { alert("Interactive data unavailable."); return; }
    ensurePlotly().then(function(Plotly){
        var overlay = document.createElement("div");
        overlay.className = "chart-modal";
        overlay.innerHTML = '<div class="chart-modal__box"><button type="button" class="chart-modal__close" aria-label="Close">&times;</button><div class="chart-modal__plot"></div></div>';
        overlay.querySelector(".chart-modal__close").addEventListener("click", function(){ overlay.remove(); });
        document.body.appendChild(overlay);
        try {
            Plotly.newPlot(overlay.querySelector(".chart-modal__plot"), buildInteractiveFigure(data).traces, buildInteractiveFigure(data).layout, {displaylogo: false, responsive: true});
        } catch(e) {
            overlay.querySelector(".chart-modal__plot").textContent = "Could not render interactive view.";
        }
    }).catch(function(e){
        alert("Interactive view requires the Plotly library (failed to load).");
    });
}

document.addEventListener("click", function(e){
    var b = e.target.closest ? e.target.closest(".chart-interactive") : null;
    if (b) openInteractiveView(b);
});

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
    clone.querySelectorAll(".modebar,.modebar-container,script").forEach(function(n){n.remove()});
    clone.querySelectorAll("details.report-section").forEach(function(d){d.open=true});
    var cssText="";
    try{var r=await fetch("/style.css");if(r.ok)cssText=await r.text()}catch(e){}
    var doc="<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"+
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"+
        "<title>"+esc(tickerSlug())+" Research Report</title>\n"+
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
    btn.id="report-tab-compare";
    btn.setAttribute("aria-selected","true");
    btn.setAttribute("aria-controls","report-content");
    btn.tabIndex=0;
    btn.textContent=analyzed.length?"Comparison — "+analyzed.join(" vs "):"Comparison";
    dom.reportTabs.appendChild(btn);
    dom.reportContent.setAttribute("aria-labelledby","report-tab-compare");
}

function mdToHTML(md){
    var h=md;
    var preserved=[];
    h=h.replace(/<div class="(?:plotly-chart-data|mermaid-data|chart-svg)"[\s\S]*?<\/div>/g,function(match){preserved.push(match);return"___PRESERVED_"+(preserved.length-1)+"___"});
    h=h.replace(/<button type="button" class="chart-interactive"[\s\S]*?<\/button>/g,function(match){preserved.push(match);return"___PRESERVED_"+(preserved.length-1)+"___"});
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
    h=h.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,function(_,txt,url){return'<a href="'+url+'" target="_blank" rel="noopener noreferrer">'+txt+'</a>'});
    h=h.replace(/^(\|.+\|)\n(\|[-|: ]+\|)\n((?:\|.+\|\n?)*)/gm,function(_,hdr,sep,body){var ths=hdr.split("|").filter(function(c){return c.trim()}).map(function(c){return"<th>"+c.trim()+"</th>"}).join("");var rows=body.trim().split("\n").map(function(row){var tds=row.split("|").filter(function(c){return c.trim()}).map(function(c){return"<td>"+c.trim()+"</td>"}).join("");return"<tr>"+tds+"</tr>"}).join("");return'<div class="table-scroll"><table><thead><tr>'+ths+'</tr></thead><tbody>'+rows+'</tbody></table></div>'});
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
    // Phase C: collapsible report sections — wrap every <h2> block in a
    // <details class="report-section" open> so analysts can collapse steps.
    // Open by default (nothing hidden on first load); beforeprint + export
    // force-open so print/PDF never drops content.
    h=h.replace(/<h2>([^<]*)<\/h2>([\s\S]*?)(?=<h2>|$)/g,function(_,head,body){
      return '<details class="report-section" open><summary><h2>'+head+'</h2></summary><div class="report-section__body">'+body+'</div></details>';
    });
    return h
}

function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML}

// Bootstrap the first-use disclaimer gate one tick after load, so it runs after
// synchronous page init (and, in tests, after the fetch mock is installed).
// typeof guards keep it shim-safe; the gate itself fails open on any error.
if (typeof requestAnimationFrame === 'function') requestAnimationFrame(initDisclaimerGate);
else if (typeof setTimeout === 'function') setTimeout(initDisclaimerGate, 0);
else initDisclaimerGate();

// Tablist arrow-key navigation, wired once (bonus: tabs already work with
// click + Tab; Left/Right move between tabs per the ARIA tabs pattern).
(function(){
    if(typeof document==="undefined"||!dom.reportTabs||dom.reportTabs.getAttribute("data-arrowkeys"))return;
    dom.reportTabs.setAttribute("data-arrowkeys","true");
    dom.reportTabs.addEventListener("keydown",function(e){
        if(e.key!=="ArrowRight"&&e.key!=="ArrowLeft")return;
        var tabs=Array.prototype.slice.call(dom.reportTabs.querySelectorAll('[role="tab"]'));
        if(tabs.length<2)return;
        e.preventDefault();
        var cur=tabs.indexOf(document.activeElement);
        var next=(cur+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;
        tabs[next].focus();
        activateReportTab(next);
    });
})();

// Print: open every collapsible section so the paper/PDF copy is complete.
if (typeof window !== 'undefined' && window.addEventListener) {
    window.addEventListener('beforeprint', function () {
        if (typeof document !== 'undefined' && document.querySelectorAll) {
            document.querySelectorAll('details.report-section').forEach(function (d) { d.open = true; });
        }
    });
}