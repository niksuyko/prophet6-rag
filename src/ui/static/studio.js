/* Prophet-6 Studio — modern shell around the faithful hardware panel.
   The panel-rendering half (control builders + renderPanel) is the original panel.js
   layout, unchanged, so the centred unit is identical to the real desktop module.
   The shell half (status, inspector, fit-to-stage, generation, MIDI) is modern.
   Same endpoints as index.html: /api/schema, /api/patch, /api/decode. */

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const $ = (sel, parent = document) => parent.querySelector(sel);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const els = {};      // param id -> {def, root, set(value, animate)}
let SCHEMA = null;
let DEFS = {};       // param id -> def
const SEC_OF = {};   // param id -> schema section name (for inspector labels)
let busy = false;

/* ====================================================================== *
 *  HARDWARE PANEL  (verbatim from the original panel.js)                  *
 * ====================================================================== */
const FX_CODES = { "off": "OFF", "bbd-delay": "bbd", "digital-delay": "ddL", "chorus": "CHO",
  "phaser-1": "PH1", "phaser-2": "PH2", "phaser-3": "PH3", "ring-mod": "rin",
  "hall-reverb": "HAL", "room-reverb": "rOO", "plate-reverb": "PLA", "spring-reverb": "SPr" };
const GLIDE_CODES = { "fixed-rate": "FR", "fixed-rate-legato": "FrA",
  "fixed-time": "Ft", "fixed-time-legato": "FtA" };
const KEYMODE_CODES = { "low": "LO", "high": "Hi", "last": "LAS",
  "low-retrig": "LOr", "high-retrig": "Hir", "last-retrig": "LAr" };
const DIVIDE_CODES = { "half": "1", "quarter": "2", "8th": "4", "8th-half-swing": "4.5",
  "8th-full-swing": "4F", "8th-triplet": "4t", "16th": "8", "16th-half-swing": "8.5",
  "16th-full-swing": "8F", "16th-triplet": "8t" };

function readoutText(def, value) {
  if (!def) return String(value);
  if (def.id === "osc1.frequency" || def.id === "osc2.frequency")
    return `${NOTE_NAMES[value % 12]}${Math.floor(value / 12)}`;
  if (def.type === "bipolar" && value > 0) return `+${value}`;
  return String(value);
}
function knobAngle(def, value) {
  return -135 + ((value - def.min) / (def.max - def.min)) * 270;
}

function reg(def, root, set) { els[def.id] = { def, root, set }; return root; }

function makeKnob(def, opts = {}) {
  const root = document.createElement("div");
  root.className = `param knob ${def.type === "bipolar" ? "bipolar" : ""} ${opts.mini ? "mini" : ""}`;
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dial"><div class="pointer"></div></div>
    <div class="readout"></div><div class="plabel">${opts.label || def.label}</div>`;
  const pointer = $(".pointer", root), readout = $(".readout", root);
  return reg(def, root, (value, animate) => {
    pointer.style.transition = animate ? "" : "none";
    pointer.style.transform = `rotate(${knobAngle(def, value)}deg)`;
    if (!animate) pointer.offsetHeight;
    readout.textContent = readoutText(def, value);
  });
}

function makeScreenKnob(def, opts = {}) {
  const root = document.createElement("div");
  root.className = "param knob encoder mini";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dial"></div>
    <div class="miniscreen"></div><div class="plabel">${opts.label || def.label}</div>`;
  const screen = $(".miniscreen", root);
  return reg(def, root, value => { screen.textContent = value; });
}

function makeKnobSelect(def, opts = {}) {
  const root = document.createElement("div");
  root.className = "param knob";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dial"><div class="pointer"></div></div>
    <div class="readout"></div><div class="plabel">${opts.label || def.label}</div>`;
  const pointer = $(".pointer", root), readout = $(".readout", root);
  return reg(def, root, (value, animate) => {
    const i = Math.max(0, def.options.indexOf(value));
    pointer.style.transition = animate ? "" : "none";
    pointer.style.transform = `rotate(${-135 + (270 * i) / (def.options.length - 1)}deg)`;
    if (!animate) pointer.offsetHeight;
    readout.textContent = value;
  });
}

function makeToggle(def, opts = {}) {
  const root = document.createElement("div");
  root.className = `param toggle ${opts.big ? "big" : ""}`;
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<button class="ledbtn" tabindex="-1"><span class="led"></span></button>
    <div class="plabel">${opts.label || def.label}</div>`;
  const btn = $(".ledbtn", root);
  return reg(def, root, value => btn.classList.toggle("on", !!value));
}

