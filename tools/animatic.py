"""가편집본(애니매틱) 만들기: 촬영 영상·음성 없이 화면 텍스트와 타이밍을 미리 본다.

python tools/animatic.py products/heatmat/config.json products/heatmat/out

- 장면 자리에는 config의 storyboard 설명이 들어간 자리표시 패널을 그린다.
- 자막 타이밍은 음성 속도 추정치(초당 음절 수)로 잡는다. 실제 Kanna 음성을 만들면 whisper 타이밍으로 다시 맞춘다.
- 폰트는 KOTRA BOLD 파일이 없으면 대체 폰트를 쓴다(config 옆 경로나 FONT 환경변수로 지정 가능).
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
SYL_PER_SEC = 7.2  # Kanna 1.19배속 + post_tempo 1.06 추정치
FALLBACK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def syllables(s):
    return len(re.findall(r"[가-힣]", s)) + 0.5 * len(re.findall(r"[A-Za-z0-9]", s))


def wrap(text, maxc):
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) > maxc and cur:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def split_even(text, parts):
    """단어 경계에서 글자 수가 고르게 parts 조각으로 나눈다."""
    words = text.split()
    if parts <= 1 or len(words) <= 1:
        return [text]
    target, out, cur = len(text) / parts, [], ""
    for i, w in enumerate(words):
        cand = (cur + " " + w).strip()
        left = len(words) - i
        if cur and len(out) < parts - 1 and (len(cand) > target * (len(out) + 1) - len(" ".join(out)) or left < parts - len(out)):
            out.append(cur)
            cur = w
        else:
            cur = cand
    out.append(cur)
    return out


def balanced_chunks(text, maxc, max_lines):
    """한 문장 조각을 자막 청크(각 1~max_lines줄, 줄당 maxc자 이내)로 고르게 나눈다."""
    k = -(-len(text) // (maxc * max_lines))
    while True:
        chunks = []
        for part in split_even(text, k):
            n = -(-len(part) // maxc)
            lines = split_even(part, n)
            if any(len(l) > maxc for l in lines):
                lines = wrap(part, maxc)
            chunks.append(lines)
        if all(len(c) <= max_lines for c in chunks) or k > 6:
            return chunks
        k += 1


def main(cfg_path, out_dir):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    st = json.load(open(os.path.join(ROOT, cfg.get("style", "templates/channel_defaults.json")), encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    font_path = os.environ.get("FONT") or (cfg.get("font_file") if cfg.get("font_file") and os.path.exists(cfg["font_file"]) else FALLBACK_FONT)
    F = lambda s: ImageFont.truetype(font_path, s)
    WHITE, ACC = hexrgb(st["colors"]["main"]), hexrgb(st["colors"]["accent"])
    OUT = hexrgb(st["colors"]["outline"])
    cap, wm, ad, top, bot = st["captions"], st["watermark"], st["ad_label"], st["top_text"], st["bottom_text"]

    # 1) 문장 조각 → 자막 청크 + 추정 시간
    phrases = [p.strip() for p in re.findall(r"[^,.!?~]+[,.!?~]?", cfg["script"]) if p.strip()]
    disp_map = cfg.get("caption_display", {})
    chunks, t = [], 0.0
    for ph in phrases:
        dur = max(0.6, syllables(ph) / SYL_PER_SEC + (0.12 if ph[-1] in ",.!?~" else 0))
        disp = ph
        for k, v in disp_map.items():
            disp = disp.replace(k, v)
        disp = re.sub(r"[,.~]$", "", disp)
        groups = balanced_chunks(disp, cap["chars_per_line_max"], cap["lines_max"])
        total_c = sum(len("".join(g)) for g in groups)
        for gi, g in enumerate(groups):
            d = dur * len("".join(g)) / total_c
            chunks.append({"start": t, "dur": d, "lines": g, "spoken": ph, "first": gi == 0})
            t += d

    def pick(entries, c, key):
        disp = " ".join(c["lines"])
        for e in entries:
            if c["first"] and c["spoken"].startswith(e["cut_at"]) or disp.startswith(e["cut_at"]):
                return e[key]
        return None

    cur_bot, cur_shot = "", ""
    for c in chunks:
        cur_bot = pick(cfg.get("bottom_texts", []), c, "text") or cur_bot
        cur_shot = pick(cfg.get("storyboard", []), c, "shot") or cur_shot
        c["bottom"], c["shot"] = cur_bot, cur_shot

    def base(shot):
        img = Image.new("RGB", (W, H), (58, 64, 74))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, H], fill=(58, 64, 74))
        d.rounded_rectangle([90, 520, 990, 1180], 28, fill=(96, 106, 122), outline=(150, 160, 175), width=4)
        d.text((540, 600), "촬영 컷 자리", font=F(40), fill=(200, 205, 215), anchor="mm")
        for i, ln in enumerate(wrap(shot, 14)):
            d.text((540, 800 + i * 70), ln, font=F(56), fill=(240, 240, 245), anchor="mm")
        return img

    def draw_text(img, xy, s, size, color, anchor="mm", stroke=6, alpha=255):
        layer = Image.new("RGBA", (W, H))
        ImageDraw.Draw(layer).text(xy, s, font=F(size), fill=color + (alpha,), anchor=anchor,
                                   stroke_width=stroke, stroke_fill=OUT + (alpha,))
        img.paste(layer, (0, 0), layer)

    def overlays(img):
        a = int(255 * wm["opacity"])
        draw_text(img, (wm["right_edge_px"], wm["center_y_px"]), wm["text"], wm["px"], WHITE, "rm", 0, a)
        draw_text(img, (ad["left_edge_px"], ad["center_y_px"]), ad["text"], ad["px"], WHITE, "lm", 0, int(255 * ad["opacity"]))

    def caption_line(img, line, cy):
        size, kws = cap["approx_px"], cfg.get("caption_keywords", [])
        spans, i = [], 0
        while i < len(line):
            hit = next((k for k in kws if line.startswith(k, i)), None)
            if hit:
                spans.append((hit, ACC)); i += len(hit)
            else:
                if spans and spans[-1][1] == WHITE:
                    spans[-1] = (spans[-1][0] + line[i], WHITE)
                else:
                    spans.append((line[i], WHITE))
                i += 1
        dd = ImageDraw.Draw(img)
        x = W / 2 - sum(dd.textlength(s, font=F(size)) for s, _ in spans) / 2
        for s, col in spans:
            draw_text(img, (x, cy), s, size, col, "lm", 5)
            x += dd.textlength(s, font=F(size))

    frames = []
    # 0) 썸네일 첫 프레임
    th = cfg["thumb"]
    img = base(cfg.get("thumb_shot", chunks[0]["shot"]))
    draw_text(img, (540, 470), th["line1"], 120, hexrgb(th.get("line1_color", "#FFFFFF")), stroke=8)
    draw_text(img, (540, 610), th["line2"], 120, hexrgb(th.get("line2_color", "#F4C70F")), stroke=8)
    overlays(img)
    img.save(os.path.join(out_dir, "thumbnail_1080x1920.jpg"), quality=92)
    p = os.path.join(out_dir, "f000.png"); img.save(p); frames.append((p, 1 / FPS))

    # 1) 자막 청크마다 한 장
    tl = cfg.get("top_text", [])
    for n, c in enumerate(chunks, 1):
        img = base(c["shot"])
        for i, ln in enumerate(tl):
            draw_text(img, (540, top["center_px"][1] - 56 + i * 112), ln, top["px"], WHITE, stroke=7)
        cy = cap["center_px"][1]
        offs = [0] if len(c["lines"]) == 1 else [-42, 42]
        for ln, o in zip(c["lines"], offs):
            caption_line(img, ln, cy + o)
        if c["bottom"]:
            draw_text(img, (540, bot["center_px"][1]), c["bottom"], bot["px"], ACC, stroke=6)
        overlays(img)
        p = os.path.join(out_dir, f"f{n:03d}.png"); img.save(p); frames.append((p, c["dur"]))

    # 2) concat → mp4 (무음 트랙 포함)
    lst = os.path.join(out_dir, "frames.txt")
    with open(lst, "w") as f:
        for p, d in frames:
            f.write(f"file '{os.path.abspath(p)}'\nduration {d:.3f}\n")
        f.write(f"file '{os.path.abspath(frames[-1][0])}'\n")
    total = sum(d for _, d in frames)
    mp4 = os.path.join(out_dir, "animatic.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{total:.3f}",
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-crf", "20",
                    "-c:a", "aac", "-shortest", mp4], check=True)

    # 3) 자막 SRT (추정 타이밍)
    def ts(x):
        ms = int(round(x * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    off = 1 / FPS
    with open(os.path.join(out_dir, "captions_estimated.srt"), "w", encoding="utf-8") as f:
        for n, c in enumerate(chunks, 1):
            f.write(f"{n}\n{ts(c['start'] + off)} --> {ts(c['start'] + c['dur'] + off)}\n" + "\n".join(c["lines"]) + "\n\n")
    for p, _ in frames:
        os.remove(p)
    os.remove(lst)
    print(f"{mp4}  {total:.2f}s  chunks={len(chunks)}  font={font_path}")
    for c in chunks:
        print(f"  {c['start']:5.2f}+{c['dur']:.2f}  {' / '.join(c['lines'])}  | 하단:{c['bottom']}  | 컷:{c['shot']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
