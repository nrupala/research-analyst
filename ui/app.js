"use strict";

// ============================================================
// Research Analyst - Browser UI v0.1.1
// Plotly.js rendering + Mermaid diagrams + Download report
// ============================================================

var dom = {
    form:         document.getElementById("research-form"),
    ticker:       document.getElementById("ticker"),
    reportType:   document.getElementById("report-type"),
    timeframe:    document.getElementById("timeframe"),
    btnSubmit:    document.getElementById("btn-submit"),
    btnText:      document.getElementById("btn-text"),
    btnSpinner:   document.getElementById("btn-spinner"),
    status:       document.getElementById("status"),
    statusText:   document.getElementById("status-text"),
    progressBar:  document.getElementById("progress-bar"),
    errorPanel:   document.getElementById("error-panel"),
    errorMessage: document.getElementById("error-message"),
    btnRetry:     document.getElementById("btn-retry"),
    results:      document.getElementById("results"),
    metaBar:      document.getElementById("meta-bar"),
    reportTabs:   document.getElementById("report-tabs"),
    reportContent:document.getElementById("report-content"),
    btnAbout:     document.getElementById("btn-about"),
    aboutModal:   document.getElementById("about-modal"),
    btnCloseAbout:document.getElementById("btn-close-about")
};

var currentReports = [];
var parsedReports = [];
var activeTabIndex = 0;
var isLoading = false;
var plotlyCounter = 0;

document.addEventListener("DOMContentLoaded", function () {
    if (typeof mermaid !== "undefined") {
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
    }
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/sw.js").catch(function () {});
    }
});

dom.form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!isLoading) runResearch();
});
dom.btnRetry.addEventListener("click", function () {
    if (!isLoading) runResearch();
});
dom.btnAbout.addEventListener("click", function () {
    dom.aboutModal.showModal();
});
dom.btnCloseAbout.addEventListener("click", function () {
    dom.aboutModal.close();
});
dom.aboutModal.addEventListener("click", function (e) {
    if (e.target === dom.aboutModal) dom.aboutModal.close();
});

