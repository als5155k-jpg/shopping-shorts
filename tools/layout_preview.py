"""YOGEOTTAE 쇼츠 레이아웃 미리보기 (1080x1920). KOTRA BOLD 대신 대체 폰트로 그린 근사치."""
import sys
from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1] if len(sys.argv) > 1 else "docs/layout_preview.jpg"
W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
WHITE, YELLOW = (255, 255, 255), (0xF4, 0xC7, 0x0F)

img = Image.new("RGB", (W, H), (70, 78, 90))
d = ImageDraw.Draw(img, "RGBA")
f = lambda s: ImageFont.truetype(FONT, s)

# 제품 영역(가상)
d.rectangle([90, 560, 990, 1150], fill=(120, 130, 145))
d.text((W // 2, 855), "제품 사용 장면", font=f(48), fill=(225, 225, 230), anchor="mm")

# 유튜브 쇼츠 UI가 덮는 구역(근사치)
for box, label in [((0, 0, W, 140), "쇼츠 상단 UI"),
                   ((930, 1040, W, 1720), "버튼"),
                   ((0, 1560, 930, H), "채널명·제목·제품태그 (쇼츠 하단 UI)")]:
    d.rectangle(box, fill=(220, 40, 40, 70), outline=(255, 80, 80, 200), width=3)
    d.text((box[0] + 16, box[1] + 12), label, font=f(30), fill=(255, 200, 200))

def text(xy, s, size, color, anchor="mm", stroke=6, alpha=255):
    layer = Image.new("RGBA", (W, H))
    ImageDraw.Draw(layer).text(xy, s, font=f(size), fill=color + (alpha,), anchor=anchor,
                               stroke_width=stroke, stroke_fill=(20, 20, 20, alpha))
    img.paste(layer, (0, 0), layer)

# 워터마크 우상단, 불투명도 68%
text((990, 195), "YOGEOTTAE", 36, WHITE, anchor="rm", stroke=0, alpha=int(255 * 0.68))
# [광고] 좌상단
text((90, 195), "[광고]", 34, WHITE, anchor="lm", stroke=0, alpha=int(255 * 0.68))
# 상단 후킹 (흰색, 2줄)
text((540, 300), "전기장판을", 96, WHITE)
text((540, 412), "접어서 들고 다녀요", 96, WHITE)
# 음성 자막 (CapCut 15 ≈ 68px 추정, 흰색 + 강조 노랑)
cap_y = 1295
parts = [("전용 ", WHITE), ("파우치", YELLOW), ("에 넣어 다녀요", WHITE)]
total = sum(d.textlength(p, font=f(68)) for p, _ in parts)
x = 540 - total / 2
for p, c in parts:
    text((x, cap_y), p, 68, c, anchor="lm", stroke=5)
    x += d.textlength(p, font=f(68))
# 하단 강조 (노랑)
text((540, 1450), "접으면 가방 한 칸", 76, YELLOW, stroke=6)

# 안내 눈금
for y, lbl in [(195, "워터마크 y195"), (356, "상단 문구 중심 y356"), (1295, "자막 y1295"), (1450, "하단 문구 y1450")]:
    d.line([(0, y), (40, y)], fill=(255, 255, 0, 180), width=3)
img.save(out, quality=90)
print("saved", out)
