# Known Issues

Open bugs and gaps, with the diagnosis already done so we can resume cold.

---

## ISSUE-1 — Schema INIT defaults are ungrounded (amp envelope visible on hardware)

**Status:** RESOLVED 2026-06-12 (D-031). Builder captured the real P6 "Basic Program" via
the new MIDI Capture button; it decoded cleanly (first live receive-direction test) and was
byte-identical to the librarian reference, confirming authenticity. `INIT_PATCH` in
`patch_schema.py` was reset to those values for the 15 sound-defining params (amp env now
A0 D127 S0 R40, etc.), keeping 3 quirks neutral for a clean canvas (pan_spread=0,
fxb.type=off, lfo.dest_freq1=off — option B). Verified: INIT now matches hardware except
exactly those 3; encoder self-test still 771/771. Original capture saved at
`data/patches/captured_dump.json`.

**(original diagnosis, retained for reference:)**
**Status:** open, diagnosed, fix deferred (builder paused work 2026-06-12).
**Symptom:** loading patches — and even `"Default INIT patch"` — to the physical
Prophet-6 (MIDI Mode 1, D-030) shows amp-envelope **attack and sustain** not at the
values the hardware treats as default.

**Diagnosis (done — NOT a pipeline bug):**
- Querying `"Default INIT patch"` returns **0 changes** → the resolved patch is pure
  `INIT_PATCH`; the LLM is not injecting stray values.
- `encode(INIT) → decode(INIT)` round-trips **byte-perfect**, amp envelope included →
  the encoder is not corrupting bytes.
- Amp-env offsets verified against real factory patches (pads = slow attack/high
  sustain, plucks = instant attack/zero sustain) → byte mapping is correct.
- **Root cause:** `src/ui/patch_schema.py` `INIT_PATCH` defaults were hand-authored
  from general synth intuition in the first panel build, never decoded from a real P6
  INIT. They don't match the hardware's true defaults.

**Evidence — schema INIT vs a decoded real P6 program (the carrier), 18 disagreements;
amp/filter envelope ones:**

| param | schema INIT | real program |
|---|---|---|
| aenv.decay | 40 | 127 |
| aenv.sustain | 127 | 0 |
| aenv.release | 0 | 40 |
| fenv.decay | 40 | 0 |

(The carrier — librarian "Basic Program" in `data/patches/init_template.json` — is itself
a *demo* sound, not a blank INIT: it has a flanger, pan spread, an LFO routed. So it is
NOT an authoritative INIT source either; it only proves our values are guesses.)

**Fix options (deferred):**
1. Quick: builder reads amp Attack/Decay/Sustain/Release off a freshly-INIT'd P6 and we
   set `INIT_PATCH` to match.
2. Best: builder dumps a real INIT edit buffer from the P6 (`.syx`) → decode it into the
   authoritative `INIT_PATCH`, grounding **every** default at once. Also the first test of
   the decoder in the *receive* direction.

**Debug script:** `src/patches/_debug_aenv.py` reproduces all of the above.

---

## ISSUE-2 — Reverb on Effect A crashes the encoder → whole patch not transmitted

**Status:** RESOLVED 2026-06-12 (D-032). `fxa.type` options restricted to the reverb-free
FX-A set; validate_changes drops a reverb-on-A; `_encode_value` falls back to "off" on any
unknown select instead of crashing. Verified: reverb-on-A is dropped at validation and the
encoder never crashes; self-test 771/771.
**Root cause:** the schema offers the *same* 12-type list (incl. reverbs) for BOTH
`fxa.type` and `fxb.type`, but the real hardware **FX A (FX1) cannot do reverbs** — and
the encoder's FX-A option list (`SELECT_OPTIONS[44] = FX_TYPES[:6]+FX_TYPES[10:]`) has no
reverbs. So when the LLM (seeing reverbs allowed on A) assigns e.g. `fxa.type=hall-reverb`,
`encode_edit_buffer` does `list.index("hall-reverb")` on a list without it → `ValueError`
→ `_sysex_for` swallows it → **`sysex` returns None → nothing is sent to the synth.**
Confirmed: encoding `fxa.type=hall-reverb` raises; `chorus` (a valid FX-A type) encodes fine.
`fxb.type=hall-reverb` encodes correctly (byte 6) — FX B / decode order is NOT the problem.
**Proposed fix:** restrict `fxa.type` options to the real FX-A set (no reverbs); unify the
schema FX lists with `decode_sysex.FX_TYPES` so order/membership can't drift; and harden
`_encode_value` to clamp/skip an out-of-list select instead of crashing the whole dump.
**Debug script:** `src/patches/_debug_fxon.py` + the inline reverb-on-A test.

