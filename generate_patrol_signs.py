from __future__ import print_function

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.barcode import qr


DPI = 300
A4_WIDTH = int(round(210 / 25.4 * DPI))
A4_HEIGHT = int(round(297 / 25.4 * DPI))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "标牌设计"
TARGET_PHOTO_NAME = "ChatGPT Image 2026年6月10日 16_08_45.png"

QR_SIZE_MM = 90
QR_SIZE_PX = int(round(QR_SIZE_MM / 25.4 * DPI))
ANCHOR_QR_PAYLOAD = "A01_STOP"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)


COLORS = {
    "white": (255, 255, 255),
    "black": (20, 24, 33),
    "gray": (92, 103, 118),
    "light_gray": (236, 240, 245),
    "blue": (31, 96, 196),
    "blue_light": (225, 238, 255),
    "red": (196, 42, 42),
    "red_light": (255, 231, 229),
    "amber": (225, 138, 25),
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


def font(size, bold=False):
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


def base_page(border_color, accent_fill):
    image = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), COLORS["white"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, A4_WIDTH - 70, A4_HEIGHT - 70), outline=border_color, width=22)
    draw.rectangle((95, 95, A4_WIDTH - 95, 300), fill=accent_fill)
    draw_corner_markers(draw, border_color)
    return image, draw


def paste_qr(image, payload, x, y):
    qr_image = make_qr_image(payload)
    image.paste(qr_image, (x, y))
    return (x, y, x + QR_SIZE_PX, y + QR_SIZE_PX)


def paste_cover(image, source_path, box):
    source = Image.open(str(source_path)).convert("RGB")
    box_width = box[2] - box[0]
    box_height = box[3] - box[1]
    src_width, src_height = source.size
    box_ratio = float(box_width) / float(box_height)
    src_ratio = float(src_width) / float(src_height)

    if src_ratio > box_ratio:
        new_width = int(round(src_height * box_ratio))
        left = (src_width - new_width) // 2
        source = source.crop((left, 0, left + new_width, src_height))
    else:
        new_height = int(round(src_width / box_ratio))
        top = (src_height - new_height) // 2
        source = source.crop((0, top, src_width, top + new_height))

    source = source.resize((box_width, box_height), RESAMPLE)
    image.paste(source, (box[0], box[1]))


def save_outputs(name, image):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUTPUT_DIR / (name + ".png")
    pdf_path = OUTPUT_DIR / (name + ".pdf")
    image.save(str(png_path), dpi=(DPI, DPI))
    image.save(str(pdf_path), "PDF", resolution=DPI)
    return png_path, pdf_path


def make_anchor_sign():
    payload_obj = {
        "station": "A01",
        "role": "stop_anchor",
        "action": "approach_and_stop",
        "qr_size_mm": QR_SIZE_MM,
        "qr_payload": ANCHOR_QR_PAYLOAD,
        "qr_format": "short_code",
    }
    payload = ANCHOR_QR_PAYLOAD

    image, draw = base_page(COLORS["blue"], COLORS["blue_light"])
    draw_centered(draw, 125, "第21届研究生电子设计竞赛 Demo", font(54), COLORS["blue"])
    draw_centered(draw, 390, "A01 工位定位牌", font(150), COLORS["black"])
    draw_centered(draw, 610, "STOP", font(260), COLORS["blue"])
    draw_centered(draw, 930, "看到此锚点后停车，开始局部巡检", font(76), COLORS["gray"])

    qr_x = (A4_WIDTH - QR_SIZE_PX) // 2
    qr_y = 1180
    paste_qr(image, payload, qr_x, qr_y)

    draw_centered(draw, 2310, "二维码角色：stop_anchor", font(64), COLORS["black"])
    draw_centered(draw, 2365, "QR PAYLOAD: A01_STOP", font(58), COLORS["black"])
    draw_centered(draw, 2410, "打印二维码真实宽度：90 mm", font(58), COLORS["gray"])
    draw_centered(draw, 2680, "用途：直线前进阶段的工位停车锚点", font(66), COLORS["black"])

    return image, payload_obj


