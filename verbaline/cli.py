#!/usr/bin/env python3
"""Verbaline For Games: direct, voice and pick every line of a project's dialogue, then hand the picks to the game.
docs/Overview.md says what it is; docs/HookingUpAProject.md how a project hooks up.

    verbaline serve [--port 8765]   the studio page (Lines, Cast, Timeline): everything below, from the browser
    verbaline lines                 read the project's lines (run by the page whenever they change)
    verbaline status [--voice V]    what's done for each voice
    verbaline design [--voice V] [--n 6]   audition candidate voices from cast.toml's descriptions (Qwen3-TTS VoiceDesign)
    verbaline choose --voice V --candidate N [--emotion neutral]   make a candidate that voice's reference
    verbaline record --voice V [--group G] [--line ID] [--missing]   act lines yourself into the mic
    verbaline convert [--voice V] [--line ID] [--ref E] [--perf NAME]   your performances -> the character's voice
                                     (Seed-VC: a "clone" take and a "pitch" take per recording)
    verbaline train --voice V [--kind clone|pitch] [--steps N]   fine-tune Seed-VC on a voice (its references and
                                     good takes); its conversions use the tuned models from then on
    verbaline tts [--voice V] [--line ID] [--takes N] [--more] [--backend B] [--regen] [--part P]   text-to-speech
                                     takes (each voice uses its cast.toml engine; a line in parts gets tries of each
                                     part, joined into whole takes)
    verbaline restyle (--voice V --from CLIP | --line ID) [--engine qwen|editx] (--style WORDS | --recipe EDITS)
                                     a new delivery in the same voice (restyle-keep keeps the best)
    verbaline mirror --from CLIP --into CLIP [--line ID]   a clip's delivery in another voice (Seed-VC)
    verbaline score [--voice V]    rate every new take (words, voice match, audio quality)
    verbaline tweaks [--voice V]   the prompts written on takes: what the next takes should change
    verbaline master [--lang en]   clean up the picks and export them
    verbaline promote TAKE --voice V --emotion E   make a good take (or any wav) a reference clip
    verbaline run --voice V        convert + tts + score in one go
    verbaline apply                master the picks, write the manifest, and hand them to the project (its hook)

Every command works on one project: --project <folder>, else $VERBALINE_PROJECT, else the nearest verbaline.toml
from the working folder up. Heavy libraries load only for the commands that need them."""
import argparse, csv, importlib, json, os, random, re, shutil, subprocess, sys, tempfile, time, tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path: sys.path.insert(0, str(HERE.parent))    # run as a script: `python verbaline/cli.py`
sys.dont_write_bytecode = True
from verbaline import lineparts, models, project as projects, workfiles   # noqa: E402

SCORE_VERSION = 2          # bump to rescore every take when the scoring rules change (2: start/end words checked)
EMOTIONS = ('neutral', 'calm', 'urgent', 'shouting', 'whisper', 'sad', 'warm', 'playful', 'stunned', 'angry', 'crying',
            'vengeful')


def ref_order(emotion):
    """The emotions whose reference a line of this emotion clones, in order: its own, neutral, calm, its nearest kin
    (workfiles.ref_order; the page's "reference: auto")."""
    return workfiles.ref_order(emotion, EMOTIONS)


# ------------------------------------------------------------------ config and lines

def load_toml(path):
    path = Path(path)
    if not path.exists(): return {}
    return tomllib.loads(workfiles.read_user_text(path))


class Ctx:
    """One project's studio: its settings (cfg), its studio files (cast, directions, pronunciations) and its work folder."""
    def __init__(self, root=None):
        self.project = projects.Project(root or projects.find())
        # Every job the page runs, and every re-run in a model's environment, works on this same project.
        os.environ['VERBALINE_PROJECT'] = str(self.project.root)
        self.reload()
        # VERBALINE_WORK: another work folder (tests: a scratch copy, never the real takes and picks).
        self.work = self.project.work_dir(); self.work.mkdir(parents=True, exist_ok=True)
        self.lang = self.cfg['project'].get('language', 'en')

    def reload(self):
        """Re-reads the settings and the studio files (the page edits them while it runs)."""
        self.project.reload(); self.cfg = self.project.cfg
        self.cast = load_toml(self.project.cast_file); self.cast.setdefault('voices', {}); self.cast.setdefault('speakers', {})
        self.say = load_toml(self.project.pronunciations_file).get('say', {})
        self.dirs = load_toml(self.project.directions_file).get('lines', {})

    @property
    def passage(self): return self.cfg['project'].get('passage', '')
    def path(self, *p): return self.work.joinpath(*p)
    def rel(self, p): return Path(p).resolve().relative_to(self.work.resolve()).as_posix()   # forward slashes on Windows too
    def voice_cfg(self, v): return self.cast.get('voices', {}).get(v, {})
    def engine(self, v):
        """The text-to-speech engine a voice uses: its cast.toml engine, else the config's default (local). An engine
        that isn't one (taken out, or misspelled) counts as unset."""
        e = self.voice_cfg(v).get('engine')
        return e if e in models.ENGINES else self.cfg['tts']['backend']
    def line_engine(self, r):
        """The engine a line's takes are made with: its own (chosen on the Lines tab, directions.toml), else its voice's."""
        return r.get('engine') if r.get('engine') in models.ENGINES else self.engine(r['voice'])
    def ref(self, voice, emotion='neutral'):
        """A voice's reference clip for an emotion and its transcript: its own, else neutral, calm, its nearest kin
        (ref_order), else any."""
        for e in ref_order(emotion):
            w = self.path('voices', voice, 'ref', e + '.wav')
            if w.exists():
                t = w.with_suffix('.txt'); return w, (t.read_text(encoding='utf-8').strip() if t.exists() else '')
        return None, ''
    def lines(self):
        p = self.path('lines.csv')
        if not p.exists(): sys.exit('No lines yet: run `verbaline lines` first.')
        with open(p, newline='', encoding='utf-8') as f: return list(csv.DictReader(f))
    def json(self, name, default):
        p = self.path(name); return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    def save_json(self, name, data):
        p = self.path(name); tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(data, indent=1), encoding='utf-8'); workfiles.replace(tmp, p)
    def export_name(self, r):
        """An exported pick's file name: [master] name, from the line's fields."""
        return self.cfg['master'].get('name', '{id}').format(id=r['id'], key=r['key'], lang=self.lang, group=r.get('group', ''),
                                                             speaker=r.get('speaker', '')) + '.wav'


def tts_text(text, say):
    """What text-to-speech reads: respelled names, and no stage punctuation it would voice oddly."""
    out = text.replace('...', ', ').replace('—', ', ')
    for word, spoken in say.items():
        out = re.sub(r'(?<![\w-])' + re.escape(word) + r'(?![\w-])', spoken, out)
    return re.sub(r'\s+', ' ', out).strip(' ,')


def default_emotion(text):
    """A line's emotion when neither the project nor its direction says: urgent when it ends in "!", else neutral."""
    return 'urgent' if text.rstrip().endswith('!') else 'neutral'


COLUMNS = ('id', 'key', 'group', 'speaker', 'voice', 'text', 'say', 'emotion', 'say_override', 'voice_default',
           'emotion_default', 'note', 'engine', 'pitch_shift', 'kind', 'context', 'parts')


