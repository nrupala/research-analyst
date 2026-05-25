"use strict";

// ============================================================
// Research Analyst - Browser UI v0.1.0
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
var mdWorker = null;
var workerCallId = 0;
var workerCallbacks = {};

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
    if (typeof mermaid !== "undefined") {
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
    }
    initWorker();
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/sw.js").catch(function () {});
    }
});

function initWorker() {
    try {
        mdWorker = new Worker("/worker.js");
        mdWorker.addEventListener("message", function (e) {
            var cb = workerCallbacks[e.data.id];
            if (cb) {
                delete workerCallbacks[e.data.id];
                cb(e.data.html);
            }
        });
        mdWorker.addEventListener("error", function () {
            mdWorker = null;
        });
    } catch (ex) {
        mdWorker = null;
    }
}

function parseMarkdown(markdown) {
    return new Promise(function (resolve) {
        if (mdWorker) {
            var id = ++workerCallId;
            workerCallbacks[id] = function (html) { resolve(html); };
            mdWorker.postMessage({ id: id, markdown: markdown });
        } else {
            resolve(mdToHTML(markdown));
        }
    });
}

// ============================================================
// Events
// ============================================================

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

// ============================================================
// Research pipeline
// ============================================================

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

// ============================================================
// UI state
// ============================================================

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

// ============================================================
// Rendering
// ============================================================

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
        requestAnimationFrame(function () {
            dom.reportContent.innerHTML = parsedReports[idx];
            postRender();
        });
        return;
    }
    dom.reportContent.innerHTML = '<p class="status__text">Rendering report...</p>';
    var html = await parseMarkdown(currentReports[idx] || "*No report content.*");
    parsedReports[idx] = html;
    if (activeTabIndex === idx) {
        requestAnimationFrame(function () {
            dom.reportContent.innerHTML = html;
            postRender();
        });
    }
}

function postRender() {
    renderMermaid();
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

function copyToClipboard(btn) {
    var code = btn.closest(".plotly-code-block").querySelector("code").textContent;
    navigator.clipboard.writeText(code).then(function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy Code"; }, 2000);
    }).catch(function () {
        var ta = document.createElement("textarea");
        ta.value = code; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); document.body.removeChild(ta);
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy Code"; }, 2000);
    });
}

// ============================================================
// Markdown to HTML (main-thread fallback)
// ============================================================

function mdToHTML(md) {
    var h = md;
    h = h.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Code blocks
    h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
        var c = code.trim();
        if (lang === "mermaid") return '<div class="mermaid-diagram"><pre class="mermaid">' + c + '</pre></div>';
        if (lang === "python") return '<div class="plotly-code-block"><pre><code class="language-python">' + c + '</code></pre><button class="btn btn--secondary btn-copy-plotly" onclick="copyToClipboard(this)" type="button">Copy Code</button></div>';
        return '<pre><code class="language-' + (lang || "text") + '">' + c + '</code></pre>';
    });

    // Headings
    h = h.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    h = h.replace(/^---$/gm, "<hr>");

    // Inline
    h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Tables
    h = h.replace(/^(\|.+\|)\n(\|[-|: ]+\|)\n((?:\|.+\|\n?)*)/gm, function (_, hdr, sep, body) {
        var ths = hdr.split("|").filter(function (c) { return c.trim(); }).map(function (c) { return "<th>" + c.trim() + "</th>"; }).join("");
        var rows = body.trim().split("\n").map(function (row) {
            var tds = row.split("|").filter(function (c) { return c.trim(); }).map(function (c) { return "<td>" + c.trim() + "</td>"; }).join("");
            return "<tr>" + tds + "</tr>";
        }).join("");
        return "<table><thead><tr>" + ths + "</tr></thead><tbody>" + rows + "</tbody></table>";
    });

    // Lists
    h = h.replace(/^- (.+)$/gm, "<li>$1</li>");
    h = h.replace(/(<li>[\s\S]*?<\/li>(?:\n|$))+/g, function (m) { return "<ul>" + m + "</ul>"; });

    // Paragraphs
    h = h.replace(/\n\n+/g, "</p><p>");
    h = "<p>" + h + "</p>";

    // Cleanup
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
