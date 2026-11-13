# Overview

## What it is

Verbaline For Games is a page a director keeps open while voicing a game. It runs on their own machine
(`verbaline serve`, http://localhost:8765 by default) for one project at a time, and it does three things:

- **Makes takes.** Text-to-speech cloning a voice's reference clips, the director's own recorded read re-voiced as
  the character, restyles and mirrors of existing clips. Every take is checked: the words it actually says, whether
  it's still the voice, and whether the audio is clean.
- **Keeps the direction.** Who each speaker is, how each line should be played, how a word is pronounced, which
  take is the pick. All of it lives in three small TOML files in the project (cast, directions, pronunciations) that
  people, the page and agents edit alike.
- **Hands the picks over.** Apply masters every pick (trimmed, leveled, one sample rate), writes a manifest, and gives
  both to the project in the way it asked for.

The studio never decides what's good. It sorts takes so the newest and the ones made on purpose come first, flags
the broken ones, and leaves the choice to the director.

## Expected experience

1. A project adds a `verbaline.toml` naming its lines (docs/HookingUpAProject.md).
2. The director opens the page. Every line is a card, filtered by voice, group (a scene, a mission, a chapter) and
   what still needs doing.
3. On the Cast tab they design each character's voice from a description and choose its reference clips: a neutral
   one, then one per emotion as they find them.
4. On the Lines tab they direct lines, generate takes or record their own reads, listen, and pick. Jobs queue in the
   sidebar and run one at a time; the page updates as they finish.
5. With a timeline, they check a scene in context: when each line lands, what's around it, and the scene played back.
6. They press Apply. The game has the picks.

The header always says what the game doesn't have yet: words edited since the last Apply (when the project tracks
them) and picks not applied.

## Where the details are

Detailed instruction and information on the page itself (each tab, each control, keys and links) can be found in
docs/details/page-details.md.
