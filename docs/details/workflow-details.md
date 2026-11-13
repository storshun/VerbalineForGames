# Directing and voicing: details

The concept is in docs/Workflow.md. Commands are shown as `verbaline <command>`; every one also runs from the page.

```
lines file / adapter ──> verbaline lines ──> lines.csv
  your mic ──> ● Record / verbaline record ──> performances/ ──> verbaline convert (Seed-VC) ──┐
  cast.toml ──> verbaline design ──> voices/<v>/ref/ ──> verbaline tts (Qwen3-TTS, ...) ──────┤
                                                                     takes/ ──> verbaline score
                                         the page (pick) ──> picks.json
                     verbaline apply ──> export/<lang>/*.wav + manifest.json ──> the project
```

## Commands

| Command | |
|---|---|
| `serve [--port P]` | the page (alias `audition`) |
| `lines` | read the project's lines into the work folder (the page runs it when a watched file changes) |
| `status [--voice V]` | per voice: reference, lines, recordings, takes, picks, prompts |
| `design [--voice V] [--n 6]` | candidate voices from the cast's description (Qwen3-TTS VoiceDesign) |
| `choose --voice V --candidate N [--emotion E]` | a candidate becomes a reference |
| `record --voice V [--group G] [--line ID] [--missing]` | act lines into the mic in a terminal |
| `convert [--voice V] [--line ID] [--ref E] [--perf NAME]` | recordings into the character (Seed-VC) |
| `train --voice V [--kind clone\|pitch] [--steps N]` | fine-tune Seed-VC on a voice |
| `tts [--voice V] [--line ID] [--takes N] [--more] [--backend B] [--regen] [--part P]` | text-to-speech takes |
| `restyle (--voice V --from CLIP \| --line ID) [--engine qwen\|editx] (--style WORDS \| --recipe EDITS)` | a new delivery, same voice |
| `restyle-keep --voice V` | judge a restyle's tries and keep the best (the page runs it after `restyle`) |
| `preview --voice V --candidate N` | a candidate's passage read by Qwen3-TTS cloning it (Hear it cloned) |
| `mirror --from CLIP --into CLIP [--line ID]` | a delivery in another voice |
| `beat --take T [--after-word W --nth N] --secs S` | a pause put into a take |
| `score [--voice V]` | check every new take |
| `refcheck` | fix reference transcripts that don't match their audio |
| `tweaks [--voice V]` | the prompts written on takes |
| `clear-takes (--group G \| --line ID \| --keys K,...) [--unpicked-lines] [--dry-run]` | move takes no pick uses (and with no prompt) to `takes/<line>/removed/`; lines with no pick only with `--unpicked-lines` |
| `promote TAKE --voice V --emotion E` | any clip becomes a reference |
| `master [--lang L]` | master the picks into `export/<lang>/` |
| `apply [--no-test]` | master, write the manifest, hand over (docs/details/project-api-details.md) |
| `run --voice V` | convert + tts + score |

Global: `--project <folder>`. `--group` filters by group (`--mission` is an alias).

## Voices

- **Design.** Qwen3-TTS VoiceDesign makes a new voice from the cast's `description` each time, reading the voice's
  `passage` (or `[project] passage`). Candidates go to `voices/<v>/design/cand_<n>.wav`. Write the description as
  who they are and how they sound (age, accent, pitch, texture, pace); write how a line is read in the line's notes.
- **References.** `choose` or the page's **Use as…** makes a candidate (or any take, via ★ Make a reference) the
  voice's reference for an emotion. The old one is kept as `ref/<emotion>_<time>.wav` with its transcript and where it
  came from (`ref/<emotion>.json`). A `refcheck` job runs after.
- **Fallback.** A line whose emotion has no reference clones its nearest: its own, neutral, calm, then its kin
  (`workfiles.ref_order`). The page says which ("no vengeful reference: auto uses neutral"); **+ make it** on an
  empty emotion restyles the neutral reference into it.
- **One voice.** References made from different candidates are different voices. The Cast tab says when a voice's
  references come from more than one; lines cloning them won't sound like one person.
- **Transcripts must match.** Qwen3-TTS reads a reference and its transcript as one recording and continues into the
  new line; a wrong transcript leaks words into every take. `refcheck` compares each transcript with Whisper and
  rewrites the ones off overall or in their first or last three words (the old one kept as `.txt.was`).

