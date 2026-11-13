from __future__ import print_function

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.barcode import qr


DPI = 300
A4_WIDTH = int(round(210 / 25.4 * DPI))
A4_HEIGHT = int(round(297 / 25.4 * DPI))
QR_SIZE_MM = 90
QR_SIZE_PX = int(round(QR_SIZE_MM / 25.4 * DPI))
QR_PAYLOAD = "A01_STOP"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIGN_DIR = PROJECT_ROOT / "标牌设计"
TARGET_REFERENCE = SIGN_DIR / "A01_巡检目标标牌.png"
OUT_ANCHOR_PNG = SIGN_DIR / "A01_工位定位锚点牌_统一版.png"
OUT_ANCHOR_PDF = SIGN_DIR / "A01_工位定位锚点牌_统一版.pdf"
OUT_COMBINED_PDF = SIGN_DIR / "A01_双标牌打印版_统一定位牌.pdf"


COLORS = {
    "white": (255, 255, 255),
    "black": (20, 24, 33),
    "gray": (92, 103, 118),
    "red": (196, 42, 42),
    "red_light": (255, 231, 229),
    "blue": (31, 96, 196),
    "blue_light": (225, 238, 255),
}


def find_font():
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


FONT_PATH = find_font()


def font(size):
    if FONT_PATH:
        return ImageFont.truetype(FONT_PATH, size=size)
    return ImageFont.load_default()


def text_size(draw, text, font_obj):
    box = draw.textbbox((0, 0), text, font=font_obj)
    return box[2] - box[0], box[3] - box[1]


def draw_centered(draw, y, text, font_obj, fill, x0=0, x1=A4_WIDTH):
    w, h = text_size(draw, text, font_obj)
    x = x0 + (x1 - x0 - w) // 2
    draw.text((x, y), text, font=font_obj, fill=fill)
    return y + h


def draw_corner_markers(draw, color):
    size = 105
    gap = 120
    positions = [
        (gap, gap),
        (A4_WIDTH - gap - size, gap),
        (gap, A4_HEIGHT - gap - size),
        (A4_WIDTH - gap - size, A4_HEIGHT - gap - size),
    ]
    for x, y in positions:
        draw.rectangle((x, y, x + size, y + size), fill=color)


def make_qr_image(payload, size_px=QR_SIZE_PX):
    widget = qr.QrCodeWidget(payload)
    image = Image.new("RGB", (size_px, size_px), COLORS["white"])

    code = widget.qr
    code.make()
    modules = code.getModuleCount()
    quiet_modules = 4
    total_modules = modules + quiet_modules * 2
    cell = max(1, size_px // total_modules)
    drawn_size = cell * total_modules
    offset = (size_px - drawn_size) // 2

    draw = ImageDraw.Draw(image)
    for row in range(modules):
        for col in range(modules):
            if code.isDark(row, col):
                x0 = offset + (col + quiet_modules) * cell
                y0 = offset + (row + quiet_modules) * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill=COLORS["black"])
    return image


def make_anchor():
    image = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), COLORS["white"])
    draw = ImageDraw.Draw(image)

    draw.rectangle((70, 70, A4_WIDTH - 70, A4_HEIGHT - 70), outline=COLORS["blue"], width=22)
    draw.rectangle((95, 95, A4_WIDTH - 95, 300), fill=COLORS["blue_light"])
    draw_corner_markers(draw, COLORS["blue"])

    draw_centered(draw, 125, "工业产线单工位巡检标牌", font(58), COLORS["blue"])
    draw_centered(draw, 390, "A01 工位定位牌", font(150), COLORS["black"])
    draw_centered(draw, 600, "STOP", font(190), COLORS["blue"])

    picture_box = (230, 900, A4_WIDTH - 230, 2250)
    draw.rectangle(picture_box, fill=COLORS["white"], outline=COLORS["blue"], width=12)

    qr_image = make_qr_image(QR_PAYLOAD)
    qr_x = (A4_WIDTH - QR_SIZE_PX) // 2
    qr_y = picture_box[1] + (picture_box[3] - picture_box[1] - QR_SIZE_PX) // 2
    image.paste(qr_image, (qr_x, qr_y))

    draw.rectangle((300, 2320, A4_WIDTH - 300, 2545), fill=COLORS["blue"])
    draw_centered(draw, 2365, "看到此定位牌后停车，开始局部巡检", font(78), COLORS["white"], 300, A4_WIDTH - 300)

    draw_centered(draw, 2690, "用途：直线前进阶段的工位停车锚点", font(66), COLORS["black"])

    return image


def main():
    anchor = make_anchor()
    anchor.save(str(OUT_ANCHOR_PNG), dpi=(DPI, DPI))
    anchor.save(str(OUT_ANCHOR_PDF), "PDF", resolution=DPI)

    if TARGET_REFERENCE.exists():
        target = Image.open(str(TARGET_REFERENCE)).convert("RGB")
        anchor.save(str(OUT_COMBINED_PDF), "PDF", resolution=DPI, save_all=True, append_images=[target])

    print("Generated unified anchor sign:")
    print(" - anchor_png:", OUT_ANCHOR_PNG)
    print(" - anchor_pdf:", OUT_ANCHOR_PDF)
    print(" - combined_pdf:", OUT_COMBINED_PDF)


if __name__ == "__main__":
    main()
