/* Prophet-6 visual patch panel — desktop-module layout (matches prophet6.jpg).
   Controls are laid out in the hardware's four bands; decorative items (Tap Tempo,
   Sequencer, Transpose, program buttons…) are inert. Patch animation: reset to INIT,
   turn each adjusted control into place sequentially, leave it highlighted. */

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const els = {};      // param id -> {def, root, set(value, animate)}
let SCHEMA = null;
let DEFS = {};       // param id -> def
let busy = false;

const $ = (sel, parent = document) => parent.querySelector(sel);

/* ---- MIDI out (D-030): Mode-1 bulk edit-buffer load via Web MIDI ---- */
const midi = { on: false, access: null, outId: null };

function midiSupported() { return typeof navigator.requestMIDIAccess === "function"; }

function midiOutputs() {
  return midi.access ? [...midi.access.outputs.values()] : [];
}

function refreshMidiPorts() {
  const sel = $("#midiPort");
  const outs = midiOutputs();
  sel.innerHTML = outs.length
    ? outs.map(o => `<option value="${o.id}">${o.name}</option>`).join("")
    : `<option value="">no MIDI output</option>`;
  if (outs.length) {
    // prefer a saved port, else one that looks like a Prophet
    const saved = localStorage.getItem("p6.midiPort");
    const pick = outs.find(o => o.id === saved)
      || outs.find(o => /prophet|sequential|p6/i.test(o.name)) || outs[0];
    midi.outId = pick.id;
    sel.value = pick.id;
  } else {
    midi.outId = null;
  }
  sel.disabled = !midi.on || !outs.length;
}

async function enableMidi() {
  if (!midiSupported()) { setStatus("Web MIDI not supported in this browser"); return false; }
  try {
    midi.access = await navigator.requestMIDIAccess({ sysex: true });
    midi.access.onstatechange = () => { if (midi.on) refreshMidiPorts(); };
    return true;
  } catch (e) {
    setStatus(`MIDI access denied: ${e.message || e}`);
    return false;
  }
}

function sendSysex(bytes) {
  if (!midi.on) return false;
  if (!bytes || !bytes.length) { setStatus("MIDI on, but no sysex in response"); return false; }
  const out = midi.access && midi.outId && midi.access.outputs.get(midi.outId);
  if (!out) { setStatus("MIDI on, but no output port selected"); return false; }
  try {
    out.send(Uint8Array.from(bytes));  // one edit-buffer dump; synth loads the full patch
    console.log(`[midi] sent ${bytes.length} bytes to "${out.name}" (state=${out.state}, conn=${out.connection})`);
    return out.name;  // truthy port name on success
  } catch (e) {
    setStatus(`MIDI send failed: ${e.message || e}`);
    console.error("[midi] send error", e);
    return false;
  }
}

async function toggleMidi() {
  const btn = $("#midiToggle");
  if (!midi.on) {
    if (!midi.access && !(await enableMidi())) return;
    midi.on = true;
    refreshMidiPorts();
    btn.textContent = "MIDI ⏻ ON";
    btn.classList.replace("off", "on");
    $("#midiCapture").disabled = false;
    const out = midi.outId && midi.access.outputs.get(midi.outId);
    setStatus(out ? `MIDI on — ${out.name}` : "MIDI on — connect a Prophet-6");
  } else {
    midi.on = false;
    btn.textContent = "MIDI ⏻ OFF";
    btn.classList.replace("on", "off");
    $("#midiPort").disabled = true;
    $("#midiCapture").disabled = true;
    setStatus("MIDI off");
  }
}

function pickInput() {
  if (!midi.access) return null;
  const ins = [...midi.access.inputs.values()];
  const out = midi.outId && midi.access.outputs.get(midi.outId);
  return ins.find(i => out && i.name === out.name)            // same device as output
      || ins.find(i => /prophet|sequential|p6/i.test(i.name))
      || ins[0] || null;
}

function applyParams(params) {
  for (const { def, set, root } of Object.values(els)) {
    if (def.id in params) {
      set(params[def.id], true);
      root.classList.add("changed");
      const sec = root.closest(".section");
      if (sec) sec.classList.add("touched");
    }
  }
}

