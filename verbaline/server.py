"""`verbaline serve`: the studio page. Every voice review and every voice decision happens here.

Open http://localhost:8765 (on Linux, scripts/install_service.sh keeps it running as a user service).

Lines tab, for each line:
  - pick the take that ships (or press 1-3): <work_dir>/picks.json;
  - write a prompt on any take you like but want tweaked: <work_dir>/tweaks.json, listed by `verbaline tweaks`;
  - flag the line for all-new takes: <work_dir>/regen.json;
  - direct it: which voice says it, its emotion, directing notes, and the text the engine reads (directions.toml);
  - ✂ split it into parts, each in its own tone ([urgent]...[/][sad]...[/], lineparts.py): each part is made on its
    own and the parts are joined into whole takes; any part can get new tries, and which try of each goes in is yours;
  - generate more takes (they're scored automatically);
  - act it yourself: record a take in the browser (<work_dir>/performances/), and Seed-VC re-voices it as the line's
    voice, keeping your timing and delivery (its takes are "you pN", scored like the rest).
Cast tab, for each cast member's voice (cast.toml):
  - the engine: local (Qwen3-TTS cloning) unless you choose a cloud one (xAI) for that voice;
  - the description voice design reads, then design candidates (local Qwen3-TTS) and choose references;
  - pitch shift for converting your own performances, xAI voice and speed, notes;
  - which speakers use it; add new cast members.
Timeline tab, for each group, when the project's adapter has a timeline hook: when every line plays, what sets it off
and what happens around it (the project's events), conversations boxed together; its words can be rewritten there,
and ▶ from here plays the scene's picked takes in turn (docs/details/timeline-details.md).
Generation runs as background jobs, one at a time (the GPU holds one model at a time), with their log on the page.
New takes from any engine show up on reload: put them in <work_dir>/takes/<line key>/<source>_<n>.wav."""
import collections, itertools, json, mimetypes, os, re, shutil, socket, subprocess, sys, threading, time, tomllib, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verbaline import lineparts, models, tomledit, workfiles

HERE = Path(__file__).resolve().parent
VO = HERE / 'cli.py'
EMOTIONS = ('neutral', 'calm', 'urgent', 'shouting', 'whisper', 'sad', 'warm', 'playful', 'stunned', 'angry', 'crying',
            'vengeful')                                    # as cli.py's
XAI_VOICES = ('ara', 'aurora', 'carina', 'celeste', 'eve', 'iris', 'liora', 'luna', 'ursa')
NOISE = re.compile(r'it/s\]|s/it\]|\d+%\||Fetching \d+ files|UserWarning|FutureWarning|warnings\.warn|deprecate\(|'
                   r'list_audio_backends\(\)|download_asset\(|self\.gen = func|Warning: You are sending unauthenticated|'
                   r'output_attentions=True|flash-attn is not installed|^\*+$|pad_token_id')


# ------------------------------------------------------------------ background jobs

def stop(proc):
    """Stops a job and what it started: on Windows a job's model environment runs as its child, and terminate() alone
    would leave that running."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
    else: proc.terminate()


class Jobs:
    """Runs studio commands (cli.py) one job at a time (each job is one or more steps), keeping their output for the page."""
    def __init__(self, root='.'):
        self.root = root; self.lock = threading.Lock(); self.queue = collections.deque(); self.current = None; self.proc = None
        self.recent = collections.deque(maxlen=100); self.log = collections.deque(maxlen=2000); self.ids = itertools.count(1)
        self.seq = 0; self.gen = int(time.time() * 1000)   # output lines are numbered (seq); gen changes on a clear or a restart
        threading.Thread(target=self.loop, daemon=True).start()

    def add(self, label, steps):
        with self.lock:
            j = dict(id=next(self.ids), label=label, steps=steps, queued=time.time()); self.queue.append(j)
        return j['id']

    def cancel(self, jid):
        with self.lock:
            for j in list(self.queue):
                if j['id'] == jid: self.queue.remove(j); return True
            if self.current and self.current['id'] == jid and self.proc:
                self.current['cancelled'] = True; stop(self.proc); return True
        return False

    def note(self, line):
        line = line.rstrip()
        if line and not NOISE.search(line):
            with self.lock: self.seq += 1; self.log.append((self.seq, time.strftime('%H:%M:%S ') + line[-400:]))

    def loop(self):
        while True:
            with self.lock: j = self.queue.popleft() if self.queue else None
            if not j: time.sleep(.3); continue
            self.current = j; j['started'] = time.time(); j['log_from'] = self.seq + 1; ok = True
            self.note(f'== {j["label"]}')
            env = dict(os.environ, PYTHONUNBUFFERED='1')
            for k, argv in enumerate(j['steps']):
                j['step'] = k + 1
                self.note('$ verbaline ' + ' '.join(argv))
                try:
                    self.proc = subprocess.Popen([sys.executable, str(VO), *argv], cwd=self.root, env=env, text=True, encoding='utf-8', errors='replace',
                                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
                    for raw in self.proc.stdout:
                        for part in raw.split('\r'): self.note(part)
                    rc = self.proc.wait()
                except OSError as e: rc = 1; self.note(f'could not start: {e}')
                if rc != 0 or j.get('cancelled'):
                    ok = False; self.note('cancelled' if j.get('cancelled') else f'failed (exit {rc})'); break
            j['secs'] = round(time.time() - j['started']); j['ok'] = ok
            self.note(f'== {"done" if ok else "stopped"}: {j["label"]} ({j["secs"]} s)')
            with self.lock: self.recent.appendleft(j); self.current = None; self.proc = None

    def clear(self):
        """Forgets finished jobs and their output; the running job's output and the queue stay."""
        with self.lock:
            self.recent.clear(); keep = self.current.get('log_from', self.seq + 1) if self.current else self.seq + 1
            self.log = collections.deque((x for x in self.log if x[0] >= keep), maxlen=self.log.maxlen); self.gen += 1

    def state(self, since=None):
        """The running job, the queue, finished jobs (newest first) and output: `log` is the last 80 lines as text;
        with `since` (a seq), `out` is every kept line after it as [seq, text], and `gen` says whether to start over."""
        with self.lock:
            cur = self.current
            s = dict(current=cur and dict(id=cur['id'], label=cur['label'], step=cur.get('step', 0),
                                          steps=len(cur['steps']), secs=round(time.time() - cur['started'])),
                     queued=[dict(id=j['id'], label=j['label']) for j in self.queue],
                     recent=[dict(id=j['id'], label=j['label'], ok=j['ok'], secs=j['secs']) for j in self.recent],
                     log=[x[1] for x in list(self.log)[-80:]], gen=self.gen, seq=self.seq)
            if since is not None: s['out'] = [list(x) for x in self.log if x[0] > since]
            return s


# ------------------------------------------------------------------ what the page shows

def same_words(a, b): return ' '.join((a or '').split()) == ' '.join((b or '').split())


def made_from(c, key):
    """{take: {text}}: the words each take was made from (verbaline records them)."""
    f = c.path('takes', key, 'made.json'); return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def line_shift(c, r):
    """A line's pitch shift for its "pitch" takes: its own (directions.toml), else its voice's (as the cli does)."""
    own = str(r.get('pitch_shift') or '').strip()
    return int(own) if own else int(c.voice_cfg(r['voice']).get('pitch_shift', 0) or 0)


def has_performances(c, keys):
    return any(re.sub(r'_p\d+$', '', p.stem) in keys for p in c.path('performances').glob('*_p*.wav'))


