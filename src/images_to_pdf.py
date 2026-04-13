#!/usr/bin/env python3
"""
images_to_pdf.py

Convert images from an exercise directory tree into a single PDF.
This is intended for folders like `algebra_7_class/<exercise>/<image files>`.

For each exercise folder:
    - the first image file is ignored as a page source
    - a small generated header is placed above the first real image page
    - compact clickable contents pages are generated at the start
    - multiple images can share a page until there is no room left
    - page numbers are added at the bottom

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
from reportlab.lib.pagesizes import A4
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
DEFAULT_TOC_COLUMNS = 3
PAGE_WIDTH, PAGE_HEIGHT = A4
HEADER_FONT_NAME = "Helvetica-Bold"
HEADER_FONT_SIZE = 18
HEADER_SPACING = 10
BLOCK_SPACING = 16
FOOTER_FONT_NAME = "Helvetica"
FOOTER_FONT_SIZE = 11
FOOTER_HEIGHT = 24
TOC_TITLE_FONT_NAME = "Helvetica-Bold"
TOC_TITLE_FONT_SIZE = 26
TOC_ENTRY_FONT_NAME = "Helvetica"
TOC_ENTRY_FONT_SIZE = 11
TOC_LINE_HEIGHT = 15
TOC_TITLE_GAP = 28
TOC_COLUMN_GAP = 20


@dataclass(frozen=True)
class ExerciseSection:
    exercise: str
    directory: Path
    source_images: list[Path]


@dataclass(frozen=True)
class ContentBlock:
    exercise: str
    image_path: Path | None
    draw_width: float
    draw_height: float
    show_header: bool
    bookmark_name: str

    @property
    def content_height(self) -> float:
        header_height = HEADER_FONT_SIZE + HEADER_SPACING if self.show_header else 0
        return header_height + self.draw_height


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert exercise image folders into a compact bookmarked PDF."
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
        help=f"Page margin in points, default: {DEFAULT_MARGIN}",
    )
    parser.add_argument(
        "--toc-title",
        default="Contents",
        help="Title used for generated contents pages",
    )
    parser.add_argument(
        "--toc-columns",
        type=int,
        default=DEFAULT_TOC_COLUMNS,
        help=f"Number of columns on contents pages, default: {DEFAULT_TOC_COLUMNS}",
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
    images.sort(key=path_sort_key)
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


def build_content_blocks(
    sections: list[ExerciseSection],
    margin: int,
) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    usable_width = PAGE_WIDTH - margin * 2
    usable_height = PAGE_HEIGHT - margin * 2 - FOOTER_HEIGHT

    for section in sections:
        bookmark_name = f"exercise-{section.exercise}"

        if not section.source_images:
            blocks.append(
                ContentBlock(
                    exercise=section.exercise,
                    image_path=None,
                    draw_width=0,
                    draw_height=0,
                    show_header=True,
                    bookmark_name=bookmark_name,
                )
            )
            continue

        for index, image_path in enumerate(section.source_images):
            source_width, source_height = load_image_size(image_path)
            header_height = HEADER_FONT_SIZE + HEADER_SPACING if index == 0 else 0
            available_height = max(usable_height - header_height, 1)
            scale = min(usable_width / source_width, available_height / source_height, 1.0)

            blocks.append(
                ContentBlock(
                    exercise=section.exercise,
                    image_path=image_path,
                    draw_width=max(source_width * scale, 1),
                    draw_height=max(source_height * scale, 1),
                    show_header=index == 0,
                    bookmark_name=bookmark_name,
                )
            )

    return blocks


def paginate_content(
    blocks: list[ContentBlock],
    margin: int,
    starting_page_number: int,
) -> tuple[list[list[ContentBlock]], dict[str, int]]:
    pages: list[list[ContentBlock]] = []
    exercise_start_pages: dict[str, int] = {}
    usable_height = PAGE_HEIGHT - margin * 2 - FOOTER_HEIGHT

    current_page_blocks: list[ContentBlock] = []
    used_height = 0.0
    current_page_number = starting_page_number

    for block in blocks:
        required_height = block.content_height
        if current_page_blocks:
            required_height += BLOCK_SPACING

        if current_page_blocks and used_height + required_height > usable_height:
            pages.append(current_page_blocks)
            current_page_blocks = []
            used_height = 0.0
            current_page_number += 1
            required_height = block.content_height

        if block.exercise not in exercise_start_pages:
            exercise_start_pages[block.exercise] = current_page_number

        current_page_blocks.append(block)
        used_height += required_height

    if current_page_blocks:
        pages.append(current_page_blocks)

    return pages, exercise_start_pages


def compute_toc_page_count(section_count: int, margin: int, toc_columns: int) -> int:
    usable_height = PAGE_HEIGHT - margin * 2 - FOOTER_HEIGHT - TOC_TITLE_FONT_SIZE - TOC_TITLE_GAP
    rows_per_column = max(int(usable_height // TOC_LINE_HEIGHT), 1)
    entries_per_page = max(rows_per_column * toc_columns, 1)
    return max((section_count + entries_per_page - 1) // entries_per_page, 1)


def build_contents_entries(
    sections: list[ExerciseSection],
    exercise_start_pages: dict[str, int],
) -> list[tuple[str, int, str]]:
    return [
        (section.exercise, exercise_start_pages[section.exercise], f"exercise-{section.exercise}")
        for section in sections
    ]


def draw_page_number(pdf: canvas.Canvas, page_number: int) -> None:
    text = str(page_number)
    pdf.setFillColor(black)
    pdf.setFont(FOOTER_FONT_NAME, FOOTER_FONT_SIZE)
    text_width = pdf.stringWidth(text, FOOTER_FONT_NAME, FOOTER_FONT_SIZE)
    pdf.drawString((PAGE_WIDTH - text_width) / 2, DEFAULT_MARGIN / 2, text)


def draw_contents_pages(
    pdf: canvas.Canvas,
    entries: list[tuple[str, int, str]],
    toc_title: str,
    toc_columns: int,
    margin: int,
) -> int:
    usable_height = PAGE_HEIGHT - margin * 2 - FOOTER_HEIGHT - TOC_TITLE_FONT_SIZE - TOC_TITLE_GAP
    rows_per_column = max(int(usable_height // TOC_LINE_HEIGHT), 1)
    entries_per_page = max(rows_per_column * toc_columns, 1)
    column_width = (PAGE_WIDTH - margin * 2 - TOC_COLUMN_GAP * (toc_columns - 1)) / toc_columns

    page_number = 1
    for page_start in range(0, len(entries), entries_per_page):
        chunk = entries[page_start : page_start + entries_per_page]
        pdf.setPageSize((PAGE_WIDTH, PAGE_HEIGHT))
        pdf.setFillColor(white)
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        pdf.setFillColor(black)

        title = toc_title if page_number == 1 else f"{toc_title} ({page_number})"
        pdf.setFont(TOC_TITLE_FONT_NAME, TOC_TITLE_FONT_SIZE)
        pdf.drawString(margin, PAGE_HEIGHT - margin - TOC_TITLE_FONT_SIZE, title)

        pdf.setFont(TOC_ENTRY_FONT_NAME, TOC_ENTRY_FONT_SIZE)
        top_y = PAGE_HEIGHT - margin - TOC_TITLE_FONT_SIZE - TOC_TITLE_GAP

        for index, (exercise, target_page, bookmark_name) in enumerate(chunk):
            column_index = index // rows_per_column
            row_index = index % rows_per_column
            x = margin + column_index * (column_width + TOC_COLUMN_GAP)
            y = top_y - row_index * TOC_LINE_HEIGHT

            left_text = f"{exercise}"
            right_text = str(target_page)
            pdf.drawString(x, y, left_text)
            right_width = pdf.stringWidth(right_text, TOC_ENTRY_FONT_NAME, TOC_ENTRY_FONT_SIZE)
            pdf.drawString(x + column_width - right_width, y, right_text)

            pdf.linkRect(
                "",
                bookmark_name,
                (x, y - 3, x + column_width, y + TOC_ENTRY_FONT_SIZE + 2),
                relative=0,
                thickness=0,
            )

        draw_page_number(pdf, page_number)
        pdf.showPage()
        page_number += 1

    return page_number - 1


def render_image_to_rgb(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)

        if img.mode in ("RGBA", "LA") or "transparency" in img.info:
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background

        return img.convert("RGB")


def draw_content_pages(
    pdf: canvas.Canvas,
    pages: list[list[ContentBlock]],
    starting_page_number: int,
    margin: int,
) -> None:
    for page_offset, blocks in enumerate(pages):
        page_number = starting_page_number + page_offset
        pdf.setPageSize((PAGE_WIDTH, PAGE_HEIGHT))
        pdf.setFillColor(white)
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

        current_top = PAGE_HEIGHT - margin
        for index, block in enumerate(blocks):
            if index > 0:
                current_top -= BLOCK_SPACING

            if block.show_header:
                header_text = f"Exercise {block.exercise}"
                pdf.bookmarkPage(block.bookmark_name)
                pdf.addOutlineEntry(header_text, block.bookmark_name, level=0)
                pdf.setFillColor(black)
                pdf.setFont(HEADER_FONT_NAME, HEADER_FONT_SIZE)
                pdf.drawString(margin, current_top - HEADER_FONT_SIZE, header_text)
                current_top -= HEADER_FONT_SIZE + HEADER_SPACING

            if block.image_path is None:
                continue

            image_y = current_top - block.draw_height
            with render_image_to_rgb(block.image_path) as rendered:
                pdf.drawImage(
                    ImageReader(rendered),
                    (PAGE_WIDTH - block.draw_width) / 2,
                    image_y,
                    width=block.draw_width,
                    height=block.draw_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            current_top = image_y

        draw_page_number(pdf, page_number)
        pdf.showPage()


def build_pdf(
    sections: list[ExerciseSection],
    output_pdf: Path,
    margin: int,
    toc_title: str,
    toc_columns: int,
) -> None:
    if not sections:
        raise ValueError("No exercise folders with supported image files found.")

    blocks = build_content_blocks(sections, margin)
    toc_page_count = compute_toc_page_count(len(sections), margin, toc_columns)
    content_pages, exercise_start_pages = paginate_content(
        blocks,
        margin,
        starting_page_number=toc_page_count + 1,
    )
    contents_entries = build_contents_entries(sections, exercise_start_pages)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pageCompression=1)

    actual_toc_pages = draw_contents_pages(
        pdf,
        contents_entries,
        toc_title=toc_title,
        toc_columns=toc_columns,
        margin=margin,
    )

    if actual_toc_pages != toc_page_count:
        raise ValueError("Contents pagination changed unexpectedly. Re-run layout logic.")

    draw_content_pages(
        pdf,
        content_pages,
        starting_page_number=toc_page_count + 1,
        margin=margin,
    )

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

    if args.toc_columns <= 0:
        print("Error: toc-columns must be greater than zero.", file=sys.stderr)
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
            toc_columns=args.toc_columns,
        )
        return 0
    except Exception as exc:
        print(f"Error while creating PDF: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
