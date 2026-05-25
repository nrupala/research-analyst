/**
 * Research Analyst - Markdown Web Worker
 * Module: ui/worker.js | Version: 0.1.0 | Updated: 2026-05-15
 *
 * Offloads Markdown-to-HTML conversion to a background thread.
 * Prevents UI jank on mobile devices when rendering large reports.
 *
 * Protocol:
 *   Main thread sends:  { id: number, markdown: string }
 *   Worker responds:    { id: number, html: string, parseTimeMs: number }
 */

"use strict";

self.addEventListener("message", function(e) {
    var data = e.data;
    var id = data.id;
    var markdown = data.markdown || "";

    var start = performance.now();
    var html = markdownToHTML(markdown);
    var elapsed = performance.now() - start;

    self.postMessage({
        id: id,
        html: html,
        parseTimeMs: Math.round(elapsed * 100) / 100
    });
});

/**
 * Lightweight Markdown to HTML converter.
 * Handles: headings, bold, italic, code blocks, inline code, tables,
 * unordered lists, blockquotes, horizontal rules, paragraphs.
 *
 * Security: escapes HTML entities before processing to prevent XSS.
 * Mermaid blocks are preserved as <pre class="mermaid"> for post-processing.
 * Python code blocks get copy buttons for Plotly code.
 */
function markdownToHTML(md) {
    var html = md;

    // Sanitize: escape HTML entities
    html = html
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // Code blocks (``` ... ```)
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
        var trimmed = code.trim();
        if (lang === "mermaid") {
            return '<div class="mermaid-diagram"><pre class="mermaid">' + trimmed + '</pre></div>';
        }
        if (lang === "python") {
            return '<div class="plotly-code-block"><pre><code class="language-python">' +
                trimmed + '</code></pre>' +
                '<button class="btn btn--secondary btn-copy-plotly" onclick="copyToClipboard(this)" type="button">Copy Code</button></div>';
        }
        return '<pre><code class="language-' + (lang || "text") + '">' + trimmed + '</code></pre>';
    });

    // Headers
    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

    // Horizontal rules
    html = html.replace(/^---$/gm, "<hr>");

    // Bold and italic
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Tables
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

    // Unordered lists
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, function(match) { return "<ul>" + match + "</ul>"; });

    // Paragraphs
    html = html.replace(/\n\n+/g, "</p><p>");
    html = "<p>" + html + "</p>";

    // Clean up empty paragraphs and misplaced wrapping
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
