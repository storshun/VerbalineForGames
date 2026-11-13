# Installing: details

The concept is in docs/Install.md. Tested on Fedora with an RTX 5090 (32 GB), PyTorch 2.8.0+cu128 and Python 3.11.
Windows 10 and 11 are supported from 0.1.1 (the section "Windows" below); macOS is untested and has no CUDA.

## What you need

- Linux or Windows, Python 3.11, git.
- An NVIDIA GPU: Qwen3-TTS needs about 6 GB, Whisper large-v3 about 4 GB, Seed-VC about 4 GB, Step-Audio-EditX about
  13 GB. 16 GB runs everything but EditX; jobs run one at a time.
- PortAudio for recording on Linux (`sudo dnf install portaudio` / `sudo apt install libportaudio2`); on Windows
  it comes with the `sounddevice` package.
- About 20 GB for the models (downloaded on first use into the Hugging Face cache), more for EditX.

## The environments

Install PyTorch for your CUDA driver first in each (https://pytorch.org/get-started/locally/), then:

| Environment | Holds | Install | Config |
|---|---|---|---|
| the studio's | the page, lines, record, master, apply, scoring | `pip install -e '<studio>[record,score]'` | run `verbaline` with it |
| Qwen | Qwen3-TTS takes, VoiceDesign, restyle | `pip install -e <studio> qwen-tts` | `[envs] qwen` |
| Seed-VC | conversion, mirror, training | `git clone https://github.com/Plachtaa/seed-vc`, then its `requirements.txt` | `[repos] seed_vc`, `[repos] seed_vc_python` |
| Step-Audio-EditX (optional, Linux only: it runs on vLLM) | ✦ Restyle "edit the clip" | `scripts/install_editx.sh` | `[repos] step_audio_editx`, `step_audio_models`, `[envs] editx` |
| IndexTTS2 (optional) | IndexTTS2 takes | its own repo's instructions | `[repos] index_tts`, `[envs] indextts2` |

If one environment can hold everything without conflicts on your machine, leave `[envs]` empty.

The machine's config, `~/.config/verbaline/config.toml` (or `$VERBALINE_CONFIG`):

```toml
[repos]
seed_vc = "~/AI/seed-vc"
seed_vc_python = "~/venvs/seedvc/bin/python"

[envs]
qwen = "~/venvs/qwen/bin/python"
```

## Checking it

```bash
verbaline --project examples/minimal lines     # 4 lines (4 distinct recordings) for 2 voices
verbaline --project examples/minimal design --voice keeper --n 2   # Qwen3-TTS VoiceDesign: two candidates
verbaline --project examples/minimal serve     # http://localhost:8765
python tests/test_verbaline.py                      # no models, no GPU: every check passes
```

The example's work folder is `examples/minimal/.verbaline/` (git-ignored); delete it to start over.

## A service

On Linux, `scripts/install_service.sh` writes a systemd user unit for one project, restarts it and checks the page answers:

```bash
scripts/install_service.sh --project ~/games/NightFerry --name nightferry-voice --port 8766 \
    --python ~/venvs/verbaline/bin/python [--env ~/.config/verbaline/env]
systemctl --user status nightferry-voice
journalctl --user -u nightferry-voice -f
```

- `--port` defaults to the project's `[project] port`. An old unit of the same name is kept beside the new one as
  `<name>.service.bak-<time>`.
- The env file (optional) holds secrets, one `KEY=value` per line: `XAI_API_KEY` for the xAI engine.
- Restart the service after updating the studio, but only when the jobs panel shows nothing running or queued: a
  restart kills the jobs.
- The page listens on 127.0.0.1 only. To reach it from another machine, use an SSH tunnel
  (`ssh -L 8765:localhost:8765 host`); it has no authentication of its own.

## Windows

The quick start in README.md has the PowerShell commands. What differs from Linux:

- **PyTorch:** PyPI's Windows wheels are CPU only. Install `torch` and `torchaudio` from pytorch.org's index into
  each environment before anything else, or every model job fails with "Torch not compiled with CUDA enabled".
- **Paths:** a venv's Python is `Scripts/python.exe`, not `bin/python`, so the machine's config reads
  `qwen = "~/venvs/qwen/Scripts/python.exe"`. `~` is your user folder, and the config lives in
  `%USERPROFILE%\.config\verbaline\config.toml`. In TOML, write paths with forward slashes or in single quotes.
- **Text:** the studio reads and writes every file as UTF-8 and starts its jobs in Python's UTF-8 mode, whatever
  the system's code page. Files saved by Notepad or PowerShell (with or without a byte-order mark) are fine. Don't
  write the config with PowerShell 5's `>>`: it writes UTF-16, which TOML can't read. Use `Add-Content -Encoding utf8`
  or an editor.
- **Seed-VC:** its README covers Windows (it suggests Python 3.10 there, and `triton-windows` is optional). Set
  `seed_vc_python` to that environment's `Scripts/python.exe`. Training already uses no extra data workers.
- **Not on Windows:** Step-Audio-EditX (vLLM is Linux only; WSL2 can run it, but the studio would need to run there
  too) and `scripts/install_service.sh` (systemd). Run `verbaline serve` in a terminal instead, or add it to Task
  Scheduler "At log on".
- **Model downloads:** Hugging Face and speechbrain copy files where Linux would link them, unless Windows'
  Developer Mode is on. It works either way and uses a little more disk.
- **xAI key:** `setx XAI_API_KEY <key>`, then start the studio from a new terminal.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "No lines yet: run `verbaline lines` first" | the page wasn't started, or the lines failed: run it and read the message |
| a speaker's lines are missing | the cast's `[speakers]` doesn't map that speaker (`verbaline lines` names it) |
| an engine isn't offered | its checkout or environment is missing; the Cast tab's engine menu or `models.editx_missing` says which |
| takes start with stray words | a reference's transcript doesn't match its audio: `verbaline refcheck` |
| converted takes warble | Seed-VC's nature: train the voice's model, or ✦ Restyle with "read it again cleanly" |
| a job fails with "Torch not compiled with CUDA enabled" | PyTorch came from PyPI (Windows): install it from pytorch.org's index into that environment |
| "[envs] ... is not a file" | the config names a Python that isn't there (on Windows: `Scripts/python.exe`) |
| Whisper scoring can't load `cudnn_ops64_9.dll` or `cublas64_12.dll` (Windows) | its CTranslate2 needs CUDA 12 and cuDNN 9 libraries: faster-whisper's README lists where to get them |
| a job waits | another job is running (one at a time), or `[train] gpu_slot` is waiting for GPU memory |
