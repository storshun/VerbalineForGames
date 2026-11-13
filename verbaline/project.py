"""A project hooked up to Verbaline For Games: its verbaline.toml, and the hooks that connect the studio to its lines and its
game. docs/HookingUpAProject.md is the guide; docs/details/project-api-details.md the reference.

A project gives the studio its lines and takes back the picked takes. The studio owns everything in between (voices,
references, takes, scores, picks, directing), in the project's work folder and its three studio files (cast,
directions, pronunciations).

Two ways to hook up:
  - a lines file (TOML, JSON or CSV) the project keeps: the studio reads lines from it and writes word edits back into
    it (FileLines, below). Apply exports the picked takes and a manifest, and copies them into the project or runs the
    project's own command.
  - a Python adapter module (verbaline.toml [lines] adapter): any of the hooks in HOOKS, each optional but lines.
    Hooks it doesn't define fall back to the lines file's (when it names one) or the studio's own defaults."""
import csv, importlib.util, json, os, re, shutil, sys, time, tomllib
from pathlib import Path

CONFIG_NAME = 'verbaline.toml'
HERE = Path(__file__).resolve().parent
USER_CONFIG = Path(os.path.expanduser(os.environ.get('VERBALINE_CONFIG') or '~/.config/verbaline/config.toml'))
HOOKS = ('lines', 'groups', 'set_words', 'game_state', 'apply', 'timeline', 'watch')


def read_toml(path):
    """A TOML file, read as UTF-8 whatever the system's code page (a byte-order mark from Windows editors is fine)."""
    return tomllib.loads(Path(path).read_text(encoding='utf-8-sig'))


def merge(base, over):
    """`over` laid onto `base`, tables merged key by key."""
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def find(start=None):
    """The project root: $VERBALINE_PROJECT, else the nearest folder from `start` (or the working folder) upwards
    that has a verbaline.toml. Raises SystemExit saying how to hook one up."""
    env = os.environ.get('VERBALINE_PROJECT')
    if env:
        p = Path(os.path.expanduser(env)).resolve()
        f = p if p.is_file() else p / CONFIG_NAME
        if not f.exists(): sys.exit(f'VERBALINE_PROJECT names {env}, which has no {CONFIG_NAME}')
        return f.parent
    here = Path(start or os.getcwd()).resolve()
    for d in [here, *here.parents]:
        if (d / CONFIG_NAME).exists(): return d
    sys.exit(f'No {CONFIG_NAME} here or above {here}: run inside a project hooked up to Verbaline For Games, or pass '
             f'--project <folder>. docs/HookingUpAProject.md says how to hook one up.')


