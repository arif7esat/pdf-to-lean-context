# Changelog

All notable changes to this project are documented here, in the style of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

The project turns English textbooks and lecture slides into page-by-page Turkish study
documents. Development was done on Ian Sommerville, *Software Engineering* (8th edition) and
verified on the whole book (865 pages, 32 chapters + glossary, 432 figures).

> Note: the repository only contains the latest versions plus two intermediate snapshots
> (v3.2, v3.3) as code. Older versions were not kept; what changed in them is documented below.

## kitap_paketle (splits a book into chapters, crops figures, builds LLM chunks and instructions)

### [3.6]
#### Fixed
Tested on a second book with a different layout (Elmasri–Navathe, *Fundamentals of Database Systems*,
6th ed.: captions above or beside figures, multi-part figures, footnotes). There, cropped figures go from
286 to 317 and warnings from 42 to 1. Changes, all as general rules:
- Captions beside a figure and aligned with its bottom edge are matched to the figure.
- Caption lines that continue in a separate text block, "(a) …" and "(continued)" captions are recognised.
- Footnotes at the bottom of the page are never cropped into a figure.
- Multi-part figures ((a), (b), … with wide gaps) are joined, but a distant part is only added when its text
  uses the figure's own fonts, it is not a lone heading line, and it does not belong to the next figure.
- Each caption reserves its nearest figure part, so neighbouring figures are not swallowed.

Sommerville: 431 of 432 figures identical in content; figure 14.16 now includes a part that was
previously missed; 0 warnings.

### [3.5]
#### Fixed
- Captions whose number and title are on separate lines ("Figure 1.1" / "The waterfall model")
  were mistaken for exercise sentences and rejected. Output on the Sommerville book is identical
  (432 figures, 0 warnings); the synthetic test book goes from 0 to 15 figures.

### [3.4]
#### Fixed
- End-of-line hyphens in table cells are preserved ("off-site", previously "offsite").

#### Verified (whole book)
- 32 chapters + glossary with correct boundaries; 432 figures, continuous numbering in every
  chapter, every figure mentioned in the text is cropped, no overlapping crops, 0 warnings.
- All words of the 82 text tables come from inside their own figure; no table is attached to
  two figures.
- Text coverage: all 198,826 words are present in the markdown (remaining differences are due
  to line-end splitting).

### [3.3]
#### Changed
- Speed: Drive upload is parallel (6 channels) and identical files already on Drive are not
  re-uploaded (md5).
- The clustering algorithm went from O(n³) to a sequential scan (same result, verified with 300
  random tests).
- Table search only runs on figures that contain text.
- Chapters are processed in parallel on multiple cores (byte-identical output).

#### Fixed
- The table finder could return the table of a neighbouring figure (6.14, 26.12, 28.2); now only
  a table inside the crop area is accepted.

### [3.2]
#### Changed
- Case icons in the margin column (book, syringe) are removed from the crop, only when safe.
- Captions never appear in the cropped image.

### [3.1]
Whole-book testing fixed:
- The "Part N" line in the table of contents being taken for a page (chapter 1 came out as a
  single page).
- Exercise sentences being taken for captions (exercise text was being deleted).
- Two stacked figures merging into one image.
- Cut-off bottom edge of tables.
- Caption fragments leaking into figure text.
- Rejection of tables with stacked rows.

### [3.0]
#### Added
- Figures with a text table are also provided as a markdown table (except marked matrices).
- Figure processing consolidated in `bolum_sekilleri()` (shared with `sekil_cikar`).

### [2.9]
#### Added
- Two-stage cropping: (1) PDF objects, (2) independent pixel verification (the page is
  rendered, body text and captions are erased, remaining ink regions join the figure; the box
  only grows).
- Warnings: caption without a found figure, figure named in the text but not croppable, drawing
  left outside next to a figure.
- "(continued)" figures get their own file name.

### [2.8]
#### Changed
- Zero-thickness lines (arrows, actor figures, table rules) are no longer discarded.
- The crop box grows to include every overflowing or nearby part belonging to the figure.
- Text falling into the margin is whitened.
- Text inside a figure is added to the prompt as text from the PDF.

### [2.7]
#### Changed
- In Colab every chapter is uploaded to Drive as soon as it finishes.
- The version file is written last (interrupted work is reprocessed).
- LLM answers and study PDFs are never deleted.

### [2.5–2.6]
#### Changed
- `calisma_pdf`: fallback font for missing glyphs (→ ≤ ✓).
- Check that catches use of "wrong:" terms in chunks and at the end of a chapter.
- Term rule hardened in the prompt.

### [2.4]
#### Added
- Quality rules from the earlier chat were folded into the prompt as a "study contract"
  (A • full translation / C • "Now let's understand this", five questions, figure reading,
  labels, tone, chapter-end structure).
- Persistent term list (`TERIMLER`; only terms occurring in the chapter enter the prompt,
  "wrong:" equivalents are flagged).

### [2.3]
#### Fixed
- A custom-font bullet appearing as "I" in the text.
- Hyphens of compound words split at a line end are restored ("service-centric").

### [2.2]
#### Added
- Every chapter in its own folder: clean text with page markers
  (`<!-- PDF p. N · book p. M -->`), `sekiller/`, `parcalar/` (ready prompts of about 1,800
  words plus a chapter-end prompt), `TALIMAT.md` (steps for the LLM agent), embedded
  `calisma_pdf.py`.
- Figures are found from the caption ("Figure 4.1"); figure regions are redacted out of the text.
- Chapter boundaries: PDF bookmarks → printed table of contents + page offset → single chapter.

## sekil_cikar (figures only + visual audit + updating translated chapters)

### [1.6]
#### Fixed
- Embedded `kitap_paketle` v3.6.

### [1.5]
#### Fixed
- Embedded `kitap_paketle` v3.5: captions whose title is on a separate line are accepted.

### [1.1–1.4]
#### Changed
- Embedded `kitap_paketle` updates.
- Given a folder without a translation, it stops without touching anything.
- Finds the right chapter by itself whatever the folder name (including a Codex task folder).

### [1.0]
#### Added
- Extracts all figures of a book with the same code as `kitap_paketle`.
- Per-figure check page (cropped image + red frame on the book page); report.
- `--guncelle`: compares the old figures of a translated chapter (real content differences
  only), replaces them, writes `SEKIL_DUZELT.md`.

## calisma_pdf / calisma_pdf_colab

- Checks LLM answers (is every source page present, are sections A and C present, is the
  translation summarised, are figure links preserved, are forbidden terms used) and produces the
  Turkish study PDF (bookmarks, tables, figures).
- `calisma_pdf_colab.py`: the same job in Colab (uploading a zip or from Drive).

## SlaytPaketle

### [1.x → 1.9]
- Turns lecture slides (PPTX/PDF) into a package for the LLM: slide text, images of slides with
  visuals, a visual check mechanism, a quality report (`Slaytlar/Jsonlar`), the same level of
  output for PDF slides, and the Drive API against "too many accesses" errors on Drive downloads.
