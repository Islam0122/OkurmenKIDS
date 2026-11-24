import re, json, sys, soundfile as sf, numpy as np
sys.path.insert(0, '.')
from script import SCENES
from kokoro_onnx import Kokoro
import os
T=os.environ.get('KOKORO_DIR','tts')+'/'
k = Kokoro(T+'kokoro-v1.0.onnx', T+'voices-v1.0.bin')
def speech(s):
    rep = [('lms.okurmenkids.com','L M S dot Okurmen Kids dot com'),('api.okurmenkids.com','A P I dot Okurmen Kids dot com'),
           ('training.okurmenkids.com','training dot Okurmen Kids dot com'),('okurmenkids.com','Okurmen Kids dot com'),
           ('OkurmenKIDS','Okurmen Kids'),('drf-spectacular','D R F spectacular'),('JWT','J W T'),('LMS','L M S'),
           ('React 19','React nineteen'),('Python 3.12','Python three point twelve'),('slash admin','slash admin'),('IP address','I P address'),
           ('CMS','C M S'),('HR','H R'),('724','seven hundred and twenty-four'),('966','nine hundred and sixty-six'),('Gunicorn','Green Unicorn')]
    for a,b in rep: s = s.replace(a,b)
    return s
voice = sys.argv[1] if len(sys.argv)>1 else 'af_heart'
out=[]
for sid, title, sents in SCENES:
    for i,(en,ru) in enumerate(sents):
        a, sr = k.create(speech(en), voice=voice, speed=0.98, lang='en-us')
        # trim silence
        nz = np.where(np.abs(a)>0.01)[0]; a = a[max(nz[0]-200,0):nz[-1]+800]
        fn=f'vo/{sid}_{i}.wav'; sf.write(fn, a, sr)
        out.append(dict(scene=sid, i=i, file=fn, dur=len(a)/sr, en=en, ru=ru))
        print(sid,i,round(len(a)/sr,2), flush=True)
json.dump(out, open('vo/segments.json','w'), ensure_ascii=False, indent=1)
print('total', sum(o['dur'] for o in out))
