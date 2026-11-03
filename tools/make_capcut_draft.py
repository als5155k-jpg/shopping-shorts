"""요거어때 쇼츠를 CapCut 프로젝트(초안)로 만든다. **CapCut이 설치된 PC에서 실행한다.**

    python tools/make_capcut_draft.py products/heatmat/config.json
    python tools/make_capcut_draft.py products/heatmat/config.json --drafts "D:/CapCut/Projects/com.lveditor.draft"

필요: pip install pycapcut pillow

만들어지는 것 (트랙 위에서부터)
- ad_label    : [광고] 좌상단 (전체 구간)
- watermark   : YOGEOTTAE 우상단, 불투명도 68% (전체 구간)
- thumb_line1/2 : 썸네일 제목 2줄 (맨 앞 1프레임)
- top_text    : 상단 흰색 후킹 문구 (1프레임 뒤 ~ 끝)
- bottom_text : 하단 노란 장점 문구 (대사 구간마다)
- captions    : 음성 자막, CapCut 크기 15, 강조 단어 #F4C70F
- scenes      : 장면 자리표시 이미지 (촬영 컷 번호가 적힌 회색 화면)

장면 자리표시는 CapCut에서 클립을 우클릭 → "교체(Replace)"로 실제 영상에 바꾼다.
자막 타이밍은 tools/animatic.py와 같은 추정치다. 실제 음성을 넣으면 자막을 음성에 맞춰 다시 만든다.
"""
import argparse
import copy
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from animatic import FPS, H, W, hexrgb, load_config, plan_chunks, wrap  # noqa: E402

try:
    import pycapcut as cc
    from pycapcut.metadata.effect_meta import EffectMeta
except ImportError:
    sys.exit("pycapcut가 없습니다: pip install pycapcut")

US = 1_000_000
FRAME_US = round(US / FPS)


def us(sec):
    return int(round(sec * US))


def rgb01(hex_color):
    return tuple(c / 255 for c in hexrgb(hex_color))


def default_drafts_dir():
    local = os.environ.get("LOCALAPPDATA", "")
    return os.path.join(local, "CapCut", "User Data", "Projects", "com.lveditor.draft")


def pick_font_file(cfg):
    for p in [os.environ.get("FONT"), cfg.get("font_file"),
              "C:/Windows/Fonts/malgunbd.ttf", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]:
        if p and os.path.exists(p):
            return p
    return None


class HighlightText(cc.TextSegment):
    """한 텍스트 안에서 특정 단어만 다른 색으로 칠한다(CapCut 텍스트 styles를 구간별로 나눔)."""

    def __init__(self, *args, keywords=(), hl_color=(1, 1, 1), **kwargs):
        super().__init__(*args, **kwargs)
        self.keywords = [k for k in keywords if k]
        self.hl_color = list(hl_color)

    def export_material(self):
        ret = super().export_material()
        content = json.loads(ret["content"])
        base = content["styles"][0]
        text, marks, i = self.text, [False] * len(self.text), 0
        while i < len(text):
            hit = next((k for k in self.keywords if text.startswith(k, i)), None)
            if hit:
                for j in range(i, i + len(hit)):
                    marks[j] = True
                i += len(hit)
            else:
                i += 1
        styles, s = [], 0
        for e in range(1, len(text) + 1):
            if e == len(text) or marks[e] != marks[s]:
                st = copy.deepcopy(base)
                st["range"] = [s, e]
                if marks[s]:
                    st["fill"]["content"]["solid"]["color"] = self.hl_color
                styles.append(st)
                s = e
        content["styles"] = styles
        ret["content"] = json.dumps(content, ensure_ascii=False)
        return ret


