# Project API: details

The concept is in docs/HookingUpAProject.md. This is the reference: everything a project can set or provide.

## Running it

`verbaline <command>` once the package is installed (`pip install -e <studio>`); without installing,
`python <studio>/verbaline/cli.py <command>` does the same.

## Finding the project

Every command works on one project, found in this order:

1. `--project <folder>` (before the command: `verbaline --project ~/games/Ferry serve`);
2. `$VERBALINE_PROJECT`;
3. the nearest folder with a `verbaline.toml`, from the working folder upward.

The studio sets `$VERBALINE_PROJECT` for everything it starts (jobs, model environments), so they all work on the
same project.

## verbaline.toml

Settings layer in this order, later winning, table by table: the studio's `verbaline/defaults.toml`, the machine's
`~/.config/verbaline/config.toml` (or `$VERBALINE_CONFIG`), then the project's `verbaline.toml`. Model paths and
Python environments belong in the machine's file; anything about the game belongs in the project's. Every setting:
docs/details/configuration-details.md. The ones a project usually sets:

```toml
[project]
name = "Night Ferry"               # the page's title (default: the folder's name)
work_dir = "~/NightFerry_VO"       # default: <project>/.verbaline (git-ignore it)
language = "en"                    # the export folder and {lang}
port = 8765                        # `verbaline serve` without --port

[lines]
file = "dialogue/lines.toml"       # a lines file (below), and/or
adapter = "tools/verbaline_adapter.py"    # a Python module with hooks (below); relative paths are from the project root

[files]                            # the studio files (defaults shown); a missing one reads as empty and is
                                   # created the first time the page saves into it
cast = "verbaline/cast.toml"
directions = "verbaline/directions.toml"
pronunciations = "verbaline/pronunciations.toml"

[groups]                           # titles for group ids, in order (without an adapter's groups hook)
intro = "The intro"
storm = "The storm"

[master]
name = "{id}"                      # exported file name without .wav: {id} {key} {lang} {group} {speaker}

[apply]
label = "Apply to game"            # the page's button
about = ""                         # its tooltip
copy_to = "game/audio/vo"          # copy the exported files and manifest.json here, or
command = ["{python}", "tools/import_vo.py", "{manifest}"]   # run this in the project root
prune = false                      # with copy_to: delete .wav files there that are no longer picked
words_from_manifest = false        # the game shows the manifest's words, not the lines file's
```

`$VERBALINE_WORK` overrides `work_dir` (tests use it).

## A line

| Field | | Meaning |
|---|---|---|
| `id` | required | Unique, also ignoring case. Letters, digits, `_`, `.`, `-` only: it names files. Not a name Windows reserves (`con`, `prn`, `aux`, `nul`, `com1`-`9`, `lpt1`-`9`, also before a dot) and not ending in a dot. Keep it under about 60 characters for Windows' path limit. Never reuse one for different words. |
| `speaker` | required | Who says it, as the game names them. The cast's `[speakers]` maps it to a voice. |
| `text` | required | The words, as the subtitles show them. |
| `group` | | A scene, mission or chapter: the page's filter, the timeline's unit. Any string. |
| `voice` | | A voice id for a speaker the cast doesn't list. The cast's mapping wins. |
| `emotion` | | The default emotion (one of the studio's, below). Default: `urgent` when the text ends in `!`, else `neutral`. |
| `kind` | | Free text shown on the line's card (a bark, a cinematic line). |
| `context` | | Free text shown under the line's words: what's happening when it's said. |

Emotions: neutral, calm, urgent, shouting, whisper, sad, warm, playful, stunned, angry, crying, vengeful.

Lines with the same voice and the same words share one recording: one card on the page, one pick, exported under each
line's own name. The card's key is the first such line's id.

A line whose speaker has no voice is left out, and `verbaline lines` names the speaker: add it to the cast.

## A lines file

The built-in reader (`verbaline/project.py`, `FileLines`) takes any of:

- **TOML**: `[[line]]` tables, each with an `id`; or one `[<id>]` table per line.
- **JSON**: a list of lines; `{"lines": [...]}`; or `{"<id>": {...}}`.
- **CSV**: a header row naming the fields; empty cells are unset. From Excel, save as "CSV UTF-8".

Every file is UTF-8 (a byte-order mark and Windows line ends are fine); a file in another encoding is refused with
the byte where it stops.

✎ edits on the page rewrite the line's `text` in place (TOML keeps its comments and layout; JSON is rewritten with an
indent of 2; CSV keeps its columns). A line id that isn't in the file is refused.

