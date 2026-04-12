# Readme

---

## Reshak scrapper

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```sh
pip install requests beautifulsoup4
python src/reshakk_images.py 702
python src/reshakk_images.py --start 700 --end 1132
```

Each exercise folder starts with a generated `01.png` title image containing the exercise number. Downloaded page images are saved after that starting from `02.*`.

---

## Images to pdf

```sh
py images_to_pdf.py "images" "album.pdf"
```

