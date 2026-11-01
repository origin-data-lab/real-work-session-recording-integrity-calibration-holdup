"""ODL 분석용 축약 패키지 만들기 (R8 스테레오+IMU 녹화 폴더 -> 작은 ZIP)

원본 30분 영상 대신 분석에 필요한 것만 뽑습니다:
  * 프레임별 SEI 타임스탬프/노출시간 (CSV, 좌/우)          -> 모션 블러, 동기, 프레임 누락 분석
  * 5분 파일당 8쌍 좌/우 정지 프레임 (JPEG 95)                -> 캘리브레이션 유지(에피폴라) 검사
  * 세션 가운데 30초 클립 1개 (재인코딩 없이 잘라냄, SEI 유지)   -> 블러/특징점 추적 확인
  * .imu, .log 원본 그대로

설치 (한 번만):   pip install imageio-ffmpeg
실행:             python odl_pack_for_analysis.py "녹화폴더" [--frames 8] [--clip 30]
결과:             녹화폴더 안에 ODL_pack_YYYYMMDD_HHMMSS.zip (세션마다 1개)
"""
import argparse, glob, os, re, struct, subprocess, sys, zipfile, csv, shutil, tempfile

def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        if shutil.which('ffmpeg'): return 'ffmpeg'
        sys.exit('ffmpeg를 찾을 수 없습니다: pip install imageio-ffmpeg')

FF = ffmpeg_exe()

def sei_rows(vid):
    """H.264 SEI(user payload 240, 'SVH') -> (svh_pts, exposure_start_us, exposure_us, strobe_seq, flags)"""
    p = subprocess.run([FF, '-v', 'error', '-i', vid, '-map', '0:v', '-c', 'copy', '-bsf:v', 'h264_mp4toannexb', '-f', 'h264', '-'], capture_output=True)
    b = p.stdout; rows = []
    for m in re.finditer(re.escape(b'\x00\x00\x01\x06\xf0\x28'), b):
        raw = b[m.start() + 6:m.start() + 6 + 60].replace(b'\x00\x00\x03', b'\x00\x00')[:40]
        if len(raw) < 36: continue
        pts, exs = struct.unpack('<QQ', raw[8:24]); ext, strobe, flags = struct.unpack('<III', raw[24:36])
        rows.append((pts, exs, ext, strobe, flags))
    return rows

def duration_s(vid):
    p = subprocess.run([FF, '-i', vid], capture_output=True, text=True, errors='ignore')
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0

def grab_frames(vid, n, outdir, tag, total):
    """ffmpeg로 프레임 추출 (Windows 한글 경로에서도 동작하도록 OpenCV를 쓰지 않음)"""
    if total <= 0: return []
    want = sorted({int(total * (i + 0.5) / n) for i in range(n)})
    sel = '+'.join(f'eq(n\\,{w})' for w in want)
    pat = os.path.join(outdir, f'__tmp_{tag}_%03d.jpg')
    subprocess.run([FF, '-v', 'error', '-i', vid, '-vf', f"select='{sel}'", '-fps_mode', 'passthrough', '-q:v', '2', pat])
    saved = []
    for k, w in enumerate(want, 1):
        p = os.path.join(outdir, f'__tmp_{tag}_{k:03d}.jpg')
        if os.path.exists(p):
            name = f'{tag}_f{w:06d}.jpg'; os.replace(p, os.path.join(outdir, name)); saved.append(name)
    return saved

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('folder'); ap.add_argument('--frames', type=int, default=8); ap.add_argument('--clip', type=int, default=30)
    a = ap.parse_args(); folder = os.path.abspath(a.folder)
    lefts = sorted(glob.glob(os.path.join(folder, '*_left_raw.mp4')))
    if not lefts: sys.exit('*_left_raw.mp4 파일이 없습니다: ' + folder)
    sessions = {}
    for L in lefts:
        base = os.path.basename(L)[:-len('_left_raw.mp4')]          # 20261101_101500_00000
        sessions.setdefault('_'.join(base.split('_')[:2]), []).append(base)
    for sess, bases in sessions.items():
        tmp = tempfile.mkdtemp(); print(f'== 세션 {sess}: 파일 {len(bases)}개')
        for f in glob.glob(os.path.join(folder, sess + '_*.imu')) + glob.glob(os.path.join(folder, sess + '_*.log')):
            shutil.copy(f, tmp)
        clip_base = bases[len(bases) // 2]   # 30초 클립은 세션 가운데 파일 1개에서만
        for base in bases:
            for eye in ('left', 'right'):
                vid = os.path.join(folder, f'{base}_{eye}_raw.mp4')
                if not os.path.exists(vid): print('  없음:', vid); continue
                tag = f'{base}_{eye}'
                rows = sei_rows(vid)
                with open(os.path.join(tmp, tag + '_sei.csv'), 'w', newline='') as fh:
                    w = csv.writer(fh); w.writerow(['svh_pts', 'exposure_start_us', 'exposure_us', 'strobe_seq', 'flags']); w.writerows(rows)
                os.makedirs(os.path.join(tmp, 'frames'), exist_ok=True)
                fr = grab_frames(vid, a.frames, os.path.join(tmp, 'frames'), tag, len(rows))
                if a.clip > 0 and base == clip_base:
                    d = duration_s(vid); st = max(0.0, d / 2 - a.clip / 2)
                    os.makedirs(os.path.join(tmp, 'clips'), exist_ok=True)
                    subprocess.run([FF, '-v', 'error', '-ss', f'{st:.2f}', '-i', vid, '-t', str(a.clip), '-map', '0:v', '-c', 'copy', os.path.join(tmp, 'clips', f'{tag}_mid{a.clip}s.mp4')])
                print(f'  {tag}: SEI {len(rows)}프레임, 정지프레임 {len(fr)}장')
        z = os.path.join(folder, f'ODL_pack_{sess}.zip')
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
            for p in glob.glob(tmp + '/**', recursive=True):
                if os.path.isfile(p): zf.write(p, os.path.relpath(p, tmp))
        shutil.rmtree(tmp); print(f'  -> {z}  ({os.path.getsize(z)/1e6:.0f} MB)')

if __name__ == '__main__':
    main()
