import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kaynak'); sys.path.insert(0, _K)
"""Sommerville düzenine benzeyen sentetik test kitabı: içindekiler, üst bilgiler, vektör şemalar,
aynı sayfada iki şekil, raster resim şekil, metin tablosu, yan kutu. Doğru cevap (beklenen.json) ile."""
import json, random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image, ImageDraw

W, H = A4
random.seed(3)
CUMLE = ("Software engineering is concerned with all aspects of software production from the early stages of "
         "system specification through to maintaining the system after it has gone into use. ")
beklenen = {"sekiller": [], "sayfa_kaymasi": 20}
c = canvas.Canvas("Test Kitabi.pdf", pagesize=A4)
sayfa = [0]


def yeni_sayfa(ust=None):
    if sayfa[0]:
        c.showPage()
    sayfa[0] += 1
    basili = sayfa[0] - beklenen["sayfa_kaymasi"]
    if ust and basili > 0:
        c.setFont("Helvetica", 8)
        if basili % 2 == 0:
            c.drawString(60, H - 40, f"{basili}  Chapter {ust[0]}  ■  {ust[1]}")
        else:
            c.drawRightString(W - 60, H - 40, f"{ust[0]}.1  ■  {ust[1]}  {basili}")
    return H - 70


def paragraf(y, n=4, x=80, gen=430):
    c.setFont("Times-Roman", 10.5)
    metin = (CUMLE * n).split()
    satir = ""
    for k in metin:
        if c.stringWidth(satir + " " + k, "Times-Roman", 10.5) > gen:
            c.drawString(x, y, satir.strip()); y -= 13.5; satir = ""
        satir += " " + k
    if satir.strip():
        c.drawString(x, y, satir.strip()); y -= 13.5
    return y - 8


def kutu_sema(x, y, etiketler):
    """Yan yana kutular ve oklar (vektör)."""
    c.setLineWidth(1)
    bw, bh, ara = 85, 30, 25
    for i, e in enumerate(etiketler):
        bx = x + i * (bw + ara)
        c.rect(bx, y - bh, bw, bh)
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(bx + bw / 2, y - bh / 2 - 3, e)
        if i:
            c.line(bx - ara, y - bh / 2, bx, y - bh / 2)
            c.line(bx - 5, y - bh / 2 + 3, bx, y - bh / 2); c.line(bx - 5, y - bh / 2 - 3, bx, y - bh / 2)
    return y - bh - 10


def alt_yazi(x, y, no, metin):
    c.setFont("Helvetica-Bold", 8.5); c.drawString(x, y, f"Figure {no}")
    c.setFont("Helvetica", 8.5); c.drawString(x + 52, y, metin)
    return y - 22


def sekil_kaydet(no, sayfa_no, kutu, tur):
    beklenen["sekiller"].append({"no": no, "pdf_sayfa": sayfa_no, "kutu": kutu, "tur": tur})


# --- Kapak ve içindekiler (sayfa 1-20)
yeni_sayfa(); c.setFont("Helvetica-Bold", 24); c.drawCentredString(W / 2, H / 2, "Test Kitabi")
for _ in range(17):
    yeni_sayfa()
y = yeni_sayfa(); c.setFont("Helvetica-Bold", 16); c.drawString(80, y, "Contents"); y -= 40
c.setFont("Times-Roman", 11)
for no, ad, s in [(1, "Introduction", 1), (2, "Software processes", 9), (3, "Agile software development", 17)]:
    c.drawString(80, y, f"Chapter {no}  {ad}"); c.drawRightString(W - 80, y, str(s)); y -= 18
c.drawString(80, y, "Glossary"); c.drawRightString(W - 80, y, "25"); y -= 18
c.drawString(80, y, "Index"); c.drawRightString(W - 80, y, "29")
yeni_sayfa()

