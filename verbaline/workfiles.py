"""File layout helpers shared by the cli and the page server (standard library only: runs in every environment).

A voice's design folder, <work_dir>/voices/<voice>/design/:
  cand_N.wav / cand_N.txt   design candidates and what they say
  cand_N.json               how it was made: {method: design|clone, seed, description, text, ...} (for ↻ retry)
  sources/cand_N.wav (.txt) a candidate's original audio, kept when a retry clones it (candidates without a seed)
  previews/cand_N.<engine>.wav   a candidate's audition text spoken by a text-to-speech engine cloning it
  rejected/                 deleted candidates (recoverable)
  origins.json              {cand_N: {voice, candidate, description}} for candidates moved here from another voice
  restyle/<id>/             a restyle's acted tries while it runs (verbaline restyle, restyle-keep), then removed

A voice's references, <work_dir>/voices/<voice>/ref/:
  <emotion>.wav / .txt      the clip local engines clone for that emotion, and what it says
  <emotion>.json            {from: where it came from} (clip_source; older references are found by their audio)

Your performances, <work_dir>/performances/:
  <line key>_pN.wav / .txt  a recording of a line, and the words it was recorded with
  removed/                  deleted recordings (recoverable)

A voice's fine-tuned Seed-VC models, <work_dir>/voices/<voice>/seedvc/clone/ (the timbre model, for "clone" takes)
and .../pitch/ (the pitch-following one, for "pitch" takes), each (verbaline train):
  model.pth / config.yml    the model and its Seed-VC config
  model.json                {f0, steps, clips, minutes, trained}: f0 says which model it tunes (pitch-following or not)
  previous/                 the model it replaced (the same three files)"""
import csv, hashlib, json, re, struct
from pathlib import Path

CAND = re.compile(r'cand_(\d+)')


def wav_seconds(path):
    """A WAV's length from its header, whatever its sample format, or 0 if it can't be read."""
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'RIFF' or not f.read(4) or f.read(4) != b'WAVE': return 0.0
            rate = align = 0
            while len(h := f.read(8)) == 8:
                cid, size = h[:4], struct.unpack('<I', h[4:])[0]
                if cid == b'data': return size / (rate * align) if rate and align else 0.0
                d = f.read(size + (size & 1))
                if cid == b'fmt ' and len(d) >= 14: rate, align = struct.unpack('<I', d[4:8])[0], struct.unpack('<H', d[12:14])[0]
    except OSError: pass
    return 0.0


# The reference an emotion without its own clones: neutral, else calm, else its nearest kin. Before Nov 6 it fell to the
# voice's first reference by name (angry): Mai_ReturnFire ("Firm, not angry") shipped cloned from her angry reference
# while her neutral was briefly removed.
NEAR = {'calm': ('warm',), 'urgent': ('shouting', 'angry'), 'shouting': ('urgent', 'angry'), 'whisper': ('calm', 'sad'),
        'sad': ('crying', 'calm'), 'warm': ('calm', 'playful'), 'playful': ('warm',), 'stunned': ('sad', 'urgent'),
        'angry': ('vengeful', 'urgent'), 'crying': ('sad',), 'vengeful': ('angry', 'calm')}


def ref_order(emotion, emotions):
    """The emotions whose reference a line of this emotion clones, in order (cli.Ctx.ref, the page's "auto")."""
    out = []
    for e in (emotion, 'neutral', 'calm', *NEAR.get(emotion, ()), *emotions):
        if e not in out: out.append(e)
    return out


