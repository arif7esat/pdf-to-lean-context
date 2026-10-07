# -*- coding: utf-8 -*-
"""
calisma_pdf.py — LLM cevaplarını kontrol eder ve Türkçe çalışma PDF'ini üretir.
(build_chapter*.py, ch4/build.py, qa.py, refine.py … betiklerinin yerine tek araç.)

KULLANIM
    python3 calisma_pdf.py "<kitap>_Bolumler/04_Software_processes"      (bölüm klasörü)

Klasörde parca-01.md (kaynak + prompt) ve parca-01-cevap.md (LLM cevabı) çiftleri olmalı.
Klasör yapısı: <bölüm>/parcalar/ (parca-NN.md + parca-NN-cevap.md) ve <bölüm>/sekiller/. Görseller dosya
adına göre bulunur; cevaptaki yol ne olursa olsun.

ÇIKTI (bölüm klasörünün içine)
    04_Software_processes_calisma.pdf   ← çalışma dokümanı (her kaynak sayfa yeni sayfada, yer imli)
    04_Software_processes_calisma.md    ← birleşik metin
    04_Software_processes_kontrol.md    ← kontrol raporu

KONTROLLER (kaynakla karşılaştırma; LLM'in kendi beyanına güvenilmez)
    - Kaynaktaki her sayfa (PDF s. N) cevapta başlık olarak var mı?
    - Her sayfada "A • Tam çeviri" ve "C • Şimdi bunu anlayalım" var mı?
    - A bölümünün uzunluğu kaynak sayfaya göre çok kısa mı? (sessiz özetleme belirtisi)
    - Kaynak sayfadaki her şekil cevapta (aynı sayfada) var mı?

Gerekli: pip3 install reportlab pillow
"""
import html
import os
import re
import sys

OZET_ESIGI = 0.55          # A bölümü kelime sayısı / kaynak sayfa kelime sayısı bunun altındaysa uyarı
A_BASLIK = re.compile(r"^##\s*A\b", re.M)
C_BASLIK = re.compile(r"^##\s*C\b", re.M)
SAYFA_ISARETI = re.compile(r"<!-- PDF s\. (\d+)(?: · kitap s\. (\d+))? -->")
GORSEL = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def kelime_say(t):
    t = GORSEL.sub("", t)
    t = re.sub(r"<!--.*?-->|^#+.*$|^\|?[-:| ]+\|?$", "", t, flags=re.M)
    return len(re.findall(r"\w+", t))


# ──────────────────────────────────────────────────────────────────────────────
# Kontrol
# ──────────────────────────────────────────────────────────────────────────────

def kaynak_sayfalari(parca_md):
    """parca-NN.md → {pdf_sayfa: (kitap_sayfa, metin)} (prompt kısmı atılır)."""
    metin = parca_md.split("=== KAYNAK METİN ===", 1)[-1]
    sonuc, isaretler = {}, list(SAYFA_ISARETI.finditer(metin))
    for i, m in enumerate(isaretler):
        son = isaretler[i + 1].start() if i + 1 < len(isaretler) else len(metin)
        sonuc[int(m.group(1))] = (m.group(2), metin[m.end():son])
    return sonuc


def cevap_sayfalari(cevap):
    """Cevabı '# ' başlıklarından bloklara böler; içinde 'PDF s. N' geçen ilk satıra göre sayfaya atar
    (hem '# PDF s. 4 …' hem '# Kitap s. 66 • … / Kaynak: PDF s. 4 …' biçimi) → {pdf_sayfa: metin}."""
    sonuc = {}
    basliklar = list(re.finditer(r"^#\s.*$", cevap, re.M))
    for i, m in enumerate(basliklar):
        son = basliklar[i + 1].start() if i + 1 < len(basliklar) else len(cevap)
        blok = cevap[m.start():son]
        s = re.search(r"PDF s\.\s*(\d+)", blok[:400])
        if s:
            sonuc.setdefault(int(s.group(1)), "")
            sonuc[int(s.group(1))] += blok
    return sonuc


