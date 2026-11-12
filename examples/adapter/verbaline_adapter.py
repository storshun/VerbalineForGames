"""Night Ferry's hook-up to Verbaline For Games: an example adapter (docs/HookingUpAProject.md, "An adapter").

The game keeps its dialogue in game/scenes.json: scenes of beats, each a spoken line or an event. This module tells
the studio which lines there are, writes word edits back into the scene file, turns the picks into the game's voice
table on Apply, and lays each scene out on a clock for the Timeline tab. Every hook is optional but lines()."""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENES = ROOT / 'game' / 'scenes.json'
WORDS_PER_SECOND = 2.6          # how long an unvoiced line is guessed to take


def _scenes():
    return json.loads(SCENES.read_text())['scenes']


def lines(ctx):
    """Every spoken line: id, speaker, text; group (its scene), emotion (the script's mood) and context are optional."""
    out = []
    for s in _scenes():
        for b in s['beats']:
            if 'id' in b:
                out.append(dict(id=b['id'], speaker=b['who'], text=b['say'], group=s['id'],
                                emotion=b.get('mood', ''), context=s['title']))
    return out


def groups(ctx):
    """The scenes, in order, with their titles. Each gets a timeline (this module has a timeline hook)."""
    return [dict(id=s['id'], title=s['title']) for s in _scenes()]


def set_words(ctx, ids, text):
    """The page's ✎ edit words: rewrite those lines' words in the scene file."""
    d = json.loads(SCENES.read_text()); n = 0
    for s in d['scenes']:
        for b in s['beats']:
            if b.get('id') in ids: b['say'] = text; n += 1
    if not n: raise ValueError(f'no line {", ".join(ids)} in {SCENES.name}')
    SCENES.write_text(json.dumps(d, indent=2) + '\n')


def watch(ctx):
    """Files whose change means the lines must be read again."""
    return [SCENES]


def game_state(ctx):
    """What the game has now: the words its voice table was made with, and the take behind each line's file. The page
    marks a line "not in the game yet" when its words or pick differ from these."""
    table = ROOT / 'game' / 'vo_table.json'
    if not table.exists(): return {}, {}
    t = json.loads(table.read_text())
    return ({i: e['text'] for i, e in t.items()}, {e['key']: e['take'] for e in t.values()})


def apply(ctx, manifest, run):
    """Apply: copy the mastered takes into game/vo and write the game's voice table from the manifest. `run` runs a
    command in the project's root, logged, and stops Apply when it fails (use it for an import or a test)."""
    m = json.loads(Path(manifest).read_text()); vo = ROOT / 'game' / 'vo'; vo.mkdir(parents=True, exist_ok=True)
    for e in m['lines'].values(): shutil.copy2(Path(manifest).parent / e['file'], vo / e['file'])
    table = {i: dict(file='vo/' + e['file'], text=e['text'], seconds=e['seconds'], key=e['key'], take=e['take'])
             for i, e in m['lines'].items()}
    (ROOT / 'game' / 'vo_table.json').write_text(json.dumps(table, indent=1) + '\n')
    print(f'  {len(table)} lines in game/vo_table.json', flush=True)


def timeline(ctx, group, options, replay=False):
    """One scene on the player's clock (docs/details/timeline-details.md): each line starts after the beat before it,
    plus its `after` pause; a voiced line lasts its take, an unvoiced one is estimated from its words. The `pace`
    option stretches the pauses (a reader who lingers)."""
    pace = float(options.get('pace', 1))
    table = {}
    if (ROOT / 'game' / 'vo_table.json').exists(): table = json.loads((ROOT / 'game' / 'vo_table.json').read_text())
    scene = next((s for s in _scenes() if s['id'] == group), _scenes()[0])
    t, out, events, prev = 0.0, [], [], None
    for b in scene['beats']:
        t += b.get('after', 0) * pace
        if 'event' in b:
            events.append(dict(kind=b['event'], t=round(t, 2), text=b['text'])); continue
        voiced = b['id'] in table
        dur = table[b['id']]['seconds'] if voiced else len(b['say'].split()) / WORDS_PER_SECOND
        out.append(dict(id=b['id'], speaker=b['who'], words=b['say'], start=round(t, 2), end=round(t + dur, 2),
                        est=not voiced, ex=scene['id'], cause=f'after {prev}' if prev else 'the scene opens',
                        flags=[dict(label='tight', why='under 0.5 s after the line before it')] if prev and b.get('after', 0) * pace < .5 else []))
        prev = b['who']; t += dur
    return dict(
        group=scene['id'], title=scene['title'],
        summary=f'{len(out)} lines, {t:.0f} s at pace x{pace:g}.',
        options=[dict(id='pace', label='pace', about='How long the player lingers between beats', value=str(options.get('pace', '1')),
                      choices=[dict(id='0.5', label='a quick reader'), dict(id='1', label='an average reader'), dict(id='2', label='a slow reader')])],
        lines=out, events=events,
        kinds={'horn': dict(label='sound', color='#9fb4ff', strip='mark'), 'choice': dict(label='choice', color='#c79bff', strip='mark', filter='choices')},
        filters=[dict(id='choices', label='choices', about='The player\'s choices on screen')],
        end=dict(t=round(t, 2), text='The scene ends'))