function makeLedList(def, opts = {}) {
  const order = opts.order || def.options;
  const names = opts.names || {};
  const root = document.createElement("div");
  root.className = "param select";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="grouplabel">${opts.label || def.label}</div>
    <div class="opts">${order.map(o =>
      `<div class="opt" data-opt="${o}"><span class="led"></span>${names[o] || o}</div>`).join("")}</div>`;
  return reg(def, root, value => {
    root.querySelectorAll(".opt").forEach(o =>
      o.classList.toggle("on", o.dataset.opt === String(value)));
  });
}

function makeHalfFull(def) {
  const root = document.createElement("div");
  root.className = "param select hf";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="opts">
      <div class="opt" data-opt="half"><span class="led"></span>Half</div>
      <div class="opt" data-opt="full"><span class="led"></span>Full</div>
    </div><div class="plabel">${def.label}</div>`;
  return reg(def, root, value => {
    root.querySelectorAll(".opt").forEach(o =>
      o.classList.toggle("on", o.dataset.opt === String(value)));
  });
}

function makeCodeDisplay(def, codes, opts = {}) {
  const root = document.createElement("div");
  root.className = "param display";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dispwin"></div><div class="plabel">${opts.label || def.label}</div>`;
  const win = $(".dispwin", root);
  return reg(def, root, value => { win.textContent = codes ? (codes[value] ?? value) : value; });
}

function makeFilterPair(lpId, hpId) {
  const wrap = document.createElement("div");
  wrap.className = "fpair";
  wrap.innerHTML = `<div class="grouplabel">Filter</div>`;
  for (const [pid, name] of [[lpId, "LP"], [hpId, "HP"]]) {
    const def = DEFS[pid];
    const root = document.createElement("div");
    root.className = "param fled";
    root.dataset.id = pid; root.title = def.hint;
    root.innerHTML = `<span class="led"></span><span class="flabel">${name}</span>`;
    reg(def, root, value => root.classList.toggle("on", !!value));
    wrap.appendChild(root);
  }
  return wrap;
}

function deco(kind, label, text = "") {
  const d = document.createElement("div");
  d.className = `param deco ${kind === "display" ? "display" : kind === "knob" ? "knob" : "toggle"}`;
  if (kind === "knob")
    d.innerHTML = `<div class="dial"><div class="pointer" style="transform:rotate(-45deg)"></div></div>
      <div class="readout"></div><div class="plabel">${label}</div>`;
  else if (kind === "display")
    d.innerHTML = `<div class="dispwin">${text}</div><div class="plabel">${label}</div>`;
  else
    d.innerHTML = `<button class="ledbtn" tabindex="-1"><span class="led"></span></button>
      <div class="plabel">${label}</div>`;
  return d;
}

function capButton(label, opts = {}) {
  const d = document.createElement("div");
  d.className = `param cap deco`;
  d.innerHTML = `<button class="capbtn ${opts.red ? "red" : ""}" tabindex="-1"><span class="led"></span></button>
    <div class="plabel">${label}</div>`;
  return d;
}

function capToggle(def, label) {
  const root = capButton(label);
  root.classList.remove("deco");
  root.dataset.id = def.id; root.title = def.hint;
  const btn = $(".capbtn", root);
  return reg(def, root, value => btn.classList.toggle("on", !!value));
}

function section(title, nodes, cls = "") {
  const sec = document.createElement("section");
  sec.className = `section ${cls}`;
  sec.innerHTML = title ? `<h2>${title}</h2>` : "";
  for (const n of nodes) sec.appendChild(n);
  return sec;
}
function subgroup(label, nodes) {
  const g = document.createElement("div");
  g.className = "subgroup";
  g.innerHTML = `<div class="grouplabel">${label}</div>`;
  const row = document.createElement("div");
  row.className = "subrow";
  for (const n of nodes) row.appendChild(n);
  g.appendChild(row);
  return g;
}
function column(...stacked) {
  const c = document.createElement("div");
  c.className = "col";
  for (const s of stacked) c.appendChild(s);
  return c;
}
function rowOf(...nodes) {
  const r = document.createElement("div");
  r.className = "band";
  for (const n of nodes) r.appendChild(n);
  return r;
}

