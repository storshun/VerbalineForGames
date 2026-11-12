"""A line in parts, each in its own tone: the studio's ✂ Parts.

A cue directed tone by tone inside itself, e.g.
'[Urgent]What do you mean they're gone?![/][Sad]Oh my god... all those people, gone...[/][Angry]OK, then we're the
command and control team until further notice.[/]'

A line's parts are written in directions.toml `parts`, in that markup:
  - [tone]words[/]: a part, said in a tone. Tones are the studio's emotions (urgent, sad, angry, shouting, ...), in any
    case, with a few everyday words for them (shout, yelling, whispering, tearful, shocked, ...: ALIASES). [/] is
    optional: the next [tone] ends a part.
  - words outside any tag: a part in the line's own emotion.
  - [pause 0.8] (or [beat]): the silence between two parts, in seconds (default 0.35 s; [pause] or [beat] alone: 0.8 s).
    Inside a part it splits it in two, in the same tone.
  - <...> tags (xAI's <loud>, <whisper>) go to the engine as written.

Text-to-speech can't change tone mid-line: Qwen3-TTS cloning takes its tone from the reference clip it clones. So each
part is made on its own, cloning the voice's reference for its tone (verbaline ref_order: its own, else neutral, calm, its
nearest kin), as tries in takes/<line>/parts/<tone>_<id>/ (an id from the voice, tone and words, so rewording one part
keeps every other part's tries). A whole take is the parts joined in order (join): each trimmed to its voice, the
silence between them the part's own room sound, drawn out, as ⏸ Add a beat does. Which try of each part goes into a
join, and its level, is the mix (parts/mix.json)."""
import hashlib, json, re, time
from pathlib import Path

EMOTIONS = ('neutral', 'calm', 'urgent', 'shouting', 'whisper', 'sad', 'warm', 'playful', 'stunned', 'angry', 'crying',
            'vengeful')                                    # as cli.EMOTIONS
ALIASES = {
    'normal': 'neutral', 'flat': 'neutral', 'plain': 'neutral', 'even': 'neutral',
    'calmly': 'calm', 'steady': 'calm', 'quiet': 'calm',
    'urgency': 'urgent', 'urgently': 'urgent', 'hurried': 'urgent', 'alarmed': 'urgent', 'panicked': 'urgent', 'panic': 'urgent',
    'shout': 'shouting', 'shouted': 'shouting', 'shouts': 'shouting', 'yell': 'shouting', 'yelling': 'shouting', 'loud': 'shouting',
    'whispering': 'whisper', 'whispered': 'whisper', 'whispers': 'whisper', 'hushed': 'whisper',
    'sadly': 'sad', 'sadness': 'sad', 'grief': 'sad', 'grieving': 'sad', 'mournful': 'sad',
    'warmly': 'warm', 'tender': 'warm', 'affectionate': 'warm', 'kind': 'warm',
    'teasing': 'playful', 'amused': 'playful', 'joking': 'playful', 'happy': 'playful',
    'shocked': 'stunned', 'shock': 'stunned', 'disbelief': 'stunned', 'surprised': 'stunned',
    'anger': 'angry', 'angrily': 'angry', 'furious': 'angry', 'mad': 'angry',
    'cry': 'crying', 'cries': 'crying', 'tearful': 'crying', 'sobbing': 'crying', 'weeping': 'crying',
    'cold': 'vengeful', 'fury': 'vengeful', 'menacing': 'vengeful', 'vengeance': 'vengeful',
}
GAP = 0.35                  # the silence between two parts, in seconds, unless a [pause] says otherwise
PAUSE = 0.8                 # [pause] or [beat] without a number
MAX_GAP = 3.0
MAX_PARTS = 12
TAG = re.compile(r'\[([^\[\]]*)\]')


def tone_of(word):
    """'Urgent' -> 'urgent', 'yelling' -> 'shouting'; None for a word that's no tone."""
    w = word.strip().lower()
    return w if w in EMOTIONS else ALIASES.get(w)


def tones_help():
    return ', '.join(EMOTIONS) + ' (or [pause 0.8] for a silence)'