async function runResearch() {
    var ticker = dom.ticker.value.trim().toUpperCase();
    if (!ticker) { dom.ticker.focus(); return; }
    if (!/^[A-Z0-9.\-]{1,10}$/.test(ticker)) {
        showError("Invalid ticker format. Use 1-10 alphanumeric characters.");
        return;
    }

    setLoading(true);
    hideError();
    hideResults();
    parsedReports = [];
    currentReports = [];
    plotlyCounter = 0;
    showStatus("Fetching data for " + ticker + "...", 10);

    var payload = {
        ticker: ticker,
        report_type: dom.reportType.value || null,
        timeframe: dom.timeframe.value,
        compare_tickers: [],
        custom_assumptions: {}
    };

    try {
        showStatus("Running analysis engines...", 30);
        var resp = await fetch("/api/research", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        showStatus("Generating reports...", 70);

        if (!resp.ok) {
            var err = await resp.json().catch(function () { return { detail: resp.statusText }; });
            throw new Error(err.detail || "HTTP " + resp.status);
        }

        var data = await resp.json();
        showStatus("Rendering...", 90);

        currentReports = data.reports_markdown || [];
        parsedReports = new Array(currentReports.length).fill(null);

        renderMetaBar(data);
        renderTabs(data.reports || []);
        await renderReport(0);
        showResults();
        showStatus("Complete", 100);
        setTimeout(function () { dom.status.hidden = true; }, 1500);
    } catch (err) {
        showError(err.message || "Research pipeline failed.");
    } finally {
        setLoading(false);
    }
}

function setLoading(v) {
    isLoading = v;
    dom.btnSubmit.disabled = v;
    dom.btnText.hidden = v;
    dom.btnSpinner.hidden = !v;
    if (v) dom.status.hidden = false;
}
function showStatus(t, pct) {
    dom.status.hidden = false;
    dom.statusText.textContent = t;
    dom.progressBar.style.width = pct + "%";
}
function showError(m) {
    dom.errorPanel.hidden = false;
    dom.errorMessage.textContent = m;
    dom.status.hidden = true;
}
function hideError() { dom.errorPanel.hidden = true; }
function hideResults() { dom.results.hidden = true; }
function showResults() { dom.results.hidden = false; }

function renderMetaBar(data) {
    var m = data.metadata || {};
    var items = [
        ["Ticker", data.ticker],
        ["Company", data.company_name],
        ["Type", data.security_type],
        ["Reports", (data.reports || []).length],
        ["Time", (m.processing_time_seconds || 0).toFixed(1) + "s"],
        ["Sources", (m.data_sources || []).length]
    ];
    dom.metaBar.innerHTML = items.map(function (p) {
        return '<div class="meta-bar__item"><span class="meta-bar__label">' +
            esc(p[0]) + ':</span> ' + esc(String(p[1])) + '</div>';
    }).join("");
}

function renderTabs(reports) {
    dom.reportTabs.innerHTML = "";
    reports.forEach(function (r, i) {
        var btn = document.createElement("button");
        btn.className = "tab" + (i === 0 ? " tab--active" : "");
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
        btn.textContent = r.report_type || "Report " + (i + 1);
        btn.addEventListener("click", function () {
            document.querySelectorAll(".tab").forEach(function (t) {
                t.classList.remove("tab--active");
                t.setAttribute("aria-selected", "false");
            });
            btn.classList.add("tab--active");
            btn.setAttribute("aria-selected", "true");
            renderReport(i);
        });
        dom.reportTabs.appendChild(btn);
    });
}

async function renderReport(idx) {
    activeTabIndex = idx;
    if (parsedReports[idx]) {
        dom.reportContent.innerHTML = parsedReports[idx];
        postRender();
        return;
    }
    dom.reportContent.innerHTML = '<p class="status__text">Rendering report...</p>';
    var md = currentReports[idx] || "*No report content.*";
    var html = mdToHTML(md);
    parsedReports[idx] = html;
    if (activeTabIndex === idx) {
        dom.reportContent.innerHTML = html;
        postRender();
    }
}

function postRender() {
    renderMermaid();
    renderPlotlyCharts();
    addDownloadButton();
}

// ============================================================
// Download Report
// ============================================================

function addDownloadButton() {
    var existing = document.getElementById("btn-download-report");
    if (existing) existing.remove();

    var md = currentReports[activeTabIndex];
    if (!md) return;

    var btn = document.createElement("button");
    btn.id = "btn-download-report";
    btn.className = "btn btn--secondary";
    btn.textContent = "Download Report (.md)";
    btn.style.marginBottom = "1rem";
    btn.addEventListener("click", function () {
        var blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        var ticker = dom.ticker.value.trim().toUpperCase() || "report";
        a.download = ticker + "_research_report.md";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    dom.reportContent.parentNode.insertBefore(btn, dom.reportContent);
}

// ============================================================
// Plotly.js Chart Rendering
// ============================================================

function renderPlotlyCharts() {
    if (typeof Plotly === "undefined") return;

    var blocks = document.querySelectorAll(".plotly-code-block");
    blocks.forEach(function (block) {
        var codeEl = block.querySelector("code");
        if (!codeEl) return;
        var code = codeEl.textContent;

        var chartData = parsePlotlyCode(code);
        if (!chartData) return;

        var chartDiv = document.createElement("div");
        chartDiv.className = "plotly-chart";
        chartDiv.id = "plotly-" + (++plotlyCounter);
        chartDiv.style.width = "100%";
        chartDiv.style.marginBottom = "1rem";

        block.parentNode.insertBefore(chartDiv, block);

        try {
            Plotly.newPlot(chartDiv.id, chartData.traces, chartData.layout, { responsive: true, displayModeBar: true });
        } catch (e) {
            console.warn("Plotly render failed:", e);
            chartDiv.innerHTML = '<p style="color:#94a3b8;font-size:0.875rem;">Chart rendering failed. Python code available below.</p>';
        }

        // Collapse code block, add toggle
        var toggle = document.createElement("button");
        toggle.className = "btn btn--secondary";
        toggle.textContent = "Show Python Code";
        toggle.style.fontSize = "0.75rem";
        toggle.style.marginTop = "0.5rem";
        toggle.addEventListener("click", function () {
            var pre = block.querySelector("pre");
            if (pre.style.display === "none") {
                pre.style.display = "";
                toggle.textContent = "Hide Python Code";
            } else {
                pre.style.display = "none";
                toggle.textContent = "Show Python Code";
            }
        });
        var pre = block.querySelector("pre");
        if (pre) pre.style.display = "none";
        block.insertBefore(toggle, block.firstChild);
    });
}

function parsePlotlyCode(code) {
    try {
        if (code.indexOf("make_subplots") !== -1 && code.indexOf("revenues") !== -1) {
            return parseRevenueMarginsChart(code);
        }
        if (code.indexOf("x_vals") !== -1 && code.indexOf("y_vals") !== -1) {
            return parseRiskHeatmap(code);
        }
        if (code.indexOf("lows") !== -1 && code.indexOf("highs") !== -1 && code.indexOf("bar_colors") !== -1) {
            return parseScenarioChart(code);
        }
        return null;
    } catch (e) {
        console.warn("Plotly parse failed:", e);
        return null;
    }
}

function extractArray(code, varName) {
    var re = new RegExp(varName + "\\s*=\\s*(\\[.*?\\])", "s");
    var m = code.match(re);
    if (!m) return null;
    var s = m[1].replace(/\bnull\b/g, "null").replace(/\bNone\b/g, "null").replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false");
    try { return JSON.parse(s); } catch (e) { return null; }
}

function extractNumber(code, varName) {
    var re = new RegExp(varName + "\\s*=\\s*([\\d.]+)");
    var m = code.match(re);
    return m ? parseFloat(m[1]) : null;
}

function parseRevenueMarginsChart(code) {
    var periods = extractArray(code, "periods");
    var revenues = extractArray(code, "revenues");
    var grossMargins = extractArray(code, "gross_margins");
    var opMargins = extractArray(code, "op_margins");
    var netMargins = extractArray(code, "net_margins");
    if (!periods || !revenues) return null;

    var traces = [];
    traces.push({
        x: periods, y: revenues, name: "Revenue ($B)",
        type: "bar", marker: { color: "#2563eb", opacity: 0.8 }, yaxis: "y"
    });
    if (grossMargins && grossMargins.some(function (v) { return v !== null; })) {
        traces.push({
            x: periods, y: grossMargins, name: "Gross Margin %",
            type: "scatter", mode: "lines+markers",
            line: { color: "#16a34a", width: 2 }, yaxis: "y2"
        });
    }
    if (opMargins && opMargins.some(function (v) { return v !== null; })) {
        traces.push({
            x: periods, y: opMargins, name: "Operating Margin %",
            type: "scatter", mode: "lines+markers",
            line: { color: "#ea580c", width: 2 }, yaxis: "y2"
        });
    }
    if (netMargins && netMargins.some(function (v) { return v !== null; })) {
        traces.push({
            x: periods, y: netMargins, name: "Net Margin %",
            type: "scatter", mode: "lines+markers",
            line: { color: "#7c3aed", width: 2, dash: "dot" }, yaxis: "y2"
        });
    }

    return {
        traces: traces,
        layout: {
            title: "Revenue & Margin Trends",
            template: "plotly_white", height: 420,
            legend: { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1 },
            yaxis: { title: "Revenue ($B)", side: "left" },
            yaxis2: { title: "Margin (%)", side: "right", overlaying: "y" },
            margin: { t: 50, b: 50, l: 60, r: 60 }
        }
    };
}

function parseRiskHeatmap(code) {
    var xVals = extractArray(code, "x_vals");
    var yVals = extractArray(code, "y_vals");
    var labels = extractArray(code, "labels");
    var sizes = extractArray(code, "sizes");
    var colors = extractArray(code, "colors");
    if (!xVals || !yVals) return null;

    return {
        traces: [{
            x: xVals, y: yVals, mode: "markers+text", type: "scatter",
            marker: { size: sizes || 30, color: colors || "#ea580c", opacity: 0.7, line: { width: 1, color: "white" } },
            text: labels || [], textposition: "top center", textfont: { size: 9 }
        }],
        layout: {
            title: "Risk Matrix - Probability vs Impact",
            template: "plotly_white", height: 380, showlegend: false,
            xaxis: { title: "Probability", tickvals: [1, 2, 3], ticktext: ["Low", "Medium", "High"], range: [0.5, 3.5] },
            yaxis: { title: "Impact", tickvals: [1, 2, 3, 4], ticktext: ["Low", "Medium", "High", "Critical"], range: [0.5, 4.5] },
            shapes: [
                { type: "rect", x0: 0.5, y0: 0.5, x1: 1.5, y1: 2.5, fillcolor: "#dcfce7", opacity: 0.3, layer: "below", line: { width: 0 } },
                { type: "rect", x0: 1.5, y0: 0.5, x1: 2.5, y1: 2.5, fillcolor: "#fef9c3", opacity: 0.3, layer: "below", line: { width: 0 } },
                { type: "rect", x0: 2.5, y0: 0.5, x1: 3.5, y1: 4.5, fillcolor: "#fecaca", opacity: 0.3, layer: "below", line: { width: 0 } },
                { type: "rect", x0: 0.5, y0: 2.5, x1: 2.5, y1: 4.5, fillcolor: "#fed7aa", opacity: 0.3, layer: "below", line: { width: 0 } }
            ],
            margin: { t: 50, b: 50, l: 60, r: 30 }
        }
    };
}

function parseScenarioChart(code) {
    var labels = extractArray(code, "labels");
    var lows = extractArray(code, "lows");
    var highs = extractArray(code, "highs");
    var barColors = extractArray(code, "bar_colors");
    var currentPrice = extractNumber(code, "current_price");
    if (!labels || !lows || !highs) return null;

    var traces = [];
    for (var i = 0; i < labels.length; i++) {
        traces.push({
            y: [labels[i]], x: [highs[i] - lows[i]], base: [lows[i]],
            type: "bar", orientation: "h",
            name: labels[i],
            marker: { color: barColors ? barColors[i] : "#2563eb", opacity: 0.8 },
            text: ["$" + Math.round(lows[i]) + " - $" + Math.round(highs[i])],
            textposition: "inside", showlegend: false
        });
    }

    var layout = {
        title: "Scenario-Based Valuation Range",
        template: "plotly_white", height: 280,
        xaxis: { title: "Price ($)" },
        margin: { t: 50, b: 50, l: 120, r: 30 }
    };

    if (currentPrice) {
        layout.shapes = [{
            type: "line", x0: currentPrice, x1: currentPrice, y0: -0.5, y1: labels.length - 0.5,
            line: { color: "black", width: 2, dash: "dash" }
        }];
        layout.annotations = [{
            x: currentPrice, y: labels.length - 0.5,
            text: "Current: $" + Math.round(currentPrice),
            showarrow: false, yshift: 15, font: { size: 11, color: "black" }
        }];
    }

    return { traces: traces, layout: layout };
}

async function renderMermaid() {
    if (typeof mermaid === "undefined") return;
    var els = document.querySelectorAll(".mermaid");
    for (var i = 0; i < els.length; i++) {
        try {
            var result = await mermaid.render("mm-" + Date.now() + "-" + i, els[i].textContent);
            els[i].innerHTML = result.svg;
        } catch (ex) { /* leave raw text */ }
    }
}

function mdToHTML(md) {
    var h = md;
    h = h.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
        var c = code.trim();
        if (lang === "mermaid") return '<div class="mermaid-diagram"><pre class="mermaid">' + c + '</pre></div>';
        if (lang === "python") return '<div class="plotly-code-block"><pre><code class="language-python">' + c + '</code></pre></div>';
        return '<pre><code class="language-' + (lang || "text") + '">' + c + '</code></pre>';
    });

    h = h.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    h = h.replace(/^---$/gm, "<hr>");
    h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

    h = h.replace(/^(\|.+\|)\n(\|[-|: ]+\|)\n((?:\|.+\|\n?)*)/gm, function (_, hdr, sep, body) {
        var ths = hdr.split("|").filter(function (c) { return c.trim(); }).map(function (c) { return "<th>" + c.trim() + "</th>"; }).join("");
        var rows = body.trim().split("\n").map(function (row) {
            var tds = row.split("|").filter(function (c) { return c.trim(); }).map(function (c) { return "<td>" + c.trim() + "</td>"; }).join("");
            return "<tr>" + tds + "</tr>";
        }).join("");
        return "<table><thead><tr>" + ths + "</tr></thead><tbody>" + rows + "</tbody></table>";
    });

    h = h.replace(/^- (.+)$/gm, "<li>$1</li>");
    h = h.replace(/(<li>[\s\S]*?<\/li>(?:\n|$))+/g, function (m) { return "<ul>" + m + "</ul>"; });

    h = h.replace(/\n\n+/g, "</p><p>");
    h = "<p>" + h + "</p>";

    h = h.replace(/<p>\s*<\/p>/g, "");
    h = h.replace(/<p>(<h[1-4]>)/g, "$1");
    h = h.replace(/(<\/h[1-4]>)<\/p>/g, "$1");
    h = h.replace(/<p>(<hr>)<\/p>/g, "$1");
    h = h.replace(/<p>(<table>)/g, "$1");
    h = h.replace(/(<\/table>)<\/p>/g, "$1");
    h = h.replace(/<p>(<ul>)/g, "$1");
    h = h.replace(/(<\/ul>)<\/p>/g, "$1");
    h = h.replace(/<p>(<pre>)/g, "$1");
    h = h.replace(/(<\/pre>)<\/p>/g, "$1");
    h = h.replace(/<p>(<div)/g, "$1");
    h = h.replace(/(<\/div>)<\/p>/g, "$1");

    return h;
}

function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

function copyToClipboard(btn) {
    var code = btn.closest(".plotly-code-block").querySelector("code").textContent;
    navigator.clipboard.writeText(code).then(function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Show Python Code"; }, 2000);
    });
}
