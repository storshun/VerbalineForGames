"""Runs a batch of Step-Audio-EditX clones and edits with its models loaded once (models.StepEditX calls it, in
its own Python: the config's [envs] editx). Step-Audio-EditX (Apache 2.0, StepFun) is a 3B audio model that edits a
clip's delivery (emotion, speaking style, speed) and keeps its voice: the edit is voiced from the clip's own speaker
features.

    python editx_run.py <Step-Audio-EditX checkout> <models folder>  < jobs.json
    jobs: [{"out", "audio", "text", "steps": [["clone", <new text>] | [<edit type>, <edit info>], ...]}, ...]
          audio + text: the clip to start from and what it says. Each step works on the previous step's result:
          "clone" reads the new text in the clip's voice, an edit ("emotion", "style", "speed") changes how it is said.
Prints one line per job: "ok <out>" or "failed <out>: <why>"."""
import json, os, random, shutil, sys, tempfile, traceback
from pathlib import Path


def main():
    repo, models = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(); jobs = json.load(sys.stdin)
    os.chdir(repo); sys.path.insert(0, str(repo))
    os.environ.setdefault('VLLM_ATTENTION_BACKEND', 'TRITON_ATTN')        # as its own tts_infer.py
    os.environ.setdefault('HF_HUB_OFFLINE', '1')                          # the models are local
    import torchaudio
    from tokenizer import StepAudioTokenizer
    import tts
    from tts import StepAudioTTS
    # vLLM V1 seeds every run the same and its requests carry no seed, so each run would make the same tries: give
    # every request its own.
    plain = tts.SamplingParams
    tts.SamplingParams = lambda **kw: plain(**{'seed': random.randrange(2 ** 31), **kw})
    tok = StepAudioTokenizer(str(models / 'Step-Audio-Tokenizer'), model_source='local')
    # vLLM's share of the 5090's 32 GB: the 3B model in bf16 (about 6.5 GB) and a cache for one 3072-token request.
    # Its tokenizer and vocoder take about 3 GB more, outside this share (13 GB in all; models.StepEditX waits for it).
    m = StepAudioTTS(str(models / 'Step-Audio-EditX'), tok, model_source='local', max_model_len=3072, max_num_seqs=1,
                     gpu_memory_utilization=float(os.environ.get('VERBALINE_EDITX_GPU', '0.32')), cosyvoice_dtype='bfloat16')
    for j in jobs:
        out = Path(j['out'])
        try:
            if not j['steps']: raise ValueError('no clone or edit asked for')
            out.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=out.parent) as tmp:   # beside the result: /tmp is RAM, and emptied
                audio, text = j['audio'], j['text']
                for k, (kind, info) in enumerate(j['steps']):
                    if kind == 'clone': wav, sr = m.clone(prompt_wav_path=audio, prompt_text=text, target_text=info); text = info
                    else: wav, sr = m.edit(prompt_wav_path=audio, prompt_text=text, edit_type=kind, edit_info=info)
                    audio = str(Path(tmp) / f'{out.stem}_{k}.wav'); torchaudio.save(audio, wav.cpu().float(), sr)
                shutil.move(audio, out)
            print(f'ok {out}', flush=True)
        except Exception as e:
            traceback.print_exc(); print(f'failed {out}: {e}', flush=True)


if __name__ == '__main__':
    main()
