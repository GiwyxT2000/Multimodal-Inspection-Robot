from __future__ import print_function

from pathlib import Path

from PIL import Image


DPI = 300
A4_WIDTH = int(round(210 / 25.4 * DPI))
A4_HEIGHT = int(round(297 / 25.4 * DPI))
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIGN_DIR = PROJECT_ROOT / "标牌设计"

BASE_TARGET = SIGN_DIR / "A01_巡检目标标牌.png"
ANCHOR = SIGN_DIR / "A01_工位定位锚点牌_短码QR.png"
NEW_PHOTO = SIGN_DIR / "ChatGPT Image 2026年6月12日 12_08_50.png"

OUT_TARGET_PNG = SIGN_DIR / "A01_巡检目标标牌_warning_同版式.png"
OUT_TARGET_PDF = SIGN_DIR / "A01_巡检目标标牌_warning_同版式.pdf"
OUT_COMBINED_PDF = SIGN_DIR / "A01_双标牌打印版_warning_同版式.pdf"


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


def main():
    for path in [BASE_TARGET, ANCHOR, NEW_PHOTO]:
        if not path.exists():
            raise RuntimeError("Missing file: {0}".format(path))

    target = Image.open(str(BASE_TARGET)).convert("RGB")

    # Same image area used by generate_patrol_signs.py:
    # picture_box = (230, 700, A4_WIDTH - 230, 2250)
    # photo_box = picture_box inset by 18 px.
    photo_box = (248, 718, A4_WIDTH - 248, 2250 - 18)
    paste_cover(target, NEW_PHOTO, photo_box)

    target.save(str(OUT_TARGET_PNG), dpi=(DPI, DPI))
    target.save(str(OUT_TARGET_PDF), "PDF", resolution=DPI)

    anchor = Image.open(str(ANCHOR)).convert("RGB")
    anchor.save(str(OUT_COMBINED_PDF), "PDF", resolution=DPI, save_all=True, append_images=[target])

    print("Generated same-template warning sign:")
    print(" - target_png:", OUT_TARGET_PNG)
    print(" - target_pdf:", OUT_TARGET_PDF)
    print(" - combined_pdf:", OUT_COMBINED_PDF)


if __name__ == "__main__":
    main()
