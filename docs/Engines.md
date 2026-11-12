# Engines

## What they are

The studio drives other people's open models; it ships none of them. Each runs in its own Python environment when
their requirements clash, and the studio re-runs itself in the right one for each job.

| Role | Model | Where |
|---|---|---|
| Text-to-speech (the default) | Qwen3-TTS Base, cloning a reference | local |
| Designing a voice from words | Qwen3-TTS VoiceDesign | local |
| Your read in the character's voice; ⇄ Mirror | Seed-VC | local |
| ✦ Restyle by editing a clip (optional) | Step-Audio-EditX | local |
| Text-to-speech with an emotion mix (optional) | IndexTTS2 | local |
| Text-to-speech in the cloud (optional, paid) | xAI | cloud |
| Checking takes | faster-whisper, SpeechBrain ECAPA, torchaudio SQUIM | local |

A voice's engine is set on the Cast tab (`cast.toml` `engine`); a line can use another. Local engines never send a
line anywhere; a voice set to a cloud engine sends its lines' words to that service, and the page asks before
switching a voice to one.

## Expected outcome

Everything works offline on one machine with a recent NVIDIA GPU. Optional engines appear on the page only once they
are installed, and the page says what's missing for one that isn't.

## Licenses and consent

The studio is Apache-2.0. The models carry their own licenses, which bind what you run and, for some, what you ship:
check each before release. Use a real person's voice as a reference only with their written consent, and disclose
generated voices where your store requires it.

## Where the details are

Detailed instruction and information on each engine (models, environments, settings, GPU memory, licenses, and how to
add an engine) can be found in docs/details/engines-details.md.
