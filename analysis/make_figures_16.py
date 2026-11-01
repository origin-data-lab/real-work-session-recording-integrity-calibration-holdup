import os, glob, numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = 'out'; FIG = f'{OUT}/figures'; RAW = 'raw'; os.makedirs(FIG, exist_ok=True)
INK, GR, C1, C2 = '#1d232b', '#8a8f98', '#1f5fbf', '#d9622b'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10.5, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True, 'grid.color': '#e7eaee', 'axes.edgecolor': '#c9ced6', 'axes.axisbelow': True})
def save(fig, name): fig.savefig(f'{FIG}/{name}.png', dpi=170, bbox_inches='tight'); fig.savefig(f'{FIG}/{name}.svg', bbox_inches='tight'); plt.close(fig)
# per-frame timing table (for figure + release)
rows = []
for d in sorted(glob.glob(f'{RAW}/ODL_pack_*')):
    sess = d.split('ODL_pack_')[1]
    L = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(f'{d}/*_left_sei.csv'))], ignore_index=True)
    R = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(f'{d}/*_right_sei.csv'))], ignore_index=True)
    cL = (L.exposure_start_us + L.exposure_us / 2).values; cR = (R.exposure_start_us + R.exposure_us / 2).values
    rows.append(pd.DataFrame(dict(session=sess, frame=np.arange(len(L)), interval_us=np.r_[np.nan, np.diff(cL)], lr_delta_us=cR - cL, exposure_us=L.exposure_us.values)))
TF = pd.concat(rows, ignore_index=True); TF.to_csv(f'{OUT}/b1_per_frame_timing.csv.gz', index=False, float_format='%.0f')
fig, axs = plt.subplots(1, 2, figsize=(10.5, 3.6))
axs[0].hist(TF.interval_us.dropna() / 1000, bins=np.arange(31.0, 35.6, 0.1), color=C1)
axs[0].set_yscale('log'); axs[0].set_xlabel('Interval between frames (ms)'); axs[0].set_ylabel('Frames (log)')
axs[0].set_title(f'Frame intervals: {TF.interval_us.min()/1000:.1f}–{TF.interval_us.max()/1000:.1f} ms, none ≥ 50 ms', loc='left', fontsize=10.5)
axs[1].hist(TF.lr_delta_us, bins=np.arange(-10, 70, 1), color=C2)
axs[1].set_yscale('log'); axs[1].set_xlabel('Right minus left exposure centre (µs)'); axs[1].set_title(f'Left/right offset: max {TF.lr_delta_us.abs().max():.0f} µs', loc='left', fontsize=10.5)
fig.suptitle(f'{len(TF):,} stereo frames, six sessions, 2026-11-01', x=0.06, y=1.04, ha='left', fontsize=11); save(fig, 'fn16_timing')
# calibration hold-up over clock time
BC = pd.read_csv(f'{OUT}/b3_by_chunk.csv', dtype={'chunk': str})
def clock(s, c):
    h, m, sec = int(s[9:11]), int(s[11:13]), int(s[13:15]); return h + m / 60 + sec / 3600 + (int(c) * 5 + 2.5) / 60
BC['t'] = [clock(s, c) for s, c in zip(BC.session, BC.chunk)]
fig, ax = plt.subplots(figsize=(8, 3.8))
for s, g in BC.groupby('session'):
    ax.plot(g.t, g.central_epi_median, 'o-', color=C1, ms=4, lw=1.2); ax.plot(g.t, g.epi_median, 's-', color=GR, ms=3, lw=0.8)
ax.plot([], [], 'o-', color=C1, label='Central field (< 500 px from centre)'); ax.plot([], [], 's-', color=GR, label='Whole image')
ax.axhline(0.731, color=C2, ls='--', lw=1, label='Reference: 2026-10-21 clip, whole image (Field Note #13)')
ax.set_ylim(0, 1.6); ax.set_xticks(range(10, 13)); ax.set_xticklabels([f'{h}:00' for h in range(10, 13)])
ax.set_xlabel('Time of day, 2026-11-01 (one point per 5 min video file, 8 frame pairs)'); ax.set_ylabel('Median epipolar distance (px)')
ax.set_title('Factory calibration during 2 h 25 min of head-mounted work', loc='left', fontsize=11); ax.legend(frameon=False, fontsize=8.5, loc='upper right')
save(fig, 'fn16_calibration_over_time')
print(TF.interval_us.describe(), (TF.interval_us > 50000).sum())
