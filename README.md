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

# geometry atanasian
python src/reshakk_images.py --start 1 --end 1431 \
  --page-url https://reshak.ru/otvet/otvet11.php \
  --exercise-param otvet1 \
  --predmet ""

python src/reshakk_images.py --start 1 --end 1431 \
  --page-url https://reshak.ru/otvet/otvet11.php \
  --exercise-param otvet1 \
  --predmet "atan10_11"

# algebra nikilskiy 8
python src/reshakk_images.py --start 1 --end 997 \
  --page-url https://reshak.ru/otvet/reshebniki.php \
  --exercise-param otvet \
  --predmet "nikol8"

# geometry atanasian 10-11 with otvet=new/{exercise}
python src/reshakk_images.py --start 1 --end 870 \
  --page-url https://reshak.ru/otvet/reshebniki.php \
  --exercise-param otvet \
  --exercise-value-template "new/{exercise}" \
  --predmet "atan10_11"
```
https://reshak.ru/otvet/reshebniki.php?otvet=1&predmet=nikol7
https://reshak.ru/otvet/reshebniki.php?otvet=2&predmet=nikol8
https://reshak.ru/otvet/otvet11.php?otvet1=1
https://reshak.ru/otvet/reshebniki.php?otvet=new/870&predmet=atan10_11

Each exercise folder starts with a generated `01.png` title image containing the exercise number. Downloaded page images are saved after that starting from `02.*`.
The downloader supports the default Reshak format `reshebniki.php?otvet=...&predmet=...`, alternate formats like `otvet11.php?otvet1=...`, and prefixed exercise values like `reshebniki.php?otvet=new/852&predmet=atan10_11` via `--page-url`, `--exercise-param`, and `--exercise-value-template`.

---

## Images to pdf

```sh
python src/images_to_pdf.py algebra_7_class algebra_7_class.pdf
python src/images_to_pdf.py reshak_images algebra_8_class.pdf
```

The PDF builder reads immediate exercise subfolders, skips the first generated image in each folder, inserts a small `Exercise 700` header above the first real image of that exercise, generates compact clickable contents pages at the beginning, packs multiple images onto each page when they fit, and prints the page number at the bottom of every page.
