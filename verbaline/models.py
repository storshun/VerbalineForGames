"""The models behind the studio, each behind a small adapter so a model can be swapped without touching the pipeline.

Every adapter is a context manager: it loads its model on entry and frees the GPU on exit, so two big models are never
resident at once (32 GB is plenty for any one of them). Libraries load lazily, inside the adapters."""
import contextlib, os, random, re, subprocess, sys, tempfile
from pathlib import Path

# How each emotion pushes IndexTTS2: its 8 emotion weights [happy, angry, sad, afraid, disgusted, melancholic, surprised,
# calm]. (Qwen3-TTS cloning has no emotion control of its own: the emotion comes from which reference clip it clones.)
EMOTION = {
    'neutral':  dict(idx=[0, 0, 0, 0, 0, 0, 0, .3]),
    'calm':     dict(idx=[0, 0, 0, 0, 0, 0, 0, .8]),
    'urgent':   dict(idx=[0, .2, 0, .5, 0, 0, .3, 0]),
    'shouting': dict(idx=[0, .7, 0, .2, 0, 0, .3, 0]),
    'whisper':  dict(idx=[0, 0, 0, .3, 0, .2, 0, .5]),
    'sad':      dict(idx=[0, 0, .7, 0, 0, .4, 0, 0]),
    'warm':     dict(idx=[.4, 0, 0, 0, 0, 0, 0, .5]),
    'playful':  dict(idx=[.7, 0, 0, 0, 0, 0, .2, 0]),
    'stunned':  dict(idx=[0, 0, .2, .2, 0, 0, .7, 0]),
    'angry':    dict(idx=[0, .9, 0, 0, .2, 0, 0, 0]),
    # crying, and vengeful: a cold, quiet fury (not a shout).
    'crying':   dict(idx=[0, 0, .8, .2, 0, .5, 0, 0]),
    'vengeful': dict(idx=[0, .6, 0, 0, .4, 0, 0, .4]),
}

# How each emotion is acted when a voice is restyled into it (✦ Restyle's presets; the page offers them, and a line's
# directing notes are added to its own): the words Qwen3-TTS VoiceDesign acts from, and the edits Step-Audio-EditX
# makes in turn (a repeated edit pushes further: its iterative editing).
STYLES = {
    'neutral':  ('Neutral, even and clear', 'emotion:remove'),
    'calm':     ('Calm, steady and low, completely in control', 'style:gentle'),
    'urgent':   ('Urgent and clipped, giving orders fast under pressure', 'style:authority, speed:faster'),
    'shouting': ('Shouting over alarms at the top of the voice', 'style:shout, style:shout'),
    'whisper':  ('Whispering, close and hushed, barely voiced', 'style:whisper, style:whisper'),
    'sad':      ('Sad and quiet, holding back tears', 'emotion:sad, emotion:sad'),
    'warm':     ('Warm and affectionate, smiling while speaking', 'style:warm'),
    'playful':  ('Playful and teasing, light and amused', 'emotion:humour'),
    'stunned':  ('Stunned, breathless disbelief', 'emotion:surprised'),
    'angry':    ('Angry and forceful, every word bitten off', 'emotion:angry, emotion:angry'),
    'crying':   ('Crying, the voice breaking, forcing the words out through tears', 'emotion:sad, emotion:sad, style:soulful'),
    'vengeful': ('Cold, quiet fury through clenched teeth: low, slow and deliberate, never shouting', 'emotion:coldness, emotion:angry, style:murmur'),
}

# Where each emotion sits in a voice's own range, in semitones from its everyday (neutral) pitch: where ✦ Restyle puts
# an acted try. VoiceDesign makes a new voice every try, often far from the voice's own range (measured: a male
# voice's "rushed, excited" tries 10-16 semitones over him, a female lead's "cold, quiet fury" 5 over her), so a try's own pitch says
# little about its acting. A whisper's voiced parts: VoiceDesign's whispers are breathy reads, two thirds voiced, and
# sit 3-8 semitones over the voice until moved. A true whisper has no pitch, and nothing moves.
PITCH = {'neutral': 0, 'calm': -1, 'urgent': 3, 'shouting': 5, 'whisper': -1, 'sad': -1, 'warm': 1, 'playful': 2,
         'stunned': 2, 'angry': 3, 'crying': 3, 'vengeful': -2}