def terim_kontrol(talimat, sayfalar):
    """Kalıcı terim listesinde "yanlış:" diye işaretlenmiş karşılıklar kullanılmış mı? sayfalar: {no: metin}"""
    sorunlar = []
    talimat = talimat.split("=== KAYNAK METİN ===")[0]
    for en, tr in re.findall(r"(?m)^- (.+?) → (.+)$", talimat):
        for yanlis in re.findall(r"yanlış: ([^;)]+)", tr):
            desen = re.compile(r"(?<!\w)" + re.escape(yanlis.strip()), re.I)
            yerler = [n for n, c in sayfalar.items() if desen.search(c)]
            if yerler:
                sorunlar.append((yerler[0], f"terim: '{yanlis.strip()}' kullanılmış, doğrusu '{tr.split(' (')[0]}' ({en}) → "
                                            + ", ".join(f"PDF s. {n}" if n != "son" else "son" for n in yerler)))
    return sorunlar


def kontrol_et(kaynak, cevap):
    """Bir parça için sorun listesi döndürür: [(pdf_sayfa, açıklama)]."""
    sorunlar = []
    ks, cs = kaynak_sayfalari(kaynak), cevap_sayfalari(cevap)
    for no, (kitap, metin) in ks.items():
        etiket = f"PDF s. {no}" + (f" (kitap s. {kitap})" if kitap else "")
        if no not in cs:
            sorunlar.append((no, f"{etiket}: cevapta bu sayfa YOK"))
            continue
        c = cs[no]
        if not A_BASLIK.search(c):
            sorunlar.append((no, f"{etiket}: 'A • Tam çeviri' bölümü yok"))
        if not C_BASLIK.search(c):
            sorunlar.append((no, f"{etiket}: 'C • Şimdi bunu anlayalım' bölümü yok"))
        a = A_BASLIK.search(c)
        if a:
            cm = C_BASLIK.search(c, a.end())
            a_metin = c[a.end(): cm.start() if cm else len(c)]
            kaynak_k, a_k = kelime_say(metin), kelime_say(a_metin)
            if kaynak_k >= 40 and a_k < OZET_ESIGI * kaynak_k:
                sorunlar.append((no, f"{etiket}: çeviri kısa ({a_k} kelime / kaynak {kaynak_k}) — özetlenmiş olabilir"))
        for _, yol in GORSEL.findall(metin):
            if os.path.basename(yol) not in c:
                sorunlar.append((no, f"{etiket}: şekil eksik → {os.path.basename(yol)}"))
    sorunlar += terim_kontrol(kaynak, cs)
    fazla = sorted(set(cs) - set(ks))
    if fazla:
        sorunlar.append((None, "kaynakta olmayan sayfa başlıkları: " + ", ".join(f"PDF s. {n}" for n in fazla)))
    return sorunlar


# ──────────────────────────────────────────────────────────────────────────────
# PDF
# ──────────────────────────────────────────────────────────────────────────────

