#!/usr/bin/env python3
"""
pdf_posters.py — 축전 포스터 PDF 폴더를 lyrics_video.py 용 jpg 폴더로 바꿉니다.

  python pdf_posters.py pdf폴더/                 # → posters/001_AI-1_이목구비즈.jpg …
  python pdf_posters.py pdf폴더/ -o posters --height 1800

  · 파일 이름의 분야·번호(예: 1794565574355__AI-1__이목구비즈.pdf)를 읽어
    AI-1, AI-2, … AI-10 처럼 번호 순서대로 정렬합니다 (문자열 순서인 AI-1, AI-10, AI-2 가 아님).
    분야가 여러 개면(AI, SW …) 분야별로 묶어 처음 나온 분야부터 차례로 둡니다.
  · PDF 마다 페이지 크기가 제각각이어도 같은 높이(기본 1800px)로 맞춰 jpg 로 저장합니다.
  · 여러 쪽짜리 PDF 는 첫 쪽만 씁니다 (경고 출력).
  · posters_index.csv 에 순서·분야·번호·팀 이름·원본 파일을 남깁니다.
  · 이미 변환된 파일은 PDF 보다 새로우면 건너뜁니다 (--force 로 다시).

필요: pip install pymupdf
"""
import argparse, csv, re, sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        sys.exit("pymupdf 가 필요합니다: pip install pymupdf")
try:
    fitz.TOOLS.mupdf_display_errors(False)     # 일부 PDF 의 사소한 문법 경고 숨김 (변환에는 영향 없음)
except Exception:
    pass

NAME_RE = re.compile(r"__([A-Za-z]+)-(\d+)__(.+)$")


def parse(p: Path):
    m = NAME_RE.search(p.stem)
    if m:
        return m.group(1).upper(), int(m.group(2)), m.group(3).replace("_", " ").strip()
    return "ETC", 10**6, p.stem                                # 형식이 다르면 맨 뒤에 이름순


def safe(s, n=40):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")
    return s[:n] or "poster"


def main():
    ap = argparse.ArgumentParser(description="포스터 PDF → 번호 붙은 jpg")
    ap.add_argument("src", nargs="+", help="PDF 폴더 또는 PDF 파일들")
    ap.add_argument("-o", "--out", default="posters")
    ap.add_argument("--height", type=int, default=1800, help="저장할 jpg 높이(px)")
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    pdfs = []
    for s in a.src:
        p = Path(s)
        pdfs += sorted(p.glob("*.pdf")) + sorted(p.glob("*.PDF")) if p.is_dir() else [p]
    if not pdfs:
        sys.exit("PDF 를 찾지 못했습니다.")
    items = [(parse(p), p) for p in pdfs]
    cats = []
    for (c, _, _), _ in items:
        if c not in cats and c != "ETC":
            cats.append(c)
    cats.append("ETC")
    etc = [p.name for (c, _, _), p in items if c == "ETC"]
    if etc:
        print(f"  ⚠ 이름이 '…__분야-번호__팀이름.pdf' 형식이 아닌 {len(etc)}개는 맨 뒤에 둡니다: "
              + ", ".join(etc[:5]) + (" …" if len(etc) > 5 else ""))
    items.sort(key=lambda x: (cats.index(x[0][0]), x[0][1], x[1].name))

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows, done, skip = [], 0, 0
    for i, ((cat, num, team), p) in enumerate(items, 1):
        name = f"{i:03d}_{cat}-{num if num < 10**6 else 'X'}_{safe(team)}.jpg"
        dst = out / name
        rows.append(dict(order=i, category=cat, number=num if num < 10**6 else "", team=team,
                         jpg=name, pdf=p.name))
        if dst.exists() and not a.force and dst.stat().st_mtime >= p.stat().st_mtime:
            skip += 1; continue
        try:
            doc = fitz.open(p)
            if doc.page_count > 1:
                print(f"  ⚠ {p.name}: {doc.page_count}쪽 — 첫 쪽만 사용")
            page = doc[0]
            z = a.height / page.rect.height
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
            pix.save(str(dst), jpg_quality=a.quality)
            done += 1
            lab = f"{cat}-{num}" if num < 10**6 else "기타"
            print(f"  {i:3d}. {lab:8s} {team[:30]:30s} {pix.width}x{pix.height}")
        except Exception as e:
            print(f"  ✗ {p.name}: {e}")
    with open(out / "posters_index.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n 완료: {len(rows)}개 (변환 {done}, 건너뜀 {skip}) → {out}/   순서표: {out}/posters_index.csv")
    print(f" 다음: python lyrics_video.py song.mp3 song.txt --posters {out}/")


if __name__ == "__main__":
    main()
