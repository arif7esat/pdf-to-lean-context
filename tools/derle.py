"""Gömülü kopyaları yeniden üretir. Kaynak dosyalardan birini değiştirdikten sonra çalıştır:

    python3 tools/derle.py

- src/calisma_pdf.py   → src/kitap_paketle.py ve src/calisma_pdf_colab.py içine gömülür
                             (Colab'de tek hücre olarak çalışabilsinler ve her bölüm klasörüne kopyalanabilsin diye)
- src/kitap_paketle.py → src/sekil_cikar_govde.py şablonuna gömülür → src/sekil_cikar.py
                             (şekil bulma/kırpma kodunun TEK kaynağı kitap_paketle'dir)
"""
import base64
import os
import re
import textwrap
import zlib

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def blob(yol):
    veri = base64.b64encode(zlib.compress(open(yol, "rb").read(), 9)).decode()
    return "\n".join(textwrap.wrap(veri, 100))


def gom(hedef, degisken, kaynak):
    s = open(hedef, encoding="utf-8").read()
    yeni = re.sub(rf'{degisken} = """\n.*?\n"""', lambda m: f'{degisken} = """\n{blob(kaynak)}\n"""', s, flags=re.S)
    if yeni != s:
        open(hedef, "w", encoding="utf-8").write(yeni)
    print(f"✓ {os.path.basename(kaynak)} → {os.path.basename(hedef)}")


k = lambda ad: os.path.join(KOK, ad)
gom(k("kitap_paketle.py"), "CALISMA_PDF_KODU", k("calisma_pdf.py"))
gom(k("calisma_pdf_colab.py"), "CALISMA_PDF_KODU", k("calisma_pdf.py"))
govde = open(k("sekil_cikar_govde.py"), encoding="utf-8").read()
open(k("sekil_cikar.py"), "w", encoding="utf-8").write(govde.replace("__KP_BLOB__", blob(k("kitap_paketle.py"))))
print("✓ kitap_paketle.py → sekil_cikar.py")