def parse(markup, emotion='neutral'):
    """The parts of a line written in the markup: [dict(tone, tag, text, gap)], where tag is the tone as written (None:
    the line's own emotion, `emotion`) and gap the silence after the part, in seconds (the last part's is 0).
    Raises ValueError, saying what's wrong, on a tag that's no tone or pause, or on nothing to say."""
    markup = (markup or '').strip()
    if not markup: return []
    if emotion not in EMOTIONS: emotion = 'neutral'
    parts, cur, tag, buf, pos = [], emotion, None, [], 0

    def close(gap=None):
        text = ' '.join(''.join(buf).split())
        buf.clear()
        if re.search(r'[A-Za-z0-9]', re.sub(r'<[^<>]*>', '', text)):
            parts.append(dict(tone=cur, tag=tag, text=text, gap=GAP))
        if gap is not None and parts: parts[-1]['gap'] = gap

    for m in TAG.finditer(markup):
        buf.append(markup[pos:m.start()]); pos = m.end()
        inner = m[1].strip()
        if inner == '/':
            close(); cur, tag = emotion, None; continue
        p = re.fullmatch(r'(pause|beat)(?:\s+(\d+(?:\.\d+)?)\s*s?)?', inner, re.I)
        if p:
            secs = float(p[2]) if p[2] else PAUSE
            if secs > MAX_GAP: raise ValueError(f'"[{inner}]": a pause is at most {MAX_GAP:g} s')
            close(secs); continue
        t = tone_of(inner)
        if not t: raise ValueError(f'"[{inner}]" isn\'t a tone. Tones: {tones_help()}')
        close(); cur, tag = t, inner
    buf.append(markup[pos:]); close()
    if not parts: raise ValueError('the parts have no words')
    if len(parts) > MAX_PARTS: raise ValueError(f'at most {MAX_PARTS} parts in a line')
    parts[-1]['gap'] = 0.0
    return parts


def dump(parts):
    """The markup for parts (the tags as written, the gaps that aren't the default as [pause N])."""
    out = []
    for i, p in enumerate(parts):
        # A part without a tag stays without one: it follows the line's emotion.
        out.append(f'[{p["tag"]}]{p["text"]}[/]' if p.get('tag') else p['text'] + ' ')
        if i < len(parts) - 1 and abs(p['gap'] - GAP) > 1e-6: out.append(f'[pause {p["gap"]:g}]')
    return ''.join(out).strip()


def plain(parts):
    """The words the parts say, as the subtitles would show them (no tags)."""
    return ' '.join(' '.join(re.sub(r'<[^<>]*>', '', p['text']).split()) for p in parts).strip()


def part_id(voice, part):
    """The folder a part's tries live in: its tone and a short id of the voice, tone and words (rewording one part, or
    changing a gap, keeps the other parts' tries)."""
    h = hashlib.sha1(f'{voice}|{part["tone"]}|{" ".join(part["text"].split())}'.encode()).hexdigest()[:8]
    return f'{part["tone"]}_{h}'


def folder(work, key, pid=None):
    f = Path(work) / 'takes' / key / 'parts'
    return f / pid if pid else f


def tries(work, key, pid):
    """A part's tries, oldest first: [Path]."""
    d = folder(work, key, pid)
    return sorted(d.glob('*.wav'), key=lambda p: (p.stat().st_mtime, p.name)) if d.exists() else []


def made(work, key, pid):
    f = folder(work, key, pid) / 'made.json'
    return json.loads(f.read_text()) if f.exists() else {}


def note_try(work, key, pid, name, **info):
    f = folder(work, key, pid) / 'made.json'; m = made(work, key, pid)
    m[name] = dict(info, at=time.strftime('%Y-%m-%d %H:%M'))
    tmp = f.with_suffix('.tmp'); tmp.write_text(json.dumps(m, indent=1)); tmp.replace(f)


def mix(work, key):
    """{part id: {try: file name, gain: dB}}: the try of each part a join uses (else its newest) and its level."""
    f = folder(work, key) / 'mix.json'
    return json.loads(f.read_text()) if f.exists() else {}


def save_mix(work, key, m):
    f = folder(work, key) / 'mix.json'; f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix('.tmp'); tmp.write_text(json.dumps(m, indent=1)); tmp.replace(f)


def chosen(work, key, pid):
    """(the try a join uses for this part, its gain in dB): the mix's, else the newest try (None when it has none)."""
    m = mix(work, key).get(pid, {}); have = tries(work, key, pid)
    t = next((p for p in have if p.name == m.get('try')), have[-1] if have else None)
    return t, float(m.get('gain', 0) or 0)


# ------------------------------------------------------------------ joining

def _mono(path):
    import numpy as np, soundfile as sf
    a, sr = sf.read(str(path), dtype='float32', always_2d=True)
    return np.ascontiguousarray(a.mean(1)), sr