function renderPanel(schema) {
  const D = DEFS;
  const panel = $("#panel");
  panel.innerHTML = "";

  /* --- top band --- */
  panel.appendChild(rowOf(
    section("", [deco("knob", "Master Vol")], "plain"),
    section("Poly Mod", [
      makeKnob(D["pmod.filt_env"], { label: "Filter Env" }),
      makeKnob(D["pmod.osc2"]),
      makeToggle(D["pmod.dest_freq1"]),
      makeToggle(D["pmod.dest_shape1"]),
      makeToggle(D["pmod.dest_pw1"]),
      makeFilterPair("pmod.dest_lp", "pmod.dest_hp"),
    ]),
    section("Clock", [
      deco("toggle", "Tap Tempo"),
      makeCodeDisplay(D["clock.bpm"], null, { label: "BPM" }),
      makeCodeDisplay(D["clock.divide"], DIVIDE_CODES, { label: "Value" }),
    ]),
    section("Arpeggiator", [
      makeToggle(D["arp.on"], { label: "On/Off" }),
      makeLedList(D["arp.octaves"], { label: "Octaves" }),
      makeLedList(D["arp.mode"], { label: "Mode",
        order: ["up", "up+down", "down", "random", "assign"],
        names: { "up": "Up", "up+down": "Up/Down", "down": "Down",
                 "random": "Random", "assign": "Assign" } }),
    ]),
    section("Sequencer", [deco("toggle", "Record"), deco("toggle", "Play")]),
    section("Aftertouch", [
      makeKnob(D["at.amount"]),
      makeToggle(D["at.dest_freq1"]),
      makeToggle(D["at.dest_freq2"]),
      makeToggle(D["at.dest_lfo"], { label: "LFO Amt" }),
      makeToggle(D["at.dest_amp"]),
      makeFilterPair("at.dest_lp", "at.dest_hp"),
    ]),
    section("Misc Parameters", [
      makeKnob(D["misc.pan_spread"]),
      makeCodeDisplay(D["unison.key_mode"], KEYMODE_CODES, { label: "Key Mode" }),
      makeCodeDisplay(D["misc.pbend_range"], null, { label: "P Whl Range" }),
      makeKnob(D["misc.program_volume"]),
    ]),
  ));

  /* --- middle bands --- */
  panel.appendChild(rowOf(
    column(
      rowOf(
        section("Distort", [makeKnob(D["dist.amount"], { label: "Amount" })]),
        section("Effects", [
          makeToggle(D["fx.on"], { label: "On/Off" }),
          subgroup("A", [
            makeCodeDisplay(D["fxa.type"], FX_CODES, { label: "Type" }),
            makeScreenKnob(D["fxa.mix"], { label: "Mix" }),
            makeScreenKnob(D["fxa.param1"], { label: "Param 1" }),
            makeScreenKnob(D["fxa.param2"], { label: "Param 2" }),
            makeToggle(D["fxa.sync"], { label: "Sync" }),
          ]),
          subgroup("B", [
            makeCodeDisplay(D["fxb.type"], FX_CODES, { label: "Type" }),
            makeScreenKnob(D["fxb.mix"], { label: "Mix" }),
            makeScreenKnob(D["fxb.param1"], { label: "Param 1" }),
            makeScreenKnob(D["fxb.param2"], { label: "Param 2" }),
            makeToggle(D["fxb.sync"], { label: "Sync" }),
          ]),
        ]),
      ),
      section("Low Frequency Oscillator", [
        makeKnob(D["lfo.frequency"]),
        makeToggle(D["lfo.sync"], { label: "LFO Sync" }),
        makeLedList(D["lfo.shape"], { label: "Shape",
          names: { "triangle": "Triangle", "sawtooth": "Sawtooth",
                   "rev-sawtooth": "Rev Saw", "square": "Square", "random": "Random" } }),
        makeKnob(D["lfo.initial_amount"], { label: "Initial Amt" }),
        makeToggle(D["lfo.dest_freq1"]),
        makeToggle(D["lfo.dest_freq2"]),
        makeToggle(D["lfo.dest_pw12"]),
        makeToggle(D["lfo.dest_amp"]),
        makeFilterPair("lfo.dest_lp", "lfo.dest_hp"),
      ]),
    ),
    column(
      rowOf(
        section("Oscillator 1", [
          makeKnob(D["osc1.frequency"]),
          makeToggle(D["osc1.sync"]),
          makeKnobSelect(D["osc1.shape"]),
          makeKnob(D["osc1.pulse_width"]),
        ]),
        section("Slop", [makeKnob(D["slop.amount"], { label: "Amount" })]),
      ),
      section("Oscillator 2", [
        makeKnob(D["osc2.frequency"]),
        makeKnob(D["osc2.fine"]),
        makeKnobSelect(D["osc2.shape"]),
        makeKnob(D["osc2.pulse_width"]),
        makeToggle(D["osc2.low_freq"]),
        makeToggle(D["osc2.keyboard"]),
      ]),
    ),
    section("Mixer", [
      makeKnob(D["mixer.osc1"]), makeKnob(D["mixer.osc2"]),
      makeKnob(D["mixer.sub_octave"]), makeKnob(D["mixer.noise"]),
    ], "grid2 tall"),
    column(
      section("High-Pass Filter", [
        makeKnob(D["hpf.cutoff"]),
        makeKnob(D["hpf.resonance"]),
        makeKnob(D["hpf.env_amount"]),
        makeToggle(D["hpf.velocity"]),
        makeHalfFull(D["hpf.keyboard"]),
      ]),
      section("Low-Pass Filter", [
        makeKnob(D["lpf.cutoff"]),
        makeKnob(D["lpf.resonance"]),
        makeKnob(D["lpf.env_amount"]),
        makeToggle(D["lpf.velocity"]),
        makeHalfFull(D["lpf.keyboard"]),
      ]),
    ),
    column(
      section("Filter Envelope", [
        makeKnob(D["fenv.attack"]), makeKnob(D["fenv.decay"]),
        makeKnob(D["fenv.sustain"]), makeKnob(D["fenv.release"]),
      ]),
      section("Amplifier Envelope", [
        makeToggle(D["aenv.velocity"]),
        makeKnob(D["aenv.env_amount"]),
        makeKnob(D["aenv.attack"]), makeKnob(D["aenv.decay"]),
        makeKnob(D["aenv.sustain"]), makeKnob(D["aenv.release"]),
      ]),
    ),
  ));

  /* --- bottom band --- */
  const digits = Array.from({ length: 10 }, (_, i) => capButton(String(i)));
  panel.appendChild(rowOf(
    section("Transpose", [capButton("Down"), capButton("Up")], "plain bottom"),
    section("", [capToggle(D["arp.hold"], "Hold")], "plain bottom"),
    section("", [
      makeKnob(D["glide.rate"], { label: "Glide Rate" }),
      capToggle(D["glide.on"], "Glide"),
      makeCodeDisplay(D["glide.mode"], GLIDE_CODES, { label: "Mode" }),
    ], "plain bottom"),
    section("", [
      capToggle(D["unison.on"], "Unison"),
      makeCodeDisplay(D["unison.voices"], null, { label: "Voices" }),
    ], "plain bottom"),
    section("", [
      capButton("Bank Select"), deco("display", "Bank Program", "P.1"), capButton("Tens Select"),
    ], "plain bottom"),
    section("", digits, "plain bottom digits"),
    section("", [capButton("Write", { red: true }), capButton("Globals"), capButton("Preset")],
      "plain bottom"),
    section("", [Object.assign(document.createElement("div"),
      { className: "logo-badge", innerHTML: "prophet~6" })], "plain bottom"),
  ));

  // safety net: any schema param the layout forgot lands in a visible fallback section
  const missing = Object.keys(DEFS).filter(id => !els[id]);
  if (missing.length)
    panel.appendChild(rowOf(section("Unplaced", missing.map(id => makeKnob(DEFS[id])))));

  resetToInit(false);
}

