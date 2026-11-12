"""Runs a batch of Seed-VC conversions with its models loaded once (models.SeedVC calls it, in Seed-VC's own Python).

Seed-VC's inference.py loads its models on every run, about 25 s of every conversion. This keeps them loaded across
the batch, so a performance's variants take seconds each. Seed-VC (GPL-3.0) is a tool we run, not code we ship.

    python seedvc_run.py <seed-vc checkout>  < conversions.json
    conversions: [{"source", "target", "out", "cfg_rate", "semitones", "f0", "steps", "fp16",
                   "checkpoint", "config"}, ...]   (checkpoint + config: a voice's fine-tuned model; none: the base one)
Prints one line per conversion: "ok <out>" or "failed <out>: <why>"."""
import argparse, json, os, shutil, sys, tempfile, traceback
from pathlib import Path


def main():
    repo = Path(sys.argv[1]).resolve(); jobs = json.load(sys.stdin)
    os.chdir(repo); sys.path.insert(0, str(repo))                  # inference.py finds its checkpoints from here
    os.environ.setdefault('HF_HUB_OFFLINE', '1')                   # everything it needs is in its checkpoints/
    import inference
    loaded, load = {}, inference.load_models
    def cached(args):                                              # one load per model: pitch or not, base or fine-tuned
        k = (args.f0_condition, args.checkpoint)
        if k not in loaded:
            if len(loaded) >= 2: loaded.clear(); __import__('torch').cuda.empty_cache()   # a batch over many voices
            loaded[k] = load(args)
        return loaded[k]
    inference.load_models = cached
    for j in jobs:
        out = Path(j['out']); fp16 = bool(j.get('fp16', True))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                inference.fp16 = fp16                              # main() reads it; a cached load wouldn't set it
                inference.main(argparse.Namespace(
                    source=j['source'], target=j['target'], output=tmp, diffusion_steps=int(j.get('steps', 30)),
                    length_adjust=1.0, inference_cfg_rate=float(j['cfg_rate']), f0_condition=bool(j['f0']),
                    auto_f0_adjust=False, semi_tone_shift=int(j.get('semitones', 0)), checkpoint=j.get('checkpoint'),
                    config=j.get('config'), fp16=fp16))
                made = sorted(Path(tmp).glob('*.wav'))
                if not made: raise RuntimeError('no output')
                out.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(made[-1]), out)
            print(f'ok {out}', flush=True)
        except Exception as e:
            traceback.print_exc(); print(f'failed {out}: {e}', flush=True)


if __name__ == '__main__':
    main()
