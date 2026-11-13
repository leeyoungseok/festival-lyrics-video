#!/usr/bin/env bash
# 축전 영상 한 번에 만들기 예시 — 파일 이름만 바꿔 쓰세요
set -e
SONG=hello.mp3                 # Suno 에서 받은 노래
LYRICS=examples/hello_tomorrow.txt
PDFS=poster_pdfs/              # 팀 포스터 PDF 폴더

# 1) 포스터 PDF → 번호 붙은 jpg (posters/)
python pdf_posters.py "$PDFS" -o posters

# 2) 영상 만들기 (서버는 --device cuda, 노트북은 --model small 또는 --times 사용)
python lyrics_video.py "$SONG" "$LYRICS" \
  --photos photos/*.jpg media/*.mp4 \
  --posters posters/ --poster-span full \
  --intro-text "2026 충남대학교 SW·AI 창의축전|참가한 학생 모두 고생했습니다.|축하합니다.|앞으로 더 멋진 미래를 기대합니다." \
  --intro-sign "컴퓨터인공지능학부 교수 일동 드림" \
  --device cuda