# Step-Audio-EditX's own edit words (its README and tts_infer.py, Jan 2026 release): an edit is "<kind>:<word>".
EDITX = {
    'emotion': ('angry', 'happy', 'sad', 'fear', 'surprised', 'confusion', 'empathy', 'embarrass', 'excited',
                'depressed', 'admiration', 'coldness', 'disgusted', 'humour', 'remove'),
    'style': ('serious', 'arrogant', 'child', 'older', 'girl', 'pure', 'sister', 'sweet', 'exaggerated', 'ethereal',
              'whisper', 'generous', 'recite', 'act_coy', 'warm', 'shy', 'comfort', 'authority', 'chat', 'radio',
              'soulful', 'gentle', 'story', 'vivid', 'program', 'news', 'advertising', 'roar', 'murmur', 'shout',
              'deeply', 'loudly', 'remove'),
    'speed': ('faster', 'slower', 'more faster', 'more slower'),
}


def editx_steps(recipe):
    """'emotion:coldness, style:murmur x2' -> [('emotion', 'coldness'), ('style', 'murmur'), ('style', 'murmur')].
    Raises ValueError on an edit Step-Audio-EditX doesn't know."""
    out = []
    for part in [p.strip() for p in re.split(r'[,;\n]+', recipe or '') if p.strip()]:
        m = re.fullmatch(r'(\w+)\s*:\s*([\w ]+?)\s*(?:[x×]\s*([1-3]))?', part.lower())
        if not m or m[1] not in EDITX or m[2] not in EDITX[m[1]]:
            raise ValueError(f'"{part}" isn\'t a Step-Audio-EditX edit (kind:word, e.g. emotion:angry or style:whisper)')
        out += [(m[1], m[2])] * int(m[3] or 1)
    if not out: raise ValueError('no edits given')
    if len(out) > 6: raise ValueError('at most 6 edits in a row')
    return out


def median_f0(path):
    """A clip's median pitch in Hz over its voiced frames (pYIN), or 0 when it has none (a whisper)."""
    import numpy as np, librosa
    y, sr = librosa.load(str(path), sr=16000)
    f0, _, _ = librosa.pyin(y, fmin=70, fmax=700, sr=sr)
    f0 = f0[~np.isnan(f0)]
    return float(np.median(f0)) if f0.size else 0.0


def free_gpu():
    import gc; gc.collect()
    try:
        import torch
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    except ImportError: pass


def seed_all(seed):
    random.seed(seed)
    try:
        import numpy, torch
        numpy.random.seed(seed); torch.manual_seed(seed)
    except ImportError: pass


def write(out, wav, sr):
    import numpy as np, soundfile as sf
    try: wav = wav.detach().cpu().numpy()
    except AttributeError: pass
    wav = np.asarray(wav, dtype='float32').squeeze()
    Path(out).parent.mkdir(parents=True, exist_ok=True); sf.write(str(out), wav, sr, subtype='PCM_24')


def qwen_budget(text):
    """Most audio tokens a Qwen3-TTS take of this text may use (12.5 per second). Generous: 8 characters a second, the
    slowest real read, plus 3 s. Without it a take that falls into a loop ("the hangar, the hangar, ...") runs to the
    model's 2048-token default, about 2.7 minutes of audio, and holds up every job behind it."""
    return int((len(text) / 8 + 3) * 12.5)


# ------------------------------------------------------------------ voice design (Qwen3-TTS, Apache 2.0)

