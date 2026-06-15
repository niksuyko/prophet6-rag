# Future Phases (v3+ candidates)

Captured-but-deferred ideas, with enough reasoning to resume cold.

---

## FP-1 — Audio-to-patch: "match the synth in this song"

**Ask:** give the system a finished song (vocals + drums + bass + synths) and a target
moment, get a P6 patch in the ballpark of that synth.

**Verdict:** realistic for "a *starting* patch close to a *prominent* part you then tweak";
NOT realistic for "automatic exact clone from a dense mix" (fundamental, not just effort).

**Pipeline (composes with existing pieces):**
1. User uploads audio + a timestamp/region (a song has many sounds; user picks the target).
2. **Source separation** (Demucs-class) → isolate the synth/"other" stem. This is where the
   full-mix difficulty concentrates.
3. **Feature analysis** of the isolated clip → structured sound descriptor: register,
   waveform character (spectral shape → saw/square/triangle leaning), brightness (filter
   proxy), attack/release (amplitude envelope), movement (LFO/PWM via periodicity),
   detune/chorus width, saturation, mono/poly.
4. **Descriptor → P6 patch** by feeding it to the EXISTING RAG patch designer as a query
   ("bright detuned saw lead, fast attack, slow filter sweep, light chorus") so it adapts a
   real factory patch and respects P6 architecture; feature→parameter seeding gives a head
   start.
5. **Render-and-refine** (rigorous): load candidate via MIDI-out (D-030), capture audio,
   embed target+candidate (CLAP-style), score similarity, iterate. This is the deferred
   **audio eval** — the keystone dependency.
