"""ODL delivery QA — run on the packs made by odl_pack_for_analysis.py.

Outputs (OUT/):
  qa_report.md                      one-page summary for the buyer
  per_frame_blur_<session>.csv      per-frame camera-blur estimate (px) to join with the video by chunk + frame
  b1_*, b2_*, b3_* CSVs             full tables (integrity, blur, calibration check)
Run: python odl_delivery_qa.py <packs_dir> <calibration.yaml> <out_dir> [--skip-calib]
"""
import sys, os, subprocess, argparse
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('packs'); ap.add_argument('calib'); ap.add_argument('out'); ap.add_argument('--skip-calib', action='store_true')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
env = dict(os.environ, ODL_CALIB=os.path.abspath(a.calib), PYTHONPATH=HERE + os.pathsep + os.environ.get('PYTHONPATH', ''))
steps = ['b1_integrity.py', 'b2_motion_blur.py'] + ([] if a.skip_calib else ['b3_calib_holdup.py'])
for s in steps:
    print('==', s, flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, s), a.packs, a.out], env=env, capture_output=True, text=True)
    if r.returncode: sys.exit(f'{s} failed:\n{r.stderr[-2000:]}')
T = pd.read_csv(f'{a.out}/b1_session_integrity.csv', dtype={'session': str}); F = pd.read_csv(f'{a.out}/b2_per_frame.csv.gz', dtype={'session': str, 'chunk': str})
for s, g in F.groupby('session'):
    g[['chunk', 'frame', 'exposure_us', 'omega_norm_dps', 'blur_total_px']].rename(columns={'blur_total_px': 'camera_blur_px', 'omega_norm_dps': 'head_speed_dps'}).to_csv(f'{a.out}/per_frame_blur_{s}.csv', index=False, float_format='%.3f')
L = [f'# Delivery QA report', '', f'Sessions: {len(T)} · minutes: {T.duration_min.sum():.1f} · frames per eye: {int(T.frames_left.sum()):,}', '',
     '## Recording integrity', '', '| Session | Minutes | Frames L/R | Dropped | Max L/R offset (µs) | IMU max gap (ms) | IMU seq breaks |', '|---|---|---|---|---|---|---|']
for r in T.itertuples():
    L.append(f'| {r.session} | {r.duration_min:.1f} | {r.frames_left:,}/{r.frames_right:,} | {r.dropped_frames_from_intervals} | {r.lr_delta_max_abs_us} | {r.imu_max_gap_us/1000:.2f} | {r.imu_seq_breaks} |')
L += ['', '## Camera motion blur (gyro × exposure; camera rotation only)', '']
L += [f'- Median {F.blur_total_px.median():.2f} px; frames > 3 px: {(F.blur_total_px > 3).mean()*100:.1f}%; frames > 8 px: {(F.blur_total_px > 8).mean()*100:.1f}%',
      '- Per-frame values: `per_frame_blur_<session>.csv` (chunk = 5-min file index, frame = frame index within that file).']
if not a.skip_calib and os.path.exists(f'{a.out}/b3_by_chunk.csv'):
    C = pd.read_csv(f'{a.out}/b3_by_chunk.csv')
    L += ['', '## Calibration consistency (target-free epipolar check, 8 frame pairs per 5-min file)', '',
          f'- Central-field median per file: {C.central_epi_median.min():.2f}–{C.central_epi_median.max():.2f} px; whole image: {C.epi_median.min():.2f}–{C.epi_median.max():.2f} px',
          '- Metric scale is not covered by this check.']
open(f'{a.out}/qa_report.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