async function captureFromP6() {
  if (!midi.on || !midi.access) { setStatus("turn MIDI on first"); return; }
  const input = pickInput();
  if (!input) { setStatus("no MIDI input found — is the Prophet-6 connected?"); return; }
  setStatus(`requesting current patch from ${input.name}…`);
  const buf = [];
  let done = false;
  const finish = async () => {
    if (done) return;
    done = true;
    input.onmidimessage = null;
    if (buf.length < 8) { setStatus("no valid sysex received from the Prophet-6"); return; }
    try {
      const res = await fetch("/api/decode", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sysex: buf }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || res.statusText);
      applyParams(data.params);
      console.log("[midi] captured patch:", data);
      setStatus(`captured "${data.name || "patch"}" (${data.bytes} bytes) — `
        + `decoded to panel + saved to data/patches/${data.file || "captured_dump.json"}`);
    } catch (err) {
      setStatus(`capture decode failed: ${err.message || err}`);
    }
  };
  input.onmidimessage = (e) => {            // buffer one F0…F7 sysex
    for (const b of e.data) {
      if (b === 0xF0) buf.length = 0;
      buf.push(b);
      if (b === 0xF7) finish();
    }
  };
  const out = midi.outId && midi.access.outputs.get(midi.outId);  // ask the P6 to send it
  if (out) { try { out.send([0xF0, 0x01, 0x2D, 0x06, 0xF7]); } catch (e) { /* ignore */ } }
  setTimeout(() => {
    if (!done) {
      input.onmidimessage = null;
      setStatus("no response — on the P6 do a manual Pgm Dump, or check the MIDI Sysex global");
    }
  }, 6000);
}

