#!/usr/bin/env python3
"""
Download images from Reshak exercise pages.

Example:
    python reshakk_images.py 702
    python reshakk_images.py 700 701 702
    python reshakk_images.py --start 700 --end 710

Requirements:
    pip install requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageDraw, ImageFont


BASE_URL = "https://reshak.ru/otvet/reshebniki.php"
DEFAULT_PREDMET = "nikol7"

# Browser-like headers help with sites that dislike default Python requests.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ru,en;q=0.9",
    "Referer": "https://reshak.ru/",
    "Connection": "keep-alive",
}


def build_page_url(exercise: str, predmet: str) -> str:
    return f"{BASE_URL}?otvet={exercise}&predmet={predmet}"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    return name.strip("._") or "image"


def guess_extension_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    _, ext = os.path.splitext(path)
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}:
        return ext
    return ".jpg"


def fetch_html(session: requests.Session, url: str, timeout: int = 30) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def extract_candidate_containers(soup: BeautifulSoup) -> list[Tag]:
    """
    Try common content containers first.
    If none are found, fall back to the full page.
    """
    selectors = [
        "div.otvet",
        "div.answer",
        "div#otvet",
        "div#answer",
        "div.content",
        "main",
        "article",
    ]

    containers: list[Tag] = []
    for selector in selectors:
        containers.extend(soup.select(selector))

    # Deduplicate while preserving order
    seen = set()
    unique: list[Tag] = []
    for tag in containers:
        key = id(tag)
        if key not in seen:
            seen.add(key)
            unique.append(tag)

    if unique:
        return unique

    if soup.body:
        return [soup.body]
    return [soup]


def image_looks_relevant(img: Tag) -> bool:
    """
    Filter obvious junk like icons, logos, counters, etc.
    """
    attrs = " ".join(
        str(img.get(attr, "")) for attr in ("src", "data-src", "alt", "class", "id")
    ).lower()

    junk_keywords = [
        "logo",
        "icon",
        "sprite",
        "counter",
        "banner",
        "yandex",
        "vk",
        "telegram",
        "whatsapp",
        "avatar",
    ]
    if any(word in attrs for word in junk_keywords):
        return False

    width = img.get("width")
    height = img.get("height")
    try:
        if width and int(width) < 40:
            return False
        if height and int(height) < 40:
            return False
    except ValueError:
        pass

    return True


def image_url_is_blocked(url: str) -> bool:
    """
    Skip images that are known placeholders or tags we don't want to download.
    """

    path = urlparse(url).path.lower()
    return "/zapret_pravo.png" in path or "/tag/" in path


def extract_image_urls(page_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    containers = extract_candidate_containers(soup)

    urls: list[str] = []
    seen = set()

    for container in containers:
        for img in container.find_all("img"):
            if not image_looks_relevant(img):
                continue

            src = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("src")
                or img.get("data-original")
            )
            if not src:
                continue

            full_url = urljoin(page_url, src.strip())
            if image_url_is_blocked(full_url):
                continue
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)

    return urls


def download_file(
    session: requests.Session,
    url: str,
    target_path: Path,
    timeout: int = 60,
) -> None:
    with session.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with target_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def build_exercise_title_text(exercise: str) -> str:
    return f"Exercise {exercise}"


def load_title_font(size: int) -> ImageFont.ImageFont:
    for font_name in ("DejaVuSans-Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_exercise_number_image(
    exercise: str,
    target_path: Path,
    width: int = 1200,
    height: int = 630,
) -> None:
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)
    text = build_exercise_title_text(exercise)

    font = None
    for font_size in range(220, 59, -8):
        candidate_font = load_title_font(font_size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=candidate_font)
        text_width = right - left
        text_height = bottom - top
        if text_width <= width - 120 and text_height <= height - 120:
            font = candidate_font
            break

    if font is None:
        font = load_title_font(60)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_width = right - left
        text_height = bottom - top

    x = (width - text_width) / 2 - left
    y = (height - text_height) / 2 - top
    draw.text((x, y), text, fill="black", font=font)
    image.save(target_path, format="PNG")


def save_images_for_exercise(
    session: requests.Session,
    exercise: str,
    predmet: str,
    output_root: Path,
    delay: float = 1.0,
) -> None:
    page_url = build_page_url(exercise, predmet)
    exercise_dir = output_root / str(exercise)
    exercise_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[INFO] Exercise {exercise}")
    print(f"[INFO] Page: {page_url}")

    try:
        html = fetch_html(session, page_url)
    except requests.HTTPError as e:
        print(f"[ERROR] Failed to fetch page: {e}")
        return
    except requests.RequestException as e:
        print(f"[ERROR] Network error: {e}")
        return

    image_urls = extract_image_urls(page_url, html)
    title_image_path = exercise_dir / "01.png"

    try:
        generate_exercise_number_image(exercise, title_image_path)
        print(f"[OK] {title_image_path} <- generated exercise title image")
    except OSError as e:
        print(f"[ERROR] Failed to generate title image for {exercise}: {e}")
        return

    if not image_urls:
        print("[WARN] No images found on page.")
        return

    print(f"[INFO] Found {len(image_urls)} image(s).")

    for index, image_url in enumerate(image_urls, start=2):
        ext = guess_extension_from_url(image_url)
        filename = f"{index:02d}{ext}"
        target_path = exercise_dir / sanitize_filename(filename)

        try:
            download_file(session, image_url, target_path)
            print(f"[OK] {target_path} <- {image_url}")
            time.sleep(delay)
        except requests.RequestException as e:
            print(f"[ERROR] Failed to download {image_url}: {e}")


def parse_exercises(args: argparse.Namespace) -> list[str]:
    exercises: list[str] = []

    if args.exercises:
        exercises.extend(args.exercises)

    if args.start is not None and args.end is not None:
        step = 1 if args.end >= args.start else -1
        exercises.extend(str(x) for x in range(args.start, args.end + step, step))

    # Deduplicate while preserving order
    seen = set()
    result = []
    for item in exercises:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download images from Reshak exercise pages."
    )
    parser.add_argument(
        "exercises",
        nargs="*",
        help="Exercise numbers, e.g. 702 703 704",
    )
    parser.add_argument("--start", type=int, help="Start exercise number")
    parser.add_argument("--end", type=int, help="End exercise number")
    parser.add_argument(
        "--predmet",
        default=DEFAULT_PREDMET,
        help=f"Predmet code, default: {DEFAULT_PREDMET}",
    )
    parser.add_argument(
        "--out",
        default="reshak_images",
        help="Output folder, default: reshak_images",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between image downloads in seconds, default: 1.0",
    )

    args = parser.parse_args()
    exercise_numbers = parse_exercises(args)

    if not exercise_numbers:
        print("Provide exercise numbers or --start/--end range.", file=sys.stderr)
        return 2

    output_root = Path(args.out)
    output_root.mkdir(parents=True, exist_ok=True)

    session = make_session()

    for exercise in exercise_numbers:
        save_images_for_exercise(
            session=session,
            exercise=exercise,
            predmet=args.predmet,
            output_root=output_root,
            delay=args.delay,
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
