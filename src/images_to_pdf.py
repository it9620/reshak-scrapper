#!/usr/bin/env python3
"""
images_to_pdf.py

Convert images from a directory tree into a single PDF.
This is intended for folders like `algebra_7_class/<exercise>/<image files>`,
where exercises and image files should be ordered numerically when possible.

Supported formats:
    .heic, .heif, .jpg, .jpeg, .png, .bmp, .tif, .tiff, .webp

Requirements:
    pip install pillow pillow-heif

Usage:
    python src/images_to_pdf.py algebra_7_class algebra_7_class.pdf
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert images from a directory tree into a PDF."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Root directory containing exercise folders and images",
    )
    parser.add_argument(
        "output_pdf",
        type=Path,
        help="Output PDF file path",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=24,
        help="White margin around each image in pixels, default: 24",
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


def find_images(input_dir: Path) -> list[Path]:
    files = [p for p in input_dir.rglob("*") if p.is_file()]
    images = [p for p in files if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    images.sort(key=lambda path: path_sort_key(path.relative_to(input_dir)))
    return images


def to_pdf_ready_image(path: Path) -> Image.Image:
    """
    Open an image and convert it into a PDF-safe RGB PIL image.
    Handles EXIF rotation and alpha transparency.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)

        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha_source = img.convert("RGBA")
            background.paste(alpha_source, mask=alpha_source.getchannel("A"))
            return background

        return img.convert("RGB")


def compute_canvas_width(images: Iterable[Image.Image], margin: int) -> int:
    max_width = max(image.width for image in images)
    return max_width + margin * 2


def build_pdf_page(image: Image.Image, canvas_width: int, margin: int) -> Image.Image:
    available_width = max(canvas_width - margin * 2, 1)

    if image.width > available_width:
        scale = available_width / image.width
        resized_width = available_width
        resized_height = max(int(round(image.height * scale)), 1)
        image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    else:
        image = image.copy()

    page_height = image.height + margin * 2
    page = Image.new("RGB", (canvas_width, page_height), "white")
    x = (canvas_width - image.width) // 2
    page.paste(image, (x, margin))
    image.close()
    return page


def build_pdf(image_paths: Iterable[Path], output_pdf: Path, margin: int) -> None:
    prepared_images: list[Image.Image] = []
    pdf_pages: list[Image.Image] = []

    try:
        for path in image_paths:
            print(f"Adding: {path}")
            prepared_images.append(to_pdf_ready_image(path))

        if not prepared_images:
            raise ValueError("No supported image files found.")

        canvas_width = compute_canvas_width(prepared_images, margin)

        for image in prepared_images:
            pdf_pages.append(build_pdf_page(image, canvas_width, margin))

        first, rest = pdf_pages[0], pdf_pages[1:]

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        Image.init()
        first.save(output_pdf, save_all=True, append_images=rest)
        print(f"\nPDF created: {output_pdf}")

    finally:
        for img in prepared_images:
            try:
                img.close()
            except Exception:
                pass
        for img in pdf_pages:
            try:
                img.close()
            except Exception:
                pass


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

    image_paths = find_images(input_dir)

    if not image_paths:
        print("Error: no supported image files found.", file=sys.stderr)
        return 1

    print("Files to include:")
    for path in image_paths:
        print(f"  {path.relative_to(input_dir)}")

    try:
        build_pdf(image_paths, output_pdf, margin=args.margin)
        return 0
    except Exception as exc:
        print(f"Error while creating PDF: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
