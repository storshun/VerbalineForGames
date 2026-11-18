"""Checks for Verbaline For Games, with no models and no GPU. They run on a throwaway project (a copy of a small one, made here)
and a temporary work folder, never real takes or picks:

    python tests/test_verbaline.py

The emotion lists agree, every restyle preset is a real Step-Audio-EditX edit, clips are named right, the page's jobs
turn into the right steps (and refuse what they should), mirrored and restyled takes say what they are, a line in
parts is made part by part (a stand-in engine) and joined, and a project hooks up: its lines file (TOML, JSON, CSV),
word edits written back, groups, Apply's export, manifest and copy, and an adapter's hooks and timeline."""
import csv, io, json, os, shutil, sys, tempfile, wave
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # its symbols, on a Windows code page too
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TMP = tempfile.TemporaryDirectory(prefix='verbaline_test_')
PROJECT = Path(TMP.name) / 'project'; WORK = Path(TMP.name) / 'work'
(PROJECT / 'verbaline').mkdir(parents=True); WORK.mkdir()
(PROJECT / 'verbaline.toml').write_text('[project]\nname = "Test"\n\n[lines]\nfile = "lines.toml"\n\n[apply]\ncopy_to = "game/vo"\n', encoding='utf-8')
(PROJECT / 'lines.toml').write_text('''[[line]]
id = "intro_alarm"
group = "intro"
speaker = "Lead"
text = "We'll deal with the POSErs later. All hands, battle stations!"
''', encoding='utf-8')
(PROJECT / 'verbaline' / 'cast.toml').write_text('''[speakers]
"Lead" = "lead"
"Pilot" = "pilot"

[voices.lead]
description = "A test voice."

[voices.pilot]
description = "Another test voice."
''', encoding='utf-8')
(PROJECT / 'verbaline' / 'pronunciations.toml').write_text('[say]\n"POSErs" = "posers"\n', encoding='utf-8')
os.environ['VERBALINE_WORK'] = str(WORK); os.environ['VERBALINE_PROJECT'] = str(PROJECT)
sys.path.insert(0, str(REPO))
from verbaline import cli as vo, server as vo_audition, workfiles as vo_files, models as vo_models, lineparts as vo_parts   # noqa: E402

failures = 0


def check(what, ok):
    global failures
    print(('PASS ' if ok else 'FAIL ') + what)
    failures += not ok


def raises(fn):
    try: fn()
    except (ValueError, KeyError, SystemExit): return True
    return False


def tone(path, secs=0.5):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * int(16000 * secs))
    path.with_suffix('.txt').write_text('This is a test.', encoding='utf-8')


# ------------------------------------------------------------------ the lists agree
check('vo.py and the page server know the same emotions', vo.EMOTIONS == vo_audition.EMOTIONS)
check('crying and vengeful are emotions', {'crying', 'vengeful'} <= set(vo.EMOTIONS))
check('every emotion has a text-to-speech setting', set(vo.EMOTIONS) <= set(vo_models.EMOTION))
check('every emotion has a restyle preset', set(vo.EMOTIONS) <= set(vo_models.STYLES))

# ------------------------------------------------------------------ Chatterbox is out
import tomllib                                                                        # noqa: E402
c0 = vo.Ctx(); cfg = c0.cfg
check('Chatterbox is no engine', 'chatterbox' not in vo_models.ENGINES)
check(f'the default engine is one there is ({cfg["tts"]["backend"]})', cfg['tts']['backend'] in vo_models.ENGINES)
cast_engines = {v: x['engine'] for v, x in c0.cast.get('voices', {}).items() if x.get('engine')}
line_engines = {k: x['engine'] for k, x in c0.dirs.items() if x.get('engine')}
gone = {k: e for k, e in {**cast_engines, **line_engines}.items() if e not in vo_models.ENGINES}
check(f'every voice and line names an engine there is ({gone or "all"})', not gone)
bad = [e for e, (_, r) in vo_models.STYLES.items() if raises(lambda: vo_models.editx_steps(r))]
check(f'every preset is a Step-Audio-EditX edit ({bad or "all"})', not bad)
check('an edit repeats with x2', vo_models.editx_steps('style:whisper x2, emotion:sad') ==
      [('style', 'whisper'), ('style', 'whisper'), ('emotion', 'sad')])
check('an unknown edit is refused', raises(lambda: vo_models.editx_steps('emotion:vengeful')))
check('words that aren\'t edits are refused', raises(lambda: vo_models.editx_steps('make her sound angry')))

# ------------------------------------------------------------------ clip names
for rel, want in (('voices/lead/design/cand_24.wav', 'lead candidate 24'), ('voices/lead/ref/neutral.wav', "lead's neutral reference"),
                  ('takes/intro_alarm/qwen_2.wav', 'take qwen_2 of intro_alarm'),
                  ('performances/intro_alarm_p3.wav', 'your recording intro_alarm_p3')):
    check(f'{rel} reads "{want}"', vo_files.clip_label(rel) == want)

