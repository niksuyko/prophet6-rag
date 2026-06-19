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
    `<button class="ghost promo-btn" title="Draft a golden-set entry from this trace">＋ Promote to golden</button></div>` +
    `<div class="qq" style="font-style:italic;color:var(--text-faint)">“${esc(rec.query || "")}” · ${esc(rec.trace_id || "")}</div>` +
    `<div class="envelope"><span><b>${esc(rec.model || "")}</b></span>` +
    `<span>grounding <b>${esc(rec.grounding || "")}</b></span><span>k=<b>${rec.k}</b></span>` +
    `<span>temp <b>${rec.temperature}</b></span><span>floor <b>${rec.action_floor}</b></span>` +
    `<span>rrf_k <b>${rec.rrf_k}</b></span><span><b>${rec.wall_ms}</b> ms</span></div>`;
  detail.appendChild(head);
  const pb = head.querySelector(".promo-btn");
  if (pb) pb.onclick = () => openPromote(rec);

  STAGES.forEach(([key, title, build]) => {
    let info; try { info = build(rec); } catch { info = { status: "warn", hl: "render error", body: "", lever: "—", raw: rec[key] }; }
    const card = el("div", `stage-card ${info.status}`);
    card.innerHTML =
      `<div class="ch"><span class="ttl">${esc(title)}</span><span class="hl ${info.status}">${esc(info.hl)}</span></div>` +
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
  ["all_general_rate", "ALL-GENERAL", "ratio"],
  ["no_patch_served_rate", "NO PATCH SERVED", "ratio"],
  ["salvage_rate", "SALVAGE/TRUNC", "ratio"],
  ["clamp_rate", "SILENT CLAMP", "ratio"],
  ["hallucinated_cite_rate", "BAD CITATIONS", "ratio"],
  ["sysex_fail_rate", "SYSEX FAIL", "ratio"],
];

function kpiTile(k, onClick) {
  const health = kpiHealth(k.value, k.target, k.direction);
  const t = el("div", "stat click");
  t.innerHTML =
    `<div class="n ${health || "amber"}">${esc(fmtVal(k.value, k.fmt))}</div>` +
    `<div class="k">${esc(k.metric)}${k.provisional ? '<span class="prov">PROV</span>' : ""}</div>` +
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
    ov.appendChild(el("div", "section-title", "Eval health — latest per kind"));
    const kstats = el("div", "stats"); ov.appendChild(kstats);
    if (!data.eval.length) kstats.appendChild(el("div", "empty-note", "No eval results yet."));
    data.eval.forEach(k => {
      if (k.kind === "recall") k.history = data.recall_history;
      kstats.appendChild(kpiTile(k, () => showKpi(rail, k)));
    });

    // --- live generation health (rolling) ---
    ov.appendChild(el("div", "section-title",
      `Live generation health — rolling last ${data.live.n_traces || 0}`));
    if (!data.live.n_ok) {
      ov.appendChild(el("div", "empty-note", "No live traces yet — generate patches in <a href='studio.html'>Studio</a>."));
    } else {
      const lstats = el("div", "stats");
      LIVE_TILES.forEach(([key, label]) => {
        const v = data.live[key];
        const t = el("div", "stat");
        t.innerHTML = `<div class="n ${rateHealth(v)}">${v == null ? "—" : (v * 100).toFixed(0) + "%"}</div><div class="k">${label}</div>`;
        lstats.appendChild(t);
      });
      const cc = data.live.mean_change_count;
      const ccH = cc == null ? "" : (cc >= 10 && cc <= 25 ? "ok" : "warn");
      const extra = el("div", "stat");
      extra.innerHTML = `<div class="n ${ccH}">${cc ?? "—"}</div><div class="k">MEAN CHANGES (10–25)</div>`;
      lstats.appendChild(extra);
      const w = el("div", "stat");
      w.innerHTML = `<div class="n">${data.live.mean_wall_ms ?? "—"}</div><div class="k">MEAN MS</div>`;
      lstats.appendChild(w);
      ov.appendChild(lstats);
    }

    // --- recent traces ---
    ov.appendChild(el("div", "section-title", "Recent traces"));
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
        c.onclick = () => { active = f; load(); };
        chips.appendChild(c);
      });
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
  const tgt = (it.detail_a.matched || {});
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
    `<div class="diff-band"><div><div class="k">${esc(d.metric)}</div>` +
    `<div class="band-vals"><span class="mono">${esc(fmtVal(d.a.value, d.fmt))}</span> → ` +
    `<span class="mono">${esc(fmtVal(d.b.value, d.fmt))}</span></div></div>` +
    `<div class="band-delta ${dcls}">${esc(fmtDelta(d.delta))}</div></div>` +
    `<div class="muted" style="margin:8px 0 4px">A: ${esc(d.a.label)} (${esc(d.a.ts)}) · B: ${esc(d.b.label)} (${esc(d.b.ts)}) · ${d.n_common} shared queries</div>` +
    (d.n_common === 0 ? `<div class="tip"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>These two runs share no query ids — likely different golden sets (e.g. v1 vs v2). Headline and per-bucket deltas still apply; pick two runs of the same set for a per-query regression list.</div>` : "");

  if (d.tripwire) {
    const tw = d.tripwire;
    out.innerHTML += `<div class="${tw.pass ? "tip" : "problems"}"><b>v1 tripwire ${tw.pass ? "PASS" : "FAIL"}</b> — ` +
      `${esc(fmtVal(tw.value, "ratio"))} vs ${tw.target}. ${esc(tw.note)}</div>`;
  }
  if (d.per_bucket.length) {
    out.innerHTML += `<div class="section-title">Per-bucket</div><table class="tbl"><tr><th>bucket</th><th>A</th><th>B</th><th>Δ</th></tr>` +
      d.per_bucket.map(b => `<tr><td class="cid">${esc(b.bucket)}</td><td>${b.a ?? "—"}</td><td>${b.b ?? "—"}</td>` +
        `<td class="${deltaCls(b.delta, dir)}">${esc(fmtDelta(b.delta))}</td></tr>`).join("") + `</table>`;
  }
  const sect = (title, items, sign) => {
    let h = `<div class="section-title">${title}</div>`;
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
    const kindSel = el("select", "sel"), aSel = el("select", "sel"), bSel = el("select", "sel");
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
    ov.appendChild(el("div", "section-title", "Coverage — families × characters (independent sources/cell)"));
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
    ov.appendChild(el("div", "section-title", "Corpus composition (chunks by source type)"));
    ov.appendChild(htmlNode(bars(c.by_source_type)));

    ov.appendChild(el("div", "section-title", "Retrieval reach (across golden recall runs)"));
    const r = c.retrieval;
    const st = el("div", "stats");
    [["distinct chunks retrieved", r.distinct_chunks_retrieved],
     ["never retrieved", c.dead.never_retrieved],
     ["recall runs scanned", r.n_recall_runs]].forEach(([k, v]) => {
      const t = el("div", "stat"); t.innerHTML = `<div class="n mono">${v}</div><div class="k">${k}</div>`; st.appendChild(t);
    });
    ov.appendChild(st);
    ov.appendChild(htmlNode(`<div class="tip"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>${esc(c.dead.note)}</div>`));
    ov.appendChild(el("div", "section-title", "Served by source type"));
    ov.appendChild(htmlNode(bars(r.served_by_source_type)));
    ov.appendChild(el("div", "section-title", "Most-retrieved chunks (over-relied head)"));
    ov.appendChild(htmlNode(`<table class="tbl"><tr><th>chunk</th><th>type</th><th>hits</th></tr>` +
      r.top_chunks.map(t => `<tr><td class="cid">${esc(t.chunk_id)}</td><td><span class="badge ${esc(t.source_type)}">${esc(t.source_type)}</span></td><td>${t.freq}</td></tr>`).join("") + `</table>`));

    rail.innerHTML = `<p class="rail-title">Corpus → which lever</p>` +
      `<p class="empty-note">A red/amber heatmap cell predicts all-“general synthesis” patches for that sound — it's the acquisition shopping list. A whole lane absent from “served by source type” means retrieval never reaches it. Both point at the <b>corpus</b> lever.</p>` +
      (cov.gaps && cov.gaps.length ? `<div class="section-title">Gap cells (&lt;3 sources)</div>` +
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
      `<div class="${gate.ok ? "tip" : "problems"}"><b>Reachability gate ${gate.ok ? "PASS" : "FAIL"}</b> — ` +
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
    ov.appendChild(el("div", "section-title", "Inventory by bucket"));
    ov.appendChild(htmlNode(bars(byBucket)));

    // table
    ov.appendChild(el("div", "section-title", `All entries (${g.records.length})`));
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
  const q = new URLSearchParams(location.search);
  $("#refreshBtn").onclick = () => go(CURRENT ? CURRENT.id : DEFAULT_VIEW, CURRENT ? CURRENT.params : {});
  go(q.get("v") || DEFAULT_VIEW, q.get("id") ? { id: q.get("id") } : {});
}
boot();
