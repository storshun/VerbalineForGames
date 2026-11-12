# The page: details

The concept is in docs/Overview.md. What each step does underneath: docs/details/workflow-details.md.

## Header

Tabs (Lines, Cast, Timeline), the Lines filters (voice, group, show, search), the mic ● Record uses, the line count,
and what the game doesn't have yet with the project's Apply button (its label and tooltip are `[apply] label` and
`about`). Show: needs a pick, everything, picked, flagged for new takes, has prompts, words not in game yet, has
old-word takes, picks in an older voice. **Generate takes for N lines needing a pick** makes more takes for every shown
line without a pick, each on its own engine (asks first when any is a cloud engine).

## Lines tab

One card per recording (lines with the same voice and words share one).

- **Head:** speaker, emotion, voice and engine (opens the voice on the Cast tab), the line ids, ⏱ when it plays (when
  its group has a timeline), picked, prompts, flagged.
- **Words:** ✎ edit words rewrites them where the project keeps them (the lines file or the adapter's `set_words`),
  for every line sharing the recording. Never respell a word here: it reaches the subtitles. Use **say it as** or
  Pronunciations.
- **Direct it:** voice (any cast voice), emotion, directing notes, **say it as** (what the engine reads, this line
  only; subtitles keep the words), reference (auto or a chosen emotion), engine (saved with the line), takes per
  generation, Generate, ✦ Restyle, ✂ Split into tones.
- **● Record** and the line's pitch shift; its recordings, with ✕ and convert again.
- **Parts panel** (a line in parts): per part its tone, words, what it clones, its tries, use, level and ↻ 2 more;
  the gaps between; Join the chosen tries.
- **Takes:** ▶, its name and source, its checks chip (hover for the numbers), what Whisper heard, Pick, and ⋯:
  ✎ Prompt, ✦ Restyle, ⇄ Mirror, ⏸ Add a beat, ★ Make a reference, ✂ Use its parts (joined takes). **none good**
  flags the line.

Keys (the selected card): j/k or ↓/↑ move, 1-3 pick, Space plays the first take, R records (R again stops, Esc throws
it away), Ctrl+Enter saves a prompt or words, Esc cancels.

## Cast tab

One voice at a time: the list on the left (most lines first, picked/lines, one marker: working…, N new, no reference),
then Speakers → voices, Pronunciations, Add cast member; the voice on the right. `[` and `]` step through voices.

- **Description**, editable in place.
- **References:** a tile per emotion in a fixed order (everyday: neutral, calm, warm, playful; heat: urgent, shouting,
  angry, vengeful; hurt and hush: whisper, sad, crying, stunned). A tile plays the reference, says where it came from
  and how many lines use it; on hover ✦ restyle, ⇄ mirror, ✕ remove (kept in `ref/removed/`). An empty tile says what
  it falls back to and offers **+ make it**.
- **Candidates**, newest first, filtered (all, in use, restyled, mirrored, designed), with **Design new** and the text
  new designs read. A row: ▶, number, how it was made, the references it is, its words, `new`. **Use as…** (says what
  it replaces; nothing happens until confirmed) and ⋯: ✦ Restyle, ⇄ Mirror, Hear it cloned, ↻ Read new words (a new
  candidate in its voice), Give to another voice, ↻ Read it again cleanly (Seed-VC ones), Delete (kept in
  `design/rejected/`). Keys: j/k move, Space plays, u Use as…, Esc closes a form.
- **Voice settings:** engine (switching to a cloud engine asks first), notes, pitch shift, xAI voice and speed, its
  recordings' models and **Train**, Generate takes for its lines without any, score.
- **Pronunciations:** the subtitle's word and what the engine reads, for every line.

## Timeline tab

docs/details/timeline-details.md. Esc stops ▶ from here or cancels a ✎ edit.

## Jobs

Generation, conversion, scoring, training and Apply run as jobs, one at a time, in the order started. The corner panel
shows the running job, the queue (each cancellable) and the log. The page reloads its data when a job finishes.
Restarting the studio kills running jobs.

## Links

`#lines`, `#lines/<line key or id>`, `#cast`, `#cast/<voice>`, `#timeline`, `#timeline/<group>`,
`#timeline/<group>/<line key or id>`.

## API

The page talks to the server in JSON; the main routes, for tools and tests (`verbaline/server.py`):
`GET /api/state` (every card), `GET /api/cast`, `GET /api/jobs`, `GET /api/timeline`, `GET /audio?p=<work path>`,
`POST /api/pick {key, take}` (`take` a work-folder path, `takes/<key>/<name>.wav`, as `/api/state` lists it; empty or null clears the pick; anything else is refused), `POST /api/text {ids, text}`, `POST /api/job {kind, ...}` (kinds: tts, bulk, design, preview,
retry, convert, restyle, mirror, beat, score, train, apply), `POST /api/job/cancel {id}`. `/api/state` is a list of cards, one per recording: `key`, `ids`, `group`, `speaker`, `voice`, `text`, `emotion`,
`note`, `kind`, `context`, `takes` (each with `path`, `name`, `source`, checks), `pick` (a take's `path`), `pending`
(its words differ from the game's), `game_text` (the game's words), `pick_pending` (the pick isn't applied yet),
`parts`, and the directing fields. The server listens
on localhost only.