def game_state(c):
    """What the game has: ({line id: words} or None if unknown, {clip key: picked take}): the project's game_state hook
    (the game's own files, so an export someone ran by hand counts too), else what the last Apply recorded."""
    try: return c.project.game_state(c)
    except Exception as e:                      # the game's files half-written by an Apply running now: unknown for now
        print(f'game_state: {type(e).__name__}: {e}', flush=True); return None, {}


EXPORT_LOCK = threading.Lock()


def fresh_lines(c, export):
    """Re-reads the project's lines when they, the cast, directions or pronunciations changed since lines.csv was written."""
    with EXPORT_LOCK: _fresh_lines(c, export)


def _fresh_lines(c, export):
    c.reload(); tomledit.use(c.project)
    out = c.path('lines.csv')
    pj = c.project
    srcs = [p for p in [pj.file, pj.cast_file, pj.directions_file, pj.pronunciations_file, *pj.watch(c)] if p.exists()]
    if not out.exists() or not c.path('groups.json').exists() or max(p.stat().st_mtime for p in srcs) > out.stat().st_mtime: export()


def state(c, export):
    fresh_lines(c, export)
    picks = c.json('picks.json', {}); regen = set(c.json('regen.json', [])); tweaks = c.json('tweaks.json', {})
    engines = models.engines(c); out = []; groups = {}
    game, applied = game_state(c)
    # Only a project's game_state hook says what the game has right now, so only then is an un-pick something waiting:
    # the game still has that line's clip, and the next Apply hands over picks without it.
    hooked = c.project.hook('game_state') is not None
    for r in c.lines(): groups.setdefault(r['key'], []).append(r)
    tuned_voices = {v for v in {r['voice'] for rows in groups.values() for r in rows} if tuned(c, v)}
    for key, rows in groups.items():
        r = rows[0]; folder = c.path('takes', key); made = made_from(c, key)
        scores = json.loads((folder / 'scores.json').read_text(encoding='utf-8')) if (folder / 'scores.json').exists() else {}
        takes = []
        for t in sorted(folder.glob('*.wav')) if folder.exists() else []:
            s = scores.get(t.name, {})
            # A conversion of your performance pN (vc_<key>_pN_<ref>_<kind>[_ft].wav) shows as "you pN clone" or "you pN
            # pitch +14", and "tuned" when made with the voice's fine-tuned model. (Before Oct 27: ..._[ft_]cfgNN.wav.)
            src = 'you ' + t.name[len(f'vc_{key}_'):].split('_')[0] if t.name.startswith(f'vc_{key}_p') else \
                'you' if t.name.startswith('vc_') else t.name.split('_')[0]
            mk = made.get(t.name, {})
            kind = re.search(r'_(clone|pitch)(_ft)?\.wav$', t.name) if src.startswith(('you', 'mirror')) else None
            if kind:
                st = mk.get('shift')
                src += ' clone' if kind[1] == 'clone' else ' pitch' + (f' {st:+d}' if st is not None else '')
            if src.startswith(('you', 'mirror')) and ((kind and kind[2]) or '_ft_cfg' in t.name): src += ' tuned'
            # ⇄ Mirror and ✦ Restyle (Nov 6): what the take came from and whose voice it was given.
            how = (dict(kind='mirror', came=workfiles.clip_label(mk.get('came')), came_path=mk.get('came', ''),
                        into=workfiles.clip_label(mk.get('target'))) if src.startswith('mirror') else
                   dict(kind='restyle', style=mk.get('style', ''), engine=mk.get('engine', 'qwen'),
                        came=workfiles.clip_label(mk.get('target'))) if src == 'restyle' else
                   dict(kind='beat', came=workfiles.clip_label(mk.get('came')), secs=mk.get('beat'), after=mk.get('after', ''))
                   if src == 'beat' else
                   dict(kind='parts', parts=[dict(tone=x['tone'], n=try_n(x['take']), gain=x.get('gain', 0), gap=x.get('gap', 0))
                                             for x in mk.get('parts', [])]) if src == 'parts' and mk.get('parts') else None)
            takes.append(dict(path=c.rel(t), name=t.name, source=src, mtime=t.stat().st_mtime,
                              total=s.get('total'), wer=s.get('wer'), voice=s.get('voice'), quality=s.get('quality'),
                              ref=made.get(t.name, {}).get('ref', ''),
                              # Old words: made from neither the line's words nor what the engine reads for them now
                              # (a respelling, "say it as" or pronunciations.toml, isn't a change of words).
                              old=(made.get(t.name, {}).get('text') if not any(same_words(made.get(t.name, {}).get('text') or r['text'], x)
                                                                               for x in (r['text'], r['say'], r.get('say_override'))) else ''),
                              heard=s.get('heard', ''), edges=s.get('edges', False), how=how,
                              tweak=tweaks.get(key, {}).get(c.rel(t), {}).get('prompt', '')))
        # Your own performances, mirrors and restyles first (you made them on purpose; the scorer would bury a strong
        # read with one misheard word under the engines' takes), takes with the words wrong last, the rest newest
        # first. Not by score: of 113 lines a director picked, the top score was the pick 12% of the time, below
        # the 18% a random pick would hit (the highest scorers are usually too dry and lack personality); newest
        # first put the pick among the three takes shown 61% of the time, by score 49%.
        takes.sort(key=lambda t: (not (t['source'].startswith(('you', 'mirror', 'restyle', 'beat')) and not t['old']),
                                  t['total'] == 0, -t['mtime']))
        perf = sorted((p for p in c.path('performances').glob(f'{key}_p*.wav') if re.fullmatch(re.escape(key) + r'_p\d+', p.stem)),
                      key=lambda p: int(p.stem.rsplit('_p', 1)[1]))
        perf = [dict(path=c.rel(p), n=p.stem[len(key) + 1:]) for p in perf]
        eng = c.line_engine(r)
        parts, parts_err = line_parts(c, r)
        pending = game is not None and any(not same_words(game.get(x['id']), x['text']) for x in rows)
        pick = picks.get(key, {}).get('take')
        auto, _ = c.ref(r['voice'], r['emotion'])         # the reference "auto" clones (its emotion's, else neutral...)
        older = older_ref(c, r['voice'], made.get(Path(pick).name, {})) if pick and Path(pick).parent.name == key else None
        out.append(dict(pending=pending, pick_pending=bool(pick) and applied.get(key) != pick,
                        unpick_pending=hooked and not pick and bool((applied or {}).get(key)), game_text=(game or {}).get(r['id'], ''),key=key, ids=[x['id'] for x in rows], group=r['group'], speaker=r['speaker'], context=r.get('context', ''), kind=r.get('kind', ''),
                        voice=r['voice'], voice_default=r.get('voice_default', ''), text=r['text'],
                        emotion=r['emotion'], emotion_default=r.get('emotion_default', 'neutral'), note=r['note'],
                        say=r.get('say_override', ''), engine=eng, engine_line=r.get('engine', ''), voice_engine=c.engine(r['voice']), cloud=engines.get(eng, {}).get('cloud', False),
                        ready=bool(c.ref(r['voice'])[0]) or not getattr(models.ENGINES.get(eng, {}).get('cls'), 'needs_ref', True),
                        takes=takes, performances=perf, pick=pick, regen=key in regen, ref_auto=auto.stem if auto else '',
                        pick_older=older,
                        shift=line_shift(c, r), shift_own=str(r.get('pitch_shift') or ''),
                        shift_voice=int(c.voice_cfg(r['voice']).get('pitch_shift', 0) or 0), tweaks=len(tweaks.get(key, {})),
                        tuned=r['voice'] in tuned_voices, parts_markup=r.get('parts', ''), parts=parts, parts_err=parts_err,
                        parts_words=lineparts.plain(parts) if parts else ''))
    return out


