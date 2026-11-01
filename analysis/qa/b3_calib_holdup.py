"""B3 — does the device calibration hold during a 2.5 h head-mounted work session?
Per chunk: SIFT matches on the 8 sampled left/right frame pairs (same frame index; L/R exposure offset ~21 us),
calibration-free gross-outlier removal (F-RANSAC 8 px, pooled per session), symmetric epipolar distance under
the device (Kalibr, 1600x1200-mode) calibration. Reference: 0.73 px median on the 2026-10-21 S1 clip (Field Note 13).
"""
import sys, os, glob
import numpy as np, pandas as pd, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from odl_calib import device_calib
RAW, OUT = sys.argv[1], sys.argv[2]
dc = device_calib(os.environ['ODL_CALIB']); T = dc['T_c1_c0']
KL, DL, KR, DR = [np.ascontiguousarray(x, dtype=np.float64) for x in (dc['cam0']['K'], dc['cam0']['D'], dc['cam1']['K'], dc['cam1']['D'])]
R, t = T[:3, :3], T[:3, 3]
E = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]]) @ R
und = lambda p, K, D: cv2.fisheye.undistortPoints(np.ascontiguousarray(p.reshape(-1, 1, 2)), K, D).reshape(-1, 2)
def epi(pl, pr):
    hl = np.c_[und(pl, KL, DL), np.ones(len(pl))]; hr = np.c_[und(pr, KR, DR), np.ones(len(pr))]
    l2 = (E @ hl.T).T; l1 = (E.T @ hr.T).T
    return (np.abs((hr * l2).sum(1)) / np.linalg.norm(l2[:, :2], axis=1) + np.abs((hl * l1).sum(1)) / np.linalg.norm(l1[:, :2], axis=1)) / 2 * KL[0, 0]
sift = cv2.SIFT_create(4000); bf = cv2.BFMatcher(); rows = []
for d in sorted(glob.glob(f'{RAW}/ODL_pack_*')):
    sess = d.split('ODL_pack_')[1]; recs = []
    for pL in sorted(glob.glob(f'{d}/frames/*_left_f*.jpg')):
        pR = pL.replace('_left_', '_right_'); a = cv2.imread(pL, 0); b = cv2.imread(pR, 0)
        ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(b, None)
        if da is None or db is None or len(ka) < 50 or len(kb) < 50: continue
        good = [x for x, y in bf.knnMatch(da, db, k=2) if x.distance < 0.7 * y.distance]
        pa = np.float64([ka[g.queryIdx].pt for g in good]); pb = np.float64([kb[g.trainIdx].pt for g in good])
        keep = (np.abs(pa[:, 1] - pb[:, 1]) < 60) & (pa[:, 0] - pb[:, 0] > -20)
        name = os.path.basename(pL); recs.append((name[16:21], int(name.split('_f')[1][:6]), pa[keep], pb[keep]))
    PL = np.vstack([r[2] for r in recs]); PR = np.vstack([r[3] for r in recs])
    _, m = cv2.findFundamentalMat(PL, PR, cv2.FM_RANSAC, 8.0, 0.999); m = m.ravel() == 1; i = 0
    for chunk, fi, pa, pb in recs:
        mm = m[i:i + len(pa)]; i += len(pa)
        e = epi(pa[mm], pb[mm]) if mm.sum() else np.array([])
        for p, v in zip(pa[mm], e): rows.append((sess, chunk, fi, p[0], p[1], v))
M = pd.DataFrame(rows, columns=['session', 'chunk', 'frame', 'u', 'v', 'epi_px'])
M['radius_px'] = np.hypot(M.u - KL[0, 2], M.v - KL[1, 2]); M['central'] = M.radius_px < 500
M.to_csv(f'{OUT}/b3_matches.csv.gz', index=False, float_format='%.4g')
agg = dict(matches=('epi_px', 'size'), epi_median=('epi_px', 'median'), epi_p75=('epi_px', lambda s: s.quantile(.75)), share_lt_1px=('epi_px', lambda s: (s < 1).mean()))
BC = M.groupby(['session', 'chunk']).agg(**agg); C = M[M.central].groupby(['session', 'chunk']).agg(central_matches=('epi_px', 'size'), central_epi_median=('epi_px', 'median'))
BC = BC.join(C).reset_index(); BC.to_csv(f'{OUT}/b3_by_chunk.csv', index=False, float_format='%.3f')
BS = M.groupby('session').agg(**agg).join(M[M.central].groupby('session').agg(central_matches=('epi_px', 'size'), central_epi_median=('epi_px', 'median'))).reset_index()
tot = pd.DataFrame([dict(session='ALL', matches=len(M), epi_median=M.epi_px.median(), epi_p75=M.epi_px.quantile(.75), share_lt_1px=(M.epi_px < 1).mean(),
                         central_matches=int(M.central.sum()), central_epi_median=M[M.central].epi_px.median())])
BS = pd.concat([BS, tot]); BS.to_csv(f'{OUT}/b3_by_session.csv', index=False, float_format='%.3f')
pd.set_option('display.width', 200); print(BS.to_string()); print(BC.to_string())
x = BC.reset_index(drop=True); print('trend: spearman(chunk order, central median) =', pd.Series(range(len(x))).corr(x.central_epi_median, method='spearman'))
