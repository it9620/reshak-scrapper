#!/usr/bin/env python3
"""
images_to_pdf.py

Convert images from an exercise directory tree into a single PDF.
This is intended for folders like `algebra_7_class/<exercise>/<image files>`.

For each exercise folder:
    - the first image file is ignored as a page source
    - a small generated header is placed above the first real image page
    - PDF contents pages are generated at the start
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
HEADER_HEIGHT = 44
HEADER_GAP = 12
HEADER_FONT_NAME = "Helvetica-Bold"
HEADER_FONT_SIZE = 20
TOC_TITLE_FONT_NAME = "Helvetica-Bold"
TOC_TITLE_FONT_SIZE = 28
TOC_ENTRY_FONT_NAME = "Helvetica"
TOC_ENTRY_FONT_SIZE = 14
TOC_LINE_HEIGHT = 20
TOC_TOP_MARGIN = 56
TOC_BOTTOM_MARGIN = 48


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
        "--toc-title",
        default="Contents",
        help="Title used for generated contents pages",
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
    font_size = HEADER_FONT_SIZE
    while font_size > 10:
        if pdf.stringWidth(text, HEADER_FONT_NAME, font_size) <= max_text_width:
            return font_size
        font_size -= 1
    return 10


def section_page_count(section: ExerciseSection) -> int:
    return max(len(section.source_images), 1)


def compute_contents_page_count(sections: list[ExerciseSection], page_height: int) -> int:
    usable_height = page_height - TOC_TOP_MARGIN - TOC_BOTTOM_MARGIN - TOC_LINE_HEIGHT * 2
    entries_per_page = max(usable_height // TOC_LINE_HEIGHT, 1)
    return max((len(sections) + entries_per_page - 1) // entries_per_page, 1)


def build_contents_entries(
    sections: list[ExerciseSection],
    contents_page_count: int,
) -> list[tuple[str, int, str]]:
    entries: list[tuple[str, int, str]] = []
    current_page = contents_page_count + 1
    for section in sections:
        entries.append((section.exercise, current_page, f"exercise-{section.exercise}"))
        current_page += section_page_count(section)
    return entries


def draw_contents_pages(
    pdf: canvas.Canvas,
    entries: list[tuple[str, int, str]],
    page_width: int,
    page_height: int,
    title: str,
) -> None:
    usable_height = page_height - TOC_TOP_MARGIN - TOC_BOTTOM_MARGIN - TOC_LINE_HEIGHT * 2
    entries_per_page = max(usable_height // TOC_LINE_HEIGHT, 1)

    for page_index in range(0, len(entries), entries_per_page):
        chunk = entries[page_index : page_index + entries_per_page]
        pdf.setPageSize((page_width, page_height))
        pdf.setFillColor(white)
        pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        pdf.setFillColor(black)

        title_text = title if page_index == 0 else f"{title} ({page_index // entries_per_page + 1})"
        pdf.setFont(TOC_TITLE_FONT_NAME, TOC_TITLE_FONT_SIZE)
        pdf.drawString(DEFAULT_MARGIN, page_height - TOC_TOP_MARGIN, title_text)

        y = page_height - TOC_TOP_MARGIN - TOC_LINE_HEIGHT * 2
        pdf.setFont(TOC_ENTRY_FONT_NAME, TOC_ENTRY_FONT_SIZE)
        for exercise, page_number, bookmark_name in chunk:
            left_text = f"Exercise {exercise}"
            right_text = str(page_number)
            pdf.drawString(DEFAULT_MARGIN, y, left_text)
            right_width = pdf.stringWidth(right_text, TOC_ENTRY_FONT_NAME, TOC_ENTRY_FONT_SIZE)
            pdf.drawString(page_width - DEFAULT_MARGIN - right_width, y, right_text)

            pdf.linkRect(
                "",
                bookmark_name,
                (
                    DEFAULT_MARGIN,
                    y - 4,
                    page_width - DEFAULT_MARGIN,
                    y + TOC_ENTRY_FONT_SIZE + 2,
                ),
                relative=0,
                thickness=0,
            )
            y -= TOC_LINE_HEIGHT

        pdf.showPage()


def draw_image_page(
    pdf: canvas.Canvas,
    image_path: Path,
    page_width: int,
    margin: int,
    exercise: str | None = None,
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
        header_height = HEADER_HEIGHT if exercise else 0
        gap = HEADER_GAP if exercise else 0
        page_height = draw_height + margin * 2 + header_height + gap

        pdf.setPageSize((page_width, page_height))
        pdf.setFillColor(white)
        pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

        if exercise:
            header_text = f"Exercise {exercise}"
            font_size = fit_font_size(pdf, header_text, page_width, margin)
            pdf.setFillColor(black)
            pdf.setFont(HEADER_FONT_NAME, font_size)
            header_y = page_height - margin - font_size
            pdf.drawString(margin, header_y, header_text)

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
    toc_title: str,
) -> None:
    if not sections:
        raise ValueError("No exercise folders with supported image files found.")

    canvas_width = compute_canvas_width(sections, margin)
    if canvas_width <= margin * 2:
        canvas_width = 1200 + margin * 2

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pageCompression=1)
    contents_page_height = 842
    contents_page_count = compute_contents_page_count(sections, contents_page_height)
    contents_entries = build_contents_entries(sections, contents_page_count)

    draw_contents_pages(
        pdf,
        contents_entries,
        canvas_width,
        contents_page_height,
        toc_title,
    )

    for section in sections:
        bookmark_name = f"exercise-{section.exercise}"
        print(f"Adding exercise {section.exercise}")

        if not section.source_images:
            pdf.setPageSize((canvas_width, HEADER_HEIGHT + margin * 2))
            pdf.setFillColor(white)
            pdf.rect(0, 0, canvas_width, HEADER_HEIGHT + margin * 2, fill=1, stroke=0)
            pdf.setFillColor(black)
            pdf.setFont(HEADER_FONT_NAME, HEADER_FONT_SIZE)
            pdf.drawString(margin, margin + HEADER_HEIGHT / 2, f"Exercise {section.exercise}")
            pdf.bookmarkPage(bookmark_name)
            pdf.addOutlineEntry(f"Exercise {section.exercise}", bookmark_name, level=0)
            pdf.showPage()
            continue

        for index, image_path in enumerate(section.source_images):
            print(f"  Adding image: {image_path}")
            draw_image_page(
                pdf,
                image_path,
                canvas_width,
                margin,
                exercise=section.exercise if index == 0 else None,
            )
            if index == 0:
                pdf.bookmarkPage(bookmark_name)
                pdf.addOutlineEntry(f"Exercise {section.exercise}", bookmark_name, level=0)
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

    if not args.toc_title.strip():
        print("Error: toc-title must not be empty.", file=sys.stderr)
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
            toc_title=args.toc_title,
        )
        return 0
    except Exception as exc:
        print(f"Error while creating PDF: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