## The adapter

A Python file named by `[lines] adapter`. Its folder is put on `sys.path`, so it can import the game's own tools. Each
hook is a module-level function; only `lines` is required, unless `[lines] file` provides the lines. A hook that's
missing falls back to the lines file's behavior or the studio's default.

| Hook | Called | Returns | Default |
|---|---|---|---|
| `lines(ctx)` | when the lines are read | an iterable of line dicts | the lines file |
| `groups(ctx)` | with the lines | `[{"id", "title", "timeline"?}]` in order | `[groups]` titles, then each group as first seen |
| `set_words(ctx, ids, text)` | ✎ edit words | nothing; raise `ValueError` to refuse | the lines file |
| `game_state(ctx)` | each page refresh | `(words, picks)`: `{line id: words}` or `None` (not tracked), `{line key: take}` | from the last Apply |
| `watch(ctx)` | each page refresh | paths whose change means the lines must be read again | the lines file |
| `apply(ctx, manifest, run)` | Apply, after export | nothing; raise or `sys.exit` to fail | `[apply] command`, else `copy_to` |
| `timeline(ctx, group, options, replay)` | the Timeline tab | a timeline dict (docs/details/timeline-details.md) | no Timeline tab |

- `ids` in `set_words` are every line sharing the recording; `text` is already whitespace-normalized.
- `game_state` runs often: keep it to reading a few files. Return `None` from it to mean "not tracked".
- `apply`'s `run(label, argv, expect=None, timeout=900, cwd=None)` runs a command in the project root, logs it to
  `<work>/logs/apply_<time>_<label>.log`, prints progress to the jobs panel, and stops Apply when the command exits
  non-zero or its output lacks `expect`. Use it for imports and checks. `ctx.no_test` is true when Apply was asked to
  skip the project's own checks (`verbaline apply --no-test`).
- `timeline`'s `group` is a group id as a string (the first group with a timeline when the page names none); `options` maps option ids to the strings the page sends back;
  `replay` is true when the director pressed the timeline's replay button.
- An exception in `timeline` is shown on the Timeline tab; one in `game_state` is logged and the page treats the
  game's words as not tracked. Neither stops the studio.

### ctx

| Member | |
|---|---|
| `ctx.project.root`, `.name`, `.cfg` | the project's folder, name and merged settings |
| `ctx.project.path(p)` | a path from the config: `~` expanded, relative to the root |
| `ctx.work`, `ctx.path(*parts)` | the work folder, and a path in it |
| `ctx.lang` | `[project] language` |
| `ctx.lines()` | the studio's line rows (after `verbaline lines`): the fields above plus `key`, `voice`, `say`, `emotion`, `note`, `parts` |
| `ctx.json(name, default)` | a JSON file in the work folder (`picks.json`: `{key: {"take": "takes/<key>/qwen_3.wav", "at": "2026-11-12 14:06"}}`) |
| `ctx.cast`, `ctx.dirs`, `ctx.say` | the studio files, parsed |
| `ctx.export_name(row)` | an exported file's name for a line row |

## The studio files

### cast.toml

```toml
[speakers]
"Ada" = "ada"                      # a speaker as the lines name it -> a voice id (same naming rules as a line id)
"Purser (radio)" = "purser"        # several speakers may share a voice

[voices.ada]
description = "A woman in her late twenties, American, quick and wry."   # voice design reads it
passage = "..."                    # what its designed candidates read (default: [project] passage)
engine = "qwen"                    # qwen (local; the default is [tts] backend), indextts2, or xai (cloud, paid)
pitch_shift = 12                   # semitones a recording's "pitch" take moves the performer's voice
xai_voice = "eve"                  # with engine = "xai": its voice and speed (0.7-1.5)
xai_speed = 1.0
notes = "..."                      # the director's notes
```