## ISSUE-3 — Master `fx.on` was mapped to the wrong byte (54 → really 46)

**Status:** RESOLVED 2026-06-19. A hardware capture-diff (same patch with FX ON vs OFF,
nothing else changed) flipped **exactly one byte: offset 46**. So the master Effects on/off
switch is byte **46**, not 54. `decode_sysex.LAYOUT` corrected to `46: ("fx.on", bool)`; the
factory bank was re-decoded under the corrected map and the encoder self-test stays 771/771.
This is the root cause of the "FX panel won't switch ON when a patch is sent" report — we
were writing `fx.on` to byte 54, which the synth ignores. It also explains the original
508/765 finding below (we were reading the wrong byte). Captures + diff tool:
`src/patches/diff_captures.py`.
**Knock-on (now open):** the old `fxa.sync`/`fxb.sync` guesses (offsets 46/47) collapsed with
this — 46 is `fx.on`, so both sync toggles are left **unmapped (raw-only)** until a targeted
FX-A/B-sync on/off capture locates them (same diff method). Offset 54's real meaning is also
unknown.

**(original diagnosis, retained for reference:)**
**Finding:** 508 of 765 factory patches that have an effect configured (type + mix) decode
to `fx.on = False`. Possibly offset 54 is mislabeled, or factory patches genuinely ship
effects configured-but-disabled. No FX-region byte cleanly correlates with audible-effect
presence, so it can't be resolved from the corpus alone. **If 54 is wrong, a reverb placed
correctly on FX B would still not engage on the synth** — the other half of the
"not transmitted" report. **Resolve via capture:** on the P6 set a patch with FX clearly
ON, capture; set FX OFF, capture; diff the two dumps — the byte that flips is the real
`fx.on`.

## ISSUE-4 — "Unison Voices" display has no physical counterpart (visual fidelity)

**Status:** open, design choice (builder reported). 
**Finding:** the panel renders a persistent red "Voices" display in the Unison section. On
the real P6 there is **no dedicated voices readout** — voice count is set by *holding* the
Unison button and using Bank/Tens Inc/Dec, shown only momentarily on the main program
display. The parameter itself is real and saved (NRPN 157, decode offset 85), so it's
legitimately part of a patch — it just isn't a standing control on the hardware.
**Proposed fix:** remove the standalone Voices display for fidelity (the value still
appears in the sidebar change list when a patch sets it), or relabel it as a derived
readout. (Note: other program params are also held-button/menu settings on the real panel
— e.g. unison key mode, glide mode, pbend range — so this is the first of a small class.)

## ISSUE-5 — FX-type enum order was wrong (FX B showed "FL1" for plate reverb)

**Status:** RESOLVED 2026-06-19. Two hardware captures anchored **flanger (FL1) = byte 45 value 8**
and **plate reverb (PLA) = 12**; the corrected internal order was cross-checked against synthmutt's
byte-level Ctrlr P6 `.syx` panel, which independently reproduces both anchors plus the trusted
off=0/bbd=1/ddl=2/chorus=3. Corrected `FX_TYPES` (byte value -> effect):
`0 off, 1 bbd-delay, 2 digital-delay, 3 chorus, 4 phaser-1, 5 phaser-2, 6 phaser-3, 7 ring-mod,
8 flanger (FL1), 9 flanger-2 (FL2), 10 hall, 11 room, 12 plate, 13 spring`. New vocabulary fact:
the P6 exposes **two flangers** (FL1/FL2) — adding FL2 at 9 is what places plate at 12.
Applied across `decode_sysex.FX_TYPES` + `LAYOUT[44]` (FX-A = `FX_TYPES[:10]`, reverb-free),
`encode_sysex.SELECT_OPTIONS`, `patch_schema` fxa/fxb options, and the panel `FX_CODES`
(added FL1/FL2). Factory bank re-decoded; encoder self-test 771/771; verified plate->byte45=12,
flanger->8, flanger-2->9, spring->13.
**Original symptom (builder, 2026-06-19):** a patch with `fxb.type=plate-reverb` displayed as **FL1**
on the synth — because encoding plate wrote byte 45 = 8 under the old *assumed* order, and the
hardware reads value 8 as flanger.
**Still to ratify (low risk):** only flanger=8 and plate=12 are direct hardware anchors; the
in-between values (phaser-3=6, ring-mod=7, FL2=9, hall=10, room=11, spring=13) and the FX-A
sub-list come from the byte-level panel source. A capture pass (set FX-B to each in turn, diff
byte 45 via `src/patches/diff_captures.py`) would fully confirm them.

---
