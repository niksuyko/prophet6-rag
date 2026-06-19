"""Prophet-6 front-panel parameter schema (decisions.md D-020).

Every parameter is grounded in the manual chunks in the corpus (sections: Oscillators,
Mixer, Filters, Filter Envelope, Amplifier Envelope, Low Frequency Oscillators,
Poly Mod, Effects - Main Parameters, Arpeggiator, Aftertouch, Glide, Slop, Distortion,
Unison, Misc Parameters). The same schema drives three things:
  1. the LLM prompt (parameter ids, ranges, semantics),
  2. server-side validation of generated patches,
  3. the visual panel (sections, control types, INIT values).

Param types:
  knob     - continuous, integer min..max
  bipolar  - continuous, integer min..max with 0 center detent
  toggle   - on/off button (bool)
  select   - one of `options`
"""

# (section, [params]) in panel display order.
SECTIONS = [
    ("Oscillator 1", [
        dict(id="osc1.frequency", label="Frequency", type="knob", min=0, max=60, init=24,
             hint="Pitch in semitones over the knob's 5-octave range (12 per semitone step; "
                  "24 = standard bass/lead register; NRPN range 0-60). Higher = higher pitch."),
        dict(id="osc1.shape", label="Shape", type="select", init="sawtooth",
             options=["triangle", "tri-saw", "sawtooth", "saw-pulse", "pulse"],
             hint="Continuously variable waveshape knob; pick the nearest shape. Sawtooth = "
                  "bright/classic, triangle = mellow, pulse = hollow/reedy."),
        dict(id="osc1.pulse_width", label="Pulse Width", type="knob", min=0, max=255, init=127,
             hint="Width of the pulse wave; 127 (center) = square, extremes = very narrow "
                  "pulse. Only audible when shape is pulse (or being PW-modulated)."),
        dict(id="osc1.sync", label="Sync", type="toggle", init=False,
             hint="Hard-syncs Osc 1 (slave) to Osc 2 (master) for aggressive, harmonically "
                  "rich tones; sweep Osc 1 pitch via Poly Mod for the classic sync sound."),
    ]),
    ("Oscillator 2", [
        dict(id="osc2.frequency", label="Frequency", type="knob", min=0, max=60, init=24,
             hint="Pitch in semitones; set a few semitones/octaves apart from Osc 1 for "
                  "intervals, or equal for detune-only thickness."),
        dict(id="osc2.fine", label="Fine", type="bipolar", min=-127, max=127, init=0,
             hint="Fine tune; full range is about a quartertone each way (±127 ≈ ±50 cents). "
                  "Small offsets (10-25) against Osc 1 give classic analog thickness."),
        dict(id="osc2.shape", label="Shape", type="select", init="sawtooth",
             options=["triangle", "tri-saw", "sawtooth", "saw-pulse", "pulse"],
             hint="Same continuously variable shape knob as Osc 1."),
        dict(id="osc2.pulse_width", label="Pulse Width", type="knob", min=0, max=255, init=127,
             hint="Pulse width for Osc 2; 127 = square."),
        dict(id="osc2.low_freq", label="Low Freq", type="toggle", init=False,
             hint="Turns Osc 2 into an extra LFO source (use with Poly Mod)."),
        dict(id="osc2.keyboard", label="Keyboard", type="toggle", init=True,
             hint="Off = Osc 2 ignores the keyboard and stays at its base frequency (drones, "
                  "fixed-pitch FM via Poly Mod)."),
    ]),
    ("Mixer", [
        dict(id="mixer.osc1", label="Osc 1", type="knob", min=0, max=127, init=127,
             hint="Oscillator 1 output level."),
        dict(id="mixer.osc2", label="Osc 2", type="knob", min=0, max=127, init=0,
             hint="Oscillator 2 output level."),
        dict(id="mixer.sub_octave", label="Sub Octave", type="knob", min=0, max=127, init=0,
             hint="Triangle sub-oscillator one octave below Osc 1; adds low-register weight "
                  "(great on basses)."),
        dict(id="mixer.noise", label="Noise", type="knob", min=0, max=127, init=0,
             hint="White noise level (breath, percussion, wind)."),
    ]),
    ("Low-Pass Filter", [
        dict(id="lpf.cutoff", label="Cutoff", type="knob", min=0, max=164, init=163,
             hint="4-pole 24 dB/oct resonant low-pass cutoff (hardware range 0-164). "
                  "Lower = darker/warmer."),
        dict(id="lpf.resonance", label="Resonance", type="knob", min=0, max=255, init=0,
             hint="Emphasis at the cutoff; high values self-oscillate."),
        dict(id="lpf.env_amount", label="Env Amount", type="bipolar", min=-127, max=127, init=0,
             hint="Bipolar amount of Filter Envelope applied to LP cutoff; negative inverts "
                  "the envelope."),
        dict(id="lpf.velocity", label="Velocity", type="toggle", init=False,
             hint="Key velocity scales the filter envelope (play harder = brighter when env "
                  "amount is positive)."),
        dict(id="lpf.keyboard", label="Keyboard", type="select", init="off",
             options=["off", "half", "full"],
             hint="Keyboard tracking of LP cutoff; full tracks in semitones (tuned "
                  "self-oscillation)."),
    ]),
    ("High-Pass Filter", [
        dict(id="hpf.cutoff", label="Cutoff", type="knob", min=0, max=164, init=0,
             hint="2-pole 12 dB/oct resonant high-pass cutoff (hardware range 0-164). "
                  "Higher = thinner, removes low end. Combine with LPF for band-pass."),
        dict(id="hpf.resonance", label="Resonance", type="knob", min=0, max=255, init=0,
             hint="Resonance of the high-pass filter."),
        dict(id="hpf.env_amount", label="Env Amount", type="bipolar", min=-127, max=127, init=0,
             hint="Bipolar amount of Filter Envelope applied to HP cutoff."),
        dict(id="hpf.velocity", label="Velocity", type="toggle", init=False,
             hint="Velocity scales the filter envelope's effect on the HP filter."),
        dict(id="hpf.keyboard", label="Keyboard", type="select", init="off",
             options=["off", "half", "full"],
             hint="Keyboard tracking of HP cutoff."),
    ]),
    ("Filter Envelope", [
        dict(id="fenv.attack", label="Attack", type="knob", min=0, max=127, init=0,
             hint="Filter envelope attack time (higher = slower opening)."),
        dict(id="fenv.decay", label="Decay", type="knob", min=0, max=127, init=0,
             hint="Filter envelope decay time."),
        dict(id="fenv.sustain", label="Sustain", type="knob", min=0, max=127, init=0,
             hint="Cutoff level held while a note is down."),
        dict(id="fenv.release", label="Release", type="knob", min=0, max=127, init=0,
             hint="How quickly the filter closes after note release."),
    ]),
    ("Amplifier Envelope", [
        dict(id="aenv.env_amount", label="Env Amount", type="knob", min=0, max=127, init=127,
             hint="Amplifier envelope depth into the VCA; usually full. Set to 0 and route "
                  "LFO square to Amp for gated-VCA effects."),
        dict(id="aenv.attack", label="Attack", type="knob", min=0, max=127, init=0,
             hint="Volume attack time. Pads = long, plucks/percussive = 0."),
        dict(id="aenv.decay", label="Decay", type="knob", min=0, max=127, init=0,
             hint="Volume decay time after the attack peak."),
        dict(id="aenv.sustain", label="Sustain", type="knob", min=0, max=127, init=127,
             hint="Held volume level while a key is down (0 for plucks)."),
        dict(id="aenv.release", label="Release", type="knob", min=0, max=127, init=40,
             hint="How quickly the sound dies out after release."),
        dict(id="aenv.velocity", label="Velocity", type="toggle", init=False,
             hint="Key velocity modulates VCA envelope amount (touch-sensitive volume)."),
    ]),
    ("Low Frequency Oscillator", [
        dict(id="lfo.frequency", label="Frequency", type="knob", min=0, max=254, init=134,
             hint="LFO speed, from very slow sweeps into the audible range."),
        dict(id="lfo.initial_amount", label="Initial Amt", type="knob", min=0, max=255, init=0,
             hint="LFO modulation depth applied continuously to the selected destinations. "
                  "At 0, LFO modulation rides only on the mod wheel."),
        dict(id="lfo.shape", label="Shape", type="select", init="triangle",
             options=["triangle", "sawtooth", "rev-sawtooth", "square", "random"],
             hint="Triangle = vibrato/tremolo/PWM, square = trills, random = sample & hold."),
        dict(id="lfo.sync", label="LFO Sync", type="toggle", init=False,
             hint="Syncs the LFO to the arpeggiator/sequencer/MIDI clock."),
        dict(id="lfo.dest_freq1", label="Freq 1", type="toggle", init=False,
             hint="Route LFO to Osc 1 pitch (triangle = vibrato)."),
        dict(id="lfo.dest_freq2", label="Freq 2", type="toggle", init=False,
             hint="Route LFO to Osc 2 pitch."),
        dict(id="lfo.dest_pw12", label="PW 1+2", type="toggle", init=False,
             hint="Route LFO to both oscillators' pulse width — triangle LFO here gives the "
                  "chorus-like PWM movement used for strings/pads."),
        dict(id="lfo.dest_amp", label="Amp", type="toggle", init=False,
             hint="Route LFO to amplitude (tremolo)."),
        dict(id="lfo.dest_lp", label="LP Filter", type="toggle", init=False,
             hint="Route LFO to low-pass cutoff (auto-wah / filter movement)."),
        dict(id="lfo.dest_hp", label="HP Filter", type="toggle", init=False,
             hint="Route LFO to high-pass cutoff."),
    ]),
    ("Poly Mod", [
        dict(id="pmod.filt_env", label="Filt Env", type="bipolar", min=-127, max=127, init=0,
             hint="Bipolar modulation amount from the Filter Envelope to the selected "
                  "destinations."),
        dict(id="pmod.osc2", label="Osc 2", type="bipolar", min=-127, max=127, init=0,
             hint="Bipolar modulation amount from Osc 2 (FM-style; set Osc 2 to low freq "
                  "for slower modulation)."),
        dict(id="pmod.dest_freq1", label="Freq 1", type="toggle", init=False,
             hint="Destination: Osc 1 pitch (classic sync sweeps, FM clang)."),
        dict(id="pmod.dest_shape1", label="Shape 1", type="toggle", init=False,
             hint="Destination: Osc 1 waveshape (animated timbre)."),
        dict(id="pmod.dest_pw1", label="PW 1", type="toggle", init=False,
             hint="Destination: Osc 1 pulse width."),
        dict(id="pmod.dest_lp", label="LP Filter", type="toggle", init=False,
             hint="Destination: low-pass cutoff."),
        dict(id="pmod.dest_hp", label="HP Filter", type="toggle", init=False,
             hint="Destination: high-pass cutoff."),
    ]),
    ("Aftertouch", [
        dict(id="at.amount", label="Amount", type="bipolar", min=-127, max=127, init=0,
             hint="Bipolar aftertouch depth to the selected destinations (key pressure)."),
        dict(id="at.dest_freq1", label="Freq 1", type="toggle", init=False,
             hint="Aftertouch bends Osc 1 pitch."),
        dict(id="at.dest_freq2", label="Freq 2", type="toggle", init=False,
             hint="Aftertouch bends Osc 2 pitch."),
        dict(id="at.dest_lfo", label="LFO Amt", type="toggle", init=False,
             hint="Aftertouch fades in LFO modulation (pressure vibrato — very expressive)."),
        dict(id="at.dest_amp", label="Amp", type="toggle", init=False,
             hint="Aftertouch swells volume."),
        dict(id="at.dest_lp", label="LP Filter", type="toggle", init=False,
             hint="Aftertouch opens/closes the low-pass filter (pressure brightness)."),
        dict(id="at.dest_hp", label="HP Filter", type="toggle", init=False,
             hint="Aftertouch moves the high-pass cutoff."),
    ]),
    ("Effect A", [
        dict(id="fxa.type", label="Type", type="select", init="off",
             # FX A (FX1) has NO reverbs on the hardware — must stay a subset of
             # decode_sysex SELECT_OPTIONS[44]; a reverb here is unrepresentable (D-032)
             options=["off", "bbd-delay", "digital-delay", "chorus", "phaser-1", "phaser-2",
                      "phaser-3", "ring-mod"],
             hint="Effect A type. FX A has NO reverbs — put any reverb on Effect B. "
                  "bbd = warm analog-style delay; chorus = vintage thickener; "
                  "phaser-1 = deep resonant sweep."),
        dict(id="fxa.mix", label="Mix", type="knob", min=0, max=127, init=64,
             hint="Wet/dry balance for Effect A (0 = dry)."),
        dict(id="fxa.param1", label="Param 1", type="knob", min=0, max=255, init=100,
             hint="Delay: time. Chorus/phaser: rate. Reverb: time (spring: decay)."),
        dict(id="fxa.param2", label="Param 2", type="knob", min=0, max=127, init=100,
             hint="Delay: feedback. Chorus/phaser: depth. Reverb: early reflections "
                  "(spring: tone)."),
        dict(id="fxa.sync", label="Clock Sync", type="toggle", init=False,
             hint="Syncs Effect A's delay time to the arpeggiator/sequencer/MIDI clock "
                  "(delay effects only)."),
    ]),
    ("Effect B", [
        dict(id="fxb.type", label="Type", type="select", init="off",
             options=["off", "bbd-delay", "digital-delay", "chorus", "phaser-1", "phaser-2",
                      "phaser-3", "ring-mod", "hall-reverb", "room-reverb", "plate-reverb",
                      "spring-reverb"],
             hint="Effect B type (commonly a reverb after a modulation effect on A)."),
        dict(id="fxb.mix", label="Mix", type="knob", min=0, max=127, init=64,
             hint="Wet/dry balance for Effect B."),
        dict(id="fxb.param1", label="Param 1", type="knob", min=0, max=255, init=64,
             hint="Same per-type meaning as Effect A param 1."),
        dict(id="fxb.param2", label="Param 2", type="knob", min=0, max=127, init=64,
             hint="Same per-type meaning as Effect A param 2."),
        dict(id="fxb.sync", label="Clock Sync", type="toggle", init=False,
             hint="Syncs Effect B's delay time to the clock (delay effects only)."),
    ]),
    ("Effects Master", [
        dict(id="fx.on", label="On/Off", type="toggle", init=False,
             hint="Master effects on/off (true bypass when off)."),
    ]),
    ("Arpeggiator / Clock", [
        dict(id="arp.on", label="On/Off", type="toggle", init=False,
             hint="Arpeggiator on/off."),
        dict(id="arp.mode", label="Mode", type="select", init="up+down",
             options=["up", "down", "up+down", "random", "assign"],
             hint="Arpeggio note order."),
        dict(id="arp.octaves", label="Octaves", type="select", init="1",
             options=["1", "2", "3"],
             hint="Arpeggio octave range."),
        dict(id="arp.hold", label="Hold", type="toggle", init=False,
             hint="Latches held notes (arp keeps playing after you let go)."),
        dict(id="clock.bpm", label="BPM", type="knob", min=30, max=250, init=120,
             hint="Internal clock tempo for the arp/sequencer and synced delay/LFO."),
        dict(id="clock.divide", label="Value", type="select", init="16th",
             options=["half", "quarter", "8th", "8th-half-swing", "8th-full-swing",
                      "8th-triplet", "16th", "16th-half-swing", "16th-full-swing",
                      "16th-triplet"],
             hint="Clock divide (time signature) for the arpeggiator/sequencer: note value "
                  "per clock beat, including swing and triplet feels."),
    ]),
    ("Glide", [
        dict(id="glide.on", label="Glide", type="toggle", init=False,
             hint="Portamento on/off (rate must also be above 0 to hear it)."),
        dict(id="glide.rate", label="Glide Rate", type="knob", min=0, max=127, init=0,
             hint="Portamento rate/time between notes."),
        dict(id="glide.mode", label="Mode", type="select", init="fixed-rate",
             options=["fixed-rate", "fixed-rate-legato", "fixed-time", "fixed-time-legato"],
             hint="Legato modes glide only when notes overlap."),
    ]),
    ("Unison", [
        dict(id="unison.on", label="Unison", type="toggle", init=False,
             hint="Monophonic voice-stack mode — up to 12 oscillators on one note for huge "
                  "basses/leads."),
        dict(id="unison.voices", label="Voices", type="select", init="1",
             options=["1", "2", "3", "4", "5", "6", "chord"],
             hint="Number of stacked voices in unison; 'chord' = chord-memory mode "
                  "(latches a chord shape onto single keys)."),
        dict(id="unison.key_mode", label="Key Mode", type="select", init="low",
             options=["low", "high", "last", "low-retrig", "high-retrig", "last-retrig"],
             hint="Note priority when more than one key is held."),
    ]),
    ("Character", [
        dict(id="slop.amount", label="Slop", type="knob", min=0, max=127, init=0,
             hint="Randomized oscillator detune emulating vintage tuning instability; small "
                  "amounts = warm and fat, high = wildly out of tune. Also detunes unison "
                  "stacks."),
        dict(id="dist.amount", label="Distortion", type="knob", min=0, max=127, init=0,
             hint="Stereo analog distortion — warmth at low settings, aggressive edge "
                  "when pushed."),
        dict(id="misc.pan_spread", label="Pan Spread", type="knob", min=0, max=127, init=0,
             hint="Spreads voices alternately left/right for a wide stereo field."),
        dict(id="misc.program_volume", label="Prgm Vol", type="knob", min=0, max=127, init=127,
             hint="Per-program volume, for matching levels between programs."),
        dict(id="misc.pbend_range", label="P Whl Range", type="knob", min=0, max=24, init=7,
             hint="Pitch-wheel range in semitones (12 = one octave each way)."),
    ]),
]

