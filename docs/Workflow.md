# Directing and voicing

## What it is

How a line goes from words to a picked take. The studio's ideas:

- **A voice is its references.** Each character has reference clips, one per emotion where it has one (neutral,
  calm, urgent, shouting, whisper, sad, warm, playful, stunned, angry, crying, vengeful). Text-to-speech clones the
  reference for the line's emotion, so a line's tone comes from which clip it clones. A voice starts as a description;
  designed candidates are auditioned, and one becomes the neutral reference.
- **Act what matters yourself.** The director records a read; Seed-VC re-voices it as the character, keeping their
  timing and acting. Two takes per recording: one in the character's own range, one following the read note for note.
- **Many takes, a person picks.** Each generation makes several takes. Each take is checked (the words it says, its
  match to the voice, how clean it is) and shows ✓ or what's wrong; the order is newest and made-on-purpose first,
  never by score.
- **Direct in words.** Notes on a line reach the models through ✦ Restyle; prompts on a take you like say what the
  next ones should change.
- **A line in parts.** A line can be written in tones, `[urgent]...[/][sad]...[/]`: each part is made in its own
  tone and the parts are joined, so a line can turn mid-sentence.
- **Reuse a delivery.** ⇄ Mirror moves a delivery you like onto another voice; ✦ Restyle gives a voice a new
  delivery.

## Expected experience

1. Cast: describe each voice, design candidates, use the best as its neutral reference, make or find its emotions.
2. Direct: on each line, its emotion, notes, and anything the engine should read differently.
3. Generate takes, or record. Listen, pick (keys 1-3), or write a prompt on a near-miss, or flag none good.
4. Fix near-misses in place: a beat added after a word, a restyle, a mirror into the right voice, one part redone.
5. Apply.

A session is mostly listening. Jobs queue and run one at a time in the background, so the director keeps picking
while the next takes are made. When a group is done, its unpicked takes can be cleared away (recoverably), and the
jobs' history cleared for the next wave.

## Where the details are

Detailed instruction and information on every step (designing voices, references and their fallbacks, generating,
recording, checks, parts markup and joining, restyle and mirror, beats, tuned models, mastering) and every command can
be found in docs/details/workflow-details.md.
Detailed instruction and information on the page's controls and keys can be found in docs/details/page-details.md.
