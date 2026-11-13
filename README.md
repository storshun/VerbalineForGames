# Verbaline For Games

A local web page for voicing a game's dialogue with open models: cast the voices, direct each line, generate takes or
act them yourself, pick the ones you want, and hand the picks to your game.

- **Lines tab:** one card per line. Direct it (voice, emotion, notes, how a word is said), generate takes, record
  your own read and have it re-voiced as the character, split a line into parts with a tone each, and pick.
- **Cast tab:** one card per character. Design voices from a description, choose reference clips per emotion, restyle
  a voice into a new delivery, mirror a delivery into another voice.
- **Timeline tab** (when your project provides one): each scene's lines on the player's clock, with what's happening
  around them, and the scene played back from the picked takes.
- **Apply:** masters the picks, writes a manifest, and hands them to your project: copied into a folder, passed to
  your import command, or through your own Python hook.

The Python package and command are both `verbaline`, and a project hooks up with a `verbaline.toml`.

Everything runs on your machine (Qwen3-TTS, Seed-VC, Whisper and friends) unless you set a voice to a cloud engine.
An NVIDIA GPU with 16 GB or more is recommended.

## Quick start

Linux:

```bash
git clone https://github.com/storshun/VerbalineForGames.git && cd VerbalineForGames
# The studio, recording and scoring (install PyTorch with CUDA for your driver first: pytorch.org)
python3.11 -m venv ~/venvs/verbaline && ~/venvs/verbaline/bin/pip install -e '.[record,score]'
# Qwen3-TTS in its own environment (it pins its own transformers)
python3.11 -m venv ~/venvs/qwen && ~/venvs/qwen/bin/pip install -e . qwen-tts
mkdir -p ~/.config/verbaline && printf '[envs]\nqwen = "~/venvs/qwen/bin/python"\n' >> ~/.config/verbaline/config.toml
~/venvs/verbaline/bin/verbaline --project examples/minimal serve
# open http://localhost:8765
```

Windows (PowerShell, with Python 3.11 from python.org and git). PyPI's PyTorch for Windows has no CUDA, so each
environment gets PyTorch from pytorch.org first; `cu128` suits a current driver (pytorch.org lists the others):

```powershell
git clone https://github.com/storshun/VerbalineForGames.git; cd VerbalineForGames
py -3.11 -m venv "$HOME\venvs\verbaline"
& "$HOME\venvs\verbaline\Scripts\pip" install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
& "$HOME\venvs\verbaline\Scripts\pip" install -e ".[record,score]"
py -3.11 -m venv "$HOME\venvs\qwen"
& "$HOME\venvs\qwen\Scripts\pip" install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
& "$HOME\venvs\qwen\Scripts\pip" install -e . qwen-tts
New-Item -ItemType Directory -Force "$HOME\.config\verbaline" | Out-Null
Add-Content -Encoding utf8 "$HOME\.config\verbaline\config.toml" "[envs]`nqwen = `"~/venvs/qwen/Scripts/python.exe`""
& "$HOME\venvs\verbaline\Scripts\verbaline" --project examples/minimal serve
# open http://localhost:8765
```

docs/Install.md covers Seed-VC (re-voicing your own reads), the optional engines, and running it as a service.

Then hook up your own project: add a `verbaline.toml` and a lines file (or a small Python adapter) to it, and run
`verbaline --project <your game> serve`.

## Documentation

- docs/Overview.md: what the studio is and how a session goes.
- docs/HookingUpAProject.md: connecting your game: the config, your lines, Apply, and an adapter.
- docs/Workflow.md: directing and voicing lines.
- docs/Timeline.md: the Timeline tab, and how a project feeds it.
- docs/Engines.md: the speech engines, their models and licenses.
- docs/Install.md: installing, the model environments, and running it as a service.
- docs/Development.md: the code and its tests.
- examples/minimal: a lines file and Apply copying into a folder. examples/adapter: a Python adapter with a timeline.

## Changes

CHANGELOG.md.

## License

Apache-2.0 (LICENSE). The models it runs have their own licenses: docs/Engines.md. Use a person's voice only with
their written consent.