def make_target_sign():
    payload_obj = {
        "station": "A01",
        "role": "inspection_target",
        "device": "MOTOR-A01",
        "visual_cues": ["red_alarm_light", "scattered_cable", "high_temperature"],
        "note": "No QR code on this sign. It is intended for multimodal model understanding.",
        "visual_source": TARGET_PHOTO_NAME if (OUTPUT_DIR / TARGET_PHOTO_NAME).exists() else "fallback_illustration",
    }

    image, draw = base_page(COLORS["red"], COLORS["red_light"])
    draw_centered(draw, 125, "工业产线单工位巡检标牌", font(58), COLORS["red"])
    draw_centered(draw, 390, "设备 A01", font(170), COLORS["black"])

    picture_box = (230, 700, A4_WIDTH - 230, 2250)
    draw.rectangle(picture_box, fill=(248, 250, 252), outline=COLORS["red"], width=12)

    target_photo = OUTPUT_DIR / TARGET_PHOTO_NAME
    photo_box = (picture_box[0] + 18, picture_box[1] + 18, picture_box[2] - 18, picture_box[3] - 18)
    if target_photo.exists():
        paste_cover(image, target_photo, photo_box)
    else:
        draw_centered(draw, 735, "模拟设备画面", font(68), COLORS["gray"], picture_box[0], picture_box[2])

        # Control cabinet
        cabinet = (420, 930, 1250, 1840)
        draw.rounded_rectangle(cabinet, radius=18, fill=(213, 221, 232), outline=(65, 76, 90), width=8)
        draw.rectangle((500, 1040, 1170, 1280), fill=(26, 33, 46), outline=(20, 24, 33), width=4)
        draw.text((560, 1100), "MOTOR-A01", font=font(72), fill=(235, 245, 255))
        draw.text((560, 1200), "TEMP  82 C", font=font(66), fill=(255, 202, 88))

        draw.ellipse((520, 1390, 650, 1520), fill=(64, 180, 95), outline=COLORS["black"], width=4)
        draw.text((700, 1402), "RUN", font=font(58), fill=COLORS["black"])
        draw.ellipse((520, 1570, 650, 1700), fill=COLORS["red"], outline=COLORS["black"], width=4)
        draw.text((700, 1582), "ALARM", font=font(58), fill=COLORS["red"])

        # Motor body
        motor = (1520, 1180, 2120, 1680)
        draw.rounded_rectangle(motor, radius=80, fill=(126, 145, 167), outline=(55, 65, 80), width=8)
        draw.ellipse((1370, 1260, 1620, 1510), fill=(96, 116, 139), outline=(55, 65, 80), width=8)
        draw.rectangle((2110, 1315, 2260, 1545), fill=(96, 116, 139), outline=(55, 65, 80), width=8)
        draw.text((1585, 1365), "PUMP", font=font(88), fill=COLORS["white"])

        # Warning triangle
        triangle = [(1620, 840), (1910, 840), (1765, 1080)]
        draw.polygon(triangle, fill=(255, 210, 72), outline=COLORS["black"])
        draw.text((1735, 870), "!", font=font(126), fill=COLORS["black"])

        # Scattered cables
        cable_paths = [
            [(690, 1830), (950, 1980), (1220, 1900), (1500, 2060), (1790, 1960), (2050, 2130)],
            [(520, 1940), (760, 2090), (1060, 2020), (1320, 2160), (1640, 2090)],
            [(1460, 1680), (1510, 1830), (1390, 1990), (1560, 2160), (1860, 2180)],
        ]
        for path in cable_paths:
            draw.line(path, fill=(18, 22, 30), width=22, joint="curve")

    draw.rectangle(picture_box, outline=COLORS["red"], width=12)

    draw.rectangle((300, 2320, A4_WIDTH - 300, 2545), fill=COLORS["red"])
    draw_centered(draw, 2365, "请识别设备状态与现场风险", font(88), COLORS["white"], 300, A4_WIDTH - 300)

    draw_centered(draw, 2690, "用途：云台主动搜索后，由多模态大模型理解画面", font(66), COLORS["black"])

    return image, payload_obj


def main():
    anchor, anchor_payload = make_anchor_sign()
    target, target_payload = make_target_sign()

    anchor_png, anchor_pdf = save_outputs("A01_工位定位锚点牌_短码QR", anchor)
    target_png, target_pdf = save_outputs("A01_巡检目标标牌", target)

    combined_pdf = OUTPUT_DIR / "A01_双标牌打印版_短码QR.pdf"
    anchor.save(str(combined_pdf), "PDF", resolution=DPI, save_all=True, append_images=[target])

    metadata = {
        "dpi": DPI,
        "page": "A4 portrait",
        "qr_size_mm": QR_SIZE_MM,
        "files": {
            "anchor_png": str(anchor_png),
            "anchor_pdf": str(anchor_pdf),
            "target_png": str(target_png),
            "target_pdf": str(target_pdf),
            "combined_pdf": str(combined_pdf),
        },
        "payloads": {
            "anchor": anchor_payload,
            "target": target_payload,
        },
    }
    metadata_path = OUTPUT_DIR / "A01_标牌元数据_短码QR.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Generated patrol signs:")
    for key, value in metadata["files"].items():
        print(" - {}: {}".format(key, value))
    print(" - metadata: {}".format(metadata_path))


if __name__ == "__main__":
    main()
