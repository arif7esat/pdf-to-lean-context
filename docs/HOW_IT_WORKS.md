# How it works

This page explains how figures are found and cropped, and how the results are checked.
For setup and the day-to-day workflow see [USAGE.md](USAGE.md).

## 1. Text first, LLM second

The chapter text is extracted from the PDF by code, not by the LLM. Page markers
(`<!-- PDF p. N · book p. M -->`) keep every paragraph tied to its source page. Figure
regions are cut out of the text, and the words inside each figure are added back as a short
text note, so the LLM can read labels without guessing from pixels. The LLM only translates and
explains.

## 2. Finding figures

Figures are found from their numbered captions ("Figure 4.1"). Captions may have the number
and the title on separate lines. Exercise sentences that merely mention a figure are not
treated as captions.

## 3. Two-stage cropping

**Stage 1 — PDF objects.** The tool collects the drawings, images and text that belong to the
figure from the PDF itself. Thin lines (arrows, stick figures, table rules) are kept. The box
grows to include every part that overflows or sits close to the figure.

**Stage 2 — pixel verification.** Independently, the page is rendered as an image. Body text and
captions are erased, and any remaining ink next to the figure is added to the box.

The box **only grows**: stage 2 can add missed parts but never cut off what stage 1 found.
Captions are never part of the cropped image, and margin icons are removed only when it is safe.

## 4. Stacked figures

When two figures sit directly on top of each other, they are split into two separate images
instead of one merged picture. A "(continued)" figure gets its own file name.

## 5. Tables

If a figure contains a text table, it is also given as a markdown table. Only a table that lies
inside the figure's crop area is accepted, so a neighbouring figure's table is never attached by
mistake.

## 6. Warnings

The tool prints a warning when it is not sure. There are three kinds:

- **Caption without a figure** — a caption was found but no figure next to it.
- **Mentioned but not cropped** — the text refers to a figure that could not be cropped.
- **Drawing left outside** — there is a drawing next to a figure that is not inside its box.

`sekil_cikar.py` also builds a **figure audit PDF**: every crop next to its book page with a red
frame, so a person can check all figures quickly.

## 7. How it was verified

The full Sommerville *Software Engineering* (8th edition) was processed and checked by audit
scripts (`audit/`):

- 32 chapters + glossary with correct boundaries.
- 432 figures; numbering is continuous in every chapter; every figure mentioned in the text is
  cropped; no two crops overlap; 0 warnings.
- 82 text tables; every word comes from inside its own figure; no table is attached to two
  figures.
- Text coverage: all 198,826 words of the book appear in the markdown.

Performance changes (such as the faster clustering step) were checked to give the same result:
300 random tests, and byte-identical output when chapters run in parallel.

A synthetic test book in `tests/` is checked on every push by CI (15 figures expected).