def _resample(a, sr, to):
    if sr == to: return a
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(sr, to); return resample_poly(a, to // g, sr // g).astype('float32')


def voiced(a, sr):
    """(start, end) of a clip's voice: from the first to the last 10 ms within 40 dB of its loudest, or the whole clip."""
    import numpy as np
    hop = max(1, sr // 100); n = len(a) // hop
    if n < 2: return 0, len(a)
    level = 20 * np.log10(np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    on = np.flatnonzero(level > level.max() - 40)
    return (on[0] * hop, min(len(a), (on[-1] + 1) * hop)) if len(on) else (0, len(a))


def room(a, sr, secs):
    """`secs` of a clip's own room sound: its quietest 30 ms, looped, faded in and out (⏸ Add a beat's pause)."""
    import numpy as np
    want = int(round(secs * sr))
    if want <= 0: return np.zeros(0, 'float32')
    hop = max(1, sr // 100); n = len(a) // hop
    if n >= 3:
        level = (a[:n * hop].reshape(n, hop) ** 2).mean(1)
        k = int(np.argmin(np.convolve(level, np.ones(3) / 3, 'same')))
        floor = a[max(0, k * hop - hop):k * hop + 2 * hop]
    else: floor = np.zeros(hop * 3, 'float32')
    out = np.resize(floor if len(floor) else np.zeros(hop, 'float32'), want).astype('float32')
    fade = min(int(.01 * sr), want // 2)
    if fade:
        ramp = np.linspace(0, 1, fade, dtype='float32'); out[:fade] *= ramp; out[-fade:] *= ramp[::-1]
    return out


def join(clips, out):
    """Joins clips into one take: clips = [(path, gap after in seconds, gain in dB)]. Each is trimmed to its voice with
    20 ms before it and 60 ms after (faded), the gap counted from the end of one voice to the start of the next and
    filled with the clip's own room sound; the first keeps 0.1 s of lead-in, the last 0.25 s of tail. The whole take is
    brought down only if it would clip. Writes `out` (24-bit) and returns (seconds, [(start, end) of each part's voice
    in the take, in seconds])."""
    import numpy as np, soundfile as sf
    if not clips: raise ValueError('nothing to join')
    sr = None; pieces, spans, t = [], [], 0
    for i, (path, gap, gain) in enumerate(clips):
        a, s = _mono(path)
        if sr is None: sr = s
        a = _resample(a, s, sr) * float(10 ** (float(gain or 0) / 20))
        v0, v1 = voiced(a, sr)
        lead = int((.1 if i == 0 else .02) * sr); tail = int((.25 if i == len(clips) - 1 else .06) * sr)
        s0, s1 = max(0, v0 - lead), min(len(a), v1 + tail)
        seg = a[s0:s1].copy()
        f_in, f_out = min(int(.01 * sr), len(seg) // 4), min(int(.03 * sr), len(seg) // 4)
        if i and f_in: seg[:f_in] *= np.linspace(0, 1, f_in, dtype='float32')
        if i < len(clips) - 1 and f_out: seg[-f_out:] *= np.linspace(1, 0, f_out, dtype='float32')
        spans.append(((t + v0 - s0) / sr, (t + v1 - s0) / sr))
        pieces.append(seg); t += len(seg)
        if i < len(clips) - 1:
            # The gap is voice to voice: this part's tail and the next one's lead-in count towards it.
            fill = room(a, sr, max(0.0, float(gap) - (s1 - v1) / sr - .02))
            pieces.append(fill); t += len(fill)
    y = np.concatenate(pieces).astype('float32')
    peak = float(np.abs(y).max()) if len(y) else 0.0
    if peak > .98: y *= .98 / peak
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), y, sr, subtype='PCM_24')
    return len(y) / sr, [(round(a, 3), round(b, 3)) for a, b in spans]


def next_take(work, key):
    """The next parts_<k>.wav of a line (numbers aren't reused, removed ones count)."""
    d = Path(work) / 'takes' / key
    ks = [int(m[1]) for p in [*d.glob('parts_*.wav'), *d.glob('removed/parts_*.wav')] if (m := re.fullmatch(r'parts_(\d+)', p.stem))]
    return d / f'parts_{1 + max(ks + [0])}.wav'


def join_line(c, r, picks=None):
    """A new whole take of a line from its parts: each part's try from `picks` ({part id: try path}), else the mix's,
    else its newest. Writes takes/<key>/parts_<k>.wav and its made.json entry (the words, the reference it's judged
    against: the longest part's, and each part's tone, try, gap and gain). Returns the take, or raises ValueError when
    a part has no try yet."""
    parts = parse(r.get('parts', ''), r.get('emotion', 'neutral'))
    if not parts: raise ValueError(f'{r["key"]} has no parts')
    work, key = c.work, r['key']; clips, recipe = [], []
    for p in parts:
        pid = part_id(r['voice'], p)
        t, gain = chosen(work, key, pid)
        if picks and picks.get(pid): t = Path(picks[pid])
        if not t or not t.exists(): raise ValueError(f'the {p["tone"]} part "{p["text"][:40]}" has no tries yet')
        info = made(work, key, pid).get(t.name, {})
        clips.append((t, p['gap'], gain))
        recipe.append(dict(tone=p['tone'], text=p['text'], part=pid, take=t.name, gap=p['gap'], gain=gain, ref=info.get('ref', '')))
    out = next_take(work, key)
    secs, spans = join(clips, out)
    for x, (a, b) in zip(recipe, spans): x['at'] = [a, b]
    # The voice is judged against the reference of the part that's longest in the take.
    longest = max(recipe, key=lambda x: x['at'][1] - x['at'][0])
    f = Path(work) / 'takes' / key / 'made.json'; m = json.loads(f.read_text()) if f.exists() else {}
    m[out.name] = dict(text=r['text'], at=time.strftime('%Y-%m-%d %H:%M'), parts=recipe, secs=round(secs, 2),
                       **({'ref': longest['ref']} if longest['ref'] else {}))
    tmp = f.with_suffix('.tmp'); tmp.write_text(json.dumps(m, indent=1)); tmp.replace(f)
    return out
