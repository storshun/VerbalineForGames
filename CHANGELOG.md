# Changelog

## 0.1.4 (2026-11-13)

The jobs sidebar, and clearing old takes.

- **The jobs sidebar**: the queue and output moved from the corner into a sidebar on the right. » hides it to a rail
  that still shows what's running; drag its edge to resize; both are remembered.
- **Links in jobs**: a line id in a job or its output opens that line on the Lines tab, a voice id opens the voice on
  the Cast tab.
- **Clear history**: forgets finished jobs and their output once a wave of work is done (the running job and the queue
  stay). The output now keeps 2,000 lines and 100 finished jobs, and the page fetches only new lines.
- **🧹 Clear unpicked takes** for a group: moves the takes no pick uses to each line's `removed/` folder
  (recoverable), keeping picks, takes with prompts and parts tries; it asks first with the counts and runs as a job.
  Lines with no pick stay unless asked. Also `verbaline clear-takes`.
- **Take numbers are never reused**: a new take was numbered by counting the line's takes, so after any take was
  taken away a new one could reuse an old name (and its checks), or overwrite another take. It now numbers past every
  take, removed ones too.
- **Releasing** is documented (docs/Releasing.md): every finished change goes out as a release, checked on Windows
  first.

## 0.1.3 (2026-11-12)

Windows, a closer look.

- **Files held open**: on Windows a file the page is reading, or that an antivirus or OneDrive has open for a moment,
  can't be replaced, so a pick, a word edit or a promoted reference could fail with "Access is denied".
  Every replace and move now waits up to about 2 seconds for the file to be let go.
- **Files from Excel and Notepad**: a lines file or studio file saved in Windows' code page stops with which file,
  which byte and how to save it as UTF-8 (Excel: "CSV UTF-8"), instead of an encoding error. Windows line ends are
  read as plain line ends; a line break inside a CSV cell is kept.
- **Names Windows can't hold**: line and voice ids such as `con`, `aux.intro` or `nul`, ids ending in a dot, and two
  ids differing only in case are refused with the reason, on every system, so a project made on Linux works on
  Windows.
- **One studio per port**: Windows let a second studio share a port, and either one might answer the page.
  The studio now asks for its port alone and, when it can't have it, says so and how to pick another (on Windows,
  how to list the ports the system reserves).
- **`[train] gpu_slot`**: a shell script can't run on Windows; training now skips it with a note instead of failing.
- **Tests**: checks for all of the above; the Windows test run also checks that Cancel stops a job's children and
  that a job in a model environment passes on its result.
- **Docs**: the install details' Windows section adds OneDrive and sync folders, long paths, reserved names, ports,
  Excel, the zip download, `py` versus `python`, and starting the studio from Task Scheduler; the troubleshooting
  table has the Windows symptoms; the project API states the id rules; development notes cover writing code that
  holds on Windows.

## 0.1.2 (2026-11-12)

- **"Use as…" on Windows**: 0.1.0 sent the page Windows paths (`voices\mai\design\cand_3.wav`), and the page's
  buttons read each backslash as an escape, so "Use as…" opened nothing (and other buttons on a candidate or take
  missed their clip). 0.1.1 sends forward slashes; a check on the Windows test run now keeps it that way.

## 0.1.1 (2026-11-12)

Windows.

- **The page loads on Windows**: every file and job output is read and written as UTF-8. Windows' code page
  (cp1252) stopped the page itself with "'charmap' codec can't decode byte 0x8f".
- **Jobs run right on Windows**: a job in a model environment reports its own result (Windows has no real exec, so
  it used to look finished at once), Cancel stops the whole job, and paths the page sees use forward slashes.
- **Files from Windows editors**: TOML, JSON and CSV with a byte-order mark read fine.
- **Clearer errors**: a config naming a Python that isn't there says so (and, on Windows, that a venv's Python is
  `Scripts/python.exe`); the xAI key message says how to set it on Windows.
- **Voice scoring on Windows** copies speechbrain's model files instead of linking them, which Windows refuses
  without Developer Mode.
- **A Windows test run** on GitHub for every push: the tests, then the quick start until the page answers.
- **Docs**: a PowerShell quick start, and a Windows section in the install details (PyTorch from pytorch.org, paths
  in TOML, what's Linux only).

## 0.1.0 (2026-11-12)

The first public release.

- **Lines, Cast and Timeline tabs**: direct each line, generate takes with Qwen3-TTS, record your own read and
  re-voice it with Seed-VC, check every take (words, voice, audio), and pick.
- **✂ Lines in parts**: `[urgent]...[/][sad]...[/]`, each part made in its own tone and joined into whole takes.
- **✦ Restyle and ⇄ Mirror**: a new delivery in the same voice, or the same delivery in another voice.
- **Hooking up a project**: `verbaline.toml` with a lines file (TOML, JSON or CSV) or a Python adapter (lines, groups,
  set_words, game_state, watch, apply, timeline hooks).
- **Apply**: masters the picks, writes `manifest.json`, and copies them into the game, runs your import command, or
  calls your hook. A pick whose take is missing fails Apply instead of being reported as delivered.
- **Timeline**: any project can feed it a documented JSON shape.
- Two example projects, a systemd service installer, and 145 checks that run without a GPU.