def training_clips(work, voice):
    """What a voice's Seed-VC fine-tune learns from: its reference clips, and its lines' takes with the words right and
    in its voice (word error ≤ 0.1, score ≥ 0.85, voice match ≥ 0.7, no stray words at the ends) or picked. Never a
    conversion: not of a performance (it would teach the model the warble, and the actor), nor a mirror, a restyle or a
    beat made from one (Seed-VC output; they score well against the very clip they were converted into). Each 1-30 s
    (Seed-VC's limits). Returns [(path, seconds)]."""
    w = Path(work); out = []; ref = w / 'voices' / voice / 'ref'
    for p in sorted(ref.glob('*.wav')) if ref.exists() else []:
        if '_' not in p.stem: out.append(p)                       # current references (replaced ones are timestamped)
    picks = json.loads((w / 'picks.json').read_text(encoding='utf-8')) if (w / 'picks.json').exists() else {}
    with open(w / 'lines.csv', newline='', encoding='utf-8') as f: keys = {r['key'] for r in csv.DictReader(f) if r['voice'] == voice}
    for key in sorted(keys):
        sc = w / 'takes' / key / 'scores.json'; mf = w / 'takes' / key / 'made.json'
        made = json.loads(mf.read_text(encoding='utf-8')) if mf.exists() else {}
        for name, s in (json.loads(sc.read_text(encoding='utf-8')) if sc.exists() else {}).items():
            if name.startswith(('vc_', 'mirror_', 'restyle_', 'beat_')) or not (w / 'takes' / key / name).exists(): continue
            if made.get(name, {}).get('target') or made.get(name, {}).get('came'): continue
            good = s.get('wer', 1) <= .1 and s.get('total', 0) >= .85 and s.get('voice', 0) >= .7 and not s.get('edges')
            if good or picks.get(key, {}).get('take') == f'takes/{key}/{name}': out.append(w / 'takes' / key / name)
    return [(p, s) for p in out if 1 <= (s := wav_seconds(p)) <= 30]


def seedvc_model(work, voice, f0):
    """A voice's fine-tuned Seed-VC model of one kind, the pitch-following model (f0) or the timbre one, as its
    record (model.json, plus its path), or None. They live in voices/<voice>/seedvc/pitch/ and .../clone/, after the
    takes they make."""
    d = Path(work) / 'voices' / voice / 'seedvc' / ('pitch' if f0 else 'clone')
    if not ((d / 'model.pth').exists() and (d / 'model.json').exists()): return None
    return dict(json.loads((d / 'model.json').read_text(encoding='utf-8')), checkpoint=str(d / 'model.pth'), config=str(d / 'config.yml'))


def next_performance(folder, key):
    """The next take number for a line's performances: after the highest ever used, deleted ones included, so a new
    recording never takes the name (and the conversions) of an old one."""
    d = Path(folder); pat = re.compile(re.escape(key) + r'_p(\d+)')
    nums = [int(m.group(1)) for p in list(d.glob(f'{key}_p*.wav')) + list(d.glob(f'removed/{key}_p*.wav'))
            if (m := pat.fullmatch(p.stem))]
    return max(nums + [0]) + 1


def next_candidate(design):
    """The next candidate number: after the highest ever used here, deleted ones included, so none is reused."""
    d = Path(design)
    nums = [int(m.group(1)) for p in list(d.glob('cand_*.wav')) + list(d.glob('rejected/cand_*.wav'))
            if (m := CAND.match(p.stem))]
    return max(nums + [0]) + 1


def previews(cand):
    """{engine: path} of a candidate's previews."""
    c = Path(cand)
    return {p.suffixes[-2].lstrip('.'): p for p in sorted((c.parent / 'previews').glob(c.stem + '.*.wav'))}


def origins(design):
    f = Path(design) / 'origins.json'; return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def save_origins(design, data):
    f = Path(design) / 'origins.json'; tmp = f.with_suffix('.tmp'); tmp.write_text(json.dumps(data, indent=1), encoding='utf-8'); tmp.replace(f)


def meta(cand):
    f = Path(cand).with_suffix('.json'); return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def save_meta(cand, data):
    f = Path(cand).with_suffix('.json'); f.write_text(json.dumps(data, indent=1), encoding='utf-8')


