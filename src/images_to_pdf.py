#!/usr/bin/env python3
"""
images_to_pdf.py

Convert images from an exercise directory tree into a single PDF.
This is intended for folders like `algebra_7_class/<exercise>/<image files>`.

For each exercise folder:
    - the first image file is ignored as a page source
    - a generated text title page is inserted instead
    - a PDF outline entry is added for fast navigation

Supported formats:
    .heic, .heif, .jpg, .jpeg, .png, .bmp, .tif, .tiff, .webp

Requirements:
    pip install pillow pillow-heif reportlab

Usage:
    python src/images_to_pdf.py algebra_7_class algebra_7_class.pdf
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from reportlab.lib.colors import black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SUPPORTED_EXTENSIONS = {
    ".heic",
    ".heif",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

DEFAULT_MARGIN = 24
DEFAULT_TITLE_PAGE_HEIGHT = 630
TITLE_FONT_NAME = "Helvetica-Bold"
TITLE_FONT_MIN_SIZE = 32
TITLE_FONT_MAX_SIZE = 220
TITLE_FONT_STEP = 4


@dataclass(frozen=True)
class ExerciseSection:
    exercise: str
    directory: Path
    source_images: list[Path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert exercise image folders into a bookmarked PDF."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Root directory containing exercise subfolders",
    )
    parser.add_argument(
        "output_pdf",
        type=Path,
        help="Output PDF file path",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=DEFAULT_MARGIN,
        help=f"White margin around each image in pixels, default: {DEFAULT_MARGIN}",
    )
    parser.add_argument(
        "--title-page-height",
        type=int,
        default=DEFAULT_TITLE_PAGE_HEIGHT,
        help=(
            "Height of generated exercise title pages in pixels, "
            f"default: {DEFAULT_TITLE_PAGE_HEIGHT}"
        ),
    )
    return parser.parse_args()


def path_sort_key(path: Path) -> tuple:
    parts = path.relative_to(path.anchor).parts if path.is_absolute() else path.parts
    key = []
    for part in parts:
        split_parts = re.split(r"(\d+)", part.lower())
        for item in split_parts:
            if not item:
                continue
            if item.isdigit():
                key.append((0, int(item)))
            else:
                key.append((1, item))
    return tuple(key)


def list_supported_files(directory: Path) -> list[Path]:
    files = [path for path in directory.iterdir() if path.is_file()]
    images = [path for path in files if path.suffix.lower() in SUPPORTED_EXTENSIONS]
    images.sort(key=lambda path: path_sort_key(path))
    return images


def collect_sections(input_dir: Path) -> list[ExerciseSection]:
    subdirs = [path for path in input_dir.iterdir() if path.is_dir()]
    subdirs.sort(key=path_sort_key)

    sections: list[ExerciseSection] = []
    for subdir in subdirs:
        images = list_supported_files(subdir)
        if not images:
            continue

        sections.append(
            ExerciseSection(
                exercise=subdir.name,
                directory=subdir,
                source_images=images[1:],
            )
        )

    return sections


def load_image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.size


def compute_canvas_width(sections: list[ExerciseSection], margin: int) -> int:
    max_width = 0
    for section in sections:
        for image_path in section.source_images:
            width, _ = load_image_size(image_path)
            max_width = max(max_width, width)
    return max_width + margin * 2


def fit_font_size(
    pdf: canvas.Canvas,
    text: str,
    page_width: int,
    margin: int,
) -> int:
    max_text_width = max(page_width - margin * 2, 1)
    for font_size in range(TITLE_FONT_MAX_SIZE, TITLE_FONT_MIN_SIZE - 1, -TITLE_FONT_STEP):
        if pdf.stringWidth(text, TITLE_FONT_NAME, font_size) <= max_text_width:
            return font_size
    return TITLE_FONT_MIN_SIZE


def draw_title_page(
    pdf: canvas.Canvas,
    exercise: str,
    page_width: int,
    page_height: int,
    margin: int,
) -> None:
    pdf.setPageSize((page_width, page_height))
    pdf.setFillColor(white)
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    title = f"Exercise {exercise}"
    font_size = fit_font_size(pdf, title, page_width, margin)
    pdf.setFillColor(black)
    pdf.setFont(TITLE_FONT_NAME, font_size)

    text_width = pdf.stringWidth(title, TITLE_FONT_NAME, font_size)
    x = (page_width - text_width) / 2
    y = (page_height - font_size) / 2
    pdf.drawString(x, y, title)


def draw_image_page(
    pdf: canvas.Canvas,
    image_path: Path,
    page_width: int,
    margin: int,
) -> None:
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)

        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha_source = img.convert("RGBA")
            background.paste(alpha_source, mask=alpha_source.getchannel("A"))
            rendered = background
        elif img.mode == "L":
            rendered = img.convert("RGB")
        else:
            rendered = img.convert("RGB")

        available_width = max(page_width - margin * 2, 1)
        scale = min(1.0, available_width / rendered.width)
        draw_width = max(int(round(rendered.width * scale)), 1)
        draw_height = max(int(round(rendered.height * scale)), 1)
        page_height = draw_height + margin * 2

        pdf.setPageSize((page_width, page_height))
        pdf.setFillColor(white)
        pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

        x = (page_width - draw_width) / 2
        y = margin
        pdf.drawImage(
            ImageReader(rendered),
            x,
            y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )


def build_pdf(
    sections: list[ExerciseSection],
    output_pdf: Path,
    margin: int,
    title_page_height: int,
) -> None:
    if not sections:
        raise ValueError("No exercise folders with supported image files found.")

    canvas_width = compute_canvas_width(sections, margin)
    if canvas_width <= margin * 2:
        canvas_width = 1200 + margin * 2

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pageCompression=1)

    for section in sections:
        bookmark_name = f"exercise-{section.exercise}"
        print(f"Adding exercise {section.exercise}")

        draw_title_page(pdf, section.exercise, canvas_width, title_page_height, margin)
        pdf.bookmarkPage(bookmark_name)
        pdf.addOutlineEntry(f"Exercise {section.exercise}", bookmark_name, level=0)
        pdf.showPage()

        for image_path in section.source_images:
            print(f"  Adding image: {image_path}")
            draw_image_page(pdf, image_path, canvas_width, margin)
            pdf.showPage()

    pdf.save()
    print(f"\nPDF created: {output_pdf}")


def main() -> int:
    register_heif_opener()

    args = parse_args()
    input_dir: Path = args.input_dir
    output_pdf: Path = args.output_pdf

    if not input_dir.exists():
        print(f"Error: directory does not exist: {input_dir}", file=sys.stderr)
        return 1

    if not input_dir.is_dir():
        print(f"Error: input path is not a directory: {input_dir}", file=sys.stderr)
        return 1

    if args.margin < 0:
        print("Error: margin must be zero or greater.", file=sys.stderr)
        return 1

    if args.title_page_height <= 0:
        print("Error: title-page-height must be greater than zero.", file=sys.stderr)
        return 1

    sections = collect_sections(input_dir)
    if not sections:
        print("Error: no exercise folders with supported image files found.", file=sys.stderr)
        return 1

    print("Exercises to include:")
    for section in sections:
        print(f"  {section.exercise}: {len(section.source_images)} page image(s)")

    try:
        build_pdf(
            sections=sections,
            output_pdf=output_pdf,
            margin=args.margin,
            title_page_height=args.title_page_height,
        )
        return 0
    except Exception as exc:
        print(f"Error while creating PDF: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
