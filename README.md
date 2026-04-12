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
python src/images_to_pdf.py algebra_7_class algebra_7_class.pdf
```

The PDF builder scans subfolders recursively, sorts exercise folders and image files numerically, and centers narrower images on a common page width so different source widths stay aligned.
