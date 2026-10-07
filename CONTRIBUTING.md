# Contributing

Thanks for your interest in improving pdf-to-lean-context.

## Reporting problems

- Open an issue using the bug report or feature request template.
- For bugs, include the book type, the page, the warning output and the report file.
- **Do not upload copyrighted book pages, figures or translations.** Describe the layout or use
  the synthetic test book in `tests/` instead.

## Making changes

1. Edit the source files in `src/`.
2. Run `python3 tools/derle.py` to regenerate the embedded copies
   (`kitap_paketle.py`, `calisma_pdf_colab.py`, `sekil_cikar.py`).
3. Run the tests:
   ```
   cd tests
   python3 test_kitap_uret.py
   python3 test_kenar_durumlari.py
   python3 ../src/sekil_cikar.py "Test Kitabi.pdf"
   ```
4. If the output of a file changes, bump its version number (`SURUM`) so Colab reprocesses
   chapters, and add an entry to `CHANGELOG.md`.

## Copyrighted content

Never commit book pages, figures or translations. Use only content generated from the
synthetic test book.