BOLUMLER = [(1, "Introduction"), (2, "Software processes"), (3, "Agile software development")]
for no, ad in BOLUMLER:
    for k in range(8):
        y = yeni_sayfa((no, ad) if k else None)
        if k == 0:
            c.setFont("Helvetica-Bold", 22); c.drawString(80, y - 20, f"{no}"); c.drawString(110, y - 20, ad)
            y -= 70
            y = paragraf(y, 6)
            continue
        if k == 1:
            c.setFont("Helvetica-Bold", 13); c.drawString(80, y, f"{no}.1  Process models"); y -= 22
            y = paragraf(y, 3)
            ust = y
            y = kutu_sema(90, y, ["Requirements", "Design", "Testing", "Release"])
            y = alt_yazi(80, y, f"{no}.1", "The waterfall model")
            sekil_kaydet(f"{no}.1", sayfa[0], (90, ust, 90 + 4 * 85 + 3 * 25, y + 22), "vektor")
            y = paragraf(y, 4)
        elif k == 3:            # aynı sayfada iki şekil
            y = paragraf(y, 2)
            ust = y
            y = kutu_sema(90, y, ["Specify", "Develop", "Validate"])
            y = alt_yazi(80, y, f"{no}.2", "Process activities")
            sekil_kaydet(f"{no}.2", sayfa[0], (90, ust, 90 + 3 * 110, y + 22), "vektor")
            y = paragraf(y, 2)
            ust = y
            y = kutu_sema(90, y, ["Plan", "Build", "Review", "Deploy"])
            y = alt_yazi(80, y, f"{no}.3", "An incremental cycle")
            sekil_kaydet(f"{no}.3", sayfa[0], (90, ust, 90 + 4 * 110, y + 22), "vektor")
            y = paragraf(y, 2)
        elif k == 5:            # raster resim şekil
            y = paragraf(y, 2)
            im = Image.new("RGB", (600, 300), "white"); d = ImageDraw.Draw(im)
            for i in range(5):
                d.rectangle((20 + i * 115, 100, 110 + i * 115, 180), outline="black", width=3)
                d.text((35 + i * 115, 130), f"Step {i + 1}", fill="black")
            im.save("rs.png")
            c.drawImage("rs.png", 90, y - 180, 360, 180)
            ust = y; y -= 192
            y = alt_yazi(80, y, f"{no}.4", "A raster diagram of the steps")
            sekil_kaydet(f"{no}.4", sayfa[0], (90, ust, 450, y + 22), "raster")
            y = paragraf(y, 3)
        elif k == 6:            # metin tablosu (Figure olarak)
            y = paragraf(y, 2)
            ust = y
            c.setLineWidth(0.5); c.line(80, y, 510, y); y -= 14
            c.setFont("Helvetica-Bold", 8.5); c.drawString(85, y, "Activity"); c.drawString(230, y, "Description"); y -= 14
            c.setFont("Helvetica", 8.5)
            for a, b in [("Specification", "Defining what the system should do"),
                         ("Development", "Designing and programming the system"),
                         ("Validation", "Checking that it does what the customer wants")]:
                c.drawString(85, y, a); c.drawString(230, y, b); y -= 13
            c.line(80, y + 4, 510, y + 4); y -= 10
            y = alt_yazi(80, y, f"{no}.5", "Fundamental activities")
            sekil_kaydet(f"{no}.5", sayfa[0], (80, ust, 510, y + 22), "tablo")
            y = paragraf(y, 3)
        else:
            y = paragraf(y, 8)
# Sözlük ve dizin
y = yeni_sayfa(); c.setFont("Helvetica-Bold", 16); c.drawString(80, y, "Glossary"); y -= 30; y = paragraf(y, 6)
for _ in range(3):
    y = yeni_sayfa(); paragraf(y, 6)
y = yeni_sayfa(); c.setFont("Helvetica-Bold", 16); c.drawString(80, y, "Index")
c.save()
json.dump(beklenen, open("beklenen.json", "w"), indent=1)
print("sayfa:", sayfa[0], "şekil:", len(beklenen["sekiller"]))