# ------------------------------------------------------------------ the page's jobs
work = WORK
tone(work / 'voices/lead/ref/neutral.wav'); tone(work / 'voices/lead/ref/shouting.wav'); tone(work / 'voices/lead/design/cand_3.wav')
tone(work / 'voices/pilot/ref/neutral.wav'); tone(work / 'takes/intro_alarm/qwen_2.wav'); tone(work / 'performances/intro_alarm_p1.wav')
cols = [c for c in vo.COLUMNS if c != 'parts']
with open(work / 'lines.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, cols); w.writeheader()
    w.writerow(dict(key='intro_alarm', id='intro_alarm', group='intro', speaker='Lead', voice='lead', voice_default='lead',
                    text="We'll deal with the POSErs later. All hands, battle stations!", say="We'll deal with the POSErs later. All hands, battle stations!",
                    emotion='shouting', say_override='', emotion_default='urgent', note='Bravado.', engine='', pitch_shift='', kind='', context=''))


class Jobs:
    def __init__(self): self.added = []
    def add(self, label, steps): self.added.append((label, steps)); return len(self.added)


c = vo.Ctx(); h = vo_audition.Handler.__new__(vo_audition.Handler); h.ctx = c; h.jobs = Jobs()
check('a line set to an engine that is gone is made with the default', c.line_engine(dict(engine='chatterbox', voice='lead')) in vo_models.ENGINES)
h.job(dict(kind='preview', voice='lead', candidate=3))
check(f'a candidate\'s preview is cloned by Qwen3-TTS ({h.jobs.added[-1][1]})', h.jobs.added[-1][1][0][-2:] == ['--backend', 'qwen'])
check('a Chatterbox preview is refused', raises(lambda: h.job(dict(kind='preview', voice='lead', candidate=3, backend='chatterbox'))))
h.job(dict(kind='mirror', key='intro_alarm', **{'from': 'takes/intro_alarm/qwen_2.wav'}, into='voices/lead/ref/shouting.wav'))
label, steps = h.jobs.added[-1]
check(f'a take mirrored into a reference: vo.py mirror into the line, then its score ({steps})',
      steps[0][:5] == ['mirror', '--from', 'takes/intro_alarm/qwen_2.wav', '--into', 'voices/lead/ref/shouting.wav']
      and '--line' in steps[0] and steps[-1] == ['score', '--line', 'intro_alarm'])
h.job(dict(kind='mirror', **{'from': 'voices/lead/design/cand_3.wav'}, into='voices/pilot/ref/neutral.wav', kinds='pitch', shift='-3'))
label, steps = h.jobs.added[-1]
check(f'a candidate mirrored into another voice: new candidates, no score step ({steps})',
      len(steps) == 1 and '--line' not in steps[0] and steps[0][-4:] == ['--kinds', 'pitch', '--shift', '-3'])
check('a recording can be mirrored', not raises(lambda: h.job(dict(kind='mirror', **{'from': 'performances/intro_alarm_p1.wav'}, into='voices/lead/ref/neutral.wav'))))
check('mirror refuses a take as the voice to go into', raises(lambda: h.job(dict(kind='mirror', **{'from': 'voices/lead/ref/neutral.wav'}, into='takes/intro_alarm/qwen_2.wav'))))
check('mirror refuses the same clip', raises(lambda: h.job(dict(kind='mirror', **{'from': 'voices/lead/ref/neutral.wav'}, into='voices/lead/ref/neutral.wav'))))
check('mirror refuses a shift past two octaves', raises(lambda: h.job(dict(kind='mirror', **{'from': 'voices/lead/ref/neutral.wav'}, into='voices/lead/design/cand_3.wav', shift='30'))))
check('mirror refuses a file outside the work folder', raises(lambda: h.job(dict(kind='mirror', **{'from': '../../etc/passwd'}, into='voices/lead/ref/neutral.wav'))))

h.job(dict(kind='restyle', key='intro_alarm', style='Shouting over alarms', n=2))
label, steps = h.jobs.added[-1]
check(f'a line restyled: restyle --line, restyle-keep in its voice, then its score ({[s[0] for s in steps]})',
      steps[0][:3] == ['restyle', '--line', 'intro_alarm'] and steps[1][:3] == ['restyle-keep', '--voice', 'lead']
      and steps[2] == ['score', '--line', 'intro_alarm'] and steps[0][steps[0].index('--tries') + 1] == '6')
h.job(dict(kind='restyle', key='intro_alarm', style='Whispering', **{'from': 'takes/intro_alarm/qwen_2.wav'}))
check('a take of the line can be restyled', '--from' in h.jobs.added[-1][1][0])
h.job(dict(kind='restyle', voice='lead', style='Crying', **{'from': 'voices/lead/design/cand_3.wav'}, n=1))
label, steps = h.jobs.added[-1]
check(f'a candidate restyled: new candidates, no score step ({[s[0] for s in steps]})', len(steps) == 2 and steps[0][1:3] == ['--voice', 'lead'])
check('restyle refuses a take of another line', raises(lambda: h.job(dict(kind='restyle', voice='lead', style='x', **{'from': 'takes/intro_alarm/qwen_2.wav'}))))
check('restyle refuses another voice\'s reference', raises(lambda: h.job(dict(kind='restyle', voice='lead', style='x', **{'from': 'voices/pilot/ref/neutral.wav'}))))
check('a Qwen restyle needs words', raises(lambda: h.job(dict(kind='restyle', key='intro_alarm', style=' '))))
if vo_models.editx_missing(c):
    check('Step-Audio-EditX restyles are refused until it is installed', raises(lambda: h.job(dict(kind='restyle', key='intro_alarm', engine='editx', recipe='style:shout'))))
else:
    check('an unknown Step-Audio-EditX edit is refused', raises(lambda: h.job(dict(kind='restyle', key='intro_alarm', engine='editx', recipe='style:yodel'))))

h.job(dict(kind='retry', voice='lead', candidate=3, text='What the hell are you doing?!'))
label, steps = h.jobs.added[-1]
check(f'↻ reads new words as a new candidate ({steps})', steps == [['design', '--voice', 'lead', '--retry', '3', '--text', 'What the hell are you doing?!']])

h.job(dict(kind='beat', key='intro_alarm', take='takes/intro_alarm/qwen_2.wav', secs=0.6, after_word='later', nth=1))
label, steps = h.jobs.added[-1]
check(f'⏸ a beat after a word, then the line scored ({steps})', steps[0][:3] == ['beat', '--take', 'takes/intro_alarm/qwen_2.wav']
      and steps[0][-4:] == ['--after-word', 'later', '--nth', '1'] and steps[1] == ['score', '--line', 'intro_alarm'])
check('a beat refuses a take of another line', raises(lambda: h.job(dict(kind='beat', key='other_line', take='takes/intro_alarm/qwen_2.wav'))))
check('a beat refuses ten seconds', raises(lambda: h.job(dict(kind='beat', key='intro_alarm', take='takes/intro_alarm/qwen_2.wav', secs=10))))

# ------------------------------------------------------------------ which reference a line without its emotion's clones
check('neutral, then calm, then the nearest kin, never the first by name', vo.ref_order('vengeful')[:4] == ['vengeful', 'neutral', 'calm', 'angry'])
(work / 'voices/lead/ref/neutral.wav').rename(work / 'voices/lead/ref/n.bak')
tone(work / 'voices/lead/ref/angry.wav'); tone(work / 'voices/lead/ref/calm.wav')
check('with neutral gone, a sad line clones calm, not angry', c.ref('lead', 'sad')[0].stem == 'calm')
(work / 'voices/lead/ref/calm.wav').unlink(); (work / 'voices/lead/ref/calm.txt').unlink()
check('...and a shouting line its own', c.ref('lead', 'shouting')[0].stem == 'shouting')
(work / 'voices/lead/ref/n.bak').rename(work / 'voices/lead/ref/neutral.wav')

# ------------------------------------------------------------------ mirrored and restyled takes on the Lines tab
tone(work / 'takes/intro_alarm/mirror_1_pitch_ft.wav'); tone(work / 'takes/intro_alarm/restyle_1.wav')
WORDS = "We'll deal with the POSErs later. All hands, battle stations!"
vo.record_made(c, 'intro_alarm', 'mirror_1_pitch_ft.wav', WORDS, None, 2, target='voices/lead/ref/shouting.wav',
               came='takes/intro_alarm/qwen_2.wav', kind='pitch', tuned=True)
vo.record_made(c, 'intro_alarm', 'restyle_1.wav', WORDS, None, None, target='voices/lead/ref/neutral.wav', style='Crying', engine='qwen')
os.utime(work / 'lines.csv')                                            # newer than the script: no re-export
L = next(x for x in vo_audition.state(c, lambda: None) if x['key'] == 'intro_alarm')
t = {x['name']: x for x in L['takes']}
m = t['mirror_1_pitch_ft.wav']
check(f'a mirrored take reads "{m["source"]}" and says what it came from and whose voice it has ({m["how"]})',
      m['source'] == 'mirror pitch +2 tuned' and m['how']['came'] == 'take qwen_2 of intro_alarm' and m['how']['into'] == "lead's shouting reference")
r = t['restyle_1.wav']
check(f'a restyled take says its style ({r["how"]})', r['source'] == 'restyle' and r['how']['style'] == 'Crying')
check('takes made on purpose (mirrors, restyles) list first', {x['name'] for x in L['takes'][:2]} == {'mirror_1_pitch_ft.wav', 'restyle_1.wav'})

check('the line says which reference "auto" clones', L['ref_auto'] == 'shouting')

# ------------------------------------------------------------------ the Cast tab's facts
vo_files.save_meta(work / 'voices/lead/design/cand_3.wav', dict(method='design', description='x', at='2026-11-06 20:00'))
tone(work / 'voices/lead/design/cand_4.wav'); vo_files.save_meta(work / 'voices/lead/design/cand_4.wav', dict(method='reread', of=3, text='Hello.'))
tone(work / 'voices/lead/design/rejected/cand_3_20261106-150000.wav'); tone(work / 'voices/lead/design/rejected/cand_2_20261106-150000.wav')
V = next(x for x in vo_audition.cast_state(c, lambda: None)['voices'] if x['id'] == 'lead')
c4 = next(x for x in V['candidates'] if x['n'] == 4)
check(f'a re-read says whose voice it is ({c4["reread"]})', c4['reread'] == dict(of=3, text='Hello.'))
check(f'deleted candidates and older versions are counted apart ({V["rejected"]} deleted, {V["older"]} older)', V['rejected'] == 1 and V['older'] == 1)
check(f'an empty emotion says what it falls back to ({V["fallback"].get("whisper")})', V['fallback'].get('whisper') == 'neutral' and 'shouting' not in V['fallback'])
# The page writes paths into its buttons' onclick strings, where a Windows backslash is an escape: with
# voices\lead\design\cand_3.wav, "Use as…" opened nothing. Paths the page gets use forward slashes on every system.
def paths_in(x):
    if isinstance(x, dict): return [p for k, v in x.items() for p in ([v] if k == 'path' and isinstance(v, str) else paths_in(v))]
    if isinstance(x, list): return [p for v in x for p in paths_in(v)]
    return []
cast_paths = paths_in(vo_audition.cast_state(c, lambda: None)); state_paths = paths_in(vo_audition.state(c, lambda: None))
check(f'the page\'s paths use forward slashes ({len(cast_paths)} on the Cast tab, {len(state_paths)} on Lines; e.g. {c4["path"]})',
      cast_paths and c4['path'] == 'voices/lead/design/cand_4.wav' and not any('\\' in p for p in cast_paths + state_paths))


# ------------------------------------------------------------------ review fixes
check('the page gets the fallback order', V and vo_audition.cast_state(c, lambda: None)['orders']['vengeful'][:3] == ['vengeful', 'neutral', 'calm'])
tone(work / 'takes/intro_alarm/qwen_9.wav')
vo.record_made(c, 'intro_alarm', 'qwen_9.wav', WORDS, work / 'voices/lead/ref/shouting.wav')
mk = vo.made_from(c, 'intro_alarm')
mk['qwen_9.wav']['at'] = '2026-10-09 18:55'; c.save_json('takes/intro_alarm/made.json', mk)
check('a take from a reference never replaced is not an older voice', vo_audition.older_ref(c, 'lead', mk['qwen_9.wav']) is None)
tone(work / 'voices/lead/ref/shouting_20261106-190556.wav')
o = vo_audition.older_ref(c, 'lead', mk['qwen_9.wav'])
check(f'one cloned from a reference replaced since is ({o})', o == dict(emotion='shouting', replaced='2026-11-06 19:05'))
check('a mirror says nothing about older voices', vo_audition.older_ref(c, 'lead', mk['mirror_1_pitch_ft.wav']) is None)
for n in ('qwen_2.wav', 'mirror_1_pitch_ft.wav', 'restyle_1.wav'): tone(work / 'takes/intro_alarm' / n, 1.5)   # 1-30 s clips only
sc = {n: dict(wer=0, total=.95, voice=.95) for n in ('qwen_2.wav', 'mirror_1_pitch_ft.wav', 'restyle_1.wav')}
(work / 'takes/intro_alarm/scores.json').write_text(json.dumps(sc), encoding='utf-8')
names = {p.name for p, _ in vo_files.training_clips(work, 'lead')}
check(f'a voice\'s fine-tune never learns from mirrors or restyles ({sorted(names)})', 'qwen_2.wav' in names and not names & {'mirror_1_pitch_ft.wav', 'restyle_1.wav'})

# ------------------------------------------------------------------ warble and dry takes
st = lambda n: 200 * 2 ** (n / 12)                                      # a pitch n semitones over a 200 Hz voice
check('a shout is put 5 semitones over the voice', vo.register_shift(st(0), 200, 'shouting') == 5)
check('a try 14 over (VoiceDesign\'s own voice) comes down to angry\'s +3', vo.register_shift(st(14), 200, 'angry') == -11)
check('a cold threat sits 2 under, wherever the try was', vo.register_shift(st(5), 200, 'vengeful') == -7)
check('a breathy whisper\'s voiced parts sit 1 under; a true whisper (no pitch) never moves',
      vo.register_shift(st(6), 200, 'whisper') == -7 and vo.register_shift(0, 200, 'whisper') == 0 and vo.register_shift(0, 200, 'angry') == 0)
check('a free style goes halfway, at most 5 over', vo.register_shift(st(6), 200, '') == -3 and vo.register_shift(st(16), 200, '') == -11)
check('...and at most 3 under', vo.register_shift(st(-10), 200, '') == 7)
check('never more than an octave', vo.register_shift(st(20), 200, 'angry') == -12)
T = lambda n, m, q, lv=-20: dict(file=n, match=m, quality=q, level=lv)
dry, acted, off = T('dry', .97, .80), T('acted', .70, .90), T('off', .40, .95)
check('a restyle keeps its cleanest tries in the voice, not the closest to the source (the least acted)',
      [t['file'] for t in vo.keep_order([dry, acted, off], 'angry')] == ['acted', 'dry'])
check('a whisper keeps its quietest tries that still match', [t['file'] for t in vo.keep_order(
      [T('loud', .8, .9, -18), T('hushed', .35, .8, -34), T('lost', .2, .9, -40)], 'whisper')] == ['hushed', 'loud'])
check('Step-Audio-EditX\'s edits pass at 0.3', [t['file'] for t in vo.keep_order([off], 'angry', editx=True)] == ['off'])
check('with none in the voice, the closest', [t['file'] for t in vo.keep_order([T('a', .3, .9), T('b', .45, .5)], 'angry')] == ['b', 'a'])
h.job(dict(kind='restyle', key='intro_alarm', style='Angry', n=2))
label, steps = h.jobs.added[-1]
check(f'a restyle reads its conversions again cleanly by default ({label})', '--raw' not in steps[0] and 'reads it again cleanly' in label)
h.job(dict(kind='restyle', key='intro_alarm', style='Angry', n=2, raw=True))
check('...or keeps them as they are', '--raw' in h.jobs.added[-1][1][0])
h.job(dict(kind='restyle', key='intro_alarm', engine='editx', recipe='style:shout', raw=True)) if not vo_models.editx_missing(c) else None
check('a Step-Audio-EditX restyle has no conversion to keep raw', vo_models.editx_missing(c) or '--raw' not in h.jobs.added[-1][1][0])
for n in ('qwen_3.wav', 'qwen_4.wav'): tone(work / 'takes/intro_alarm' / n, 1.5)
sc.update({'qwen_2.wav': dict(wer=0, total=.97, voice=1, quality=.9), 'qwen_3.wav': dict(wer=0, total=.82, voice=.7, quality=.85),
           'qwen_4.wav': dict(wer=.5, total=0, voice=.9, quality=.9)})
(work / 'takes/intro_alarm/scores.json').write_text(json.dumps(sc), encoding='utf-8')
for k, n in enumerate(('qwen_9.wav', 'qwen_2.wav', 'qwen_3.wav', 'qwen_4.wav')):
    os.utime(work / 'takes/intro_alarm' / n, (1e9 + k, 1e9 + k))  # qwen_4 the newest
L = next(x for x in vo_audition.state(c, lambda: None) if x['key'] == 'intro_alarm')
order = [x['name'] for x in L['takes'] if x['source'] == 'qwen']
check(f'the engines\' takes list newest first, not by score, words wrong last ({order})', order == ['qwen_3.wav', 'qwen_2.wav', 'qwen_9.wav', 'qwen_4.wav'])
vo_files.save_meta(work / 'voices/lead/design/cand_3.wav', dict(method='restyle', style='Angry', engine='qwen', reread=True, match=.8))
V = next(x for x in vo_audition.cast_state(c, lambda: None)['voices'] if x['id'] == 'lead')
check('a restyled candidate says it was read again cleanly', next(x for x in V['candidates'] if x['n'] == 3)['restyle']['reread'] is True)

# ------------------------------------------------------------------ ✂ a line in parts, each in its own tone
import numpy as np, soundfile as sf                                                   # noqa: E402
EXAMPLE = ("[Urgent]What do you mean they're gone?![/][Sad]Oh my god... all those people, gone...[/][Angry]OK, then we're "
           "the command and control team until further notice.[/][Shouting]Grab a duty station and get a sit-rep from your "
           "team! All Decks, battle stations![/]")
P = vo_parts.parse(EXAMPLE, 'neutral')
check(f'The example reads as four parts in four tones ({[x["tone"] for x in P]})', [x['tone'] for x in P] == ['urgent', 'sad', 'angry', 'shouting'])
check('...each with its words, the default gap between them and none after the last',
      P[1]['text'] == 'Oh my god... all those people, gone...' and [x['gap'] for x in P] == [vo_parts.GAP] * 3 + [0])
check('...and its words are the line\'s, without the tags', vo_parts.plain(P).startswith("What do you mean they're gone?! Oh my god..."))
Q = vo_parts.parse('Status? [yelling]Get down![pause 1.2]Now![/] [beat] [whispering]they\'re here', 'calm')
check(f'words outside a tag take the line\'s emotion, everyday words name tones, a pause splits a part ({[(x["tone"], x["text"], x["gap"]) for x in Q]})',
      [(x['tone'], x['text'], x['gap']) for x in Q] == [('calm', 'Status?', vo_parts.GAP), ('shouting', 'Get down!', 1.2),
                                                         ('shouting', 'Now!', vo_parts.PAUSE), ('whisper', "they're here", 0)])
check('[Sad] without [/] runs to the next tone', [x['tone'] for x in vo_parts.parse('[sad]a [angry]b')] == ['sad', 'angry'])
check('xAI\'s <loud> tags go to the engine but not the words', vo_parts.plain(vo_parts.parse('[urgent]<loud>Move</loud> it[/]')) == 'Move it')
check('a tag that is no tone is refused, saying the tones', raises(lambda: vo_parts.parse('[Resigned]fine.')))
check('a pause over 3 s is refused', raises(lambda: vo_parts.parse('[sad]a[/][pause 5][sad]b[/]')))
check('parts with no words are refused', raises(lambda: vo_parts.parse('[sad][/][pause]')))
D = vo_parts.dump(Q)
check(f'parts written back read the same ({D})', vo_parts.parse(D, 'calm') == Q)
ids = [vo_parts.part_id('lead', x) for x in P]
P2 = vo_parts.parse(EXAMPLE.replace('gone...[/]', 'gone...[/][pause 1]').replace('OK, then', 'Right, then'), 'neutral')
ids2 = [vo_parts.part_id('lead', x) for x in P2]
check('rewording one part, or a new gap, keeps the other parts\' tries', ids2[0] == ids[0] and ids2[1] == ids[1] and ids2[3] == ids[3] and ids2[2] != ids[2])
check('a part in another voice is another part', vo_parts.part_id('second', P[0]) != ids[0])
check('the page refuses parts it can\'t read', raises(lambda: vo_audition.check_parts('[Resigned]fine.', 'neutral')))
check('...and saves a line\'s parts on one line', vo_audition.check_parts('[sad]a\n[angry]b', 'neutral') == '[sad]a [angry]b')


def speech(path, secs, lead=.4, tail=.6, sr=24000, f=220.0):
    """A clip like a take: room noise, then `secs` of a voice-like tone, then room noise."""
    n0, n1, n2 = int(lead * sr), int(secs * sr), int(tail * sr); rng = np.random.default_rng(int(secs * 1000))
    y = rng.normal(0, .001, n0 + n1 + n2).astype('float32')
    t = np.arange(n1) / sr; y[n0:n0 + n1] += (.3 * np.sin(2 * np.pi * f * t) * np.hanning(n1) ** .1).astype('float32')
    path.parent.mkdir(parents=True, exist_ok=True); sf.write(str(path), y, sr, subtype='PCM_16')


jd = work / 'join'; speech(jd / 'a.wav', 1.0); speech(jd / 'b.wav', 1.5, lead=.9); speech(jd / 'c.wav', .8, sr=16000)
secs, spans = vo_parts.join([(jd / 'a.wav', .5, 0), (jd / 'b.wav', 1.2, -6), (jd / 'c.wav', 0, 0)], jd / 'out.wav')
gaps = [round(b[0] - a[1], 2) for a, b in zip(spans, spans[1:])]
check(f'joined parts: the gaps are voice to voice as asked ({gaps})', all(abs(g - w) < .04 for g, w in zip(gaps, (.5, 1.2))))
check(f'...each part keeps its length ({[round(b - a, 2) for a, b in spans]})', all(abs((b - a) - w) < .05 for (a, b), w in zip(spans, (1.0, 1.5, .8))))
y, sr = sf.read(str(jd / 'out.wav'))
check(f'...its long silences are trimmed, a clip at another rate is resampled ({secs:.2f} s at {sr} Hz)', sr == 24000 and abs(secs - (.1 + 1 + .5 + 1.5 + 1.2 + .8 + .25)) < .06)
lv = lambda a, b: 20 * np.log10(np.sqrt(np.mean(y[int(a * sr):int(b * sr)] ** 2)))
check(f'...a part 6 dB down is 6 dB down ({lv(*spans[1]) - lv(*spans[0]):.1f} dB)', abs(lv(*spans[1]) - lv(*spans[0]) + 6) < .7)
mid = (spans[0][1] + spans[1][0]) / 2
check(f'...and the gap is the take\'s own room sound, not digital silence ({lv(mid - .1, mid + .1):.0f} dB)', -80 < lv(mid - .1, mid + .1) < -45)

# The parts made: a fake engine stands in for Qwen3-TTS (a tone as long as the words), so no voice is generated.
KEY = 'storm_gone'
tone(work / 'voices/lead/ref/sad.wav'); tone(work / 'voices/lead/ref/urgent.wav')
with open(work / 'lines.csv', newline='', encoding='utf-8') as f: rows = list(csv.DictReader(f))
rows.append(dict(rows[0], key=KEY, id=KEY, group='storm', text=vo_parts.plain(P), say=vo_parts.plain(P), emotion='urgent', note=''))
for r in rows: r['parts'] = EXAMPLE if r['key'] == KEY else ''
with open(work / 'lines.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, cols + ['parts']); w.writeheader(); w.writerows(rows)
said = []


class FakeTTS:
    def __init__(self, *a): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def say(self, text, ref, ref_text, emotion, voice, out, seed=1):
        said.append((text, Path(ref).stem, emotion)); speech(Path(out), .05 * len(text.split()) + .3, f=180 + 20 * seed)


real_backend = vo_models.backend; vo_models.backend = lambda name, ctx: FakeTTS()
import argparse                                                                       # noqa: E402
A = lambda **k: argparse.Namespace(**dict(dict(voice=None, group=None, line=KEY, keys=None, todo=False, regen=False, all=True,
                                               more=True, takes=2, backend='qwen', engine=None, ref=None, part=None), **k))
vo.cmd_tts(c, A())
pid = [vo_parts.part_id('lead', x) for x in P]
check(f'Generate on a line in parts: 2 tries of each of its 4 parts ({len(said)} said)', len(said) == 8
      and all(len(vo_parts.tries(work, KEY, i)) == 2 for i in pid))
check(f'...each part cloning its tone\'s reference, else what it falls back to ({sorted({(e, r) for _, r, e in said})})',
      {(e, r) for _, r, e in said} == {('urgent', 'urgent'), ('sad', 'sad'), ('angry', 'angry'), ('shouting', 'shouting')})
check('...each part read with the pronunciations, its "..." a pause', said[2][0] == 'Oh my god, all those people, gone')
whole = sorted(x.name for x in (work / 'takes' / KEY).glob('parts_*.wav'))
mk = vo.made_from(c, KEY)
check(f'...joined into 2 whole takes, try k of every part ({whole})', whole == ['parts_1.wav', 'parts_2.wav']
      and [x['take'] for x in mk['parts_2.wav']['parts']] == ['qwen_2.wav'] * 4 and mk['parts_1.wav']['text'] == vo_parts.plain(P))
check(f'...judged against the reference of its longest part ({mk["parts_1.wav"].get("ref")})', mk['parts_1.wav'].get('ref') == 'shouting')
said.clear(); h.export = lambda: None
os.utime(work / 'lines.csv')
h.post('/api/parts/mix', dict(key=KEY, part=pid[0], **{'try': 'qwen_1.wav'}))
h.post('/api/parts/mix', dict(key=KEY, part=pid[3], gain=-4))
vo.cmd_tts(c, A(part=pid[1]))
mk = vo.made_from(c, KEY); new = sorted(set(mk) - {'parts_1.wav', 'parts_2.wav'}, key=lambda n: int(n[6:-4]))
check(f'↻ on one part: 2 tries of only that part ({[e for _, _, e in said]})', [e for _, _, e in said] == ['sad', 'sad']
      and len(vo_parts.tries(work, KEY, pid[1])) == 4 and len(vo_parts.tries(work, KEY, pid[0])) == 2)
check(f'...each joined with the other parts\' choices: the mix\'s try and level, else the newest ({[[x["take"] for x in mk[n]["parts"]] for n in new]})',
      [[x['take'] for x in mk[n]['parts']] for n in new] == [['qwen_1.wav', 'qwen_3.wav', 'qwen_2.wav', 'qwen_2.wav'],
                                                             ['qwen_1.wav', 'qwen_4.wav', 'qwen_2.wav', 'qwen_2.wav']]
      and mk[new[0]]['parts'][3]['gain'] == -4)
check('the mix refuses a try that isn\'t there', raises(lambda: h.post('/api/parts/mix', dict(key=KEY, part=pid[0], **{'try': 'qwen_9.wav'}))))
check('...and a level past 12 dB', raises(lambda: h.post('/api/parts/mix', dict(key=KEY, part=pid[0], gain=20))))
r = h.post('/api/parts/join', dict(key=KEY))
check(f'Join the chosen tries: a new take at once, and a score job ({r["take"]}, {h.jobs.added[-1][1]})',
      r['take'] == f'takes/{KEY}/parts_5.wav' and h.jobs.added[-1][1] == [['score', '--line', KEY]])
h.post('/api/parts/mix', dict(key=KEY, part=pid[0], **{'try': ''}))
r = h.post('/api/parts/mix', dict(key=KEY, from_take=f'takes/{KEY}/parts_1.wav'))
check(f'✂ Use its parts: a joined take\'s tries become the mix ({r})', r == dict(kept=4, parts=4)
      and all(vo_parts.chosen(work, KEY, i)[0].name == 'qwen_1.wav' for i in pid) and vo_parts.chosen(work, KEY, pid[3])[1] == 0)
L = next(x for x in vo_audition.state(c, lambda: None) if x['key'] == KEY)
check(f'the page gets the parts, their tries, the chosen one and the reference each clones ({[(x["tone"], len(x["tries"]), x["chosen"], x["ref"]) for x in L["parts"]]})',
      [(x['tone'], len(x['tries']), x['chosen'], x['ref']) for x in L['parts']] ==
      [('urgent', 2, 'qwen_1.wav', 'urgent'), ('sad', 4, 'qwen_1.wav', 'sad'), ('angry', 2, 'qwen_1.wav', 'angry'), ('shouting', 2, 'qwen_1.wav', 'shouting')])
jt = next(x for x in L['takes'] if x['name'] == 'parts_3.wav')
check(f'a joined take says which try of each part it has ({jt["how"]})', jt['source'] == 'parts' and jt['how']['kind'] == 'parts'
      and [(x['tone'], x['n']) for x in jt['how']['parts']] == [('urgent', '1'), ('sad', '3'), ('angry', '2'), ('shouting', '2')])
check('no joined take has old words', not any(x['old'] for x in L['takes'] if x['source'] == 'parts'))
(work / 'voices/lead/ref/angry.wav').rename(work / 'voices/lead/ref/a.bak')
L = next(x for x in vo_audition.state(c, lambda: None) if x['key'] == KEY)
check(f'a tone without its reference says what it clones instead ({L["parts"][2]["ref"]})', L['parts'][2]['ref'] == 'neutral')
(work / 'voices/lead/ref/a.bak').rename(work / 'voices/lead/ref/angry.wav')
h.job(dict(kind='tts', key=KEY, voice='lead', n=2, part=pid[1]))
label, steps = h.jobs.added[-1]
check(f'↻ 2 more of a part: vo.py tts --part, then the line scored ({label})', steps[0][-2:] == ['--part', pid[1]] and '--more' in steps[0]
      and steps[1] == ['score', '--line', KEY] and 'sad part' in label)
check('a part that isn\'t a part id is refused', raises(lambda: h.job(dict(kind='tts', key=KEY, voice='lead', part='../x'))))
vo_models.backend = real_backend

# ------------------------------------------------------------------ a project hooks up
from verbaline import project as projects                                           # noqa: E402
import tomllib                                                                         # noqa: E402

LINES = [dict(id='a_1', group='a', speaker='Lead', text='First words.'), dict(id='b_1', group='b', speaker='Pilot', text='Second words.', emotion='calm')]
d = Path(TMP.name) / 'files'; d.mkdir()
(d / 'l.toml').write_text('# kept comment\n' + ''.join(f'[[line]]\nid = "{l["id"]}"\ngroup = "{l["group"]}"\nspeaker = "{l["speaker"]}"\ntext = "{l["text"]}"\n\n' for l in LINES), encoding='utf-8')
(d / 'l.json').write_text(json.dumps(dict(lines=LINES)), encoding='utf-8')
(d / 'k.json').write_text(json.dumps({l['id']: {k: v for k, v in l.items() if k != 'id'} for l in LINES}), encoding='utf-8')
with open(d / 'l.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, ['id', 'group', 'speaker', 'text', 'emotion']); w.writeheader(); w.writerows(LINES)
for name in ('l.toml', 'l.json', 'k.json', 'l.csv'):
    fl = projects.FileLines(d / name); got = fl.lines()
    check(f'a lines file ({name}) reads every line with its fields', [(x['id'], x['speaker'], x['text'], x.get('group')) for x in got]
          == [(l['id'], l['speaker'], l['text'], l['group']) for l in LINES])
    fl.set_words(['b_1'], 'New words, "quoted".')
    check(f'...and takes word edits back ({name})', next(x for x in fl.lines() if x['id'] == 'b_1')['text'] == 'New words, "quoted".'
          and next(x for x in fl.lines() if x['id'] == 'a_1')['text'] == 'First words.')
    check(f'...refusing a line it doesn\'t have ({name})', raises(lambda: fl.set_words(['nope'], 'x')))
check('a TOML lines file keeps its comments through an edit', (d / 'l.toml').read_text(encoding='utf-8').startswith('# kept comment'))

pj = Project = projects.Project(PROJECT)
check(f'the project is found from $VERBALINE_PROJECT ({projects.find()})', projects.find() == PROJECT.resolve())   # Windows: temp is a short 8.3 name (RUNNER~1)
check(f'its work folder is $VERBALINE_WORK ({pj.work_dir()})', pj.work_dir() == WORK)
check('its config layers over the defaults', pj.cfg['apply']['copy_to'] == 'game/vo' and pj.cfg['tts']['takes'] == 8 and pj.name == 'Test')
bad = Path(TMP.name) / 'bad'; bad.mkdir(); (bad / 'verbaline.toml').write_text('[lines]\nfile = "l.toml"\n', encoding='utf-8')
for i, (txt, why) in enumerate((('id = "has space"\nspeaker = "x"\ntext = "y"', 'an id with a space'),
                               ('id = "a"\nspeaker = "x"\ntext = ""', 'a line with no words'),
                               ('id = "a"\nspeaker = "x"\ntext = "y"\n[[line]]\nid = "a"\nspeaker = "x"\ntext = "z"', 'an id used twice'),
                               ('id = "aux"\nspeaker = "x"\ntext = "y"', 'an id Windows reserves (aux)'),
                               ('id = "con.intro"\nspeaker = "x"\ntext = "y"', 'an id Windows reserves with a dot after it (con.intro)'),
                               ('id = "end."\nspeaker = "x"\ntext = "y"', 'an id ending in a dot'),
                               ('id = "Intro"\nspeaker = "x"\ntext = "y"\n[[line]]\nid = "intro"\nspeaker = "x"\ntext = "z"', 'ids that differ only in case'))):
    (bad / 'l.toml').write_text('[[line]]\n' + txt + '\n', encoding='utf-8')
    check(f'lines are refused with {why}', raises(lambda: projects.Project(bad).lines(None)))
(bad / 'l.toml').write_bytes('[[line]]\nid = "a"\nspeaker = "Zoë"\ntext = "Déjà vu"\n'.encode('cp1252'))
try: projects.Project(bad).lines(None); why = ''
except ValueError as e: why = str(e)
check(f'a lines file saved in Windows\' code page says how to save it as UTF-8 ({why[:60]}...)', 'CSV UTF-8' in why)
(bad / 'l.toml').write_bytes(b'\xef\xbb\xbf[[line]]\r\nid = "a"\r\nspeaker = "Zo\xc3\xab"\r\ntext = "y"\r\n')
check('a lines file with a byte-order mark and Windows line ends reads fine', projects.Project(bad).lines(None)[0]['speaker'] == 'Zoë')
(bad / 'verbaline.toml').write_text('[lines]\nfile = "l.csv"\n', encoding='utf-8')
(bad / 'l.csv').write_bytes(b'\xef\xbb\xbfid,speaker,text\r\na,Ada,"Two lines:\r\nhere"\r\nb,Ada,One\r\n')
rows = projects.Project(bad).lines(None)
check(f'an Excel CSV (byte-order mark, CRLF, a quoted line break) reads as its lines ({[r["id"] for r in rows]})', [r['id'] for r in rows] == ['a', 'b'] and rows[0]['text'] == 'Two lines:\r\nhere')
(bad / 'verbaline.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
check('a project with neither a lines file nor an adapter is refused', raises(lambda: projects.Project(bad)))

# The whole loop on the throwaway project: lines, a pick, Apply (copy_to), the manifest, and what the page says.
c = vo.Ctx(PROJECT); c.dirs.clear()
A2 = lambda **k: argparse.Namespace(**dict(dict(voice=None, group=None, line=None, keys=None, todo=False, lang=None, force=False, no_test=False), **k))
vo.cmd_lines(c, A2())
rows = c.lines()
check(f'lines: the project\'s line with its speaker\'s voice and its pronunciation in what the engine reads ({rows[0]["say"]})',
      len(rows) == 1 and rows[0]['voice'] == 'lead' and rows[0]['group'] == 'intro' and 'posers' in rows[0]['say'])
check('groups.json names the project\'s groups', c.json('groups.json', []) == [dict(id='intro', title='intro', timeline=False)])
speech(WORK / 'takes/intro_alarm/qwen_1.wav', 1.2)
c.save_json('picks.json', {'intro_alarm': dict(take='takes/intro_alarm/qwen_1.wav')})
S0 = vo_audition.state(c, lambda: None)
check('before Apply a file project tracks picks, not words (the game reads the same lines file)', not S0[0]['pending'] and S0[0]['pick_pending'])
hp = vo_audition.Handler.__new__(vo_audition.Handler); hp.ctx = c; hp.jobs = Jobs(); hp.export = lambda: None
check('a pick must name a take of its line as a work path', raises(lambda: hp.post('/api/pick', dict(key='intro_alarm', take='qwen_1.wav')))
      and raises(lambda: hp.post('/api/pick', dict(key='intro_alarm', take='takes/intro_alarm/nope_9.wav'))))
check('...of a line there is', raises(lambda: hp.post('/api/pick', dict(key='no.such', take='takes/intro_alarm/qwen_1.wav'))))
hp.post('/api/pick', dict(key='intro_alarm', take='takes/intro_alarm/qwen_1.wav'))
check('...and a real one is saved', c.json('picks.json', {})['intro_alarm']['take'] == 'takes/intro_alarm/qwen_1.wav')
vo.cmd_apply(c, A2())
m = json.loads((PROJECT / 'game/vo/manifest.json').read_text(encoding='utf-8'))
e = m['lines'].get('intro_alarm', {})
check(f'Apply copies the mastered pick and manifest.json into copy_to ({sorted(x.name for x in (PROJECT / "game/vo").iterdir())})',
      (PROJECT / 'game/vo/intro_alarm.wav').exists() and e.get('file') == 'intro_alarm.wav')
check(f'...the manifest says the words, speaker, group, voice, take and length ({e})', e.get('speaker') == 'Lead' and e.get('group') == 'intro'
      and e.get('voice') == 'lead' and e.get('take') == 'takes/intro_alarm/qwen_1.wav' and 1.0 < e.get('seconds', 0) < 1.6 and m['project'] == 'Test')
S1 = vo_audition.state(c, lambda: None)
check('after Apply the page has nothing pending', not S1[0]['pending'] and not S1[0]['pick_pending'])
c.save_json('picks.json', {})
check('without a game_state hook an un-pick is not marked as waiting (only the hook says what the game has now)',
      not vo_audition.state(c, lambda: None)[0]['unpick_pending'])
c.save_json('picks.json', {'intro_alarm': dict(take='takes/intro_alarm/qwen_1.wav')})
(PROJECT / 'verbaline.toml').write_text((PROJECT / 'verbaline.toml').read_text(encoding='utf-8') + 'words_from_manifest = true\n', encoding='utf-8'); c.reload()
(PROJECT / 'lines.toml').write_text((PROJECT / 'lines.toml').read_text(encoding='utf-8').replace('battle stations!', 'action stations!'), encoding='utf-8')
vo.cmd_lines(c, A2())
check('with words_from_manifest, a line whose words changed since Apply is "not in the game yet"', vo_audition.state(c, lambda: None)[0]['pending'])
c.project.cfg['apply'] = dict(label='x', command=['{python}', '-c', 'import sys, json; json.load(open(sys.argv[1], encoding="utf-8")); print("imported", sys.argv[2])', '{manifest}', '{language}'])
check('Apply runs [apply] command with its placeholders filled', not raises(lambda: vo.cmd_apply(c, A2())))
c.project.cfg['apply'] = dict(label='x', command=['{python}', '-c', 'raise SystemExit(3)'])
check('...and stops when the command fails', raises(lambda: vo.cmd_apply(c, A2())))

speech(WORK / 'takes/intro_alarm/qwen_2.wav', 1.0); c.save_json('picks.json', {'intro_alarm': dict(take='takes/intro_alarm/qwen_2.wav')})
(WORK / 'takes/intro_alarm/qwen_2.wav').unlink()
c.project.cfg['apply'] = dict(label='x', copy_to='game/vo')
check('Apply fails when a pick\'s take is gone', raises(lambda: vo.cmd_apply(c, A2())))
check('...and doesn\'t record it as applied, so the page still says the game lacks it',
      c.json('applied.json', {})['picks'].get('intro_alarm') is None and vo_audition.state(c, lambda: None)[0]['pick_pending'])
c.save_json('picks.json', {})

# The adapter example: every hook, and its timeline in the shape the page draws.
ex = Path(TMP.name) / 'adapter'; shutil.copytree(REPO / 'examples/adapter', ex)
os.environ['VERBALINE_PROJECT'] = str(ex); os.environ['VERBALINE_WORK'] = str(Path(TMP.name) / 'work2')
ca = vo.Ctx(ex); vo.cmd_lines(ca, A2())
ra = ca.lines(); ga = ca.json('groups.json', [])
check(f'the adapter example: its lines, voices and scenes ({len(ra)} lines, {[g["id"] for g in ga]})', len(ra) == 6 and {r['voice'] for r in ra} == {'ada', 'purser', 'stranger'}
      and [g['id'] for g in ga] == ['dock', 'deck'] and all(g['timeline'] for g in ga))
check('the page gets a line\'s kind and context', next(x for x in vo_audition.state(ca, lambda: None) if x['key'] == 'dock_01')['context'] == 'Scene 1: The dock')
check('...a mood the script names is the line\'s emotion', next(r for r in ra if r['id'] == 'dock_04')['emotion'] == 'whisper')
ca.project.set_words(ca, ['dock_02'], 'One to the island, please.', ra)
check('...word edits go back into its scene file', 'One to the island, please.' in (ex / 'game/scenes.json').read_text(encoding='utf-8'))
T = ca.project.timeline(ca, 'dock', {'pace': '2'})
check(f'...its timeline: lines in order with their moments, events, an end ({len(T["lines"])} lines, {len(T["events"])} events)',
      [l['id'] for l in T['lines']] == ['dock_01', 'dock_02', 'dock_03', 'dock_04'] and T['end']['t'] > T['lines'][-1]['start']
      and all(b['start'] >= a['end'] for a, b in zip(T['lines'], T['lines'][1:])))
check('...each event kind it uses is described, and its options say their value', {e['kind'] for e in T['events']} <= set(T['kinds'])
      and T['options'][0]['value'] == '2')
speech(Path(ca.path('takes/dock_01/qwen_1.wav')), 2.0)
ca.save_json('picks.json', {'dock_01': dict(take='takes/dock_01/qwen_1.wav')})
vo.cmd_apply(ca, A2())
words, picks = ca.project.game_state(ca)
check(f'...its Apply writes the game\'s voice table, which its game_state reads back ({picks})', picks == {'dock_01': 'takes/dock_01/qwen_1.wav'} and words['dock_01'].startswith('Last call'))
Sa = {x['key']: x for x in vo_audition.state(ca, lambda: None)}
check('...after Apply the applied line isn\'t waiting, and no line shows an un-pick',
      not Sa['dock_01']['pending'] and not Sa['dock_01']['pick_pending'] and not any(x['unpick_pending'] for x in Sa.values()))
ca.save_json('picks.json', {})
Sa = {x['key']: x for x in vo_audition.state(ca, lambda: None)}
check('un-picking a take the game has is waiting: the next Apply removes that line\'s clip',
      Sa['dock_01']['unpick_pending'] and not Sa['dock_01']['pick_pending'] and not any(x['unpick_pending'] for k, x in Sa.items() if k != 'dock_01'))
pg = (REPO / 'verbaline/page.html').read_text(encoding='utf-8')
check('...and the page says so on the line, in the header\'s count and summary, and on the Timeline',
      'l.unpick_pending?' in pg and 'u=S.filter(l=>l.unpick_pending)' in pg and 'n||p||u?' in pg and 's.unpick_pending' in pg
      and pg.count("the game's clip for this line will be removed at the next") == 2 and "will be removed at the next ${esc(C.apply_label)}`" in pg)
real_gs = vo_audition.game_state; vo_audition.game_state = lambda c: (None, {})     # the hook returned None, or failed
check('...but not when the game state is unknown', not any(x['unpick_pending'] for x in vo_audition.state(ca, lambda: None)))
vo_audition.game_state = real_gs
vo.cmd_apply(ca, A2())
check('Apply is unchanged: the un-picked line leaves the game, and then nothing is waiting',
      ca.project.game_state(ca)[1] == {} and not any(x['unpick_pending'] for x in vo_audition.state(ca, lambda: None)))
ca.save_json('picks.json', {'dock_01': dict(take='takes/dock_01/qwen_1.wav')}); vo.cmd_apply(ca, A2())
T2 = ca.project.timeline(ca, 'dock', {})
check(f'...and a voiced line lasts its take on the timeline ({T2["lines"][0]["end"] - T2["lines"][0]["start"]:.2f} s)',
      not T2['lines'][0]['est'] and abs(T2['lines'][0]['end'] - T2['lines'][0]['start'] - 2.0) < .2)

# ------------------------------------------------------------------ 🧹 clearing a group's unpicked takes, and take numbers
import time                                                                            # noqa: E402
os.environ['VERBALINE_WORK'] = str(WORK); cx = vo.Ctx(PROJECT); T = WORK / 'takes' / 'intro_alarm'   # the throwaway project again (hp's)
if T.exists(): shutil.rmtree(T)
for n in ('qwen_1', 'qwen_2', 'qwen_3', 'qwen_4', 'restyle_1'): speech(T / f'{n}.wav', .4)
speech(T / 'parts' / 'neutral_0a1b2c3d' / 'qwen_1.wav', .4); speech(T / 'removed' / 'qwen_4.wav', .4); speech(T / 'removed' / 'qwen_7.wav', .4)
(T / 'scores.json').write_text(json.dumps({f'{n}.wav': dict(total=.9) for n in ('qwen_1', 'qwen_2', 'qwen_3', 'qwen_4', 'restyle_1')}), encoding='utf-8')
check('a new take\'s number is past every take, removed ones too (a gap or a clear never reuses a name, or overwrites the pick)',
      vo_files.next_take_number(T, 'qwen') == 8 and vo_files.next_take_number(T, 'restyle') == 2 and vo_files.next_take_number(T, 'xai') == 1)
cx.save_json('picks.json', {'intro_alarm': dict(take='takes/intro_alarm/qwen_1.wav')})
cx.save_json('tweaks.json', {'intro_alarm': {'takes/intro_alarm/qwen_3.wav': dict(prompt='warmer')}})
CT = lambda **k: argparse.Namespace(**dict(dict(voice=None, group='intro', line=None, keys=None, todo=False, unpicked_lines=False, dry_run=False, before=None), **k))
plan = hp.post('/api/takes/clear', dict(group='intro', dry=1))['plan']
check(f'🧹 the page is told what a clear would move first ({plan})',
      plan == dict(lines=1, picked=1, takes=3, prompted=1, unpicked=0, unpicked_takes=0))
check('...a group with no lines is refused', raises(lambda: hp.post('/api/takes/clear', dict(group='nowhere', dry=1))))
before = sorted(x.name for x in T.glob('*.wav'))
vo.cmd_clear_takes(cx, CT(dry_run=True))
check('...a dry run moves nothing', sorted(x.name for x in T.glob('*.wav')) == before)
jid = hp.post('/api/takes/clear', dict(group='intro'))['job']
st = hp.jobs.added[-1][1][0]
check(f'...the clear itself is a job, saying when you confirmed ({st})', st[:3] == ['clear-takes', '--group', 'intro'] and st[3] == '--before' and abs(float(st[4]) - time.time()) < 60 and jid)
mk = {f'{n}.wav': dict(text='x', at='then') for n in ('qwen_1', 'qwen_2', 'qwen_3', 'qwen_4', 'restyle_1')}
(T / 'made.json').write_text(json.dumps(mk), encoding='utf-8')
newer = T / 'qwen_9.wav'; speech(newer, .4); os.utime(newer, (time.time() + 600, time.time() + 600))
real_still = vo_files.remove_takes
def racing(work, key, names, still=None):
    seen = {'n': 0}
    def still2():
        seen['n'] += 1; s = still()
        return s | ({'takes/intro_alarm/qwen_4.wav'} if seen['n'] >= 3 else set())
    return real_still(work, key, names, still2)
vo_files.remove_takes = racing
vo.cmd_clear_takes(cx, CT(before=time.time())); vo_files.remove_takes = real_still
left = sorted(x.name for x in T.glob('*.wav')); gone = sorted(x.name for x in (T / 'removed').glob('*.wav'))
check(f'...a take picked while the job runs stays (or comes back) ({left})', 'qwen_4.wav' in left)
check(f'...takes made after you confirmed (by jobs queued ahead) stay', 'qwen_9.wav' in left)
check('...the moved takes\' records go with them (removed/made.json)', set(json.loads((T / 'removed' / 'made.json').read_text(encoding='utf-8'))) >= {'qwen_2.wav', 'restyle_1.wav'}
      and set(json.loads((T / 'made.json').read_text(encoding='utf-8'))) == {'qwen_1.wav', 'qwen_3.wav', 'qwen_4.wav'})
newer.unlink(); vo.cmd_clear_takes(cx, CT())
left = sorted(x.name for x in T.glob('*.wav')); gone = sorted(x.name for x in (T / 'removed').glob('*.wav'))
check(f'...the pick and a take with a prompt stay; the rest go to removed/ ({left})', left == ['qwen_1.wav', 'qwen_3.wav'])
check(f'...a take whose name is already in removed/ keeps both ({gone})', 'qwen_4.wav' in gone and any(x.startswith('qwen_4_') for x in gone)
      and {'qwen_2.wav', 'restyle_1.wav', 'qwen_7.wav'} <= set(gone))
check('...parts tries aren\'t touched', (T / 'parts' / 'neutral_0a1b2c3d' / 'qwen_1.wav').exists())
check('...moved takes\' checks are forgotten (a restored take is checked again)',
      sorted(json.loads((T / 'scores.json').read_text(encoding='utf-8'))) == ['qwen_1.wav', 'qwen_3.wav'])
check('...and the next take still doesn\'t reuse a name', vo_files.next_take_number(T, 'qwen') == 8)
cx.save_json('picks.json', {}); vo.cmd_clear_takes(cx, CT())
check('...a line with no pick keeps its takes', sorted(x.name for x in T.glob('*.wav')) == ['qwen_1.wav', 'qwen_3.wav'])
vo.cmd_clear_takes(cx, CT(unpicked_lines=True))
check('...unless asked: then all but the prompted one go', sorted(x.name for x in T.glob('*.wav')) == ['qwen_3.wav'])
check('...and it needs lines named', raises(lambda: vo.cmd_clear_takes(cx, CT(group=None))))

# The jobs sidebar: numbered output, fetched from where the page left off, and history that can be cleared.
JB = vo_audition.Jobs(str(PROJECT)); time.sleep(.01)
check('each start of the studio has its own output gen (a page open across a restart starts over)', vo_audition.Jobs(str(PROJECT)).gen != JB.gen)
for i in range(3): JB.note(f'old {i}')
JB.recent.appendleft(dict(id=1, label='old job', ok=True, secs=1))
JB.current = dict(id=2, label='running', steps=[['x']], started=0, log_from=JB.seq + 1)
JB.note('running 1'); s0 = JB.state(since=0); s2 = JB.state(since=2)
check(f'job output is numbered, and the page fetches only what\'s new ({[x[1][9:] for x in s2["out"]]})',
      [x[1][9:] for x in s0['out']] == ['old 0', 'old 1', 'old 2', 'running 1'] and [x[1][9:] for x in s2['out']] == ['old 2', 'running 1'])
g0 = JB.gen; JB.clear(); s = JB.state(since=0)
check(f'Clear history forgets finished jobs and their output, keeping the running job\'s ({[x[1][9:] for x in s["out"]]})',
      not s['recent'] and [x[1][9:] for x in s['out']] == ['running 1'] and s['gen'] == g0 + 1 and s['current']['id'] == 2)
JB.current = None; JB.clear(); JB.note('next')
check('...and numbering carries on after a clear (a page that missed it starts over by gen)', JB.state(since=0)['out'][-1][0] == s0['out'][-1][0] + 1)

# ------------------------------------------------------------------ Windows (the Windows test run checks these there)
import subprocess, threading, time                                                   # noqa: E402
from verbaline import tomledit                                                       # noqa: E402
s1 = vo_audition.bind(0); port = s1.server_address[1]
check(f'a second studio on a taken port is refused, saying what to do (port {port}; Windows would have shared it)', raises(lambda: vo_audition.bind(port)))
s1.server_close()
busy = Path(TMP.name) / 'busy.json'; busy.write_text('{}', encoding='utf-8')
new = busy.with_name('busy.json.tmp'); new.write_text('{"a": 1}', encoding='utf-8')
held = open(busy, encoding='utf-8'); threading.Timer(.3, held.close).start()
vo_files.replace(new, busy)
check('a file another program has open is replaced once it lets go (Windows refuses the rename meanwhile)', json.loads(busy.read_text(encoding='utf-8')) == {'a': 1})
check('a voice id Windows reserves is refused (nul)', raises(lambda: tomledit.add_voice('nul')))

calls, real = [], (vo.subprocess.call, vo.os.execv)
vo.subprocess.call = lambda argv: (calls.append('call'), 7)[1]
vo.os.execv = lambda py, argv: calls.append('execv')
fake = Path(TMP.name) / ('python.exe' if os.name == 'nt' else 'python'); fake.write_text('', encoding='utf-8')
c.cfg.setdefault('envs', {})['score'] = str(fake); code = None
try: vo.reexec(c, argparse.Namespace(cmd='score', engine=None, backend=None))
except SystemExit as e: code = e.code
finally: vo.subprocess.call, vo.os.execv = real; c.cfg['envs']['score'] = ''
if os.name == 'nt':
    check(f'a model environment\'s job runs as a child on Windows, its exit code passed on ({calls}, {code})', calls == ['call'] and code == 7)
    # Cancel: the job's own child (the model environment's Python) stops with it.
    pidf = Path(TMP.name) / 'child.pid'
    parent = subprocess.Popen([sys.executable, '-c', 'import subprocess, sys, time; p = subprocess.Popen([sys.executable, "-c", '
                               '"import time; time.sleep(60)"]); open(sys.argv[1], "w").write(str(p.pid)); time.sleep(60)', str(pidf)])
    child = None
    for _ in range(100):
        try: child = int(pidf.read_text()); break
        except (OSError, ValueError): time.sleep(.1)
    vo_audition.stop(parent); parent.wait(timeout=10); time.sleep(.5)
    alive = child and str(child) in subprocess.run(['tasklist', '/FI', f'PID eq {child}', '/NH'], capture_output=True, text=True).stdout
    check(f'Cancel stops a job and what it started (child {child})', child and not alive)
else:
    check(f'a model environment\'s job replaces itself with that Python ({calls})', calls == ['execv'])

# The page: no game's names left in it, and the title is the project's.
page = (REPO / 'verbaline/page.html').read_text(encoding='utf-8')
check('the page\'s title is the project\'s', '<title>{{PROJECT}}: Verbaline For Games</title>' in page)

# Windows: text defaults to the code page there (cp1252), which can't read the page or the words. Every text file
# and pipe the studio opens names its encoding, and paths the page sees use forward slashes.
import ast
def implicit_text(path):
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if not isinstance(n, ast.Call) or any(k.arg == 'encoding' for k in n.keywords): continue
        f = n.func; name = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
        mode = n.args[1].value if name == 'open' and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else ''
        text_pipe = name in ('Popen', 'run') and any(k.arg == 'text' for k in n.keywords)
        if (name in ('read_text', 'write_text') or (name == 'open' and isinstance(f, ast.Name) and 'b' not in mode)
                or (name == 'TemporaryFile' and n.args and 'b' not in n.args[0].value) or text_pipe):
            out.append(f'{path.name}:{n.lineno}')
    return out
loose = [x for f in [*(REPO / 'verbaline').rglob('*.py'), *(REPO / 'examples').rglob('*.py')] for x in implicit_text(f)]
check(f'every text file and pipe names its encoding (Windows) {loose}', not loose)
check('paths the page sees use forward slashes', 'relative_to(root).as_posix()' in (REPO / 'verbaline/server.py').read_text(encoding='utf-8')
      and '.relative_to(self.work.resolve()).as_posix()' in (REPO / 'verbaline/cli.py').read_text(encoding='utf-8'))

print(f'verbaline checks: {failures} failed')
TMP.cleanup()
sys.exit(1 if failures else 0)
