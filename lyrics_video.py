#!/usr/bin/env python3
"""
lyrics_video.py — mp3 + 가사 txt → 가사가 아래에서 위로 흘러가는 mp4

화면에는 음악과 가사만 나옵니다. 검은 배경에 흰 글씨, 지금 부르는 줄은 밝게,
나머지 줄은 흐리게 보이고, 부르는 줄이 화면 가운데를 지나가도록 가사 전체가 위로 움직입니다.

  python lyrics_video.py Here-00.mp3 Here-00.txt                 # → Here-00.mp4
  python lyrics_video.py Here-00.mp3 Here-00.txt --device cuda      # 정렬은 GPU, 인코딩은 CPU
  python lyrics_video.py Here-00.mp3 Here-00.txt --times Here-00.times.json   # 정렬 재사용
  python lyrics_video.py run.mp3 run.txt --photos a.jpg b.jpg c.jpg d.jpg      # 사진 배경
  python lyrics_video.py hello.mp3 hello.txt --photos p*.jpg --posters posters/  # 팀 포스터

포스터 (--posters 폴더 또는 파일들)
  · 팀 포스터를 두 장면으로 보여 줍니다. 모든 팀이 같은 시간만큼 나옵니다.
    0) --poster-span full: 첫 가사부터 마지막 후렴 전까지 곡 전체를 묶음 화면으로 (포스터 중심 영상)
    1) 묶음 화면: 16장 → 8장 → 4장(--poster-layouts)으로 배치를 바꿔 가며 넘김.
       장면마다 등장 효과가 바뀜 (하나씩 튀어나옴 / 줄마다 좌우에서 밀려옴 / 천천히 다가감).
       모든 포스터가 한 번은 나오고, 시간이 남으면 다른 포스터부터 다시 돌림.
    2) 모자이크: 전체 포스터를 한 화면에 깔고, 가운데 한 장에서 천천히 뒤로 빠지며 전체가 드러남
  · 구간은 가사 태그로 자동으로 잡습니다: [Verse 2] ~ [Bridge] 직전 = 묶음 화면,
    [Final Chorus](없으면 마지막 [Chorus]) ~ 끝 = 모자이크. 태그가 없으면 곡의 35~60% / 78%~끝.
    직접 정하려면 --poster-grid 60 105 --poster-mosaic 150 (초).
  · 포스터가 나오는 동안 가사는 화면 아래 자막 한 줄로 바뀝니다.
  · 파일 이름 순서대로 배치하니 01_팀이름.jpg 처럼 번호를 붙여 두세요. (jpg/png, PDF 는 이미지로 변환)

시작 인사말 (--intro-text, --intro-sign, --intro-sec)
  · 영상 처음 몇 초(기본 5초) 동안 화면을 어둡게 하고 인사말을 가운데에 보여 줍니다.
    줄은 | 로 나누고 첫 줄은 크게, 서명은 아래에 작게. 0.8초 동안 나타났다 사라집니다.

사진·영상 배경 (--photos, 같은 뜻으로 --media)
  · 사진과 영상(mp4/mov/m4v/mkv/webm)을 섞어서 순서대로 줄 수 있습니다.
  · 영상은 자기 길이만큼(최대 --clip-max 15초) 재생되고, 사진은 남는 시간을 똑같이 나눠 가집니다.
    영상 소리는 쓰지 않고 노래만 나옵니다. 세로 영상도 사진처럼 잘리지 않게 맞춥니다.
  · 사진은 천천히 확대·이동하며, 모든 항목이 1.5초 동안 겹쳐 바뀝니다.
  · 가사가 잘 보이도록 사진을 어둡게 깝니다 (--photo-dim, 기본 0.5).
  · 휴대폰 사진의 회전 정보(EXIF)를 반영합니다.
  · --photo-fit auto(기본): 화면과 비율이 비슷한 사진은 화면을 꽉 채우고(cover),
    세로 사진처럼 비율이 많이 다른 사진은 잘리지 않게 전체를 가운데 두고(contain),
    빈 양옆은 같은 사진을 흐리게 확대해 채웁니다. cover / contain 으로 고정할 수도 있습니다.

가사 파일
  · 빈 줄 = 덩어리 경계 (덩어리 사이를 조금 더 띄움)
  · [Verse 1], [Chorus] 같은 Suno 태그 줄은 자동으로 빠짐 (Suno 에 넣은 가사 그대로 써도 됨)

타이밍
  · stable-ts 로 곡과 가사를 맞춰 줄마다 시작 시각을 구하고 <곡>.times.json 에 저장합니다.
  · 시각이 어긋난 줄은 이 JSON 의 start 값을 고친 뒤 --times 로 다시 주면 됩니다.
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

TAG_RE = re.compile(r"^\[[^\]]*\]$")
FONT_CANDIDATES = [
    "NotoSansKR-Medium.ttf", "NotoSansKR-Regular.ttf", "NotoSansKR[wght].ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    os.path.expanduser("~/.fonts/NotoSansKR-Medium.ttf"),
]


# ── 가사 ─────────────────────────────────────────────────────────
def read_lyrics(path):
    lines, block, tags = [], 0, []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or TAG_RE.match(s):
            if s:
                tags.append(s[1:-1].strip().lower())
            if lines and lines[-1]["block"] == block:
                block += 1
            continue
        first = not lines or lines[-1]["block"] != block
        lines.append(dict(text=s, block=block, tag=" | ".join(tags) if first else ""))
        if first:
            tags = []
    if not lines:
        sys.exit("가사 줄이 없습니다.")
    return lines


def _norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def align(mp3, lines, model_name, device, language):
    import stable_whisper
    print(f"  가사 정렬 (stable-ts {model_name}, {device}) …")
    model = stable_whisper.load_model(model_name, device=device)
    r = model.align(mp3, "\n".join(l["text"] for l in lines), language=language)
    words = [(w.word, float(w.start), float(w.end)) for s in r.segments for w in s.words]
    # 글자 수 누적으로 단어를 줄에 배정
    bounds, pos = [], 0
    for l in lines:
        k = len(_norm(l["text"])); bounds.append((pos, pos + k)); pos += k
    per, cur = [[] for _ in lines], 0
    for w, st, en in words:
        k = len(_norm(w))
        if k == 0 or en <= st:
            cur += k; continue
        i = next((n for n, (a, b) in enumerate(bounds) if a <= cur < b), len(lines) - 1)
        per[i].append((st, en)); cur += k
    for l, ws in zip(lines, per):
        l["start"] = ws[0][0] if ws else None
        l["end"] = ws[-1][1] if ws else None
    fill_missing(lines)


def fill_missing(lines):
    known = [i for i, l in enumerate(lines) if l.get("start") is not None]
    if not known:
        sys.exit("정렬된 줄이 없습니다.")
    for i, l in enumerate(lines):
        if l.get("start") is None:
            p = max([k for k in known if k < i], default=None)
            n = min([k for k in known if k > i], default=None)
            if p is not None and n is not None:
                a0, b0 = lines[p]["start"], lines[n]["start"]
                l["start"] = a0 + (b0 - a0) * (i - p) / (n - p)
            elif p is not None:
                l["start"] = lines[p]["start"] + 2.0 * (i - p)
            else:
                l["start"] = max(0.0, lines[n]["start"] - 2.0 * (n - i))
    # 시작 시각이 거꾸로 가지 않게
    for i in range(1, len(lines)):
        if lines[i]["start"] < lines[i - 1]["start"] + 0.05:
            lines[i]["start"] = lines[i - 1]["start"] + 0.05


def duration_of(mp3):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", mp3], capture_output=True, text=True)
    return float(out.stdout.strip())


# ── 렌더링 ───────────────────────────────────────────────────────
def find_font(user):
    for p in ([user] if user else []) + FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    sys.exit("한글 폰트를 찾지 못했습니다. --font 로 .ttf/.otf/.ttc 경로를 주세요.")


def line_image(text, font_path, size, max_w):
    while True:
        font = ImageFont.truetype(font_path, size)
        x0, y0, x1, y1 = font.getbbox(text)
        if x1 - x0 <= max_w or size <= 20:
            break
        size -= 2
    pad = max(4, size // 4)                       # 그림자가 번질 여백
    img = Image.new("L", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), 0)
    ImageDraw.Draw(img).text((pad - x0, pad - y0), text, font=font, fill=255)
    sh = img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(size / 8))
    return (np.asarray(img, dtype=np.float32) / 255.0,
            np.clip(np.asarray(sh, dtype=np.float32) / 255.0 * 1.6, 0, 1))


VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi")


def probe_video(path):
    """(가로, 세로, 길이초) — 휴대폰 영상의 회전 정보를 반영한 실제 화면 크기."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration",
                          "-of", "json", path], capture_output=True, text=True).stdout
    d = json.loads(out or "{}")
    st = (d.get("streams") or [{}])[0]
    w, h = int(st.get("width", 0)), int(st.get("height", 0))
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((st.get("tags") or {}).get("rotate", 0)))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h, float((d.get("format") or {}).get("duration", 0) or 0)


