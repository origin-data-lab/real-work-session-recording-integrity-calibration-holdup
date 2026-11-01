"""B2 — head motion and motion-blur budget during real work.
Per frame: rotation during the exposure window from gyro (integrated, camera frame via T_cam_imu),
blur at image centre = f * |rot_xy| ; roll blur at radius 400 px = 400 * |rot_z|.
Also: what-if exposures (2, 4, 6 ms) assuming the same motion.
Validation: per-frame sharpness in the 30 s clips vs predicted blur (scene-normalised).
"""
import sys, os, glob, re, struct, subprocess
import numpy as np, pandas as pd, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from read_zximu import load; from odl_calib import device_calib
dc = device_calib(os.environ['ODL_CALIB']); K = dc['cam0']['K']; f = K[0, 0]
Rci = dc['cam0']['T_cam_imu'][:3, :3]; shift_us = dc['cam0']['shift'] * 1e6

def gyro_integral(d):
    r, _ = load(glob.glob(f'{d}/*.imu')[0]); g = r[r['k1'] == 2]
    t = g['ts'].astype(np.int64); W = (Rci @ np.c_[g['x'], g['y'], g['z']].astype(float).T).T
    dt = np.diff(t) / 1e6; cum = np.vstack([np.zeros(3), np.cumsum((W[1:] + W[:-1]) / 2 * dt[:, None], 0)])
    return t, W, cum

def rot_during(t, cum, t0, t1):
    a = np.c_[[np.interp(t0, t, cum[:, k]) for k in range(3)]].T; b = np.c_[[np.interp(t1, t, cum[:, k]) for k in range(3)]].T
    return b - a   # rad, camera frame