PARAMS = {p["id"]: p for _, plist in SECTIONS for p in plist}
INIT_PATCH = {pid: p["init"] for pid, p in PARAMS.items()}


def schema_for_prompt() -> str:
    """Compact schema text for the LLM prompt."""
    lines = []
    for section, plist in SECTIONS:
        lines.append(f"## {section}")
        for p in plist:
            if p["type"] in ("knob", "bipolar"):
                rng = f"integer {p['min']}..{p['max']}"
            elif p["type"] == "toggle":
                rng = "true|false"
            else:
                rng = "|".join(p["options"])
            lines.append(f"- {p['id']} ({rng}, init={p['init']!r}): {p['hint']}")
    return "\n".join(lines)


def validate_changes(changes: list, meta: dict | None = None) -> tuple[list, list]:
    """Clamp/coerce LLM-proposed changes to the schema. Returns (clean, problems).

    Pass an optional `meta` dict to capture the otherwise-silent mutations (clamped
    values, fuzzy-matched selects, coerced toggles, dropped no-ops) for observability.
    The (clean, problems) return is byte-identical whether or not `meta` is supplied, so
    eval callers (e.g. eval/patch_accuracy.py) are unaffected."""
    clean, problems = [], []
    clamped, noop, fuzzy, coerced = [], [], [], []
    for ch in changes:
        pid = ch.get("param")
        p = PARAMS.get(pid)
        if p is None:
            problems.append(f"unknown param {pid!r} dropped")
            continue
        val = ch.get("value")
        if p["type"] in ("knob", "bipolar"):
            try:
                val = int(round(float(val)))
            except (TypeError, ValueError):
                problems.append(f"{pid}: non-numeric value {val!r} dropped")
                continue
            proposed = val
            val = max(p["min"], min(p["max"], val))
            if val != proposed:
                clamped.append({"param": pid, "proposed": proposed, "clamped": val,
                                "min": p["min"], "max": p["max"]})
        elif p["type"] == "toggle":
            if isinstance(val, str):
                b = val.strip().lower() in ("true", "on", "yes", "1")
                coerced.append({"param": pid, "proposed": val, "bool": b})
                val = b
            val = bool(val)
        else:  # select
            sval = str(val).strip().lower()
            match = next((o for o in p["options"] if o.lower() == sval), None)
            if match is None:
                match = next((o for o in p["options"] if sval and sval in o.lower()), None)
                if match is not None:
                    fuzzy.append({"param": pid, "proposed": val, "matched": match})
            if match is None:
                problems.append(f"{pid}: option {val!r} not in {p['options']} — dropped")
                continue
            val = match
        if val == p["init"]:
            noop.append(pid)
            continue  # not actually a change
        clean.append({"param": pid, "value": val,
                      "why": str(ch.get("why", "")).strip(),
                      "source": str(ch.get("source", "")).strip()})
    if meta is not None:
        meta.update({"clamped_values": clamped, "noop_dropped": noop,
                     "select_fuzzy_matched": fuzzy, "coerced_toggle": coerced})
    return clean, problems