class VideoClip:
    """영상 파일을 ffmpeg 로 화면 크기에 맞춰 한 프레임씩 읽는다 (소리는 쓰지 않음).
    cover = 꽉 채워 자름, contain = 전체를 보이고 빈 곳은 같은 영상을 흐리게."""

    def __init__(self, path, W, H, fps, mode):
        self.path, self.W, self.H, self.fps, self.mode = path, W, H, fps, mode
        _, _, self.len = probe_video(path)
        self.len = max(self.len, 1.0 / fps)
        self.proc = None; self.idx = 0; self.last = None

    def _start(self):
        W, H = self.W, self.H
        if self.mode == "cover":
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={self.fps},format=rgb24"
        else:
            vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"boxblur=20:2,eq=brightness=-0.25[bg];"
                  f"[b]scale={int(W * 0.96)}:{int(H * 0.94)}:force_original_aspect_ratio=decrease[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={self.fps},format=rgb24")
        self.close()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", self.path, "-an", "-filter_complex", vf,
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        self.idx = 0

    def frame(self, lt):
        """영상 안 시각 lt 의 프레임 (영상보다 길면 처음부터 반복)."""
        want = int((lt % self.len) * self.fps)
        if self.proc is None or want < self.idx - 1:
            self._start()
        n = self.W * self.H * 3
        while self.idx <= want or self.last is None:
            buf = self.proc.stdout.read(n)
            if len(buf) < n:                       # 끝: 처음부터 다시
                if self.last is not None and want >= self.idx - 1:
                    break
                self._start(); continue
            self.last = np.frombuffer(buf, dtype=np.uint8).reshape(self.H, self.W, 3)
            self.idx += 1
        return self.last.astype(np.float32)

    def close(self):
        if self.proc:
            self.proc.kill(); self.proc.wait(); self.proc = None


