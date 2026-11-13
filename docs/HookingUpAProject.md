# Hooking up a project

## What it is

A project is any folder with a `verbaline.toml` at its root: usually a game's repository. The file tells the studio
three things, and everything else (voices, references, takes, scores, picks) the studio keeps for itself:

1. **Where the lines are.** Every spoken line: an id, who says it, and its words. Optionally a group (a scene, a
   mission, a chapter), an emotion, and context for the director. Ids name files, so they follow the strictest
   system's rules (Windows): the studio checks them on every machine.
2. **Where the direction lives.** Three TOML files the page edits: the cast (speakers to voices, and how each voice
   sounds), the directions (how each line is played), and pronunciations.
3. **How the picks reach the game.** What Apply does after it has mastered the picks and written a manifest.

The studio's work folder (big WAV files) lives outside the repo or in a git-ignored `.verbaline/` folder. The three
studio files are small and belong in the repo, so the direction travels with the game.

## Two ways in

**A lines file.** The simplest: the project keeps its lines in a TOML, JSON or CSV file the studio reads, and ✎ edits
on the page are written back into it. Apply copies the mastered files and `manifest.json` into a folder of the game,
or runs the project's own import command with the manifest's path. No Python needed. examples/minimal is one.

**An adapter.** When the lines already live in the game's own format (a dialogue graph, scene scripts, a database),
a small Python module turns them into the studio's line list, and can also write word edits back, report what the
game currently has, do the import on Apply, and provide a timeline. Each hook is optional except the lines.
examples/adapter is one.

Both can mix: a lines file with an adapter that only adds `apply` or `timeline`.

## What the game gets

After Apply, the game has one mastered WAV per picked line (named by a pattern the project chooses), and a
`manifest.json` listing each line's file, words, speaker, group, voice, take and length. A game can read the
manifest directly, or the project's apply step can turn it into whatever the engine wants (its own audio format,
import settings, a voice table, lip sync).

## What the page shows about the game

The header says what the game doesn't have yet:

- **Picks not applied:** always tracked, from the last Apply.
- **Words changed since:** only when the game keeps its own copy of the words: an adapter's `game_state` hook reads
  them from the game's files, or `[apply] words_from_manifest` says the game takes them from the manifest. A game that
  reads the same lines file the studio edits always has the current words.

## Expected outcome

A team new to the studio can hook up a project in under an hour from this document and its reference: write the
config, point it at their lines, cast two voices, generate and pick a take, Apply, and hear it in their game.

## Where the details are

Detailed instruction and information on the config file, the line schema, every adapter hook and its arguments, the
studio files' formats, the manifest and the work folder can be found in docs/details/project-api-details.md.
Detailed instruction and information on the timeline hook's output can be found in docs/details/timeline-details.md.
