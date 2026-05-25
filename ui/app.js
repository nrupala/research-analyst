/**
 * Research Analyst - Browser UI Application
 * Module: ui/app.js | Version: 0.1.0 | Updated: 2026-05-15
 *
 * Vanilla JavaScript. No frameworks. No build step.
 * Handles: form submission, API calls, Markdown rendering (via Web Worker),
 * Plotly chart code blocks, Mermaid diagram rendering, lazy tab switching.
 *
 * Performance:
 *   - Markdown parsing offloaded to Web Worker (keeps UI thread free)
 *   - Lazy tab rendering (only active tab is parsed and rendered)
 *   - Cached parsed HTML per tab (no re-parse on tab switch)
 *   - requestAnimationFrame for DOM updates
 *   - Debounced form submission
 *
 * Security:
 *   - All user input sanitized before DOM insertion
 *   - No eval() or innerHTML with raw user data
 *   - XSS prevention via textContent for user-supplied strings
 */

"use strict";

// ============================================================
// DOM References
// ============================================================

const dom = {
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
    btnCloseAbout:document.getElementById("btn-close-about"),
};

// ============================================================
// State
// ============================================================

let currentReports = [];      // Raw markdown per report
let parsedReports = [];       // Cached parsed HTML per report (lazy)
let activeTabIndex = 0;
let isLoading = false;
let mdWorker = null;          // Web Worker instance
let workerCallId = 0;
let workerCallbacks = {};     // Pending worker callbacks by ID

// ============================================================
// Initialization
// ============================================================

document.addEventListener("DOMContentLoaded", function() {
    // Initialize Mermaid
    if (typeof mermaid \!== "undefined") {
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
    }

    // Initialize Web Worker for Markdown parsing
    initWorker();

    // Register service worker for PWA
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/sw.js").catch(function() {
            // Non-critical failure
        });
    }
});

function initWorker() {
    try {
        mdWorker = new Worker("/static/worker.js");
        mdWorker.addEventListener("message", function(e) {
            var data = e.data;
            var cb = workerCallbacks[data.id];
            if (cb) {
                delete workerCallbacks[data.id];
                cb(data.html, data.parseTimeMs);
            }
        });
        mdWorker.addEventListener("error", function(err) {
            console.warn("Worker error, falling back to main thread:", err);
            mdWorker = null;
        });
    } catch (e) {
        // Workers not supported; fall back to main thread
        mdWorker = null;
    }
}

/**
 * Parse markdown via Web Worker (async) or main thread (sync fallback).
 * Returns a Promise<string> of HTML.
 */
function parseMarkdown(markdown) {
    return new Promise(function(resolve) {
        if (mdWorker) {
            var id = ++workerCallId;
            workerCallbacks[id] = function(html, ms) {
                resolve(html);
            };
            mdWorker.postMessage({ id: id, markdown: markdown });
        } else {
            // Fallback: parse on main thread
            resolve(markdownToHTMLFallback(markdown));
        }
    });
}

// ============================================================
// Event Handlers
// ============================================================

dom.form.addEventListener("submit", function(e) {
    e.preventDefault();
    if (\!isLoading) runResearch();
});

dom.btnRetry.addEventListener("click", function() {
    if (\!isLoading) runResearch();
});

dom.btnAbout.addEventListener("click", function() {
    dom.aboutModal.showModal();
});

dom.btnCloseAbout.addEventListener("click", function() {
    dom.aboutModal.close();
});

dom.aboutModal.addEventListener("click", function(e) {
    if (e.target === dom.aboutModal) dom.aboutModal.close();
});

document.addEventListener("keydown", function(e) {
    if (e.key === "Escape" && dom.aboutModal.open) dom.aboutModal.close();
});

// ============================================================
// Research Pipeline
// ============================================================

