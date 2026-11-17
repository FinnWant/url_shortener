// Minimal dependency-free SVG bar chart. barChart(el, [{label, value}, ...])
function barChart(el, data) {
  const NS = "http://www.w3.org/2000/svg", W = 720, H = 200, L = 30, B = 20, T = 8;
  const max = Math.max(1, ...data.map(d => d.value));
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("width", "100%");
  const add = (name, attrs, text) => {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    svg.appendChild(n);
    return n;
  };
  add("text", {x: 0, y: T + 8, class: "axis"}, String(max));
  add("text", {x: 0, y: H - B, class: "axis"}, "0");
  add("line", {x1: L, x2: W, y1: H - B, y2: H - B, stroke: "#999"});
  const bw = (W - L) / data.length, ph = H - B - T;
  data.forEach((d, i) => {
    const h = d.value / max * ph;
    const r = add("rect", {x: L + i * bw + 1, y: H - B - h, width: Math.max(bw - 2, 1),
                           height: h, class: "bar"});
    const t = document.createElementNS(NS, "title");
    t.textContent = `${d.label}: ${d.value}`;
    r.appendChild(t);
  });
  add("text", {x: L, y: H - 5, class: "axis"}, data[0].label);
  add("text", {x: W, y: H - 5, class: "axis", "text-anchor": "end"}, data[data.length - 1].label);
  el.replaceChildren(svg);
}
