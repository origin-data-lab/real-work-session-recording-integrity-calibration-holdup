"""B1 — recording integrity over a real work session (SEI CSVs + .imu + device .log)."""
import sys, os, glob, re
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from read_zximu import load
RAW, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
rows, bnd = [], []
for d in sorted(glob.glob(f'{RAW}/ODL_pack_*')):
    sess = d.split('ODL_pack_')[1]
    chunks = sorted({os.path.basename(p)[:-len('_left_sei.csv')] for p in glob.glob(f'{d}/*_left_sei.csv')})
    E = {}
    for eye in ('left', 'right'):
        parts = []
        for ci, c in enumerate(chunks):
            x = pd.read_csv(f'{d}/{c}_{eye}_sei.csv'); x['chunk'] = ci; parts.append(x)
        E[eye] = pd.concat(parts, ignore_index=True)
    L, R = E['left'], E['right']
    cL = (L.exposure_start_us + L.exposure_us / 2).values.astype(np.int64); cR = (R.exposure_start_us + R.exposure_us / 2).values.astype(np.int64)
    k = min(len(cL), len(cR)); dt = np.diff(cL); dlr = cR[:k] - cL[:k]
    # chunk boundaries
    for ci in range(1, len(chunks)):
        i = np.where(L.chunk.values == ci)[0][0]
        bnd.append(dict(session=sess, boundary=f'{ci-1}->{ci}', interval_us=int(cL[i] - cL[i - 1]), strobe_step=int(L.strobe_seq[i] - L.strobe_seq[i - 1]), lr_delta_us=int(dlr[i])))
    r, _ = load(glob.glob(f'{d}/*.imu')[0]); g = r[r['k1'] == 2]; a = r[r['k1'] == 4]
    tg = g['ts'].astype(np.int64); gd = np.diff(tg); ta = a['ts'].astype(np.int64)
    log = open(glob.glob(f'{d}/*.log')[0]).read()
    m = re.search(r'frames=(\d+)/(\d+)', log); st = re.search(r'STROBE drop=(\d+) s0 irq=\d+ pulse=(\d+).*?s1 irq=\d+ pulse=(\d+)', log)
    gap = re.search(r'close gap pts g=(\d+)/(\d+)us a=(\d+)/(\d+)us seq g=(\d+)/(\d+) a=(\d+)/(\d+) ovw g=(\d+) a=(\d+)', log)
    rows.append(dict(session=sess, chunks=len(chunks), frames_left=len(L), frames_right=len(R), duration_min=(cL[-1] - cL[0]) / 6e7,
        frame_interval_median_us=np.median(dt), frame_interval_min_us=dt.min(), frame_interval_max_us=dt.max(),
        dropped_frames_from_intervals=int(np.sum(np.round(dt / 33333.33) - 1)),
        strobe_seq_consecutive_left=bool(np.all(np.diff(L.strobe_seq) == 1)), strobe_seq_consecutive_right=bool(np.all(np.diff(R.strobe_seq) == 1)),
        lr_delta_median_us=np.median(dlr), lr_delta_max_abs_us=int(np.abs(dlr).max()),
        exposure_median_us=L.exposure_us.median(), exposure_p5_us=L.exposure_us.quantile(.05), exposure_p95_us=L.exposure_us.quantile(.95), exposure_max_us=int(L.exposure_us.max()),
        imu_gyro_samples=len(g), imu_accel_samples=len(a), imu_rate_hz=1e6 / np.median(gd), imu_max_gap_us=int(gd.max()), imu_gaps_over_5ms=int((gd > 5000).sum()),
        imu_seq_breaks=int(np.sum(np.diff(r['seq'].astype(np.int64)) != 1)),
        video_start_after_imu_ms=(cL[0] - tg[0]) / 1e3, video_end_before_imu_end_ms=(tg[-1] - cL[-1]) / 1e3,
        log_frames=m.group(0) if m else '', log_strobe_drop=int(st.group(1)) if st else None, log_strobe_pulses=f'{st.group(2)}/{st.group(3)}' if st else '',
        log_imu_gap_counters=gap.group(0) if gap else ''))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/b1_session_integrity.csv', index=False, float_format='%.3f')
B = pd.DataFrame(bnd); B.to_csv(f'{OUT}/b1_chunk_boundaries.csv', index=False)
pd.set_option('display.width', 250); print(T.drop(columns=['log_imu_gap_counters']).T.to_string()); print(B.describe().to_string())