class QwenDesign:
    """Makes an original voice from a description: Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign."""
    MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
    def __enter__(self):
        import torch
        from qwen_tts import Qwen3TTSModel
        kw = dict(device_map='cuda:0', dtype=torch.bfloat16)
        try: self.m = Qwen3TTSModel.from_pretrained(self.MODEL, attn_implementation='flash_attention_2', **kw)
        except Exception: self.m = Qwen3TTSModel.from_pretrained(self.MODEL, **kw)   # no flash-attn installed
        return self
    def __exit__(self, *_): del self.m; free_gpu()
    STYLE = ' Natural, unhurried read; clean studio recording.'
    def design(self, description, text, out, seed=None, style=None):
        # A recorded seed makes a candidate replayable: the same seed and description with new words (verbaline design --retry).
        # style: how it's read instead of the natural, unhurried default (verbaline restyle's acting).
        if seed is not None: seed_all(seed)
        wavs, sr = self.m.generate_voice_design(text=text, language='English', instruct=description + (self.STYLE if style is None else style),
                                                max_new_tokens=qwen_budget(text))
        write(out, wavs[0], sr)


# ------------------------------------------------------------------ text-to-speech backends

class Qwen:
    """Qwen3-TTS Base (Apache 2.0): clones the reference clip with its transcript. No emotion control of its own:
    the emotion comes from which reference clip is used (voices/<voice>/ref/<emotion>.wav)."""
    MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'
    def __init__(self, ctx): self.ctx = ctx; self.prompts = {}
    def __enter__(self):
        import torch
        from qwen_tts import Qwen3TTSModel
        self.m = Qwen3TTSModel.from_pretrained(self.MODEL, device_map='cuda:0', dtype=torch.bfloat16); return self
    def __exit__(self, *_): del self.m; free_gpu()
    def say(self, text, ref, ref_text, emotion, voice, out, seed=1):
        seed_all(seed)
        if ref not in self.prompts:
            self.prompts[ref] = self.m.create_voice_clone_prompt(ref_audio=str(ref), ref_text=ref_text or None,
                                                                 x_vector_only_mode=not ref_text)
        wavs, sr = self.m.generate_voice_clone(text=text, language='English', voice_clone_prompt=self.prompts[ref],
                                               max_new_tokens=qwen_budget(text))
        write(out, wavs[0], sr)


class IndexTTS2:
    """bilibili IndexTTS2: the strongest emotion control (a vector of 8 emotions). Its license needs checking
    before anything it makes ships; fine for prototyping. Runs from its own checkout (the config's [repos])."""
    def __init__(self, ctx): self.repo = Path(os.path.expanduser(ctx.cfg['repos']['index_tts']))
    def __enter__(self):
        sys.path.insert(0, str(self.repo))
        from indextts.infer_v2 import IndexTTS2 as Model
        self.m = Model(cfg_path=str(self.repo / 'checkpoints' / 'config.yaml'), model_dir=str(self.repo / 'checkpoints'),
                       use_fp16=True)
        return self
    def __exit__(self, *_): del self.m; free_gpu()
    def say(self, text, ref, ref_text, emotion, voice, out, seed=1):
        seed_all(seed); vec = EMOTION.get(emotion, EMOTION['neutral'])['idx']
        self.m.infer(spk_audio_prompt=str(ref), text=text, output_path=str(out), emo_vector=vec, use_random=True)


