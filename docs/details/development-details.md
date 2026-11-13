# Developing: details

The concept is in docs/Development.md.

## Layout

| Path | |
|---|---|
| `verbaline/cli.py` | every command; `Ctx` (one project's settings, studio files and work folder); re-running a job in its model's Python (`reexec`) |
| `verbaline/server.py` | the HTTP server, the page's JSON (`state`, `cast_state`), the job queue (`Jobs`), and turning the page's requests into commands (`Handler.job`) |
| `verbaline/page.html` | the page: HTML, CSS and JS in one file; `{{PROJECT}}` is replaced with the project's name |
| `verbaline/project.py` | finding a project, its layered settings, the hooks and their defaults, the lines file reader, the manifest |
| `verbaline/models.py` | engines, voice design, Seed-VC, Step-Audio-EditX, the scorer, emotion tables |
| `verbaline/lineparts.py` | a line in parts: markup, part ids, tries, the mix, joining |
| `verbaline/workfiles.py` | the work folder's layout and metadata (standard library only: runs in every environment) |
| `verbaline/tomledit.py` | editing the studio files in place, keeping comments (tomlkit) |
| `verbaline/runners/` | batch runners for Seed-VC and Step-Audio-EditX, run in their own Pythons |
| `verbaline/defaults.toml` | every setting's default |
| `scripts/` | `install_service.sh`, `install_editx.sh` |
| `.github/workflows/` | `windows.yml`: the tests and the quick start on Windows |
| `examples/` | `minimal` (a lines file, Apply copying) and `adapter` (every hook, a timeline) |
| `tests/test_verbaline.py` | the checks |

## How a page action runs

1. The page `POST`s `/api/job {kind, ...}`. `Handler.job` checks it (refusing what it should: paths outside the work
   folder, unknown edits, out-of-range values) and turns it into steps: `verbaline` argument lists.
2. `Jobs` runs them one at a time in the project root, as `python cli.py <step>` with `$VERBALINE_PROJECT` set; each
   step that needs a model re-execs itself in `[envs]`'s Python.
3. The jobs panel polls `/api/jobs`; when a job finishes the page reloads `/api/state` and `/api/cast`.
4. `/api/state` re-reads the lines (`verbaline lines`) when the project's watched files are newer than `lines.csv`.

Small edits (pick, notes, emotion, words, cast fields) are direct `POST`s that write the files at once.

## Tests

`python tests/test_verbaline.py` (the studio's Python; no GPU, no models, about 10 s). It builds a temporary project and
work folder, and checks: the emotion and engine tables agree; restyle presets are real EditX edits; clip names; every
job kind's steps and refusals; reference fallback; take order and checks; register shifts and restyle keeping; parts
markup, part ids, joining (gaps, levels, room tone, resampling) and generation with a stand-in engine; lines files in
TOML, JSON and CSV with edits written back; config layering; line validation; Apply with `copy_to` and `command`; the
manifest; word tracking; the adapter example's hooks and timeline; every text file and pipe naming its encoding. Add
a check with every behavior change.

On GitHub, `.github/workflows/windows.yml` runs them on Windows for every push and pull request, then follows the
README's Windows quick start (its config line in Windows PowerShell, `verbaline lines`, `serve`) until the page and
`/api/state` answer. It has no GPU, so the models aren't in it. To check Windows text handling on Linux, run the
tests with `PYTHONUTF8=0 LC_ALL=en_US.CP1252` (a locale the system lacks falls back to ASCII, which is stricter than
cp1252).

## Changing the project API

The line schema, the hooks, `verbaline.toml`, the manifest and the timeline shape are a contract with every project
using the studio. Prefer adding an optional field or hook to changing one. A change updates
docs/details/project-api-details.md (or timeline-details.md), the examples, and the tests, in the same commit, and a
breaking change says so in the commit message.

## Changing the page

No build step: edit `page.html`. Check its script parses (`node --check` on the extracted script), then load it on an
example project. Headless Chromium can screenshot it after scripts run:
`chrome-headless-shell --window-size=1300,1300 --virtual-time-budget=4000 --screenshot=out.png http://localhost:8765/#timeline/dock`.
Page text names no game; project-specific words come from the project (`C.apply_label`, `C.files`, group titles, the
timeline's labels).

## Style

American English. Code comments say why, with measurements where a choice was measured. Settings that shape behavior
go in `defaults.toml` with a comment, never as hidden constants or environment-only switches.
