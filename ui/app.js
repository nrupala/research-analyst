// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
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

    var t=data.trends||{};
    h+='<h3>Growth &amp; Margins</h3>'+qtable(["Metric","Value","Formula"],
        [["Revenue CAGR",qfmt(t.revenue_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Diluted EPS CAGR",qfmt(t.eps_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Free cash flow CAGR",qfmt(t.fcf_cagr,true),"(last/first)^(1/periods) − 1"],
         ["Latest YoY revenue growth",qfmt(t.yoy_revenue_growth_latest,true),"rev_t / rev_t−1 − 1"],
         ["Latest gross margin",qfmt(t.gross_margin_latest,true),"gross_profit / revenue"],
         ["Latest net margin",qfmt(t.net_margin_latest,true),"net_income / revenue"]],
        "Compound growth and margins over the statement window.");

    var d=data.dupont||{},dl=d.latest||{},attr=d.attribution||{};
    var drows=(d.rows||[]).map(function(r){return[r.period,qfmt(r.roe,true),qfmt(r.net_margin,true),qfmt(r.asset_turnover),qfmt(r.leverage)]});
    h+='<h3>DuPont ROE Decomposition</h3>'+qtable(["Period","ROE","Net margin","Asset turnover","Leverage"],drows,
        "ROE = net margin × asset turnover × leverage; averages are (current + prior) / 2.");
    if(attr.roe_change_pp!==null&&attr.roe_change_pp!==undefined){
        h+='<p class="status__text">ROE change: '+attr.roe_change_pp.toFixed(1)+'pp — margin '+
            (attr.margin_contribution_pp||0).toFixed(1)+'pp, turnover '+(attr.turnover_contribution_pp||0).toFixed(1)+
            'pp, leverage '+(attr.leverage_contribution_pp||0).toFixed(1)+'pp.</p>';
    }

    var f=data.forensics||{};
    h+='<h3>Forensic Screens</h3>';
    h+='<p class="status__text">Altman Z and Beneish M are statistical screens, not verdicts. A flag means “look closer”, never “this company will fail / is fraudulent”.</p>';
    h+=qtable(["Screen","Value","Reading"],
        [["Altman Z-score",qfmt(f.altman_z),(f.altman_zone||"n/a")+" — safe > 2.99, grey 1.81–2.99, distress < 1.81"],
         ["Beneish M-score",qfmt(f.beneish_m),f.beneish_flag===null||f.beneish_flag===undefined?"n/a":(f.beneish_flag?"FLAGGED (M > −1.78)":"not flagged")],
         ["Sloan accruals ratio",qfmt(f.sloan_accruals),"(net_income − operating_cash_flow) / total_assets"],
         ["Cash conversion",qfmt(f.cash_conversion,true),"operating_cash_flow / net_income"]],
        "Earnings-quality screens; zones and thresholds shown with each value.");

    var v=data.valuation||{};
    h+='<h3>Valuation Checks</h3>'+qtable(["Metric","Value","Formula"],
        [["Graham number",qfmt(v.graham_number)+" "+cur,"√(22.5 × EPS × BVPS)"],
         ["Lynch fair value (PEG = 1)",qfmt(v.lynch_fair_value)+" "+cur,"EPS × EPS-growth-%"],
         ["Implied explicit-stage growth",qfmt(v.implied_explicit_stage_growth,true),"reverse DCF bisection: constant g over 5 explicit years + Gordon terminal, solved for current EV"],
         ["Implied perpetual growth",qfmt(v.implied_perpetual_growth,true),"Gordon algebra: g = (EV×r − FCF) / (EV + FCF)"]],
        "Two distinct implied-growth models — never a bare “implied growth”.");

    var a=data.allocation||{};
    h+='<h3>Capital Allocation</h3>'+qtable(["Metric","Value","Formula"],
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
}

// Phase F: charts AND diagrams are server-rendered static SVG — nothing to
// instantiate. Kept as named no-ops for export/print stripping hooks.
function renderPlotlyCharts(){
    return
}
function renderMermaidDiagrams(){
    return
}

// ---- Phase G: on-demand interactive chart view (lazy Plotly, never on the
// main page — the report stays zero-JS/stable; the modal loads Plotly only
// when an analyst asks for it) ----
var raPlotlyPromise = null;
function ensurePlotly(){
    if (typeof window.Plotly !== "undefined") return Promise.resolve(window.Plotly);
    if (raPlotlyPromise) return raPlotlyPromise;
    raPlotlyPromise = new Promise(function(resolve, reject){
        var s = document.createElement("script");
        s.src = "https://cdn.plot.ly/plotly-2.32.0.min.js";
        s.onload = function(){ resolve(window.Plotly); };
        s.onerror = function(){ reject(new Error("Plotly CDN failed to load")); };
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
        alert("Interactive view requires the Plotly library (CDN blocked?).");
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