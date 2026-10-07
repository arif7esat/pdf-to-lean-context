# Usage guide

## Required packages

```
pip install pymupdf pymupdf4llm pillow numpy reportlab
```

## Steps

1. **Package:** In Colab run `kitap_paketle.py` and give the Drive folder link of the book when
   asked.
2. **Download:** Download the generated chapter folder to your computer.
3. **Translate:** Tell the LLM agent (Codex etc.): "Apply the task in TALIMAT.md from start to
   finish".
4. **Check and PDF:** In the chapter folder run `python3 calisma_pdf.py .`. If there is a ⚠
   warning, have the LLM fix only those pages and run the command again.
5. **Figure problems:** If you suspect a problem with figures, run `sekil_cikar.py`; to update
   the figures of an already translated chapter use `--guncelle`.