def cmd_lines(c, a):
    """Every line of the project (its lines hook, or its lines file), with its voice, the text the engine reads, its
    emotion and direction, into <work>/lines.csv. Lines with the same voice and words share one recording (a 'clip
    key': the first line's id)."""
    rows, keys, unknown = [], {}, set()
    for l in c.project.lines(c):
        i, t, who = l['id'], str(l['text']), l['speaker']; d = c.dirs.get(i, {})
        # A line can be given to a different voice than its speaker's (directions.toml "voice"); the project can name
        # one for a speaker the cast doesn't list (its line's "voice").
        dflt = c.cast['speakers'].get(who) or l.get('voice', '')
        voice = d.get('voice') or dflt
        if not voice: unknown.add(who); continue
        emo_d = l.get('emotion') or default_emotion(t)
        if emo_d not in EMOTIONS: print(f'  {i}: the project names emotion "{emo_d}", which isn\'t one; using neutral'); emo_d = 'neutral'
        emo = d.get('emotion', emo_d)
        if emo not in EMOTIONS: print(f'  {i}: unknown emotion "{emo}", using neutral'); emo = 'neutral'
        key = keys.setdefault((voice, t.strip()), i)
        # "say": what the engine reads, when it should differ from the words (xAI tags, a respelling).
        rows.append(dict(id=i, key=key, group=str(l.get('group', '')), speaker=who, voice=voice, text=t,
                         say=tts_text(d.get('say') or t, c.say), emotion=emo, say_override=d.get('say', ''),
                         voice_default=dflt, emotion_default=emo_d, note=d.get('note', ''), engine=d.get('engine', ''),
                         pitch_shift=d.get('pitch_shift', ''), kind=l.get('kind', ''), context=l.get('context', ''),
                         parts=d.get('parts', '')))
    # ✂ Parts: a line written in parts, each in its own tone (directions.toml "parts", lineparts.py). The engine reads
    # the parts' words, so they take the place of "say it as".
    for r in rows:
        if r['parts']:
            try: r['say'] = tts_text(lineparts.plain(lineparts.parse(r['parts'], r['emotion'])), c.say)
            except ValueError as e: print(f'  {r["id"]}: its parts can\'t be read ({e}): no takes until they\'re fixed')
    stale = sorted(set(c.dirs) - {r['id'] for r in rows})
    for v in sorted({r['voice'] for r in rows}):
        if why := workfiles.name_problem(v): sys.exit(f'voice id {why}: it names a folder of the work folder; rename it in the cast')
    with open(c.path('lines.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    c.save_json('groups.json', c.project.groups(c, rows))
    clips = len({r['key'] for r in rows})
    print(f'{len(rows)} lines ({clips} distinct recordings) for {len({r["voice"] for r in rows})} voices -> {c.path("lines.csv")}')
    for s in sorted(unknown): print(f'  no voice for speaker "{s}": add it to the cast\'s [speakers]')
    for s in stale: print(f'  directions name {s}, which the project no longer has')


# ------------------------------------------------------------------ what's where

def keys_of(c, a):
    """The clip keys a command works on (one per distinct recording), filtered by --voice / --group / --line / --keys,
    and --todo (only lines that don't have a pick yet)."""
    seen, out = set(), []
    picked = c.json('picks.json', {}) if getattr(a, 'todo', False) else {}
    keys = set(a.keys.split(',')) if getattr(a, 'keys', None) else None
    for r in c.lines():
        if keys is not None and r['key'] not in keys: continue
        if r['key'] in picked: continue
        if getattr(a, 'voice', None) and r['voice'] != a.voice: continue
        if getattr(a, 'group', None) is not None and r['group'] != str(a.group): continue
        if getattr(a, 'line', None) and a.line not in (r['id'], r['key']): continue
        if r['key'] in seen: continue
        seen.add(r['key']); out.append(r)
    return out


def performances(c, key): return sorted(c.path('performances').glob(f'{key}_p*.wav'))
def takes(c, key): return sorted(c.path('takes', key).glob('*.wav'))


def same_words(a, b): return ' '.join((a or '').split()) == ' '.join((b or '').split())


def made_from(c, key):
    """{take file: {text, at}}: the words each take was made from (a take whose words changed since is outdated)."""
    f = c.path('takes', key, 'made.json'); return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def record_made(c, key, name, text, ref=None, shift=None, **more):
    made = made_from(c, key); made[name] = dict(text=text, at=time.strftime('%Y-%m-%d %H:%M'))
    if ref: made[name]['ref'] = Path(ref).stem            # which reference clip it was cloned from
    if shift is not None: made[name]['shift'] = shift     # a conversion's pitch shift, in semitones
    # Restyled and mirrored takes: target (the clip whose voice it has, judged against), from, style, kind, engine.
    made[name].update({k: v for k, v in more.items() if v is not None})
    c.save_json(c.rel(c.path('takes', key, 'made.json')), made)


def cmd_status(c, a):
    lines = c.lines(); picks = c.json('picks.json', {}); tweaks = c.json('tweaks.json', {})
    by = {}
    for r in lines:
        if r['id'] != r['key']: continue
        s = by.setdefault(r['voice'], dict(clips=0, ref=0, perf=0, takes=0, picked=0, prompts=0))
        s['clips'] += 1; s['perf'] += bool(performances(c, r['key'])); s['takes'] += bool(takes(c, r['key']))
        s['picked'] += r['key'] in picks; s['prompts'] += len(tweaks.get(r['key'], {}))
    print(f'{"voice":12} {"ref":>4} {"lines":>6} {"acted":>6} {"takes":>6} {"picked":>7} {"prompts":>8}')
    for v, s in sorted(by.items()):
        if a.voice and v != a.voice: continue
        ref = 'yes' if c.ref(v)[0] else '-'
        print(f'{v:12} {ref:>4} {s["clips"]:>6} {s["perf"]:>6} {s["takes"]:>6} {s["picked"]:>7} {s["prompts"]:>8}')
    exported = len(list(c.path('export', c.lang).glob('*.wav'))) if c.path('export', c.lang).exists() else 0
    print(f'exported ({c.lang}): {exported} of {len(lines)} line files')


# ------------------------------------------------------------------ voices

def cmd_design(c, a):
    if a.retry:
        if not a.voice: sys.exit('--retry needs --voice')
        return retry_candidate(c, a)
    voices = [a.voice] if a.voice else sorted(c.cast['voices'])
    with models.QwenDesign() as q:
        for v in voices:
            vc = c.voice_cfg(v)
            if not vc: print(f'{v}: not in cast.toml'); continue
            out = c.path('voices', v, 'design'); out.mkdir(parents=True, exist_ok=True)
            passage = vc.get('passage') or c.passage
            have = workfiles.next_candidate(out) - 1      # never reuses a deleted candidate's number
            for n in range(have + 1, have + a.n + 1):
                seed = random.randrange(1, 2 ** 31); cand = out / f'cand_{n}.wav'
                q.design(vc['description'], passage, cand, seed=seed)
                cand.with_suffix('.txt').write_text(passage, encoding='utf-8')
                workfiles.save_meta(cand, dict(method='design', seed=seed, description=vc['description'], style=q.STYLE,
                                              model=q.MODEL, text=passage, at=time.strftime('%Y-%m-%d %H:%M')))
            print(f'{v}: {a.n} candidates in {out} (listen, then `verbaline choose --voice {v} --candidate N`)')


def retry_candidate(c, a):
    """↻ on a candidate: the same voice reading other words (--text, default the voice's audition text), as a NEW
    candidate. It clones the candidate's ORIGINAL audio (its design/sources/ copy, or itself) with Qwen3-TTS Base.
    Until Nov 6 a retry replaced the candidate in place (the old audio to rejected/), and so silently changed what
    its row played under the references made from it: 24 of the cast's 43 references came from versions no row
    played any more (one voice's calm, neutral and warm were three older readings of its candidate 24). Now the candidate and
    its references stay as they are.

    Why not replay the design seed: measured Oct 7, the same seed and description with new words is no closer to the
    original voice than a fresh seed (speaker similarity 0.35, against 0.15-0.34 for fresh seeds); the sampling
    diverges once the text changes. Cloning keeps it (0.81-0.82). Seeds are still recorded: with the same text they
    reproduce a candidate exactly."""
    d = c.path('voices', a.voice, 'design'); cand = d / f'cand_{a.retry}.wav'
    if not cand.exists(): sys.exit(f'No {cand}')
    text = (a.text or '').strip() or c.voice_cfg(a.voice).get('passage') or c.passage; m = workfiles.meta(cand)
    src = d / 'sources' / cand.name
    if not src.exists(): src = cand                  # never retried: its own audio is the original
    src_text = src.with_suffix('.txt').read_text(encoding='utf-8').strip() if src.with_suffix('.txt').exists() else ''
    seed = random.randrange(1, 2 ** 31); t0 = time.time()
    n = workfiles.next_candidate(d); out = d / f'cand_{n}.wav'
    with models.Qwen(c) as q: q.say(tts_text(text, c.say), src, src_text, 'neutral', {}, out, seed=seed)
    out.with_suffix('.txt').write_text(text, encoding='utf-8')
    workfiles.save_meta(out, dict(method='reread', of=a.retry, seed=seed, source=c.rel(src), model=models.Qwen.MODEL,
                                 description=m.get('description', ''), text=text, at=time.strftime('%Y-%m-%d %H:%M')))
    print(f'{a.voice}: candidate {n} is candidate {a.retry}\'s voice reading new words ({time.time() - t0:.1f} s); '
          f'candidate {a.retry} stays as it was.')


def cmd_preview(c, a):
    """A design candidate's audition text, spoken by a text-to-speech engine cloning it: how that engine will deliver
    the voice before it's chosen. Written to design/previews/cand_N.<engine>.wav."""
    src = c.path('voices', a.voice, 'design', f'cand_{a.candidate}.wav')
    if not src.exists(): sys.exit(f'No {src}')
    text = src.with_suffix('.txt').read_text(encoding='utf-8').strip() if src.with_suffix('.txt').exists() else c.passage
    out = src.parent / 'previews' / f'{src.stem}.{a.backend}.wav'; out.parent.mkdir(exist_ok=True)
    with models.backend(a.backend, c) as tts:
        t0 = time.time()
        tts.say(tts_text(text, c.say), src, text, 'neutral', c.voice_cfg(a.voice), out, seed=1)
    print(f'{a.voice} candidate {a.candidate}: {a.backend} preview in {time.time() - t0:.1f} s -> {out.name}')


def line_row(c, key):
    r = next((x for x in c.lines() if x['key'] == key), None)
    if not r: sys.exit(f'No line {key}')
    return r


def clip_info(c, rel):
    """Any clip in the work folder and what it is: (path, {kind, voice, label, text, ...}). kind 'candidate' (n,
    method), 'ref' (emotion; came: where that reference came from), 'take' (line, take) or 'recording' (line, name).
    voice: whose voice it is ('' for your recordings); text: what it says (its transcript; for a take, what Whisper
    heard in it, else the words it was made from)."""
    p = c.path(rel).resolve(); w = c.work.resolve()
    if not p.exists() or p.suffix != '.wav' or w not in p.parents: sys.exit(f'No {rel}')
    parts = p.relative_to(w).parts
    txt = p.with_suffix('.txt').read_text(encoding='utf-8').strip() if p.with_suffix('.txt').exists() else ''
    if len(parts) == 4 and parts[0] == 'voices' and parts[2] == 'design' and workfiles.CAND.fullmatch(p.stem):
        n = int(p.stem.split('_')[1])
        return p, dict(kind='candidate', voice=parts[1], n=n, method=workfiles.meta(p).get('method', 'design'), text=txt,
                       label=f'{parts[1]} candidate {n}')
    if len(parts) == 4 and parts[0] == 'voices' and parts[2] == 'ref' and p.stem in EMOTIONS:
        return p, dict(kind='ref', voice=parts[1], emotion=p.stem, text=txt, came=workfiles.clip_source(c.work, parts[1], p),
                       label=f'{parts[1]}\'s {p.stem} reference')
    if len(parts) == 3 and parts[0] == 'takes':
        key = parts[1]; r = next((x for x in c.lines() if x['key'] == key), None)
        sc = c.path('takes', key, 'scores.json')
        heard = json.loads(sc.read_text(encoding='utf-8')).get(p.name, {}).get('heard', '') if sc.exists() else ''
        return p, dict(kind='take', line=key, take=p.name, voice=r['voice'] if r else '',
                       text=heard or made_from(c, key).get(p.name, {}).get('text', ''), label=f'take {p.stem} of {key}')
    if len(parts) == 2 and parts[0] == 'performances':
        return p, dict(kind='recording', line=re.sub(r'_p\d+$', '', p.stem), name=p.stem, voice='', text=txt,
                       label=f'your recording {p.stem}')
    sys.exit(f'{rel} is not a candidate, reference, take or recording')


def spoken(text):
    """What a local engine reads: no xAI tags (<loud>, [pause]) left in a line's engine text."""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>|\[[^\]]*\]', ' ', text)).strip()


def says(a, b):
    """Two transcripts say the same words (case, punctuation and spacing aside)."""
    return models.words(a) == models.words(b)


def restyle_source(c, voice, rel, line=None):
    """A restyle's source, whose voice is kept: a candidate or a reference of the voice, or (restyling a line) a take of
    that line. (path, what) as clip_info, without its transcript."""
    p, what = clip_info(c, rel)
    if not ((what['kind'] in ('candidate', 'ref') and what['voice'] == voice)
            or (line and what['kind'] == 'take' and what['line'] == line)):
        sys.exit(f'{rel}: restyle a candidate or reference of {voice}' + (f', or a take of {line}' if line else ''))
    return p, what


def cmd_restyle(c, a):
    """✦ Restyle, part 1: the source's voice in a new delivery, --tries times. The same voice shouting, whispering,
    crying or vengeful, from one reference or candidate.
    Into new candidates (a candidate or reference of --voice; reads --text, default its audition text), or with --line
    into new takes of that line (from the voice's neutral reference, or --from one of its takes or references).
    Two engines (--engine):
      qwen (default): Qwen3-TTS VoiceDesign acts the words from the voice's description and --style (free words, e.g.
        the line's directing notes), Seed-VC puts the source's voice back on, and Qwen3-TTS reads it again cloning
        that conversion (revoice; --raw keeps the conversion itself).
        Why three models: VoiceDesign acts a style from words but makes a new voice each time (speaker match to the
        source 0.41-0.52); Qwen3-TTS cloning keeps the voice (0.78-0.86) but not the style; Seed-VC's pitch-following
        model gives the acted take the source's timbre and keeps its acting. Measured on a female lead's neutral
        reference, shouted: 0.54-0.78 with the shout kept (+4.6 semitones, 3 dB louder). Its timbre model matched as
        well (0.74-0.84) but pulled the pitch back into her calm range: no shout left. Seed-VC warbles, though
        (audibly: warble and compression artifacts), and cloning its conversion keeps the acting
        without it.
      editx: Step-Audio-EditX edits the source clip itself (--recipe: its edits in turn, e.g. "emotion:coldness,
        style:murmur"), reading the new words in its voice first when the source says other words. Its voice comes
        from the clip's own speaker features, so no conversion follows."""
    row = line_row(c, a.line) if a.line else None
    voice = row['voice'] if row else a.voice
    if not voice: sys.exit('restyle needs --voice or --line')
    rel = getattr(a, 'from')
    if not rel and row:
        # The voice's everyday reference (neutral, else any): the delivery comes from the acting, and an emotion's own
        # reference would pull the pitch toward its emotion (Nov 6: from the angry one, "quiet, cold" came out at
        # 304-339 Hz, as high as the angry takes).
        ref, _ = c.ref(voice, 'neutral')
        if not ref: sys.exit(f'{voice} has no reference to restyle from (Cast tab)')
        rel = c.rel(ref)
    if not rel: sys.exit('restyle needs --from (a candidate or reference)')
    src, what = restyle_source(c, voice, rel, a.line)
    src_text = what.pop('text')
    if what['kind'] == 'take':                         # the words it was made from: Whisper may mishear one
        src_text = made_from(c, a.line).get(src.name, {}).get('text') or src_text
    work = c.path('voices', voice, 'design', 'restyle', a.dir); work.mkdir(parents=True, exist_ok=True)
    m = workfiles.meta(src) if what['kind'] == 'candidate' else {}
    description = m.get('description') or c.voice_cfg(voice).get('description', '')
    words = row['text'] if row else (a.text or c.voice_cfg(voice).get('passage') or c.passage)   # what it says
    text = spoken(row['say']) if row else tts_text(words, c.say)                             # what the engine reads
    plan = dict(voice=voice, source=c.rel(src), what=what, engine=a.engine, style=(a.style or '').strip(),
                recipe=(a.recipe or '').strip(), text=words, n=a.n, description=description, line=a.line or '',
                emotion=a.emotion or '', say_override=row.get('say_override', '') if row else '', tries=[])
    if a.engine == 'editx':
        try: steps = models.editx_steps(a.recipe)
        except ValueError as e: sys.exit(str(e))
        if not src_text: sys.exit(f'{rel} has no transcript: Step-Audio-EditX needs to know what it says')
        # A take of the line already says it (never read again: that would throw its delivery away); anything else
        # reads the line's words in its voice first.
        lead = [] if what['kind'] == 'take' or says(src_text, text) else [('clone', text)]
        jobs = [dict(out=work / f'try_{k}.wav', audio=src, text=src_text, steps=lead + steps) for k in range(a.tries)]
        made = {Path(x).name for x in models.StepEditX(c).run(jobs)}
        plan['tries'] = [dict(file=f'try_{k}.wav') for k in range(a.tries) if f'try_{k}.wav' in made]
        how = a.recipe.strip(); plan['style'] = ''          # the edits are the label (not the page's words)
    else:
        if not plan['style']: sys.exit('restyle needs --style: how it should be read')
        style = ' ' + plan['style'].rstrip('.') + '. Clean studio recording.'
        with models.QwenDesign() as q:
            for k in range(a.tries):
                seed = random.randrange(1, 2 ** 31); out = work / f'try_{k}.wav'
                q.design(description, text, out, seed=seed, style=style)
                plan['tries'].append(dict(file=out.name, seed=seed)); print(f'  acted {k + 1} of {a.tries}', flush=True)
        revoice(c, plan, work, src, text, raw=a.raw)
        how = plan['style']
    (work / 'plan.json').write_text(json.dumps(plan, indent=1), encoding='utf-8')
    if not plan['tries']: sys.exit(f'{voice}: no tries were made ("{how}"): see the errors above')
    if a.engine != 'editx' and not any('out' in t for t in plan['tries']):
        sys.exit(f'{voice}: Seed-VC made none of the {len(plan["tries"])} conversions (see above); the tries stay in {work}')
    print(f'{voice}: {len(plan["tries"])} tries "{how}" in {Path(src).name}\'s voice; restyle-keep keeps the best of them')


def revoice(c, plan, work, src, said, raw=False):
    """Restyle with the qwen engine, part 2: the source's voice put back on each acted try with Seed-VC's
    pitch-following model, its pitch moved to where its emotion sits in that voice (register_shift); then, unless raw,
    Qwen3-TTS Base reads the same words again, cloning that conversion. Each try's 'out' is what restyle-keep judges.
    Why the re-read (measured Nov 7 on 4 tries each of three voices: angry, urgent and vengeful, SQUIM's PESQ
    estimate): Qwen's acted tries 3.7-4.2, after Seed-VC 3.1-3.3, and no Seed-VC setting fixed that (fp32, 60 steps,
    cfg 0.3 or no shift: 2.8-3.4); read again 3.9-4.1, as clean as Qwen's own takes (median 0.89 on the page's audio
    scale, Seed-VC conversions 0.55). The re-read kept the loudness and its swings, the pitch range and the voice
    (match 0.79-0.94); the pitch itself moved some (one angry +2.4 semitones over the everyday pitch became +0.9,
    an urgent +5.1 +4.3, a vengeful +2.2 +3.2), and it read about 10% faster."""
    home = home_f0(c, src, plan['what']); vc_cfg = c.cfg['convert']
    todo = []
    for t in plan['tries']:
        acted = work / t['file']; t['shift'] = register_shift(models.median_f0(acted), home, plan.get('emotion'))
        todo.append((acted, src, work / ('vc_' + t['file']), float(vc_cfg.get('cfg_rate', 0.7)), t['shift'], True, None))
    seed = models.SeedVC(Path(os.path.expanduser(c.cfg['repos']['seed_vc'])), vc_cfg.get('diffusion_steps', 30),
                            c.cfg['repos'].get('seed_vc_python', ''))
    made = {Path(p).name for p in seed.convert(todo)}
    for t in plan['tries']:
        if 'vc_' + t['file'] in made: t['out'] = 'vc_' + t['file']
    plan['reread'] = not raw
    if raw or not made: return
    with models.Qwen(c) as q:
        for k, t in enumerate(t for t in plan['tries'] if 'out' in t):
            out = work / ('rr_' + t['file'])
            try: q.say(said, work / t['out'], said, '', {}, out, seed=random.randrange(1, 2 ** 31))
            except Exception as e:
                print(f'  {t["file"]}: the clean re-read failed ({e}); its conversion is judged instead', flush=True); continue
            t['out'] = out.name; print(f'  read again cleanly: {k + 1} of {len(made)}', flush=True)


def cmd_restyle_keep(c, a):
    """Restyle, part 3: each try judged against the source (ECAPA speaker match, Whisper for the words, SQUIM for the
    audio), --n kept (keep_order) as new candidates labelled with the style and what they came from, or as new takes
    of the line (restyle_<k>.wav, scored with it); the rest go. Nothing kept fails the job."""
    import numpy as np
    voice = a.voice
    work = c.path('voices', voice, 'design', 'restyle', a.dir); plan = json.loads((work / 'plan.json').read_text(encoding='utf-8'))
    src = c.path(plan['source']); conv = plan.get('engine', 'qwen') != 'editx'
    if not conv:
        for t in plan['tries']: t['out'] = t['file']          # Step-Audio-EditX's edits already have the voice
    if not any('out' in t for t in plan['tries']):
        sys.exit(f'{voice}: nothing to judge in {work} (a restyle from before Nov 7, or its conversions failed): restyle again')
    forgive = set(c.say) | {w for v in c.say.values() for w in models.words(v)}
    if plan.get('say_override'):                   # the line's own respelling, forgiven as cmd_score does
        forgive |= set(models.words(plan['say_override'])) ^ set(models.words(plan['text']))
    import soundfile as sf
    with models.Scorer(c.cfg['score']['whisper_model']) as s:
        for t in plan['tries']:
            if 'out' not in t: continue
            r = s.score(work / t['out'], plan['text'], src, forgive)
            y, _ = sf.read(work / t['out'], dtype='float32', always_2d=True)
            t.update(match=r['voice'], wer=r['wer'], quality=r['quality'], heard=r['heard'],
                     level=float(20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-9)))
    ok = keep_order([t for t in plan['tries'] if 'match' in t and t['wer'] <= c.cfg['score']['max_wer']],
                    plan.get('emotion'), not conv)
    kept = []
    label = plan['style'] or plan.get('recipe', '')
    clean = conv and plan.get('reread', False)
    for t in ok[:plan['n']]:
        got = work / t['out']; reread = clean and t['out'].startswith('rr_')
        if plan.get('line'):
            key = plan['line']; out = c.path('takes', key); out.mkdir(parents=True, exist_ok=True)
            k = 1 + max([int(m[1]) for p in list(out.glob('restyle_*.wav')) + list(out.glob('removed/restyle_*.wav'))
                         if (m := re.fullmatch(r'restyle_(\d+)', p.stem))] + [0])
            shutil.copy2(got, out / f'restyle_{k}.wav')
            record_made(c, key, f'restyle_{k}.wav', plan['text'], src if plan['what']['kind'] == 'ref' else None,
                        t.get('shift'), target=plan['source'], style=label, engine=plan.get('engine', 'qwen'),
                        match=t['match'], reread=reread or None)
            kept.append(f'restyle_{k} (voice {t["match"]:.2f}, audio {t["quality"]:.2f})')
        else:
            d = c.path('voices', voice, 'design'); n = workfiles.next_candidate(d); cand = d / f'cand_{n}.wav'
            shutil.copy2(got, cand); cand.with_suffix('.txt').write_text(plan['text'], encoding='utf-8')
            workfiles.save_meta(cand, dict(method='restyle', style=label, engine=plan.get('engine', 'qwen'), emotion=plan.get('emotion', ''),
                                          source=plan['source'], what=plan['what'], description=plan['description'],
                                          seed=t.get('seed'), shift=t.get('shift'), match=t['match'], quality=t['quality'],
                                          reread=reread, model=models.QwenDesign.MODEL if conv else 'stepfun-ai/Step-Audio-EditX',
                                          text=plan['text'], at=time.strftime('%Y-%m-%d %H:%M')))
            kept.append(f'candidate {n} (voice {t["match"]:.2f}, audio {t["quality"]:.2f})')
    shutil.rmtree(work)
    if not kept: sys.exit(f'{voice}: restyled "{label}": none kept: the words came out wrong in all {len(plan["tries"])} tries')
    print(f'{voice}: restyled "{label}"{" (read again cleanly)" if clean else ""}: {", ".join(kept)} of {len(plan["tries"])} tries')