def fontlari_kaydet():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    adaylar = [
        ("/System/Library/Fonts/Supplemental/Verdana.ttf", "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
         "/System/Library/Fonts/Supplemental/Verdana Italic.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ]
    try:                                        # matplotlib DejaVu'yu her yerde (Colab dahil) taşır
        import matplotlib
        k = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        adaylar.append((f"{k}/DejaVuSans.ttf", f"{k}/DejaVuSans-Bold.ttf", f"{k}/DejaVuSans-Oblique.ttf"))
    except Exception:
        pass
    for normal, kalin, egik in adaylar:
        if all(os.path.exists(x) for x in (normal, kalin, egik)):
            for ad, yol in (("F", normal), ("FB", kalin), ("FI", egik)):
                pdfmetrics.registerFont(TTFont(ad, yol))
            pdfmetrics.registerFontFamily("F", normal="F", bold="FB", italic="FI", boldItalic="FB")
            KARAKTERLER["F"] = set(pdfmetrics.getFont("F").face.charToGlyph)
            # Ana yazı tipinde olmayan işaretler (→, ≤, ✓ …) için yedek yazı tipi
            for yedek in [a[0] for a in adaylar[1:]] + ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                                                        "/Library/Fonts/Arial Unicode.ttf"]:
                if os.path.exists(yedek) and yedek != normal:
                    try:
                        pdfmetrics.registerFont(TTFont("FY", yedek))
                        KARAKTERLER["FY"] = set(pdfmetrics.getFont("FY").face.charToGlyph)
                        break
                    except Exception:
                        pass
            return
    raise SystemExit("Türkçe karakterleri basabilen bir TTF yazı tipi bulunamadı (Verdana ya da DejaVu Sans).")


KARAKTERLER = {}
ASCII_KARSILIK = {"→": "->", "←": "<-", "↔": "<->", "⇒": "=>", "⇐": "<=", "⇔": "<=>", "↑": "^", "↓": "v",
                  "≤": "<=", "≥": ">=", "≠": "!=", "≈": "~", "✓": "+", "✔": "+", "✗": "x", "✘": "x", "×": "x"}


def _isaretleri_duzelt(t):
    """Ana yazı tipinde glifi olmayan karakterleri yedek yazı tipiyle ya da ASCII karşılığıyla basar
    (yoksa PDF'te boş kutu ☐ çıkar)."""
    ana = KARAKTERLER.get("F")
    if not ana:
        return t
    cikti = []
    for ch in t:
        if ord(ch) < 0x2000 or ord(ch) in ana or ch in "\n":
            cikti.append(ch)
        elif ord(ch) in KARAKTERLER.get("FY", ()):
            cikti.append(f"<font name='FY'>{ch}</font>")
        else:
            cikti.append(ASCII_KARSILIK.get(ch, "?"))
    return "".join(cikti)


def satir_ici(t):
    t = html.escape(t.replace("‑", "-"))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    return _isaretleri_duzelt(t)


def pdf_uret(md, cikis, gorsel_klasoru, baslik):
    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)
    fontlari_kaydet()
    lacivert, camgobegi, gri = colors.HexColor("#193348"), colors.HexColor("#007E87"), colors.HexColor("#526271")
    st = {
        "h1": ParagraphStyle("h1", fontName="FB", fontSize=15, leading=20, textColor=lacivert, spaceAfter=9, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="FB", fontSize=12, leading=16, textColor=camgobegi, spaceBefore=6, spaceAfter=7, keepWithNext=True),
        "h3": ParagraphStyle("h3", fontName="FB", fontSize=10.5, leading=14, textColor=gri, spaceAfter=6, keepWithNext=True),
        "p": ParagraphStyle("p", fontName="F", fontSize=10, leading=14.2, textColor=lacivert, spaceAfter=7),
        "madde": ParagraphStyle("madde", fontName="F", fontSize=10, leading=14.2, textColor=lacivert, spaceAfter=5, leftIndent=12, firstLineIndent=-9),
        "alinti": ParagraphStyle("alinti", fontName="FI", fontSize=9.5, leading=13.5, textColor=gri, spaceAfter=7, leftIndent=12),
        "alt": ParagraphStyle("alt", fontName="FI", fontSize=8, leading=11, textColor=gri, spaceAfter=8),
        "hucre": ParagraphStyle("hucre", fontName="F", fontSize=8.5, leading=12, textColor=lacivert),
        "bhucre": ParagraphStyle("bhucre", fontName="FB", fontSize=8.5, leading=12, textColor=colors.white),
    }

    class Belge(SimpleDocTemplate):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.guncel = baslik

        def afterFlowable(self, f):
            if isinstance(f, Paragraph) and f.style.name == "h1":
                self.guncel = f.getPlainText()
                anahtar = f"b{id(f)}"
                self.canv.bookmarkPage(anahtar)
                self.canv.addOutlineEntry(self.guncel[:90], anahtar, level=0, closed=False)

        def afterPage(self):
            c = self.canv
            c.saveState()
            w, _ = self.pagesize
            c.setStrokeColor(colors.HexColor("#C9DADF"))
            c.line(40, 38, w - 40, 38)
            c.setFont("F", 7)
            c.setFillColor(gri)
            c.drawString(40, 26, self.guncel[:95])
            c.drawRightString(w - 40, 26, str(self.page))
            c.restoreState()

    GEN = 595.28 - 80
    hikaye, eksik_gorsel = [], []
    bloklar = [b for b in re.split(r"^\s*---PAGE---\s*$", md, flags=re.M) if b.strip()]
    for bi, blok in enumerate(bloklar):
        if bi:
            hikaye.append(PageBreak())
        satirlar = blok.strip().splitlines()
        i = 0
        while i < len(satirlar):
            s = satirlar[i].strip()
            if not s or s.startswith("<!--"):
                i += 1
                continue
            m = GORSEL.match(s)
            if m:
                yol = os.path.join(gorsel_klasoru, os.path.basename(m.group(2)))
                if os.path.exists(yol):
                    w, h = PILImage.open(yol).size
                    olcek = min(GEN / w, 300 / h, 1.0 if w < 300 else 9)
                    hikaye.append(KeepTogether([Image(yol, width=w * olcek, height=h * olcek), Spacer(1, 3),
                                                Paragraph(satir_ici(m.group(1)) + " • Kaynak: kitap", st["alt"])]))
                else:
                    eksik_gorsel.append(os.path.basename(m.group(2)))
                    hikaye.append(Paragraph(f"[Görsel bulunamadı: {html.escape(m.group(2))}]", st["alt"]))
                i += 1
                continue
            if s.startswith("|"):
                satir_listesi = []
                while i < len(satirlar) and satirlar[i].strip().startswith("|"):
                    hucreler = [v.strip() for v in satirlar[i].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r":?-{2,}:?", v) for v in hucreler if v):
                        satir_listesi.append(hucreler)
                    i += 1
                n = max(len(r) for r in satir_listesi)
                satir_listesi = [r + [""] * (n - len(r)) for r in satir_listesi]
                uzunluk = [max(8, min(60, max(len(r[k]) for r in satir_listesi))) for k in range(n)]
                genislik = [GEN * u / sum(uzunluk) for u in uzunluk]
                veri = [[Paragraph(satir_ici(v), st["bhucre" if ri == 0 else "hucre"]) for v in r]
                        for ri, r in enumerate(satir_listesi)]
                tablo = Table(veri, colWidths=genislik, repeatRows=1, hAlign="LEFT")
                tablo.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), camgobegi), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F0F6F7"), colors.white]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6E3E7"))]))
                hikaye.extend([tablo, Spacer(1, 8)])
                continue
            if re.match(r"^#{3,6}\s", s):
                hikaye.append(Paragraph(satir_ici(s.lstrip("#").strip()), st["h3"]))
            elif s.startswith("## "):
                hikaye.append(Paragraph(satir_ici(s[3:]), st["h2"]))
            elif s.startswith("# "):
                hikaye.append(Paragraph(satir_ici(s[2:]), st["h1"]))
            elif re.match(r"^[-*•]\s", s):
                hikaye.append(Paragraph("• " + satir_ici(s[2:]), st["madde"]))
            elif re.match(r"^\d+[.)]\s", s):
                hikaye.append(Paragraph(satir_ici(s), st["madde"]))
            elif s.startswith(">"):
                hikaye.append(Paragraph(satir_ici(s.lstrip("> ")), st["alinti"]))
            else:
                hikaye.append(Paragraph(satir_ici(s), st["p"]))
            i += 1
    belge = Belge(cikis, pagesize=(595.28, 841.89), leftMargin=40, rightMargin=40, topMargin=35, bottomMargin=49,
                  title=baslik, author="Türkçe çalışma dokümanı")
    belge.build(hikaye)
    return eksik_gorsel


