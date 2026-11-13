# festival-lyrics-video

노래(mp3)와 가사(txt)로 **가사가 아래에서 위로 흐르는 영상**을 만들고, 사진·영상·팀 포스터를 함께 넣어
행사 영상(예: 2026 충남대학교 SW·AI 창의축전)을 만드는 도구입니다.

## 결과 영상

2026 충남대학교 SW·AI 창의축전 영상 (가사 · 사진 · 팀 포스터 · 시작 인사말)

[![2026 충남대학교 SW·AI 창의축전 영상](https://img.youtube.com/vi/4t8PDYUJnHI/hqdefault.jpg)](https://youtu.be/4t8PDYUJnHI)

▶ https://youtu.be/4t8PDYUJnHI

## 구성

| 파일 | 하는 일 |
|---|---|
| `lyrics_video.py` | mp3 + 가사 → mp4. 가사 자동 정렬, 사진·영상 배경, 포스터 화면, 시작 인사말 |
| `pdf_posters.py` | 포스터 PDF 폴더 → 번호 순서대로 정리된 jpg 폴더 |
| `examples/hello_tomorrow.txt` | Suno 형식 가사 예시 (태그·듀엣 표시 포함) |
| `examples/make_video.sh` | 포스터 변환부터 영상까지 한 번에 돌리는 예시 |

## 설치

```bash
pip install -r requirements.txt
# ffmpeg (영상 인코딩)
sudo apt install -y ffmpeg          # 또는 conda install -c conda-forge ffmpeg
# 한글 폰트 (없을 때)
sudo apt install -y fonts-noto-cjk  # 또는 --font 로 .ttf 경로 지정
```

가사 자동 정렬에는 [stable-ts](https://github.com/jianfch/stable-ts)(Whisper)를 씁니다.
large-v3 모델은 CPU에서 메모리를 10GB 안팎 쓰므로, 노트북에서는 `--model small` 을 쓰거나
GPU 서버에서 정렬한 타이밍 파일(`<곡>.times.json`)을 가져와 `--times` 로 주세요.

## 1. 포스터 PDF → jpg

```bash
python pdf_posters.py poster_pdfs/ -o posters
```

- `…__AI-1__팀이름.pdf` 형식의 이름에서 분야·번호를 읽어 **AI-1, AI-2, …, AI-10** 순서로 정렬합니다
  (문자열 순서 AI-1, AI-10, AI-2 가 아님). 분야가 여러 개면(AI, SW …) 분야별로 묶습니다.
- 페이지 크기가 제각각이어도 같은 높이(기본 1800px)의 jpg로 저장합니다.
- `posters/posters_index.csv` 에 순서·분야·번호·팀 이름·원본 파일을 남깁니다.
- 이름 형식이 다른 PDF는 경고 후 맨 뒤에, 여러 쪽 PDF는 첫 쪽만 씁니다.

## 2. 영상 만들기

가장 단순한 형태 (검은 배경 + 가사):

```bash
python lyrics_video.py song.mp3 song.txt --device cuda
```

행사 영상 예시:

```bash
python lyrics_video.py hello.mp3 examples/hello_tomorrow.txt \
  --photos photos/*.jpg media/*.mp4 \
  --posters posters/ --poster-span full \
  --intro-text "2026 충남대학교 SW·AI 창의축전|참가한 학생 모두 고생했습니다.|축하합니다." \
  --intro-sign "컴퓨터인공지능학부 교수 일동 드림" \
  --device cuda
```

### 가사

- 빈 줄 = 덩어리 경계. `[Verse 1]`, `[Chorus]` 같은 Suno 태그와 줄 앞 `(Male)`·`(Female)`·`(Duet)` 표시는
  자동으로 빠지니 Suno에 넣은 가사를 그대로 쓰면 됩니다.
- 처음 실행하면 줄별 시각을 `<곡>.times.json` 에 저장합니다. 어긋난 줄은 `start` 를 고친 뒤
  `--times <곡>.times.json` 으로 다시 돌리면 정렬 없이 바로 렌더링합니다.

### 사진·영상 배경 (`--photos`, 같은 뜻 `--media`)

- jpg/png와 mp4/mov 등을 섞어 순서대로 줍니다. 영상은 자기 길이만큼(최대 `--clip-max` 15초) 재생되고
  소리는 쓰지 않습니다. 사진은 남는 시간을 나눠 가지며 천천히 확대·이동합니다.
- `--photo-fit auto`(기본): 가로 사진·영상은 화면을 채우고, 세로·정사각형은 자르지 않고 양옆을 흐리게 채웁니다.

### 포스터 (`--posters`)

- 16장 → 8장 → 4장 화면을 번갈아 보여 주고(`--poster-layouts`), 마지막 후렴부터는 전체 모자이크에서
  한 장으로부터 천천히 뒤로 빠지며 끝납니다. 모든 팀이 최소 한 번 나옵니다.
- 구간은 가사 태그로 잡습니다: `[Verse 2]`~`[Bridge]` 직전 = 묶음 화면, `[Final Chorus]`~끝 = 모자이크.
  `--poster-span full` 이면 첫 가사부터 곡 전체를 포스터로 채웁니다(포스터가 많을 때 권장).
  직접 정하려면 `--poster-grid 60 105 --poster-mosaic 150`.

### 시작 인사말

`--intro-text` 의 줄은 `|` 로 나누고(첫 줄은 크게), `--intro-sign` 은 아래에 작게 들어갑니다.
기본 5초(`--intro-sec`) 동안 보이고, 그동안 가사는 숨깁니다.

### 그 밖의 옵션

`--width 1080 --height 1920`(세로 영상), `--font-scale`(글자 크기), `--dim`(흐린 줄 밝기),
`--photo-dim`(배경 어둡기), `--nvenc`(NVIDIA 인코딩. B200·H100 같은 데이터센터 GPU에는 인코더가 없어
자동으로 CPU 인코딩으로 넘어갑니다). 전체 옵션은 `python lyrics_video.py -h`.

## 개인정보

포스터·사진·노래와 학생 이름이 들어간 가사 등은 저장소에 올리지 마세요. `.gitignore` 가 mp3·mp4·pdf·
`posters/`·`photos/`·`media/` 를 제외합니다. 학생 얼굴이나 이름이 나오는 영상을 외부에 공개할 때는
미리 동의를 받아 두세요.

## License

MIT