def keep_order(tries, emotion, editx=False):
    """The judged tries a restyle keeps, best first. Not the ones closest to the source: those are the least acted
    (the highest-scoring takes are usually too dry and lack personality; of 113 lines a director picked, the
    top score was the pick 12% of the time, below the 18% a random pick would hit). The voice is a gate instead, its
    match to the source at least 0.5 (0.3 for a whisper, which ECAPA hears as another voice, and for Step-Audio-EditX,
    whose edits it does too: 0.2-0.58 in the Nov 7 tests). Past it a whisper keeps its quietest tries, the rest their
    cleanest audio. None through the gate: the closest to the voice."""
    good = [t for t in tries if t['match'] >= (.3 if emotion == 'whisper' or editx else .5)]
    if not good: return sorted(tries, key=lambda t: -t['match'])
    if emotion == 'whisper': return sorted(good, key=lambda t: t['level'])
    return sorted(good, key=lambda t: -t.get('quality', 0))


def register_shift(f0, home, emotion):
    """Semitones that move an acted try (median pitch f0) to where its emotion sits in its voice, which speaks around
    home (models.PITCH: a shout 5 over, a cold threat 2 under). An emotion not in the table (a free style): halfway
    from the try's own pitch toward home, but no more than 3 under or 5 over it (when every try went halfway,
    a male voice's "rushed, excited" ones stayed 6-8 semitones over him). 0 when either pitch is unknown (a true
    whisper has none); at most an octave either way."""
    import math
    if not f0 or not home: return 0
    gap = 12 * math.log2(f0 / home)
    want = models.PITCH.get(emotion, 'half') if emotion else 'half'
    if want == 'half': want = min(5, max(-3, gap / 2))
    return int(round(min(12, max(-12, want - gap))))


