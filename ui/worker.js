"use strict";

// Research Analyst - Markdown Web Worker v0.1.0
// Offloads MD-to-HTML to background thread

self.addEventListener("message", function (e) {
    var id = e.data.id;
    var md = e.data.markdown || "";
    var start = performance.now();
    var html = mdToHTML(md);
    self.postMessage({ id: id, html: html, parseTimeMs: Math.round((performance.now() - start) * 100) / 100 });
});

function mdToHTML(md) {
    var h = md;
    h = h.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
        var c = code.trim();
        if (lang === "mermaid") return '<div class="mermaid-diagram"><pre class="mermaid">' + c + '</pre></div>';
        if (lang === "python") return '<div class="plotly-code-block"><pre><code class="language-python">' + c + '</code></pre><button class="btn btn--secondary btn-copy-plotly" onclick="copyToClipboard(this)" type="button">Copy Code</button></div>';
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