/* ---- hardware display codes (from the manual's 7-segment readouts) ---- */
const FX_CODES = { "off": "OFF", "bbd-delay": "bbd", "digital-delay": "ddL", "chorus": "CHO",
  "phaser-1": "PH1", "phaser-2": "PH2", "phaser-3": "PH3", "ring-mod": "rin",
  "flanger": "FL1", "flanger-2": "FL2",
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

/* ---- control builders: each returns a .param root and registers in els ---- */

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
  // pointer-less 360° encoder knob + its own red value screen (P6 FX mix/param knobs)
  const root = document.createElement("div");
  root.className = "param knob encoder mini";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dial"></div>
    <div class="miniscreen"></div><div class="plabel">${opts.label || def.label}</div>`;
  const screen = $(".miniscreen", root);
  return reg(def, root, value => { screen.textContent = value; });
}


function makeKnobSelect(def, opts = {}) { // hardware shape knobs (osc 1/2)
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

function makeHalfFull(def) { // filter keyboard tracking: off/half/full as two LEDs
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

function makeCodeDisplay(def, codes, opts = {}) { // red 7-seg style window
  const root = document.createElement("div");
  root.className = "param display";
  root.dataset.id = def.id; root.title = def.hint;
  root.innerHTML = `<div class="dispwin"></div><div class="plabel">${opts.label || def.label}</div>`;
  const win = $(".dispwin", root);
  return reg(def, root, value => { win.textContent = codes ? (codes[value] ?? value) : value; });
}

function makeFilterPair(lpId, hpId) { // FILTER destination: LP/HP LED pair
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

/* ---- decorative (non-patch) hardware items ---- */
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

function capButton(label, opts = {}) { // bottom-row rectangular switch
  const d = document.createElement("div");
  d.className = `param cap deco`;
  d.innerHTML = `<button class="capbtn ${opts.red ? "red" : ""}" tabindex="-1"><span class="led"></span></button>
    <div class="plabel">${label}</div>`;
  return d;
}

function capToggle(def, label) { // bottom-row switch bound to a param
  const root = capButton(label);
  root.classList.remove("deco");
  root.dataset.id = def.id; root.title = def.hint;
  const btn = $(".capbtn", root);
  return reg(def, root, value => btn.classList.toggle("on", !!value));
}

/* ---- section / band assembly ---- */
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

  /* --- middle bands: columns spanning two rows where the hardware does --- */
  panel.appendChild(rowOf(
    column(
      rowOf(
        section("Distort", [makeKnob(D["dist.amount"], { label: "Amount" })]),
        section("Effects", [
          makeToggle(D["fx.on"], { label: "On/Off" }),
          // FX mix/param knobs are pointer-less 360° encoders on the hardware;
          // each value reads out on its own red screen (ranges per Appendix C:
          // mix 0-127, param1 0-255, param2 0-127)
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
    root.classList.remove("changed", "moving");
    const sec = root.closest(".section");
    if (sec) sec.classList.remove("touched");
  }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

function badge(source) {
  const cls = source.startsWith("Manual") ? "manual"
            : source.startsWith("reddit") ? "reddit"
            : source.startsWith("patch") ? "patch" : "general";
  return `<span class="badge ${cls}">${source || "general synthesis"}</span>`;
}

function sectionOf(pid) {
  for (const [name, params] of SCHEMA.sections)
    if (params.some(p => p.id === pid)) return name;
  return "";
}

function renderSidebar(patch) {
  const side = $("#sidebar");
  side.innerHTML = `
    <h3>${patch.patch_name}</h3>
    <div class="summary">${patch.summary}</div>
    <div id="changeList">${patch.changes.map((c, i) => {
      const def = DEFS[c.param];
      return `<div class="change" data-i="${i}">
        <div class="head"><span class="pname">${def.label}
          <small style="color:#6e6a60">· ${sectionOf(c.param)}</small></span>
          <span class="pval">${readoutText(def, c.value)}</span></div>
        <div class="why">${c.why}</div>${badge(c.source)}
      </div>`;
    }).join("")}</div>
    ${patch.playing_tip ? `<div class="tip">▸ ${patch.playing_tip}</div>` : ""}
    ${patch.problems.length ? `<div class="problems">Validator notes: ${patch.problems.join("; ")}</div>` : ""}
    <div class="src-list"><h4>Retrieved context</h4>
      ${patch.retrieved.map(r => `<a href="${r.url}" target="_blank">${r.label}</a>`).join("")}
    </div>`;
}

async function animatePatch(patch, sentTo = false) {
  resetToInit(false);
  setStatus(sentTo ? `✓ sent to ${sentTo} — animating…` : "starting from INIT…");
  await sleep(700);
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
    setStatus(`setting ${i + 1}/${patch.changes.length}: ${el.def.label}`);
    el.set(c.value, true);
    await sleep(480);
    el.root.classList.remove("moving");
    el.root.classList.add("changed");
    if (row) row.classList.remove("lit");
    await sleep(90);
  }
  const tail = sentTo ? ` · loaded on ${sentTo}` : "";
  setStatus(`“${patch.patch_name}” — ${patch.changes.length} parameters adjusted${tail}`);
}

function setStatus(msg) { $("#status").textContent = msg; }

async function generate(query) {
  busy = true;
  $("#goBtn").disabled = true;
  setStatus("retrieving + designing patch…");
  try {
    const res = await fetch("/api/patch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || res.statusText);
    renderSidebar(data);
    // MIDI ON: load the whole patch to the hardware up-front (one edit-buffer dump);
    // the animation below is then purely visual (D-030).
    const sentTo = midi.on ? sendSysex(data.sysex) : false;
    await animatePatch(data, sentTo);
  } catch (e) {
    setStatus(`error: ${e.message}`);
  } finally {
    busy = false;
    $("#goBtn").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  SCHEMA = await (await fetch("/api/schema")).json();
  for (const [, params] of SCHEMA.sections)
    for (const def of params) DEFS[def.id] = def;
  renderPanel(SCHEMA);
  $("#queryForm").addEventListener("submit", e => {
    e.preventDefault();
    const q = $("#queryInput").value.trim();
    if (q && !busy) generate(q);
  });
  $("#resetBtn").addEventListener("click", () => {
    if (busy) return;
    if (midi.on && sendSysex(SCHEMA.init_sysex)) { resetToInit(true); setStatus("INIT — sent to Prophet-6"); }
    else { resetToInit(true); setStatus("INIT"); }
  });
  // MIDI controls
  if (!midiSupported()) {
    $("#midiToggle").disabled = true;
    $("#midiToggle").title = "Web MIDI unsupported (use Chrome/Edge)";
  }
  $("#midiToggle").addEventListener("click", () => { if (!busy) toggleMidi(); });
  $("#midiCapture").addEventListener("click", () => { if (!busy) captureFromP6(); });
  $("#midiPort").addEventListener("change", e => {
    midi.outId = e.target.value || null;
    if (midi.outId) localStorage.setItem("p6.midiPort", midi.outId);
    const out = midi.outId && midi.access.outputs.get(midi.outId);
    if (out) setStatus(`MIDI port: ${out.name}`);
  });
  const params = new URLSearchParams(location.search);
  const x = params.get("x");                 // ?x=px pre-scrolls the panel (screenshots)
  if (x) $(".synth").scrollLeft = +x;
  const q = params.get("q");                 // shareable ?q= links auto-run
  if (q) { $("#queryInput").value = q; generate(q); }
});