def candidate_files(cand):
    """Every file that belongs to a candidate: [(path, suffix after its stem)], for moving or deleting it as one."""
    c = Path(cand); out = [(c, '.wav')]
    for ext in ('.txt', '.json'):
        if c.with_suffix(ext).exists(): out.append((c.with_suffix(ext), ext))
    for e, p in previews(c).items(): out.append((p, f'.{e}.preview.wav'))
    for ext in ('.wav', '.txt'):
        s = c.parent / 'sources' / (c.stem + ext)
        if s.exists(): out.append((s, '.source' + ext))
    return out


# ------------------------------------------------------------------ where a reference came from (ref-source, Nov 6)

def source_by_path(work, voice, src):
    """Where a clip about to become a reference is, by its path: {kind: 'candidate', voice, n, version} (version
    'current'; 'original', its audio before a ↻ retry; 'earlier', an older version kept in rejected/; 'deleted', a
    candidate since deleted), {kind: 'take', line, take}, {kind: 'recording', name}, or None."""
    src = Path(src).resolve(); work = Path(work).expanduser().resolve()
    d = (work / 'voices' / voice / 'design').resolve()
    m = CAND.match(src.stem)
    if m and src.parent == d: return dict(kind='candidate', voice=voice, n=int(m.group(1)), version='current')
    if m and src.parent == d / 'sources': return dict(kind='candidate', voice=voice, n=int(m.group(1)), version='original')
    if m and src.parent == d / 'rejected':
        n = int(m.group(1)); alive = (d / f'cand_{n}.wav').exists()
        return dict(kind='candidate', voice=voice, n=n, version='earlier' if alive else 'deleted')
    if src.parent.parent == (work / 'takes').resolve(): return dict(kind='take', line=src.parent.name, take=src.name)
    if src.parent == (work / 'performances').resolve(): return dict(kind='recording', name=src.stem)
    return None


_digests = {}


def _digest(p):
    st = p.stat(); k = (str(p), st.st_size, st.st_mtime)
    if k not in _digests: _digests[k] = hashlib.md5(p.read_bytes()).hexdigest()
    return _digests[k]


def clip_source(work, voice, ref):
    """Where a voice's reference clip came from (as source_by_path), from its <emotion>.json; for one made before that
    was kept, by finding the same audio among its candidates (current, original, older versions and deleted ones)
    and every take. A reference is a byte-for-byte copy, and only clips of its exact size are read."""
    ref = Path(ref); side = ref.with_suffix('.json')
    if side.exists():
        try: return json.loads(side.read_text(encoding='utf-8')).get('from')
        except ValueError: pass
    work = Path(work).expanduser(); d = work / 'voices' / voice / 'design'
    size = ref.stat().st_size; want = None
    pools = [sorted(d.glob('cand_*.wav')), sorted((d / 'sources').glob('cand_*.wav')),
             sorted((d / 'rejected').glob('cand_*.wav'), reverse=True), sorted((work / 'takes').glob('*/*.wav'))]
    for pool in pools:
        for p in pool:
            if p.stat().st_size != size: continue
            want = want or _digest(ref)
            if _digest(p) == want: return source_by_path(work, voice, p)
    return None


def clip_label(rel):
    """A clip's name for the page, from its path in the work folder: "lead candidate 24", "lead's neutral reference",
    "take qwen_2 of intro_hello", "your recording intro_hello_p3"."""
    parts = Path(rel or '').parts; stem = Path(rel or '').stem
    if len(parts) == 4 and parts[0] == 'voices' and parts[2] == 'design' and CAND.fullmatch(stem):
        return f'{parts[1]} candidate {stem.split("_")[1]}'
    if len(parts) == 4 and parts[0] == 'voices' and parts[2] == 'ref': return f'{parts[1]}\'s {stem} reference'
    if len(parts) == 3 and parts[0] == 'takes': return f'take {stem} of {parts[1]}'
    if len(parts) == 2 and parts[0] == 'performances': return f'your recording {stem}'
    return rel or '?'


def note_source(work, voice, src, ref):
    """Records where a new reference came from, beside it (ref/<emotion>.json)."""
    f = Path(ref).with_suffix('.json'); f.write_text(json.dumps({'from': source_by_path(work, voice, src)}, indent=1), encoding='utf-8')
