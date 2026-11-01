"""B2b — validate predicted blur against image sharpness in the 30 s clips (left eye).
Sharpness = variance of Laplacian in central 800x600 crop; scene-normalised by a centred rolling median (31 frames).
"""
import sys, os, glob, re, struct, subprocess
import numpy as np, pandas as pd, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, '.')
from b2_lib import gyro_integral, rot_during, f, shift_us
from scipy.stats import spearmanr
RAW, OUT = sys.argv[1], sys.argv[2]
try:
    import imageio_ffmpeg; FF = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FF = 'ffmpeg'
def sei(vid):
    b = subprocess.run([FF, '-v', 'error', '-i', vid, '-map', '0:v', '-c', 'copy', '-bsf:v', 'h264_mp4toannexb', '-f', 'h264', '-'], capture_output=True).stdout
    out = []
    for m in re.finditer(re.escape(b'\x00\x00\x01\x06\xf0\x28'), b):
        raw = b[m.start() + 6:m.start() + 66].replace(b'\x00\x00\x03', b'\x00\x00')[:40]
        out.append(struct.unpack('<QQI', raw[8:28]))
    return np.array(out, dtype=np.int64)
rows = []
for d in sorted(glob.glob(f'{RAW}/ODL_pack_*')):
    sess = d.split('ODL_pack_')[1]; vid = glob.glob(f'{d}/clips/*_left_mid30s.mp4')[0]
    S = sei(vid); t, W, cum = gyro_integral(d)
    t0 = S[:, 1] + shift_us; t1 = t0 + S[:, 2]; rot = rot_during(t, cum, t0, t1)
    blur = np.hypot(f * np.hypot(rot[:, 0], rot[:, 1]), 400 * np.abs(rot[:, 2]))
    cap = cv2.VideoCapture(vid); sh = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        g = cv2.cvtColor(fr[300:900, 400:1200], cv2.COLOR_BGR2GRAY); sh.append(cv2.Laplacian(g, cv2.CV_64F).var())
    n = min(len(sh), len(blur)); sh = np.array(sh[:n]); bl = blur[:n]
    rel = sh / pd.Series(sh).rolling(31, center=True, min_periods=10).median().values
    rows.append(pd.DataFrame(dict(session=sess, blur_px=bl, sharpness=sh, sharpness_rel=rel)))
    print(sess, n, 'frames; spearman(blur, rel sharpness) = %.3f' % spearmanr(bl, rel, nan_policy='omit')[0])
V = pd.concat(rows, ignore_index=True); V.to_csv(f'{OUT}/b2b_clip_sharpness.csv.gz', index=False, float_format='%.4g')
V['bin'] = pd.cut(V.blur_px, [0, 0.5, 1, 2, 3, 5, 8, 100])
B = V.groupby('bin', observed=True).agg(frames=('blur_px', 'size'), rel_sharpness_median=('sharpness_rel', 'median')).reset_index(); B['bin'] = B['bin'].astype(str)
B.to_csv(f'{OUT}/b2b_sharpness_by_blur.csv', index=False, float_format='%.3f'); print(B.to_string())
print('pooled spearman %.3f' % spearmanr(V.blur_px, V.sharpness_rel, nan_policy='omit')[0], 'n', len(V))