6. **Output:** patch + similarity score + honest report ("matched detune & filter sweep;
   couldn't match the FM bell layer — outside P6 architecture"), same anti-claim ethos as
   the cross-synth translation table.

**Hard parts (why exact clone stays out of reach):**
- Isolating ONE synth among several layered in the "other" stem; buried pads separate badly.
  Sweet spot = exposed lead/bass.
- You match the *recorded/processed* sound (mix reverb/EQ/compression/mastering baked in),
  not the raw synth.
- Inversion is ill-posed: many param sets → near-identical sound; only perceptually-close
  patches exist, not a unique "correct" one. ("Close starting point" is the realistic goal.)
- Architecture limits: FM/wavetable/sampled targets only approximable on a subtractive P6.

**Dependencies / order:** sits on top of the deferred **audio eval** (v3 keystone) and the
**MIDI-out renderer** (D-030, done). Eval-first: build the audio-similarity metric before
trusting any audio→patch output.

**Tradeoff to weigh:** first phase that BREAKS the project's CPU-only / no-heavy-ML-infra
rule — separation + audio embeddings want a GPU. Deliberate departure, not free.

---

### FP-1 design detail (captured 2026-06-14, design discussion)

**Integration principle:** audio is NOT a parallel system. It's a new front-end that
produces the same thing the text path already consumes (a query + seed parameters), so
~70% of the back-end (generate_patch, retrieve, corpus, schema, panel, MIDI-out) is reused.

**Stage flow** (audio front-end converges onto the existing `retrieve → generate`):
```
audio in (upload / loopback capture)
  → waveform region select (slider)
  → Demucs: isolate synth stem            [acquire+clean analog]
  → feature analysis → SOUND DESCRIPTOR   [the new contract artifact, ~ chunks.jsonl]
       ├─► text query   → retrieve() over corpus ─┐
       └─► seed params  → generate_patch (LLM) ───┴─► JSON patch → panel + MIDI-out
```

**How audio is "read" (feature extraction → P6 params).** Audio is just amplitude samples
(44,100/sec). Two lenses: time domain (amplitude→envelope) and frequency domain (FFT/STFT
→ spectrogram→timbre). Each measurement seeds a parameter:
- amplitude envelope (envelope follower) → **A/D/S/R** (rise=attack, etc.)
- spectral centroid ("center of mass" of spectrum) → **filter cutoff**; its motion over the
  note → **filter envelope sweep**
- harmonic shape (all harmonics=saw, odd-only=square, odd+steep=triangle) → **osc shape / PW**
- fundamental f0 (autocorrelation / YIN pitch tracker) → **osc frequency / register**
- beating (two near-equal f0s interfering = slow amplitude pulse) → **detune / slop / unison**
  (beat rate = detune amount)
- spectral flatness (tonal vs noise) → **noise**; inharmonic partials → **ring-mod / FM**
- L/R decorrelation → **pan spread / chorus**; diffuse decaying tail → **reverb / delay**
- **LFO/movement trick:** take a feature time-series (pitch, amplitude, or brightness over
  time) and FFT *that series* — a peak at e.g. 4 Hz = the **LFO rate**, its size = depth;
  which feature wobbles tells the destination (pitch→osc, amp→tremolo, brightness→filter/PWM).

**Two readings, two jobs:** classic DSP features (above) seed *interpretable* knobs; a
learned **CLAP embedding** is a holistic "fingerprint" for *audio→audio retrieval* — find the
factory patch that sounds nearest (the audio analog of `similar.py`'s param-space NN).

**Adapt, not snap (D-024 reused).** The nearest-sounding preset is a SEED, not the output.
Division of labor: CLAP finds the seed (closest real patch) → the DSP descriptor says how the
target *differs* from it ("brighter, slower attack, +4 Hz filter wobble") → the LLM adapts the
seed toward the target, citing `patch:<id>` for kept moves. Feed top-N seeds so it can blend.
Optionally offer a "snap" toggle (load the closest real patch verbatim) as a fast baseline.
The render-and-match loop then refines the adapted patch against the actual sound.

**Building the audio→audio patch index — automated, NOT manual per-patch.** A script loops
over all 770 patches: load patch via MIDI sysex (D-030, already built) → play a MIDI test note
→ record the P6's audio output N seconds → trim/normalize/save → next. ~1–1.5 h unattended.
- **One hardware prerequisite:** an audio interface (P6 stereo out → interface → computer
  line-in). The P6's USB is MIDI-ONLY — it does not stream audio over USB — so audio capture
  needs the analog path. One-time human setup = cabling + pick the test note + start the script.
- **Test note:** use the SAME note for all 770 (comparability > which note). A held mid C +
  release tail covers most; 2–3 notes (low/mid/high) + a held chord improves coverage.
- **Double duty:** the same record-a-patch rig IS the "render + capture" step of the
  render-and-match loop AND the keystone audio eval — build it once, unlock all three.
- **No-hardware bootstrap:** render through a software P6-approximation (u-he/Arturia-class)
  — faster/scalable but not the real unit's sound; use only as a stopgap.

**Polyphony / chord-input mismatch (known limitation).** The index + DSP assumptions are
monophonic (mid-C). A *chord* input is out-of-distribution and degrades gracefully:
- survives: brightness/cutoff, envelope (for block chords), LFO/movement (affect all notes).
- degrades: f0/register (multiple fundamentals confuse a mono pitch tracker), waveform
  inference (stacked harmonic series muddy the saw/square/triangle read), and **detune is
  OVER-read** (inter-note beating mimics oscillator detune). CLAP match also noisier (a
  chord's fuller texture ≠ a single note's).
- mitigations: (a) guide the user via the slider to pick a monophonic moment; (b) detect
  polyphony and down-weight pitch-dependent features; (c) record a chord fingerprint per
  preset too, and match like-with-like (chord input → chord recordings).

**Reused vs new:** reused — generate_patch, retrieve, corpus, similar.py, MIDI-out (D-030),
patch_quality eval. New — audio I/O + waveform UI, Demucs, DSP descriptor, CLAP embeddings +
audio index, render→capture→compare loop, audio-similarity eval.

**Phasing:** (1) audio→audio patch index first (only needs MIDI-out + capture + CLAP; instantly
useful as "what factory patch sounds like this clip?"); (2) Demucs + DSP descriptor front-end;
(3) close the render-and-match refinement loop. Each step independently valuable.

### FP-1 polyphony / chord handling (external research, captured 2026-06-14)

Mono-only would waste a poly synth. The field handles polyphonic input well; the resolution
hinges on one reframe plus three established approaches.

**THE KEY REFRAME — a chord is N copies of ONE patch.** On a subtractive poly synth every
voice in a chord uses the *identical* patch (same filter/env/osc); polyphony is just that one
voice at several pitches. So we don't reverse-engineer each note — we estimate the single
*shared* parameter set from a mixture. That converts "polyphonic transcription" (hard) into
"extract shared synthesis params from a mixture of harmonic sounds" — studied directly in the
DDSP Mixture Model (Hayes et al., arXiv:2202.00200).

**Three approaches (and how each fits our pipeline):**

1. **Neural inverse synthesis (audio→params), trained on the synth's own output.** Lineage:
   InverSynth (CNN on spectrograms, arXiv:1812.06349) → audio-spectrogram-transformer sound
   matching (DAFx 2024) → DiffMoog differentiable modular synth (arXiv:2401.12570) →
   Sound2Synth (FM). Pattern: render millions of (params→audio) pairs, train a net to invert.
   FIT: our recording rig IS the training-data generator — and we can render presets playing
   CHORDS, so the model is poly-robust by construction (no mono assumption baked in).

2. **Differentiable synthesis + perceptual loss = our render-and-match loop, upgraded.**
   DDSP (Engel et al., openreview B1x1ma4tDr), DiffMoog, "Learning to Solve Inverse Problems
   for Perceptual Sound Matching" (arXiv:2311.14213), Modulation Discovery w/ DDSP
   (arXiv:2510.06204). Make the synth differentiable, optimize params by gradient descent to
   minimize an audio-similarity loss between target and candidate. Same as our render-match
   loop but with gradients (far more efficient), and the loss is computed on the FULL
   polyphonic audio — never needs to separate the chord into notes. Chords just work.

3. **Polyphonic transcription as a front-end (only if per-note reads are wanted).**
   basic-pitch (Spotify, lightweight, instrument-agnostic, ICASSP 2022) or MT3 (transformer,
   multi-instrument, arXiv:2111.03017) extract the chord's notes; then fold the spectrum
   per-note and AVERAGE the inferred timbre (valid because all notes share the patch).
   "Scaling Polyphonic Transcription with Mixtures of Monophonic Transcriptions" (ISMIR 2022)
   is the decompose-to-mono variant. Carries its own transcription error on dense harmonics,
   so it's the weaker backbone vs. routes 1–2.

**Least-new-machinery poly-robust path (recommended):**
- Use a **polyphony-robust perceptual loss** (CLAP-style or multi-resolution spectral) on the
  FULL audio for BOTH the audio→audio retrieval and the render-match loop — it compares whole
  sounds, so it has no monophonic assumption to break (chord target vs chord render is fine).
- **Generate poly data with the recording rig** — render each preset playing chords as well as
  single notes, so the index (and any learned inverse model) is poly-native.
- Add **basic-pitch** as a cheap front-end only where the interpretable pitch/detune part of
  the descriptor is wanted, replacing the mono pitch tracker that chokes on chords.
- The "shared patch" reframe is the theory that makes all of this sound.

**Caveats:** research-grade, GPU + training-data dependent (the rig generates it, but it's real
work); sound matching stays imperfect/ill-posed even in the papers (close-start-then-tweak
reality holds); poly transcription itself errs on overlapping harmonics (favor routes 1–2).

---