class PhotoBG:
    """사진·영상 배경: 사진은 천천히 확대·이동(Ken Burns), 영상은 그대로 재생. 교차 페이드 + 어둡게.
    비율이 화면과 많이 다른 것(세로 사진·세로 영상 등)은 자르지 않고 전체를 보이고 빈 곳은 흐리게 채운다.
    영상은 자기 길이만큼(--clip-max 상한) 머물고, 사진은 남는 시간을 나눠 가진다."""
    ZOOM = 0.10          # cover: 한 장이 머무는 동안 확대되는 비율
    ZOOM_FIT = 0.05      # contain: 전경 사진이 커지는 비율 (작게)
    FADE = 1.5           # 교차 페이드 길이(초)
    AUTO_TOL = 0.35      # auto: 비율 차이(log)가 이보다 크면 contain — 4:3·3:2 가로는 cover, 정사각·세로는 contain
    MIN_PHOTO = 3.0      # 사진 한 장 최소 시간(초)

    def __init__(self, paths, W, H, dur, dim, fit="auto", fps=30, clip_max=15.0):
        self.W, self.H, self.dur, self.dim = W, H, dur, dim
        self.items = []
        fr = W / H
        pick = lambda r: fit if fit != "auto" else ("cover" if abs(np.log(r / fr)) <= self.AUTO_TOL else "contain")
        for p in paths:
            if Path(p).suffix.lower() in VIDEO_EXTS:
                w, h, ln = probe_video(p)
                if not w or not h:
                    print(f"    ⚠ {Path(p).name}: 영상을 읽지 못해 건너뜁니다"); continue
                mode = pick(w / h)
                clip = VideoClip(p, W, H, fps, mode)
                self.items.append(dict(mode="video", clip=clip, want=min(ln, clip_max)))
                print(f"    {Path(p).name}: 영상 {w}x{h} {ln:.1f}초 → {mode}, {min(ln, clip_max):.1f}초 사용")
                continue
            im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
            mode = pick(im.width / im.height)
            if mode == "cover":
                sc = max(W * (1 + self.ZOOM) / im.width, H * (1 + self.ZOOM) / im.height)
                big = im.resize((int(im.width * sc) + 2, int(im.height * sc) + 2), Image.LANCZOS)
                self.items.append(dict(mode="cover", img=big))
            else:
                sc = max(W / im.width, H / im.height)
                bg = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.BILINEAR)
                l, t = (bg.width - W) // 2, (bg.height - H) // 2
                bg = bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(W / 40))
                bg = np.asarray(bg, dtype=np.float32) * 0.55
                fs = min(W * 0.96 / im.width, H * 0.94 / im.height)
                fw, fh = im.width * fs, im.height * fs
                fg = im.resize((int(fw * (1 + self.ZOOM_FIT)) + 1, int(fh * (1 + self.ZOOM_FIT)) + 1),
                               Image.LANCZOS)
                self.items.append(dict(mode="contain", bg=bg, fg=fg, fw=fw, fh=fh))
            print(f"    {Path(p).name}: {im.width}x{im.height} → {mode}")
        self.n = len(self.items)
        if not self.n:
            sys.exit("--photos 에서 쓸 수 있는 사진·영상이 없습니다.")
        # 구간 나누기: 영상은 자기 길이, 사진은 남는 시간을 똑같이 (최소 MIN_PHOTO)
        vids = sum(it["want"] for it in self.items if it["mode"] == "video")
        n_ph = sum(1 for it in self.items if it["mode"] != "video")
        ph = max(self.MIN_PHOTO, (dur - vids) / n_ph) if n_ph else 0.0
        lens = [it["want"] if it["mode"] == "video" else ph for it in self.items]
        k = dur / sum(lens)                        # 곡 길이에 맞게 늘이거나 줄임 (영상이 늘어나면 반복 재생)
        t = 0.0
        for it, L in zip(self.items, lens):
            it["start"], it["end"] = t, t + L * k; t += L * k
        self.seg = dur / self.n                    # (표시용 평균)

    def _frame(self, k, t):
        """k 번째 항목의 시각 t 화면."""
        it = self.items[k]
        u = float(np.clip((t - it["start"]) / max(1e-6, it["end"] - it["start"]), 0, 1))
        if it["mode"] == "video":
            return it["clip"].frame(max(0.0, t - it["start"] + self.FADE))   # 페이드 동안에도 이미 재생
        if it["mode"] == "cover":
            im = it["img"]
            z = 1 + self.ZOOM * (u if k % 2 == 0 else 1 - u)      # 번갈아 확대/축소
            cw, ch = self.W * (1 + self.ZOOM) / z, self.H * (1 + self.ZOOM) / z
            cw, ch = min(cw, im.width), min(ch, im.height)
            dx = (im.width - cw) * (u if k % 3 != 1 else 1 - u)    # 번갈아 좌우 이동
            dy = (im.height - ch) * 0.5
            return np.asarray(im.resize((self.W, self.H), Image.BILINEAR,
                                        box=(dx, dy, dx + cw, dy + ch)), dtype=np.float32)
        z = 1 + self.ZOOM_FIT * (u if k % 2 == 0 else 1 - u)
        w, h = int(it["fw"] * z), int(it["fh"] * z)
        fg = np.asarray(it["fg"].resize((w, h), Image.BILINEAR), dtype=np.float32)
        out = it["bg"].copy()
        x0, y0 = (self.W - w) // 2, (self.H - h) // 2
        xs, ys = max(0, -x0), max(0, -y0)
        xe, ye = min(w, self.W - x0), min(h, self.H - y0)
        out[y0 + ys:y0 + ye, x0 + xs:x0 + xe] = fg[ys:ye, xs:xe]
        return out

    def at(self, t):
        k = next((i for i, it in enumerate(self.items) if t < it["end"]), self.n - 1)
        out = self._frame(k, t)
        if k > 0 and self.items[k - 1]["mode"] == "video" and t > self.items[k]["start"] + 0.1:
            self.items[k - 1]["clip"].close()                      # 끝난 영상은 닫기
        nxt = self.items[k]["end"]
        if k + 1 < self.n and t > nxt - self.FADE:
            w = (t - (nxt - self.FADE)) / self.FADE
            out = out * (1 - w) + self._frame(k + 1, t) * w
        if t < 1.0:                                               # 처음 1초 페이드 인
            out = out * t
        if t > self.dur - 2.0:                                    # 마지막 2초 페이드 아웃
            out = out * max(0.0, (self.dur - t) / 2.0)
        return out * (1 - self.dim)

    def close(self):
        for it in self.items:
            if it["mode"] == "video":
                it["clip"].close()