class Project:
    """A project's settings (the studio's defaults, then the user's machine config, then its verbaline.toml) and its
    hooks."""
    def __init__(self, root):
        root = Path(os.path.expanduser(str(root))).resolve()
        if root.is_file(): root = root.parent                          # its verbaline.toml named itself
        if not (root / CONFIG_NAME).exists(): sys.exit(f'{root} has no {CONFIG_NAME} (docs/HookingUpAProject.md)')
        self.root = root; self.file = root / CONFIG_NAME
        self.reload()

    def reload(self):
        cfg = read_toml(HERE / 'defaults.toml')
        if USER_CONFIG.exists():
            cfg = merge(cfg, read_toml(USER_CONFIG))
        own = read_toml(self.file)
        self.cfg = merge(cfg, own)
        p = self.cfg.setdefault('project', {})
        self.name = p.get('name') or self.root.name
        files = self.cfg.get('files', {})
        self.cast_file = self.path(files.get('cast', 'verbaline/cast.toml'))
        self.directions_file = self.path(files.get('directions', 'verbaline/directions.toml'))
        self.pronunciations_file = self.path(files.get('pronunciations', 'verbaline/pronunciations.toml'))
        lines = self.cfg.get('lines', {})
        self.lines_file = self.path(lines['file']) if lines.get('file') else None
        self.adapter = load_adapter(self.path(lines['adapter'])) if lines.get('adapter') else None
        if not self.adapter and not self.lines_file:
            sys.exit(f'{self.file}: [lines] needs a file (a lines file) or an adapter (a Python module)')

    def path(self, p):
        """A path from verbaline.toml: ~ expanded, relative ones from the project's root."""
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else self.root / p

    def work_dir(self):
        return Path(os.path.expanduser(os.environ.get('VERBALINE_WORK') or self.cfg['project'].get('work_dir')
                                       or str(self.root / '.verbaline')))

    def hook(self, name):
        """The adapter's hook, or None."""
        return getattr(self.adapter, name, None) if self.adapter else None

    # ------------------------------------------------------------------ the hooks, with their defaults

    def lines(self, ctx):
        """Every line, as dicts: id, speaker, text, and optionally group, voice, emotion, kind, context (see
        docs/details/project-api-details.md, "A line")."""
        fn = self.hook('lines')
        out = list(fn(ctx)) if fn else FileLines(self.lines_file).lines()
        seen = set()
        for i, l in enumerate(out):
            for k in ('id', 'speaker', 'text'):
                if not str(l.get(k) or '').strip(): raise ValueError(f'line {i + 1} ({l.get("id", "?")}) has no {k}')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', l['id']): raise ValueError(f'line id "{l["id"]}": letters, digits, _ . - only (it names files)')
            if l['id'] in seen: raise ValueError(f'line id "{l["id"]}" is used twice')
            seen.add(l['id'])
        return out

    def groups(self, ctx, lines):
        """The groups lines are filed under (a mission, a scene, a chapter), in order: [{id, title, timeline}]. The
        adapter's, else [groups] titles in verbaline.toml, else each group by its own name, in the order first seen."""
        fn = self.hook('groups')
        if fn: gs = [dict(g, id=str(g['id'])) for g in fn(ctx)]
        else:
            titles = {str(k): v for k, v in self.cfg.get('groups', {}).items()}
            ids = list(dict.fromkeys([*titles, *(str(l.get('group', '')) for l in lines)]))
            gs = [dict(id=g, title=titles.get(g) or g or 'Ungrouped') for g in ids if any(str(l.get('group', '')) == g for l in lines)]
        tl = bool(self.hook('timeline'))
        for g in gs: g.setdefault('title', g['id']); g['timeline'] = tl and g.get('timeline', True)
        return gs

    def set_words(self, ctx, ids, text, rows):
        """Rewrites lines' words where the project keeps them: the adapter's hook, else the lines file in place."""
        text = ' '.join((text or '').split())
        if not text: raise ValueError('a line needs words')
        fn = self.hook('set_words')
        if fn: return fn(ctx, ids, text)
        if not self.lines_file: raise ValueError('this project\'s lines can\'t be edited here (its adapter has no set_words)')
        FileLines(self.lines_file).set_words(ids, text)

    def game_state(self, ctx):
        """What the game has: ({line id: words} or None, {clip key: picked take}). The adapter's hook (it reads the game's
        own files), else what the studio's last Apply recorded (<work>/applied.json). Words are None (not tracked: the
        game reads the same lines file) unless [apply] words_from_manifest says the game takes its words from the
        manifest."""
        fn = self.hook('game_state')
        if fn:
            r = fn(ctx)
            return r if r is not None else (None, {})
        tracked = self.cfg.get('apply', {}).get('words_from_manifest', False)
        f = ctx.path('applied.json')
        if not f.exists(): return ({} if tracked else None), {}
        d = json.loads(f.read_text(encoding='utf-8'))
        return (d.get('words', {}) if tracked else None), d.get('picks', {})

    def watch(self, ctx):
        """Files whose change means the lines must be read again (the adapter's, plus the lines file)."""
        fn = self.hook('watch')
        out = [Path(p) for p in (fn(ctx) if fn else [])]
        if self.lines_file: out.append(self.lines_file)
        return out

    def apply(self, ctx, manifest, run):
        """Puts the picks into the game, after the studio has mastered them into the export folder and written the
        manifest: the adapter's hook, else [apply] command, else [apply] copy_to (the files and manifest copied into the
        project), else nothing (the export folder is the hand-off)."""
        fn = self.hook('apply')
        if fn: return fn(ctx, manifest, run)
        a = self.cfg.get('apply', {})
        if a.get('command'):
            fill = dict(manifest=str(manifest), export_dir=str(Path(manifest).parent), project=str(self.root),
                        work_dir=str(ctx.work), language=ctx.lang, python=sys.executable)
            argv = [str(x).format(**fill) for x in (a['command'] if isinstance(a['command'], list) else a['command'].split())]
            run(a.get('label', 'Run the project\'s apply command'), argv)
        elif a.get('copy_to'):
            dst = self.path(a['copy_to']); dst.mkdir(parents=True, exist_ok=True); m = json.loads(Path(manifest).read_text(encoding='utf-8'))
            keep = {Path(x['file']).name for x in m['lines'].values()}
            for name in keep: shutil.copy2(Path(manifest).parent / name, dst / name)
            if a.get('prune', False):
                for f in dst.glob('*.wav'):
                    if f.name not in keep: f.unlink()
            shutil.copy2(manifest, dst / Path(manifest).name)
            print(f'  {len(keep)} files and {Path(manifest).name} copied to {dst}', flush=True)

    def timeline(self, ctx, group, options, replay=False):
        fn = self.hook('timeline')
        if not fn: raise ValueError('this project has no timeline (its adapter has no timeline hook)')
        return fn(ctx, group, options, replay)


