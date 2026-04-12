#!/usr/bin/env python3
"""
images_to_pdf.py

Convert HEIC and other image files from a directory into a single PDF.
Files are sorted lexicographically by filename.

Supported formats:
    .heic, .heif, .jpg, .jpeg, .png, .bmp, .tif, .tiff, .webp

Requirements:
    pip install pillow pillow-heif

Usage:
    python images_to_pdf.py "C:/path/to/images" output.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

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
        description="Convert HEIC and other images from a directory into a PDF."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing images",
    )
    parser.add_argument(
        "output_pdf",
        type=Path,
        help="Output PDF file path",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search for images recursively in subdirectories",
    )
    return parser.parse_args()


def find_images(input_dir: Path, recursive: bool) -> List[Path]:
    if recursive:
        files = [p for p in input_dir.rglob("*") if p.is_file()]
    else:
        files = [p for p in input_dir.iterdir() if p.is_file()]

    images = [p for p in files if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    images.sort(key=lambda p: p.name)  # lexicographical sort by filename
    return images


def to_pdf_ready_image(path: Path) -> Image.Image:
    """
    Open an image and convert it into a PDF-safe RGB PIL image.
    Handles EXIF rotation and alpha transparency.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)

        # Convert palette / grayscale / alpha images safely to RGB
        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha_source = img.convert("RGBA")
            background.paste(alpha_source, mask=alpha_source.getchannel("A"))
            return background
        else:
            return img.convert("RGB")


def build_pdf(image_paths: Iterable[Path], output_pdf: Path) -> None:
    prepared_images: List[Image.Image] = []

    try:
        for path in image_paths:
            print(f"Adding: {path}")
            prepared_images.append(to_pdf_ready_image(path))

        if not prepared_images:
            raise ValueError("No supported image files found.")

        first, rest = prepared_images[0], prepared_images[1:]

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        # Pillow's PDF writer uses the JPEG encoder internally for RGB pages.
        # With HEIC-only input, that encoder may not be registered yet.
        Image.init()
        first.save(output_pdf, save_all=True, append_images=rest)
        print(f"\nPDF created: {output_pdf}")

    finally:
        for img in prepared_images:
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

    image_paths = find_images(input_dir, recursive=args.recursive)

    if not image_paths:
        print("Error: no supported image files found.", file=sys.stderr)
        return 1

    print("Files to include (lexicographical order):")
    for p in image_paths:
        print(f"  {p.name}")

    try:
        build_pdf(image_paths, output_pdf)
        return 0
    except Exception as exc:
        print(f"Error while creating PDF: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
