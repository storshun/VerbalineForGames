# Changelog

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
