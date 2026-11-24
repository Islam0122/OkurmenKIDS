# Original ambient-tech bed: pads + soft arpeggio + sub pulse. 48 kHz stereo.
import numpy as np, soundfile as sf, sys
SR=48000; DUR=float(sys.argv[1]) if len(sys.argv)>1 else 420
BPM=92; beat=60/BPM; bar=4*beat
n=int(SR*DUR); t=np.arange(n)/SR
L=np.zeros(n); R=np.zeros(n)
def midi(m): return 440*2**((m-69)/12)
prog=[[57,60,64,67],[53,57,60,64],[48,52,55,59],[55,59,62,66]]  # Am7 Fmaj7 Cmaj7 G(maj7-ish)
rng=np.random.default_rng(7)
def env(length, a, r):
    e=np.ones(length); ai=int(a*SR); ri=int(r*SR)
    e[:ai]=np.linspace(0,1,ai); e[-ri:]=np.minimum(e[-ri:],np.linspace(1,0,ri)); return e
def lp(x, a):  # one-pole lowpass
    y=np.zeros_like(x); acc=0.0
    import scipy.signal as ss
    return ss.lfilter([a],[1,-(1-a)],x)
chord_len=2*bar
i=0; pos=0.0
while pos<DUR:
    ch=prog[i%4]; s=int(pos*SR); length=min(int((chord_len+1.5)*SR), n-s)
    if length<=0: break
    tt=np.arange(length)/SR; e=env(length,1.2,1.6)
    for k,m in enumerate(ch):
        f=midi(m)
        for det,pan in ((-0.12,0.25),(0.12,0.75)):
            ph=rng.random()*6.28
            w=(np.sin(2*np.pi*f*(1+det/100)*tt+ph)+0.35*np.sin(2*np.pi*2*f*(1+det/100)*tt)+0.12*np.sin(2*np.pi*3*f*tt))
            L[s:s+length]+=w*e*(1-pan)*0.05; R[s:s+length]+=w*e*pan*0.05
    # bass
    fb=midi(ch[0]-24); bl=np.sin(2*np.pi*fb*tt)*e*0.09
    L[s:s+length]+=bl; R[s:s+length]+=bl
    # arpeggio (8th notes) - soft pluck
    for st in range(16):
        ts=pos+st*beat/2
        if ts>=DUR: break
        m=ch[[0,2,1,3,2,1,3,2][st%8]]+12
        f=midi(m); ss_=int(ts*SR); ln=min(int(0.9*SR), n-ss_)
        if ln<=0: continue
        tt2=np.arange(ln)/SR; pe=np.exp(-tt2*5.5)
        w=(np.sin(2*np.pi*f*tt2)+0.3*np.sin(2*np.pi*2*f*tt2))*pe*0.035
        pan=0.3+0.4*((st%4)/3)
        L[ss_:ss_+ln]+=w*(1-pan); R[ss_:ss_+ln]+=w*pan
    # soft pulse on beats
    for b in range(8):
        ts=pos+b*beat; ss_=int(ts*SR); ln=min(int(0.25*SR), n-ss_)
        if ln<=0: continue
        tt2=np.arange(ln)/SR; k=np.sin(2*np.pi*(55+60*np.exp(-tt2*30))*tt2)*np.exp(-tt2*14)*0.10
        L[ss_:ss_+ln]+=k; R[ss_:ss_+ln]+=k
    pos+=chord_len; i+=1
# simple stereo delay/reverb tail
d=int(0.33*SR)
L2=L.copy(); R2=R.copy(); L2[d:]+=0.28*R[:-d]; R2[d:]+=0.28*L[:-d]
d2=int(0.51*SR); L2[d2:]+=0.15*L[:-d2]; R2[d2:]+=0.15*R[:-d2]
x=np.stack([L2,R2],1); x/=np.max(np.abs(x))*1.12
fi=int(2*SR); fo=int(4*SR); x[:fi]*=np.linspace(0,1,fi)[:,None]; x[-fo:]*=np.linspace(1,0,fo)[:,None]
sf.write('music.wav', x.astype(np.float32), SR)
print('ok', DUR)
