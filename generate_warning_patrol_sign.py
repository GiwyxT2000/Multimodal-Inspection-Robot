from __future__ import print_function

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DPI = 300
A4_WIDTH = int(round(210 / 25.4 * DPI))
A4_HEIGHT = int(round(297 / 25.4 * DPI))
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "标牌设计"
SOURCE_IMAGE = OUTPUT_DIR / "ChatGPT Image 2026年6月12日 12_08_50.png"
ANCHOR_IMAGE = OUTPUT_DIR / "A01_工位定位锚点牌_短码QR.png"


COLORS = {
    "white": (255, 255, 255),
    "black": (20, 24, 33),
    "gray": (92, 103, 118),
    "light_gray": (236, 240, 245),
    "amber": (218, 133, 18),
    "amber_light": (255, 245, 222),
    "dark_amber": (125, 74, 0),
    "red": (196, 42, 42),
    "blue": (31, 96, 196),
}


def find_font():
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
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


def make_warning_target_sign():
    image = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), COLORS["white"])
    draw = ImageDraw.Draw(image)

    draw.rectangle((70, 70, A4_WIDTH - 70, A4_HEIGHT - 70), outline=COLORS["amber"], width=22)
    draw.rectangle((95, 95, A4_WIDTH - 95, 300), fill=COLORS["amber_light"])
    draw_corner_markers(draw, COLORS["amber"])

    draw_centered(draw, 125, "工业产线单工位巡检标牌", font(58), COLORS["dark_amber"])
    draw_centered(draw, 390, "设备 A01", font(170), COLORS["black"])

    status_box = (300, 575, A4_WIDTH - 300, 705)
    draw.rounded_rectangle(status_box, radius=18, fill=COLORS["amber"], outline=COLORS["dark_amber"], width=6)
    draw_centered(draw, 603, "WARNING  温度已恢复，电气危险仍需警戒", font(68), COLORS["white"], status_box[0], status_box[2])

    picture_box = (230, 760, A4_WIDTH - 230, 2250)
    draw.rectangle(picture_box, fill=(248, 250, 252), outline=COLORS["amber"], width=12)
    photo_box = (picture_box[0] + 18, picture_box[1] + 18, picture_box[2] - 18, picture_box[3] - 18)
    paste_cover(image, SOURCE_IMAGE, photo_box)
    draw.rectangle(picture_box, outline=COLORS["amber"], width=12)

    draw.rectangle((300, 2320, A4_WIDTH - 300, 2545), fill=COLORS["amber"])
    draw_centered(draw, 2363, "请识别设备状态与现场风险", font(88), COLORS["white"], 300, A4_WIDTH - 300)

    draw_centered(draw, 2630, "状态提示：温度显示正常，但现场存在电气危险标识与线缆风险", font(60), COLORS["black"])
    draw_centered(draw, 2700, "建议等级：warning / 预警", font(72), COLORS["dark_amber"])
    draw_centered(draw, 2810, "用途：云台主动搜索后，由多模态大模型理解画面并给出处置建议", font(56), COLORS["gray"])

    return image


def save_outputs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = make_warning_target_sign()
    target_png = OUTPUT_DIR / "A01_巡检目标标牌_warning.png"
    target_pdf = OUTPUT_DIR / "A01_巡检目标标牌_warning.pdf"
    target.save(str(target_png), dpi=(DPI, DPI))
    target.save(str(target_pdf), "PDF", resolution=DPI)

    combined_pdf = OUTPUT_DIR / "A01_双标牌打印版_warning.pdf"
    if ANCHOR_IMAGE.exists():
        anchor = Image.open(str(ANCHOR_IMAGE)).convert("RGB")
        anchor.save(str(combined_pdf), "PDF", resolution=DPI, save_all=True, append_images=[target])

    metadata = {
        "variant": "warning",
        "dpi": DPI,
        "page": "A4 portrait",
        "source_image": str(SOURCE_IMAGE),
        "risk_design": {
            "expected_level": "warning",
            "visual_logic": "Temperature recovered to normal range, but electrical hazard sign and cable risk remain.",
        },
        "files": {
            "target_png": str(target_png),
            "target_pdf": str(target_pdf),
            "combined_pdf": str(combined_pdf) if ANCHOR_IMAGE.exists() else None,
        },
    }
    metadata_path = OUTPUT_DIR / "A01_标牌元数据_warning.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata_path, metadata


def main():
    if not SOURCE_IMAGE.exists():
        raise RuntimeError("Source image not found: {0}".format(SOURCE_IMAGE))
    metadata_path, metadata = save_outputs()
    print("Generated warning patrol sign:")
    for key, value in metadata["files"].items():
        print(" - {0}: {1}".format(key, value))
    print(" - metadata: {0}".format(metadata_path))


if __name__ == "__main__":
    main()