def home_f0(c, p, info):
    """The everyday pitch of a clip's voice, for moving a delivery between voices: the voice's neutral reference (else
    calm, else its first), so a shouted clip isn't taken for how the voice usually sits. That holds for candidates too:
    most audition texts are shouted (a shouted "...we're not going to make it!!" put one candidate at 412 Hz against its voice's
    neutral 249). A clip of a voice with no reference, or one of your recordings: its own."""
    if info.get('voice'):
        for e in ('neutral', 'calm'):
            w = c.path('voices', info['voice'], 'ref', e + '.wav')
            if w.exists(): return models.median_f0(w)
        w, _ = c.ref(info['voice'])
        if w: return models.median_f0(w)
    return models.median_f0(p)


def ref_then(c, info):
    """(the reference clip a take was cloned from, its emotion) as it was when the take was made, or None: the
    reference recorded in its made.json, and of that emotion's kept clips (ref/<emotion>_<time>.wav, ref/removed/) the
    first one replaced after the take was made; while none was, the current one."""
    m = made_from(c, info['line']).get(info['take'], {}); e = m.get('ref'); at = m.get('at', '')
    if not e or e not in EMOTIONS or not at: return None
    when = at.replace('-', '').replace(' ', '-').replace(':', '') + '00'      # '2026-10-09 18:55' -> '20261009-185500'
    d = c.path('voices', info['voice'], 'ref')
    kept = sorted((p for p in [*d.glob(f'{e}_*.wav'), *d.glob(f'removed/{e}_*.wav')]
                   if re.fullmatch(re.escape(e) + r'_\d{8}-\d{6}', p.stem)), key=lambda p: p.stem[-15:])
    later = [p for p in kept if p.stem[-15:] > when]
    return (later[0], e) if later else ((d / f'{e}.wav', e) if (d / f'{e}.wav').exists() else None)


def cmd_mirror(c, a):
    """⇄ Mirror: a clip's delivery (its timing, intonation and energy) in another voice. For a delivery you like on the
    wrong voice: an existing candidate's or take's delivery and cadence under another candidate's voice.
    --from: any take, candidate, reference or recording; --into: the reference or candidate whose voice it gets.
    Seed-VC makes each --kinds: "clone" (its timbre model: the target's own sound and pitch range; the timing exact,
    the intonation looser) and "pitch" (its pitch-following model: the delivery note for note, moved by --shift
    semitones; auto: the difference between the two voices' everyday pitch, so a shout stays a shout).
    With --line: new takes of that line (mirror_<k>_<kind>.wav; score the line after). Without: new candidates of
    the target's voice, judged against the target."""
    import numpy as np
    src, came = clip_info(c, getattr(a, 'from')); tgt, into = clip_info(c, a.into)
    if into['kind'] not in ('ref', 'candidate'): sys.exit(f'{a.into}: mirror into a reference or a candidate')
    if src == tgt: sys.exit('the clip and the voice to mirror it into are the same clip')
    kinds = [k for k in (a.kinds or 'clone,pitch').split(',') if k in ('clone', 'pitch')] or ['clone', 'pitch']
    if a.shift in (None, '', 'auto'):
        f_src, f_tgt = home_f0(c, src, came), home_f0(c, tgt, into)
        was = ref_then(c, came) if came['kind'] == 'take' and came['voice'] == into['voice'] else None
        if was:                                    # made from a reference since replaced: like for like
            now, _ = c.ref(into['voice'], was[1])
            if now and now.exists() and now.resolve() != was[0].resolve():
                f_src, f_tgt = models.median_f0(was[0]), models.median_f0(now)
                print(f'  the take was cloned from {into["voice"]}\'s {was[1]} reference of the time, since replaced', flush=True)
        shift = int(np.clip(round(12 * np.log2(f_tgt / f_src)), -24, 24)) if f_src and f_tgt else 0
        print(f'  pitch {shift:+d} semitones: {came["voice"] or "your recording"} speaks around {f_src:.0f} Hz, '
              f'{into["label"]} around {f_tgt:.0f} Hz', flush=True)
    else: shift = int(a.shift)
    # Into one of a voice's references: its tuned Seed-VC model of that kind when it has one (closer to the voice).
    # Into a candidate: the base models (a tuned model leans toward the references it learned, not the candidate).
    tuned = {k: tuned_model(c, into['voice'], k == 'pitch') if into['kind'] == 'ref' else None for k in kinds}
    vc = c.cfg['convert']; cfg_rate = float(vc.get('cfg_rate', 0.7))
    seed = models.SeedVC(Path(os.path.expanduser(c.cfg['repos']['seed_vc'])), vc.get('diffusion_steps', 30),
                            c.cfg['repos'].get('seed_vc_python', ''))
    words = came['text']
    if a.line:
        r = line_row(c, a.line); out = c.path('takes', a.line); out.mkdir(parents=True, exist_ok=True)
        k = 1 + max([int(m[1]) for p in list(out.glob('mirror_*.wav')) + list(out.glob('removed/mirror_*.wav'))
                     if (m := re.fullmatch(r'mirror_(\d+)_\w+', p.stem))] + [0])
        todo = [(src, tgt, out / f'mirror_{k}_{kind}{"_ft" if tuned[kind] else ""}.wav', cfg_rate, shift if kind == 'pitch' else 0,
                 kind == 'pitch', tuned[kind]) for kind in kinds]
        made = seed.convert(todo)
        # The words it says: a take of this line says the line (as it was made); anything else, its own transcript.
        said = made_from(c, a.line).get(src.name, {}).get('text') if came['kind'] == 'take' and came['line'] == a.line else words
        ref = tgt if into['kind'] == 'ref' and into['voice'] == r['voice'] else None
        for o in made:
            kind = 'pitch' if '_pitch' in Path(o).stem else 'clone'
            record_made(c, a.line, Path(o).name, said or r['text'], ref, shift if kind == 'pitch' else None,
                        target=c.rel(tgt), came=c.rel(src), kind=kind, tuned=bool(tuned[kind]) or None)
        print(f'{a.line}: {len(made)} mirrored takes ({", ".join(Path(o).stem for o in made)}): {came["label"]} in the voice of {into["label"]}')
        return
    d = c.path('voices', into['voice'], 'design'); d.mkdir(parents=True, exist_ok=True)
    work = d / 'restyle' / f'mirror_{time.strftime("%Y%m%d-%H%M%S")}'; work.mkdir(parents=True, exist_ok=True)
    todo = [(src, tgt, work / f'{kind}.wav', cfg_rate, shift if kind == 'pitch' else 0, kind == 'pitch', tuned[kind]) for kind in kinds]
    made = seed.convert(todo); kept = []
    forgive = set(c.say) | {w for v in c.say.values() for w in models.words(v)}
    with models.Scorer(c.cfg['score']['whisper_model']) as s:
        for o in made:
            kind = Path(o).stem; r = s.score(o, words, tgt, forgive) if words else s.score(o, '', tgt, forgive)
            n = workfiles.next_candidate(d); cand = d / f'cand_{n}.wav'; shutil.copy2(o, cand)
            cand.with_suffix('.txt').write_text(words or r['heard'], encoding='utf-8')
            workfiles.save_meta(cand, dict(method='mirror', kind=kind, shift=shift if kind == 'pitch' else None, tuned=bool(tuned[kind]),
                                          came=c.rel(src), came_what={k: v for k, v in came.items() if k != 'text'},
                                          into=c.rel(tgt), into_what={k: v for k, v in into.items() if k != 'text'},
                                          match=r['voice'], wer=r['wer'] if words else None, text=words or r['heard'],
                                          at=time.strftime('%Y-%m-%d %H:%M')))
            kept.append(f'candidate {n} ({kind}, match {r["voice"]:.2f})')
    shutil.rmtree(work)
    print(f'{into["voice"]}: {came["label"]} mirrored into {into["label"]}: {", ".join(kept) or "nothing made"}')