def try_n(name):
    """'qwen_3.wav' -> '3' (a part's try, as the page numbers it)."""
    m = re.search(r'_(\d+)\.wav$', name or ''); return m[1] if m else (name or '?')


def line_parts(c, r):
    """✂ A line's parts for the page: ([dict(id, tone, tag, text, gap, ref, tries=[{path, name, n, at, engine}], chosen,
    gain)], error). ref is the reference the part clones (its tone's, else neutral, calm, its nearest kin)."""
    try: parts = lineparts.parse(r.get('parts', ''), r['emotion'])
    except ValueError as e: return [], str(e)
    m = lineparts.mix(c.work, r['key']); out = []
    for p in parts:
        pid = lineparts.part_id(r['voice'], p); made = lineparts.made(c.work, r['key'], pid)
        tries = [dict(path=c.rel(t), name=t.name, n=try_n(t.name), at=made.get(t.name, {}).get('at', ''),
                      engine=made.get(t.name, {}).get('engine', t.name.split('_')[0])) for t in lineparts.tries(c.work, r['key'], pid)]
        t, gain = lineparts.chosen(c.work, r['key'], pid)
        ref, _ = c.ref(r['voice'], p['tone'])
        out.append(dict(id=pid, tone=p['tone'], tag=p['tag'] or '', text=p['text'], gap=p['gap'], ref=ref.stem if ref else '',
                        tries=tries, chosen=t.name if t else '', gain=gain, mixed=bool(m.get(pid, {}).get('try'))))
    return out, ''


def check_parts(markup, emotion):
    """✂ A line's parts as they're saved: '' for none; ValueError (said on the page) when they can't be read."""
    markup = ' '.join(str(markup or '').split())
    if markup: lineparts.parse(markup, emotion if emotion in EMOTIONS else 'neutral')
    return markup


def older_ref(c, voice, made):
    """When a take was cloned from a reference that has since been replaced or removed: {emotion, replaced} (the time
    it was replaced), else None. From made.json's ref and time, and the kept clips (ref/<emotion>_<time>.wav, ref/removed/)."""
    e, at = made.get('ref'), made.get('at', '')
    if not e or e not in EMOTIONS or not at or made.get('target'): return None
    when = at.replace('-', '').replace(' ', '-').replace(':', '') + '00'
    d = c.path('voices', voice, 'ref')
    later = sorted(p.stem[-15:] for p in [*d.glob(f'{e}_*.wav'), *d.glob(f'removed/{e}_*.wav')]
                   if re.fullmatch(re.escape(e) + r'_\d{8}-\d{6}', p.stem) and p.stem[-15:] > when)
    if not later: return None
    t = later[0]; return dict(emotion=e, replaced=f'{t[:4]}-{t[4:6]}-{t[6:8]} {t[9:11]}:{t[11:13]}')


def tuned(c, voice):
    """A voice's fine-tuned Seed-VC models (verbaline train), {"clone": record, "pitch": record} for the kinds it has, or
    None: its "clone" takes use the timbre one, its "pitch" takes the pitch-following one (as cli.tuned_model)."""
    out = {}
    for kind in ('clone', 'pitch'):
        m = workfiles.seedvc_model(c.work, voice, kind == 'pitch')
        if m: out[kind] = {k: m[k] for k in ('steps', 'clips', 'minutes', 'trained') if k in m}
    return out or None


def cast_state(c, export):
    fresh_lines(c, export)
    rows = c.lines(); picks = c.json('picks.json', {})
    speakers = dict(c.cast.get('speakers', {}))
    for r in rows: speakers.setdefault(r['speaker'], r.get('voice_default', ''))
    voices = []
    for v, prof in sorted(c.cast.get('voices', {}).items()):
        mine = [r for r in rows if r['voice'] == v and r['id'] == r['key']]
        refs = []
        for w in sorted(c.path('voices', v, 'ref').glob('*.wav')) if c.path('voices', v, 'ref').exists() else []:
            if w.stem not in EMOTIONS: continue           # older references kept with a timestamp
            t = w.with_suffix('.txt')
            refs.append(dict(emotion=w.stem, path=c.rel(w), text=t.read_text(encoding='utf-8').strip() if t.exists() else '',
                             source=workfiles.clip_source(c.work, v, w)))       # ref-source: the candidate or take it is
        cands = []
        d = c.path('voices', v, 'design'); came = workfiles.origins(d) if d.exists() else {}
        for w in sorted(d.glob('cand_*.wav'), key=lambda p: int(p.stem.split('_')[1])) if d.exists() else []:
            m = workfiles.meta(w); n = int(w.stem.split('_')[1])
            # ref-source: the references made from it (this audio, or a version of it from before a ↻ retry), and
            # for a restyled one, its style, what it was restyled from and how well it kept that voice.
            uses = [dict(emotion=r['emotion'], version=r['source']['version']) for r in refs
                    if (r['source'] or {}).get('kind') == 'candidate' and r['source'].get('n') == n]
            rs = dict(style=m.get('style', ''), what=m.get('what', {}), match=m.get('match'), engine=m.get('engine', 'qwen'),
                      emotion=m.get('emotion', ''), reread=bool(m.get('reread'))) \
                if m.get('method') == 'restyle' else None
            rr = dict(of=m.get('of'), text=m.get('text', '')) if m.get('method') == 'reread' else None
            mi = dict(kind=m.get('kind', ''), shift=m.get('shift'), came=workfiles.clip_label(m.get('came')), came_path=m.get('came', ''),
                      into=workfiles.clip_label(m.get('into')), into_path=m.get('into', ''), match=m.get('match')) \
                if m.get('method') == 'mirror' else None
            cands.append(dict(n=n, path=c.rel(w), origin=came.get(w.stem), uses=uses, restyle=rs, mirror=mi, reread=rr,
                              method=m.get('method', 'design' if m else ''), at=m.get('at', ''),
                              description=m.get('description', '') if m.get('method') == 'design' else '',
                              seeded=m.get('method') == 'design' and bool(m.get('seed')), retries=m.get('retries', 0),
                              text=w.with_suffix('.txt').read_text(encoding='utf-8').strip() if w.with_suffix('.txt').exists() else '',
                              previews={e: c.rel(p) for e, p in workfiles.previews(w).items()}))
        # In rejected/: deleted candidates, and the old versions retries replaced (before Nov 6 a retry replaced in place).
        alive = {int(x['n']) for x in cands}
        kept = [int(m[1]) for p in d.glob('rejected/cand_*.wav') if (m := re.fullmatch(r'cand_(\d+)_\d{8}-\d{6}', p.stem))] if d.exists() else []
        rejected = len(set(kept) - alive); older = sum(n in alive for n in kept)
        # What an emotion without its own reference clones (verbaline ref_order): shown on its empty tile.
        fallback = {}
        for e in EMOTIONS:
            if not any(x['emotion'] == e for x in refs):
                w, _ = c.ref(v, e); fallback[e] = w.stem if w else ''
        clips = workfiles.training_clips(c.work, v)
        voices.append(dict(id=v, profile=prof, engine=c.engine(v), refs=refs, candidates=cands, rejected=rejected, older=older,
                           fallback=fallback,
                           tuned=tuned(c, v),
                           train_clips=len(clips), train_minutes=round(sum(s for _, s in clips) / 60, 1),
                           speakers=sorted(s for s, x in speakers.items() if x == v),
                           lines=len(mine), with_takes=sum(bool(list(c.path('takes', r['key']).glob('*.wav'))) for r in mine),
                           picked=sum(r['key'] in picks for r in mine)))
    eng = models.engines(c)
    return dict(voices=voices, speakers=speakers, emotions=EMOTIONS, xai_voices=XAI_VOICES,
                engines=[dict(id=k, label=e['label'], cloud=e['cloud']) for k, e in eng.items()],
                default_engine=c.cfg['tts']['backend'], xai_key=bool(os.environ.get('XAI_API_KEY')),
                # ✦ Restyle's presets per emotion (Qwen's words, Step-Audio-EditX's edits) and whether EditX can run.
                styles={e: dict(words=w, recipe=r) for e, (w, r) in models.STYLES.items()},
                tones=dict(aliases=lineparts.ALIASES, gap=lineparts.GAP, pause=lineparts.PAUSE, max_gap=lineparts.MAX_GAP),
                orders={e: workfiles.ref_order(e, EMOTIONS) for e in EMOTIONS},   # what an emotion clones without its own
                editx=dict(why=models.editx_missing(c), edits=models.EDITX),
                takes_default=c.cfg['tts'].get('takes', 8), passage_default=c.passage, project=c.project.name,
                apply_label=c.cfg.get('apply', {}).get('label', 'Apply to game'), apply_about=c.cfg.get('apply', {}).get('about', ''),
                groups=c.json('groups.json', []), files={k: rel(c.project.root, getattr(c.project, k + '_file'))
                                                         for k in ('cast', 'directions', 'pronunciations')},
                pronunciations=[dict(word=w, say=s) for w, s in sorted(c.say.items(), key=lambda x: x[0].lower())])