class XAI:
    """xAI text-to-speech (cloud, paid: about $15 per million characters). Used only for voices whose engine is set to
    "xai" in cast.toml. Needs no reference clip: the voice is one of xAI's (xai_voice), at its speed (xai_speed).
    Direction is done with xAI's inline tags in the line's engine text (directions.toml "say"), e.g. [pause],
    <loud>...</loud>. The key comes from $XAI_API_KEY (for the studio service: ~/.config/verbaline/env)."""
    URL = 'https://api.x.ai/v1/tts'
    # Emotions xAI has a tag for; a line whose engine text already has tags is sent as written.
    TAGS = {'whisper': ('<whisper>', '</whisper>'), 'shouting': ('<loud>', '</loud>')}
    needs_ref = False
    def __init__(self, ctx):
        self.key = os.environ.get('XAI_API_KEY', '')
        if not self.key:
            sys.exit('xAI: no API key. Put XAI_API_KEY=... in ~/.config/verbaline/env (then '
                     'restart the studio service), or export it in your shell.')
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def say(self, text, ref, ref_text, emotion, voice, out, seed=1):
        import json, urllib.request
        if emotion in self.TAGS and '<' not in text and '[' not in text:
            a, b = self.TAGS[emotion]; text = a + text + b
        body = dict(text=text, voice_id=voice.get('xai_voice', 'ursa'), language=voice.get('language', 'en'),
                    speed=float(voice.get('xai_speed', 1.0)), output_format=dict(codec='wav', sample_rate=48000))
        req = urllib.request.Request(self.URL, data=json.dumps(body).encode(), method='POST', headers={
            'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=300) as r: data = r.read()
        except urllib.error.HTTPError as e:
            sys.exit(f'xAI refused the request ({e.code}): {e.read()[:300].decode(errors="replace")}')
        Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(data)


# The text-to-speech engines a voice can use (cast.toml "engine"). Local engines run on this PC; cloud engines send
# the line's text to an online service, and only for voices set to them. Chatterbox was taken out (its output
# fell short); its old takes stay pickable.
ENGINES = {
    'qwen':       dict(label='Qwen3-TTS clone', cloud=False, cls=Qwen),
    'indextts2':  dict(label='IndexTTS2 (license: check)', cloud=False, cls=IndexTTS2),
    'xai':        dict(label='xAI', cloud=True, cls=XAI),
}


def engines(ctx):
    """The engines that can run here: IndexTTS2 only when its checkout exists."""
    repo = Path(os.path.expanduser(ctx.cfg['repos'].get('index_tts', '')))
    return {k: v for k, v in ENGINES.items() if k != 'indextts2' or (repo / 'indextts').exists()}


def backend(name, ctx):
    if name not in ENGINES: sys.exit(f'Unknown engine "{name}": {", ".join(ENGINES)}')
    return ENGINES[name]['cls'](ctx)


# ------------------------------------------------------------------ voice conversion of your performances

class SeedVC:
    """Seed-VC (GPL-3.0; a tool we run, not code we ship): your performance, in the character's voice. Your timing
    is kept exactly. Two models: the timbre model sounds most like the character and sets its pitch itself, in the
    voice's own range, following your intonation loosely (a male performer into a female voice: voice match 0.62, pitch contour r
    0.67-0.77); the pitch-aware model follows your intonation note for note (r 0.97-0.99), moved by a pitch shift,
    and sounds like the character only when the shift lands in the character's range (that voice at +6: 160 Hz, voice match
    0.42-0.47, "a pitch-shifted me"; at +12 to +15: 200-236 Hz, 0.55-0.58). A voice's fine-tuned model (verbaline train)
    is used for the kind it was tuned from."""
    RUNNER = Path(__file__).resolve().parent / 'runners' / 'seedvc_run.py'
    # The base models, by pitch-following or not: (checkpoint in Seed-VC's Hugging Face snapshot, training preset).
    MODELS = {True: ('DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth', 'config_dit_mel_seed_uvit_whisper_base_f0_44k.yml'),
              False: ('DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth', 'config_dit_mel_seed_uvit_whisper_small_wavenet.yml')}
    def __init__(self, repo, steps=30, python=''):
        self.repo, self.steps = repo, steps
        self.python = os.path.expanduser(python) if python else sys.executable   # its own venv, if it has one
        if not (repo / 'inference.py').exists(): sys.exit(f'Seed-VC not found at {repo} ([repos] seed_vc in the config)')
    def base(self, f0):
        """The base model's local checkpoint (no download), or None."""
        return next((self.repo / 'checkpoints' / 'models--Plachta--Seed-VC' / 'snapshots').glob('*/' + self.MODELS[f0][0]), None)
    def convert(self, todo):
        """todo: [(source, target, out, cfg_rate, semitones, f0, tuned)], all converted in one Seed-VC run (its models
        load once, then each conversion takes seconds); f0: the pitch-following model (your intonation, moved by the
        semitones) or the timbre model (it sets the voice's own pitch; semitones unused); tuned: a voice's fine-tuned
        {checkpoint, config, f0} of that model, or None for the base one. Returns the outputs made."""
        import json
        if not todo: return []
        jobs = [dict(source=str(s), target=str(t), out=str(o), cfg_rate=cfg, semitones=st if f0 else 0, f0=f0,
                     steps=self.steps, **({k: m[k] for k in ('checkpoint', 'config')} if m else {}))
                for s, t, o, cfg, st, f0, m in todo]
        names = {str(o): Path(s).name for s, _, o, *_ in todo}; made = []
        with tempfile.TemporaryFile('w+') as err:
            p = subprocess.Popen([self.python, str(self.RUNNER), str(self.repo)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=err, text=True)
            p.stdin.write(json.dumps(jobs)); p.stdin.close()
            for line in p.stdout:
                if line.startswith('ok '):
                    out = line[3:].strip(); made.append(out); print(f'  {names[out]} -> {Path(out).name}', flush=True)
                elif line.startswith('failed '): print('  Seed-VC ' + line.strip(), flush=True)
            if p.wait() or len(made) < len(todo):
                err.seek(0); print(f'  Seed-VC made {len(made)} of {len(todo)}:\n{err.read()[-1500:]}')
        return made


# ------------------------------------------------------------------ restyling a clip itself (Step-Audio-EditX, Apache 2.0)

def editx_missing(ctx):
    """Why Step-Audio-EditX can't run here ('' when it can): its checkout, models and Python (scripts/install_editx.sh
    makes them; the config's [repos] step_audio_editx, step_audio_models, [envs] editx)."""
    r, e = ctx.cfg.get('repos', {}), ctx.cfg.get('envs', {})
    repo, models = Path(os.path.expanduser(r.get('step_audio_editx', ''))), Path(os.path.expanduser(r.get('step_audio_models', '')))
    python = Path(os.path.expanduser(e.get('editx', '')))
    if not r.get('step_audio_editx') or not (repo / 'tts.py').exists(): return 'its code isn\'t installed (scripts/install_editx.sh)'
    if not (models / 'Step-Audio-EditX').is_dir() or not (models / 'Step-Audio-Tokenizer').is_dir():
        return 'its models aren\'t downloaded (scripts/install_editx.sh)'
    if not e.get('editx') or not python.exists(): return 'its Python environment isn\'t installed (scripts/install_editx.sh)'
    return ''


class StepEditX:
    """Step-Audio-EditX (StepFun, Apache 2.0): a 3B audio model that edits how a clip is said (emotion, speaking style,
    speed) and keeps its voice, which comes from the clip's own speaker features; it can also read new words in a
    clip's voice first. Edits can be repeated to push further. Runs in its own Python (vLLM, PyTorch 2.9) through
    editx_run.py, its models loaded once per batch, in one of the PC's GPU slots once 14 GB is free (it holds about
    13 GB: an open game editor can hold much of the card, so it may wait for that)."""
    RUNNER = Path(__file__).resolve().parent / 'runners' / 'editx_run.py'
    def __init__(self, ctx):
        why = editx_missing(ctx)
        if why: sys.exit(f'Step-Audio-EditX can\'t run: {why}')
        r = ctx.cfg['repos']
        self.repo, self.models = Path(os.path.expanduser(r['step_audio_editx'])), Path(os.path.expanduser(r['step_audio_models']))
        self.python = os.path.expanduser(ctx.cfg['envs']['editx'])
        self.slot = os.path.expanduser(ctx.cfg.get('train', {}).get('gpu_slot', '') or '')
    def run(self, jobs):
        """jobs: [dict(out, audio, text, steps=[(kind, info), ...])] (editx_run.py), all in one run. Returns the
        outputs made."""
        import json
        if not jobs: return []
        argv = [self.python, str(self.RUNNER), str(self.repo), str(self.models)]
        if self.slot and Path(self.slot).exists(): argv = [self.slot, '--need', '14000', *argv]   # editx_run.py: about 13 GB
        import collections
        made, tail = [], collections.deque(maxlen=30)
        # Its log and the GPU slot's "waiting for 14000 MiB" come on one stream, so a wait shows on the page.
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        p.stdin.write(json.dumps([dict(j, out=str(j['out']), audio=str(j['audio'])) for j in jobs])); p.stdin.close()
        for line in p.stdout:
            if line.startswith('ok '): made.append(line[3:].strip()); print(f'  edited {len(made)} of {len(jobs)}', flush=True)
            elif line.startswith(('failed ', 'gpu_slot')): print('  ' + line.strip(), flush=True)
            else: tail.append(line.rstrip())
        if p.wait() or len(made) < len(jobs):
            print(f'  Step-Audio-EditX made {len(made)} of {len(jobs)}:\n' + '\n'.join(tail))
        return made


# ------------------------------------------------------------------ scoring takes

WORD = re.compile(r"[a-z0-9']+")
ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen ' \
       'seventeen eighteen nineteen'.split()
TENS = 'twenty thirty forty fifty sixty seventy eighty ninety'.split()


def spell(n):
    n = int(n)
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10 - 2] + ('' if n % 10 == 0 else ' ' + ONES[n % 10])
    return str(n)


def words(text, forgive=()):
    t = text.lower().replace('-', ' ')
    t = re.sub(r'\d+', lambda m: spell(m.group()), t)
    skip = {w.lower() for w in forgive}
    return [w.strip("'") for w in WORD.findall(t) if w.strip("'") and w.strip("'") not in skip]


def wer(ref, hyp):
    if not ref: return 0.0 if not hyp else 1.0
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / len(ref)


class Scorer:
    """Rates a take three ways, each 0..1:
      words:   Whisper's transcript against the script (word error rate; names in pronunciations.toml forgiven)
      voice:   how much it sounds like the voice's reference clip (ECAPA speaker embedding, cosine)
      quality: an estimate of clean, natural audio with no reference needed (torchaudio's SQUIM, PESQ scale)"""
    def __init__(self, whisper_model='large-v3'): self.whisper_model = whisper_model; self.refs = {}
    def __enter__(self):
        import torch
        from faster_whisper import WhisperModel
        from speechbrain.inference.speaker import EncoderClassifier
        from torchaudio.pipelines import SQUIM_OBJECTIVE
        self.asr = WhisperModel(self.whisper_model, device='cuda', compute_type='float16')
        self.spk = EncoderClassifier.from_hparams('speechbrain/spkrec-ecapa-voxceleb', run_opts={'device': 'cuda:0'},
                                                  savedir=str(Path.home() / '.cache' / 'verbaline' / 'ecapa'))
        self.squim = SQUIM_OBJECTIVE.get_model().cuda().eval(); self.torch = torch
        return self
    def __exit__(self, *_): del self.asr, self.spk, self.squim; free_gpu()
    def load16k(self, path):
        import torchaudio
        w, sr = torchaudio.load(str(path)); w = w.mean(0, keepdim=True)
        return torchaudio.functional.resample(w, sr, 16000) if sr != 16000 else w
    def embed(self, path):
        with self.torch.no_grad():
            e = self.spk.encode_batch(self.load16k(path).cuda()).squeeze()
        return e / e.norm()
    def score(self, take, text, ref, forgive):
        segs, _ = self.asr.transcribe(str(take), language='en', beam_size=5)
        heard = ' '.join(s.text.strip() for s in segs)
        w = wer(words(text, forgive), words(heard, forgive))
        voice = 0.0
        if ref:
            if ref not in self.refs: self.refs[ref] = self.embed(ref)
            cos = float((self.embed(take) * self.refs[ref]).sum())
            voice = min(1.0, max(0.0, (cos - .25) / .55))
        with self.torch.no_grad():
            x = self.load16k(take).cuda()
            _, pesq, _ = self.squim(x[:, :16000 * 20])
        quality = min(1.0, max(0.0, (float(pesq) - 1.0) / 3.5))
        return dict(heard=heard, wer=round(w, 3), voice=round(voice, 3), quality=round(quality, 3))
