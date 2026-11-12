# Configuration: details

The concept is in docs/Install.md. Three layers, later winning table by table: `verbaline/defaults.toml`, the
machine's `~/.config/verbaline/config.toml` (or `$VERBALINE_CONFIG`), the project's `verbaline.toml`. Paths
expand `~`; a project's relative paths are from its root.

Environment variables: `VERBALINE_PROJECT` (the project), `VERBALINE_WORK` (the work folder, over `work_dir`),
`VERBALINE_CONFIG` (the machine's config), `XAI_API_KEY`, `VERBALINE_EDITX_GPU` (EditX's share of GPU memory,
default 0.32).

## [project]

| Key | Default | |
|---|---|---|
| `name` | the folder's name | the page's title, the manifest's `project` |
| `work_dir` | `<project>/.verbaline` | takes, references, picks: keep it out of git |
| `language` | `en` | the export folder and `{lang}` |
| `port` | 8765 | `serve` without `--port`, and the service |
| `passage` | a pangram | what designed candidates read (a voice's own `passage` wins) |

## [lines], [files], [groups]

| Key | |
|---|---|
| `[lines] file` | a lines file (TOML, JSON, CSV) |
| `[lines] adapter` | a Python module with hooks |
| `[files] cast`, `directions`, `pronunciations` | the studio files (default `verbaline/<name>.toml`) |
| `[groups] <id> = "<title>"` | group titles, in order |

docs/details/project-api-details.md has their formats.

## [apply]

| Key | Default | |
|---|---|---|
| `label` | "Apply to game" | the page's button |
| `about` | "" | its tooltip |
| `copy_to` | | copy the exported files and `manifest.json` here |
| `prune` | false | with `copy_to`: delete `.wav` files there no longer picked |
| `command` | | run in the project root with `{manifest}` `{export_dir}` `{project}` `{work_dir}` `{language}` `{python}` |
| `words_from_manifest` | false | the game shows the manifest's words: track word changes since the last Apply |

An adapter's `apply` hook replaces `command` and `copy_to`.

## [master]

| Key | Default | |
|---|---|---|
| `name` | `{id}` | an exported file's name without `.wav`: `{id}` `{key}` `{lang}` `{group}` `{speaker}` |
| `sample_rate` | 48000 | Hz, mono |
| `loudness_lufs` | -18.0 | integrated loudness |
| `peak_dbfs` | -1.0 | the peak ceiling |
| `pad_ms` | 60 | silence kept around the trimmed words |
| `highpass_hz` | 70 | |

## [tts]

| Key | Default | |
|---|---|---|
| `backend` | `qwen` | the default engine (`qwen`, `indextts2`; a voice or line can choose another) |
| `takes` | 8 | takes per line (the page's menu offers 2, 4, 8) |

## [convert] (Seed-VC)

| Key | Default | |
|---|---|---|
| `kinds` | `["clone", "pitch"]` | the takes each recording makes |
| `cfg_rate` | 0.7 | Seed-VC's guidance |
| `diffusion_steps` | 30 | |

## [train]

| Key | Default | |
|---|---|---|
| `steps` | 600 | per model |
| `batch_size` | 4 | |
| `gpu_slot` | "" | a script run as `<script> --need <MB> <command…>` that waits for free GPU memory (EditX and training use it) |

## [score]

| Key | Default | |
|---|---|---|
| `whisper_model` | `large-v3` | faster-whisper's model |
| `max_wer` | 0.34 | word error over this: the **words** check fails |
| `weight_words`, `weight_voice`, `weight_quality` | 0.45, 0.35, 0.20 | the total's weights |

## [repos] and [envs]

| Key | |
|---|---|
| `[repos] seed_vc` | a Seed-VC checkout (default `~/AI/seed-vc`) |
| `[repos] seed_vc_python` | its Python (empty: the studio's) |
| `[repos] index_tts` | an IndexTTS2 checkout (optional) |
| `[repos] step_audio_editx`, `step_audio_models` | Step-Audio-EditX's checkout and models (optional) |
| `[envs] qwen`, `score`, `indextts2`, `editx` | the Python each runs in (empty: the studio's) |