def rel(root, path):
    """A path as the page names it: from the project's root when inside it."""
    try: return Path(path).relative_to(root).as_posix()
    except ValueError: return Path(path).as_posix()

def promote(c, src, voice, emotion, text):
    """Makes a clip a voice's reference for an emotion, keeping the old one with a timestamp."""
    dst = c.path('voices', voice, 'ref', emotion + '.wav'); dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        old = dst.with_name(f'{emotion}_{time.strftime("%Y%m%d-%H%M%S")}.wav'); workfiles.replace(dst, old)
        if dst.with_suffix('.json').exists(): workfiles.replace(dst.with_suffix('.json'), old.with_suffix('.json'))
        # Its transcript goes with it (until Nov 6 it was overwritten, so a kept reference lost the words Qwen reads).
        if dst.with_suffix('.txt').exists(): workfiles.replace(dst.with_suffix('.txt'), old.with_suffix('.txt'))
    shutil.copy2(src, dst); dst.with_suffix('.txt').write_text(text.strip(), encoding='utf-8')
    workfiles.note_source(c.work, voice, src, dst)             # ref-source: which candidate or take it came from


def save_performance(c, key, words, data):
    """A take recorded on the page (a WAV) -> <work_dir>/performances/<key>_pN.wav, with the words it was recorded with.
    Trimmed to the voice, with 0.2 s of room either side (the silence before and after would only be converted
    into noise), and brought to a -3 dB peak: one gain for the whole take, so the delivery's dynamics are kept.
    Returns (path, seconds, the recording's own peak)."""
    import io, numpy as np, soundfile as sf
    audio, sr = sf.read(io.BytesIO(data), dtype='float32', always_2d=True); audio = audio.mean(1)
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    frame = max(1, sr // 50); n = len(audio) // frame
    if n:
        level = np.sqrt((audio[:n * frame].reshape(n, frame) ** 2).mean(1))
        on = np.flatnonzero(level > level.max() / 50)                 # within about 34 dB of the loudest moment
        pad = int(.2 * sr)
        audio = audio[max(0, on[0] * frame - pad):min(len(audio), (on[-1] + 1) * frame + pad)]
    if len(audio) < .3 * sr or peak < .003: raise ValueError('nothing recorded (check the microphone)')
    audio = audio * (.7 / max(float(np.abs(audio).max()), 1e-6))
    d = c.path('performances'); d.mkdir(exist_ok=True)
    p = d / f'{key}_p{workfiles.next_performance(d, key)}.wav'
    sf.write(p, audio, sr, subtype='PCM_24'); p.with_suffix('.txt').write_text(words, encoding='utf-8')
    return p, len(audio) / sr, peak


# ------------------------------------------------------------------ the server

class Handler(BaseHTTPRequestHandler):
    ctx = jobs = export = None
    def log_message(self, *a): pass
    def send(self, code, body, kind='application/json'):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)
    def file_in_work(self, rel):
        f = (self.ctx.work / rel).resolve()
        return f if self.ctx.work.resolve() in f.parents and f.is_file() else None
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == '/': return self.send(200, page(self.ctx), 'text/html; charset=utf-8')
            if u.path == '/api/state': return self.send(200, json.dumps(state(self.ctx, self.export)))
            if u.path == '/api/cast': return self.send(200, json.dumps(cast_state(self.ctx, self.export)))
            if u.path == '/api/jobs':
                q = urllib.parse.parse_qs(u.query); since = q.get('since', [''])[0]; gen = q.get('gen', [''])[0]
                since = int(since) if since.isdigit() else None
                if since is not None and gen != str(self.jobs.gen): since = 0   # cleared (or a restart) since that page last asked: all of it
                return self.send(200, json.dumps(self.jobs.state(since)))
            if u.path == '/api/timeline':
                # The project's timeline of one group (its adapter's timeline hook: docs/details/timeline-details.md).
                q = urllib.parse.parse_qs(u.query); opts = {k[4:]: v[0] for k, v in q.items() if k.startswith('opt.')}
                try: t = self.ctx.project.timeline(self.ctx, q.get('group', [''])[0] or next((g['id'] for g in self.ctx.json('groups.json', []) if g.get('timeline')), ''), opts, q.get('replay', [''])[0] == '1')
                except (ValueError, OSError): raise
                except Exception as e:                    # the project's hook failed: say so on the page
                    import traceback; traceback.print_exc()
                    return self.send(500, json.dumps(dict(error=f'The timeline failed: {type(e).__name__}: {e}')))
                return self.send(200, json.dumps(t))
            if u.path == '/audio':
                f = self.file_in_work(urllib.parse.parse_qs(u.query).get('p', [''])[0])
                if not f: return self.send(404, 'no')
                return self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or 'audio/wav')
        except (OSError, tomllib.TOMLDecodeError, ValueError) as e:
            return self.send(500, json.dumps(dict(error=str(e))))
        self.send(404, 'no')
    def do_POST(self):
        u = urllib.parse.urlparse(self.path); size = int(self.headers.get('Content-Length', 0))
        if u.path == '/api/perform':                      # a take recorded on the page: the body is the WAV itself
            if not 0 < size <= 60_000_000: return self.send(400, json.dumps(dict(error='no recording, or over 5 minutes')))
            try: res = self.perform(urllib.parse.parse_qs(u.query), self.rfile.read(size))
            except (ValueError, KeyError, OSError, RuntimeError) as e: return self.send(400, json.dumps(dict(error=str(e))))
            return self.send(200, json.dumps(dict(ok=True, **res)))
        try: body = json.loads(self.rfile.read(size) or b'{}')
        except ValueError: return self.send(400, json.dumps(dict(error='bad request')))
        try: res = self.post(self.path, body) or {}
        except (ValueError, KeyError, OSError, tomllib.TOMLDecodeError) as e: return self.send(400, json.dumps(dict(error=str(e))))
        self.send(200, json.dumps(dict(ok=True, **res)))
    def perform(self, q, data):
        """Keeps your recording of a line, then converts it into the line's voice (Seed-VC) and scores it, as a job."""
        c = self.ctx; key, ref = q.get('key', [''])[0], q.get('ref', [''])[0]
        r = next((x for x in c.lines() if x['key'] == key), None)
        if not r: raise ValueError('no such line')
        if ref and ref not in EMOTIONS: raise ValueError('unknown reference')
        p, secs, peak = save_performance(c, key, r['text'], data)
        n = p.stem[len(key) + 1:]; via = ['--ref', ref] if ref else []
        jid = self.jobs.add(f'your take {n} of {key} in {r["voice"]}\'s voice (Seed-VC)',
                            [['convert', '--line', key, '--perf', p.stem, *via], ['score', '--line', key]])
        return dict(name=n, secs=round(secs, 1), peak=round(peak, 3), job=jid)
    def post(self, path, body):
        c, key = self.ctx, body.get('key', '')
        if path == '/api/pick':
            picks = c.json('picks.json', {})
            if not any(r['key'] == key for r in c.lines()): raise ValueError(f'no line {key!r}')
            take = body.get('take')
            if take:                                     # a take of this line, as a work-folder path: takes/<key>/<name>.wav
                if not str(take).startswith(f'takes/{key}/') or not self.file_in_work(take):
                    raise ValueError(f'no take {take!r} of {key} (a pick names takes/{key}/<take>.wav)')
                picks[key] = dict(take=take, at=time.strftime('%Y-%m-%d %H:%M'))
            else: picks.pop(key, None)                   # no take: the line has no pick
            c.save_json('picks.json', picks)
        elif path == '/api/tweak':
            tweaks = c.json('tweaks.json', {}); prompt = (body.get('prompt') or '').strip(); take = body.get('take', '')
            if prompt: tweaks.setdefault(key, {})[take] = dict(prompt=prompt, at=time.strftime('%Y-%m-%d %H:%M'))
            else:
                tweaks.get(key, {}).pop(take, None)
                if not tweaks.get(key): tweaks.pop(key, None)
            c.save_json('tweaks.json', tweaks)
        elif path == '/api/regen':
            regen = set(c.json('regen.json', []))
            (regen.add if body.get('on') else regen.discard)(key); c.save_json('regen.json', sorted(regen))
        elif path == '/api/line':
            # Store only what differs from the script's defaults, so script changes still flow through.
            f = {k: body.get(k, '') for k in tomledit.LINE_FIELDS}
            if f['voice'] == body.get('voice_default'): f['voice'] = ''
            if f['emotion'] == body.get('emotion_default'): f['emotion'] = ''
            if f['emotion'] and f['emotion'] not in EMOTIONS: raise ValueError(f'unknown emotion {f["emotion"]}')
            if f['engine'] and f['engine'] not in models.ENGINES: raise ValueError(f'unknown engine {f["engine"]}')
            # Parts are saved only when sent (✂ on the page sends them; a change of voice or notes leaves them be).
            if 'parts' in body: f['parts'] = check_parts(body['parts'], f['emotion'] or body.get('emotion_default', 'neutral'))
            else: f.pop('parts')
            own = str(f['pitch_shift'] or '').strip(); f['pitch_shift'] = str(int(own)) if own else ''
            r0 = next((x for x in c.lines() if x['id'] in body['ids']), None)
            was = line_shift(c, r0) if r0 else None
            tomledit.set_line(body['ids'], f)
            # A new pitch shift for the line: its recordings are converted again at it (a picked take stays as it is).
            if r0 and (int(own) if own else int(c.voice_cfg(r0['voice']).get('pitch_shift', 0) or 0)) != was \
                    and has_performances(c, {r0['key']}):
                fresh_lines(c, self.export)                   # the job reads the line's new shift from lines.csv
                return dict(job=self.job(dict(kind='convert', key=r0['key'])))
        elif path == '/api/text':
            # Edit-only: rewords existing lines (their ids come from the game's script); new lines start in the game.
            known = {r['id']: r for r in c.lines()}
            ids = [i for i in body['ids'] if i in known]
            if not ids: raise ValueError('no such line')
            self.ctx.project.set_words(self.ctx, ids, body.get('text', ''), [known[i] for i in ids])
        elif path == '/api/voice':
            f = body.get('fields', {})
            if f.get('engine') and f['engine'] not in models.ENGINES: raise ValueError(f'unknown engine {f["engine"]}')
            was = int(c.voice_cfg(body['voice']).get('pitch_shift', 0) or 0)
            tomledit.set_voice(body['voice'], f)
            # A new pitch shift: the voice's recordings are converted again at it, except lines with their own (picked
            # takes stay as they are).
            if 'pitch_shift' in f and int(f['pitch_shift'] or 0) != was \
                    and has_performances(c, {r['key'] for r in c.lines() if r['voice'] == body['voice']}):
                return dict(job=self.job(dict(kind='convert', voice=body['voice'])))
        elif path == '/api/voice/add': tomledit.add_voice(body['voice'], body.get('description', ''))
        elif path == '/api/speaker': tomledit.set_speaker(body['speaker'], body['voice'])
        elif path == '/api/pronunciation': tomledit.set_pronunciation(body.get('word', ''), body.get('say', ''))
        elif path == '/api/reference':
            src = self.file_in_work(body['path'])
            if not src: raise ValueError('no such clip')
            if body['emotion'] not in EMOTIONS: raise ValueError('unknown emotion')
            # The transcript must be what the clip actually says (Qwen cloning reads both as one recording; a wrong
            # transcript leaks words into every take). A take: what Whisper heard in it, else the words it was made
            # from; never the line's current words, which may have been rewritten since.
            text = body.get('text') or (src.with_suffix('.txt').read_text(encoding='utf-8') if src.with_suffix('.txt').exists() else '')
            if not text and src.parent.parent == c.path('takes').resolve():
                sc = src.parent / 'scores.json'; heard = json.loads(sc.read_text(encoding='utf-8')).get(src.name, {}).get('heard', '') if sc.exists() else ''
                text = heard or made_from(c, src.parent.name).get(src.name, {}).get('text', '')
            if not text: raise ValueError('no transcript for that clip (score it first)')
            promote(c, src, body['voice'], body['emotion'], text)
            # Then Whisper double-checks it in the background (and fixes it if it's off).
            self.jobs.add(f'check {body["voice"]}\'s {body["emotion"]} reference transcript',
                          [['refcheck', '--voice', body['voice'], '--emotion', body['emotion']]])
        elif path == '/api/candidate/delete':
            # A design candidate that's clearly wrong for the character: moved to design/rejected/ (recoverable), so it
            # can't be chosen by mistake. References already made from it are copies and stay.
            src = self.file_in_work(body['path']); d = c.path('voices', body['voice'], 'design')
            if not src or src.parent != d.resolve() or not re.fullmatch(r'cand_\d+\.wav', src.name): raise ValueError('not a design candidate')
            gone = d / 'rejected'; gone.mkdir(exist_ok=True); stamp = time.strftime('%Y%m%d-%H%M%S')
            for f, suffix in workfiles.candidate_files(src): workfiles.replace(f, gone / f'{src.stem}_{stamp}{suffix}')
        elif path == '/api/candidate/move':
            # A candidate that's wrong for this character but right for another: it becomes the other voice's next
            # candidate (with its transcript and previews), remembering where it came from and what made it.
            src = self.file_in_work(body['path']); d = c.path('voices', body['voice'], 'design')
            if not src or src.parent != d.resolve() or not re.fullmatch(r'cand_\d+\.wav', src.name): raise ValueError('not a design candidate')
            to = body['to']
            if to == body['voice'] or to not in c.cast.get('voices', {}): raise ValueError(f'no other voice "{to}"')
            dd = c.path('voices', to, 'design'); dd.mkdir(parents=True, exist_ok=True)
            n = workfiles.next_candidate(dd); stem = f'cand_{n}'
            came = workfiles.origins(d).get(src.stem) or dict(voice=body['voice'], candidate=int(src.stem.split('_')[1]),
                                                            description=c.voice_cfg(body['voice']).get('description', ''))
            for f, suffix in workfiles.candidate_files(src):      # its transcript, recipe, previews and original go too
                if suffix.endswith('.preview.wav'): to_f = dd / 'previews' / f'{stem}.{suffix.split(".")[1]}.wav'
                elif suffix.startswith('.source'): to_f = dd / 'sources' / (stem + suffix[len('.source'):])
                else: to_f = dd / (stem + suffix)
                to_f.parent.mkdir(exist_ok=True); workfiles.replace(f, to_f)
            o = workfiles.origins(dd); o[stem] = came; workfiles.save_origins(dd, o)
            o = workfiles.origins(d)
            if o.pop(src.stem, None) is not None: workfiles.save_origins(d, o)
            return dict(moved_to=f'{to} candidate {n}')
        elif path == '/api/reference/delete':
            # Removing a reference: kept in ref/removed/ (recoverable). The page confirms first.
            if body.get('emotion') not in EMOTIONS: raise ValueError('unknown emotion')
            ref = c.path('voices', body['voice'], 'ref', body['emotion'] + '.wav')
            if not ref.exists(): raise ValueError(f'{body["voice"]} has no {body["emotion"]} reference')
            gone = ref.parent / 'removed'; gone.mkdir(exist_ok=True); stamp = time.strftime('%Y%m%d-%H%M%S')
            for f in (ref, ref.with_suffix('.txt'), ref.with_suffix('.json')):
                if f.exists(): workfiles.replace(f, gone / f'{f.stem}_{stamp}{f.suffix}')
        elif path == '/api/perform/delete':
            # A recording you don't want: it and its conversions go to removed/ folders (recoverable). A picked
            # conversion stays where it is. Take numbers aren't reused, so nothing new takes their names.
            src = self.file_in_work(body['path']); d = c.path('performances')
            if not src or src.parent != d.resolve() or not re.fullmatch(re.escape(key) + r'_p\d+\.wav', src.name):
                raise ValueError('not a recording of that line')
            gone = d / 'removed'; gone.mkdir(exist_ok=True)
            for f in (src, src.with_suffix('.txt')):
                if f.exists(): workfiles.replace(f, gone / f.name)
            picked = c.json('picks.json', {}).get(key, {}).get('take'); t = c.path('takes', key)
            for f in t.glob(f'vc_{src.stem}_*.wav'):
                if c.rel(f) != picked: (t / 'removed').mkdir(exist_ok=True); workfiles.replace(f, t / 'removed' / f.name)
        elif path == '/api/parts':
            # ✂ Just the line's parts (the markup), checked: '' takes them away (its takes stay).
            r = self.row(key)
            tomledit.set_line([x['id'] for x in c.lines() if x['key'] == key], dict(parts=check_parts(body.get('parts', ''), r['emotion'])))
        elif path == '/api/parts/mix':
            # ✂ Which try of a part goes into a join, and its level (dB).
            r = self.row(key); pid = body.get('part', '')
            if not body.get('from_take') and pid not in {lineparts.part_id(r['voice'], p) for p in lineparts.parse(r.get('parts', ''), r['emotion'])}: raise ValueError('no such part')
            m = lineparts.mix(c.work, key)
            if body.get('from_take'):
                # Every part's try as a joined take had them (that take's mix), where the part is still the same.
                f = self.file_in_work(body['from_take'])
                if not f or f.parent != c.path('takes', key).resolve(): raise ValueError('not a take of this line')
                rec = made_from(c, key).get(f.name, {}).get('parts') or []
                if not rec: raise ValueError('that take wasn\'t joined from parts')
                now = {lineparts.part_id(r['voice'], p) for p in lineparts.parse(r.get('parts', ''), r['emotion'])}
                kept = 0
                for x in rec:
                    if x.get('part') in now and (lineparts.folder(c.work, key, x['part']) / x['take']).is_file():
                        e = m.setdefault(x['part'], {}); e['try'] = x['take']; kept += 1
                        if x.get('gain'): e['gain'] = x['gain']
                        else: e.pop('gain', None)
                lineparts.save_mix(c.work, key, m)
                return dict(kept=kept, parts=len(now))
            e = m.setdefault(pid, {})
            if 'try' in body:
                name = str(body['try'] or '')
                if name and not (lineparts.folder(c.work, key, pid) / name).is_file(): raise ValueError('no such try')
                if name: e['try'] = name
                else: e.pop('try', None)
            if 'gain' in body:
                g = float(body['gain'] or 0)
                if not -12 <= g <= 12: raise ValueError('a part\'s level is -12 to +12 dB')
                if g: e['gain'] = round(g, 1)
                else: e.pop('gain', None)
            if not e: m.pop(pid, None)
            lineparts.save_mix(c.work, key, m)
        elif path == '/api/parts/gap':
            # ✂ The silence after part i, in seconds: written back into the markup as [pause N].
            r = self.row(key); parts = lineparts.parse(r.get('parts', ''), r['emotion']); i = int(body.get('index', -1))
            if not 0 <= i < len(parts) - 1: raise ValueError('no gap there')
            secs = round(float(body.get('secs', lineparts.GAP)), 2)
            if not 0 <= secs <= lineparts.MAX_GAP: raise ValueError(f'a gap is 0 to {lineparts.MAX_GAP:g} s')
            parts[i]['gap'] = secs
            tomledit.set_line([x['id'] for x in c.lines() if x['key'] == key], dict(parts=lineparts.dump(parts)))
        elif path == '/api/parts/join':
            # ✂ A whole take from the chosen try of each part (numpy only, at once), then scored as a job.
            r = self.row(key)
            if not r.get('parts'): raise ValueError('this line has no parts')
            out = lineparts.join_line(c, r)
            return dict(take=c.rel(out), job=self.jobs.add(f'score {key} (the parts joined: {out.stem})', [['score', '--line', key]]))
        elif path == '/api/job':
            return dict(id=self.job(body))
        elif path == '/api/jobs/clear':
            self.jobs.clear()
        elif path == '/api/takes/clear':
            # 🧹 A group's takes its picks don't use, into each line's removed/ (recoverable). {group, unpicked, dry}:
            # dry says what would move (the page asks first); otherwise it's a job, after any running one.
            g = str(body.get('group', '')); unpicked = bool(body.get('unpicked'))
            keys = list(dict.fromkeys(r['key'] for r in c.lines() if str(r.get('group', '')) == g))
            if not g or not keys: raise ValueError('no lines in that group')
            if body.get('dry'):
                picks, tweaks = c.json('picks.json', {}), c.json('tweaks.json', {}); n = dict(lines=len(keys), picked=0, takes=0, prompted=0, unpicked=0, unpicked_takes=0)
                for k in keys:
                    pick = picks.get(k, {}).get('take', ''); prompted = set(tweaks.get(k, {}))
                    move, keep = workfiles.clear_plan(c.work, k, pick, prompted, True)
                    if pick: n['picked'] += 1; n['takes'] += len(move); n['prompted'] += sum(f'takes/{k}/{x}' in prompted for x in keep)
                    else: n['unpicked'] += 1; n['unpicked_takes'] += len(move); n['prompted'] += sum(f'takes/{k}/{x}' in prompted for x in keep)
                return dict(plan=n)
            title = next((x.get('title') for x in c.json('groups.json', []) if str(x.get('id')) == g), '') or g
            return dict(job=self.jobs.add(f'clear the takes no pick uses in {title}' + (' (and lines with no pick)' if unpicked else ''),
                                          [['clear-takes', '--group', g, '--before', f'{time.time():.3f}', *(['--unpicked-lines'] if unpicked else [])]]))
        elif path == '/api/job/cancel':
            if not self.jobs.cancel(int(body['id'])): raise ValueError('no such job')
        else: raise ValueError('unknown request')
    def row(self, key):
        """A line by its clip key, from lines.csv made fresh (its parts as saved)."""
        fresh_lines(self.ctx, self.export)
        r = next((x for x in self.ctx.lines() if x['key'] == key), None)
        if not r: raise ValueError('no such line')
        return r
    def job(self, b):
        kind, n = b.get('kind'), str(max(1, min(int(b.get('n', 4)), 24)))
        if kind == 'design':
            return self.jobs.add(f'design {n} candidates for {b["voice"]} (local Qwen3-TTS)', [['design', '--voice', b['voice'], '--n', n]])
        if kind == 'tts':
            where = ['--line', b['key']] if b.get('key') else ['--voice', b['voice']]
            more = ['--more', '--all'] if b.get('key') else []
            eng = self.ctx.engine(b['voice']) if b.get('voice') else '?'
            what = b.get('key') or f'{b["voice"]}\'s lines without takes'
            ref = b.get('ref') or ''
            if ref and ref not in EMOTIONS: raise ValueError('unknown reference')
            via = ['--ref', ref] if ref else []
            if b.get('engine'):            # this batch only, on the engine chosen on the page (cloud only when chosen)
                if b['engine'] not in models.engines(self.ctx): raise ValueError(f'unknown engine {b["engine"]}')
                eng = b['engine']; via += ['--backend', eng]
            if b.get('part'):              # ✂ new tries of one part of the line, each joined with the others' choice
                if not re.fullmatch(r'[a-z]+_[0-9a-f]{8}', b['part']) or not b.get('key'): raise ValueError('no such part')
                tone = b['part'].split('_')[0]
                return self.jobs.add(f'{n} tries of the {tone} part of {b["key"]}, each joined into a take ({eng})',
                                     [['tts', *where, '--takes', n, *more, *via, '--part', b['part']], ['score', *where]])
            if b.get('key') and b.get('parts'):
                return self.jobs.add(f'{n} tries of each part of {b["key"]}, joined into {n} takes ({eng})',
                                     [['tts', *where, '--takes', n, *more, *via], ['score', *where]])
            return self.jobs.add(f'{n} takes for {what} ({eng}{", " + ref + " reference" if ref else ""})',
                                 [['tts', *where, '--takes', n, *more, *via], ['score', *where]])
        if kind == 'bulk':
            # Every line given (the page sends the shown lines that still need a pick): n more takes each, on each
            # line's own engine, then scored.
            keys = [k for k in b.get('keys', []) if re.fullmatch(r'[A-Za-z0-9_]+', k)]
            if not keys: raise ValueError('no lines to generate')
            where = ['--keys', ','.join(keys)]
            return self.jobs.add(f'{n} takes each for {len(keys)} lines that need a pick',
                                 [['tts', *where, '--todo', '--takes', n, '--more', '--all'], ['score', *where]])
        if kind == 'preview':
            eng = b.get('backend', 'qwen')
            if eng not in models.ENGINES or models.ENGINES[eng]['cloud']: raise ValueError('previews use a local engine')
            return self.jobs.add(f'{b["voice"]} candidate {int(b["candidate"])}: hear it cloned ({models.ENGINES[eng]["label"]})',
                                 [['preview', '--voice', b['voice'], '--candidate', str(int(b['candidate'])), '--backend', eng]])
        if kind == 'restyle':
            # A new delivery in the same voice (verbaline restyle, then restyle-keep): a candidate or reference of the voice
            # read again as new candidates; or a line (key) as new takes, from its reference or one of its takes.
            # Engines: qwen (Qwen3-TTS acts the style in words, Seed-VC puts the voice back) or editx (Step-Audio-EditX
            # edits the clip itself).
            c = self.ctx; eng = b.get('engine') or 'qwen'; key = b.get('key') or ''
            if eng not in ('qwen', 'editx'): raise ValueError(f'unknown restyle engine "{eng}"')
            if key:
                r = next((x for x in c.lines() if x['key'] == key), None)
                if not r: raise ValueError('no such line')
                v = r['voice']
            else: v = b.get('voice', '')
            if v not in c.cast.get('voices', {}): raise ValueError(f'no voice "{v}"')
            style = ' '.join(str(b.get('style', '')).split())[:600]; recipe = ' '.join(str(b.get('recipe', '')).split())[:200]
            if eng == 'qwen' and not style: raise ValueError('say how it should be read')
            if eng == 'editx':
                why = models.editx_missing(c)
                if why: raise ValueError(f'Step-Audio-EditX can\'t run here: {why}')
                models.editx_steps(recipe)                      # ValueError: an edit it doesn't know
            src = self.file_in_work(b['from']) if b.get('from') else None; vd = c.path('voices', v).resolve()
            if b.get('from') and not (src and ((src.parent == vd / 'design' and re.fullmatch(r'cand_\d+\.wav', src.name))
                                               or (src.parent == vd / 'ref' and src.stem in EMOTIONS)
                                               or (key and src.parent == c.path('takes', key).resolve()))):
                raise ValueError('restyle a candidate or reference of this voice' + (', or a take of this line' if key else ''))
            if not src and not key: raise ValueError('restyle what? (a candidate or reference)')
            keep = str(max(1, min(int(b.get('n', 2)), 4))); stamp = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
            text = ' '.join(str(b.get('text', '')).split())[:600]
            base, _ = c.ref(v, 'neutral')
            what = (f'{key} from ' if key else '') + workfiles.clip_label(c.rel(src) if src else c.rel(base) if base else '?')
            how = f'"{style}"' if eng == 'qwen' else recipe
            raw = eng == 'qwen' and bool(b.get('raw'))       # Seed-VC's conversion as it is, not read again cleanly
            via = ('Qwen3-TTS acts, Seed-VC keeps the voice' + ('' if raw else ', Qwen3-TTS reads it again cleanly')) if eng == 'qwen' \
                else 'Step-Audio-EditX edits it'
            into = f'takes of {key}' if key else 'new candidates'
            return self.jobs.add(f'restyle {what} as {how}: {keep} {into}, best of {int(keep) * 3} (local: {via})',
                                 [['restyle', *(['--line', key] if key else ['--voice', v]),
                                   *(['--from', c.rel(src)] if src else []), '--engine', eng, *(['--raw'] if raw else []),
                                   *(['--style', style] if style and eng == 'qwen' else []), *(['--recipe', recipe] if eng == 'editx' else []),
                                   '--n', keep, '--tries', str(int(keep) * 3), '--dir', stamp,
                                   *(['--emotion', b['emotion']] if b.get('emotion') in EMOTIONS else []),
                                   *(['--text', text] if text and not key else [])],
                                  ['restyle-keep', '--voice', v, '--dir', stamp],
                                  *([['score', '--line', key]] if key else [])])
        if kind == 'mirror':
            # A clip's delivery in another voice (verbaline mirror, Seed-VC): any take, candidate, reference or recording,
            # into a reference or candidate's voice; as takes of a line (key), or new candidates of the target's voice.
            c = self.ctx; src = self.file_in_work(b.get('from', '')); tgt = self.file_in_work(b.get('into', ''))
            w = c.work.resolve(); key = b.get('key') or ''
            def where(p): return p.relative_to(w).parts if p and w in p.parents else ()
            sp, tp = where(src), where(tgt)
            if not (len(sp) == 4 and sp[0] == 'voices' and ((sp[2] == 'design' and re.fullmatch(r'cand_\d+\.wav', sp[3]))
                                                         or (sp[2] == 'ref' and Path(sp[3]).stem in EMOTIONS))
                    or len(sp) == 3 and sp[0] == 'takes' or len(sp) == 2 and sp[0] == 'performances'):
                raise ValueError('mirror a take, candidate, reference or recording')
            if not (len(tp) == 4 and tp[0] == 'voices' and ((tp[2] == 'design' and re.fullmatch(r'cand_\d+\.wav', tp[3]))
                                                         or (tp[2] == 'ref' and Path(tp[3]).stem in EMOTIONS))):
                raise ValueError('mirror into a reference or a candidate')
            if src == tgt: raise ValueError('that is the same clip')
            if key and not any(x['key'] == key for x in c.lines()): raise ValueError('no such line')
            kinds = b.get('kinds') or 'clone,pitch'
            if kinds not in ('clone', 'pitch', 'clone,pitch'): raise ValueError('kinds: clone, pitch or both')
            shift = str(b.get('shift', '')).strip() or 'auto'
            if shift != 'auto' and not re.fullmatch(r'[+-]?\d+', shift) or shift != 'auto' and abs(int(shift)) > 24:
                raise ValueError('pitch shift: auto, or -24 to 24 semitones')
            what, into = workfiles.clip_label(c.rel(src)), workfiles.clip_label(c.rel(tgt))
            return self.jobs.add(f'mirror {what} into {into}\'s voice: {"takes of " + key if key else "new candidates"} (local Seed-VC)',
                                 [['mirror', '--from', c.rel(src), '--into', c.rel(tgt), *(['--line', key] if key else []),
                                   '--kinds', kinds, '--shift', shift], *([['score', '--line', key]] if key else [])])
        if kind == 'beat':
            # ⏸ A take with a pause put in, after each sentence or after one word (verbaline beat), then scored.
            c = self.ctx; key = b.get('key', ''); src = self.file_in_work(b.get('take', ''))
            if not src or src.parent != c.path('takes', key).resolve() or src.suffix != '.wav': raise ValueError('add a beat to a take of this line')
            secs = float(b.get('secs', .6))
            if not .1 <= secs <= 3: raise ValueError('a beat is 0.1 to 3 seconds')
            word = str(b.get('after_word', '')).strip(); nth = max(1, min(int(b.get('nth', 1) or 1), 9))
            if word and not re.fullmatch(r"[A-Za-z0-9']{1,40}", word): raise ValueError('after which word?')
            where = f'after "{word}"' if word else 'after each sentence'
            return self.jobs.add(f'a {secs:.1f} s beat {where} in take {src.stem} of {key}',
                                 [['beat', '--take', c.rel(src), '--secs', f'{secs:.2f}',
                                   *(['--after-word', word, '--nth', str(nth)] if word else [])], ['score', '--line', key]])
        if kind == 'retry':
            # ↻: the candidate's voice reading other words, as a new candidate (verbaline design --retry); it stays.
            n = int(b['candidate']); text = ' '.join(str(b.get('text', '')).split())[:600]
            return self.jobs.add(f'{b["voice"]} candidate {n} reads new words, as a new candidate (local Qwen3-TTS)',
                                 [['design', '--voice', b['voice'], '--retry', str(n), *(['--text', text] if text else [])]])
        if kind == 'apply':
            return self.jobs.add(f'{self.ctx.cfg.get("apply", {}).get("label", "Apply to game")}: the picks mastered and handed to {self.ctx.project.name}', [['apply']])
        if kind == 'score':
            where = ['--line', b['key']] if b.get('key') else ['--voice', b['voice']]
            return self.jobs.add(f'score {b.get("key") or b["voice"]}', [['score', *where]])
        if kind == 'convert':
            where = ['--line', b['key']] if b.get('key') else ['--voice', b['voice']]
            ref = b.get('ref') or ''
            if ref and ref not in EMOTIONS: raise ValueError('unknown reference')
            return self.jobs.add(f'convert performances for {b.get("key") or b["voice"]} (Seed-VC{", " + ref + " reference" if ref else ""})',
                                 [['convert', *where, *(['--ref', ref] if ref else [])], ['score', *where]])
        if kind == 'train':
            # A voice's two Seed-VC fine-tunes, clone then pitch (about 25 min), then every performance of its lines
            # converted again with them.
            v = b['voice']
            if v not in self.ctx.cast.get('voices', {}): raise ValueError(f'no voice "{v}"')
            return self.jobs.add(f'tune Seed-VC\'s clone and pitch models on {v}, then convert its performances with them (about 25 min)',
                                 [['train', '--voice', v], ['convert', '--voice', v], ['score', '--voice', v]])
        raise ValueError(f'unknown job "{kind}"')


