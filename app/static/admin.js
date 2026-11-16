const $ = id => document.getElementById(id);
const KEY = "admin_token";
const msg = t => { $("msg").textContent = t || ""; };

function token() { return sessionStorage.getItem(KEY); }
function show() {
  const ok = !!token();
  $("login").hidden = ok; $("app").hidden = !ok;
  if (ok) load();
}
async function api(path, opts = {}) {
  const r = await fetch(path, {...opts, headers: {
    ...(opts.body ? {"Content-Type": "application/json"} : {}),
    Authorization: "Bearer " + token()}});
  if (r.status === 401) { sessionStorage.removeItem(KEY); show(); throw new Error("Invalid token"); }
  if (!r.ok) {
    let d = r.statusText;
    try { const j = await r.json(); d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) {}
    throw new Error(d);
  }
  return r.status === 204 ? null : r.json();
}
const run = f => async (...a) => { msg(); try { await f(...a); } catch (e) { msg(e.message); } };
// Build text via textContent only: targets/referrers are untrusted.
function cell(tr, text) { const td = document.createElement("td"); td.textContent = text; tr.appendChild(td); return td; }

const load = run(async () => {
  const links = await api("/api/links");
  const tb = document.querySelector("#links tbody"); tb.replaceChildren();
  for (const l of links) {
    const tr = document.createElement("tr");
    cell(tr, l.code); cell(tr, l.target); cell(tr, l.clicks);
    const td = cell(tr, "");
    const b = document.createElement("button"); b.textContent = "Stats";
    b.onclick = run(() => stats(l.code)); td.appendChild(b);
    const d = document.createElement("button"); d.textContent = "Delete";
    d.onclick = run(async () => {
      if (!confirm("Delete " + l.code + "?")) return;
      await api("/api/links/" + encodeURIComponent(l.code), {method: "DELETE"});
      $("stats").hidden = true; await load();
    });
    td.appendChild(d);
    tb.appendChild(tr);
  }
});

async function stats(code) {
  const s = await api("/api/links/" + encodeURIComponent(code) + "/stats");
  $("stats-code").textContent = code; $("stats").hidden = false;
  barChart($("chart"), s.clicks_per_day.map(d => ({label: d.date, value: d.clicks})));
  const fill = (id, items, key) => {
    const ul = $(id); ul.replaceChildren();
    if (!items.length) { const li = document.createElement("li"); li.textContent = "No clicks yet"; ul.appendChild(li); }
    for (const i of items) { const li = document.createElement("li"); li.textContent = `${i[key]} — ${i.clicks}`; ul.appendChild(li); }
  };
  fill("refs", s.top_referrers, "referrer"); fill("browsers", s.browsers, "family");
}

$("login").onsubmit = e => { e.preventDefault(); sessionStorage.setItem(KEY, $("token").value); $("token").value = ""; show(); };
$("logout").onclick = () => { sessionStorage.removeItem(KEY); $("stats").hidden = true; show(); };
$("create").onsubmit = run(async e => {
  e.preventDefault();
  const body = {target: $("target").value}; if ($("code").value) body.code = $("code").value;
  await api("/api/links", {method: "POST", body: JSON.stringify(body)});
  $("target").value = ""; $("code").value = ""; await load();
});
show();