def load_adapter(path):
    """The project's adapter module (imported from its file; its folder goes on sys.path so it can import its own)."""
    if not path.exists(): sys.exit(f'No adapter at {path} (verbaline.toml [lines] adapter)')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('verbaline_adapter_' + re.sub(r'\W', '_', path.stem), path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ the built-in lines file

class FileLines:
    """A lines file the project keeps: TOML ([[line]] tables, or [<id>] tables), JSON (a list, or {"lines": [...]}, or
    {id: {...}}), or CSV (a header row). Fields: id, speaker, text, and optionally group, voice, emotion, kind, context.
    Word edits are written back into it, keeping a TOML file's comments and layout."""
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists(): sys.exit(f'No lines file at {self.path} (verbaline.toml [lines] file)')
        self.kind = self.path.suffix.lower().lstrip('.')
        if self.kind not in ('toml', 'json', 'csv'): sys.exit(f'{self.path}: a lines file is .toml, .json or .csv')

    def lines(self):
        if self.kind == 'csv':
            with open(self.path, newline='', encoding='utf-8-sig') as f: return [{k: v for k, v in r.items() if v not in (None, '')} for r in csv.DictReader(f)]
        if self.kind == 'json':
            d = json.loads(self.path.read_text(encoding='utf-8-sig'))
        else:
            d = read_toml(self.path)
        if isinstance(d, dict) and isinstance(d.get('line'), list): d = d['line']
        elif isinstance(d, dict) and isinstance(d.get('lines'), list): d = d['lines']
        elif isinstance(d, dict): d = [dict(v, id=k) for k, v in d.items() if isinstance(v, dict)]
        return [dict(x) for x in d]

    def set_words(self, ids, text):
        ids = set(ids); n = 0
        if self.kind == 'toml':
            import tomlkit
            doc = tomlkit.parse(self.path.read_text(encoding='utf-8-sig'))
            if isinstance(doc.get('line'), list):                     # [[line]] tables, each with its id
                for t in doc['line']:
                    if t.get('id') in ids: t['text'] = text; n += 1
            else:                                                       # [<id>] tables
                for k in list(doc):
                    if k in ids and isinstance(doc[k], dict): doc[k]['text'] = text; n += 1
            out = tomlkit.dumps(doc)
        elif self.kind == 'json':
            d = json.loads(self.path.read_text(encoding='utf-8-sig')); items = d['line'] if isinstance(d, dict) and isinstance(d.get('line'), list) else \
                d['lines'] if isinstance(d, dict) and isinstance(d.get('lines'), list) else d
            if isinstance(items, list):
                for x in items:
                    if x.get('id') in ids: x['text'] = text; n += 1
            else:
                for k in ids & set(items): items[k]['text'] = text; n += 1
            out = json.dumps(d, indent=2, ensure_ascii=False) + '\n'
        else:
            with open(self.path, newline='', encoding='utf-8-sig') as f: rows = list(csv.DictReader(f)); fields = list(rows[0]) if rows else ['id', 'speaker', 'text']
            for r in rows:
                if r.get('id') in ids: r['text'] = text; n += 1
            import io
            buf = io.StringIO(); w = csv.DictWriter(buf, fields, lineterminator='\n'); w.writeheader(); w.writerows(rows); out = buf.getvalue()
        if not n: raise ValueError(f'no line {", ".join(sorted(ids))} in {self.path.name}')
        tmp = self.path.with_suffix(self.path.suffix + '.tmp'); tmp.write_text(out, encoding='utf-8'); tmp.replace(self.path)


# ------------------------------------------------------------------ Apply's manifest

def write_manifest(ctx, rows, picks, export_dir, name_of):
    """export/<lang>/manifest.json: every line with a pick, its exported file (relative to the manifest), words,
    speaker, group, take and length. What a game reads to play the picks (docs/details/project-api-details.md,
    "The manifest")."""
    import soundfile as sf
    lines = {}
    for r in rows:
        p = picks.get(r['key'])
        if not p: continue
        f = Path(export_dir) / name_of(r)
        if not f.exists(): continue
        lines[r['id']] = dict(file=f.name, text=r['text'], speaker=r['speaker'], group=r['group'], voice=r['voice'],
                              key=r['key'], take=p['take'], seconds=round(sf.info(str(f)).duration, 3))
    m = dict(project=ctx.project.name, language=ctx.lang, made=time.strftime('%Y-%m-%d %H:%M:%S'), lines=lines)
    out = Path(export_dir) / 'manifest.json'; tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding='utf-8'); tmp.replace(out)
    return out
