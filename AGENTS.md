# Verbaline For Games

A local web page for directing, voicing and picking every line of a game's dialogue with open models, and handing the
picks to the game. A project hooks up through a `verbaline.toml`; the studio itself knows no game.

## This file

- It holds only pillar rules. Everything else lives in one document per concept: docs/<Concept>.md says what a thing
  is and how it should behave, and docs/details/<concept>-details.md holds its specs, schemas, commands and procedures.
  Read a document when the task touches its concept, not before.
- When you learn or change something, update the document that owns that concept. Add a line here only for a new
  pillar rule or a new concept.
- Refer to documents by plain path. Never put @ in front of a path: that loads the file into every session.

## Pillars

- **The director decides.** The studio makes takes and checks them; a person picks. Never pick, delete or overwrite
  a pick, a take or a reference on their behalf, and never rank takes by score as if the score were taste.
- **No game in the core.** Nothing in `verbaline/` names a game, an engine or a project's files. Anything a project
  needs goes through its `verbaline.toml` or its adapter's hooks (docs/HookingUpAProject.md).
- **Local by default.** Lines and voices stay on the machine unless the director sets a voice to a cloud engine, and
  the page asks before that happens.
- **Consent.** Never use a person's voice as a reference, or ship a voice made from one, without their written
  consent.
- **The page, the files and the command line agree.** The page edits the project's studio files in place, keeping
  their comments; anything the page does, a command does too.

## Rules

- Never write into a project's work folder from tests: tests run on a temporary project and `$VERBALINE_WORK`.
- Restart a running studio only when its jobs panel shows nothing running or queued: a restart kills the jobs.
- A change to the line schema, a hook, the manifest or the timeline shape updates docs/details/project-api-details.md
  or docs/details/timeline-details.md in the same commit, with a check in tests/test_verbaline.py.
- American English everywhere: code, page text, docs.
- `python tests/test_verbaline.py` passes before every commit.
- Every finished change is published as a release (version, CHANGELOG.md entry, tag, release files) in the same
  session, after the Windows run passes. Nothing finished stays unpublished.

## Where everything else is

Additional information on what the studio is and what its page does can be found in docs/Overview.md.
Additional information on hooking a project up (its config, lines, adapter hooks and Apply) can be found in docs/HookingUpAProject.md. Read it before changing anything a project touches.
Additional information on the Timeline tab and the shape a project's timeline hook returns can be found in docs/Timeline.md.
Additional information on directing and voicing a line (cast, references, takes, recording, parts, restyle, mirror, picking) can be found in docs/Workflow.md.
Additional information on the speech engines, their models and licenses can be found in docs/Engines.md. Read it before adding or changing an engine.
Additional information on installing the studio and its configuration can be found in docs/Install.md.
Additional information on the code's layout and how to test it can be found in docs/Development.md. Read it before changing the code.
Additional information on releasing (numbering, the change log, the checks, the release files) can be found in docs/Releasing.md. Read it before publishing.
