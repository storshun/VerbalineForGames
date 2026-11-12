# The Timeline tab

## What it is

Lines read on cards lose their context: who spoke just before, what the player is doing, how long the quiet is. The
Timeline tab puts one group's lines (a scene, a mission) on the player's clock, as the game would play them, with
whatever else the project wants beside them: on-screen prompts, choices, combat, music cues.

The studio can't know when a game plays a line, so the project tells it: its adapter's `timeline` hook returns the
group laid out in time. That can be as simple as adding up a scripted scene's pauses and line lengths, or as rich as
a headless playthrough of the game. The page draws whatever comes back in one shape.

## Expected experience

- A strip across the top shows the whole group at a glance, one color per speaker, with the project's events marked
  and an optional track (intensity, enemies on screen, music level) drawn under them. Clicking it jumps the list.
- The list below shows lines in the order the player hears them, boxed into exchanges, each with its speaker,
  emotion, words, length (estimated from the words until it's voiced), its pick, what sets it off, and the project's
  flags (too tight, never heard, talking over action) with their reasons on hover.
- Events sit between the lines at their moments. Long quiet stretches show their length.
- ✎ rewrites a line's words in its moment. **▶ from here** plays the scene from that line with the picked takes at
  their moments, long quiet stretches shortened.
- The project's options (a fast or slow player, a difficulty, a branch) and filters sit in the header.
- Every line card on the Lines tab whose group has a timeline links to its moment (⏱ when it plays).

## Expected outcome

A director can hear a conversation as the player will, fix a line that lands on top of another, and write lines that
answer each other, without launching the game.

## Where the details are

Detailed instruction and information on the timeline hook's arguments, the JSON shape it returns, and how each field
is drawn can be found in docs/details/timeline-details.md.
