# The page: details

The concept is in docs/Overview.md. What each step does underneath: docs/details/workflow-details.md.

## Header

Tabs (Lines, Cast, Timeline), the Lines filters (voice, group, show, search), the mic ● Record uses, the line count,
and what the game doesn't have yet with the project's Apply button (its label and tooltip are `[apply] label` and
`about`). Show: needs a pick, everything, picked, flagged for new takes, has prompts, words not in game yet, has
old-word takes, picks in an older voice. **Generate takes for N lines needing a pick** makes more takes for every shown
line without a pick, each on its own engine (asks first when any is a cloud engine). With a group chosen, **🧹 Clear unpicked
takes** clears that group's takes no pick uses (below).

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

Generation, conversion, scoring, training, clearing takes and Apply run as jobs, one at a time, in the order started.
The page reloads its data when a job finishes. Restarting the studio kills running jobs and forgets their history.

The jobs sidebar, on the right, shows the running job (**stop**), the queue (**remove** each), finished jobs (✓ done,
✗ stopped or failed: the output says why) and the output.

- **» hides it** to a thin rail on the right edge that still shows a running job and how many are waiting; click the
  rail to open it again. Drag its left edge to make it wider. Open or hidden, and its width, are remembered in this
  browser. Under 900 px wide it opens over the page instead of beside it.
- **Links:** a line id or key in a job or its output opens that line on the Lines tab (the filters are cleared if
  they hid it, and the page says so); a voice id opens the voice on the Cast tab. Ctrl+click opens it in a new tab.
- **Clear history** forgets finished jobs and their output, once you're done with a wave of work. The running job,
  its output so far and the queue stay. It's for every open page (the studio keeps one history).

The output keeps the last 2,000 lines and the last 100 finished jobs.

## 🧹 Clear unpicked takes

With a group chosen in the Lines tab's group filter, **🧹 Clear unpicked takes** in the bar moves the takes no pick
uses in that group to each line's `takes/<line key>/removed/` folder. It asks first, saying how many takes from how
many lines, and runs as a job after any running one; the output names each line and the take it kept. What stays:

- each line's pick (read again for each line as the job runs, so a pick made meanwhile counts);
- takes with a prompt on them (✎: a near-miss you asked to have redone);
- a line's parts tries (`parts/`, which ✂ joins draw on);
- lines with no pick yet, unless you tick "Also the lines with no pick yet", which clears all their takes.

Nothing is deleted: move a file back from `removed/` to bring it back (score it again with `verbaline score`). New
takes never reuse a removed take's name. From a terminal: `verbaline clear-takes --group G [--unpicked-lines]
[--dry-run]`.

## Links

`#lines`, `#lines/<line key or id>`, `#cast`, `#cast/<voice>`, `#timeline`, `#timeline/<group>`,
`#timeline/<group>/<line key or id>`.

## API

The page talks to the server in JSON; the main routes, for tools and tests (`verbaline/server.py`):
`GET /api/state` (every card), `GET /api/cast`, `GET /api/jobs`, `GET /api/timeline`, `GET /audio?p=<work path>`,
`POST /api/pick {key, take}` (`take` a work-folder path, `takes/<key>/<name>.wav`, as `/api/state` lists it; empty or null clears the pick; anything else is refused), `POST /api/text {ids, text}`, `POST /api/job {kind, ...}` (kinds: tts, bulk, design, preview,
retry, convert, restyle, mirror, beat, score, train, apply), `POST /api/job/cancel {id}`, `GET /api/jobs?since=<seq>&gen=<gen>` (output lines after `since` as `out: [[seq, text]]`; all of them when `gen` isn't the studio's: its history was cleared), `POST /api/jobs/clear`, `POST /api/takes/clear {group, unpicked, dry}` (`dry`: what would move, as `plan`; otherwise a job). `/api/state` is a list of cards, one per recording: `key`, `ids`, `group`, `speaker`, `voice`, `text`, `emotion`,
`note`, `kind`, `context`, `takes` (each with `path`, `name`, `source`, checks), `pick` (a take's `path`), `pending`
(its words differ from the game's), `game_text` (the game's words), `pick_pending` (the pick isn't applied yet),
`parts`, and the directing fields. The server listens
on localhost only.
