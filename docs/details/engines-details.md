# Engines: details

The concept is in docs/Engines.md. Code: `verbaline/models.py` (`ENGINES`, `EMOTION`, `STYLES`, `PITCH`, `EDITX`),
the batch runners in `verbaline/runners/`.

## Text-to-speech engines

| Id | Label | Class | Needs |
|---|---|---|---|
| `qwen` | Qwen3-TTS clone | `Qwen` | `qwen-tts` in `[envs] qwen` (or the studio's Python); model `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| `indextts2` | IndexTTS2 | `IndexTTS2` | `[repos] index_tts` checkout, `[envs] indextts2`; offered only when the checkout exists |
| `xai` | xAI | `XAI` | `XAI_API_KEY` in the studio's environment; cloud, paid |

- **Qwen3-TTS** (Apache-2.0). Clones the reference for the line's emotion, with its transcript. Its emotion comes only
  from that reference. bfloat16 on `cuda:0`; flash-attn is used when installed. A take is capped at about 8
  characters a second plus 3 s.
- **VoiceDesign** (`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`, Apache-2.0) makes candidates from a description and
  ✦ Restyle's acted tries. It makes a new voice every time.
- **IndexTTS2**: an 8-emotion mix per line (`models.EMOTION`). Check its license before shipping anything it makes.
- **xAI**: one of its voices (`xai_voice`: ara, aurora, carina, celeste, eve, iris, liora, luna, ursa, or its male
  voices) at `xai_speed` (0.7-1.5). Direction goes in the line's `say` as xAI tags (`[pause]`, `<loud>...</loud>`);
  whisper and shouting lines get tags added. For the service, put `XAI_API_KEY=...` in its env file
  (`~/.config/verbaline/env` by default) and restart it. On Windows, `setx XAI_API_KEY <key>` and start the studio
  from a new terminal.
- **Chatterbox** was removed: its output fell short. A voice or line naming it is made with the default engine; its
  old takes stay pickable.

## Seed-VC

GPL-3.0; a tool the studio runs as a separate program (`runners/seedvc_run.py`), not code it ships. Its output audio
isn't covered by the GPL. `[repos] seed_vc` (a checkout of https://github.com/Plachtaa/seed-vc) and
`[repos] seed_vc_python` (its own environment). Two models: the timbre model ("clone" takes; sets the voice's own
pitch, follows intonation loosely, r 0.67-0.77) and the pitch-aware model ("pitch" takes; intonation note for note,
r 0.97-0.99, moved by a pitch shift). `[convert]`: `kinds`, `cfg_rate` 0.7, `diffusion_steps` 30. A voice's
fine-tuned models (`verbaline train`) are used for the kind they were tuned from. Training needs OpenVoice V2's
converter and `se_db.pt` in Seed-VC's `checkpoints/`.

## Step-Audio-EditX (optional)

StepFun, Apache-2.0, 3B, about 15 GB with its models. `scripts/install_editx.sh` installs its code, models and own
Python (3.12, PyTorch 2.9, vLLM); then set `[repos] step_audio_editx`, `[repos] step_audio_models` and `[envs] editx`.
`models.editx_missing()` says what's missing; the page offers the engine once nothing is. It runs through
`runners/editx_run.py`, waiting for about 14 GB of free GPU memory (`[train] gpu_slot` when set); it holds about 13 GB
(vLLM's share is 0.32 of the card, `VERBALINE_EDITX_GPU` overrides it).

## The checks

`verbaline score` (`[score]`): faster-whisper `whisper_model` (large-v3) transcribes; word error against the words
(`max_wer` 0.34); SpeechBrain ECAPA cosine to the take's reference (cached in `~/.cache/verbaline/ecapa`);
torchaudio SQUIM's PESQ estimate for audio quality. The total weighs words 0.45, voice 0.35, quality 0.20; a take with
stray end words is capped at 0.5. `SCORE_VERSION` in `cli.py` rescored everything when bumped.

## Environments

The studio re-runs a job in `[envs]`'s Python for its model: `qwen` for design, restyle and Qwen takes; `score` for
scoring, mirror, beat and restyle-keep; the engine's id for `tts`; nothing for xAI. Unset: the studio's own Python.
Every environment needs the studio's own light requirements (`pip install -e <studio>` in it).

Known-good versions (an RTX 5090, Fedora): Python 3.11 throughout; PyTorch 2.8.0+cu128 in each environment; the studio
with transformers 5.2, faster-whisper 1.2.1, speechbrain 1.1.1; Qwen with transformers 4.57.3, qwen-tts 0.1.1;
Seed-VC with transformers 4.46.3.

## Adding an engine

1. A class in `models.py` with `__init__(self, ctx)`, `__enter__`/`__exit__` (load and free the model), `needs_ref`,
   and `say(self, text, ref, ref_text, emotion, voice, out, seed=1)` writing a WAV to `out`.
2. An `ENGINES` entry: `label`, `cloud`, `cls`. A cloud engine's lines are sent only for voices set to it.
3. If it needs its own Python, an `[envs]` key named after its id, documented in docs/details/configuration-details.md.
4. Its license in this file. A check in tests/test_verbaline.py that the engine is listed and refused when not installed.