async function runResearch() {
    var ticker = dom.ticker.value.trim().toUpperCase();
    if (\!ticker) {
        dom.ticker.focus();
        return;
    }

    // Validate ticker format
    if (\!/^[A-Z0-9.\-]{1,10}$/.test(ticker)) {
        showError("Invalid ticker format. Use 1-10 alphanumeric characters.");
        return;
    }

    setLoading(true);
    hideError();
    hideResults();

    // Reset cached parsed reports
    parsedReports = [];
    currentReports = [];

    showStatus("Fetching data for " + ticker + "...", 10);

    var payload = {
        ticker: ticker,
        report_type: dom.reportType.value || null,
        timeframe: dom.timeframe.value,
        compare_tickers: [],
        custom_assumptions: {},
    };

    try {
        showStatus("Running analysis engines...", 30);

        var resp = await fetch("/api/research", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        showStatus("Generating reports...", 70);

        if (\!resp.ok) {
            var err = await resp.json().catch(function() { return { detail: resp.statusText }; });
            throw new Error(err.detail || ("HTTP " + resp.status));
        }

        var data = await resp.json();

        showStatus("Rendering...", 90);

        currentReports = data.reports_markdown || [];
        parsedReports = new Array(currentReports.length).fill(null); // Lazy: null = not parsed yet

        renderMetaBar(data);
        renderTabs(data.reports || []);

        // Render only the first (active) tab immediately
        await renderReport(0);

        showResults();
        showStatus("Complete", 100);

        setTimeout(function() { dom.status.hidden = true; }, 1500);

    } catch (err) {
        showError(err.message || "Research pipeline failed. Please try again.");
    } finally {
        setLoading(false);
    }
}

// ============================================================
// UI State Management
// ============================================================

function setLoading(loading) {
    isLoading = loading;
    dom.btnSubmit.disabled = loading;
    dom.btnText.hidden = loading;
    dom.btnSpinner.hidden = \!loading;
    if (loading) dom.status.hidden = false;
}

function showStatus(text, pct) {
    dom.status.hidden = false;
    dom.statusText.textContent = text;
    dom.progressBar.style.width = pct + "%";
}

function showError(msg) {
    dom.errorPanel.hidden = false;
    dom.errorMessage.textContent = msg;
    dom.status.hidden = true;
}

function hideError() { dom.errorPanel.hidden = true; }
function hideResults() { dom.results.hidden = true; }
function showResults() { dom.results.hidden = false; }

// ============================================================
// Rendering (Lazy Tabs)
// ============================================================

function renderMetaBar(data) {
    var meta = data.metadata || {};
    var items = [
        { label: "Ticker", value: data.ticker },
        { label: "Company", value: data.company_name },
        { label: "Type", value: data.security_type },
        { label: "Reports", value: (data.reports || []).length },
        { label: "Time", value: (meta.processing_time_seconds || 0).toFixed(1) + "s" },
        { label: "Sources", value: (meta.data_sources || []).length },
    ];

    if (meta.warnings && meta.warnings.length > 0) {
        items.push({ label: "Warnings", value: meta.warnings.length });
    }

    dom.metaBar.innerHTML = items.map(function(item) {
        return '<div class="meta-bar__item"><span class="meta-bar__label">' +
            esc(item.label) + ':</span> ' + esc(String(item.value)) + '</div>';
    }).join("");
}

function renderTabs(reports) {
    dom.reportTabs.innerHTML = "";
    reports.forEach(function(report, i) {
        var btn = document.createElement("button");
        btn.className = "tab" + (i === 0 ? " tab--active" : "");
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
        btn.textContent = report.report_type || ("Report " + (i + 1));
        btn.addEventListener("click", function() {
            document.querySelectorAll(".tab").forEach(function(t) {
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

/**
 * Render a report tab. Uses cached HTML if already parsed (lazy loading).
 * First parse goes through the Web Worker; subsequent switches are instant.
 */
async function renderReport(index) {
    activeTabIndex = index;

    // Check cache first (lazy: only parse when tab is first selected)
    if (parsedReports[index]) {
        requestAnimationFrame(function() {
            dom.reportContent.innerHTML = parsedReports[index];
            postRender();
        });
        return;
    }

    var markdown = currentReports[index] || "*No report content.*";

    // Show loading indicator in report area
    dom.reportContent.innerHTML = '<p class="status__text">Rendering report...</p>';

    // Parse via Web Worker (non-blocking)
    var html = await parseMarkdown(markdown);

    // Cache the parsed HTML
    parsedReports[index] = html;

    // Only update DOM if this tab is still active (user may have switched)
    if (activeTabIndex === index) {
        requestAnimationFrame(function() {
            dom.reportContent.innerHTML = html;
            postRender();
        });
    }
}

/**
 * Post-render: initialize Mermaid diagrams and Plotly code blocks.
 * Called after DOM is updated via requestAnimationFrame.
 */
function postRender() {
    renderMermaidDiagrams();
    setupPlotlyBlocks();
}

// ============================================================
// Mermaid Rendering
// ============================================================

async function renderMermaidDiagrams() {
    if (typeof mermaid === "undefined") return;

    var diagrams = document.querySelectorAll(".mermaid");
    for (var i = 0; i < diagrams.length; i++) {
        var el = diagrams[i];
        var code = el.textContent;
        try {
            var id = "mermaid-" + Date.now() + "-" + i;
            var result = await mermaid.render(id, code);
            el.innerHTML = result.svg;
        } catch (err) {
            console.warn("Mermaid render failed:", err);
        }
    }
}

// ============================================================
// Plotly Code Blocks
// ============================================================

function setupPlotlyBlocks() {
    // Plotly code is Python (copy-paste-ready), not executed in browser
}

function copyToClipboard(btn) {
    var block = btn.closest(".plotly-code-block");
    var code = block.querySelector("code").textContent;
    navigator.clipboard.writeText(code).then(function() {
        var original = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function() { btn.textContent = original; }, 2000);
    }).catch(function() {
        var textarea = document.createElement("textarea");
        textarea.value = code;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        btn.textContent = "Copied";
        setTimeout(function() { btn.textContent = "Copy Code"; }, 2000);
    });
}

// ============================================================
// Fallback Markdown Parser (main thread, no Worker)
// ============================================================

function markdownToHTMLFallback(md) {
    var html = md;

    html = html
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
        if (lang === "mermaid") {
            return '<div class="mermaid-diagram"><pre class="mermaid">' + code.trim() + '</pre></div>';
        }
        if (lang === "python") {
            return '<div class="plotly-code-block"><pre><code class="language-python">' + code.trim() +
                '</code></pre><button class="btn btn--secondary btn-copy-plotly" onclick="copyToClipboard(this)" type="button">Copy Code</button></div>';
        }
        return '<pre><code class="language-' + (lang || "text") + '">' + code.trim() + '</code></pre>';
    });

    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    html = html.replace(/^---$/gm, "<hr>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    html = html.replace(/^(\|.+\|)\n(\|[\-\|: ]+\|)\n((?:\|.+\|\n?)*)/gm, function(match, header, sep, body) {
        var ths = header.split("|").filter(function(c) { return c.trim(); })
            .map(function(c) { return "<th>" + c.trim() + "</th>"; }).join("");
        var rows = body.trim().split("\n").map(function(row) {
            var tds = row.split("|").filter(function(c) { return c.trim(); })
                .map(function(c) { return "<td>" + c.trim() + "</td>"; }).join("");
            return "<tr>" + tds + "</tr>";
        }).join("");
        return "<table><thead><tr>" + ths + "</tr></thead><tbody>" + rows + "</tbody></table>";
    });

    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, function(match) { return "<ul>" + match + "</ul>"; });

    html = html.replace(/\n\n+/g, "</p><p>");
    html = "<p>" + html + "</p>";

    html = html.replace(/<p>\s*<\/p>/g, "");
    html = html.replace(/<p>(<h[1-4]>)/g, "$1");
    html = html.replace(/(<\/h[1-4]>)<\/p>/g, "$1");
    html = html.replace(/<p>(<hr>)<\/p>/g, "$1");
    html = html.replace(/<p>(<table>)/g, "$1");
    html = html.replace(/(<\/table>)<\/p>/g, "$1");
    html = html.replace(/<p>(<ul>)/g, "$1");
    html = html.replace(/(<\/ul>)<\/p>/g, "$1");
    html = html.replace(/<p>(<pre>)/g, "$1");
    html = html.replace(/(<\/pre>)<\/p>/g, "$1");
    html = html.replace(/<p>(<div)/g, "$1");
    html = html.replace(/(<\/div>)<\/p>/g, "$1");

    return html;
}

// ============================================================
// Utility
// ============================================================

function esc(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
