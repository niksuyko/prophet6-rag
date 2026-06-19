/* Prophet-6 Observability dashboard — vanilla JS, same fetch/render idiom as studio.js.
   A view registry (VIEWS) drives the nav; each milestone appends a view. No framework. */

const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => [...p.querySelectorAll(s)];
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const htmlNode = h => { const t = el("div"); t.innerHTML = h; return t.firstElementChild || t; };

/* ---- inline teaching help: HELP[key] = {term, what, why, tip?} (populated below) ---- */
let HELP = {};
function helpIcon(key) {
  // emit the ⓘ only if we actually have copy for this key (no dead affordances)
  return HELP[key] ? `<span class="help" data-help="${esc(key)}" tabindex="0" role="button" aria-label="Explain: ${esc(HELP[key].term)}"></span>` : "";
}
// a section title with an optional help icon (icon sits before the trailing hairline)
function secTitle(text, key) { return el("div", "section-title", esc(text) + (key ? helpIcon(key) : "")); }

function initHelp() {
  const pop = el("div", "help-pop"); document.body.appendChild(pop);
  let hideT;
  const show = icon => {
    const d = HELP[icon.dataset.help]; if (!d) return;
    clearTimeout(hideT);
    pop.innerHTML = `<span class="ht">${esc(d.term)}</span><p class="hw">${esc(d.what)}</p>` +
      `<p class="hy">${esc(d.why)}</p>` + (d.tip ? `<p class="htip">${esc(d.tip)}</p>` : "");
    pop.style.visibility = "hidden"; pop.classList.add("show");
    pop.style.left = "0px"; pop.style.top = "0px";
    const r = icon.getBoundingClientRect(), pr = pop.getBoundingClientRect();
    let left = Math.max(12, Math.min(r.left, innerWidth - pr.width - 12));
    let top = r.bottom + 8;
    if (top + pr.height > innerHeight - 12) top = Math.max(12, r.top - pr.height - 8);
    pop.style.left = left + "px"; pop.style.top = top + "px"; pop.style.visibility = "";
  };
  const hide = () => { hideT = setTimeout(() => pop.classList.remove("show"), 60); };
  const closest = (e, sel) => e.target && e.target.closest && e.target.closest(sel);
  document.addEventListener("mouseover", e => { const i = closest(e, ".help"); if (i) show(i); });
  document.addEventListener("mouseout", e => { if (closest(e, ".help")) hide(); });
  document.addEventListener("focusin", e => { const i = closest(e, ".help"); if (i) show(i); });
  document.addEventListener("focusout", e => { if (closest(e, ".help")) hide(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") pop.classList.remove("show"); });
}

async function jget(url) {
  const r = await fetch(url);
  let d = {};
  try { d = await r.json(); } catch { /* non-json error body */ }
  if (!r.ok || d.error) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}
function setStatus(cls, text) { const s = $("#status"); s.className = "status " + cls; s.textContent = text; }

/* ---- shared formatting ---- */
const PROV = ["manual", "official_kb", "reddit", "patch", "article", "general"];
function stacked(dist, big) {
  const total = Object.values(dist || {}).reduce((a, b) => a + b, 0);
  if (!total) return `<div class="stacked${big ? " lg" : ""}"></div>`;
  const segs = PROV.filter(k => dist[k]).map(k =>
    `<span class="seg-${k}" style="width:${(dist[k] / total * 100).toFixed(1)}%" title="${k}: ${dist[k]}"></span>`);
  // include any unexpected keys at the end
  Object.keys(dist).filter(k => !PROV.includes(k) && dist[k]).forEach(k =>
    segs.push(`<span class="seg-general" style="width:${(dist[k] / total * 100).toFixed(1)}%" title="${esc(k)}: ${dist[k]}"></span>`));
  return `<div class="stacked${big ? " lg" : ""}">${segs.join("")}</div>`;
}
function provLegend(dist) {
  const cols = { manual: "#7fd08a", official_kb: "#7fd08a", reddit: "#ff9d5c", patch: "#6fb8ff", article: "#4a5160", general: "#9aa3b2" };
  return `<div class="legend">${Object.entries(dist || {}).map(([k, v]) =>
    `<span><i style="background:${cols[k] || "#9aa3b2"}"></i>${esc(k)} ${v}</span>`).join("")}</div>`;
}
function kv(rows) {  // rows: [[label, value, cls?], …]
  return `<dl class="kv">${rows.filter(Boolean).map(([k, v, c]) =>
    `<dt>${esc(k)}</dt><dd${c ? ` class="${c}"` : ""}>${v == null || v === "" ? "—" : esc(v)}</dd>`).join("")}</dl>`;
}
function rawJSON(obj) {
  const j = JSON.stringify(obj, null, 2)
    .replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))
    .replace(/^(\s*)("[^"]+")(:)/gm, '$1<span class="k">$2</span>$3');
  return `<pre class="rawbox">${j}</pre>`;
}
function fmtVal(v, fmt) {
  if (v == null) return "—";
  if (fmt === "ratio") return Number(v).toFixed(3);
  if (fmt === "pct100") return Number(v).toFixed(0) + "%";
  if (fmt === "pct") return (Number(v) * 100).toFixed(0) + "%";
  return String(v);
}
function kpiHealth(v, target, dir) {
  if (v == null || target == null) return "";
  const ok = dir === "high" ? v >= target : v <= target;
  if (ok) return "ok";
  return Math.abs(v - target) <= target * 0.06 + 0.001 ? "warn" : "bad";
}
function rateHealth(v) { return v == null ? "" : v === 0 ? "ok" : v < 0.2 ? "warn" : "bad"; }
function sparkline(hist, target) {
  if (!hist || hist.length < 2) return "";
  const w = 150, h = 34, pad = 3, vals = hist.map(p => p.value);
  const mn = Math.min(...vals, target ?? Infinity), mx = Math.max(...vals, target ?? -Infinity);
  const X = i => pad + i * (w - 2 * pad) / (hist.length - 1);
  const Y = v => h - pad - ((v - mn) / ((mx - mn) || 1)) * (h - 2 * pad);
  const pts = hist.map((p, i) => `${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ");
  const last = hist[hist.length - 1];
  const tl = target != null ? `<line x1="0" y1="${Y(target).toFixed(1)}" x2="${w}" y2="${Y(target).toFixed(1)}" stroke="var(--border)" stroke-dasharray="3 3"/>` : "";
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${tl}` +
    `<polyline points="${pts}" fill="none" stroke="var(--amber)" stroke-width="1.5"/>` +
    `<circle cx="${X(hist.length - 1).toFixed(1)}" cy="${Y(last.value).toFixed(1)}" r="2.5" fill="var(--amber)"/></svg>`;
}

/* ====================================================================== *
 *  ROUTER                                                                *
 * ====================================================================== */
const VIEWS = [];
let DEFAULT_VIEW = "overview";
function register(v) { VIEWS.push(v); }
function renderNav(active) {
  const n = $("#nav"); n.innerHTML = "";
  VIEWS.forEach(v => {
    const b = el("button", v.id === active ? "on" : "", esc(v.label));
    b.onclick = () => go(v.id);
    n.appendChild(b);
  });
}
let CURRENT = null;
async function go(id, params = {}) {
  const v = VIEWS.find(x => x.id === id) || VIEWS.find(x => x.id === DEFAULT_VIEW) || VIEWS[0];
  CURRENT = { id: v.id, params };
  renderNav(v.id);
  const vh = $("#viewHelp"); if (vh) vh.innerHTML = helpIcon("view." + v.id);
  const qs = new URLSearchParams({ v: v.id, ...(params.id ? { id: params.id } : {}) });
  history.replaceState(null, "", "?" + qs.toString());
  const main = $("#main"), rail = $("#rail");
  main.innerHTML = ""; rail.innerHTML = `<p class="rail-title">Inspector</p>`;
  try {
    await v.mount(main, rail, params);
  } catch (e) {
    setStatus("error", e.message);
    main.appendChild(el("div", "problems", "Failed to load view: " + esc(e.message)));
  }
}

/* ====================================================================== *
 *  TRACE EXPLORER (M1)                                                   *
 * ====================================================================== */
const FILTERS = ["all", "no-patch", "all-general", "clamped", "salvage", "hallucinated-cite", "sysex-fail", "error"];

function rowHealth(t) {
  if (!t.ok || t.all_general || !t.sysex_ok) return "bad";
  if (t.n_clamped || t.salvaged || !t.patch_served || t.n_unmatched || t.mixer_all_down) return "warn";
  return "ok";
}
function traceRow(t, onClick, selected) {
  const r = el("div", `trace-row ${rowHealth(t)}${selected ? " sel" : ""}`);
  const flags = [];
  if (!t.ok) flags.push("err");
  if (t.all_general) flags.push("all-gen");
  else if (!t.patch_served) flags.push("no-patch");
  if (t.salvaged) flags.push("salvage");
  if (t.n_clamped) flags.push(t.n_clamped + " clamp");
  r.innerHTML =
    `<div class="q">${esc(t.query || "(no query)")}</div>` +
    stacked(t.source_distribution) +
    `<div class="row2"><span class="ts">${esc(t.ts || "")}</span>` +
    `<span class="flags mono muted">${esc(flags.join(" · "))}</span></div>`;
  r.onclick = onClick;
  return r;
}

/* --- stage renderers: each returns {status, hl, body, lever, raw} --- */
const cls = (v, warn, bad) => (bad ? "bad" : warn ? "warn" : "ok");
const STAGES = [
  ["classify", "Query & classification", rec => {
    const c = rec.classify || {};
    return { status: "ok", hl: c.recipe_shaped ? "recipe-shaped" : "factual",
      body: kv([["recipe_shaped", String(c.recipe_shaped)],
                ["note", "patch path always treats query as recipe-shaped — this flag is diagnostic only (matters for ask.py)"]]),
      lever: "Retrieval mode (regex) — affects Q&A path only", raw: c };
  }],
  ["pool", "Retrieval pool (k=25)", rec => {
    const p = rec.pool || {}; const lanes = p.per_lane_contribution_counts || {};
    const patchN = lanes.patch || 0;
    const rows = (p.pool_chunks || []).slice(0, 8).map(c =>
      `<tr><td class="cid">${esc(c.chunk_id)}</td><td><span class="badge ${esc(c.source_type)}">${esc(c.source_type)}</span></td>` +
      `<td>${(c.rrf ?? 0).toFixed?.(4) ?? c.rrf}</td><td>${(c.sim ?? 0)}</td></tr>`).join("");
    return { status: cls(0, patchN === 0, false), hl: `patch lane ${patchN}`,
      body: kv([["lanes", (p.lanes_present_in_pool || []).join(", ")],
                ["per-lane counts", JSON.stringify(lanes)],
                ["similarity range", (p.top_similarity_range || []).join(" – ")]]) +
        (rows ? `<table class="tbl" style="margin-top:9px"><tr><th>chunk</th><th>lane</th><th>rrf</th><th>sim</th></tr>${rows}</table>` : ""),
      lever: patchN === 0 ? "Corpus — no patch exemplar reached the pool for this sound" : "Retrieval mode",
      raw: p };
  }],
  ["rerank", "Actionability rerank + RRF", rec => {
    const r = rec.rerank || {}; const ov = (r.deduped_to_overflow || []).length;
    const swaps = (r.rank_before_after || []).filter(x => x[1] !== x[2]).length;
    return { status: "ok", hl: `${swaps} reordered`,
      body: kv([["chunks deduped to overflow", ov],
                ["reordered by actionability", swaps],
                ["note", "full per-chunk actionability components in the raw record →"]]),
      lever: "Retrieval mode — tune _PARAM_TERMS / _CHATTER / ACTION_WEIGHT", raw: r };
  }],
  ["diversify", "Diversity injection", rec => {
    const d = rec.diversify || {}; const o = d.patch_injection_outcome;
    const bad = o === "no_candidate_in_pool" || o === "all_below_floor";
    const below = d.candidates_below_floor || [];
    return { status: cls(0, false, bad), hl: o || "—",
      body: kv([["patch_injection_outcome", o, bad ? "bad" : "ok"],
                ["groups satisfied", (d.groups_already_satisfied || []).join(", ")],
                ["injected swaps", (d.injected_swaps || []).length],
                ["candidates below floor", below.length ? below.map(c => `${c.chunk_id}(${c.action})`).join(", ") : "none",
                 below.length ? "warn" : ""]]),
      lever: o === "all_below_floor" ? "Retrieval mode — lower ACTION_FLOOR / widen _PARAM_TERMS"
        : bad ? "Corpus — acquire patch exemplars for this sound" : "—",
      raw: d };
  }],
  ["adapt", "Grounding block (retrieve-and-adapt)", rec => {
    const a = rec.adapt || {}; const ids = a.patch_ids_selected || [];
    const ne = a.neighbor_outcome || ""; const neBad = ne.startsWith("Exception");
    return { status: cls(0, ids.length === 0 || neBad, false), hl: `${a.num_patch_exemplars ?? 0} exemplars`,
      body: kv([["patch_ids_selected", ids.join(", "), ids.length ? "" : "warn"],
                ["files missing", (a.patch_files_missing || []).join(", ")],
                ["neighbor_outcome", ne, neBad ? "bad" : ""],
                ["neighbor_distance", a.neighbor_distance],
                ["block size (chars)", a.block_char_len]]),
      lever: ids.length === 0 ? "Corpus / retrieval — model had no real patch to adapt"
        : neBad ? "Corpus — patch JSON integrity (neighbor expansion threw)" : "—",
      raw: a };
  }],
  ["prompt", "Prompt assembly", rec => {
    const p = rec.prompt || {}; const big = (p.prompt_total_chars || 0) > 14000;
    return { status: cls(0, big, false), hl: `${p.prompt_total_chars ?? "?"} chars`,
      body: kv([["context chunks", p.num_context_chunks],
                ["est. input tokens", p.est_input_tokens],
                ["schema present", String(p.schema_present)],
                ["labels", (p.chunk_labels_in_prompt || []).join(", ")]]),
      lever: big ? "System prompt — trim real_patch_block to leave output headroom" : "—", raw: p };
  }],
  ["llm", "LLM output", rec => {
    const l = rec.llm || {}; const trunc = l.stop_reason === "max_tokens";
    return { status: cls(0, false, trunc), hl: l.stop_reason || "—",
      body: kv([["stop_reason", l.stop_reason, trunc ? "bad" : ""],
                ["output tokens", `${l.usage_output_tokens ?? "?"} / ${rec.max_tokens ?? "?"}`, trunc ? "bad" : ""],
                ["model", l.model_returned],
                ["request_id", l.request_id],
                ["api_exception", l.api_exception, l.api_exception ? "bad" : ""]]) +
        `<div class="muted" style="margin-top:8px">full raw output in the raw record →</div>`,
      lever: trunc ? "System prompt (cap change count) or raise max_tokens" : "—", raw: l };
  }],
  ["extract", "JSON parse", rec => {
    const e = rec.extract || {}; const salv = e.extraction_path === "salvage";
    return { status: cls(0, salv || e.extraction_path === "regex_object", false), hl: e.extraction_path || "—",
      body: kv([["extraction_path", e.extraction_path, salv ? "warn" : ""],
                ["had markdown fences", String(e.had_markdown_fences)],
                ["salvaged change count", e.salvaged_change_count],
                ["raw_parse_error", e.raw_parse_error, e.raw_parse_error ? "warn" : ""]]),
      lever: salv ? "System prompt — output got truncated; salvage kept complete changes only" : "—", raw: e };
  }],
  ["validate", "Validation / clamping", rec => {
    const v = rec.validate || {}; const clamped = v.clamped_values || [];
    const coerced = v.coerced_toggle || []; const probs = v.problems || [];
    const warn = clamped.length || coerced.length || probs.length || (v.select_fuzzy_matched || []).length;
    return { status: cls(0, warn, false), hl: `${v.clean_change_count ?? "?"} / ${v.input_change_count ?? "?"} kept`,
      body: kv([["clamped", clamped.map(c => `${c.param} ${c.proposed}→${c.clamped}`).join(", "), clamped.length ? "warn" : ""],
                ["coerced toggle", coerced.map(c => `${c.param} '${c.proposed}'→${c.bool}`).join(", "), coerced.length ? "warn" : ""],
                ["fuzzy select", (v.select_fuzzy_matched || []).map(c => `${c.param} '${c.proposed}'→${c.matched}`).join(", ")],
                ["noop dropped", (v.noop_dropped || []).join(", ")],
                ["problems", probs.join("; "), probs.length ? "warn" : ""]]),
      lever: clamped.length || coerced.length ? "System prompt — tighten range / toggle vocabulary" : "—", raw: v };
  }],
  ["patch", "Final patch", rec => {
    const p = rec.patch || {}; const cc = p.change_count ?? 0;
    const offTarget = cc < 10 || cc > 25; const nnd = p.narrated_not_delivered || [];
    return { status: cls(0, offTarget || nnd.length, false), hl: `${cc} changes`,
      body: kv([["patch_name", p.patch_name],
                ["change_count (target 10–25)", cc, offTarget ? "warn" : "ok"],
                ["narrated but not delivered", nnd.join(", "), nnd.length ? "warn" : ""],
                ["non-default params", Object.keys(p.resolved_nondefault || {}).length]]),
      lever: nnd.length ? "System prompt — don't narrate moves that get dropped" : "—", raw: p };
  }],
  ["provenance", "Provenance", rec => {
    const pr = rec.provenance || {}; const dist = pr.source_distribution || {};
    const total = Object.values(dist).reduce((a, b) => a + b, 0);
    const allGen = total > 0 && (dist.general || 0) === total;
    const unmatched = pr.unmatched_citations || [];
    return { status: cls(0, pr.mixer_all_down || unmatched.length, allGen), hl: allGen ? "ALL general" : "mixed",
      body: stacked(dist, true) + provLegend(dist) +
        kv([["unmatched citations", unmatched.join(", "), unmatched.length ? "bad" : ""],
            ["mixer all down", String(pr.mixer_all_down), pr.mixer_all_down ? "bad" : ""]]),
      lever: allGen ? "Corpus / retrieval — nothing from the corpus shaped this patch"
        : unmatched.length ? "System prompt — tighten the citation contract" : "—", raw: pr };
  }],
  ["sysex", "SysEx (MIDI out)", rec => {
    const s = rec.sysex || {}; const ok = s.outcome === "ok";
    return { status: cls(0, false, s.outcome && !ok), hl: ok ? "ok" : (s.outcome || "—"),
      body: kv([["outcome", s.outcome, ok ? "ok" : "bad"],
                ["name truncated", String(s.name_truncated)]]),
      lever: ok ? "—" : "Encoder — surface, don't hide (ISSUE-2)", raw: s };
  }],
];

function showStageRaw(rail, title, raw) {
  rail.innerHTML = `<p class="rail-title">${esc(title)}</p>` + rawJSON(raw);
}

function renderTrace(rec, detail, rail) {
  detail.innerHTML = "";
  const head = el("div");
  if (rec.ok === false) {
    head.innerHTML = `<div class="stage-head"><h1>Generation failed</h1></div>` +
      `<div class="problems">${esc(rec.error || "unknown error")}</div>`;
    head.innerHTML += kv([["query", rec.query], ["trace_id", rec.trace_id], ["ts", rec.ts], ["wall_ms", rec.wall_ms]]);
    detail.appendChild(head);
    return;
  }
  const p = rec.patch || {};
  head.innerHTML =
    `<div class="stage-head"><h1>${esc(p.patch_name || "Untitled")}</h1>` +
    `<button class="ghost promo-btn" title="Draft a golden-set entry from this trace">＋ Promote to golden</button>${helpIcon("golden.promote")}</div>` +
    `<div class="qq" style="font-style:italic;color:var(--text-faint)">“${esc(rec.query || "")}” · ${esc(rec.trace_id || "")}</div>` +
    `<div class="envelope"><span><b>${esc(rec.model || "")}</b>${helpIcon("env.model")}</span>` +
    `<span>grounding <b>${esc(rec.grounding || "")}</b>${helpIcon("env.grounding")}</span>` +
    `<span>k=<b>${rec.k}</b>${helpIcon("env.k")}</span>` +
    `<span>temp <b>${rec.temperature}</b>${helpIcon("env.temperature")}</span>` +
    `<span>floor <b>${rec.action_floor}</b>${helpIcon("env.action_floor")}</span>` +
    `<span>rrf_k <b>${rec.rrf_k}</b>${helpIcon("env.rrf_k")}</span><span><b>${rec.wall_ms}</b> ms</span></div>`;
  detail.appendChild(head);
  const pb = head.querySelector(".promo-btn");
  if (pb) pb.onclick = () => openPromote(rec);

  STAGES.forEach(([key, title, build]) => {
    let info; try { info = build(rec); } catch { info = { status: "warn", hl: "render error", body: "", lever: "—", raw: rec[key] }; }
    const card = el("div", `stage-card ${info.status}`);
    card.innerHTML =
      `<div class="ch"><span class="ttl">${esc(title)}${helpIcon("stage." + key)}</span><span class="hl ${info.status}">${esc(info.hl)}</span></div>` +
      `<div class="stage-body">${info.body || ""}</div>` +
      (info.lever && info.lever !== "—" ? `<div class="lever">LEVER → <b>${esc(info.lever)}</b></div>` : "");
    card.onclick = () => {
      $$(".stage-card", detail).forEach(c => c.classList.remove("sel"));
      card.classList.add("sel");
      showStageRaw(rail, title, info.raw);
    };
    detail.appendChild(card);
  });
}

/* ====================================================================== *
 *  OVERVIEW (M2)                                                         *
 * ====================================================================== */
const LIVE_TILES = [
  ["all_general_rate", "ALL-GENERAL", "live.all_general"],
  ["no_patch_served_rate", "NO PATCH SERVED", "live.no_patch"],
  ["salvage_rate", "SALVAGE/TRUNC", "live.salvage"],
  ["clamp_rate", "SILENT CLAMP", "live.clamp"],
  ["hallucinated_cite_rate", "BAD CITATIONS", "live.bad_citations"],
  ["sysex_fail_rate", "SYSEX FAIL", "live.sysex_fail"],
];

function kpiTile(k, onClick) {
  const health = kpiHealth(k.value, k.target, k.direction);
  const t = el("div", "stat click");
  t.innerHTML =
    `<div class="n ${health || "amber"}">${esc(fmtVal(k.value, k.fmt))}</div>` +
    `<div class="k">${esc(k.metric)}${helpIcon("kpi." + k.kind)}` +
    `${k.provisional ? '<span class="prov">PROV</span>' + helpIcon("kpi.provisional") : ""}</div>` +
    (k.kind === "recall" ? sparkline(k.history, k.target) : "");
  t.onclick = onClick;
  return t;
}

register({
  id: "overview", label: "Overview",
  mount: async (main, rail, params) => {
    setStatus("working", "loading overview…");
    const [data, recent] = await Promise.all([
      jget("/api/overview"), jget("/api/traces?limit=8"),
    ]);
    setStatus("done", `${data.live.n_traces} live trace${data.live.n_traces === 1 ? "" : "s"} · ${data.eval.length} eval kinds`);
    $("#dataAsOf").textContent = recent.traces.length ? "latest " + recent.traces[0].ts
      : (data.eval[0] ? "eval " + data.eval[0].ts : "no data yet");

    const ov = el("div", "ov"); main.appendChild(ov);

    // --- eval health KPIs ---
    ov.appendChild(secTitle("Eval health — latest per kind", "kpi.threshold"));
    const kstats = el("div", "stats"); ov.appendChild(kstats);
    if (!data.eval.length) kstats.appendChild(el("div", "empty-note", "No eval results yet."));
    data.eval.forEach(k => {
      if (k.kind === "recall") k.history = data.recall_history;
      kstats.appendChild(kpiTile(k, () => showKpi(rail, k)));
    });

    // --- live generation health (rolling) ---
    ov.appendChild(secTitle(`Live generation health — rolling last ${data.live.n_traces || 0}`, "live.intro"));
    if (!data.live.n_ok) {
      ov.appendChild(el("div", "empty-note", "No live traces yet — generate patches in <a href='studio.html'>Studio</a>."));
    } else {
      const lstats = el("div", "stats");
      LIVE_TILES.forEach(([key, label, hk]) => {
        const v = data.live[key];
        const t = el("div", "stat");
        t.innerHTML = `<div class="n ${rateHealth(v)}">${v == null ? "—" : (v * 100).toFixed(0) + "%"}</div><div class="k">${label}${helpIcon(hk)}</div>`;
        lstats.appendChild(t);
      });
      const cc = data.live.mean_change_count;
      const ccH = cc == null ? "" : (cc >= 10 && cc <= 25 ? "ok" : "warn");
      const extra = el("div", "stat");
      extra.innerHTML = `<div class="n ${ccH}">${cc ?? "—"}</div><div class="k">MEAN CHANGES (10–25)${helpIcon("live.mean_changes")}</div>`;
      lstats.appendChild(extra);
      const w = el("div", "stat");
      w.innerHTML = `<div class="n">${data.live.mean_wall_ms ?? "—"}</div><div class="k">MEAN MS${helpIcon("live.mean_ms")}</div>`;
      lstats.appendChild(w);
      ov.appendChild(lstats);
    }

    // --- recent traces ---
    ov.appendChild(secTitle("Recent traces", "trace.what_is"));
    if (!recent.traces.length) {
      ov.appendChild(el("div", "empty-note", "No traces yet."));
    } else {
      const list = el("div"); list.style.cssText = "display:flex;flex-direction:column;gap:8px;max-width:680px;";
      recent.traces.forEach(t => list.appendChild(traceRow(t, () => go("trace", { id: t.trace_id }), false)));
      ov.appendChild(list);
    }

    // rail: honesty notes
    rail.innerHTML = `<p class="rail-title">Reading these numbers</p>` +
      `<div class="tip"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>` +
      `Tiles tagged <span class="prov">PROV</span> are assistant-judged or carry a known artifact — spot-check before acting. Click any KPI for its caveat.</div>` +
      `<p class="empty-note">Colour marks threshold state only: green = at/above target, amber = near, red = below. Neutral tiles have no hard target.</p>`;
  },
});

function showKpi(rail, k) {
  rail.innerHTML = `<p class="rail-title">${esc(k.metric)}</p>` +
    kv([["value", fmtVal(k.value, k.fmt)], ["target", k.target ?? "—"],
        ["run", k.run], ["ts", k.ts], ["file", k.file],
        ...Object.entries(k.extra || {}).map(([kk, vv]) => [kk, JSON.stringify(vv)])]) +
    (k.provisional ? `<div class="problems" style="margin-top:12px">${esc(k.caveat || "Provisional — pending builder review.")}</div>`
      : k.caveat ? `<div class="tip" style="margin-top:12px"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>${esc(k.caveat)}</div>` : "");
}

register({
  id: "trace", label: "Trace",
  mount: async (main, rail, params) => {
    setStatus("working", "loading traces…");
    const wrap = el("div", "dash-main");
    const list = el("aside", "trace-list scroll");
    const detail = el("div", "trace-detail scroll");
    wrap.append(list, detail); main.appendChild(wrap);
    const chips = el("div", "filter-chips");
    const body = el("div"); body.style.cssText = "display:flex;flex-direction:column;gap:9px;";
    list.append(chips, body);
    let active = params.filter || "all";
    let selected = params.id || null;

    async function openTrace(id) {
      selected = id;
      $$(".trace-row", body).forEach(r => r.classList.toggle("sel", r.dataset.id === id));
      detail.innerHTML = `<div class="empty-note">loading trace…</div>`;
      try {
        const rec = await jget("/api/trace?id=" + encodeURIComponent(id));
        renderTrace(rec, detail, rail);
        const qs = new URLSearchParams({ v: "trace", id }); history.replaceState(null, "", "?" + qs);
      } catch (e) { detail.innerHTML = `<div class="problems">${esc(e.message)}</div>`; }
    }

    async function load() {
      chips.innerHTML = "";
      FILTERS.forEach(f => {
        const c = el("button", "chip" + (f === active ? " on" : ""), esc(f));
        c.onclick = () => {
          active = f;
          if (CURRENT) CURRENT.params.filter = f === "all" ? undefined : f;  // survive Refresh
          const qs = new URLSearchParams({ v: "trace", ...(selected ? { id: selected } : {}), ...(f !== "all" ? { filter: f } : {}) });
          history.replaceState(null, "", "?" + qs);
          load();
        };
        chips.appendChild(c);
      });
      chips.insertAdjacentHTML("beforeend", helpIcon("trace.filters"));
      body.innerHTML = `<div class="muted pad">loading…</div>`;
      const { traces } = await jget("/api/traces?limit=200" + (active !== "all" ? "&filter=" + active : ""));
      setStatus("done", `${traces.length} trace${traces.length === 1 ? "" : "s"}`);
      $("#dataAsOf").textContent = traces.length ? "latest " + traces[0].ts : "no traces yet";
      body.innerHTML = "";
      if (!traces.length) {
        body.appendChild(el("div", "empty-note",
          active !== "all" ? `No traces match “${esc(active)}”.`
            : "No traces yet — generate a patch in <a href='studio.html'>Studio</a> and refresh."));
        detail.innerHTML = `<div class="empty-note">Generate a patch to populate the trace log.</div>`;
        return;
      }
      traces.forEach(t => {
        const r = traceRow(t, () => openTrace(t.trace_id), t.trace_id === selected);
        r.dataset.id = t.trace_id;
        body.appendChild(r);
      });
      if (selected && traces.some(t => t.trace_id === selected)) openTrace(selected);
      else detail.innerHTML = `<div class="empty-note">Select a trace to walk its pipeline, stage by stage.</div>`;
    }
    await load();
  },
});

/* ====================================================================== *
 *  RUN-DIFF (M3)                                                         *
 * ====================================================================== */
function labelWrap(label, node) {
  const w = el("label", "field");
  w.appendChild(el("span", "field-k", esc(label)));
  w.appendChild(node);
  return w;
}
const deltaCls = (d, dir) => d == null || d === 0 ? "" : ((dir === "high" ? d > 0 : d < 0) ? "t-ok" : "t-bad");
const fmtDelta = d => d == null ? "—" : (d > 0 ? "+" : "") + Number(d).toFixed(3);
const recallWord = v => v === 1 ? "hit" : v === 0 ? "miss" : v;

function chunkList(chunks, targetMatch) {
  const tgt = targetMatch && targetMatch.chunk_id;
  if (!chunks || !chunks.length) return `<div class="empty-note">— none —</div>`;
  return `<ol class="chunklist">` + chunks.map(c =>
    `<li class="${c === tgt ? "is-target" : ""}">${esc(c)}${c === tgt ? " ← target" : ""}</li>`).join("") + `</ol>`;
}
function showRecallMiss(rail, it) {
  const tgt = (it.detail_a.matched || it.detail_b.matched || {});  // B supplies it for MISS→HIT rows
  rail.innerHTML = `<p class="rail-title">${esc(it.id)} · recall</p>` +
    kv([["A", recallWord(it.a)], ["B", recallWord(it.b)], ["target", tgt.chunk_id]]) +
    `<div class="section-title">A · top-5</div>` + chunkList(it.detail_a.top_chunks, tgt) +
    `<div class="section-title">B · top-5</div>` + chunkList(it.detail_b.top_chunks, tgt) +
    `<div class="tip" style="margin-top:12px"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>If the target dropped out of B's top-5, the chunks now above it are the displacers (D-027). If the target itself looks wrong, this is eval-staleness — re-target the golden entry, don't chase recall (D-015/D-029).</div>`;
}

function renderDiff(d, out, rail) {
  const dir = d.direction || "high";
  const good = d.delta == null ? null : (dir === "high" ? d.delta >= 0 : d.delta <= 0);
  const dcls = d.delta == null || d.delta === 0 ? "" : (good ? "delta-pos" : "delta-neg");
  out.innerHTML =
    `<div class="diff-band"><div><div class="k">${esc(d.metric)}${helpIcon("diff.delta")}</div>` +
    `<div class="band-vals"><span class="mono">${esc(fmtVal(d.a.value, d.fmt))}</span> → ` +
    `<span class="mono">${esc(fmtVal(d.b.value, d.fmt))}</span></div></div>` +
    `<div class="band-delta ${dcls}">${esc(fmtDelta(d.delta))}</div></div>` +
    `<div class="muted" style="margin:8px 0 4px">A: ${esc(d.a.label)} (${esc(d.a.ts)}) · B: ${esc(d.b.label)} (${esc(d.b.ts)}) · ${d.n_common} shared queries${helpIcon("diff.shared_queries")}</div>` +
    (d.n_common === 0 ? `<div class="tip"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>These two runs share no query ids — likely different golden sets (e.g. v1 vs v2). Headline and per-bucket deltas still apply; pick two runs of the same set for a per-query regression list.</div>` : "");

  if (d.tripwire) {
    const tw = d.tripwire;
    out.innerHTML += `<div class="${tw.pass ? "tip" : "problems"}"><b>v1 tripwire ${tw.pass ? "PASS" : "FAIL"}</b>${helpIcon("diff.tripwire")} — ` +
      `${esc(fmtVal(tw.value, "ratio"))} vs ${tw.target}. ${esc(tw.note)}</div>`;
  }
  if (d.per_bucket.length) {
    out.innerHTML += `<div class="section-title">Per-bucket${helpIcon("diff.per_bucket")}</div><table class="tbl"><tr><th>bucket</th><th>A</th><th>B</th><th>Δ</th></tr>` +
      d.per_bucket.map(b => `<tr><td class="cid">${esc(b.bucket)}</td><td>${b.a ?? "—"}</td><td>${b.b ?? "—"}</td>` +
        `<td class="${deltaCls(b.delta, dir)}">${esc(fmtDelta(b.delta))}</td></tr>`).join("") + `</table>`;
  }
  const sect = (title, items, sign) => {
    let h = `<div class="section-title">${title}${helpIcon("diff.regressed_improved")}</div>`;
    if (!items.length) return h + `<div class="empty-note">none</div>`;
    return h + `<div class="reg-list">` + items.map((it, i) =>
      `<div class="reg-row ${sign}" data-i="${i}" data-sign="${sign}"><span class="cid mono">${esc(it.id)}</span>` +
      `<span class="muted">b${it.bucket ?? "?"}</span>` +
      `<span class="mono">${esc(d.kind === "recall" ? recallWord(it.a) : it.a)} → ${esc(d.kind === "recall" ? recallWord(it.b) : it.b)}</span></div>`).join("") + `</div>`;
  };
  out.innerHTML += sect(`Regressed (${d.regressed.length})`, d.regressed, "neg") +
    sect(`Improved (${d.improved.length})`, d.improved, "pos");

  if (d.kind === "recall") {
    $$(".reg-row", out).forEach(row => {
      row.style.cursor = "pointer";
      row.onclick = () => {
        const items = row.dataset.sign === "neg" ? d.regressed : d.improved;
        showRecallMiss(rail, items[+row.dataset.i]);
      };
    });
  }
}

register({
  id: "diff", label: "Run-Diff",
  mount: async (main, rail, params) => {
    setStatus("working", "loading eval runs…");
    const { runs } = await jget("/api/eval/runs");
    setStatus("done", `${runs.length} eval runs`);
    if (!runs.length) { main.appendChild(el("div", "ov", "<div class='empty-note'>No eval results to diff.</div>")); return; }
    const kinds = [...new Set(runs.map(r => r.kind))];
    const ov = el("div", "ov"); main.appendChild(ov);
    const pick = el("div", "picker-row"); ov.appendChild(pick);
    const kindSel = el("select", "rdsel"), aSel = el("select", "rdsel"), bSel = el("select", "rdsel");
    kinds.forEach(k => kindSel.add(new Option(k, k)));
    pick.append(labelWrap("metric", kindSel), labelWrap("baseline · A", aSel), labelWrap("candidate · B", bSel));
    const outWrap = el("div"); outWrap.style.marginTop = "18px"; ov.appendChild(outWrap);

    async function run() {
      if (aSel.value === bSel.value) { outWrap.innerHTML = `<div class="tip">Pick two different runs to compare.</div>`; return; }
      outWrap.innerHTML = `<div class="empty-note">loading diff…</div>`;
      try {
        const d = await jget(`/api/eval/diff?a=${encodeURIComponent(aSel.value)}&b=${encodeURIComponent(bSel.value)}`);
        renderDiff(d, outWrap, rail);
      } catch (e) { outWrap.innerHTML = `<div class="problems">${esc(e.message)}</div>`; }
    }
    function fillRuns() {
      const rs = runs.filter(r => r.kind === kindSel.value);  // newest first
      [aSel, bSel].forEach(s => { s.innerHTML = ""; rs.forEach(r => s.add(new Option(`${r.ts || "?"} · ${r.label}`, r.file))); });
      bSel.selectedIndex = 0;
      aSel.selectedIndex = Math.min(1, rs.length - 1);
      run();
    }
    kindSel.onchange = fillRuns; aSel.onchange = run; bSel.onchange = run;
    kindSel.value = params.kind && kinds.includes(params.kind) ? params.kind
      : (kinds.includes("recall") ? "recall" : kinds[0]);
    fillRuns();
  },
});

/* ====================================================================== *
 *  CORPUS HEALTH (M4)                                                    *
 * ====================================================================== */
function heatClass(v) { return v == null ? "hm-na" : v >= 3 ? "hm-ok" : v >= 1 ? "hm-warn" : "hm-bad"; }
function bars(obj, max) {
  const m = max || Math.max(1, ...Object.values(obj));
  return `<div class="barlist">` + Object.entries(obj).map(([k, v]) =>
    `<div class="barrow"><span class="bk">${esc(k)}</span>` +
    `<span class="bb"><span style="width:${(v / m * 100).toFixed(1)}%"></span></span>` +
    `<span class="bn mono">${v}</span></div>`).join("") + `</div>`;
}

register({
  id: "corpus", label: "Corpus",
  mount: async (main, rail) => {
    setStatus("working", "scanning corpus (lazy, first open is slow)…");
    const c = await jget("/api/corpus");
    setStatus("done", `${c.n_chunks} chunks · ${Object.keys(c.by_source_type).length} source types`);
    $("#dataAsOf").textContent = c.model || "";
    const ov = el("div", "ov"); main.appendChild(ov);

    // coverage heatmap
    const cov = c.coverage || {};
    ov.appendChild(secTitle("Coverage — families × characters (independent sources/cell)", "corpus.coverage"));
    if (cov.cells) {
      const pct = cov.pct_cells_3plus;
      ov.appendChild(htmlNode(`<div class="muted" style="margin-bottom:8px">` +
        `<span class="n ${pct >= 0.9 ? "t-ok" : "t-bad"} mono" style="font-size:15px">${(pct * 100).toFixed(0)}%</span> of cells have ≥3 sources (target 90%). ` +
        `Fixed-filename report — no trend until the writer timestamps (now added).</div>`));
      let h = `<table class="hm"><tr><th></th>` + cov.characters.map(ch => `<th>${esc(ch)}</th>`).join("") + `</tr>`;
      cov.families.forEach(f => {
        h += `<tr><th class="hm-fam">${esc(f)}</th>`;
        cov.characters.forEach(ch => {
          const v = cov.cells[`${f}|${ch}`];
          h += `<td class="${heatClass(v)}" title="${esc(f)} × ${esc(ch)}: ${v == null ? "excluded" : v}">${v == null ? "·" : v}</td>`;
        });
        h += `</tr>`;
      });
      ov.appendChild(htmlNode(h + `</table>`));
      ov.appendChild(htmlNode(`<div class="legend"><span><i class="hm-ok"></i>≥3</span><span><i class="hm-warn"></i>1–2 (gap)</span><span><i class="hm-bad"></i>0</span><span><i class="hm-na"></i>excluded</span></div>`));
    } else ov.appendChild(el("div", "empty-note", "No coverage_report.json — run eval/coverage_report.py --write."));

    // composition + retrieval
    ov.appendChild(secTitle("Corpus composition (chunks by source type)", "corpus.composition"));
    ov.appendChild(htmlNode(bars(c.by_source_type)));

    ov.appendChild(secTitle("Retrieval reach (across golden recall runs)", "corpus.retrieval_reach"));
    const r = c.retrieval;
    const st = el("div", "stats");
    [["distinct chunks retrieved", r.distinct_chunks_retrieved, "corpus.retrieval_reach"],
     ["never retrieved", c.dead.never_retrieved, "corpus.dead"],
     ["recall runs scanned", r.n_recall_runs, null]].forEach(([k, v, hk]) => {
      const t = el("div", "stat"); t.innerHTML = `<div class="n mono">${v}</div><div class="k">${k}${hk ? helpIcon(hk) : ""}</div>`; st.appendChild(t);
    });
    ov.appendChild(st);
    ov.appendChild(htmlNode(`<div class="tip"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>${esc(c.dead.note)}</div>`));
    ov.appendChild(el("div", "section-title", "Served by source type"));
    ov.appendChild(htmlNode(bars(r.served_by_source_type)));
    ov.appendChild(secTitle("Most-retrieved chunks (over-relied head)", "corpus.top_chunks"));
    ov.appendChild(htmlNode(`<table class="tbl"><tr><th>chunk</th><th>type</th><th>hits</th></tr>` +
      r.top_chunks.map(t => `<tr><td class="cid">${esc(t.chunk_id)}</td><td><span class="badge ${esc(t.source_type)}">${esc(t.source_type)}</span></td><td>${t.freq}</td></tr>`).join("") + `</table>`));

    rail.innerHTML = `<p class="rail-title">Corpus → which lever</p>` +
      `<p class="empty-note">A red/amber heatmap cell predicts all-“general synthesis” patches for that sound — it's the acquisition shopping list. A whole lane absent from “served by source type” means retrieval never reaches it. Both point at the <b>corpus</b> lever.</p>` +
      (cov.gaps && cov.gaps.length ? `<div class="section-title">Gap cells (&lt;3 sources)${helpIcon("corpus.gaps")}</div>` +
        cov.gaps.map(([k, v]) => `<div class="reg-row neg"><span class="cid mono">${esc(k)}</span><span class="mono">${v}</span></div>`).join("")
        : `<div class="tip" style="margin-top:12px">All cells ≥3 sources.</div>`);
  },
});

/* ====================================================================== *
 *  GOLDEN SET (M4)                                                       *
 * ====================================================================== */
register({
  id: "golden", label: "Golden",
  mount: async (main, rail) => {
    setStatus("working", "loading golden set…");
    const g = await jget("/api/golden");
    setStatus("done", `${g.records.length} golden entries`);
    const ov = el("div", "ov"); main.appendChild(ov);
    const gate = g.gate;

    ov.appendChild(htmlNode(
      `<div class="${gate.ok ? "tip" : "problems"}"><b>Reachability gate ${gate.ok ? "PASS" : "FAIL"}</b>${helpIcon("golden.gate")} — ` +
      `${gate.total} entries; ${gate.unreachable.length} unreachable, ${gate.partial.length} partial, ${gate.missing_patch.length} missing patch. ` +
      `(mirrors check_targets.py — re-run it after edits, D-015)</div>`));
    if (gate.unreachable.length) {
      ov.appendChild(el("div", "section-title", "Unreachable targets"));
      ov.appendChild(htmlNode(gate.unreachable.map(u =>
        `<div class="reg-row neg"><span class="cid mono">${esc(u.id)}</span><span class="muted">${esc(u.file)}</span><span class="mono">${esc(JSON.stringify(u.targets))}</span></div>`).join("")));
    }

    // bucket coverage
    const byBucket = {};
    g.records.forEach(r => { const k = "bucket " + r.bucket; byBucket[k] = (byBucket[k] || 0) + 1; });
    ov.appendChild(secTitle("Inventory by bucket", "golden.buckets"));
    ov.appendChild(htmlNode(bars(byBucket)));

    // table
    ov.appendChild(secTitle(`All entries (${g.records.length})`, "golden.targets"));
    const rows = g.records.map(r =>
      `<tr><td class="cid">${esc(r.id)}</td><td>${r.bucket}</td><td class="gq">${esc((r.query || "").slice(0, 80))}</td>` +
      `<td>${esc((r.expected_targets || []).map(t => t.source_type + ":" + t.match).join(", "))}</td>` +
      `<td class="muted">${esc(r.file.replace("golden_set", "").replace(".jsonl", "") || "v1")}</td></tr>`).join("");
    ov.appendChild(htmlNode(`<table class="tbl gold"><tr><th>id</th><th>b</th><th>query</th><th>targets</th><th>set</th></tr>${rows}</table>`));

    rail.innerHTML = `<p class="rail-title">Growing the golden set</p>` +
      `<p class="empty-note">The golden set is only as good as its coverage of real failures. Open a failing request in <b>Trace</b> and click <b>＋ Promote to golden</b> to draft an entry from the served chunks (§2.6); it's appended only after you confirm (D-015), then re-run check_targets.py.</p>`;
  },
});

/* ---- promote-to-golden dialog (opened from a trace) ---- */
function goldenDraft(rec) {
  const seen = new Set(), targets = [];
  (rec.final_chunks || []).forEach(c => {
    const t = c.source_type === "manual" ? { source_type: "manual", match: c.section }
      : { source_type: c.source_type, match: c.source_id };
    const key = t.source_type + "|" + t.match;
    if (t.match && !seen.has(key)) { seen.add(key); targets.push(t); }
  });
  const slug = (rec.query || "q").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 28).replace(/(^-|-$)/g, "");
  return { id: "v2-b2-" + (slug || "promoted"), query: rec.query, bucket: 2,
    expected_targets: targets.slice(0, 4), phrasing: "promoted from trace " + rec.trace_id, notes: "" };
}
function openPromote(rec) {
  const back = el("div", "promo-backdrop");
  const pop = el("div", "popover promo");
  pop.innerHTML =
    `<div class="pop-head"><b>Promote to golden_set_v2</b><button class="x" title="close">✕</button></div>` +
    `<p class="pop-note">Verbatim query; targets pre-filled from the served chunks (§2.6). Edit, then append — it lands only on your confirm (D-015). Re-run check_targets.py after.</p>` +
    `<textarea class="promo-ta" spellcheck="false"></textarea>` +
    `<div class="promo-msg muted"></div>` +
    `<div style="display:flex;gap:8px;margin-top:10px"><button class="ghost cancel" style="flex:1">Cancel</button>` +
    `<button class="primary conf" style="flex:1">Append</button></div>`;
  back.appendChild(pop); document.body.appendChild(back);
  $(".promo-ta", pop).value = JSON.stringify(goldenDraft(rec), null, 2);
  const close = () => back.remove();
  $(".x", pop).onclick = close; $(".cancel", pop).onclick = close;
  back.onclick = e => { if (e.target === back) close(); };
  $(".conf", pop).onclick = async () => {
    const msg = $(".promo-msg", pop);
    let record;
    try { record = JSON.parse($(".promo-ta", pop).value); }
    catch (e) { msg.className = "promo-msg t-bad"; msg.textContent = "Invalid JSON: " + e.message; return; }
    $(".conf", pop).disabled = true; msg.className = "promo-msg muted"; msg.textContent = "appending…";
    try {
      const r = await fetch("/api/golden/promote", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record }),
      });
      const d = await r.json();
      if (!r.ok || d.error) throw new Error(d.error || "HTTP " + r.status);
      msg.className = "promo-msg t-ok";
      msg.innerHTML = `✓ appended as <b>${esc(d.id)}</b>. ${esc(d.note || "")}`;
      $(".conf", pop).style.display = "none"; $(".cancel", pop).textContent = "Close";
    } catch (e) { msg.className = "promo-msg t-bad"; msg.textContent = "Failed: " + e.message; $(".conf", pop).disabled = false; }
  };
}

