"""
demo/make_demo_media.py — Draw the three made-up images used as demo
"visual resources". Everything here is invented and labeled as a
fictional illustration. Run once; writes PNGs into demo/media/.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "media"
OUT.mkdir(exist_ok=True)
FONTS = Path("C:/Windows/Fonts")


def font(name, size, fallback="arial.ttf"):
    for n in (name, fallback):
        try:
            return ImageFont.truetype(str(FONTS / n), size)
        except OSError:
            continue
    return ImageFont.load_default()


HAND = lambda s: font("segoepr.ttf", s)  # Segoe Print: marker-on-whiteboard look
HANDB = lambda s: font("segoeprb.ttf", s, "segoepr.ttf")
SANS = lambda s: font("segoeui.ttf", s)
SANSB = lambda s: font("segoeuib.ttf", s)


def label(d, w, h):
    d.rectangle((w - 430, h - 44, w - 12, h - 12), fill=(255, 255, 255))
    d.text((w - 420, h - 40), "Illustration · fictional demo data", fill=(110, 110, 110), font=SANS(20))


def arrow(d, a, b, color, width=6, head=22):
    d.line((a, b), fill=color, width=width)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for s in (-0.45, 0.45):
        d.line((b, (b[0] - head * math.cos(ang + s), b[1] - head * math.sin(ang + s))), fill=color, width=width)


# 1. Whiteboard: the reporting chain (CPT Okafor's interview).
w, h = 1600, 1000
im = Image.new("RGB", (w, h), (246, 247, 244))
d = ImageDraw.Draw(im)
d.rectangle((0, 0, w - 1, h - 1), outline=(160, 165, 170), width=18)
blue, red, black, green = (35, 80, 170), (200, 40, 40), (40, 40, 45), (30, 120, 70)
d.text((70, 50), "Where the grid's \"how\" gets lost", fill=black, font=HANDB(54))
boxes = [((90, 290, 430, 490), "Scout section", "sends grid"),
         ((620, 290, 960, 490), "Troop CP", "knows: ground\ntruth or box?"),
         ((1150, 290, 1490, 490), "Squadron", "sees: icons only")]
for (x0, y0, x1, y1), title, sub in boxes:
    d.rounded_rectangle((x0, y0, x1, y1), radius=26, outline=blue, width=6)
    d.text((x0 + 30, y0 + 22), title, fill=blue, font=HANDB(40))
    d.multiline_text((x0 + 30, y0 + 82), sub, fill=black, font=HAND(30), spacing=6)
arrow(d, (440, 385), (608, 385), black)
arrow(d, (970, 385), (1138, 385), black)
d.line((1000, 250, 1110, 520), fill=red, width=8)
d.line((1110, 250, 1000, 520), fill=red, width=8)
d.text((930, 540), "context dies here", fill=red, font=HANDB(40))
d.text((90, 640), "Our code words (not in any manual):", fill=green, font=HANDB(36))
d.text((130, 705), "GROUND TRUTH  =  map + terrain", fill=green, font=HAND(34))
d.text((130, 760), "BOX  =  the GPS", fill=green, font=HAND(34))
d.text((90, 840), "40 min delay  ≈  1/3 navigation, 2/3 relay", fill=black, font=HAND(34))
label(d, w, h)
im.save(OUT / "okafor_whiteboard_reporting_chain.png", optimize=True)

# 2. Map sketch: the position jump (SSG Treadway's interview).
w, h = 1600, 1000
im = Image.new("RGB", (w, h), (237, 233, 214))
d = ImageDraw.Draw(im)
for i in range(0, w, 100):
    d.line((i, 0, i, h), fill=(205, 200, 178), width=2)
for j in range(0, h, 100):
    d.line((0, j, w, j), fill=(205, 200, 178), width=2)
brown = (150, 105, 60)
for k in range(7):  # contour lines for a ridge
    r = 90 + k * 55
    d.ellipse((380 - r * 1.6, 520 - r, 380 + r * 1.6, 520 + r), outline=brown, width=3)
d.rectangle((308, 582, 432, 626), fill=(237, 233, 214))
d.text((318, 580), "RIDGE", fill=brown, font=SANSB(34))
d.line((900, 160, 1000, 420, 980, 700, 1080, 960), fill=(70, 120, 190), width=10)
d.text((1030, 640), "draw", fill=(70, 120, 190), font=SANS(30))
d.ellipse((350, 480, 410, 540), fill=(30, 110, 60))
d.text((425, 455), "Actual position", fill=(30, 110, 60), font=SANSB(32))
d.ellipse((1300, 640, 1360, 700), fill=(200, 40, 40))
d.text((1180, 715), "GPS said we were here", fill=(200, 40, 40), font=SANSB(32))
arrow(d, (420, 520), (1290, 665), (200, 40, 40), width=5)
d.rectangle((690, 440, 1100, 492), fill=(250, 248, 238))
d.text((702, 446), "≈ 2 km jump, then \"no fix\"", fill=(200, 40, 40), font=SANSB(30))
d.rectangle((1180, 210, 1260, 290), outline=(40, 40, 45), width=5)
d.text((1100, 300), "OP reported 800 m off,\nwrong side of the draw", fill=(40, 40, 45), font=SANS(28))
d.rectangle((40, 30, 900, 110), fill=(250, 248, 238))
d.text((60, 42), "Night screen, 0200: GPS position jump", fill=(40, 40, 45), font=SANSB(42))
label(d, w, h)
im.save(OUT / "treadway_map_position_jump.png", optimize=True)

# 3. Timeline: intermittent jamming over one night (CW3 Vasquez-Hart).
w, h = 1600, 900
im = Image.new("RGB", (w, h), (255, 255, 255))
d = ImageDraw.Draw(im)
ink, muted, red, grey = (35, 40, 55), (110, 115, 125), (205, 50, 60), (220, 224, 232)
d.text((70, 40), "Jamming logged over one night (intermittent, not a switch)", fill=ink, font=SANSB(40))
x0, x1, y = 120, 1500, 330
d.rectangle((x0, y, x1, y + 110), fill=grey)
start = 60  # minutes after 0100 on the axis (0100 to 0500 = 240 min)
segments = [(60, 72), (76, 88), (91, 98), (120, 131), (134, 150), (171, 177), (185, 199)]
px = lambda m: x0 + (x1 - x0) * m / 240
for a, b in segments:
    d.rectangle((px(a), y, px(b), y + 110), fill=red)
for hour, m in (("0100", 0), ("0200", 60), ("0300", 120), ("0400", 180), ("0500", 240)):
    d.line((px(m), y + 110, px(m), y + 130), fill=ink, width=3)
    d.text((px(m) - 34, y + 140), hour, fill=ink, font=SANS(28))
d.rectangle((120, 560, 150, 590), fill=red)
d.text((165, 555), "Receiver jammed (lock lost)", fill=ink, font=SANS(28))
d.rectangle((560, 560, 590, 590), fill=grey)
d.text((605, 555), "Signal back (some fixes still bad)", fill=ink, font=SANS(28))
d.line((px(60), 300, px(72), 300), fill=ink, width=3)
d.text((px(60) - 10, 250), "crews noticed after 5 to 15 min", fill=ink, font=SANS(28))
d.text((120, 660), "One night also showed signs of spoofing: a parked vehicle's position drifting\n"
                   "in a straight line at a steady speed, while the screen looked healthy.",
       fill=muted, font=SANS(28), spacing=8)
label(d, w, h)
im.save(OUT / "vasquez_hart_jamming_timeline.png", optimize=True)
print("wrote:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