function resetToInit(animate) {
  for (const { def, set, root } of Object.values(els)) {
    set(SCHEMA.init[def.id], animate);
    root.classList.remove("changed", "moving", "peek");
    const sec = root.closest(".section");
    if (sec) sec.classList.remove("touched");
  }
}

/* used by MIDI capture: apply a full decoded param set instantly */
function applyParams(params) {
  resetToInit(false);
  for (const { def, set, root } of Object.values(els)) {
    if (def.id in params) {
      set(params[def.id], false);
      root.classList.add("changed");
      const sec = root.closest(".section");
      if (sec) sec.classList.add("touched");
    }
  }
}

/* ====================================================================== *
 *  MODERN SHELL                                                          *
 * ====================================================================== */
function setStatus(msg, cls = "idle") {
  const s = $("#status");
  s.textContent = msg;
  s.className = `status ${cls}`;
}

function badgeClass(source) {
  return source.startsWith("Manual") ? "manual"
       : source.startsWith("reddit") ? "reddit"
       : source.startsWith("patch") ? "patch" : "general";
}

function renderInspector(patch) {
  const changed = patch.changes.length;
  const grounded = patch.changes.filter(c => c.source && c.source !== "general synthesis").length;
  const pct = changed ? Math.round((grounded / changed) * 100) : 0;

  const rows = patch.changes.map((c, i) => {
    const def = DEFS[c.param];
    const label = def ? def.label : c.param;
    const sec = SEC_OF[c.param] || "";
    const val = readoutText(def, c.value);
    return `<div class="change" data-i="${i}" data-pid="${c.param}">
      <div class="head">
        <span class="pname">${label} <small>· ${sec}</small></span>
        <span class="pval">${val}</span>
      </div>
      <div class="why">${c.why || ""}</div>
      <span class="badge ${badgeClass(c.source || "")}">${c.source || "general synthesis"}</span>
    </div>`;
  }).join("");

  $("#inspector").innerHTML = `
    <div class="result">
      <h2>${patch.patch_name}</h2>
      <p class="query-echo">“${patch.query}”</p>
      <p class="summary">${patch.summary || ""}</p>
      <div class="stats">
        <div class="stat"><div class="n amber">${changed}</div><div class="k">Params changed</div></div>
        <div class="stat"><div class="n">${pct}%</div><div class="k">Corpus-grounded</div></div>
        <div class="stat"><div class="n">${patch.retrieved.length}</div><div class="k">Sources</div></div>
      </div>
      ${patch.problems && patch.problems.length
        ? `<div class="problems"><b>Validator:</b> ${patch.problems.join("; ")}</div>` : ""}
      <div class="section-title">Changes</div>
      <div id="changeList">${rows}</div>
      ${patch.playing_tip ? `<div class="tip">
        <svg viewBox="0 0 24 24"><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2Z"/><path d="M9 21h6"/></svg>
        <span>${patch.playing_tip}</span></div>` : ""}
      <div class="section-title">Retrieved context</div>
      <div class="sources">${patch.retrieved.map(r =>
        `<a href="${r.url}" target="_blank" rel="noopener"><span class="tag">${badgeClass(r.label)}</span>${r.label}</a>`
      ).join("")}</div>
    </div>`;

  // hover a change row -> peek the matching control on the panel
  $("#changeList").querySelectorAll(".change").forEach(row => {
    const el = els[row.dataset.pid];
    if (!el) return;
    row.addEventListener("mouseenter", () => {
      el.root.classList.add("peek");
      el.root.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    });
    row.addEventListener("mouseleave", () => el.root.classList.remove("peek"));
  });
}