### directions.toml

```toml
[lines.storm_after]                # a line id
emotion = "sad"
note = "Shouting into the radio, then the silence lands."   # shown when recording and auditioning
voice = "keeper"                   # a different voice than the speaker's
say = "Gull, come in! ... Gull?"   # what the engine reads instead of the words (subtitles keep the words)
engine = "xai"                     # this line's engine
pitch_shift = 10                   # this line's, over the voice's
parts = "[urgent]Gull, come in![/][pause 1.2][sad]...Gull?[/]"   # a line in tones (docs/details/workflow-details.md)
```

### pronunciations.toml

```toml
[say]
"Okafor" = "oak-a-four"            # whole words, case-sensitive: the subtitle's word = what the engine reads
```

## Apply

`verbaline apply` (the page's Apply button runs it as a job):

1. Re-masters each pick the game doesn't have yet, then masters any pick without an export
   (`<work>/export/<lang>/<[master] name>.wav`: trimmed, high-passed at 70 Hz, -18 LUFS, peaks at -1 dBFS, 48 kHz
   mono; docs/details/configuration-details.md, `[master]`).
2. Writes `<work>/export/<lang>/manifest.json` (below).
3. Hands over: the adapter's `apply`, else `[apply] command`, else `[apply] copy_to`, else nothing (the export folder
   is the hand-off).
4. Records `<work>/applied.json`: the words and picks applied, which the page compares against when there is no
   `game_state` hook.

`[apply] command` is a list (or a string split on spaces) run in the project root. Placeholders: `{manifest}`,
`{export_dir}`, `{project}`, `{work_dir}`, `{language}`, `{python}` (the studio's Python).

### manifest.json

```json
{
 "project": "Night Ferry",
 "language": "en",
 "made": "2026-11-12 14:06:54",
 "lines": {
  "dock_01": {"file": "dock_01.wav", "text": "Last call for the night ferry!", "speaker": "Purser",
              "group": "dock", "voice": "purser", "key": "dock_01", "take": "takes/dock_01/qwen_3.wav",
              "seconds": 2.41}
 }
}
```

A pick that names a take which no longer exists is left out of the manifest and of `applied.json`, and Apply exits
non-zero after handing over the rest, naming it.

`file` is relative to the manifest. Only lines with a pick are listed. `take` names the studio's take (stable while
the pick stands): a game can compare it to know a line's audio changed.

## The work folder

| Path | |
|---|---|
| `lines.csv`, `groups.json` | the lines as the studio reads them (rewritten by `verbaline lines`, which the page runs whenever a watched file changes) |
| `voices/<voice>/design/cand_<n>.wav` | designed candidates (`rejected/`: deleted ones and replaced versions) |
| `voices/<voice>/ref/<emotion>.wav`, `.txt`, `.json` | references, their transcripts and where they came from (`<emotion>_<time>.*`: replaced ones) |
| `voices/<voice>/seedvc/<clone/pitch>/` | the voice's fine-tuned Seed-VC models |
| `performances/<line>_p<n>.wav` | the director's recordings |
| `takes/<line key>/<source>_<n>.wav` | takes, with `made.json` (how each was made) and `scores.json` |
| `takes/<line key>/parts/` | a line in parts: each part's tries and `mix.json` |
| `picks.json`, `tweaks.json`, `regen.json` | picks, prompts on takes, lines flagged for new takes |
| `export/<lang>/` | mastered picks and `manifest.json` |
| `applied.json`, `logs/` | the last Apply, and each Apply step's log |

Takes from anywhere (another engine, a studio session) can be dropped into `takes/<line key>/<source>_<n>.wav`;
`verbaline score` checks them and the page lists them.
