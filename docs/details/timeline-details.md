# The timeline: details

The concept is in docs/Timeline.md. This is the reference for the adapter's `timeline` hook and what the page does with
its output. examples/adapter/verbaline_adapter.py is a working one.

## The hook

```python
def timeline(ctx, group, options, replay=False) -> dict
```

- `group`: the group id (a string) the page asks for. Every group from `groups()` has a timeline unless it says
  `"timeline": false`.
- `options`: `{option id: value}` as strings, from the page's option menus (empty on first load: use defaults).
- `replay`: true when the director pressed the replay button (`replay` below): redo any cached simulation.
- Called on the server's thread for each request: cache anything slow (a playthrough) in `ctx.path('timeline', ...)`
  and redo it only when its inputs change.
- Raise to show an error on the tab.

The page asks `GET /api/timeline?group=<id>&opt.<id>=<value>&replay=0|1`.

## The shape

All times are seconds on the player's clock from the group's start. Everything but `lines` is optional.

```json
{
 "group": "dock",
 "title": "Scene 1: The dock",
 "summary": "4 lines, 23 s at pace x2.",
 "notes": ["Line timings are from the last export."],
 "options": [{"id": "pace", "label": "pace", "about": "How long the player lingers", "value": "2",
              "choices": [{"id": "1", "label": "an average reader", "about": "..."}]}],
 "filters": [{"id": "choices", "label": "choices", "about": "The player's choices on screen"}],
 "replay": {"label": "↻ Play again", "about": "Plays the scene again (about 2 s)"},
 "minor_label": "barks", "minor_about": "Lines the game may drop when the channel is busy",
 "speaker_colors": {"Ada": "#5cc8ff"},
 "lines": [{"id": "dock_02", "speaker": "Ada", "words": "One, to the island.", "start": 6.46, "end": 9.92,
            "est": true, "arrive": 6.0, "minor": false, "ex": "dock-1", "cause": "after Purser + 1.5 s",
            "context": ["2 enemies on screen"], "flags": [{"label": "tight", "why": "0.2 s after the line before"}]}],
 "events": [{"kind": "horn", "t": 12.9, "t1": 14.0, "text": "The ferry's horn sounds twice", "detail": "audio cue",
             "label": "sound", "color": "#9fb4ff", "flags": []}],
 "kinds": {"horn": {"label": "sound", "plural": "sounds", "color": "#9fb4ff", "strip": "mark", "filter": "choices",
                    "merge": 15, "about": "..."}},
 "track": {"label": "enemies", "about": "Armed enemies on screen (height), alarm (tint)", "color": "#5a2a2a",
           "highlight": "#ff6b6b", "points": [[0, 0, false], [30, 4, true]]},
 "end": {"t": 61.2, "label": "end", "text": "Won", "flags": []},
 "unheard_label": "Not heard in this run",
 "unheard": [{"id": "dock_09", "speaker": "Purser", "waits": "the player refusing", "pending": false}]
}
```

### lines

| Field | | Drawn as |
|---|---|---|
| `id` | required | the line id: matched to the studio's card (its words, emotion, pick, notes, ✎ and Lines ↗) |
| `speaker` | required | name and color (`speaker_colors`, else a color from the name; a trailing `(radio)` is ignored for color) |
| `start`, `end` | | its moment and length; `start: null` means never heard in this run (a red tick on the strip) |
| `words` | | shown when the line isn't one of the studio's |
| `est` | | its length is an estimate (hatched on the strip, `~` before its length) |
| `arrive` | | when it was ready to play: `start - arrive` over 1 s shows as "waited N s" |
| `at` | | where a never-heard line sits (default `arrive`) |
| `minor` | | dimmed, hidden by the `minor_label` checkbox |
| `ex` | | an exchange id: consecutive lines sharing one are boxed, headed "A → B → A · 3 lines" |
| `cause` | | "⟵ cause": what sets it off |
| `context` | | short strings under it (what's happening) |
| `flags` | | chips: `label`, with `why` on hover |

Lines are listed by `start` (never-heard ones at `at`); ▶ from here plays the shown lines in `start` order, each
picked take at its moment, gaps over 3 s cut to 3 s, a line with no pick silent for its length.

### events, kinds, filters

An event is drawn as a row between the lines at `t`: a chip with its kind's `label` (or the event's own `label`) in
its kind's `color`, then `text`, then `detail` dimmed, then its flags. On the strip, by its kind's `strip`:

| `strip` | |
|---|---|
| `mark` | a short mark in the middle row |
| `span` | a bar from `t` to `t1` |
| `tick` | a small tick at the bottom (one per merged event) |
| `tall` | a tall tick at the bottom (losses, deaths) |
| `none` or unset | not on the strip, and not in the legend |

A kind with `merge: N` joins consecutive events of that kind less than N seconds apart into one row ("a, b, c"),
labeled `plural` when there is more than one. A kind with `filter: <id>` is hidden when that filter's checkbox is off;
`filters` lists the checkboxes in order.

### track

`points` are `[t, value, highlight]`, drawn as a filled area along the strip's bottom, scaled to its largest value;
stretches where `highlight` is true are tinted with `highlight`.

### options and replay

Each option is a menu in the header; choosing sends `opt.<id>=<choice id>` and redraws. Return each option's current
`value` so the menu shows it. `replay`, when present, adds its button; pressing it calls the hook with `replay=True`.

### end and unheard

`end` is the last row (and the strip's length, with the latest line or event). `unheard` lists lines this run never
reached, under `unheard_label`, each with what it waits on and whether it was still pending at the end.

## The page's link

`#timeline/<group>/<line id or key>` opens a group's timeline at a line.
