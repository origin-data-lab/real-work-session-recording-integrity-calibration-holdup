"""B2 — head motion and motion-blur budget during real work.
Per frame: rotation during the exposure window from gyro (integrated, camera frame via T_cam_imu),
blur at image centre = f * |rot_xy| ; roll blur at radius 400 px = 400 * |rot_z|.
Also: what-if exposures (2, 4, 6 ms) assuming the same motion.
Validation: per-frame sharpness in the 30 s clips vs predicted blur (scene-normalised).
"""
import sys, os, glob, re, struct, subprocess
import numpy as np, pandas as pd, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from read_zximu import load; from odl_calib import device_calib
RAW, OUT = sys.argv[1], sys.argv[2]
dc = device_calib(os.environ['ODL_CALIB']); K = dc['cam0']['K']; f = K[0, 0]
Rci = dc['cam0']['T_cam_imu'][:3, :3]; shift_us = dc['cam0']['shift'] * 1e6
print('f', f, 'timeshift us', shift_us)

def gyro_integral(d):
    r, _ = load(glob.glob(f'{d}/*.imu')[0]); g = r[r['k1'] == 2]
    t = g['ts'].astype(np.int64); W = (Rci @ np.c_[g['x'], g['y'], g['z']].astype(float).T).T
    dt = np.diff(t) / 1e6; cum = np.vstack([np.zeros(3), np.cumsum((W[1:] + W[:-1]) / 2 * dt[:, None], 0)])
    return t, W, cum

def rot_during(t, cum, t0, t1):
    a = np.c_[[np.interp(t0, t, cum[:, k]) for k in range(3)]].T; b = np.c_[[np.interp(t1, t, cum[:, k]) for k in range(3)]].T
    return b - a   # rad, camera frame

rows = []; speed_rows = []
for d in sorted(glob.glob(f'{RAW}/ODL_pack_*')):
    sess = d.split('ODL_pack_')[1]; t, W, cum = gyro_integral(d)
    for p in sorted(glob.glob(f'{d}/*_left_sei.csv')):
        x = pd.read_csv(p); t0 = x.exposure_start_us.values + shift_us; t1 = t0 + x.exposure_us.values
        rot = rot_during(t, cum, t0, t1); tc = (t0 + t1) / 2
        w = np.c_[[np.interp(tc, t, W[:, k]) for k in range(3)]].T
        rows.append(pd.DataFrame(dict(session=sess, chunk=os.path.basename(p)[16:21], frame=np.arange(len(x)), exposure_us=x.exposure_us.values,
            omega_xy_dps=np.degrees(np.hypot(w[:, 0], w[:, 1])), omega_z_dps=np.degrees(np.abs(w[:, 2])), omega_norm_dps=np.degrees(np.linalg.norm(w, axis=1)),
            blur_centre_px=f * np.hypot(rot[:, 0], rot[:, 1]), blur_roll_r400_px=400 * np.abs(rot[:, 2]))))
F = pd.concat(rows, ignore_index=True)
F['blur_total_px'] = np.hypot(F.blur_centre_px, F.blur_roll_r400_px)
F.to_csv(f'{OUT}/b2_per_frame.csv.gz', index=False, float_format='%.4g')
qs = [.5, .75, .9, .95, .99]
summ = []
for name, col in [('head angular speed (deg/s)', 'omega_norm_dps'), ('blur at image centre (px)', 'blur_centre_px'), ('blur incl. roll at r=400 px (px)', 'blur_total_px'), ('exposure (us)', 'exposure_us')]:
    summ.append(dict(quantity=name, **{f'p{int(q*100)}': F[col].quantile(q) for q in qs}, max=F[col].max()))
S = pd.DataFrame(summ); S.to_csv(f'{OUT}/b2_summary.csv', index=False, float_format='%.3f'); print(S.to_string())
# threshold shares, actual and what-if exposure
sh = []
for thr in (0.5, 1, 2, 3, 5):
    r = dict(threshold_px=thr, actual=(F.blur_total_px > thr).mean())
    for e in (2000, 4000, 6000):
        r[f'if_{e//1000}ms'] = (F.blur_total_px * e / F.exposure_us > thr).mean()
    sh.append(r)
SH = pd.DataFrame(sh); SH.to_csv(f'{OUT}/b2_blur_shares.csv', index=False, float_format='%.4f'); print(SH.to_string())
bysess = F.groupby('session').agg(frames=('blur_total_px', 'size'), speed_median=('omega_norm_dps', 'median'), speed_p95=('omega_norm_dps', lambda v: v.quantile(.95)),
                                  blur_median=('blur_total_px', 'median'), share_gt_1px=('blur_total_px', lambda v: (v > 1).mean()), share_gt_3px=('blur_total_px', lambda v: (v > 3).mean()))
bysess.to_csv(f'{OUT}/b2_by_session.csv', float_format='%.4f'); print(bysess.to_string())
print('gyro max dps', F.omega_norm_dps.max(), 'frames', len(F))
