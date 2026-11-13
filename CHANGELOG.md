# Changelog

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
