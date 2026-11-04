// AIMLDS partial Plotly.js bundle for Research Analyst (Quant Lab Phase 1).
// Traces: scatter, bar, waterfall, heatmap, indicator — nothing else.
// Built from plotly.js 2.32.0 (MIT) via the documented lib/core route.
// See README.md in this directory for the build record.
var Plotly = require('plotly.js/lib/core');
Plotly.register([
    require('plotly.js/lib/scatter'),
    require('plotly.js/lib/bar'),
    require('plotly.js/lib/waterfall'),
    require('plotly.js/lib/heatmap'),
    require('plotly.js/lib/indicator')
]);
module.exports = Plotly;