def cmd_beat(c, a):
    """⏸ Add a beat: a take with a pause put in after each sentence, or after one word, as a new take of its line
    (beat_<k>.wav, then scored). For directing notes no model follows reliably: "a beat between the two sentences"
    (End_HijackMai, Mai_HoldFire), "a real pause after each" (Intro_WhatCouldWeDo). Whisper finds the words; the cut
    goes in the quietest stretch near the break, and the pause is the take's own floor (its quietest 30 ms, looped), so
    it sounds like its other pauses, not like a dropout."""
    import numpy as np, soundfile as sf
    import torch                                           # noqa: F401  loads the CUDA libraries faster-whisper needs
    from faster_whisper import WhisperModel
    src, info = clip_info(c, a.take)
    if info['kind'] != 'take': sys.exit('add a beat to a take')
    key = info['line']; audio, sr = sf.read(src, dtype='float32', always_2d=True); audio = audio.mean(1)
    asr = WhisperModel(c.cfg['score']['whisper_model'], device='cuda', compute_type='float16')
    segs, _ = asr.transcribe(str(src), language='en', beam_size=5, word_timestamps=True)
    words = [w for seg in segs for w in (seg.words or [])]
    if len(words) < 2: sys.exit('no words found in that take')
    norm = lambda x: re.sub(r'[^a-z0-9\']', '', x.lower())
    if a.after_word:
        hits = [i for i, w in enumerate(words[:-1]) if norm(w.word) == norm(a.after_word)]
        if len(hits) < a.nth: sys.exit(f'"{a.after_word}" isn\'t in the take {a.nth} time(s) (Whisper heard: {" ".join(w.word.strip() for w in words)})')
        at = [hits[a.nth - 1]]
    else:
        at = [i for i, w in enumerate(words[:-1]) if re.search(r'[.!?;:]["\')]*$', w.word.strip())]
        if not at: at = [i for i, w in enumerate(words[:-1]) if re.search(r'[,—-]$', w.word.strip())]
        if not at: sys.exit('no sentence breaks in that take: choose a word to put the beat after')
    # Whisper's word times are only near the words (Nov 6: its gap after "crew." held the end of the word, so drawing it
    # out repeated speech at -30 dB). So cut in the quietest stretch near each break, and fill with the take's own floor:
    # its quietest 30 ms, looped, which is what its pauses already sound like.
    hop = max(1, sr // 100); n = len(audio) // hop
    level = 20 * np.log10(np.sqrt((audio[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    quiet = level.min(); floor_at = int(np.argmin(np.convolve(level, np.ones(3) / 3, 'same')))
    floor = audio[max(0, floor_at * hop - hop):floor_at * hop + 2 * hop]
    if not len(floor): floor = np.zeros(hop * 3, 'float32')
    want = int(a.secs * sr); fade = int(.01 * sr); out, last = [], 0
    for i in at:
        lo = max(0, int((words[i].end - .25) * 100)); hi = min(n, max(lo + 1, int((words[i + 1].start + .25) * 100)))
        win = level[lo:hi]; still = win <= max(quiet + 20, level.max() - 45)
        if still.any():                                       # the middle of the longest quiet run near the break
            runs, k = [], 0
            while k < len(still):
                if still[k]:
                    j = k
                    while j < len(still) and still[j]: j += 1
                    runs.append((j - k, k, j)); k = j
                else: k += 1
            _, r0, r1 = max(runs); cut = (lo + (r0 + r1) // 2) * hop
        else: cut = (lo + int(np.argmin(win))) * hop          # no real pause: the quietest moment
        room = np.resize(floor, want).astype('float32')
        if len(room) > 2 * fade:
            ramp = np.linspace(0, 1, fade, dtype='float32'); room[:fade] *= ramp; room[-fade:] *= ramp[::-1]
        out += [audio[last:cut], room]; last = cut
    out.append(audio[last:]); new = np.concatenate(out)
    folder = c.path('takes', key)
    k = 1 + max([int(m[1]) for p in list(folder.glob('beat_*.wav')) + list(folder.glob('removed/beat_*.wav'))
                 if (m := re.fullmatch(r'beat_(\d+)', p.stem))] + [0])
    dst = folder / f'beat_{k}.wav'; sf.write(dst, new, sr, subtype='PCM_24')
    made = made_from(c, key).get(src.name, {})
    record_made(c, key, dst.name, made.get('text') or info['text'], made.get('ref'), made.get('shift'),
                target=made.get('target'), came=c.rel(src), beat=round(a.secs, 2),
                after=' / '.join(words[i].word.strip() for i in at))
    print(f'{key}: {dst.name}: {a.secs:.1f} s after {", ".join(repr(words[i].word.strip()) for i in at)} in {src.name}')


def cmd_choose(c, a):
    src = c.path('voices', a.voice, 'design', f'cand_{a.candidate}.wav')
    if not src.exists(): sys.exit(f'No {src}')
    promote(c, src, a.voice, a.emotion, src.with_suffix('.txt').read_text(encoding='utf-8'))


def promote(c, src, voice, emotion, text):
    dst = c.path('voices', voice, 'ref', emotion + '.wav'); dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        old = dst.with_name(f'{emotion}_{time.strftime("%Y%m%d-%H%M%S")}.wav'); workfiles.replace(dst, old)
        if dst.with_suffix('.json').exists(): workfiles.replace(dst.with_suffix('.json'), old.with_suffix('.json'))
        # Its transcript goes with it (until Nov 6 it was overwritten, so a kept reference lost the words Qwen reads).
        if dst.with_suffix('.txt').exists(): workfiles.replace(dst.with_suffix('.txt'), old.with_suffix('.txt'))
        print(f'  kept the old one as {old.name}')
    shutil.copy2(src, dst); dst.with_suffix('.txt').write_text(text.strip(), encoding='utf-8')
    workfiles.note_source(c.work, voice, src, dst)             # ref-source: which candidate or take it came from
    print(f'{voice}: {emotion} reference is now {Path(src).name}')


def cmd_promote(c, a):
    src = Path(a.take).expanduser()
    if not src.is_absolute(): src = c.path(a.take)
    if not src.exists(): sys.exit(f'No {src}')
    text = a.text
    if not text:   # a take: its line's words
        key = src.parent.name; row = next((r for r in c.lines() if r['key'] == key), None)
        if not row: sys.exit('Pass --text with what the clip says.')
        text = row['text']
    promote(c, src, a.voice, a.emotion, text)


# ------------------------------------------------------------------ your performances

def cmd_record(c, a):
    import numpy as np, sounddevice as sd, soundfile as sf
    sr = c.cfg['master']['sample_rate']; todo = keys_of(c, a)
    if a.missing: todo = [r for r in todo if not performances(c, r['key'])]
    if not todo: sys.exit('Nothing to record with those filters.')
    out = c.path('performances'); out.mkdir(exist_ok=True)
    print(f'{len(todo)} lines. Enter: record / stop.  p: play the last take.  r: redo it.  n: next line.  q: quit.\n')
    i = 0
    while i < len(todo):
        r = todo[i]; have = performances(c, r['key'])
        print(f'\n[{i + 1}/{len(todo)}] {r["key"]}  ({r["speaker"]}, {r["emotion"]})  takes so far: {len(have)}')
        if r['note']: print(f'  direction: {r["note"]}')
        print(f'\n    "{r["text"]}"\n')
        last = None
        while True:
            cmd = input('  > ').strip().lower()
            if cmd == 'q': return
            if cmd == 'n': i += 1; break
            if cmd == 'p' and last: d, s = sf.read(last); sd.play(d, s); sd.wait(); continue
            if cmd == 'r' and last: last.unlink(); print('  deleted'); last = None; continue
            if cmd == '':
                buf = []
                with sd.InputStream(samplerate=sr, channels=1, dtype='float32', callback=lambda d, *_: buf.append(d.copy())):
                    input('  recording... Enter to stop ')
                audio = np.concatenate(buf)[:, 0] if buf else np.zeros(1, 'float32')
                peak = float(np.abs(audio).max())
                n = workfiles.next_performance(out, r['key'])
                last = out / f'{r["key"]}_p{n}.wav'; sf.write(last, audio, sr, subtype='PCM_24')
                last.with_suffix('.txt').write_text(r['text'], encoding='utf-8')     # the words it was recorded with
                warn = '  (clipping: back off the mic)' if peak > .98 else '  (quiet: move closer)' if peak < .1 else ''
                print(f'  saved {last.name}, {len(audio) / sr:.1f} s{warn}')


def cmd_convert(c, a):
    vc_cfg = c.cfg['convert']; todo = [r for r in keys_of(c, a) if performances(c, r['key'])]
    if not todo: print('No performances to convert (record some with ● Record on the studio page).'); return
    seed = models.SeedVC(Path(os.path.expanduser(c.cfg['repos']['seed_vc'])), vc_cfg.get('diffusion_steps', 30),
                            c.cfg['repos'].get('seed_vc_python', ''))
    todo_vc, made_for = [], {}
    picked = {p['take'] for p in c.json('picks.json', {}).values()}
    for r in todo:
        # The voice to convert into: --ref names one of its references; otherwise the line's emotion, else neutral
        # (as text-to-speech picks). Measured: the reference matching the delivery beats several joined together.
        if a.ref:
            ref = c.path('voices', r['voice'], 'ref', a.ref + '.wav')
            if not ref.exists(): print(f'{r["key"]}: {r["voice"]} has no {a.ref} reference'); continue
        else: ref, _ = c.ref(r['voice'], r['emotion'])
        if not ref: print(f'{r["key"]}: {r["voice"]} has no reference voice yet (design + choose)'); continue
        shift = line_shift(c, r); cfg_rate = float(vc_cfg.get('cfg_rate', 0.7))
        out = c.path('takes', r['key']); out.mkdir(parents=True, exist_ok=True); made = made_from(c, r['key'])
        for p in performances(c, r['key']):
            if a.perf and p.stem != a.perf: continue
            words = p.with_suffix('.txt').read_text(encoding='utf-8').strip() if p.with_suffix('.txt').exists() else r['text']
            # Two takes per recording: "clone" (the timbre model: the voice's own sound and pitch, your timing and a
            # looser read of your intonation) and "pitch" (the pitch-following model: your intonation note for note,
            # moved by the line's pitch shift). Each with the voice's tuned model of that kind when it has one.
            for kind in vc_cfg.get('kinds', ['clone', 'pitch']):
                f0 = kind == 'pitch'; st = shift if f0 else 0; tuned = tuned_model(c, r['voice'], f0)
                newest = max(ref.stat().st_mtime, Path(tuned['checkpoint']).stat().st_mtime if tuned else 0)
                dst = out / f'vc_{p.stem}_{ref.stem}_{kind}{"_ft" if tuned else ""}.wav'
                # Up to date: newer than its performance, reference and model, and made at the line's pitch shift.
                if (dst.exists() and dst.stat().st_mtime > max(p.stat().st_mtime, newest)
                        and made.get(dst.name, {}).get('shift') == st): continue
                # Cleared away (🧹 or ✕): not remade unless its recording, reference, model or shift changed since.
                gone = out / 'removed' / dst.name
                if (not dst.exists() and gone.exists() and gone.stat().st_mtime > max(p.stat().st_mtime, newest)
                        and workfiles.removed_made(out).get(dst.name, {}).get('shift') == st): continue
                # A picked take is never remade under its name (a new reference, shift or retrain would): the pick
                # would change sound without anyone hearing it.
                if dst.exists() and f'takes/{r["key"]}/{dst.name}' in picked: print(f'  {dst.name}: picked, kept as it is'); continue
                todo_vc.append((p, ref, dst, cfg_rate, st, f0, tuned)); made_for[str(dst)] = (r['key'], words, ref, st)
    if todo_vc:
        who = sorted({r['voice'] for r in todo if tuned_model(c, r['voice'], True) or tuned_model(c, r['voice'], False)})
        print(f'{len(todo_vc)} conversions with Seed-VC{" (tuned: " + ", ".join(who) + ")" if who else ""}...', flush=True)
    made = seed.convert(todo_vc)
    for dst in made:
        key, words, ref, shift = made_for[dst]; record_made(c, key, Path(dst).name, words, ref, shift)
    print(f'{len(made)} conversions made.')


def tuned_model(c, voice, f0):
    """A voice's fine-tuned Seed-VC model of one kind ({checkpoint, config, f0, ...}): the pitch-following model (f0)
    for its "pitch" takes, the timbre model for its "clone" takes. None: the base model."""
    return workfiles.seedvc_model(c.work, voice, f0)


def line_shift(c, r):
    """The semitones a line's "pitch" takes move your voice by: the line's own (its card, directions.toml), else its
    voice's (the Cast tab, cast.toml)."""
    own = str(r.get('pitch_shift') or '').strip()
    return int(own) if own else int(c.voice_cfg(r['voice']).get('pitch_shift', 0) or 0)


def cmd_train(c, a):
    """Fine-tunes Seed-VC on one voice, from its references and its good takes (workfiles.training_clips), so your
    performances convert into it closer to the voice and with a little less warble (measured on one voice: voice match
    0.74 -> 0.86, PESQ 2.93 -> 3.1-3.2, and preferred by ear). It tunes both models your recordings convert
    with (--kind: one of them): the timbre model for their "clone" takes, then the pitch-following one for their
    "pitch" takes. Each starts fresh from its base model and keeps the model it replaces. Saved in
    <work_dir>/voices/<voice>/seedvc/<clone|pitch>/; `verbaline convert` then uses them."""
    v = a.voice
    if v not in c.cast.get('voices', {}): sys.exit(f'No voice "{v}" in cast.toml')
    clips = workfiles.training_clips(c.work, v); mins = sum(s for _, s in clips) / 60
    if mins < 1: sys.exit(f'{v}: only {mins:.1f} min of clean clips (its references and takes with the words right). '
                          'Seed-VC needs a minute at least, 3+ is better: generate more takes first.')
    seed = models.SeedVC(Path(os.path.expanduser(c.cfg['repos']['seed_vc'])), python=c.cfg['repos'].get('seed_vc_python', ''))
    kinds = [a.kind] if a.kind else ['clone', 'pitch']
    for kind in kinds:
        if not seed.base(kind == 'pitch'):
            sys.exit(f'Seed-VC\'s base model {models.SeedVC.MODELS[kind == "pitch"][0]} is not in {seed.repo}/checkpoints')
    data = c.path('voices', v, 'seedvc', 'data')
    if data.exists(): shutil.rmtree(data)                    # fresh data
    data.mkdir(parents=True)
    for p, _ in clips:                                       # hard links: no copies of the audio
        dst = data / f'{p.parent.name}_{p.name}'
        try: os.link(p, dst)
        except OSError: shutil.copy2(p, dst)
    for kind in kinds: train_model(c, a, seed, v, kind, data, clips, mins)
    shutil.rmtree(data)
    print(f'{v}: your performances convert into {v} with its tuned {" and ".join(kinds)} model{"s" if len(kinds) > 1 else ""} now; '
          '"convert again" redoes a line.', flush=True)


def train_model(c, a, seed, v, kind, data, clips, mins):
    """One of a voice's tuned models (verbaline train): kind "clone" (the timbre model) or "pitch" (the pitch-following
    one), fresh from Seed-VC's base checkpoint, installed in voices/<voice>/seedvc/<kind>/."""
    import collections
    t = c.cfg.get('train', {}); steps = a.steps or int(t.get('steps', 600)); batch = int(t.get('batch_size', 4))
    f0 = kind == 'pitch'; base = seed.base(f0); preset = models.SeedVC.MODELS[f0][1]
    d = c.path('voices', v, 'seedvc', kind); d.mkdir(parents=True, exist_ok=True); run = seed.repo / 'runs' / f'vs_{v}_{kind}'
    if run.exists(): shutil.rmtree(run)                      # fresh from the base model
    print(f'{v}: tuning the {"pitch-following" if f0 else "timbre"} model ("{kind}" takes) on {len(clips)} clips '
          f'({mins:.1f} min{", thin: 3+ min is better" if mins < 3 else ""}), {steps} steps...', flush=True)
    cmd = [seed.python, 'train.py', '--config', f'configs/presets/{preset}', '--pretrained-ckpt', str(base),
           '--dataset-dir', str(data), '--run-name', run.name, '--batch-size', str(batch), '--max-steps', str(steps),
           '--max-epochs', '100000', '--save-every', str(steps + 1), '--num-workers', '0']
    slot = Path(os.path.expanduser(t.get('gpu_slot', '')))   # a GPU-slot script ([train] gpu_slot), so another GPU job can't run it out of memory
    if t.get('gpu_slot') and slot.exists():
        if os.name == 'nt' and slot.suffix.lower() not in ('.exe', '.bat', '.cmd'):
            print(f'  [train] gpu_slot is {slot.name}, which Windows can\'t run: training without it', flush=True)
        else: cmd = [str(slot), '--need', '10000', *cmd]
    env = dict(os.environ, HF_HUB_CACHE='./checkpoints/hf_cache', HF_HUB_OFFLINE='1')
    t0 = time.time(); tail = collections.deque(maxlen=25)
    p = subprocess.Popen(cmd, cwd=seed.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding='utf-8', errors='replace')
    for raw in p.stdout:
        for line in filter(None, (x.strip() for x in raw.split('\r'))):
            tail.append(line)
            if line.startswith('Failed to load any checkpoint'):  # it would train from nothing: useless in minutes
                p.kill(); sys.exit(f'{v}: Seed-VC could not load its base model, so nothing was trained.')
            if line.startswith('gpu_slot:'): print('  ' + line, flush=True)   # waiting for the GPU behind other jobs
            m = re.search(r'epoch \d+, step (\d+), loss: ([\d.]+)', line)   # often behind a progress bar on one line
            if m and int(m.group(1)) % 100 == 0: print(f'  step {m.group(1)} of {steps}, loss {float(m.group(2)):.3f}', flush=True)
    made = run / 'ft_model.pth'
    if p.wait() or not made.exists(): sys.exit(f'{v}: training failed (exit {p.returncode}):\n' + '\n'.join(tail))
    if (d / 'model.pth').exists():                           # the model it replaces stays, one back
        (d / 'previous').mkdir(exist_ok=True)
        for f in ('model.pth', 'config.yml', 'model.json'):
            if (d / f).exists(): workfiles.replace(d / f, d / 'previous' / f)
    shutil.move(made, d / 'model.pth'); shutil.copy2(run / preset, d / 'config.yml'); shutil.rmtree(run)
    (d / 'model.json').write_text(json.dumps(dict(f0=f0, steps=steps, clips=len(clips), minutes=round(mins, 1),
                                                  trained=time.strftime('%Y-%m-%d %H:%M'), secs=round(time.time() - t0)), indent=1), encoding='utf-8')
    print(f'{v}: tuned {kind} model saved ({(time.time() - t0) / 60:.0f} min).', flush=True)


def cmd_tts(c, a):
    regen = set(c.json('regen.json', [])); picks = c.json('picks.json', {})
    rows = keys_of(c, a)
    if a.regen: rows = [r for r in rows if r['key'] in regen]
    # Lines you've acted are voiced from your performance; text-to-speech fills the rest (or adds to them with --all).
    if not a.all and not a.regen: rows = [r for r in rows if not performances(c, r['key'])]
    if not a.backend and not a.engine:
        # Each voice uses its own engine (cast.toml), and each engine runs in its own environment: one run per engine.
        need = sorted({c.line_engine(r) for r in rows})
        args = [x for x in sys.argv[2:]]
        failed = [e for e in need if subprocess.run([sys.executable, __file__, 'tts', *args, '--engine', e]).returncode]
        if failed: sys.exit(f'text-to-speech failed for: {", ".join(failed)}')
        return
    if a.engine: rows = [r for r in rows if c.line_engine(r) == a.engine]
    if not rows: return
    n = a.takes or c.cfg['tts']['takes']; backend = a.backend or a.engine
    with models.backend(backend, c) as tts:
        needs_ref = getattr(tts, 'needs_ref', True)
        for r in rows:
            if r.get('parts'):                        # ✂ a line in parts: each part made on its own, then joined
                try: made = tts_parts(c, a, tts, backend, needs_ref, r, n)
                except ValueError as e: print(f'{r["key"]}: its parts can\'t be read ({e}): fix them on its card'); continue
                if made: regen.discard(r['key'])
                continue
            # The reference: --ref names one (any of the voice's references); otherwise the line's emotion, else neutral.
            if a.ref:
                ref = c.path('voices', r['voice'], 'ref', a.ref + '.wav')
                if needs_ref and not ref.exists(): print(f'{r["key"]}: {r["voice"]} has no {a.ref} reference'); continue
                t = ref.with_suffix('.txt'); ref_text = t.read_text(encoding='utf-8').strip() if t.exists() else ''
            else: ref, ref_text = c.ref(r['voice'], r['emotion'])
            if needs_ref and not ref: print(f'{r["key"]}: {r["voice"]} has no reference voice yet (design + choose)'); continue
            out = c.path('takes', r['key']); out.mkdir(parents=True, exist_ok=True)
            have = len(list(out.glob(f'{backend}_*.wav')))
            want = n if (a.regen or a.more or (have == 0 and r['key'] not in picks)) else 0   # a picked line has what it needs
            t0 = time.time(); k0 = workfiles.next_take_number(out, backend)
            for k in range(k0, k0 + want):
                tts.say(r['say'], ref, ref_text, r['emotion'], c.voice_cfg(r['voice']), out / f'{backend}_{k}.wav', seed=k)
                record_made(c, r['key'], f'{backend}_{k}.wav', r['text'], ref if needs_ref else None)
            if want: print(f'{r["key"]}: {want} takes ({backend}, {(time.time() - t0) / want:.1f} s each)')
            regen.discard(r['key'])
    c.save_json('regen.json', sorted(regen))


def tts_parts(c, a, tts, backend, needs_ref, r, n):
    """✂ A line in parts (lineparts.py): n new tries of each part, each cloning the voice's reference for the part's
    tone, then n whole takes, try k of every part joined (parts_<j>.wav). With --part, only that part gets new tries,
    each joined with the other parts' mix (their chosen try, else their newest), so every try is heard in its place. A
    part with no tries yet always gets them. Returns whether anything was made."""
    parts = lineparts.parse(r['parts'], r['emotion'])
    have = {lineparts.part_id(r['voice'], p): lineparts.tries(c.work, r['key'], lineparts.part_id(r['voice'], p)) for p in parts}
    whole = list(c.path('takes', r['key']).glob('parts_*.wav'))
    if a.part and a.part not in have: print(f'{r["key"]}: no part {a.part} (its parts changed?)'); return False
    if not (a.regen or a.more or not whole): n = 0             # it has takes: only parts without tries get some
    fresh = {}
    t0 = time.time(); made = 0
    for p in parts:
        pid = lineparts.part_id(r['voice'], p)
        want = n if (not a.part or pid == a.part) else 0
        if not have[pid]: want = max(want, n or a.takes or c.cfg['tts']['takes'])
        if not want: continue
        ref, ref_text = c.ref(r['voice'], p['tone'])
        if needs_ref and not ref: print(f'{r["key"]}: {r["voice"]} has no reference voice yet (design + choose)'); return False
        if needs_ref and ref.stem != p['tone']:
            print(f'{r["key"]}: {r["voice"]} has no {p["tone"]} reference: its {p["tone"]} part clones {ref.stem}')
        d = lineparts.folder(c.work, r['key'], pid); d.mkdir(parents=True, exist_ok=True)
        k0 = 1 + max([int(m[1]) for x in d.glob(f'{backend}_*.wav') if (m := re.fullmatch(re.escape(backend) + r'_(\d+)', x.stem))] + [0])
        text = tts_text(p['text'], c.say)
        for k in range(k0, k0 + want):
            out = d / f'{backend}_{k}.wav'
            tts.say(text, ref, ref_text, p['tone'], c.voice_cfg(r['voice']), out, seed=k)
            lineparts.note_try(c.work, r['key'], pid, out.name, text=p['text'], tone=p['tone'], engine=backend,
                              ref=Path(ref).stem if needs_ref and ref else '')
            fresh.setdefault(pid, []).append(out); made += 1
    if not fresh: return False
    # Whole takes: the k-th new try of each part that has new ones, with the mix's choice for the rest.
    joins = max(len(v) for v in fresh.values()); out = []
    for j in range(joins):
        picks = {pid: str(v[min(j, len(v) - 1)]) for pid, v in fresh.items()}
        out.append(lineparts.join_line(c, r, picks).name)
    print(f'{r["key"]}: {made} part tries ({backend}, {(time.time() - t0) / made:.1f} s each), joined into {", ".join(out)}')
    return True


def cmd_score(c, a):
    sc = c.cfg['score']; rows = keys_of(c, a)
    def take_ref(r, t, made):
        """The clip a take's voice is judged against: the clip whose voice a restyle or a mirror gave it, else the
        reference it was cloned from, else the voice's default one."""
        tgt = made.get(t.name, {}).get('target')
        if tgt and c.path(tgt).exists(): return c.path(tgt)
        w = c.path('voices', r['voice'], 'ref', made.get(t.name, {}).get('ref', '') + '.wav')
        return w if made.get(t.name, {}).get('ref') and w.exists() else c.ref(r['voice'])[0]
    def stale(r, t, done, made):
        d = done.get(t.name, {}); ref = take_ref(r, t, made)
        return d.get('v') != SCORE_VERSION or d.get('mtime') != t.stat().st_mtime or not same_words(d.get('text'), r['text']) \
            or d.get('ref') != (ref.name if ref else None) or d.get('ref_mtime') != (ref.stat().st_mtime if ref else None)
    def unscored(r):
        f = c.path('takes', r['key'], 'scores.json'); done = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
        made = made_from(c, r['key'])
        return [t for t in takes(c, r['key']) if stale(r, t, done, made)]
    rows = [r for r in rows if unscored(r)]
    if not rows: print('Nothing new to score.'); return
    # Respelled names are forgiven both as written and as spoken ("Ls" and "L S").
    forgive = set(c.say) | {w for v in c.say.values() for w in models.words(v)}
    with models.Scorer(sc['whisper_model']) as s:
        for r in rows:
            folder = c.path('takes', r['key']); found = takes(c, r['key'])
            if not found: continue
            scores = c.json(c.rel(folder / 'scores.json'), {}) if (folder / 'scores.json').exists() else {}
            made = made_from(c, r['key']); new = 0
            for t in found:
                # Rescored when the take, its words, or the reference it's judged against changes.
                if t.name in scores and not stale(r, t, scores, made): continue
                ref = take_ref(r, t, made)
                # A line's own "say it as" respells words too: those are forgiven as written and as spoken.
                own = set(models.words(r['say_override'])) ^ set(models.words(r['text'])) if r.get('say_override') else set()
                res = s.score(t, r['text'], ref, forgive | own)
                res['mtime'] = t.stat().st_mtime; res['text'] = r['text']
                res['ref'] = ref.name if ref else None; res['ref_mtime'] = ref.stat().st_mtime if ref else None
                res['v'] = SCORE_VERSION
                # Extra or wrong words at the very start or end (e.g. a reference's last words leaking in) can hide
                # under the word-error limit on a long line: such a take is capped at 0.5 and says why.
                _, start, end = ref_mismatch(r['text'], res['heard'])
                res['edges'] = start > .5 or end > .5
                res['total'] = 0.0 if res['wer'] > sc['max_wer'] else round(
                    sc['weight_words'] * (1 - res['wer']) + sc['weight_voice'] * res['voice'] + sc['weight_quality'] * res['quality'], 4)
                if res['edges']: res['total'] = min(res['total'], .5)
                scores[t.name] = res; new += 1
            for gone in set(scores) - {t.name for t in found}: del scores[gone]
            (folder / 'scores.json').write_text(json.dumps(scores, indent=1), encoding='utf-8')
            if new: print(f'{r["key"]}: scored {new}, best {max(v["total"] for v in scores.values()):.2f}')


def cmd_run(c, a):
    """convert, tts and score in turn, each as its own run (so each can use its own environment)."""
    flt = [x for k in ('voice', 'group', 'line') if getattr(a, k) is not None for x in ('--' + k, str(getattr(a, k)))]
    tts = flt + (['--takes', str(a.takes)] if a.takes else []) + (['--backend', a.backend] if a.backend else []) \
        + (['--regen'] if a.regen else []) + (['--all'] if a.all else [])
    for step, extra in (('convert', flt), ('tts', tts), ('score', flt)):
        print(f'== {step}'); subprocess.run([sys.executable, __file__, step, *extra], check=False)


# ------------------------------------------------------------------ the picks, cleaned up and exported

def cmd_master(c, a):
    import numpy as np, soundfile as sf, pyloudnorm, scipy.signal as sig
    m = c.cfg['master']; lang = a.lang or c.lang; sr_out = m['sample_rate']
    picks = c.json('picks.json', {}); out = c.path('export', lang); out.mkdir(parents=True, exist_ok=True)
    rows = c.lines(); done = 0
    for key, pick in picks.items():
        src = c.path(pick['take'])
        if not src.exists(): print(f'{key}: picked take is gone ({pick["take"]})'); continue
        targets = [out / c.export_name(r) for r in rows if r['key'] == key]
        row = next((r for r in rows if r['key'] == key), None); was = made_from(c, key).get(src.name, {}).get('text')
        if row and was and not any(same_words(was, x) for x in (row['text'], row['say'], row.get('say_override'))):   # a respelling isn't new words
            print(f'{key}: the picked take says the old words ("{was[:60]}"); pick or make a take of the new ones')
        if all(t.exists() and t.stat().st_mtime > src.stat().st_mtime for t in targets) and not a.force: continue
        x, sr = sf.read(src, always_2d=True); x = x.mean(axis=1)
        if sr != sr_out:
            g = np.gcd(sr, sr_out); x = sig.resample_poly(x, sr_out // g, sr // g); sr = sr_out
        x = sig.sosfilt(sig.butter(4, m['highpass_hz'], 'highpass', fs=sr, output='sos'), x)
        # Trim to the words: frames 40 dB under the loudest, with a little air either side.
        f = int(sr * .01); rms = np.sqrt(np.convolve(x ** 2, np.ones(f) / f, 'same')) + 1e-9
        db = 20 * np.log10(rms); on = np.where(db > max(db.max() - 40, -60))[0]
        if len(on): pad = int(sr * m['pad_ms'] / 1000); x = x[max(0, on[0] - pad):on[-1] + pad]
        fade = int(sr * .005); x[:fade] *= np.linspace(0, 1, fade); x[-fade:] *= np.linspace(1, 0, fade)
        meter = pyloudnorm.Meter(sr)
        try: x = pyloudnorm.normalize.loudness(x, meter.integrated_loudness(x), m['loudness_lufs'])
        except ValueError: pass     # too short to measure: leave its level
        peak = np.abs(x).max(); ceiling = 10 ** (m['peak_dbfs'] / 20)
        if peak > ceiling: x *= ceiling / peak
        for t in targets: sf.write(t, x.astype('float32'), sr, subtype='PCM_24')
        done += len(targets)
    print(f'{done} files written to {out}.' + ('' if getattr(a, 'from_apply', False) else ' `verbaline apply` hands them to the project.'))


def cmd_clear_takes(c, a):
    """Moves the takes a group's (or the chosen lines') picks don't use into each line's removed/ folder."""
    if not (a.group or a.line or a.keys): sys.exit('Say which lines: --group, --line or --keys.')
    keys = list(dict.fromkeys(r['key'] for r in c.lines() if (not a.group or str(r.get('group', '')) == a.group)
                              and (not a.line or a.line in (r['id'], r['key'])) and (not a.keys or r['key'] in a.keys.split(','))
                              and (not a.voice or r['voice'] == a.voice)))
    if not keys: sys.exit('No lines match.')
    total = kept_lines = 0
    for key in keys:
        picks = c.json('picks.json', {}); tweaks = c.json('tweaks.json', {})      # read per line: the page may pick meanwhile
        pick = picks.get(key, {}).get('take', '')
        move, keep = workfiles.clear_plan(c.work, key, pick, set(tweaks.get(key, {})), a.unpicked_lines, a.before)
        if not pick and not a.unpicked_lines:
            if keep: kept_lines += 1
            continue
        if a.dry_run: moved = move
        else:
            def still(k=key):          # what must stay, read again before each move: a pick or prompt made meanwhile counts
                p = c.json('picks.json', {}).get(k, {}).get('take', ''); return {p, *c.json('tweaks.json', {}).get(k, {})}
            moved = workfiles.remove_takes(c.work, key, move, still)
        if moved:
            total += len(moved)
            print(f'{key}: {len(moved)} take{"s" * (len(moved) != 1)} {"would go" if a.dry_run else "moved"} to removed/'
                  + (f', kept {", ".join(Path(x).stem for x in keep)}' if keep else ''), flush=True)
    left = f'; {kept_lines} line{"s" * (kept_lines != 1)} without a pick left alone' if kept_lines else ''
    print(f'{total} take{"s" * (total != 1)} {"would move" if a.dry_run else "moved"} to takes/<line>/removed/ (recoverable){left}')


def cmd_tweaks(c, a):
    """The director's prompts from the page: takes they like, and what the next round of takes for that line should change.
    Each next take should start from the liked take (same backend, reference and settings) and follow the prompt."""
    tweaks = c.json('tweaks.json', {}); rows = {r['key']: r for r in c.lines()}; n = 0
    for key, by_take in sorted(tweaks.items()):
        r = rows.get(key)
        if a.voice and (not r or r['voice'] != a.voice): continue
        print(f'{key}  ({r["speaker"] if r else "?"}, {r["voice"] if r else "?"}): "{r["text"] if r else ""}"')
        for take, t in sorted(by_take.items()):
            print(f'  {take}  [{t["at"]}]\n    -> {t["prompt"]}'); n += 1
    print(f'{n} prompts' + ('' if n else ' (write them in the audition page: http://localhost:8765)'))


def cmd_apply(c, a):
    """Apply: the picks into the game. Masters every pick the game doesn't have yet into <work>/export/<lang>/, writes
    the manifest there (every picked line: its file, words, speaker, group, take and length), then hands it to the
    project (its apply hook, or [apply] command / copy_to: project.py). Afterwards it records what was applied
    (<work>/applied.json), which is what the page compares against when the project has no game_state hook. Each step's
    output goes to <work>/logs/apply_<time>_<step>.log."""
    logs = c.path('logs'); logs.mkdir(exist_ok=True); stamp = time.strftime('%Y%m%d-%H%M%S')
    def run(label, argv, expect=None, timeout=900, cwd=None):
        """Runs one step of the project's Apply in its root (or cwd), logged; stops Apply when it fails, or when its
        output lacks `expect`. Returns its output."""
        print(f'{label}...', flush=True); t0 = time.time()
        log = logs / f'apply_{stamp}_{re.sub(r"[^a-z0-9]+", "_", label.lower())[:40]}.log'
        try: r = subprocess.run([str(x) for x in argv], cwd=cwd or c.project.root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout); out, rc = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired as e: out, rc = f'{e.stdout or ""}{e.stderr or ""}\ntimed out after {timeout} s', -1
        except OSError as e: out, rc = f'could not start {argv[0]}: {e}', -1
        log.write_text(out, encoding='utf-8')
        if rc or (expect and expect not in out):
            sys.exit(f'{label} failed (exit {rc}). Log: {log}\n' + '\n'.join(out.strip().splitlines()[-10:]))
        print(f'  done in {time.time() - t0:.0f} s', flush=True)
        return out
    rows = c.lines(); picks = c.json('picks.json', {})
    # Re-master the picks the game doesn't have yet, so a re-pick of an older take can't ride on the newer export of
    # the take it replaces.
    _, have = c.project.game_state(c)
    new = {k: p['take'] for k, p in picks.items() if (have or {}).get(k) != p['take']}
    for r in rows:
        if r['key'] in new: c.path('export', c.lang, c.export_name(r)).unlink(missing_ok=True)
    # A pick whose take is gone can't reach the game: it's left out (and not recorded as applied) and Apply fails at the
    # end, after handing over the rest, so the page keeps saying the game lacks it.
    missing = sorted(k for k, p in picks.items() if not c.path(p['take']).is_file())
    a.lang, a.force, a.from_apply = None, False, True; cmd_master(c, a)
    manifest = projects.write_manifest(c, rows, picks, c.path('export', c.lang), c.export_name)
    print(f'Manifest: {manifest} ({len(json.loads(manifest.read_text(encoding="utf-8"))["lines"])} lines)', flush=True)
    c.no_test = bool(getattr(a, 'no_test', False))           # --no-test: the project may skip its own checks
    c.project.apply(c, manifest, run)
    c.save_json('applied.json', dict(at=time.strftime('%Y-%m-%d %H:%M:%S'), words={r['id']: r['text'] for r in rows},
                                     picks={k: p['take'] for k, p in picks.items() if k not in missing}))
    print(f'{c.project.name} has the current words and {len(picks) - len(missing)} picks ({len(set(new) - set(missing))} new).', flush=True)
    if missing: sys.exit(f'{len(missing)} pick(s) name a take that is gone, so the game doesn\'t have them: {", ".join(missing)}. Pick again.')


def ref_mismatch(have, heard):
    """How far a transcript is from what Whisper heard: (overall, first three words, last three words), each as the
    share of letters that differ (spelling, spacing and gonna/going to don't count)."""
    def letters(x): return re.sub(r'[^a-z]', '', x.lower().replace('gonna', 'goingto').replace('wanna', 'wantto').replace('gotta', 'gotto'))
    def lev(x, y):
        d = list(range(len(y) + 1))
        for i, ch in enumerate(x, 1):
            prev, d[0] = d[0], i
            for j, ch2 in enumerate(y, 1): prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ch != ch2))
        return d[-1]
    def rate(x, y): x, y = letters(x), letters(y); return lev(x, y) / max(1, len(x))
    hw, rw = re.findall(r"[A-Za-z']+", have), re.findall(r"[A-Za-z']+", heard)
    return rate(have, heard), rate(' '.join(hw[:3]), ' '.join(rw[:3])), rate(' '.join(hw[-3:]), ' '.join(rw[-3:]))


def cmd_refcheck(c, a):
    """Checks every reference clip's transcript against what's actually in the audio (Whisper), and fixes the ones
    that don't match. Qwen3-TTS cloning reads a reference's audio and transcript as one continuous recording and then
    goes on to the new line: when the transcript is wrong, the leftover words leak into every take (once, one voice's
    urgent reference ended "...our main hangar" but its transcript said "...the hangar", so takes began "The hangar").
    The old transcript is kept as <emotion>.txt.was."""
    import torch  # noqa: F401  (loads the CUDA libraries faster-whisper needs)
    from faster_whisper import WhisperModel
    asr = WhisperModel(c.cfg['score']['whisper_model'], device='cuda', compute_type='float16')
    voices = [a.voice] if a.voice else sorted(c.cast.get('voices', {})); fixed = checked = 0
    for v in voices:
        d = c.path('voices', v, 'ref')
        for w in sorted(d.glob('*.wav')) if d.exists() else []:
            if w.stem not in EMOTIONS or (a.emotion and w.stem != a.emotion): continue
            t = w.with_suffix('.txt'); have = t.read_text(encoding='utf-8').strip() if t.exists() else ''
            segs, _ = asr.transcribe(str(w), language='en', beam_size=5)
            heard = ' '.join(s.text.strip() for s in segs).strip(); checked += 1
            whole, start, end = ref_mismatch(have, heard)
            # Whisper writes "gonna" as "going to", "Firebrand" as "fire brand": compare letters, and only rewrite a
            # transcript that's really off, overall or at either end (where leaked words come from).
            if not have or whole > a.tolerance or start > .3 or end > .3:
                if have: t.with_suffix('.txt.was').write_text(have, encoding='utf-8')
                t.write_text(heard, encoding='utf-8'); fixed += 1
                print(f'{v} {w.stem}: transcript fixed ({whole:.0%} different; start {start:.0%}, end {end:.0%})'
                      f'\n  was:   {have}\n  heard: {heard}')
    print(f'{checked} references checked, {fixed} transcripts fixed.')


def cmd_serve(c, a):
    from verbaline import server
    server.serve(c, a.port or int(c.cfg['project'].get('port', 8765)), lambda: cmd_lines(c, a))


def utf8_everywhere():
    """Windows defaults text to its code page (cp1252 and friends), which can't hold the studio's words or symbols:
    its own output, and every Python it starts (jobs, model environments, runners, an Apply command), use UTF-8."""
    os.environ.setdefault('PYTHONUTF8', '1'); os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    for s in (sys.stdout, sys.stderr):
        if s and s.encoding.lower().replace('-', '') != 'utf8': s.reconfigure(encoding='utf-8', errors='replace')


def main():
    utf8_everywhere()
    p = argparse.ArgumentParser(prog='verbaline', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--project', help='the project\'s folder (its verbaline.toml); default: $VERBALINE_PROJECT, '
                                     'else the nearest verbaline.toml from here up')
    sub = p.add_subparsers(dest='cmd', required=True)
    def add(name, fn, *flags):
        s = sub.add_parser(name); s.set_defaults(fn=fn)
        for f in flags:
            if f == 'filters':
                s.add_argument('--voice'); s.add_argument('--group', '--mission', dest='group', help='only this group (a mission, a scene)'); s.add_argument('--line')
                s.add_argument('--keys', help='only these clip keys (comma separated)')
                s.add_argument('--todo', action='store_true', help='only lines without a pick')
        return s
    add('lines', cmd_lines)
    add('status', cmd_status).add_argument('--voice')
    s = add('design', cmd_design); s.add_argument('--voice'); s.add_argument('--n', type=int, default=6)
    s.add_argument('--retry', type=int, metavar='N', help='candidate N\'s voice reading other words, as a new candidate')
    s.add_argument('--text', help='with --retry: the words (default: the voice\'s audition text)')
    s = add('preview', cmd_preview); s.add_argument('--voice', required=True); s.add_argument('--candidate', type=int, required=True)
    s.add_argument('--backend', default='qwen')
    s = add('restyle', cmd_restyle); s.add_argument('--voice', help='the voice (or --line: its voice)')
    s.add_argument('--line', help='restyle this line: new takes of it, from its voice\'s neutral reference (or --from one of its takes)')
    s.add_argument('--from', help='the candidate, reference or take to restyle (its path in the work folder)')
    s.add_argument('--engine', choices=('qwen', 'editx'), default='qwen',
                   help='qwen: Qwen3-TTS acts --style, Seed-VC keeps the voice; editx: Step-Audio-EditX edits the clip (--recipe)')
    s.add_argument('--style', help='how it should be read, in words (qwen), e.g. "angry, shouting over alarms"')
    s.add_argument('--recipe', help='Step-Audio-EditX edits in turn (editx), e.g. "emotion:coldness, style:murmur"')
    s.add_argument('--text', help='what it reads (candidates; default: the voice\'s audition text)')
    s.add_argument('--emotion', choices=EMOTIONS, help='the emotion it is meant for (the page offers it first in "Use as")')
    s.add_argument('--n', type=int, default=2, help='how many to keep'); s.add_argument('--tries', type=int, default=6)
    s.add_argument('--raw', action='store_true', help='qwen: keep Seed-VC\'s conversion as it is, not read again cleanly')
    s.add_argument('--dir', default=time.strftime('%Y%m%d-%H%M%S'), help='its working folder under design/restyle/')
    s = add('restyle-keep', cmd_restyle_keep); s.add_argument('--voice', required=True); s.add_argument('--dir', required=True)
    s = add('mirror', cmd_mirror)
    s.add_argument('--from', required=True, help='the take, candidate, reference or recording whose delivery is kept')
    s.add_argument('--into', required=True, help='the reference or candidate whose voice it gets')
    s.add_argument('--line', help='new takes of this line (else: new candidates of the target\'s voice)')
    s.add_argument('--kinds', default='clone,pitch', help='clone (timbre model), pitch (pitch-following model), or both')
    s.add_argument('--shift', default='auto', help='semitones for the pitch kind (auto: between the two voices\' everyday pitch)')
    s = add('beat', cmd_beat); s.add_argument('--take', required=True, help='the take (its path in the work folder)')
    s.add_argument('--secs', type=float, default=0.6, help='how long the beat is')
    s.add_argument('--after-word', help='after this word (default: after each sentence)')
    s.add_argument('--nth', type=int, default=1, help='with --after-word: which time it comes')
    s = add('choose', cmd_choose); s.add_argument('--voice', required=True); s.add_argument('--candidate', type=int, required=True)
    s.add_argument('--emotion', default='neutral', choices=EMOTIONS)
    s = add('promote', cmd_promote); s.add_argument('take'); s.add_argument('--voice', required=True)
    s.add_argument('--emotion', required=True, choices=EMOTIONS); s.add_argument('--text')
    s = add('record', cmd_record, 'filters'); s.add_argument('--missing', action='store_true')
    s = add('convert', cmd_convert, 'filters')
    s.add_argument('--ref', choices=EMOTIONS, help='convert into this reference (default: the line\'s emotion, else neutral)')
    s.add_argument('--perf', help='only this performance (e.g. intro_hello_p3)')
    s = add('train', cmd_train); s.add_argument('--voice', required=True)
    s.add_argument('--kind', choices=('clone', 'pitch'), help='tune only this model (default: both)')
    s.add_argument('--steps', type=int, help='training steps (default: [train] steps in the config)')
    s = add('tts', cmd_tts, 'filters'); s.add_argument('--takes', type=int); s.add_argument('--backend')
    s.add_argument('--regen', action='store_true', help='only the lines flagged for new takes in the audition')
    s.add_argument('--all', action='store_true', help='also lines you have performed')
    s.add_argument('--more', action='store_true', help='add --takes new takes even to lines that have some')
    s.add_argument('--ref', choices=EMOTIONS, help='clone this reference (default: the line\'s emotion, else neutral)')
    s.add_argument('--engine', help=argparse.SUPPRESS)   # internal: only the lines whose voice uses this engine
    s.add_argument('--part', help='a line in parts: new tries of only this part (its id, e.g. sad_1a2b3c4d)')
    add('score', cmd_score, 'filters')
    s = add('run', cmd_run, 'filters'); s.add_argument('--takes', type=int); s.add_argument('--backend')
    s.add_argument('--regen', action='store_true'); s.add_argument('--all', action='store_true')
    s = add('serve', cmd_serve); s.add_argument('--port', type=int, help='default: verbaline.toml [project] port, else 8765')
    s = add('audition', cmd_serve); s.add_argument('--port', type=int, help=argparse.SUPPRESS)   # its old name
    s = add('clear-takes', cmd_clear_takes, 'filters')
    s.add_argument('--unpicked-lines', action='store_true', help='also lines with no pick yet (all their takes)')
    s.add_argument('--dry-run', action='store_true', help='only say what would move')
    s.add_argument('--before', type=float, help='only takes made before this time (seconds since 1970): the page passes when you confirmed')
    add('tweaks', cmd_tweaks).add_argument('--voice')
    s = add('refcheck', cmd_refcheck); s.add_argument('--voice'); s.add_argument('--emotion', choices=EMOTIONS)
    s.add_argument('--tolerance', type=float, default=0.05, help='share of letters off above which a transcript is rewritten')
    s = add('apply', cmd_apply); s.add_argument('--no-test', action='store_true', help='ask the project to skip its own checks (c.no_test)')
    s = add('master', cmd_master); s.add_argument('--lang'); s.add_argument('--force', action='store_true')
    a = p.parse_args(); c = Ctx(a.project)
    reexec(c, a)
    a.fn(c, a)


def reexec(c, a):
    """Runs a model job in its own virtual environment ([envs] in the config) when one is set."""
    env = {'design': 'qwen', 'restyle': 'qwen', 'restyle-keep': 'score', 'mirror': 'score', 'beat': 'score', 'score': 'score',
           'refcheck': 'score'}.get(a.cmd)
    if a.cmd == 'restyle' and a.engine == 'editx': env = None       # Step-Audio-EditX runs in its own Python (editx_run.py)
    if a.cmd == 'tts': env = a.backend or a.engine
    if a.cmd == 'preview': env = a.backend
    if env == 'xai': env = None                                  # a web request: runs anywhere
    python = os.path.expanduser(c.cfg.get('envs', {}).get(env, '') if env else '')
    # Compare without resolving symlinks: every venv's python links to the same base interpreter.
    same = lambda a, b: os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))   # C:\ vs c:/ on Windows
    if python and not same(python, sys.executable):
        if not os.path.isfile(python):
            sys.exit(f'[envs] {env} in the config names {python}, which is not a file'
                     + (' (on Windows a venv\'s Python is Scripts/python.exe, not bin/python)' if os.name == 'nt' else ''))
        if os.name == 'nt': sys.exit(subprocess.call([python, __file__, *sys.argv[1:]]))   # Windows has no real exec
        os.execv(python, [python, __file__, *sys.argv[1:]])


if __name__ == '__main__':
    main()