def load_poster_paths(items):
    exts = (".jpg", ".jpeg", ".png", ".webp")
    out = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted(str(q) for q in p.iterdir() if q.suffix.lower() in exts)
        elif p.suffix.lower() in exts:
            out.append(str(p))
    return out


def poster_windows(lines, dur, args):
    """가사 태그로 묶음 화면 구간과 모자이크 구간을 정한다."""
    def first(pred, after=-1.0):
        for l in lines:
            if l.get("tag") and pred(l["tag"]) and l["start"] > after:
                return l["start"]
        return None
    grid = mosaic = None
    v2 = first(lambda g: re.search(r"verse\s*2", g))
    if v2 is not None:
        br = first(lambda g: "bridge" in g, v2) or first(lambda g: "chorus" in g and "final" not in g, v2)
        if br is not None:
            # 두 번째 후렴이 끝날 때까지: 브리지 시작 직전
            grid = (max(0.0, v2 - 0.5), br - 0.3)
    fin = first(lambda g: "final" in g)
    if fin is None:
        ch = [l["start"] for l in lines if l.get("tag") and "chorus" in l["tag"]]
        fin = ch[-1] if len(ch) >= 2 else None
    if fin is not None:
        mosaic = (max(0.0, fin - 0.5), dur)
    src = "가사 태그"
    if args.poster_grid:
        grid = tuple(args.poster_grid); src = "직접 지정"
    if args.poster_mosaic:
        m = args.poster_mosaic
        mosaic = (m[0], m[1] if len(m) > 1 else dur); src = "직접 지정"
    if grid is None and mosaic is None:
        grid, mosaic, src = (dur * 0.35, dur * 0.60), (dur * 0.78, dur), "기본 비율(태그 없음)"
    if getattr(args, "poster_span", "tags") == "full" and not args.poster_grid:
        # 곡 전체를 포스터로: 첫 가사부터 모자이크 직전까지 묶음 화면
        if mosaic is None:
            mosaic = (dur * 0.82, dur)
        g0 = max(0.0, lines[0]["start"] - 1.0)
        grid, src = (g0, mosaic[0] - 0.2), src + " · 전체 구간"
    return grid, mosaic, src