## Takes

- **Generate** makes N takes (default `[tts] takes`) with the line's engine (its own, else its voice's, else
  `[tts] backend`), cloning the reference for its emotion, reading the line's `say` if set, with pronunciations
  applied. Then a score job.
- **Length cap.** A Qwen take stops at about 8 characters a second plus 3 s, so a runaway take can't hold the queue.
- **Checks** (`verbaline score`, `[score]`): Whisper's transcript against the words (word error over `max_wer`:
  **words**), stray or wrong words in the first or last three (**ends**, caps the total at 50), ECAPA voice match to
  its reference under 0.5 (**voice?**), SQUIM audio quality under 0.7 (**rough**). A respelled word in `say` or the
  pronunciations is forgiven. The director's own recordings get no voice or rough flag.
- **Order.** The director's recordings, mirrors, restyles, beats and joined parts first; then the engines' takes
  newest first; takes with wrong words last. Three show, the rest fold. (On 113 lines a director picked, the
  top-scoring take was the pick 12% of the time, under a random pick's 18%: the highest scorers are often the
  flattest.)
- **Old words.** When a line's words change, takes of the old words show an "old words" badge and are checked against
  the new ones.
- **Prompts.** ✎ Prompt on a take: what the next takes should change. `verbaline tweaks` lists them; the next takes
  start from that take.
- **Flags.** "None good" flags the line; `verbaline tts --regen` makes new takes for flagged lines.
- **Picks in an older voice.** A pick cloned from a reference since replaced, or matching its voice under 0.5, is
  listed under the show menu's "picks in an older voice" with **⇄ Mirror it into today's voice**.

## Recording your own read

- **● Record** (or R on the selected card) records from the header's mic (raw: no echo cancelling, noise suppression
  or gain). Stop with the button or R; Esc throws it away. Saved as `performances/<line>_p<n>.wav`, trimmed, one gain
  to a -3 dB peak.
- A job converts it into the line's reference (Seed-VC) and scores it, about 30 s after you stop. Two takes
  (`[convert] kinds`):
  - **clone** (`vc_<line>_p<n>_<ref>_clone.wav`): Seed-VC's timbre model. The character's own sound and pitch range,
    your timing exactly, your intonation loosely.
  - **pitch** (`..._pitch.wav`): the pitch-following model. Your intonation note for note, moved by the pitch shift.
- **Pitch shift** (the voice's, or the line's own): it must land in the character's range,
  12 × log2(their Hz / yours). A performer speaking around 118 Hz needs about +11 to +14 for an adult woman's voice,
  0 for a man in their range. Too small sounds like the performer pitched up.
- Seed-VC's conversions warble some (PESQ about 3.1 against 3.9-4.4 for Qwen takes); no setting removes it. A tuned
  model helps (below), and ✦ Restyle's re-read is clean.
- **✕** on a recording moves it and its conversions to `removed/` folders (a picked conversion stays). **convert
  again** redoes a line's recordings into the reference now chosen.

## A voice's tuned model

**Train** (Cast tab, Voice settings; `verbaline train --voice V`) fine-tunes both Seed-VC models on the voice, then
converts its recordings again. It learns from the voice's references and its good takes (word error ≤ 0.1, score ≥
0.85, voice match ≥ 0.7, no stray end words, or picked; never a conversion, mirror or restyle). It needs a minute of
audio; three or more is better. `[train]`: steps, batch size, an optional GPU-slot script. Models live in
`voices/<v>/seedvc/<clone|pitch>/`, the previous one in `previous/`. Measured on one voice: voice match 0.74 → 0.86,
PESQ 2.93 → 3.1-3.2. Training needs OpenVoice V2's converter and Seed-VC's `se_db.pt` in Seed-VC's `checkpoints/`.

## ✂ A line in parts

No engine changes tone mid-line, and Qwen3-TTS takes its tone from the reference it clones. So a line written in
parts is made part by part, each cloning its tone's reference, and joined.