async function animatePatch(patch, sentTo = false) {
  resetToInit(false);
  setStatus(sentTo ? `Sent to ${sentTo} — animating…` : "Starting from INIT…", "working");
  await sleep(650);
  for (let i = 0; i < patch.changes.length; i++) {
    const c = patch.changes[i];
    const el = els[c.param];
    if (!el) continue;
    const row = $(`#changeList .change[data-i="${i}"]`);
    el.root.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    el.root.classList.add("moving");
    const sec = el.root.closest(".section");
    if (sec) sec.classList.add("touched");
    if (row) { row.classList.add("lit"); row.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    setStatus(`Setting ${i + 1}/${patch.changes.length} · ${el.def.label}`, "working");
    el.set(c.value, true);
    await sleep(460);
    el.root.classList.remove("moving");
    el.root.classList.add("changed");
    if (row) row.classList.remove("lit");
    await sleep(90);
  }
  const tail = sentTo ? ` · loaded on ${sentTo}` : "";
  setStatus(`“${patch.patch_name}” — ${patch.changes.length} parameters adjusted${tail}`, "done");
}

async function generate(query) {
  if (busy) return;
  busy = true;
  $("#goBtn").classList.add("loading");
  $("#goBtn").disabled = true;
  setStatus("Retrieving corpus + designing patch…", "working");
  try {
    const res = await fetch("/api/patch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || res.statusText);
    renderInspector(data);
    const sentTo = midi.on ? sendSysex(data.sysex) : false;   // bulk load up-front (D-030)
    await animatePatch(data, sentTo);
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  } finally {
    busy = false;
    $("#goBtn").classList.remove("loading");
    $("#goBtn").disabled = false;
  }
}

/* fit the (1500px-wide) hardware unit to the stage, or show it 1:1 */
let zoom100 = false;
function fitUnit() {
  const stage = $("#stage"), unit = $("#unit");
  if (!stage || !unit) return;
  unit.style.zoom = "1";
  if (zoom100) return;
  const avail = stage.clientWidth - 56;        // stage horizontal padding
  const natural = unit.offsetWidth;
  if (natural > 0) unit.style.zoom = String(Math.min(1, avail / natural));
}
function setZoom(fit) {
  zoom100 = !fit;
  $("#zoomFit").classList.toggle("on", fit);
  $("#zoom100").classList.toggle("on", !fit);
  fitUnit();
}

/* ============================== MIDI out (D-030) — ported ============================== */
const midi = { on: false, access: null, outId: null };
const midiSupported = () => typeof navigator.requestMIDIAccess === "function";
const midiOutputs = () => midi.access ? [...midi.access.outputs.values()] : [];

function refreshMidiPorts() {
  const sel = $("#midiPort");
  const outs = midiOutputs();
  sel.innerHTML = outs.length
    ? outs.map(o => `<option value="${o.id}">${o.name}</option>`).join("")
    : `<option value="">no MIDI output</option>`;
  if (outs.length) {
    const saved = localStorage.getItem("p6.midiPort");
    const pick = outs.find(o => o.id === saved)
      || outs.find(o => /prophet|sequential|p6/i.test(o.name)) || outs[0];
    midi.outId = pick.id; sel.value = pick.id;
  } else midi.outId = null;
  sel.disabled = !midi.on || !outs.length;
}

async function enableMidi() {
  if (!midiSupported()) { setMidiHint("Web MIDI not supported — use Chrome or Edge."); return false; }
  try {
    midi.access = await navigator.requestMIDIAccess({ sysex: true });
    midi.access.onstatechange = () => { if (midi.on) refreshMidiPorts(); };
    return true;
  } catch (e) { setMidiHint(`MIDI access denied: ${e.message || e}`); return false; }
}

function sendSysex(bytes) {
  if (!midi.on) return false;
  if (!bytes || !bytes.length) { setStatus("MIDI on, but no sysex in response", "error"); return false; }
  const out = midi.access && midi.outId && midi.access.outputs.get(midi.outId);
  if (!out) { setStatus("MIDI on, but no output port selected", "error"); return false; }
  try { out.send(Uint8Array.from(bytes)); return out.name; }
  catch (e) { setStatus(`MIDI send failed: ${e.message || e}`, "error"); return false; }
}

function reflectMidiUi() {
  const btn = $("#midiBtn"), tg = $("#midiToggle");
  btn.classList.toggle("on", midi.on);
  tg.classList.toggle("on", midi.on);
  tg.classList.toggle("off", !midi.on);
  tg.textContent = midi.on ? "MIDI output is ON" : "MIDI output is OFF";
  $("#midiCapture").disabled = !midi.on;
}

async function toggleMidi() {
  if (!midi.on) {
    if (!midi.access && !(await enableMidi())) return;
    midi.on = true; refreshMidiPorts(); reflectMidiUi();
    const out = midi.outId && midi.access.outputs.get(midi.outId);
    setMidiHint(out ? `Connected — ${out.name}` : "On — connect a Prophet-6.");
  } else {
    midi.on = false; $("#midiPort").disabled = true; reflectMidiUi();
    setMidiHint("MIDI output off.");
  }
}

function pickInput() {
  if (!midi.access) return null;
  const ins = [...midi.access.inputs.values()];
  const out = midi.outId && midi.access.outputs.get(midi.outId);
  return ins.find(i => out && i.name === out.name)
      || ins.find(i => /prophet|sequential|p6/i.test(i.name)) || ins[0] || null;
}

async function captureFromP6() {
  if (!midi.on || !midi.access) { setMidiHint("Turn MIDI on first."); return; }
  const input = pickInput();
  if (!input) { setMidiHint("No MIDI input found — is the Prophet-6 connected?"); return; }
  setStatus(`Requesting current patch from ${input.name}…`, "working");
  const buf = []; let done = false;
  const finish = async () => {
    if (done) return; done = true; input.onmidimessage = null;
    if (buf.length < 8) { setStatus("No valid sysex received from the Prophet-6", "error"); return; }
    try {
      const res = await fetch("/api/decode", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sysex: buf }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || res.statusText);
      applyParams(data.params);
      setStatus(`Captured “${data.name || "patch"}” (${data.bytes} bytes) — decoded to panel`, "done");
    } catch (err) { setStatus(`Capture decode failed: ${err.message || err}`, "error"); }
  };
  input.onmidimessage = (e) => {
    for (const b of e.data) { if (b === 0xF0) buf.length = 0; buf.push(b); if (b === 0xF7) finish(); }
  };
  const out = midi.outId && midi.access.outputs.get(midi.outId);
  if (out) { try { out.send([0xF0, 0x01, 0x2D, 0x06, 0xF7]); } catch (e) { /* ignore */ } }
  setTimeout(() => {
    if (!done) { input.onmidimessage = null;
      setStatus("No response — do a manual Pgm Dump on the P6, or check its MIDI Sysex global", "error"); }
  }, 6000);
}

function setMidiHint(msg) { $("#midiHint").textContent = msg; }
function toggleMidiPanel(force) {
  const p = $("#midiPanel");
  p.hidden = force === undefined ? !p.hidden : !force;
}

/* ============================== boot ============================== */
document.addEventListener("DOMContentLoaded", async () => {
  SCHEMA = await (await fetch("/api/schema")).json();
  for (const [name, params] of SCHEMA.sections)
    for (const def of params) { DEFS[def.id] = def; SEC_OF[def.id] = name; }
  renderPanel(SCHEMA);
  fitUnit();
  window.addEventListener("resize", fitUnit);

  $("#queryForm").addEventListener("submit", e => {
    e.preventDefault();
    const q = $("#queryInput").value.trim();
    if (q) generate(q);
  });
  $("#resetBtn").addEventListener("click", () => {
    if (busy) return;
    if (midi.on && sendSysex(SCHEMA.init_sysex)) { resetToInit(true); setStatus("INIT — sent to Prophet-6", "done"); }
    else { resetToInit(true); setStatus("INIT — every control reset", "idle"); }
  });
  document.querySelectorAll(".suggest .chip").forEach(chip =>
    chip.addEventListener("click", () => {
      $("#queryInput").value = chip.textContent;
      generate(chip.textContent);
    }));
  $("#changesOnly").addEventListener("change", e =>
    $("#panel").classList.toggle("filtered", e.target.checked));
  $("#zoomFit").addEventListener("click", () => setZoom(true));
  $("#zoom100").addEventListener("click", () => setZoom(false));

  // MIDI controls
  if (!midiSupported()) {
    $("#midiBtn").disabled = true;
    $("#midiBtn").title = "Web MIDI unsupported (use Chrome/Edge)";
  }
  $("#midiBtn").addEventListener("click", () => { if (!busy) toggleMidiPanel(); });
  $("#midiClose").addEventListener("click", () => toggleMidiPanel(false));
  $("#midiToggle").addEventListener("click", () => { if (!busy) toggleMidi(); });
  $("#midiCapture").addEventListener("click", () => { if (!busy) captureFromP6(); });
  $("#midiPort").addEventListener("change", e => {
    midi.outId = e.target.value || null;
    if (midi.outId) localStorage.setItem("p6.midiPort", midi.outId);
    const out = midi.outId && midi.access.outputs.get(midi.outId);
    if (out) setMidiHint(`Port: ${out.name}`);
  });
  document.addEventListener("click", e => {
    if (!$("#midiPanel").hidden && !e.target.closest("#midiPanel") && !e.target.closest("#midiBtn"))
      toggleMidiPanel(false);
  });
  reflectMidiUi();

  const q = new URLSearchParams(location.search).get("q");   // ?q= auto-runs a query
  if (q) { $("#queryInput").value = q; generate(q); }
});
