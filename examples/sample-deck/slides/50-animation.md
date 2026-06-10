# Embedded Animation — D3.js

The chart below is a live D3 view, embedded as an isolated page so its script
actually runs (see the README for why this beats inlining `<script>` in Markdown).
In PDF export it resolves to a still frame — `data-poster-at` sets the capture
moment; the page also paints a deterministic frame under `?static`.

<iframe class="embed" src="d3-bars.html" title="Live token-probability chart"
        data-poster-at="800"
        width="980" height="380" loading="lazy" style="border:0;"></iframe>