class PosterShow:
    """팀 포스터: 4장 묶음 화면을 고르게 넘기고, 마지막엔 전체 모자이크에서 천천히 뒤로 빠진다."""
    EDGE = 0.6          # 포스터 장면 들어오고 나갈 때 페이드(초)
    XF = 0.3            # 묶음 화면끼리 교차 페이드(초)

    def __init__(self, paths, W, H, grid, mosaic, per, bg):
        self.W, self.H, self.grid, self.mosaic, self.per = W, H, grid, mosaic, per
        self.bgc = tuple(int(v) for v in bg)
        self._cache = {}
        ims = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in paths]
        self.n = len(ims)
        # ── 묶음 화면: 16장 → 8장 → 4장 … 배치를 바꿔 가며 장면을 이어 붙인다
        self.ims = ims
        self.scenes = []
        if grid:
            self.scenes = self._plan(grid, per)
            used = sorted({i for sc in self.scenes for i in sc["idx"]})
            desc = " → ".join(f'{sc["k"]}장' for sc in self.scenes[:6]) + (" …" if len(self.scenes) > 6 else "")
            print(f"  묶음 화면 {len(self.scenes)}개 ({desc}), 포스터 {len(used)}/{self.n}장 노출")
        # ── 모자이크 미리 그리기
        if mosaic:
            asp = float(np.median([im.width / im.height for im in ims]))
            best = None
            for cols in range(1, self.n + 1):
                rows = int(np.ceil(self.n / cols))
                ratio = cols * asp / rows
                score = abs(np.log(ratio / (W / H))) + 0.02 * (cols * rows - self.n)
                if best is None or score < best[0]:
                    best = (score, cols, rows)
            _, cols, rows = best
            chp = int(min(H * 0.7, 9000 / rows)); cwp = int(chp * asp); gap = max(4, chp // 30)
            MW, MH = cols * (cwp + gap) + gap, rows * (chp + gap) + gap
            # 전체가 보이는 마지막 화면(16:9)이 캔버스 안에 들어오도록 여백을 충분히
            if MW / MH > W / H:
                ew = MW * 1.04; eh = ew * H / W
            else:
                eh = MH * 1.04; ew = eh * W / H
            padx = int(max(MW * 0.06, (ew - MW) / 2 + 8))
            pady = int(max(MH * 0.06, (eh - MH) / 2 + 8))
            mz = Image.new("RGB", (MW + 2 * padx, MH + 2 * pady), self.bgc)
            for i, im in enumerate(ims):
                r, c = divmod(i, cols)
                if r == rows - 1:                               # 마지막 줄은 가운데 정렬
                    c += (cols * rows - self.n) / 2
                sc = min(cwp / im.width, chp / im.height)
                t = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
                x = int(padx + gap + c * (cwp + gap) + (cwp - t.width) / 2)
                y = int(pady + gap + r * (chp + gap) + (chp - t.height) / 2)
                mz.paste(t, (x, y))
            self.mz, self.cols, self.rows = mz, cols, rows
            self.mz_full = (padx, pady, MW, MH)
            mid = (self.n - 1) // 2; r, c = divmod(mid, cols)
            self.start_c = (padx + gap + c * (cwp + gap) + cwp / 2, pady + gap + r * (chp + gap) + chp / 2)
            self.start_h = chp * 1.25
            print(f"  모자이크 {cols}x{rows} ({mz.width}x{mz.height}px)")

    # ---- 묶음 화면 ------------------------------------------------------
    BASE_DUR = {16: 5.0, 12: 4.4, 9: 4.0, 8: 3.8, 6: 3.4, 4: 3.0, 3: 2.8, 2: 2.6, 1: 2.4}

    def _layout(self, k):
        """k 장을 16:9 화면(아래 자막 자리 비움)에 가장 크게 놓는 행·열."""
        W, H = self.W, self.H
        asp = float(np.median([im.width / im.height for im in self.ims]))
        aw, ah = W * 0.96, H * 0.76
        best = None
        for rows in range(1, k + 1):
            cols = int(np.ceil(k / rows))
            cw, ch = aw / cols, ah / rows
            ph = min(ch * 0.92, cw * 0.92 / asp)
            if best is None or ph > best[0]:
                best = (ph, rows, cols)
        ph, rows, cols = best
        return rows, cols, ph, ph * asp

    def _plan(self, grid, per):
        """창 길이에 맞춰 장면 목록을 만든다. 모든 포스터가 한 번은 나오게 하고, 시간이 남으면 처음부터 다시."""
        layouts = list(per) if isinstance(per, (list, tuple)) else [per]
        a, b = grid
        L = b - a
        # 한 바퀴(모든 포스터)에 필요한 장면들
        def one_pass(start_idx=0):
            sc, i, li = [], start_idx, 0
            while i < start_idx + self.n:
                k = layouts[li % len(layouts)]; li += 1
                idx = [(i + j) % self.n for j in range(min(k, start_idx + self.n - i))]
                sc.append(dict(k=k, idx=idx)); i += len(idx)
            return sc
        scenes = one_pass()
        need = sum(self.BASE_DUR.get(s["k"], 3.0) for s in scenes)
        if need > L:                                   # 시간이 모자라면 큰 묶음만으로
            big = max(layouts)
            scenes = [dict(k=big, idx=list(range(i, min(i + big, self.n)))) for i in range(0, self.n, big)]
            need = sum(self.BASE_DUR.get(s["k"], 3.0) for s in scenes)
            if need > L:
                print(f"  ⚠ 묶음 화면 구간({L:.0f}초)이 짧아 장면당 {L / len(scenes):.1f}초로 빠르게 넘깁니다.")
        else:                                           # 시간이 남으면 처음부터 다시 돌림
            off = 0
            while need + 3.0 < L:
                off = (off + 7) % self.n                # 매번 다른 포스터부터
                for s2 in one_pass(off):
                    d = self.BASE_DUR.get(s2["k"], 3.0)
                    if need + d > L:
                        break
                    scenes.append(s2); need += d
                else:
                    continue
                break
        scale = L / need
        t = a
        for n_, sc in enumerate(scenes):
            d = self.BASE_DUR.get(sc["k"], 3.0) * scale
            rows, cols, ph, pw = self._layout(sc["k"])
            sc.update(start=t, end=t + d, rows=rows, cols=cols, ph=ph, pw=pw,
                      fx=("pop", "slide", "zoom")[n_ % 3] if len(layouts) > 1 else "zoom")
            t += d
        return scenes

    def _thumb(self, i, w, h):
        key = (i, int(w), int(h))
        c = self._cache.get(key)
        if c is None:
            im = self.ims[i]
            sc = min(w / im.width, h / im.height)
            c = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
            self._cache[key] = c
        return c

    def _draw_scene(self, sc, lt):
        """장면 sc 를 장면 안 시각 lt 에서 그린다. 등장 효과: pop(하나씩 튀어나옴) / slide(줄마다 좌우에서) / zoom(천천히 다가감)."""
        W, H = self.W, self.H
        cv = Image.new("RGB", (W, H), self.bgc)
        rows, cols, pw, ph = sc["rows"], sc["cols"], sc["pw"], sc["ph"]
        k = len(sc["idx"])
        aw, ah = W * 0.96, H * 0.76
        cw, ch = aw / cols, ah / rows
        y0 = H * 0.43 - ah / 2
        dur = sc["end"] - sc["start"]
        z = 1.0 + (0.05 * lt / dur if sc["fx"] == "zoom" else 0.0)
        for j, i in enumerate(sc["idx"]):
            r, c = divmod(j, cols)
            n_in_row = min(cols, k - r * cols)
            xoff = (cols - n_in_row) * cw / 2                     # 덜 찬 줄은 가운데로
            cx = W * 0.02 + xoff + c * cw + cw / 2
            cy = y0 + r * ch + ch / 2
            a = 1.0; s = 1.0; dx = 0.0
            if sc["fx"] == "pop":
                d0 = j * min(0.06, 0.9 / max(1, k))
                u = float(np.clip((lt - d0) / 0.35, 0, 1)); a = u; s = 0.8 + 0.2 * (1 - (1 - u) ** 3)
            elif sc["fx"] == "slide":
                u = float(np.clip((lt - r * 0.12) / 0.6, 0, 1)); e = 1 - (1 - u) ** 3
                dx = (1 - e) * W * 0.6 * (-1 if r % 2 == 0 else 1); a = u
            else:
                u = float(np.clip((lt - j * 0.08) / 0.5, 0, 1)); a = u
            if a <= 0:
                continue
            w_, h_ = pw * s * z, ph * s * z
            th = self._thumb(i, w_, h_)
            x = int(W / 2 + (cx - W / 2) * z + dx - th.width / 2)
            y = int(H * 0.43 + (cy - H * 0.43) * z - th.height / 2)
            if a >= 1:
                cv.paste(th, (x, y))
            else:
                cv.paste(th, (x, y), Image.new("L", th.size, int(255 * a)))
        return np.asarray(cv, dtype=np.float32)

    def _edge(self, t, w):
        a, b = w
        return float(np.clip(min((t - a) / self.EDGE, (b - t) / self.EDGE), 0, 1))

    def at(self, t):
        """(화면, 섞는 비율) — 포스터 구간이 아니면 (None, 0)."""
        if self.scenes and self.grid[0] <= t < self.grid[1]:
            k = next((n for n, sc in enumerate(self.scenes) if t < sc["end"]), len(self.scenes) - 1)
            sc = self.scenes[k]
            fr = self._draw_scene(sc, t - sc["start"])
            rem = sc["end"] - t
            if k + 1 < len(self.scenes) and rem < self.XF:          # 다음 장면으로 교차 페이드
                w = 1 - rem / self.XF
                fr = fr * (1 - w) + self._draw_scene(self.scenes[k + 1], 0.0) * w
            return fr, self._edge(t, self.grid)
        if self.mosaic and self.mosaic[0] <= t <= self.mosaic[1]:
            a, b = self.mosaic
            pull = min(12.0, (b - a) * 0.6)
            u = float(np.clip((t - a) / pull, 0, 1)); u = u * u * (3 - 2 * u)     # smoothstep
            px, py, MW, MH = self.mz_full
            if MW / MH > self.W / self.H:
                end_w = MW * 1.04; end_h = end_w * self.H / self.W
            else:
                end_h = MH * 1.04; end_w = end_h * self.W / self.H
            h0 = self.start_h
            h = np.exp(np.log(h0) * (1 - u) + np.log(end_h) * u)              # 로그 보간 → 일정한 속도로 빠짐
            w = h * self.W / self.H
            cx = self.start_c[0] * (1 - u) + (px + MW / 2) * u
            cy = self.start_c[1] * (1 - u) + (py + MH / 2) * u
            if u >= 1:                                                         # 다 빠진 뒤엔 아주 천천히 다가감
                z = 1 - 0.03 * min(1.0, (t - a - pull) / max(1.0, b - a - pull))
                w, h = w * z, h * z
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            mw, mh = self.mz.size
            if box[0] < 0 or box[1] < 0 or box[2] > mw or box[3] > mh:      # 안전장치: 밖으로 나가면 잘라서 맞춤
                box = (max(0.0, box[0]), max(0.0, box[1]), min(mw, box[2]), min(mh, box[3]))
            fr = np.asarray(self.mz.resize((self.W, self.H), Image.BILINEAR, box=box), dtype=np.float32)
            return fr, self._edge(t, (a, b + self.EDGE))
        return None, 0.0


def intro_card(text, sign, font_path, W, H):
    """시작 인사말 카드: 줄마다 가운데 정렬. 첫 줄은 크게, 서명은 작게 아래쪽에. (마스크, 그림자) 반환."""
    lines = [l.strip() for l in re.split(r"\s*\|\s*|\n", text) if l.strip()]
    big, mid, small = int(H * 0.062), int(H * 0.046), int(H * 0.036)
    rows = [(lines[0], big)] + [(l, mid) for l in lines[1:]] if lines else []
    gaps = [int(big * 0.9)] + [int(mid * 0.55)] * max(0, len(rows) - 1)
    imgs = [line_image(t, font_path, sz, int(W * 0.86)) for t, sz in rows]
    sign_img = line_image(sign, font_path, small, int(W * 0.8)) if sign else None
    total = sum(m.shape[0] for m, _ in imgs) + sum(gaps[:-1]) + \
        ((int(mid * 1.6) + sign_img[0].shape[0]) if sign_img else 0)
    mask = np.zeros((H, W), np.float32); shadow = np.zeros((H, W), np.float32)
    y = int((H - total) / 2)
    def put(m, sh, y):
        x = int((W - m.shape[1]) / 2)
        hh, ww = min(m.shape[0], H - y), min(m.shape[1], W - x)
        if hh > 0 and y >= 0:
            mask[y:y + hh, x:x + ww] = np.maximum(mask[y:y + hh, x:x + ww], m[:hh, :ww])
            shadow[y:y + hh, x:x + ww] = np.maximum(shadow[y:y + hh, x:x + ww], sh[:hh, :ww])
    for (m, sh), g in zip(imgs, gaps):
        put(m, sh, y); y += m.shape[0] + g
    if sign_img:
        y += int(mid * 1.6) - gaps[-1]
        put(sign_img[0] * 0.85, sign_img[1], y)
    return mask, shadow


def intro_alpha(t, sec, fade=0.8):
    if sec <= 0 or t >= sec:
        return 0.0
    return float(min(1.0, (t + 0.05) / fade, (sec - t) / fade))


def build_positions(lines, line_h, block_gap):
    y, ys = 0.0, []
    for i, l in enumerate(lines):
        if i and l["block"] != lines[i - 1]["block"]:
            y += block_gap
        ys.append(y); y += line_h
    return np.array(ys)


def scroll_curve(lines, ys, dur, H, lead):
    """시각 t → 화면 가운데에 올 가사 좌표. 줄이 불리기 시작할 때 그 줄이 가운데에 온다."""
    ts = [0.0] + [l["start"] for l in lines] + [dur]
    first, last = ys[0], ys[-1]
    pos = [first - H * 0.5] + list(ys) + [last + H * 0.55]
    ts = np.array(ts) - np.r_[0.0, [lead] * len(lines), 0.0]
    ts[0] = 0.0
    order = np.maximum.accumulate(ts)          # 단조 증가 보장
    return order, np.array(pos)


def nvenc_ok():
    """NVENC 사용 가능 여부를 작은 시험 인코딩으로 확인 (B200·H100 같은 데이터센터 GPU 에는 NVENC 가 없음)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1",
                        "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0


def render(args):
    mp3 = args.mp3
    out = args.out or str(Path(mp3).with_suffix(".mp4"))
    times_path = args.times or str(Path(mp3).with_suffix(".times.json"))
    lines = read_lyrics(args.lyrics)
    dur = duration_of(mp3)

    if args.times and os.path.exists(args.times):
        saved = json.load(open(args.times, encoding="utf-8"))
        if len(saved) != len(lines):
            sys.exit(f"--times 의 줄 수({len(saved)})가 가사 줄 수({len(lines)})와 다릅니다.")
        for l, s in zip(lines, saved):
            l["start"] = s.get("start"); l["end"] = s.get("end")
        fill_missing(lines)
        print(f"  타이밍 재사용: {args.times}")
    else:
        align(mp3, lines, args.model, args.device, args.language)
        json.dump([dict(text=l["text"], start=round(l["start"], 3),
                        end=round(l["end"], 3) if l.get("end") else None) for l in lines],
                  open(times_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  타이밍 저장: {times_path}  (어긋난 줄은 고친 뒤 --times 로 재사용)")

    W, H, fps = args.width, args.height, args.fps
    font_path = find_font(args.font)
    fsize = int(H * args.font_scale)
    line_h = int(fsize * 1.9)
    imgs = [line_image(l["text"], font_path, fsize, int(W * 0.88)) for l in lines]
    card = None
    if args.intro_text:
        card = intro_card(args.intro_text, args.intro_sign, font_path, W, H)
        first = lines[0]["start"] if lines else dur
        note = f" (첫 가사 {first:.1f}초 — 겹치는 동안 가사는 숨김)" if first < args.intro_sec else ""
        print(f"  시작 인사말 {args.intro_sec:g}초{note}")
    if args.photos and args.dim == 0.35:
        args.dim = 0.5                                # 사진 배경에서는 흐린 줄을 조금 더 밝게
    ys = build_positions(lines, line_h, line_h * 0.6)
    kt, kp = scroll_curve(lines, ys, dur, H, args.lead)
    starts = np.array([l["start"] for l in lines])
    bg = np.array(args.bg, dtype=np.float32)
    photos = PhotoBG(args.photos, W, H, dur, args.photo_dim, args.photo_fit, fps, args.clip_max) \
        if args.photos else None
    posters = None
    if args.posters:
        pp = load_poster_paths(args.posters)
        if not pp:
            sys.exit("--posters 에서 이미지(jpg/png/webp)를 찾지 못했습니다.")
        grid, mosaic, src = poster_windows(lines, dur, args)
        fmt = lambda w: f"{w[0]:.1f}~{w[1]:.1f}초" if w else "없음"
        print(f"  포스터 {len(pp)}장 · 묶음 화면 {fmt(grid)} · 모자이크 {fmt(mosaic)} ({src})")
        lay = [args.poster_per_screen] if args.poster_per_screen else args.poster_layouts
        posters = PosterShow(pp, W, H, grid, mosaic, lay, args.poster_bg)
    if photos:
        nv = sum(1 for it in photos.items if it["mode"] == "video")
        print(f"  배경 {photos.n}개 (사진 {photos.n - nv} · 영상 {nv})")
    fg = np.array(args.fg, dtype=np.float32)

    use_nvenc = args.nvenc and nvenc_ok()
    if args.nvenc and not use_nvenc:
        print("  ⚠ 이 GPU/ffmpeg 에서는 NVENC 를 쓸 수 없어 CPU(libx264)로 인코딩합니다.")
    enc = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21"] if use_nvenc else \
          ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", mp3, *enc,
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    n_frames = int(np.ceil(dur * fps))
    cy = H * args.center
    base = np.empty((H, W, 3), dtype=np.float32)
    print(f"  렌더링 {W}x{H} {fps}fps, {n_frames}프레임 → {out}")
    for f in range(n_frames):
        t = f / fps
        p = float(np.interp(t, kt, kp))
        cur = int(np.searchsorted(starts, t + args.lead, side="right")) - 1
        if photos:
            base[:] = photos.at(t)
        else:
            base[:] = bg
        pa = 0.0
        ia = intro_alpha(t, args.intro_sec) if card else 0.0
        lf = (0.0 if t < args.intro_sec - 0.8 else 1 - ia) if card and t < args.intro_sec else 1.0   # 인사말 동안 가사 숨김
        if posters:
            pf, pa = posters.at(t)
            if pa > 0:
                base[:] = base * (1 - pa) + pf * pa
        if pa > 0 and 0 <= cur < len(imgs):
            # 포스터 위: 아래쪽을 어둡게 하고 지금 줄만 자막으로
            band = int(H * 0.76)
            grad = np.linspace(1.0, 0.35, H - band, dtype=np.float32)[:, None, None]
            base[band:] = base[band:] * (1 - pa + pa * grad)
            im, sh = imgs[cur]
            y = int(H * 0.88 - im.shape[0] / 2); x = int((W - im.shape[1]) / 2)
            y0, y1 = max(0, y), min(H, y + im.shape[0])
            reg = base[y0:y1, x:x + im.shape[1]]
            ms = (sh[y0 - y:y1 - y] * 0.8 * pa * lf)[..., None]; reg[:] = reg * (1 - ms)
            m = (im[y0 - y:y1 - y] * pa * lf)[..., None]; reg[:] = reg * (1 - m) + fg * m
        for i, (im, sh) in enumerate(imgs):
            if pa >= 1.0:
                break
            y = cy + (ys[i] - p) - im.shape[0] / 2
            if y > H or y + im.shape[0] < 0:
                continue
            # 가장자리로 갈수록 흐려지게
            d = abs((y + im.shape[0] / 2) - cy) / (H * 0.5)
            edge = max(0.0, 1.0 - d) ** 1.2
            a = (1.0 if i == cur else args.dim) * edge * (1 - pa) * lf
            if a <= 0.01:
                continue
            x = int((W - im.shape[1]) / 2)
            y0, y1 = int(max(0, y)), int(min(H, y + im.shape[0]))
            sl = im[y0 - int(y): y1 - int(y)]
            if sl.size == 0:
                continue
            region = base[y0:y0 + sl.shape[0], x:x + sl.shape[1]]
            if photos or posters:                     # 사진·포스터 위에서는 글자 뒤에 옅은 그림자
                ms = (sh[y0 - int(y): y1 - int(y)] * min(1.0, a * 1.4) * 0.75)[..., None]
                region[:] = region * (1 - ms)
            m = (sl * a)[..., None]
            region[:] = region * (1 - m) + fg * m
        if ia > 0:                                            # 시작 인사말: 화면을 어둡게 하고 글자
            base *= (1 - 0.75 * ia)
            cm, cs = card
            base *= (1 - (cs * 0.8 * ia))[..., None]
            m = (cm * ia)[..., None]
            base[:] = base * (1 - m) + fg * m
        proc.stdin.write(base.astype(np.uint8).tobytes())
        if f % (fps * 10) == 0:
            print(f"    {t:6.1f}s / {dur:.1f}s", end="\r", flush=True)
    proc.stdin.close(); proc.wait()
    if photos:
        photos.close()
    print(f"\n  완료: {out}")


def main():
    ap = argparse.ArgumentParser(description="mp3 + 가사 → 가사가 위로 흐르는 영상")
    ap.add_argument("mp3"); ap.add_argument("lyrics")
    ap.add_argument("--out", default="")
    ap.add_argument("--times", default="", help="저장된 타이밍 JSON (있으면 정렬 생략)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font", default="", help="한글 폰트 경로")
    ap.add_argument("--font-scale", type=float, default=0.05, help="글자 크기 = 화면 높이 × 이 값")
    ap.add_argument("--center", type=float, default=0.5, help="부르는 줄이 오는 높이 (0=위, 1=아래)")
    ap.add_argument("--lead", type=float, default=0.15, help="줄이 불리기 몇 초 전에 가운데 도착할지")
    ap.add_argument("--dim", type=float, default=0.35, help="부르지 않는 줄의 밝기")
    ap.add_argument("--bg", type=int, nargs=3, default=[0, 0, 0])
    ap.add_argument("--fg", type=int, nargs=3, default=[255, 255, 255])
    ap.add_argument("--photos", "--media", nargs="+", default=[],
                    help="배경 사진·영상 (jpg/png/mp4/mov 등 섞어서, 순서대로)")
    ap.add_argument("--clip-max", type=float, default=15.0, help="영상 하나를 쓰는 최대 길이(초)")
    ap.add_argument("--photo-fit", default="auto", choices=["auto", "cover", "contain"],
                    help="auto(기본)=비율이 비슷하면 꽉 채우고 세로 사진 등은 잘리지 않게 · cover=항상 꽉 채움(잘림) · contain=항상 전체 보임")
    ap.add_argument("--photo-dim", type=float, default=0.5, help="사진을 어둡게 하는 정도 (0=원본, 1=검정)")
    ap.add_argument("--posters", nargs="+", default=[], help="팀 포스터 폴더 또는 이미지 파일들 (이름순 배치)")
    ap.add_argument("--poster-layouts", type=int, nargs="+", default=[16, 8, 4],
                    help="묶음 화면 배치 순서 (기본 16 8 4 를 번갈아). 4 만 주면 4장씩 고정")
    ap.add_argument("--poster-span", default="tags", choices=["tags", "full"],
                    help="tags(기본)=2절~2번째 후렴만 · full=첫 가사부터 마지막 후렴 전까지 곡 전체")
    ap.add_argument("--poster-per-screen", type=int, default=0, help="(예전 옵션) 이 값을 주면 이 장수로 고정")
    ap.add_argument("--poster-grid", type=float, nargs=2, metavar=("시작", "끝"), help="묶음 화면 구간(초)")
    ap.add_argument("--poster-mosaic", type=float, nargs="+", metavar="초", help="모자이크 시작(초) [끝]")
    ap.add_argument("--poster-bg", type=int, nargs=3, default=[16, 16, 22], help="포스터 장면 바탕색")
    ap.add_argument("--intro-text", default="",
                    help="시작 인사말. 줄은 | 로 나눔 (첫 줄은 크게). 예: '2026 축전|모두 고생했습니다'")
    ap.add_argument("--intro-sign", default="", help="인사말 아래 서명 (작게)")
    ap.add_argument("--intro-sec", type=float, default=5.0, help="인사말을 보여 줄 시간(초)")
    ap.add_argument("--nvenc", action="store_true", help="NVIDIA GPU 인코딩 (지원 안 되면 자동으로 CPU)")
    render(ap.parse_args())


if __name__ == "__main__":
    main()