- **Markup** (directions.toml `parts`; the card's ✂ Split into tones; `verbaline/lineparts.py`):
  - `[tone]words[/]`: a part. A tone is an emotion, any case, or an everyday word for one (`ALIASES`: shout, yelling,
    whispering, tearful, shocked, furious, teasing…). `[/]` is optional: the next tone ends a part. Words outside a
    tag take the line's own emotion.
  - `[pause 0.8]` or `[beat]`: the silence between parts, voice to voice (default 0.35 s; alone 0.8 s; at most 3 s).
    Inside a part it splits it, same tone.
  - `<...>` tags (xAI's `<loud>`) go to the engine. Any other `[word]` is refused, naming the tones.
- **Words.** The engine reads the parts' words; the subtitles stay the line's words, and takes are checked against
  them. When they differ, the panel offers **Make the line's words match**.
- **Making it.** Generate makes N tries of every part, then N whole takes (try k of every part, `parts_<k>.wav`),
  scored like any take. Per part: ▶ a try alone, **use** one for the next join (else the newest), a level (-6 to +6
  dB), **↻ 2 more** of only that part (each joined with the others' choices). **Join the chosen tries** makes a take at
  once (no model). **✂ Use its parts** on a joined take makes its tries the chosen ones.
- **Joining** (`lineparts.join`): each part trimmed to its voice (40 dB under its loudest, 20 ms kept before and 60 ms
  after, faded); 0.1 s lead-in, 0.25 s tail; gaps filled with the part's own room tone, not digital silence; other
  sample rates resampled; brought down only if it would clip.
- **Where.** `takes/<line>/parts/<tone>_<id>/`, the id from the voice, tone and words, so rewording one part keeps the
  others' tries. `parts/mix.json` holds each part's chosen try and level.
- **Limits.** Each tone's reference is a voice of its own if it came from another candidate (the panel says so). A
  tone without a reference clones its fallback. One- or two-word parts give the model little to act. It stays one line
  in the game.

## ✦ Restyle and ⇄ Mirror

- **✦ Restyle: the same voice, a new delivery**, from a candidate or reference (new candidates) or a line or take (new
  takes). Presets per emotion (`models.STYLES`), followed on a line by its notes. Keeps 1-4 of 3 tries each: the voice
  is a gate (match to the source ≥ 0.5; 0.3 for a whisper or an EditX edit), then the cleanest audio (a whisper: the
  quietest).
  - **act it from words** (default): Qwen3-TTS VoiceDesign acts the words from the description and style; Seed-VC's
    pitch model puts the source's voice back on, pitched to where the emotion sits in that voice (`models.PITCH`,
    semitones over its everyday pitch: shouting +5; angry, urgent, crying +3; playful, stunned +2; warm +1; calm, sad,
    whisper -1; vengeful -2); then Qwen3-TTS Base reads it again cloning the conversion, which removes Seed-VC's warble
    and keeps the acting (**read it again cleanly**, on by default).
  - **edit the clip** (Step-Audio-EditX, when installed): edits the source itself, one edit after another
    (`emotion:coldness, style:murmur`; `x2` repeats). Edits: emotions angry, happy, sad, fear, surprised, confusion,
    empathy, embarrass, excited, depressed, admiration, coldness, disgusted, humour; styles serious, arrogant, child,
    older, girl, pure, sister, sweet, exaggerated, ethereal, whisper, generous, recite, act_coy, warm, shy, comfort,
    authority, chat, radio, soulful, gentle, story, vivid, program, news, advertising, roar, murmur, shout, deeply,
    loudly; speeds faster, slower; `remove`. Its edits drift from the voice (match 0.2-0.6).
- **⇄ Mirror: the same delivery, another voice.** From any take, candidate, reference or recording, into any reference
  or candidate (Seed-VC). **pitch**: note for note, shifted by the two voices' everyday pitches; **clone**: the
  target's own range. About 30 s. A Seed-VC conversion is marked "may warble"; ⋯ → **↻ Read it again cleanly** makes a
  clean copy.

## ⏸ A beat

A pause put into a take after each sentence, or after a chosen word, 0.3-1.2 s, as a new take `beat_<k>.wav`, scored.
Whisper's word times find the spot; the pause is the take's own room tone.

## Mastering

`verbaline master` (and Apply) writes each pick to `export/<lang>/` (`[master]`): trimmed to the words, high-passed
at 70 Hz, normalized to -18 LUFS, peaks at -1 dBFS, 48 kHz mono, named by `[master] name`.

## Other languages

Set `[project] language` and supply the translated lines (a lines file per language, or an adapter that reads the
language). Recordings only work in languages the performer speaks; Qwen3-TTS covers ten.
