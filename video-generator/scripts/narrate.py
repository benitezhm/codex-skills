"""Run using the existing Kokoro environment; no Pillow or package installation needed."""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    tasks = [t for t in request['tasks'] if not Path(t['output']).exists()]
    if not tasks:
        return
    model = Path(request['model_dir']).expanduser()
    options = ort.SessionOptions()
    options.intra_op_num_threads = request.get('threads', 4)
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model / 'kokoro-v1.0.onnx'), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    tts = Kokoro.from_session(session, str(model / 'voices-v1.0.bin'))
    for task in tasks:
        audio, rate = tts.create(task['text'], voice=request['voice'],
                                 speed=request['speed'], lang=request['language'])
        if not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-5:
            raise ValueError('Kokoro returned empty, silent or non-finite audio')
        peak = float(np.max(np.abs(audio)))
        if peak > 0.99:
            audio = audio * (0.99 / peak)
        dest = Path(task['output'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_suffix('.tmp.wav')
        sf.write(temp, audio, rate, subtype='PCM_16')
        temp.replace(dest)
        print(f"Narrated {task['id']}: {len(audio)/rate:.2f}s", flush=True)


if __name__ == '__main__':
    main()