/* ====================================================================== *
 *  BOOT                                                                  *
 * ====================================================================== */
function boot() {
  initHelp();
  const rh = $("#ragHelp"); if (rh) rh.innerHTML = helpIcon("rag.what_is");
  const q = new URLSearchParams(location.search);
  $("#refreshBtn").onclick = () => go(CURRENT ? CURRENT.id : DEFAULT_VIEW, CURRENT ? CURRENT.params : {});
  const params = {};
  if (q.get("id")) params.id = q.get("id");
  if (q.get("filter")) params.filter = q.get("filter");
  go(q.get("v") || DEFAULT_VIEW, params);
}
HELP = {
 "rag.what_is": {
  "term": "What RAG is",
  "what": "RAG (Retrieval-Augmented Generation) means: before the AI writes your patch, we first look up the most relevant pages from a reference library (the Prophet-6 manual, forum threads, and real factory patches) and hand them to the AI to work from. Then the AI writes the patch using those references instead of relying only on what it happens to remember.",
  "why": "The AI's own memory is fuzzy and can confidently make things up. Feeding it real Prophet-6 facts ('grounding') is what keeps patches accurate to the actual synth rather than generic guesswork. If patches feel wrong, the cause is usually upstream: either we found the wrong reference text, or the AI ignored the good text we gave it.",
  "tip": "Good: the patch cites a real manual section or factory patch. Bad: most settings cite 'general synthesis', meaning the AI fell back on generic memory."
 },
 "view.overview": {
  "term": "Overview screen",
  "what": "A single health dashboard for the whole system. It shows scorecards from offline test runs (graded against known-correct answers) plus live rates from the real patches people are generating right now.",
  "why": "It is your at-a-glance 'is everything OK?' page. If a number drops here, you switch to the other views to find out which request or which part of the pipeline is responsible.",
  "tip": "Start here. Treat it as the smoke alarm, not the diagnosis."
 },
 "view.trace": {
  "term": "Trace Explorer",
  "what": "Replays ONE single request step by step, from the original text query all the way to the final patch. You can open each stage in order: what we searched for, which reference chunks came back, what we handed the AI, and what JSON patch it wrote.",
  "why": "This is how you find exactly where a bad patch went wrong. A weak patch usually fails at one specific stage, for example the search returned irrelevant text, or the AI was given good text but ignored it.",
  "tip": "When a user reports 'this patch sounds nothing like what I asked', open its trace and walk the stages until the quality drops."
 },
 "view.diff": {
  "term": "Run-Diff",
  "what": "Compares two offline test runs side by side, a before and an after. You typically run the test set, change something (the search settings, the prompt, the corpus), run it again, and diff the two.",
  "why": "It answers 'did my change actually help, or did it quietly break something else?' Without this you are guessing whether a tweak improved patch quality or just moved problems around.",
  "tip": "Always re-run the full test set after a change and diff it, even for a 'small' tweak."
 },
 "view.corpus": {
  "term": "Corpus Health",
  "what": "Shows the health of the reference library the system searches: the manual pages, forum threads, and factory patches. It surfaces coverage and gaps in that library.",
  "why": "The AI can only ground its answer in text that actually exists in the library. If a topic is missing or thinly covered here, requests about it will produce weak, guessed patches no matter how good the rest of the pipeline is.",
  "tip": "If a certain kind of sound consistently produces bad patches, check whether the library even has good reference material on it."
 },
 "view.golden": {
  "term": "Golden set",
  "what": "A fixed list of test questions, each paired with a known correct answer. Running it scores the system objectively, the same questions every time, so results are comparable run to run.",
  "why": "It is your objective yardstick: it tells you whether overall patch quality is going up or down, instead of relying on the gut feel of a few spot-checks. It is the input the test runs and Run-Diff are scored against.",
  "tip": "Keep it fixed. If you change the questions, old and new scores are no longer comparable."
 },
 "kpi.recall": {
  "term": "recall@5",
  "what": "Out of the test questions, how often the one known-correct source chunk appears in the top 5 results the search returns. Like asking 'did the right page end up in our first handful of hits?'",
  "why": "This is the foundation: if search can't even surface the right facts, the LLM has nothing good to work from and the patch suffers. A drop here means fix retrieval before anything downstream.",
  "tip": "0-1, higher is better. Low recall = the answer was in the corpus but search didn't find it."
 },
 "kpi.coverage": {
  "term": "category coverage (≥3 sources)",
  "what": "Of all the sound types the product cares about (sound family like bass/lead/pad combined with a character like warm/aggressive), the share that have at least 3 independent sources backing them in the corpus.",
  "why": "Categories with thin backing tend to produce weak, guesswork patches. A low number tells you which sound types need more reference material added to the corpus.",
  "tip": "Higher is better. Find the under-3-source categories and feed in more docs/patches for them."
 },
 "kpi.provenance": {
  "term": "provenance cited ratio",
  "what": "Every setting in a generated patch carries a 'source.' This is the share of settings that point to a real corpus source, versus settings tagged 'general synthesis' (the model's own generic guess). Think of it as 'how much of this patch can we trace back to actual Prophet-6 facts.'",
  "why": "This is the headline trust signal: higher means the patch is grounded in real documented behavior, lower means more of it is the model improvising. If it's low, the patch may sound plausible but isn't backed by anything.",
  "tip": "Higher is better. Good: most settings cite a manual/forum/factory-patch source. Bad: lots of 'general synthesis.'"
 },
 "kpi.patch_accuracy": {
  "term": "patch accuracy vs reference",
  "what": "For test cases that have a real factory patch to compare against, this measures how closely the generated patch matches it setting-by-setting (knob for knob).",
  "why": "It's the most direct 'did we get the actual sound right' check. Only the subset of cases with a known reference patch can be scored, so it's a strong but partial signal.",
  "tip": "Higher is better. Measured only where a ground-truth reference patch exists."
 },
 "kpi.faithfulness": {
  "term": "faithfulness (Q&A)",
  "what": "On the question-answering side, the share of answers where every claim is actually backed by the retrieved text rather than made up. An AI grader does the judging.",
  "why": "Tells you whether answers are sticking to the sources or inventing things. Because an AI judges it, treat it as a guide and spot-check, not gospel.",
  "tip": "Higher is better. Carries a PROV badge — verify a few by hand before trusting a swing."
 },
 "kpi.bakeoff": {
  "term": "bake-off win rate",
  "what": "A head-to-head comparison: the RAG system (with retrieval) versus a plain baseline with no retrieval, scored by an AI judge. The number is how often retrieval's answer wins.",
  "why": "Answers the bottom-line question: is all this retrieval machinery actually helping? Above 50% means retrieval beats going without it; near 50% means it's barely earning its keep.",
  "tip": "Higher is better. AI-judged (PROV) — spot-check the verdicts before drawing conclusions."
 },
 "kpi.provisional": {
  "term": "PROV (provisional) badge",
  "what": "A flag meaning this number was judged by an AI grader or has a known measurement caveat. It's a useful estimate, not a hard measurement.",
  "why": "It's a 'trust but verify' marker: spot-check a few underlying cases before you act on the number or read a change as real.",
  "tip": "See a PROV badge? Open the drill-down and eyeball a couple of examples first."
 },
 "kpi.threshold": {
  "term": "tile color (threshold state)",
  "what": "A tile's color reflects only how it compares to its target, not anything else: green = at or above target, amber = near it, red = below. Tiles with no hard target stay neutral.",
  "why": "Lets you scan for trouble at a glance — red means a metric is under its goal and likely needs attention. Neutral just means there's no fixed bar to grade against, not that it's bad.",
  "tip": "Color = target state only. Neutral = no hard target set, so judge it on its own."
 },
 "trace.what_is": {
  "term": "Trace",
  "what": "A trace is the full recorded play-by-play of one patch generation: every stage's inputs and outputs, from the search results to the final knob settings.",
  "why": "It lets you replay any single request and see exactly where things went right or wrong, so you can diagnose a bad patch instead of guessing.",
  "tip": "Bad patch? Open its trace and read the stages top to bottom to find the first one that misbehaved."
 },
 "trace.filters": {
  "term": "Filter chips",
  "what": "Buttons that show only the traces with a specific problem: no-patch (nothing was produced), all-general (no real sources used), clamped (values had to be corrected to legal range), salvage (output was truncated and rescued), hallucinated-cite (cited a source that does not exist), sysex-fail (could not build the synth file), and error.",
  "why": "Instead of scrolling everything, you jump straight to the failures of one kind, which makes patterns and root causes obvious.",
  "tip": "Pick the symptom you care about most today and fix those traces first."
 },
 "trace.lever": {
  "term": "Lever",
  "what": "Each stage card ends with a LEVER: the one concrete thing to change if that stage caused the problem, such as the corpus, a retrieval setting, the system prompt, or the golden set.",
  "why": "It turns a diagnosis into an action by telling you which dial actually controls that stage, so you do not waste time tuning the wrong thing.",
  "tip": "Fix the lever on the earliest broken stage first; later stages often heal once the input is good."
 },
 "env.grounding": {
  "term": "Grounding mode (adapt vs pure)",
  "what": "How the model was fed reference material: adapt means it got full real factory-patch examples to copy and tweak; pure means it got only text chunks (manual and forum snippets), no example patches.",
  "why": "Adapt usually grounds better because the model can start from a real working patch instead of inventing settings from descriptions.",
  "tip": "If pure-mode traces look guessy, try adapt so the model has a real patch to lean on."
 },
 "env.k": {
  "term": "k (reference chunks)",
  "what": "How many reference snippets were placed into the prompt for the model to read. Here it is 8.",
  "why": "Too few and the model lacks facts and falls back on guesswork; too many can bury the most relevant snippet in noise.",
  "tip": "If patches miss obvious facts, more chunks may help; if they drift off-topic, fewer may help."
 },
 "env.temperature": {
  "term": "Temperature",
  "what": "The model's creativity/randomness dial: 0 means deterministic (same answer every time), higher means more varied. Patch design uses a little so sounds are not cookie-cutter.",
  "why": "Higher values give more variety but also more drift and less repeatability; lower values are steadier but can feel formulaic.",
  "tip": "Chasing a flaky, inconsistent bug? Lower it toward 0 to make runs repeatable."
 },
 "env.action_floor": {
  "term": "Action floor",
  "what": "The minimum actionability (how much real sound-design substance a chunk has) a snippet must clear to be force-included in the prompt.",
  "why": "Raise it to block fluffy, low-content chunks from crowding the prompt; lower it if genuinely useful chunks are being left out.",
  "tip": "Prompt full of vague filler? Raise it. Good snippets missing? Lower it."
 },
 "env.rrf_k": {
  "term": "rrf_k (fusion constant)",
  "what": "A constant in the formula that merges the keyword-search ranking and the meaning-based ranking into one combined list. It is a tuning knob for how strongly the very top ranks are favored.",
  "why": "It shapes which results win when the two search methods disagree, so it quietly influences what the model gets to read.",
  "tip": "Adjust only if you have a specific reason; small changes here ripple through every retrieval."
 },
 "env.model": {
  "term": "Model",
  "what": "Which Claude model generated this patch.",
  "why": "Different models can produce different patch quality, so knowing which one ran helps you compare results and reproduce a trace.",
  "tip": "Comparing patch quality across traces? Check they used the same model before blaming other settings."
 },
 "diff.delta": {
  "term": "Delta (change A→B)",
  "what": "How much a score moved from run A (your old baseline) to run B (your new candidate change). Green means it moved the right direction, red means it got worse.",
  "why": "This is the one-line verdict on whether your change helped or hurt. A red delta is your cue to drill in and find out what broke before you ship it.",
  "tip": "Green = keep the change. Red = stop and investigate the per-question list."
 },
 "diff.tripwire": {
  "term": "Recall tripwire (≥0.95)",
  "what": "A guard rail: the share of test questions where the correct source still gets found must stay at or above 0.95. A FAIL warns that your change made search worse at finding the right material.",
  "why": "If search stops surfacing the right facts, the patch is built on guesswork. Treat a FAIL seriously, but note the caveat: a single 'miss' can be stale test data, not a true regression.",
  "tip": "On a FAIL, open the per-question drill first; don't assume the worst until you've looked."
 },
 "diff.per_bucket": {
  "term": "Per-bucket breakdown",
  "what": "The same score split by question category ('bucket'), e.g. bass sounds vs pad sounds. Shows which kinds of requests got better or worse, not just the overall average.",
  "why": "An overall number can hide trouble: one category improving while another tanks can net out flat. The breakdown tells you exactly which sound types to worry about.",
  "tip": "Watch for one bucket dropping while the headline looks fine."
 },
 "diff.regressed_improved": {
  "term": "Regressed / improved questions",
  "what": "The individual test questions that flipped between the two runs, e.g. a question that used to find the right source ('hit') now misses ('regressed'), or the reverse ('improved').",
  "why": "This is where you see the real cause. Click a regressed question to see which chunks pushed the correct answer out of the results, so you can tell if your change is to blame.",
  "tip": "Regressions are the actionable list, read those before celebrating improvements."
 },
 "diff.shared_queries": {
  "term": "Shared questions",
  "what": "How many test questions both runs actually have in common. The comparison is only apples-to-apples on these shared questions.",
  "why": "If this is 0, the two runs used different test sets, so only the headline and per-bucket averages are comparable, not the per-question diffs. A low number means treat the comparison with caution.",
  "tip": "0 shared = different test sets; don't trust the per-question flips."
 },
 "corpus.coverage": {
  "term": "Coverage heatmap",
  "what": "A grid of sound families (bass, pad, lead...) against characters (warm, bright...) showing how many independent sources back each combination. Red/amber cells are thin spots with few sources.",
  "why": "Cells with few sources predict weak patches for those sounds, the model has little real material to lean on. Treat the red/amber cells as your shopping list of content to go acquire.",
  "tip": "Red cell = expect poor patches there until you add sources."
 },
 "corpus.composition": {
  "term": "Corpus composition",
  "what": "How many text chunks the library holds from each kind of source, e.g. official manual vs Reddit threads vs real patch files.",
  "why": "Tells you what the knowledge base is actually made of. A library that's almost all forum chatter and little manual, or vice versa, hints at where answers may be unbalanced or shaky.",
  "tip": "Balance matters, all one source type is a blind spot."
 },
 "corpus.retrieval_reach": {
  "term": "Retrieval reach",
  "what": "How many distinct chunks ever actually showed up in search results across all the test questions. A sense of how much of the library the search can realistically reach.",
  "why": "If only a tiny fraction of a big library is ever reached, most of your content isn't doing any work. Low reach suggests search or content tagging may be leaving good material buried.",
  "tip": "Measured only over the test questions, so it's a sample, not the full picture."
 },
 "corpus.dead": {
  "term": "Never-retrieved chunks",
  "what": "Chunks that never appeared in any test-question's results. With a small test set this number is expected to be high, so it's not a per-chunk dead list.",
  "why": "Don't read individual entries here. Read it per source type: if a whole lane (e.g. all patch files) never surfaces, that's a real signal that an entire category isn't being reached.",
  "tip": "A whole source type at zero is the alarm, not the raw total."
 },
 "corpus.top_chunks": {
  "term": "Most-retrieved chunks",
  "what": "The chunks that show up most often in search results, the 'head' of content the system leans on heavily.",
  "why": "If a handful of chunks carry most answers, the system is over-relying on a narrow slice. That's fragile, if those chunks are wrong or thin, many patches inherit the same weakness.",
  "tip": "A very lopsided head suggests you need more variety in retrieval."
 },
 "corpus.gaps": {
  "term": "Coverage gaps (<3 sources)",
  "what": "Sound categories backed by fewer than three independent sources, the concrete weak spots pulled out of the heatmap.",
  "why": "Fewer than three sources means the model has little to ground a patch in for that sound, so quality there is likely poor. This is a ready-made list of content to go acquire.",
  "tip": "Each gap is a direct to-do, find sources for that sound type."
 },
 "golden.gate": {
  "term": "Golden integrity gate",
  "what": "A pass/fail check that, for every test question, its known-correct answer still actually exists in the corpus. A FAIL means a question's expected source went missing.",
  "why": "If the right answer isn't even in the library, the question can never be scored fairly, it will always look like a failure. A red gate means fix the test set or corpus before trusting any scores.",
  "tip": "Always green before you read recall numbers, otherwise the scores are unfair."
 },
 "golden.buckets": {
  "term": "Golden buckets",
  "what": "The test questions grouped by what they're checking, e.g. 'did search find the right source' versus 'is the final patch accurate'.",
  "why": "Different buckets test different stages of the pipeline. Knowing the bucket tells you whether a failure is a search problem or a patch-writing problem, which points to a different fix.",
  "tip": "A failure's bucket tells you which part of the pipeline to look at."
 },
 "golden.targets": {
  "term": "Expected targets",
  "what": "For each test question, the specific source(s) that must be retrieved for the answer to count as correct, the official 'right answers' for that question.",
  "why": "These define what counts as a hit. If a question's targets are wrong or outdated, it will score as a miss for no real reason, so check the targets when a question fails unexpectedly.",
  "tip": "A surprising miss is sometimes a stale target, not a real regression."
 },
 "golden.promote": {
  "term": "Promote to golden",
  "what": "Turn a real failing request into a new permanent test case with one click, so future runs are measured against it.",
  "why": "Real-world failures become tracked tests instead of being forgotten. Over time this grows your test set to cover the things users actually got wrong, so the same mistake can't silently come back.",
  "tip": "When a real request fails badly, promote it so it's guarded forever."
 },
 "live.intro": {
  "term": "Live vs eval",
  "what": "These tiles are rolling rates over the most recent REAL patch generations people actually ran - not the offline test set above. They reflect what is happening in production right now.",
  "why": "The offline scores show how the system does on a fixed exam; these show how it does on real, messy, in-the-wild requests. A problem that is rare on the exam can be common in the wild.",
  "tip": "For most of these, lower is better (they count problems); 'mean changes' has a healthy middle band."
 },
 "live.all_general": {
  "term": "All-general rate",
  "what": "The share of recent patches where EVERY setting was tagged 'general synthesis' - not one setting could be traced to the corpus. The AI built the whole patch from generic memory.",
  "why": "This is the clearest 'the corpus isn't helping' alarm. When it is high, requests are getting no useful reference material, so patches are educated guesses rather than grounded in real Prophet-6 facts.",
  "tip": "High -> check whether retrieval is finding anything, and whether the corpus covers those sounds."
 },
 "live.no_patch": {
  "term": "No-patch-served rate",
  "what": "The share of recent generations where no real factory-patch example reached the AI, so it had nothing known-good to adapt from and built the patch from text alone.",
  "why": "Adapting a real patch is a big accuracy lever; without one the AI guesses more. A high rate points to missing patch examples in the corpus for the sounds being requested.",
  "tip": "High -> add real/factory patches to the corpus, especially for the sound types being asked for."
 },
 "live.salvage": {
  "term": "Salvage / truncation rate",
  "what": "The share of recent patches where the AI's output got cut off (it hit the length limit) and the app had to salvage the partial result, keeping only the settings that arrived complete.",
  "why": "Salvaged patches are likely missing their final settings, so they can sound unfinished. A rising rate usually means prompts are too long or the output limit is too low.",
  "tip": "High -> shorten the prompt (fewer examples) or raise the output token limit."
 },
 "live.clamp": {
  "term": "Silent-clamp rate",
  "what": "The share of recent patches where at least one value the AI asked for was out of the synth's legal range and got silently snapped to the nearest legal value.",
  "why": "Each clamp means the delivered patch differs from what the AI intended - usually a bit duller or weaker. Repeated clamps on the same knob mean the AI keeps misjudging that range.",
  "tip": "High -> tighten the parameter-range guidance in the system prompt."
 },
 "live.bad_citations": {
  "term": "Bad-citation rate",
  "what": "The share of recent patches where the AI cited a source that was not actually in the material it was given - a fabricated, or 'hallucinated', citation.",
  "why": "Made-up citations undermine the whole provenance signal: a setting looks grounded but isn't. A rising rate means the AI is being loose with its sourcing rules.",
  "tip": "High -> tighten the prompt's instruction to cite only the provided sources."
 },
 "live.sysex_fail": {
  "term": "SysEx-fail rate",
  "what": "The share of recent patches where encoding the patch to a MIDI message (for sending to hardware) failed. This is a robustness signal, not a sound-quality one.",
  "why": "It tells you the hardware-export feature is misbehaving, but says nothing about whether the patches sound right. Useful for catching a regression in the encoder.",
  "tip": "This won't affect on-screen patch quality - it only concerns MIDI export to hardware."
 },
 "live.mean_changes": {
  "term": "Mean changes per patch",
  "what": "The average number of settings changed per generated patch across recent runs. There is a healthy band (roughly 10-25): enough to fully shape a sound without piling on noise.",
  "why": "Consistently too few means thin, underdeveloped patches; too many means the AI is over-tweaking with settings that don't help. Either drift is worth a prompt nudge.",
  "tip": "Below the band -> patches feel unfinished; above it -> noisy, over-engineered patches."
 },
 "live.mean_ms": {
  "term": "Mean generation time",
  "what": "The average wall-clock time, in milliseconds, to produce one patch end to end (search + the AI call + validation).",
  "why": "A speed and cost signal. A sudden jump can mean prompts grew, the model slowed, or retrieval got heavier - worth investigating even if quality looks fine.",
  "tip": "The AI call usually dominates; a big jump often traces to a larger prompt or a slower model."
 },
 "stage.classify": {
  "term": "Query classification",
  "what": "A quick guess at whether your text reads like a 'make me a sound' recipe versus a factual question. On the patch-designer path it is recorded for insight only - the designer always treats the request as a sound recipe.",
  "why": "It is a diagnostic breadcrumb here, not a decision point. It mainly matters on the question-answering side; on the patch path treat it as informational.",
  "tip": "Marked diagnostic-only on this path - it does not change what gets retrieved."
 },
 "stage.pool": {
  "term": "Retrieval pool (top ~25)",
  "what": "The first wide net: the ~25 most relevant chunks pulled from the corpus. Each shows a relevance score ('rrf', from fusing keyword + meaning search) and a meaning-similarity score ('sim'), grouped by 'lane' (manual / reddit / article / patch).",
  "why": "This is the raw material the AI builds from. If the right source is not in this pool, nothing downstream can rescue it. Watch the 'patch' lane - if it shows 0, no real factory patch was found to copy from for this sound.",
  "tip": "Good: a healthy mix of lanes with a patch example present. Bad: patch lane 0, or everything from one source."
 },
 "stage.rerank": {
  "term": "Actionability re-rank",
  "what": "A second pass that re-sorts the pool to favor chunks packed with real sound-design settings ('actionability') and push down chatter like 'thanks!' or jokes, blended with the original relevance.",
  "why": "Relevant is not the same as useful: a post can be on-topic yet contain no actual settings. This step makes sure the chunks reaching the AI carry concrete knob values, not noise.",
  "tip": "If a clearly useful chunk ranks low, its wording may lack the setting-words the score rewards."
 },
 "stage.diversify": {
  "term": "Diversity injection",
  "what": "Makes sure the final handful of chunks is not all from one place - it tries to include a manual chunk, a community chunk, and a real factory-patch example. The 'patch_injection_outcome' readout says whether a real patch made it in, or why not (none in the pool, or all too low-quality).",
  "why": "A patch grounded in the manual AND a real example AND community tips beats three near-duplicate chunks. 'no_candidate_in_pool' or 'all_below_floor' here is the usual root cause of all-'general synthesis' patches.",
  "tip": "'all_below_floor' -> lower the actionability floor; 'no_candidate_in_pool' -> the corpus lacks patch examples for this sound."
 },
 "stage.adapt": {
  "term": "Grounding block (retrieve-and-adapt)",
  "what": "Loads the full settings of any real factory patches that were found, so the AI can start from a known-good patch and tweak it instead of building from scratch. Shows how many examples loaded and how the nearest-neighbor lookup went.",
  "why": "Adapting a real patch is the single biggest accuracy lever - the AI copies proven settings rather than guessing. Empty here (no patch ids) means the AI had no real example to anchor on.",
  "tip": "Empty grounding block -> expect more guesswork; add factory patches for that sound to the corpus."
 },
 "stage.prompt": {
  "term": "Prompt assembly",
  "what": "The full instruction package sent to the AI: the legal parameters and their ranges (the 'schema'), the reference chunks, any real patch examples, and your request. Shows the total size in characters and rough tokens (a token is about three-quarters of a word, the unit the model reads).",
  "why": "There is a fixed budget shared by input and output. An over-large prompt can crowd out the room the model needs to finish a complete patch, leading to cut-off output.",
  "tip": "Very large prompt plus cut-off output downstream -> trim how many examples are included."
 },
 "stage.llm": {
  "term": "LLM output",
  "what": "The AI's raw response. 'stop_reason' tells you how it finished: 'end_turn' is a clean finish; 'max_tokens' means it ran out of room and got cut off mid-patch. It also shows how many tokens it produced.",
  "why": "A 'max_tokens' finish means the patch is probably incomplete - later settings got chopped off. That is a cue to shorten the prompt or raise the output limit.",
  "tip": "Good: end_turn. Bad: max_tokens (truncated) - settings are likely missing."
 },
 "stage.extract": {
  "term": "JSON parse",
  "what": "Turns the AI's text into a clean, structured patch. 'json.loads' means it parsed perfectly; 'salvage' means the output was broken or cut off and the app recovered as many complete settings as it could.",
  "why": "Salvage means you are getting a partial patch - the tail end was unrecoverable. Frequent salvage usually traces back to truncated output (see the LLM stage).",
  "tip": "Good: json.loads. Watch: salvage means some settings were dropped."
 },
 "stage.validate": {
  "term": "Validation & clamping",
  "what": "Checks every proposed setting against the synth's real legal range. Out-of-range values are 'clamped' to the nearest legal value, unrecognized options are corrected or dropped, and settings equal to the default are removed. It surfaces these otherwise-silent changes.",
  "why": "The AI sometimes asks for impossible values (e.g. a cutoff of 300 when the max is 164). Clamping keeps the patch playable, but a clamped value means the result differs from what the AI intended.",
  "tip": "Many clamps on the same knob -> tighten that knob's range guidance in the prompt."
 },
 "stage.patch": {
  "term": "Final patch",
  "what": "The finished, validated patch handed to the panel: how many settings changed (a healthy band is roughly 10-25), the patch name, and any setting the AI talked about in its explanation but that did not actually make it into the patch.",
  "why": "Too few changes means an underdeveloped sound; too many means noise. 'Narrated but not delivered' catches the confusing case where the explanation describes a setting the user will not find on the panel.",
  "tip": "Aim for ~10-25 changes. Narrated-not-delivered items are a prompt/validation mismatch to fix."
 },
 "stage.provenance": {
  "term": "Provenance breakdown",
  "what": "Where this patch's settings came from: real corpus sources (manual / community / factory patch) versus 'general synthesis' (the AI's own generic knowledge). It also flags any citation the AI invented that was not in the prompt.",
  "why": "This is the per-patch version of the Overview's provenance score. All-'general synthesis' means the corpus contributed nothing - the AI improvised the whole patch, so accuracy for this specific synth is at risk.",
  "tip": "All-general -> look upstream at retrieval/grounding/corpus. Fabricated citations -> tighten the prompt's citation rules."
 },
 "stage.sysex": {
  "term": "SysEx (MIDI out)",
  "what": "Encodes the finished patch into a MIDI 'SysEx' message - the format a real Prophet-6 understands - so it can be sent to hardware. 'outcome: ok' means it encoded; anything else is an encoding error, now surfaced instead of hidden.",
  "why": "This is a convenience feature, not a sound-quality signal. It is shown so a silent encoding failure does not go unnoticed, but a failure here does not mean the patch itself is wrong.",
  "tip": "A sound-quality problem will not show up here; this only concerns sending the patch to hardware."
 }
};

boot();