# ──────────────────────────────────────────────────────────────────────────────
# Ana akış
# ──────────────────────────────────────────────────────────────────────────────

def calistir(parca_klasoru):
    yol = os.path.abspath(parca_klasoru.rstrip("/"))
    bolum_klasoru = os.path.dirname(yol) if os.path.basename(yol) == "parcalar" else yol
    parca_klasoru = os.path.join(bolum_klasoru, "parcalar")
    if not os.path.isdir(parca_klasoru):
        raise SystemExit("Bölüm klasörünü ver (içinde 'parcalar' klasörü olmalı).")
    bolum = os.path.join(bolum_klasoru, os.path.basename(bolum_klasoru))
    gorsel_klasoru = os.path.join(bolum_klasoru, "sekiller")
    kaynaklar = sorted(f for f in os.listdir(parca_klasoru) if re.fullmatch(r"parca-\d+\.md", f))
    if not kaynaklar:
        raise SystemExit("Klasörde parca-NN.md dosyası yok.")
    rapor, cevaplar, toplam_sorun = [f"# Kontrol raporu — {os.path.basename(bolum)}", ""], [], 0
    for kf in kaynaklar:
        cf = kf.replace(".md", "-cevap.md")
        kaynak = open(os.path.join(parca_klasoru, kf), encoding="utf-8").read()
        if not os.path.exists(os.path.join(parca_klasoru, cf)):
            rapor.append(f"- ⛔ **{kf}**: cevap dosyası yok ({cf}) — bu parça PDF'e girmedi")
            toplam_sorun += 1
            continue
        cevap = open(os.path.join(parca_klasoru, cf), encoding="utf-8").read()
        sorunlar = kontrol_et(kaynak, cevap)
        toplam_sorun += len(sorunlar)
        if sorunlar:
            rapor.append(f"- ⚠ **{kf}**: {len(sorunlar)} sorun")
            rapor += [f"    - {a}" for _, a in sorunlar]
        else:
            rapor.append(f"- ✓ **{kf}**: tüm sayfalar, A/C bölümleri ve şekiller tamam")
        cevaplar.append(cevap.strip())
    son = os.path.join(parca_klasoru, "parca-son-cevap.md")
    if os.path.exists(son):
        son_metin = open(son, encoding="utf-8").read().strip()
        cevaplar.append(son_metin)
        son_talimat = os.path.join(parca_klasoru, "parca-son.md")
        terim_hatalari = terim_kontrol(open(son_talimat, encoding="utf-8").read(), {"son": son_metin}) \
            if os.path.exists(son_talimat) else []
        if terim_hatalari:
            rapor.append(f"- ⚠ **parca-son**: {len(terim_hatalari)} sorun")
            rapor += [f"    - {a.replace(' → son', ' → bölüm sonu')}" for _, a in terim_hatalari]
            toplam_sorun += len(terim_hatalari)
        else:
            rapor.append("- ✓ **parca-son**: sözlük / tekrar / sorular eklendi")
    else:
        rapor.append("- ℹ parca-son-cevap.md yok (sözlük/tekrar/sorular bölümü eklenmedi)")
    md = "\n\n---PAGE---\n\n".join(cevaplar)
    md = re.sub(r"(?:\s*---PAGE---\s*){2,}", "\n\n---PAGE---\n\n", md)
    baslik = os.path.basename(bolum).replace("_", " ")
    with open(bolum + "_calisma.md", "w", encoding="utf-8") as f:
        f.write(md + "\n")
    eksik = pdf_uret(md, bolum + "_calisma.pdf", gorsel_klasoru, baslik) if cevaplar else []
    if eksik:
        rapor.append(f"- ⚠ PDF'te bulunamayan görseller: {', '.join(eksik)}")
        toplam_sorun += 1
    with open(bolum + "_kontrol.md", "w", encoding="utf-8") as f:
        f.write("\n".join(rapor) + "\n")
    print("\n".join(rapor))
    print(f"\n{'✅ Sorun yok.' if not toplam_sorun else f'⚠ {toplam_sorun} sorun — yukarıdaki parçaları yeniden iste.'}")
    if cevaplar:
        print(f"📄 {bolum}_calisma.pdf")
    return toplam_sorun


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Kullanım: python3 calisma_pdf.py "<kitap>_Bolumler/<bölüm klasörü>"')
    calistir(sys.argv[1])
