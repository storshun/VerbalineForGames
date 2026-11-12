"""Edits a project's studio files (its cast, directions and pronunciations) for the page, keeping their comments and
layout (tomlkit).

Every change is written straight back to the file, so the TOML files stay the one place the cast and the direction
live: hand edits, agents and the page all see the same thing. Where they live is the project's (verbaline.toml
[files]); use() points this module at a project."""
import re
from pathlib import Path
import tomlkit

PROJECT = None


def use(project):
    """Edit this project's files from now on (project.Project)."""
    global PROJECT
    PROJECT = project


def _path(name):
    if PROJECT is None: raise RuntimeError('tomledit.use(project) first')
    return {'cast.toml': PROJECT.cast_file, 'directions.toml': PROJECT.directions_file,
            'pronunciations.toml': PROJECT.pronunciations_file}[name]


VOICE_ID = re.compile(r'^[a-z][a-z0-9_]{1,31}$')
# Profile fields the page may set, with their types. Empty strings remove a field (back to the default).
VOICE_FIELDS = {'description': str, 'passage': str, 'engine': str, 'pitch_shift': int, 'xai_voice': str, 'xai_speed': float,
                'notes': str}
LINE_FIELDS = ('voice', 'emotion', 'note', 'say', 'engine', 'pitch_shift', 'parts')   # parts: ✂ lineparts.py


def _load(name):
    p = _path(name)
    return tomlkit.parse(p.read_text()) if p.exists() else tomlkit.document()


def _save(name, doc):
    text = re.sub(r'\n{3,}', '\n\n', tomlkit.dumps(doc)).rstrip('\n') + '\n'   # removed tables leave blank lines
    p = _path(name); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp'); tmp.write_text(text); tmp.replace(p)


def set_voice(voice, fields):
    """Updates a voice's profile; a field set to '' or None goes back to its default."""
    doc = _load('cast.toml'); voices = doc.setdefault('voices', tomlkit.table(is_super_table=True))
    if voice not in voices: raise ValueError(f'no voice "{voice}"')
    v = voices[voice]
    for k, val in fields.items():
        if k not in VOICE_FIELDS: raise ValueError(f'unknown field "{k}"')
        if val is None or (isinstance(val, str) and not val.strip()):
            if k in v: del v[k]
            continue
        v[k] = VOICE_FIELDS[k](val.strip() if isinstance(val, str) else val)
    _save('cast.toml', doc)


def add_voice(voice, description=''):
    """A new cast member's voice profile."""
    if not VOICE_ID.match(voice): raise ValueError('a voice id is lowercase letters, digits and _, like "okafor"')
    doc = _load('cast.toml')
    if 'voices' not in doc: doc['voices'] = tomlkit.table(is_super_table=True)
    if voice in doc['voices']: raise ValueError(f'"{voice}" already exists')
    t = tomlkit.table(); t['description'] = description.strip() or 'Describe how this voice sounds.'
    t['pitch_shift'] = 0
    doc['voices'][voice] = t
    _save('cast.toml', doc)


def set_speaker(speaker, voice):
    """Which voice a script speaker uses by default."""
    doc = _load('cast.toml')
    if voice not in doc.get('voices', {}): raise ValueError(f'no voice "{voice}"')
    if 'speakers' not in doc: doc['speakers'] = tomlkit.table()
    doc['speakers'][speaker] = voice
    _save('cast.toml', doc)


def set_line(ids, fields):
    """A line's direction: its voice (if not its speaker's), emotion, directing note, the text the engine reads
    (if not the script's), the engine that makes its takes (if not its voice's), the pitch shift your recordings
    of it convert at (if not its voice's), and its parts, each in its own tone (✂, lineparts.py). Applied to every id given (lines that share one recording are directed together)."""
    doc = _load('directions.toml')
    if 'lines' not in doc: doc['lines'] = tomlkit.table(is_super_table=True)
    lines = doc['lines']
    for i in ids:
        if i not in lines: lines[i] = tomlkit.table()
        t = lines[i]
        for k, val in fields.items():
            if k not in LINE_FIELDS: raise ValueError(f'unknown field "{k}"')
            val = str(val if val is not None else '').strip()
            if val: t[k] = int(val) if k == 'pitch_shift' else val
            elif k in t: del t[k]
        if not len(t): del lines[i]
    _save('directions.toml', doc)


def set_pronunciation(word, say):
    """How text-to-speech says a word in every line (pronunciations.toml [say]): the game's subtitles keep the word.
    An empty say removes it."""
    word, say = (word or '').strip(), (say or '').strip()
    if not re.fullmatch(r"[\w'.-]+", word): raise ValueError('a pronunciation is for one whole word, as the script spells it')
    doc = _load('pronunciations.toml')
    if 'say' not in doc: doc['say'] = tomlkit.table()
    if say: doc['say'][word] = say
    elif word in doc['say']: del doc['say'][word]
    _save('pronunciations.toml', doc)
