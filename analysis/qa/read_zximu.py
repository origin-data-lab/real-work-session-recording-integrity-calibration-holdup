import numpy as np, sys
dt=np.dtype([('ts','<u8'),('seq','<u4'),('k1','<u2'),('k2','<u2'),('k3','<u4'),('idx','<u4'),('x','<f4'),('y','<f4'),('z','<f4'),('t','<u4')])
def load(p):
    b=open(p,'rb').read(); hs=int.from_bytes(b[10:12],'little')
    return np.frombuffer(b[hs:],dtype=dt), b[:hs]
if __name__=='__main__':
    for p in sys.argv[1:]:
        r,h=load(p); g=r[r['k1']==2]; a=r[r['k1']==4]
        d=np.diff(g['ts'].astype(np.int64)); sq=np.diff(r['seq'].astype(np.int64))
        G=np.c_[g['x'],g['y'],g['z']]
        print(p.split('/')[-1],'n',len(g),len(a),'dur %.2fs'%((g['ts'][-1]-g['ts'][0])/1e6),'rate %.2f'%(1e6/np.median(d)),'maxgap us',d.max(),'seq jumps',(sq!=1).sum(),'gyro p95 deg/s %.0f'%np.degrees(np.percentile(np.linalg.norm(G,axis=1),95)),'t0',g['ts'][0])