def make_placeholders(chunks, cfg, out_dir, font_file):
    os.makedirs(out_dir, exist_ok=True)
    F = (lambda s: ImageFont.truetype(font_file, s)) if font_file else (lambda s: ImageFont.load_default())
    shots = []
    for name in [cfg.get("thumb_shot") or chunks[0]["shot"]] + [c["shot"] for c in chunks]:
        if name not in shots:
            shots.append(name)
    paths = {}
    for n, shot in enumerate(shots, 1):
        img = Image.new("RGB", (W, H), (58, 64, 74))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([90, 520, 990, 1180], 28, fill=(96, 106, 122), outline=(150, 160, 175), width=4)
        d.text((540, 600), "촬영 컷 자리 — CapCut에서 교체", font=F(40), fill=(200, 205, 215), anchor="mm")
        for i, ln in enumerate(wrap(shot, 14)):
            d.text((540, 800 + i * 70), ln, font=F(56), fill=(240, 240, 245), anchor="mm")
        p = os.path.join(out_dir, f"shot{n:02d}.png")
        img.save(p)
        paths[shot] = p
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--drafts", default=None, help="CapCut 프로젝트 폴더(기본: %%LOCALAPPDATA%%/CapCut/User Data/Projects/com.lveditor.draft)")
    ap.add_argument("--name", default=None, help="CapCut 프로젝트 이름(기본: config의 name)")
    ap.add_argument("--replace", action="store_true", help="같은 이름 프로젝트를 덮어쓴다(CapCut에서 닫혀 있어야 함)")
    a = ap.parse_args()

    cfg, st = load_config(a.config)
    name = a.name or cfg["name"]
    drafts = a.drafts or cfg.get("capcut_drafts_dir") or default_drafts_dir()
    workdir = cfg["workdir"]
    for label, path in [("프로젝트 이름", name), ("workdir", workdir)]:
        if not path.isascii() or " " in path:
            sys.exit(f"{label}에는 영문·숫자만 쓰세요(공백·한글 금지): {path}")
    if not os.path.isdir(drafts):
        sys.exit(f"CapCut 프로젝트 폴더를 찾지 못했습니다: {drafts}\n--drafts 로 경로를 지정하세요.")

    chunks = plan_chunks(cfg, st)
    t0 = FRAME_US  # 맨 앞 1프레임은 썸네일
    end = t0 + us(chunks[-1]["start"] + chunks[-1]["dur"])
    ph = make_placeholders(chunks, cfg, os.path.join(workdir, "placeholders"), pick_font_file(cfg))

    script = cc.DraftFolder(drafts).create_draft(name, W, H, FPS, allow_replace=a.replace)
    # 아래에서 위로 쌓인다(relative_index 클수록 앞)
    script.add_track(cc.TrackType.video, "scenes")
    for idx, tname in enumerate(["captions", "bottom_text", "top_text", "thumb_line1", "thumb_line2", "watermark", "ad_label"]):
        script.add_track(cc.TrackType.text, tname, relative_index=idx + 1)

    font_id = st["font"].get("capcut_resource_id") or ""
    font_meta = EffectMeta(st["font"]["name"], False, font_id, font_id, "") if font_id else None
    WHITE, ACC, OUT = rgb01(st["colors"]["main"]), rgb01(st["colors"]["accent"]), rgb01(st["colors"]["outline"])

    def text(track, s, start, dur, size, color, x, y, *, align=1, alpha=1.0, border=True, shadow=False,
             keywords=()):
        seg = HighlightText(
            s, cc.Timerange(start, dur), keywords=keywords, hl_color=ACC,
            style=cc.TextStyle(size=size, color=color, alpha=alpha, align=align, line_spacing=2),
            clip_settings=cc.ClipSettings(transform_x=x, transform_y=y),
            border=cc.TextBorder(color=OUT, width=40.0) if border else None,
            shadow=cc.TextShadow(alpha=0.8, color=(0, 0, 0), diffuse=15.0, distance=5.0) if shadow else None)
        if font_meta:
            seg.font = font_meta
        script.add_segment(seg, track)

    # 장면: 같은 컷이 이어지는 청크는 한 클립으로 합친다
    def photo(path, start, dur):
        script.add_segment(cc.VideoSegment(cc.VideoMaterial(path), cc.Timerange(start, dur)), "scenes")

    thumb_shot = cfg.get("thumb_shot") or chunks[0]["shot"]
    photo(ph[thumb_shot], 0, FRAME_US)
    runs = []
    for c in chunks:
        s, e = t0 + us(c["start"]), t0 + us(c["start"] + c["dur"])
        if runs and runs[-1][0] == c["shot"]:
            runs[-1][2] = e
        else:
            runs.append([c["shot"], s, e])
    for shot, s, e in runs:
        photo(ph[shot], s, e - s)

    # 썸네일 제목(1프레임)
    th, tcfg = cfg["thumb"], st["thumbnail"]
    text("thumb_line1", th["line1"], 0, FRAME_US, tcfg["capcut_size"], rgb01(th.get("line1_color", "#FFFFFF")),
         0.0, tcfg["line1_capcut_y"], shadow=True)
    text("thumb_line2", th["line2"], 0, FRAME_US, tcfg["capcut_size"], rgb01(th.get("line2_color", "#F4C70F")),
         0.0, tcfg["line2_capcut_y"], shadow=True)

    # 상단 후킹(고정)
    top = st["top_text"]
    if cfg.get("top_text"):
        text("top_text", "\n".join(cfg["top_text"]), t0, end - t0, top["capcut_size"], WHITE,
             top["capcut_x"], top["capcut_y"], shadow=True)

    # 자막
    cap = st["captions"]
    for c in chunks:
        s, e = t0 + us(c["start"]), t0 + us(c["start"] + c["dur"])
        text("captions", "\n".join(c["lines"]), s, e - s, cap["capcut_size"], WHITE,
             cap["capcut_x"], cap["capcut_y"], keywords=cfg.get("caption_keywords", []))

    # 하단 장점 문구: 같은 문구가 이어지는 구간을 합친다
    bot, bruns = st["bottom_text"], []
    for c in chunks:
        s, e = t0 + us(c["start"]), t0 + us(c["start"] + c["dur"])
        if not c["bottom"]:
            continue
        if bruns and bruns[-1][0] == c["bottom"] and bruns[-1][2] == s:
            bruns[-1][2] = e
        else:
            bruns.append([c["bottom"], s, e])
    for s_text, s, e in bruns:
        text("bottom_text", s_text, s, e - s, bot["capcut_size"], ACC, bot["capcut_x"], bot["capcut_y"])

    # 워터마크·광고 표시(처음~끝)
    wm, ad = st["watermark"], st["ad_label"]
    text("watermark", wm["text"], 0, end, wm["capcut_size"], WHITE, wm["capcut_x"], wm["capcut_y"],
         align=2, alpha=wm["opacity"], border=False)
    text("ad_label", ad["text"], 0, end, ad["capcut_size"], WHITE, ad["capcut_x"], ad["capcut_y"],
         align=0, alpha=ad["opacity"], border=False)

    script.save()
    print(f"CapCut 프로젝트 생성: {os.path.join(drafts, name)}")
    print(f"길이 {end / US:.2f}s, 장면 {len(runs) + 1}개, 자막 {len(chunks)}개, 하단 문구 {len(bruns)}개")
    print("폰트: " + (f"{st['font']['name']} ({font_id})" if font_id else
                     "CapCut 기본 폰트 (channel_defaults.json의 font.capcut_resource_id를 채우면 코트라 볼드로 지정됨)"))
    print("장면 교체 순서:")
    print(f"  0.00s  (썸네일 1프레임) {thumb_shot}")
    for shot, s, e in runs:
        print(f"  {s / US:5.2f}s ~ {e / US:5.2f}s  {shot}")


if __name__ == "__main__":
    main()