class Server(ThreadingHTTPServer):
    """The page's server, with its port to itself. Python's lets a port be reused (SO_REUSEADDR), and on Windows that
    lets a second studio bind the same port without an error and take half the page's requests: there it asks for the
    port exclusively instead."""
    allow_reuse_address = os.name != 'nt'
    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def bind(port, handler=None):
    """The server on 127.0.0.1:port, or SystemExit saying why the port can't be had."""
    try: return Server(('127.0.0.1', port), handler or Handler)
    except OSError as e:
        hint = (' On Windows a port can also sit in a range the system reserves: `netsh interface ipv4 show '
                'excludedportrange protocol=tcp` lists them.' if os.name == 'nt' else '')
        sys.exit(f'Port {port} can\'t be used ({e.strerror or e}): another studio or program may have it. Choose another '
                 f'with --port or [project] port in verbaline.toml.{hint}')


def serve(c, port, export):
    tomledit.use(c.project)
    server = bind(port)
    Handler.ctx, Handler.jobs, Handler.export = c, Jobs(c.project.root), staticmethod(export)
    print(f'Verbaline For Games, {c.project.name}: http://localhost:{port}  (Ctrl+C to stop)', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass


PAGE_FILE = HERE / 'page.html'


def page(c):
    """The page, with the project's name in its title."""
    import html
    return PAGE_FILE.read_text(encoding='utf-8').replace('{{PROJECT}}', html.escape(c.project.name))
