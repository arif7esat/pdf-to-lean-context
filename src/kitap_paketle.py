# -*- coding: utf-8 -*-
"""
kitap_paketle.py — PDF kitabı (ya da tek bölümünü) LLM'e verilecek paketlere çevirir.

HER BÖLÜM İÇİN ÇIKTI
--------------------
<kitap adı>_Bolumler/
  04_Software_processes/              ← her bölüm kendi klasöründe
    04_Software_processes.md          ← temiz metin; her sayfa başında <!-- PDF s. 4 · kitap s. 66 -->,
                                         şekiller metinde kendi sayfasında ![Figure 4.1: …](sekiller/…png)
    sekiller/                         ← yalnızca şekil ve tabloların kırpılmış görselleri (sekil-4-1.png …)
    parcalar/                         ← LLM'e verilecek parçalar (hazır prompt + metin; eklenecek görseller
                                         her parçanın başında yazar)
  KULLANIM.md

AKIŞ
----
1) Bu betik: PDF → yukarıdaki paket (LLM yok, token harcamaz).
2) Sen: her parca-NN.md dosyasını YENİ bir sohbete yapıştır (+ başında yazan görselleri ekle).
   Cevabı aynı klasöre parca-NN-cevap.md olarak kaydet.
3) calisma_pdf.py: cevapları kontrol eder (eksik sayfa/şekil, özetlenmiş sayfa) ve çalışma PDF'ini üretir.

ÇALIŞTIRMA
----------
A) Colab: kodu bir hücreye yapıştır, ders klasörü linkini ver. 'Kitap' klasöründeki PDF'ler işlenir.
B) Mac:   pip3 install pymupdf pymupdf4llm
          python3 kitap_paketle.py "Software engineering.pdf"

Bölümler: PDF yer imleri → basılı içindekiler → (ikisi de yoksa) PDF'in tamamı tek bölüm sayılır;
bölümden ayrılmış bir PDF verilebilir. Glossary/Sözlük ve kitap sonundaki ekler (Appendix A, B …)
bulunursa ayrı klasör olarak çıkar (Ek_A_…).
"""

import os
import re
import sys
import shutil
import subprocess
from collections import Counter

# ============================================================
# AYARLAR
# ============================================================
DRIVE_A_YUKLE = True     # Colab'de: bölümleri Drive'a da yükle (izin ister)
SOZLUGU_DAHIL_ET = True  # Glossary/Sözlük bölümünü de çıkar
EKLERI_DAHIL_ET = True   # kitabın sonundaki ekleri (Appendix A, B …) de ayrı klasör olarak çıkar
SURUM = "3.8"            # çıktı biçimi değişince artar; Colab eski sürümle bölünmüş kitapları yeniden işler
PARCA_KELIME = 1800      # bir LLM parçasındaki yaklaşık İngilizce kelime (≈ 4-5 kitap sayfası)
SEKIL_DPI = 200          # kırpılan şekillerin çözünürlüğü

COLAB = "google.colab" in sys.modules or os.path.exists("/content")

# ============================================================
# Kurulum
# ============================================================
def _kur(*paketler):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *paketler])

try:
    import pymupdf
    import pymupdf4llm
except ImportError:
    print("📦 pymupdf / pymupdf4llm yükleniyor...")
    _kur("pymupdf", "pymupdf4llm")
    import pymupdf
    import pymupdf4llm

# ============================================================
# Bölüm tespiti
# ============================================================
BOLUM_BASLIK = re.compile(
    r"^\s*(?:chapter|bölüm|bolum|ünite|unite)\s+(\d{1,3})\s*[:.\-–—]?\s*(.*)$", re.I)
SOZLUK_BASLIK = re.compile(r"^\s*(glossary|sözlük|sozluk|terimler sözlüğü)\s*$", re.I)
# Ek: "Appendix A Title", "APPENDIX B: Title", "Ek-C Başlık", tek ek için yalnız "Appendix". Türkçe "Ek" yalnız harf/numarayla
# kabul edilir ("Ek bilgiler" bir ek değildir).
EK_BASLIK = re.compile(r"^\s*(?:(?i:appendix|ek)[\s\-–]*([A-Z]|\d{1,2})(?!\w)|(?i:appendix)(?!\w))\s*[:.\-–—]?\s*(.*)$")


def _ekleri_sec(adaylar, bolum_baslari):
    """Ek adaylarından gerçek kitap eklerini seçer: son bölümden SONRA başlayanlar (bölüm içi "Appendix"
    alt başlıkları ya da önsözdeki anmalar değil). Harfsiz ekler sırayla A, B … alır; aynı ek bir kez."""
    if not bolum_baslari:
        return []
    son_bolum = max(bolum_baslari)
    secilen, gorulen = [], set()
    for harf, baslik, bas, bit in adaylar:
        if bas <= son_bolum:
            continue
        harf = harf or chr(ord("A") + len(secilen))
        if harf in gorulen:
            continue
        gorulen.add(harf)
        secilen.append((harf, baslik or f"Appendix {harf}", bas, bit))
    return secilen


def yer_imlerinden(doc):
    """PDF yer imlerinden [(no, başlık, ilk_sayfa_idx, son_sayfa_idx)] çıkarır."""
    toc = doc.get_toc(simple=True)  # [seviye, başlık, sayfa(1'den)]
    if not toc:
        return None

    bolumler, sozluk, ek_adaylari, bolum_seviyeleri = [], None, [], []
    for i, (seviye, baslik, sayfa) in enumerate(toc):
        baslik = " ".join(baslik.split())
        m = BOLUM_BASLIK.match(baslik)
        e = None if m else EK_BASLIK.match(baslik)
        if m or e or SOZLUK_BASLIK.match(baslik):
            # Bitiş: bundan sonra gelen, aynı ya da daha üst seviyedeki ilk girdi
            son = doc.page_count
            for sv2, _, sy2 in toc[i + 1:]:
                if sv2 <= seviye and sy2 > sayfa:
                    son = sy2 - 1
                    break
            if e:
                ek_adaylari.append((seviye, e.group(1), e.group(2).strip(), sayfa - 1, son - 1))
                continue
            if m:
                bolum_seviyeleri.append(seviye)
            kayit = (int(m.group(1)) if m else 99,
                     (m.group(2).strip() if m else baslik) or f"Bolum {m.group(1)}",
                     sayfa - 1, son - 1)
            if m:
                bolumler.append(kayit)
            else:
                sozluk = kayit
    if len(bolumler) < 2:
        return None
    if EKLERI_DAHIL_ET:
        # Kitap eki bölümlerle aynı ya da daha üst seviyede durur (daha derindeki "Appendix" bir bölümün parçasıdır)
        ust = min(bolum_seviyeleri)
        bolumler += _ekleri_sec([(h, b, bs, bt) for sv, h, b, bs, bt in ek_adaylari if sv <= ust],
                                [b[2] for b in bolumler])
    return bolumler, sozluk


TOC_BOLUM = re.compile(r"^(?:chapter|bölüm|bolum)\s+(\d{1,3})\b\s*(.*)$", re.I)
TOC_SOZLUK = re.compile(r"^(glossary|sözlük|sozluk)\b\s*(\d{1,4})?$", re.I)
TOC_SON = re.compile(r"^(subject index|author index|index|dizin|kaynakça|references)\b\s*(\d{1,4})?$", re.I)
SAYI = re.compile(r"^\d{1,4}$")
TOC_KISIM = re.compile(r"^(part|kısım|kisim)\s+(\d{1,2})\b.*$", re.I)
TOC_EK = EK_BASLIK


def sayfa_kaymasi(doc):
    """Basılı sayfa no -> PDF sayfa indeksi kaymasını, sayfaların ilk/son
    satırlarındaki numaralardan oy çokluğuyla bulur."""
    oylar = Counter()
    for idx in range(doc.page_count):
        satirlar = [s.strip() for s in doc[idx].get_text().splitlines() if s.strip()]
        if not satirlar:
            continue
        for s in satirlar[:2] + satirlar[-2:]:
            for m in re.finditer(r"(?:^|\s)(\d{1,4})(?:\s|$)", s):
                basili = int(m.group(1))
                if 1 <= basili <= 5000:
                    oylar[idx - (basili - 1)] += 1
    if not oylar:
        return None
    kayma, oy = oylar.most_common(1)[0]
    return kayma if oy >= 5 else None


def icindekiler_satirlari(doc):
    """İçindekiler girdilerini okur. PDF'ler aynı girdiyi tek satırda
    ('Chapter 3 Agile software development 72') ya da parçalı
    ('Chapter 3' / 'Agile software development' / '72') verebilir; ikisi de desteklenir.
    Dönüş: [(tür, no, başlık, basılı_sayfa)], tür: 'bolum' | 'ek' | 'sozluk' | 'son' | 'kisim'"""
    girdiler = []
    for idx in range(min(40, doc.page_count)):
        satirlar = [" ".join(s.split()) for s in doc[idx].get_text().splitlines()]
        satirlar = [s for s in satirlar if s]
        i = 0
        while i < len(satirlar):
            s = satirlar[i]
            m = TOC_BOLUM.match(s)
            ek = None if m else TOC_EK.match(s)
            if m or ek:
                no, kalan = (int(m.group(1)), m.group(2).strip()) if m else (ek.group(1) or "", ek.group(2).strip())
                sayfa = None
                son_sayi = re.search(r"\s(\d{1,4})$", " " + kalan)
                if son_sayi:                        # hepsi tek satırda
                    sayfa = int(son_sayi.group(1))
                    kalan = kalan[: son_sayi.start()].strip()
                j = i + 1
                if not kalan and j < len(satirlar) and not SAYI.match(satirlar[j]):
                    kalan = satirlar[j]              # başlık alt satırda
                    j += 1
                if sayfa is None and j + 1 < len(satirlar) and not SAYI.match(satirlar[j]) \
                        and SAYI.match(satirlar[j + 1]) and len(satirlar[j]) < 60 and kalan:
                    kalan += " " + satirlar[j]       # iki satıra bölünmüş başlık ("Alternative …" / "for ER Models")
                    j += 1
                if sayfa is None and j < len(satirlar) and SAYI.match(satirlar[j]):
                    sayfa = int(satirlar[j])         # sayfa no alt satırda
                    j += 1
                if kalan and sayfa:
                    girdiler.append(("bolum" if m else "ek", no, kalan, sayfa))
                    i = j
                    continue
            for tur, rx in (("sozluk", TOC_SOZLUK), ("son", TOC_SON), ("kisim", TOC_KISIM)):
                m = rx.match(s)
                if m:
                    sayfa = m.group(2) if tur != "kisim" else None
                    if tur == "kisim":                # 'Part 2 Başlık 283' ya da sayı alt satırda
                        son_sayi = re.search(r"\s(\d{1,4})$", s[m.end(2):])   # 'Part 2'nin kendi no'su sayfa değil
                        sayfa = son_sayi.group(1) if son_sayi else None
                    if not sayfa and i + 1 < len(satirlar) and SAYI.match(satirlar[i + 1]):
                        sayfa = satirlar[i + 1]
                    if sayfa:
                        girdiler.append((tur, 0, m.group(1), int(sayfa)))
                    break
            i += 1
    return girdiler


def icindekilerden(doc):
    """Basılı içindekiler sayfasından bölüm sınırlarını çıkarır."""
    okunan = icindekiler_satirlari(doc)
    tekil = {}   # aynı bölüm iki kez geçebilir (özet + ayrıntılı içindekiler): ilkini tut
    for tur, no, baslik, sayfa in okunan:
        if tur == "bolum":
            tekil.setdefault(no, (no, baslik, sayfa))
    girdiler = sorted(tekil.values())
    sozluk_bas = next((s for t, _, _, s in okunan if t == "sozluk"), None)
    son_sinir = next((s for t, _, _, s in okunan if t == "son"), None)
    if len(girdiler) < 2:
        return None
    # Kısım (Part) sınırı yalnızca bölümler ARASINDA olabilir: bir bölümün ilk 3 sayfasına düşen değer
    # yanlış okunmuştur (ör. 'Part 2' satırındaki 2'nin sayfa sanılması) — atılır.
    baslar = sorted(g[2] for g in girdiler)
    kisimlar = sorted({s for t, _, _, s in okunan if t == "kisim"
                       and not any(0 <= s - b < 3 for b in baslar)})

    kayma = sayfa_kaymasi(doc)
    if kayma is None:
        return None

    # Ekler (son bölümden sonra başlayanlar) kendi sınırlarıdır: son bölüm eke kadar sürer, eki içine almaz.
    ek_tekil = {}
    for t, harf, baslik, s in okunan:
        if t == "ek":
            ek_tekil.setdefault(harf or baslik, (harf, baslik, s))
    ek_girdiler = [e for e in ek_tekil.values() if e[2] > max(baslar)]
    sinirlar = ([g[2] for g in girdiler] + kisimlar + [e[2] for e in ek_girdiler]
                + [x for x in (sozluk_bas, son_sinir) if x])
    def bitis(bas_basili):
        sonrakiler = [s for s in sinirlar if s > bas_basili]
        return (min(sonrakiler) - 1) if sonrakiler else None

    def idx(basili):
        return max(0, min(doc.page_count - 1, basili - 1 + kayma))

    bolumler = []
    for no, baslik, sayfa in girdiler:
        b = bitis(sayfa)
        bolumler.append((no, baslik, idx(sayfa), idx(b) if b else doc.page_count - 1))
    if EKLERI_DAHIL_ET:
        adaylar = []
        for harf, baslik, sayfa in sorted(ek_girdiler, key=lambda e: e[2]):
            b = bitis(sayfa)
            adaylar.append((harf, baslik, idx(sayfa), idx(b) if b else doc.page_count - 1))
        bolumler += _ekleri_sec(adaylar, [b[2] for b in bolumler])
    sozluk = None
    if sozluk_bas:
        b = bitis(sozluk_bas)
        sozluk = (99, "Glossary", idx(sozluk_bas), idx(b) if b else doc.page_count - 1)
    return bolumler, sozluk


# ============================================================
# Şekil ve tablo bulma (alt yazıdan: "Figure 4.1", "Table 2.3")
# ============================================================
ALT_YAZI = re.compile(r"^\s*(Figure|Fig\.|Table|Şekil|Tablo)\s+((?:\d+|(?-i:[A-Z])(?=\.))(?:\.\d+)+)\s*(.*)$", re.I)   # ekte "A.1"


def govde_fontu(belge, sayfalar):
    """En çok karakter basılmış (font, boyut) çifti = gövde metni."""
    sayac = Counter()
    for i in sayfalar:
        for b in belge[i].get_text("dict")["blocks"]:
            if b["type"]:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    sayac[(s["font"], round(s["size"]))] += len(s["text"].strip())
    return sayac.most_common(1)[0][0] if sayac else ("", 10)


def _blok_metni(b):
    return " ".join("".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]).strip()


def _blok_fontu(b):
    sayac = Counter()
    for l in b["lines"]:
        for s in l["spans"]:
            sayac[(s["font"], round(s["size"], 1))] += len(s["text"].strip())
    return sayac.most_common(1)[0][0] if sayac else ("", 0)


def _govde_paragrafi(b, r, govde, sayfa_genisligi):
    """Ağırlıklı yazı tipi farklı olsa da gövde paragrafı: içinde italik bir sorgu/terim geçen ve bu yüzden
    çoğunluğu italik görünen paragraf ("For example, the query Q0B: *List the …* can be specified …").
    Ölçüt: karakterlerin en az beşte biri tam gövde yazı tipinde, en az iki satır, geniş ve satırlar bloğu
    dolduruyor (gövde yazı tipindeki tablo hücreleri dar olduğu için sayılmaz). Tamamen italik
    yazılmış metin şekilleri (Sommerville 1.6, 30.2) gövde yazısı içermediği için şekil olarak kalır."""
    toplam = gov = 0
    for l in b["lines"]:
        for sp in l["spans"]:
            n = len(sp["text"].strip())
            toplam += n
            if sp["font"] == govde[0] and abs(sp["size"] - govde[1]) < 1:
                gov += n
    if not (toplam > 0 and gov >= 0.2 * toplam and len(b["lines"]) >= 2 and r.width > 0.4 * sayfa_genisligi):
        return False
    # Paragraf satırları bloğu doldurur; tablo hücreleri (gövde yazı tipinde olsalar da) dardır
    return sum(l["bbox"][2] - l["bbox"][0] for l in b["lines"]) / len(b["lines"]) >= 0.6 * r.width


def _birlesik(kutular, bosluk):
    """Birbirine 'bosluk' kadar yakın kutuları tek kümede birleştirir (birleşen kümeler büyüdükçe yeniden
    dener; sonuç eski tek tek karşılaştırmalı yöntemle aynı, ama x'e göre sıralı tarama ile çok daha hızlı)."""
    kumeler = [pymupdf.Rect(k) for k in kutular]
    while True:
        n = len(kumeler)
        ebeveyn = list(range(n))

        def kok(i):
            while ebeveyn[i] != i:
                ebeveyn[i] = ebeveyn[ebeveyn[i]]
                i = ebeveyn[i]
            return i
        sira = sorted(range(n), key=lambda i: kumeler[i].x0)
        aktif = []                                  # x aralığı hâlâ çakışabilecek kutular
        birlesti = False
        for i in sira:
            r = kumeler[i]
            aktif = [j for j in aktif if kumeler[j].x1 + 2 * bosluk >= r.x0]
            gen = r + (-bosluk, -bosluk, bosluk, bosluk)
            for j in aktif:
                if gen.intersects(kumeler[j]):
                    a, b = kok(i), kok(j)
                    if a != b:
                        ebeveyn[a] = b
                        birlesti = True
            aktif.append(i)
        if not birlesti:
            return kumeler
        gruplar = {}
        for i in range(n):
            k = kok(i)
            gruplar[k] = gruplar[k] | kumeler[i] if k in gruplar else pymupdf.Rect(kumeler[i])
        kumeler = list(gruplar.values())


def _altyazi_uzakligi(k, ak):
    """Şekil adayı k ile alt yazı kutusu ak arasındaki uzaklık (40 pt'den uzaksa None). Alt yazı:
    şeklin altında (üst kenarı şeklin altına yakın), üstünde (alt kenarı şeklin üstüne yakın), kenar
    sütununda üstten hizalı (Sommerville) ya da kenar sütununda ALTTAN hizalı (Elmasri–Navathe: alt yazı
    şeklin yanında, dikeyde onunla örtüşür; L biçimli şeklin boş köşesine de düşebilir)."""
    d = min(abs(k.y0 - ak.y0), abs(ak.y0 - k.y1), abs(k.y0 - ak.y1), _yandan_alttan(k, ak))
    return d if d < 40 else None


def _yandan_alttan(k, ak):
    """Alt yazı şeklin yanında (dikeyde örtüşüyor) duruyorsa alt kenarlar arası fark; değilse sonsuz."""
    ortusme = min(k.y1, ak.y1) - max(k.y0, ak.y0)
    yatay = max(k.x0 - ak.x1, ak.x0 - k.x1)
    return abs(k.y1 - ak.y1) if ortusme > 0.5 * min(ak.height, k.height) and yatay < 60 else float("inf")


def _dipnot_cizgisi(sayfa, bloklar, govde_boyut):
    """Sayfa altı dipnot bölgesinin üst sınırı (ayırma çizgisinin y'si) ya da None. Dipnot: sayfanın alt
    kısmında kısa bir yatay çizgi ve hemen altında gövdeden küçük puntolu, rakamla başlayan metin."""
    W, H = sayfa.rect.width, sayfa.rect.height
    for d in sayfa.get_drawings():
        r = d["rect"]
        if not (r.height < 1.5 and 40 < r.width < 0.45 * W and r.y0 > 0.6 * H):
            continue
        for b in bloklar:
            if b["type"] != 0:
                continue
            br = pymupdf.Rect(b["bbox"])
            if 0 < br.y0 - r.y1 < 20 and abs(br.x0 - r.x0) < 6 and _blok_fontu(b)[1] < govde_boyut - 0.5 \
                    and re.match(r"\d{1,3}\s*[A-Za-z(“\"]", _blok_metni(b)):
                return r.y0
    return None


def _yazi_tipleri(sayfa, r):
    """r içindeki metin satırlarının (yazı tipi, punto) kümesi ve satır sayısı."""
    tipler, n = set(), 0
    for b in sayfa.get_text("dict", clip=r)["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["text"].strip()]
            if sp:
                n += 1
                tipler |= {(s["font"], round(s["size"])) for s in sp}
    return tipler, n


def _uzak_parca_uygun(sayfa, a, kutu, k, i, ogeler, n_yazi, altyazilar, kumeler, ayrilan):
    """Şekilden 30–90 pt uzaktaki k kümesi bu şeklin bir parçası mı ((a)/(b) parçaları, boşluklu diyagram)?
    Parça değildir: (1) yazıları şeklin yazılarından farklı yazı tipindeyse (alıştırma, alıntı, kod, başlık);
    (2) çizimsiz tek satırsa (sayfa üstü/bölüm başlığı) ya da şekilde metin yokken
    yalnız metinden oluşuyorsa (alıntı kutusu); (3) başka bir şeklin alt yazısıyla o şeklin arasında
    kalıyorsa (alt yazısı altta olan bir sonraki şeklin üst parçası)."""
    k_tip, k_satir = _yazi_tipleri(sayfa, k)
    cizim = any(k.contains(o) for o in ogeler[n_yazi:])
    if not cizim and k_satir <= 1:
        return False
    if k_satir:
        s_tip, s_satir = _yazi_tipleri(sayfa, kutu)
        if s_satir and not (k_tip & s_tip):
            return False
        if not s_satir and not cizim:              # şekil yazısız (çizilmiş harfler), parça yalnız metin: alıntı/paragraf
            return False
    asagida = k.y0 >= kutu.y1 - 1                  # k şeklin altında mı (değilse üstünde)
    for b in altyazilar:
        if b is a or id(b) not in ayrilan:
            continue
        bk, kume = b["alt_yazi_kutu"], kumeler[ayrilan[id(b)]]
        sekil_ustte = (kume.y0 + kume.y1) / 2 < (bk.y0 + bk.y1) / 2     # b'nin şekli alt yazısının üstünde
        if asagida and bk.y0 >= k.y1 - 1 and sekil_ustte:
            return False                           # k, b'nin alt yazısının üstünde: b'nin şekline ait
        if not asagida and bk.y1 <= k.y0 + 1 and not sekil_ustte:
            return False                           # k, b'nin alt yazısının altında: b'nin şekline ait
    return True


def _nesne_sekilleri(sayfa, govde, ust_alt_pay=0.07):
    """1. aşama — PDF nesnelerinden (çizim, resim, küçük yazı) şekil kutuları. Döndürür:
    (bulunan, eşleşmeyen alt yazılar, gövde blokları, üst sınır, alt sınır)"""
    W, H = sayfa.rect.width, sayfa.rect.height
    govde_font, govde_boyut = govde
    ust, alt = H * ust_alt_pay, H * (1 - ust_alt_pay * 0.6)
    altyazilar, sekil_yazilari, govde_bloklari = [], [], []
    bloklar = sayfa.get_text("dict")["blocks"]
    dipnot_y = _dipnot_cizgisi(sayfa, bloklar, govde_boyut)
    if dipnot_y is not None:                  # dipnot bölgesi (çizgisiyle) gövde gibi engel: kırpmaya girmez
        govde_bloklari.append(pymupdf.Rect(0, dipnot_y - 1, W, H))
    for b in bloklar:
        if b["type"] == 1:
            continue
        r = pymupdf.Rect(b["bbox"])
        metin = _blok_metni(b)
        if not metin or r.y1 < ust or r.y0 > alt:
            continue
        font, boyut = _blok_fontu(b)
        govde_mi = (font == govde_font and abs(boyut - govde_boyut) < 1) or _govde_paragrafi(b, r, govde, W)
        if govde_mi or boyut > govde_boyut + 0.5:
            govde_bloklari.append(r)          # gövde metni ya da başlık (metindeki "Figure 4.8 illustrates" dahil)
            continue
        if dipnot_y is not None and r.y0 > dipnot_y:
            govde_bloklari.append(r)          # sayfa altı dipnotu ("13 In an ER diagram…") şekle ait değil
            continue
        # Küçük/farklı font: satır satır incele. Alt yazı satırı ve aynı sütunda onu izleyen satırlar alt
        # yazıdır; geri kalanlar şekil içi etiket ya da tablo hücresidir. (Alt yazı bir etiketle aynı bloğa
        # düşebilir: "Retest program / Figure 4.8 The debugging process".)
        satirlar = [(pymupdf.Rect(l["bbox"]), "".join(sp["text"] for sp in l["spans"]).strip()) for l in b["lines"]]
        satirlar = [(lr, t) for lr, t in satirlar if t]
        i = 0
        while i < len(satirlar):
            lr, t = satirlar[i]
            m = ALT_YAZI.match(t)
            if not m:
                sekil_yazilari.append(lr)
                i += 1
                continue
            kutu, parca = pymupdf.Rect(lr), [t]
            j = i + 1
            while j < len(satirlar) and -6 < satirlar[j][0].x0 - lr.x0 < 30 and \
                    satirlar[j][0].y0 - kutu.y1 < 0.8 * lr.height and not ALT_YAZI.match(satirlar[j][1]):
                kutu |= satirlar[j][0]
                parca.append(satirlar[j][1])
                j += 1
            birlesik = ""
            for t2 in parca:                      # satır sonu tiresi: "Activity-" + "based" → "Activity-based"
                birlesik = birlesik + t2 if birlesik.endswith("-") else (birlesik + " " + t2).strip()
            m = ALT_YAZI.match(birlesik)
            ilk = m.group(3).lstrip(" .:–—-")[:1]
            onceki = satirlar[i - 1] if i else None
            devam = (onceki is not None and abs(onceki[0].x0 - lr.x0) < 4 and 0 <= lr.y0 - onceki[0].y1 < lr.height
                     and not re.search(r"[.:;!?]$", onceki[1]))     # paragrafın ortasındaki satır
            alt_sekiller = re.match(r"\(([a-z]|[ivx]{1,4}|continued|cont\.?|devam(ı)?)\)(\s|$)",
                                    m.group(3).lstrip(" .:–—-"), re.I)  # "(a) …, (b) …", "(continued)"
            if ilk.islower() or (ilk and ilk in "(,;" and not alt_sekiller) or devam:
                # "Figure 5.15 gives task durations…" — alıştırma/metin cümlesi, alt yazı DEĞİL
                # (gerçek alt yazının başlığı büyük harfle başlar: "Figure 5.15 Task durations")
                sekil_yazilari += [satirlar[x][0] for x in range(i, j)]
                i = j
                continue
            altyazilar.append({"tur": "tablo" if m.group(1).lower() in ("table", "tablo") else "sekil",
                               "no": m.group(2), "baslik": re.sub(r"\s+", " ", m.group(3)).strip(),
                               "alt_yazi_kutu": kutu, "satir_h": lr.height})
            i = j
    if not altyazilar:
        return [], [], govde_bloklari, ust, alt
    # Alt yazının devamı ayrı bir metin bloğuna düşebilir (asılı girintili satırlar): alt yazının hemen
    # altında, aynı sütunda ve aynı satır yüksekliğindeki satırlar da alt yazıdır.
    for a in altyazilar:
        ak, h = a["alt_yazi_kutu"], a["satir_h"]
        degisti = True
        while degisti:
            degisti = False
            for lr in sekil_yazilari:
                if -6 < lr.x0 - ak.x0 < 30 and -2 <= lr.y0 - ak.y1 < 0.8 * h and 0.7 * h < lr.height < 1.5 * h:   # alt/üst simgeli satır daha yüksek
                    ak |= lr
                    sekil_yazilari.remove(lr)
                    degisti = True
                    break
        a["alt_yazi_kutu"] = ak
    ogeler = list(sekil_yazilari)
    n_yazi = len(ogeler)                    # ogeler[:n_yazi] şekil içi yazı, gerisi çizim/resim
    uzun_cizgiler = []
    for d in sayfa.get_drawings():
        r = pymupdf.Rect(d["rect"])
        # Düz yatay/dikey çizgilerin kutusu sıfır kalınlıktadır ("boş" sayılır) — oklar, aktör figürünün
        # kolları, tablo çizgileri kaybolmasın diye yarım punto kalınlık ver.
        if r.height < 1:
            r.y0, r.y1 = r.y0 - 0.5, r.y1 + 0.5
        if r.width < 1:
            r.x0, r.x1 = r.x0 - 0.5, r.x1 + 0.5
        r &= sayfa.rect
        if r.is_empty or r.y1 < ust or r.y0 > alt:
            continue
        if dipnot_y is not None and r.y0 >= dipnot_y - 2:      # dipnot ayırma çizgisi ve altı
            continue
        if r.get_area() > 0.5 * sayfa.rect.get_area():       # sayfa çerçevesi / kesim işaretleri
            continue
        dolgu = d.get("fill")
        if d.get("type") == "f" and dolgu and min(dolgu) > 0.97:   # görünmez beyaz zemin dikdörtgeni
            continue
        if r.width > 0.55 * W and r.height < 2:      # uzun yatay çizgi: kümelemeye katma (iki şekli
            uzun_cizgiler.append(r)                  # birleştirmesin) ama tablo çizgisiyse kırpmaya dahil et
            continue
        if r.width < 1.5 and r.height < 1.5:
            continue
        if r.height > 0.6 * H or r.width > 0.8 * W:    # sütun çizgisi / kenar süsü
            continue
        ogeler.append(r)
    for im in sayfa.get_images(full=True):
        for r in sayfa.get_image_rects(im[0]):
            if ust < r.y1 and r.y0 < alt and r.get_area() > 400:
                ogeler.append(r)
    # Gövde metniyle çakışan çizimler (altı çizili başlık vb.) şekil sayılmaz
    kumeler = [k for k in _birlesik(ogeler, 9)
               if k.get_area() > 1500 and not any((k & g).get_area() > 0.5 * g.get_area() for g in govde_bloklari)]
    # Her alt yazıya en uygun kümeyi ata: alt yazı ile aynı hizada başlayan (kenar sütunu düzeni), hemen
    # üstünde biten (alt yazı altta) ya da hemen altında başlayan (alt yazı üstte) küme.
    sonuc, kullanilan, eslesmeyen = [], set(), []
    # Her alt yazının (tek başına bakıldığında) en yakın kümesi: henüz işlenmemiş bir alt yazının kümesine,
    # önce işlenen şeklin kutusu _tamamla ile büyürken girilmesin (yan yana/üst üste şekiller).
    ayrilan = {}
    for b in altyazilar:
        uz = [(_altyazi_uzakligi(k, b["alt_yazi_kutu"]), i) for i, k in enumerate(kumeler)]
        uz = [x for x in uz if x[0] is not None]
        if uz:
            ayrilan[id(b)] = min(uz)[1]
    for a in sorted(altyazilar, key=lambda a: a["alt_yazi_kutu"].y0):
        ak = a["alt_yazi_kutu"]
        en_iyi = None
        for i, k in enumerate(kumeler):
            if i in kullanilan:
                continue
            aday = _altyazi_uzakligi(k, ak)
            if aday is not None and (en_iyi is None or aday < en_iyi[0]):
                en_iyi = (aday, i)
        if en_iyi is None:
            eslesmeyen.append(a)                # 2. aşamada piksel taramasıyla aranır
            continue
        kullanilan.add(en_iyi[1])
        kutu = pymupdf.Rect(kumeler[en_iyi[1]])
        # Aynı şekle ait olup ara boşlukla kopmuş kümeleri ekle (başka alt yazıya daha yakın olmayanlar)
        degisti = True
        while degisti:
            degisti = False
            for i, k in enumerate(kumeler):
                if i in kullanilan:
                    continue
                dikey = max(0, max(k.y0, kutu.y0) - min(k.y1, kutu.y1))
                yatay_ortusme = min(k.x1, kutu.x1) - max(k.x0, kutu.x0) > -20
                baska = any(abs(k.y0 - b["alt_yazi_kutu"].y0) < 15 or _yandan_alttan(k, b["alt_yazi_kutu"]) < 15
                            or ayrilan.get(id(b)) == i      # başka alt yazının en yakın kümesi
                            for b in altyazilar if b is not a)
                # Çok parçalı şekil ((a), (b), (c) arasında geniş boşluk): arada gövde metni ya da başka alt
                # yazı yoksa parça bu şekle aittir.
                bant = pymupdf.Rect(min(k.x0, kutu.x0), min(k.y1, kutu.y1), max(k.x1, kutu.x1), max(k.y0, kutu.y0))
                # Başka bir alt yazı (hangi sütunda olursa olsun: kenar sütunu düzeni) bu parçanın hizasına ya
                # da aradaki boşluğa düşüyorsa parça o şeklindir.
                y0_, y1_ = min(bant.y0, k.y0), max(bant.y1, k.y1)
                arada_engel = any(g.intersects(bant) for g in govde_bloklari) or \
                    any(b["alt_yazi_kutu"].y1 > y0_ and b["alt_yazi_kutu"].y0 < y1_ for b in altyazilar if b is not a) \
                    or a["alt_yazi_kutu"].intersects(bant)
                if (dikey < 30 or (dikey < 90 and not arada_engel and _uzak_parca_uygun(sayfa, a, kutu, k, i, ogeler, n_yazi,
                                                                              altyazilar, kumeler, ayrilan))) \
                        and yatay_ortusme and not baska:
                    kutu |= k
                    kullanilan.add(i)
                    degisti = True
        a["kutu"] = _tamamla(kutu, ogeler + uzun_cizgiler, n_yazi, govde_bloklari,
                             [b["alt_yazi_kutu"] for b in altyazilar if b is not a],
                             [s["kutu"] for s in sonuc] +
                             [kumeler[ayrilan[id(b)]] for b in altyazilar
                              if b is not a and "kutu" not in b and id(b) in ayrilan
                              and ayrilan[id(b)] not in kullanilan])
        sonuc.append(a)
    return sonuc, eslesmeyen, govde_bloklari, ust, alt


def sayfa_sekilleri(sayfa, govde, ust_alt_pay=0.07):
    """Sayfadaki şekilleri döndürür: [{'tur','no','baslik','kutu','alt_yazi_kutu','engeller','kenar_uyari'}]
    Eşleştirilemeyen alt yazılar {'kutu': None, 'bulunamadi': True} ile döner (uyarı için).

    İki bağımsız aşama:
      1) PDF nesneleri (çizgi, şekil, resim, yazı) ile kutu bulunur.
      2) Sayfa piksel olarak çizilir; gövde metni, alt yazılar, üst/alt bilgi silinince geriye kalan
         "mürekkep" bağlı bölgelere ayrılır ve şekle değen her bölge kutuya katılır. PDF'in şekli nasıl
         çizdiğinden (ince çizgi, form nesnesi, kırpma yolu, gömülü resim, gölge…) bağımsızdır.
    Kutular yalnızca BÜYÜR (2. aşama hiçbir şeyi kesemez); başka şeklin alanına ya da gövde metnine girmez."""
    sonuc, eslesmeyen, govde_bloklari, ust, alt = _nesne_sekilleri(sayfa, govde, ust_alt_pay)
    if not sonuc and not eslesmeyen:
        return []
    altyazi_kutulari = [a["alt_yazi_kutu"] for a in sonuc + eslesmeyen]
    for a in sonuc + eslesmeyen:
        a["engeller"] = govde_bloklari + altyazi_kutulari   # kenar payında beyazlatılacak metinler
        a["altyazilar"] = altyazi_kutulari                  # resimde HİÇ görünmemeli (metinde zaten var)
        a["kenar_uyari"] = False
    try:
        _piksel_tamamla(sayfa, sonuc, eslesmeyen, govde_bloklari, ust, alt)
        _ust_uste_ayir(sayfa, sonuc + eslesmeyen)
        _simgeleri_at(sayfa, [a for a in sonuc + eslesmeyen if a.get("kutu") is not None],
                      [a["alt_yazi_kutu"] for a in sonuc + eslesmeyen], govde_bloklari)
        _disarida_kalan(sayfa, [a for a in sonuc + eslesmeyen if a.get("kutu") is not None],
                        sonuc + eslesmeyen, govde_bloklari, ust, alt)
    except ImportError:
        pass                                    # numpy yoksa 1. aşamanın sonucu kalır
    for a in [x for x in eslesmeyen if x.get("kutu") is not None]:   # ayırmayla şeklini bulanlar
        eslesmeyen.remove(a)
        sonuc.append(a)
    for a in eslesmeyen:
        if a.get("kutu") is None:
            a["bulunamadi"] = True
        sonuc.append(a)
    return sorted(sonuc, key=lambda a: a["alt_yazi_kutu"].y0)


def _gri(sayfa, r):
    import numpy as np
    pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=r, colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width), 2.0


def _murekkebe_daralt(sayfa, r):
    """Kutuyu içindeki mürekkebin sınırına daraltır (boş kenarları atar)."""
    import numpy as np
    g, o = _gri(sayfa, r)
    ys, xs = np.nonzero(g < 245)
    if not len(ys):
        return pymupdf.Rect(r)
    return pymupdf.Rect(r.x0 + xs.min() / o, r.y0 + ys.min() / o, r.x0 + (xs.max() + 1) / o, r.y0 + (ys.max() + 1) / o)


def _ust_uste_ayir(sayfa, hepsi):
    """Üst üste duran iki şekil (ör. aynı gölgeli zeminde iki kod listesi, art arda iki tablo) tek kutuda
    birleşmişse, alttaki şeklin alt yazısının hizasındaki boş satırdan ikiye böler. Alt yazının şeklin
    üst hizasında durduğu düzende çalışır (bu kitaptaki gibi); kesecek boş satır yoksa dokunmaz."""
    import numpy as np
    for A in sorted([a for a in hepsi if a.get("kutu") is not None], key=lambda a: a["kutu"].y0):
        for C in sorted(hepsi, key=lambda a: a["alt_yazi_kutu"].y0):
            if C is A or A.get("kutu") is None:
                continue
            k, cy = A["kutu"], C["alt_yazi_kutu"].y0
            if not (k.y0 + 12 < cy < k.y1 - 12) or abs(A["alt_yazi_kutu"].y0 - k.y0) > 25:
                continue
            bolge = pymupdf.Rect(k.x0, max(k.y0, cy - 45), k.x1, min(k.y1, cy + 45))
            g, o = _gri(sayfa, bolge)
            bos = (g < 245).sum(axis=1) == 0
            # Boş satır ÖBEKLERİ: iki şekil arasındaki boşluk kalındır; tablo satırları arasındaki ince beyaz
            # çizgiler (1 pt) kesim yeri sayılmaz. En kalın öbek seçilir, eşitse alt yazıya en yakını.
            obekler, bas = [], None
            for i, b in enumerate(list(bos) + [False]):
                if b and bas is None:
                    bas = i
                elif not b and bas is not None:
                    obekler.append((bas, i))
                    bas = None
            obekler = [(b0, b1) for b0, b1 in obekler if (b1 - b0) / o >= 3]
            if not obekler:
                continue
            hedef = (cy - bolge.y0) * o
            b0, b1 = max(obekler, key=lambda x: (min(x[1] - x[0], 12 * o), -abs((x[0] + x[1]) / 2 - hedef)))
            kes = bolge.y0 + (b0 + b1) / 2 / o
            ust_parca, alt_parca = pymupdf.Rect(k.x0, k.y0, k.x1, kes), pymupdf.Rect(k.x0, kes, k.x1, k.y1)
            A["kutu"] = _murekkebe_daralt(sayfa, ust_parca)
            if C.get("kutu") is None:
                C["kutu"] = _murekkebe_daralt(sayfa, alt_parca)
            else:
                C["kutu"] = _murekkebe_daralt(sayfa, pymupdf.Rect(C["kutu"]) & pymupdf.Rect(-1e4, kes, 1e4, 1e4)) \
                    | _murekkebe_daralt(sayfa, alt_parca)


def _simgeleri_at(sayfa, sekiller, altyazilar, govde_bloklari):
    """Alt yazının hemen altındaki küçük simge (kitabın vaka işareti: kitap, şırınga…) kırpmaya girmişse çıkarır.
    Koşullar: simge alt yazının en çok 45 pt altında başlar ve 60x60 pt'den küçüktür; simgenin sağında baştan
    sona boş bir dikey şerit vardır; şeklin geri kalanı tamamen o şeridin sağındadır. Bu koşullar
    sağlanmazsa hiçbir şey değişmez — şekle ait hiçbir şey kesilmez."""
    import numpy as np
    for a in sekiller:
        k = a["kutu"]
        g, o = _gri(sayfa, k)
        m = g < 245
        for c in altyazilar:                                   # alt yazı metni resimde zaten beyazlatılıyor
            cc = (pymupdf.Rect(c) + (-1.5, -1.5, 1.5, 1.5)) & k
            if not cc.is_empty:
                m[int((cc.y0 - k.y0) * o):int((cc.y1 - k.y0) * o) + 1,
                  int((cc.x0 - k.x0) * o):int((cc.x1 - k.x0) * o) + 1] = False
        dolu_sutun = m.any(axis=0)
        if not dolu_sutun.any():
            continue
        # soldan ilk mürekkep öbeği ve ardından gelen boş şerit
        x = int(np.argmax(dolu_sutun))
        bitis = x
        while bitis < len(dolu_sutun) and dolu_sutun[bitis]:
            bitis += 1
        bosluk = bitis
        while bosluk < len(dolu_sutun) and not dolu_sutun[bosluk]:
            bosluk += 1
        if bosluk >= len(dolu_sutun) or (bosluk - bitis) / o < 6:
            continue                                           # ayıran boş şerit yok
        ys = np.nonzero(m[:, x:bitis].any(axis=1))[0]
        simge = pymupdf.Rect(k.x0 + x / o, k.y0 + ys.min() / o, k.x0 + bitis / o, k.y0 + (ys.max() + 1) / o)
        alt_yazi_alti = any(0 <= simge.y0 - c.y1 < 45 and min(simge.x1, c.x1) - max(simge.x0, c.x0) > -10
                            for c in altyazilar)
        if simge.width < 60 and simge.height < 60 and alt_yazi_alti:
            # Güvenlik: atılacak şeritte simgeden başka TEK bir mürekkep noktası bile olmamalı
            serit = m[:, :bosluk].copy()
            sy0, sy1 = int((simge.y0 - k.y0) * o), int((simge.y1 - k.y0) * o) + 1
            serit[sy0:sy1, x:bitis] = False
            if not serit.any():
                a["kutu"] = pymupdf.Rect(k.x0 + bosluk / o - 1, k.y0, k.x1, k.y1)


def _disarida_kalan(sayfa, sekiller, hepsi, govde_bloklari, ust, alt):
    """SON DENETİM (kırpmadan bağımsız): sayfadan gövde metni, alt yazılar, üst/alt bilgi ve bütün kırpma
    kutuları silinir. Bir şeklin yanında (aynı yükseklikte, 120 pt içinde) hâlâ mürekkep kalıyorsa o şekil
    ⚠ ile işaretlenir. Kenar sütunundaki simgeler (gövde metninin solu) sayılmaz."""
    import numpy as np
    pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY, alpha=False)
    m = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width) < 245
    m = m.copy()
    sx, sy = pix.width / sayfa.rect.width, pix.height / sayfa.rect.height

    def sil(r, pay):
        m[max(0, int((r.y0 - pay) * sy)):int((r.y1 + pay) * sy) + 1,
          max(0, int((r.x0 - pay) * sx)):int((r.x1 + pay) * sx) + 1] = False
    m[: int(ust * sy), :] = False
    m[int(alt * sy):, :] = False
    for b in govde_bloklari:
        sil(b, 1.5)
    for a in hepsi:
        sil(a["alt_yazi_kutu"], 1.5)
        c = a["alt_yazi_kutu"]                    # alt yazının altındaki vaka simgesi (şekle ait değil)
        simge_alani = pymupdf.Rect(c.x0 - 10, c.y1, c.x1 + 10, c.y1 + 60)
        for s_ in sekiller:                       # şeklin alanına taşmasın: yalnız şeklin solunda kalan kısım
            if simge_alani.intersects(s_["kutu"]):
                simge_alani.x1 = min(simge_alani.x1, s_["kutu"].x0 - 1)
        if simge_alani.width > 0:
            sil(simge_alani, 0)
    for a in sekiller:
        sil(a["kutu"], 1)
    marj = min((b.x0 for b in govde_bloklari), default=0)
    for a in sekiller:
        a["kenar_uyari"] = False
        k = a["kutu"]
        bant = pymupdf.Rect(max(marj + 2, k.x0 - 120), k.y0, min(sayfa.rect.width, k.x1 + 120), k.y1)
        bant |= pymupdf.Rect(k.x0, max(ust, k.y0 - 8), k.x1, min(alt, k.y1 + 8))   # hemen üstü/altı
        parca = m[int(bant.y0 * sy):int(bant.y1 * sy), int(bant.x0 * sx):int(bant.x1 * sx)]
        if parca.sum() >= 40:                       # ~40 nokta: tek bir çizgi parçasından büyük
            a["kenar_uyari"] = True


PIKSEL_HUCRE = 2          # pt — piksel taramasında ızgara hücresi
PIKSEL_ARALIK = (18, 12, 8, 5, 3)   # pt — aynı şekle ait sayılacak en büyük boşluk; çakışmada küçülür


def _piksel_tamamla(sayfa, sonuc, eslesmeyen, govde_bloklari, ust, alt):
    import numpy as np
    from collections import deque
    hucre = PIKSEL_HUCRE
    pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY, alpha=False)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    murekkep = g < 245
    sx, sy = pix.width / sayfa.rect.width, pix.height / sayfa.rect.height

    def sil(r, pay=1.5):
        x0, y0 = max(0, int((r.x0 - pay) * sx)), max(0, int((r.y0 - pay) * sy))
        x1, y1 = min(pix.width, int((r.x1 + pay) * sx) + 1), min(pix.height, int((r.y1 + pay) * sy) + 1)
        murekkep[y0:y1, x0:x1] = False

    murekkep[: int(ust * sy), :] = False                  # üst bilgi
    murekkep[int(alt * sy):, :] = False                   # alt bilgi
    sekil_kutulari = [a["kutu"] for a in sonuc]
    for b in govde_bloklari:
        if not any(b.intersects(k) for k in sekil_kutulari):
            sil(b)
    for a in sonuc + eslesmeyen:
        sil(a["alt_yazi_kutu"])
    # Kaba ızgara (hücre içinde mürekkep var mı)
    H, W = murekkep.shape
    hy, hx = max(1, int(hucre * sy)), max(1, int(hucre * sx))
    ny, nx = H // hy, W // hx
    izgara = murekkep[: ny * hy, : nx * hx].reshape(ny, hy, nx, hx).any(axis=(1, 3))
    if not izgara.any():
        return

    def hucrele(r):
        return (max(0, int(r.x0 / hucre)), max(0, int(r.y0 / hucre)),
                min(nx - 1, int(r.x1 / hucre)), min(ny - 1, int(r.y1 / hucre)))

    def bolgeler(aralik):
        """Mürekkebi 'aralik' pt'ye kadar boşlukları köprüleyerek bağlı bölgelere ayırır."""
        k = max(1, int(round(aralik / 2 / hucre)))
        gen = izgara.copy()
        for _ in range(k):                                 # yarıçap kadar genişlet (köprüle)
            g2 = gen.copy()
            g2[1:, :] |= gen[:-1, :]
            g2[:-1, :] |= gen[1:, :]
            g2[:, 1:] |= gen[:, :-1]
            g2[:, :-1] |= gen[:, 1:]
            gen = g2
        etiket = np.zeros(gen.shape, dtype=np.int32)
        n = 0
        for y0, x0 in zip(*np.nonzero(izgara)):
            if etiket[y0, x0]:
                continue
            n += 1
            q = deque([(y0, x0)])
            etiket[y0, x0] = n
            while q:
                y, x = q.popleft()
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < ny and 0 <= xx < nx and gen[yy, xx] and not etiket[yy, xx]:
                        etiket[yy, xx] = n
                        q.append((yy, xx))
        etiket[~izgara] = 0                                # yalnız gerçek mürekkep hücreleri
        return etiket, n

    def kutusu(etiket, i):
        ys, xs = np.nonzero(etiket == i)
        return pymupdf.Rect(xs.min() * hucre, ys.min() * hucre, (xs.max() + 1) * hucre, (ys.max() + 1) * hucre)

    def degen(etiket, r):
        x0, y0, x1, y1 = hucrele(r)
        return set(np.unique(etiket[y0:y1 + 1, x0:x1 + 1])) - {0}

    for aralik in PIKSEL_ARALIK:
        etiket, n = bolgeler(aralik)
        sahip = [degen(etiket, k) for k in sekil_kutulari]
        cakisma = any(sahip[i] & sahip[j] for i in range(len(sahip)) for j in range(i + 1, len(sahip)))
        if not cakisma or aralik == PIKSEL_ARALIK[-1]:
            break
    alinan = set()
    for i, a in enumerate(sonuc):
        bolge = set(sahip[i]) - set().union(*(sahip[j] for j in range(len(sahip)) if j != i)) if len(sahip) > 1 \
            else set(sahip[i])
        yeni = pymupdf.Rect(a["kutu"])
        marj = min((g.x0 for g in govde_bloklari), default=0)
        altyazilar_ = [s["alt_yazi_kutu"] for s in sonuc + eslesmeyen]
        for b in bolge:
            r = kutusu(etiket, b)
            # Kenar sütununda, bir alt yazının hemen altında duran küçük simge (kitabın vaka/örnek işareti)
            # şekle ait değildir — alınmaz.
            if r.x1 <= marj + 2 and r.width < 60 and r.height < 60 and not r.intersects(a["kutu"]) and \
                    any(0 <= r.y0 - c.y1 < 45 and min(r.x1, c.x1) - max(r.x0, c.x0) > -10 for c in altyazilar_):
                continue
            yeni |= r
        # Başka şeklin kutusuna girmesin. (Başka şeklin alt yazısı kutunun içinde kalırsa sorun değil:
        # _ust_uste_ayir iki şekli o alt yazının hizasından ayırır.)
        if not any(yeni.intersects(s["kutu"]) for s in sonuc if s is not a):
            a["kutu"] = yeni
        alinan |= bolge
    # Nesne aşamasında şekli bulunamayan alt yazılar: alt yazının hemen üstünde/altında/sağında duran,
    # başka şekle ait olmayan en yakın mürekkep bölgesi
    for a in eslesmeyen:
        ak = a["alt_yazi_kutu"]
        adaylar = []
        for b in set(np.unique(etiket)) - {0} - alinan:
            r = kutusu(etiket, b)
            if r.get_area() < 400:
                continue
            uzaklik = _altyazi_uzakligi(r, ak)
            if uzaklik is not None:
                adaylar.append((uzaklik, b, r))
        if adaylar:
            _, b, r = min(adaylar, key=lambda x: x[0])
            a["kutu"] = r
            alinan.add(b)



def _bosluk(a, b):
    return max(max(0, max(a.x0, b.x0) - min(a.x1, b.x1)), max(0, max(a.y0, b.y0) - min(a.y1, b.y1)))


def _tamamla(kutu, ogeler, n_yazi, govde_bloklari, diger_altyazilar, diger_sekiller):
    """Kırpma kutusunu, şekle ait olup dışarıda kalan her parçayı içine alacak şekilde büyütür:
    - kutunun kenarından taşan (kesilecek) her çizim/yazı,
    - kutuya 25 pt'den yakın her çizim/yazı (ör. oka değmeyen aktör figürü, altındaki etiket),
    - kutuyla aynı yükseklikte, yanında 90 pt içindeki çizimler (ör. kullanım durumu şemasının sağındaki aktör).
    Gövde metnine, başka şeklin alt yazısına ya da başka şekle değen parça alınmaz."""
    kutu = pymupdf.Rect(kutu)
    degisti = True
    while degisti:
        degisti = False
        for j, e in enumerate(ogeler):
            if kutu.contains(e):
                continue
            if any(e.intersects(g) for g in govde_bloklari) or any(e.intersects(g) for g in diger_altyazilar) \
                    or any(e.intersects(g) for g in diger_sekiller):
                continue
            bos = _bosluk(e, kutu)
            dikey_ortusme = min(e.y1, kutu.y1) - max(e.y0, kutu.y0)
            yan = j >= n_yazi and dikey_ortusme >= 0.6 * max(e.height, 1) and bos < 90
            if not (e.intersects(kutu) or bos < 25 or yan):
                continue
            yeni = kutu | e
            if any((yeni & g).get_area() > 0.3 * g.get_area() for g in govde_bloklari):
                continue                            # büyütmek gövde metnini içine alıyorsa alma
            kutu = yeni
            degisti = True
    return kutu


def kirp(sayfa, kutu, yol, dpi=SEKIL_DPI, pay=6, engeller=(), altyazilar=()):
    """Kutuyu 'pay' kadar genişletip kırpar. Kenar payına düşen gövde metni / alt yazı parçaları beyazlatılır
    (şeklin kendisine — kutunun içine — asla dokunulmaz)."""
    k = pymupdf.Rect(kutu)
    r = (k + (-pay, -pay, pay, pay)) & sayfa.rect
    pix = sayfa.get_pixmap(dpi=dpi, clip=r, alpha=False)
    olcek = dpi / 72
    beyaz = [(g, True) for g in engeller] + [(c, False) for c in altyazilar]
    for g, disari in beyaz:
        alan = (pymupdf.Rect(g) + (-1.5, -1.5, 1.5, 1.5)) & r
        for parca in (_fark(alan, k) if disari else ([alan] if not alan.is_empty else [])):
            ir = pymupdf.IRect(pix.x + int((parca.x0 - r.x0) * olcek), pix.y + int((parca.y0 - r.y0) * olcek),
                               pix.x + int((parca.x1 - r.x0) * olcek) + 1, pix.y + int((parca.y1 - r.y0) * olcek) + 1)
            ir &= pix.irect
            if not ir.is_empty:
                pix.set_rect(ir, (255,) * pix.n)
    pix.save(yol)


def _fark(a, b):
    """a dikdörtgeninin b dışında kalan kısmı (en çok 4 dikdörtgen)."""
    if a.is_empty:
        return []
    if not a.intersects(b):
        return [a]
    parcalar = [pymupdf.Rect(a.x0, a.y0, a.x1, b.y0), pymupdf.Rect(a.x0, b.y1, a.x1, a.y1),
                pymupdf.Rect(a.x0, max(a.y0, b.y0), b.x0, min(a.y1, b.y1)),
                pymupdf.Rect(b.x1, max(a.y0, b.y0), a.x1, min(a.y1, b.y1))]
    return [p for p in parcalar if p.width > 0 and p.height > 0]


# ============================================================
# Markdown üretimi
# ============================================================
RESIM_BAS = "<!-- Start of picture text -->"
RESIM_SON = "<!-- End of picture text -->"


def resim_metni_temizle(metin):
    """Şekil/resim içinden okunan metin bloklarını işler:
    - Anlamsız OCR çöpünü (bölüm açılış fotoğrafı gibi) tamamen siler,
    - Anlamlı olanları (şekil etiketleri) tutar ama işaretleri kaldırır."""
    def blok(m):
        icerik = m.group(1)
        tokenler = [t for t in re.split(r"<br>|\s+", icerik) if t]
        if not tokenler:
            return ""
        kelime = [t for t in tokenler
                  if re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü][a-zçğıöşü'’\-]{2,}[.,;:]?", t)]
        return "" if len(kelime) / len(tokenler) < 0.5 else icerik
    # Başlangıç işareti olsun olmasın, bitiş işaretine kadarki paragrafı ele al
    metin = re.sub(r"(?:" + re.escape(RESIM_BAS) + r"\s*)?([^\n]*?)\s*" + re.escape(RESIM_SON),
                   blok, metin)
    return metin.replace(RESIM_BAS, "")


def _duz(s):
    """Markdown biçimlendirmesini atıp düz metin bırakır (karşılaştırma için)."""
    return re.sub(r"\*\*|__|~~|</?u>|[#>`]", "", s).strip()


def sayfa_no_satirlarini_sil(metin, beklenen_no):
    """Sayfanın ilk/son 2 satırı içinden, o sayfanın basılı numarasını içeren
    KISA satırları siler: '2.1 ■ Software process models **45**',
    '**70 Chapter 2 ■ Software processes**', 'Contents 11' gibi."""
    if beklenen_no is None:
        return metin
    satirlar = metin.splitlines()
    dolu = [i for i, s in enumerate(satirlar) if s.strip()]
    kenar = set(dolu[:2] + dolu[-2:])
    hedef = str(beklenen_no)
    def ust_bilgi_mi(s):
        # Üst/alt bilgide sayfa no hep satırın BAŞINDA ya da SONUNDA durur:
        # '... models 45', '70 Chapter 2 ...', 'Contents 11', '4 Preface'
        d = _duz(s)
        if len(d) > 100:
            return False
        return bool(re.match(rf"^{hedef}(?!\d|\.\d)", d) or re.search(rf"(?<![\d.]){hedef}$", d))
    return "\n".join(s for i, s in enumerate(satirlar)
                     if not (i in kenar and ust_bilgi_mi(s)))


LISTE_MADDESI = re.compile(r"^(\d+\.|[-*•])\s")
BOLUM_BASLIGI = re.compile(r"^#{1,5}\s")          # gerçek bölüm/alt bölüm başlığı
KUTU_BASLIGI = re.compile(r"^######\s")          # kitaptaki yan kutu (sidebar) başlığı
SEKIL_ALTI = re.compile(r"^(Figure|Table|Şekil|Tablo)\s+(?:\d+|[A-Z])\.\d+\w*\s+[A-Z“\"(]")


def _kelime(p):
    return len(p.split())


def tamamlanmis(p):
    """Paragraf cümle sonu işaretiyle mi bitiyor? (sondaki tırnak/parantez/** atılır)"""
    s = re.sub(r"[\s*_”’\"')\]»]+$", "", p)
    return s.endswith((".", ":", "!", "?"))


def paragraf_turu(paragraflar, i):
    """'yuzen' (kutu içeriği dışında akışa ait olmayan: tablo, şekil, şekil altı,
    dipnot, URL), 'baslik', 'kutu' (yan kutu başlığı) ya da 'metin'."""
    p = paragraflar[i]
    if BOLUM_BASLIGI.match(p):
        return "baslik"
    if KUTU_BASLIGI.match(p):
        return "kutu"
    if (p.startswith("|") or "<br>" in p or p.startswith("<!--") or p.startswith("![")
            or re.match(r"^[*_`\s]*<[A-Za-z/]", p)            # XML/kod bloğu (şekil içeriği)
            or re.match(r"^>\s*[†‡*§]|^[†‡]", p)
            or re.fullmatch(r"(#+\s*)?https?://\S+(\s*/)?\s*", p)
            or (SEKIL_ALTI.match(p) and _kelime(p) <= 20)):
        return "yuzen"
    # Şekil etiketlerinin artığı: şekil/şekil altı yanındaki kısa, yarım satır
    # ('of testing', 'Tier 1. Presentation', 'systems engineering')
    if _kelime(p) <= 6 and not tamamlanmis(p) and not LISTE_MADDESI.match(p):
        komsular = [paragraflar[j] for j in (i - 1, i + 1) if 0 <= j < len(paragraflar)]
        if any(SEKIL_ALTI.match(k) or "<br>" in k for k in komsular):
            return "yuzen"
    return "metin"


def sayfalari_birlestir(sayfalar):
    """Sayfa sonunda yarım kalan cümleyi devamıyla birleştirir. Araya giren
    tablo, şekil, şekil altı yazısı, dipnot ya da yan kutu (sidebar) atlanır ve
    birleşen paragrafın SONRASINA kalır:
      '...fewer natural' + [kutu: History of SE] + 'resources, changing...'
      -> '...fewer natural resources, changing...' + [kutu]"""
    paragraflar = [p.strip() for s in sayfalar
                   for p in re.split(r"\n\s*\n", s) if p.strip()]
    turler = [paragraf_turu(paragraflar, i) for i in range(len(paragraflar))]

    cikti = []   # [metin, tür]
    for p, tur in zip(paragraflar, turler):
        if tur == "metin" and not LISTE_MADDESI.match(p):
            ilk = p.lstrip("_*“\"‘'(")[:1]
            kucuk_harf = ilk.islower()
            araya_giren, kutu_gecti, metin_gecti = 0, False, False
            j = len(cikti) - 1
            while j >= 0 and araya_giren <= 12:
                t, tt = cikti[j]
                if tt == "baslik":
                    break
                if tt in ("yuzen", "kutu"):
                    kutu_gecti |= tt == "kutu"
                    araya_giren += 1
                    j -= 1
                    continue
                if not tamamlanmis(t) and (_kelime(t) <= 6 or (j > 0 and cikti[j - 1][1] == "kutu")):
                    # Yarım ama kutuya ait: 'Case study: Group composition' gibi kısa
                    # başlık satırı ya da kutu başlığının hemen altındaki içerik
                    # ('Alice—self-oriented Brian—task-oriented ...'). Hedef olamaz.
                    if _kelime(t) <= 6:
                        kutu_gecti = True
                    else:
                        metin_gecti = True
                    araya_giren += 1
                    j -= 1
                    continue
                if not tamamlanmis(t):
                    # Küçük harfle devam: arada tamamlanmış metin geçildiyse bunlar
                    #   bir yan kutunun içinde olmalı (kutu başlığı görülmüş olmalı).
                    # Büyük harfle devam: yalnızca arada SADECE tablo/şekil varsa
                    #   ('...a Unified Modeling' + [şekil] + 'Language (UML)...').
                    if kucuk_harf:
                        uygun = not metin_gecti or kutu_gecti
                    else:
                        uygun = (ilk.isupper() and araya_giren > 0
                                 and not kutu_gecti and not metin_gecti)
                    if uygun:
                        cikti[j][0] = t.rstrip() + " " + p
                        p = None
                    break
                if not kucuk_harf:
                    break
                metin_gecti = True          # tamamlanmış paragraf: yan kutu içi olabilir
                araya_giren += 1
                j -= 1
        if p is not None:
            cikti.append([p, tur])
    return "\n\n".join(t for t, _ in cikti)


def buyuk_d_duzelt(metin):
    """Bazı yazı tiplerinde büyük 'D' PDF'e küçük 'd' olarak gömülür:
    'decisions made...' -> 'Decisions made...'. Sadece paragraf/madde başında
    ve nokta+boşluktan sonra gelen kelimelerde düzeltir ('doi:' hariç)."""
    metin = re.sub(r"(?m)^(\s*(?:[-*]\s+|\d+\.\s+)?)d(?=[a-z]{2,})(?!oi\b)", r"\1D", metin)
    return re.sub(r"(?<=[.!?] )d(?=[a-z]{2,})(?!oi\b)", "D", metin)


def _tuhaf_buyuk_harf(w):
    """'exerCiSeS', 'reFerenCeS', 'FuRTheR' gibi küçük-büyük harf karışıklığı."""
    if len(w) < 4 or w.isupper():
        return False
    if w[0].islower() and any(c.isupper() for c in w):
        return True
    return sum(1 for a, b in zip(w, w[1:]) if a.islower() and b.isupper()) >= 2


def son_duzeltmeler(metin):
    # Sayfa başındaki tekrar eden kocaman bölüm numarası: '# **2**'
    metin = re.sub(r"(?m)^#\s*\*\*\d+\*\*\s*$\n?", "", metin)
    # Başlıklardaki font kaynaklı harf karışıklığı: '##### **exerCiSeS**' -> 'Exercises'
    metin = re.sub(r"(?m)^#.*$", lambda m: re.sub(
        r"[A-Za-z]+", lambda w: w.group(0).capitalize() if _tuhaf_buyuk_harf(w.group(0))
        else w.group(0), m.group(0)), metin)
    # Şekil altı yazısının madde işaretine yapışması:
    # '- Figure 3.4 Extreme programming practices<sup>4.</sup> Change is...'
    metin = re.sub(r"\s*<sup>(\d+)\.</sup>\s*", r"\n\n\1. ", metin)
    metin = re.sub(r"(?m)^[-*]\s+((?:Figure|Table)\s+(?:\d+|[A-Z])\.\d+)", r"\1", metin)
    metin = re.sub(r"(?m)^[ \t]+(\d+\.\s)", r"\1", metin)
    # İçindekiler tek satıra sıkışmışsa maddelere ayır:
    # '17.1 Distributed systems 17.2 Client–server computing ...'
    def icindekiler(m):
        satirlar = []
        for satir in m.group(2).splitlines():
            satir = re.sub(r"^[-*]\s*", "", satir.strip())
            if not satir:
                continue
            for parca in re.split(r"\s+(?=\d{1,2}\.\d{1,2}\s)", satir):
                satirlar.append("- " + parca.strip())
        return m.group(1) + "\n\n".join(satirlar) + "\n\n"
    metin = re.sub(r"(?s)(#+\s*\**Contents\**\s*\n\n)((?:(?:[-*]\s*)?\d{1,2}\.\d{1,2}\s[^\n]*\n\n?)+)",
                   icindekiler, metin)
    return metin


def ust_alt_bilgi_temizle(sayfalar):
    """Sayfaların çoğunda tekrar eden KISA ilk/son satırları (üst/alt bilgi:
    sayfa no, bölüm adı) siler. Uzun satırlar (paragraflar) asla silinmez."""
    def norm(s):
        return re.sub(r"\d+", "#", s.strip().lower())
    def aday(s):
        return 0 < len(s.strip()) <= 100
    sayac = Counter()
    for metin in sayfalar:
        satirlar = [s for s in metin.splitlines() if s.strip()]
        for s in set(satirlar[:3] + satirlar[-3:]):
            if aday(s):
                sayac[norm(s)] += 1
    esik = max(3, len(sayfalar) // 4)
    tekrar = {k for k, v in sayac.items() if v >= esik}
    temiz = []
    for metin in sayfalar:
        satirlar = metin.splitlines()
        dolu = [i for i, s in enumerate(satirlar) if s.strip()]
        kenar = set(dolu[:3] + dolu[-3:])
        temiz.append("\n".join(s for i, s in enumerate(satirlar)
                               if not (i in kenar and aday(s) and norm(s) in tekrar)))
    return temiz


def dosya_adi(no, baslik):
    ad = re.sub(r'[\\/:*?"<>|]', "", baslik).strip()
    ad = re.sub(r"\s+", "_", ad)[:80] or f"Bolum_{no}"
    if isinstance(no, str):                           # kitap eki: "Ek_A_Başlık.md"
        return f"Ek_{no}_{ad}.md"
    return f"{no:02d}_{ad}.md"


def sayfalari_temizle(sayfa_metinleri, sayfa_indeksleri, kayma, ekler=None):
    """Tüm temizlik adımları, sırasıyla. Test edilebilsin diye ayrı fonksiyon.
    ekler: sayfa başına (önce, sonra) metinleri — sayfa işareti ve şekil bağlantıları. Üst/alt bilgi
    temizliğinden SONRA eklenir (işaret satırı üst bilgi penceresini kaydırmasın)."""
    sayfalar = []
    for idx, metin in zip(sayfa_indeksleri, sayfa_metinleri):
        metin = resim_metni_temizle(metin)
        beklenen = (idx - kayma + 1) if kayma is not None else None
        sayfalar.append(sayfa_no_satirlarini_sil(metin, beklenen))
    sayfalar = ust_alt_bilgi_temizle(sayfalar)
    sayfalar = [re.sub(r"\s*<sup>(\d+)\.</sup>\s*", r"\n\n\1. ", s) for s in sayfalar]
    sayfalar = [re.sub(r"(?m)^[-*]\s+((?:Figure|Table)\s+(?:\d+|[A-Z])\.\d+)", r"\1", s) for s in sayfalar]
    if ekler:
        sayfalar = [f"{once}\n\n{s}\n\n{sonra}".strip() for s, (once, sonra) in zip(sayfalar, ekler)]
    govde = sayfalari_birlestir(sayfalar)
    govde = buyuk_d_duzelt(govde)                          # birleştirmeden SONRA
    govde = re.sub(r"~~(\d+(?:\.\d+)*)~~", r"\1", govde)   # renkli bölüm no != üstü çizili
    govde = son_duzeltmeler(govde)
    govde = madde_isareti_duzelt(govde)
    return re.sub(r"\n{3,}", "\n\n", govde).strip()


BIRLESIK_ON = {"so", "self", "non", "multi", "well", "high", "low", "real", "cross", "user", "object",
               "safety", "mission", "business", "time"}   # "re-", "inter-" gibi hece önekleri bilerek yok
BIRLESIK_SON = {"based", "centric", "critical", "oriented", "driven", "called", "level", "stage", "scale",
                "specific", "wide", "intensive", "defined", "dependent", "independent", "known", "time",
                "term", "making", "sized", "free", "like", "off", "up", "in", "out", "aided", "related"}


def bas_harfleri(sayfa, govde_boyut):
    """Süslü baş harfler (drop cap): paragrafın ilk harfi birkaç satır yüksekliğinde ayrı yazılmıştır ("D" +
    "atabases and …"). Metin çıkarılırken bu harf yanlış satıra düşer ("essential Dcomponent"). Ölçüt: tek
    büyük harf, gövde puntosunun 2 katından büyük, hemen sağında küçük harfle başlayan bir satır.
    Döndürür: [(harf kutusu, harf, sağdaki satırın ilk kelimeleri)]."""
    d = sayfa.get_text("dict")
    satirlar = [(pymupdf.Rect(l["bbox"]), "".join(sp["text"] for sp in l["spans"]).strip())
                for b in d["blocks"] if b["type"] == 0 for l in b["lines"]]
    sonuc = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for sp in l["spans"]:
                t = sp["text"].strip()
                if not (len(t) == 1 and t.isalpha() and t.isupper() and sp["size"] > 2 * govde_boyut):
                    continue
                r = pymupdf.Rect(sp["bbox"])
                sag = sorted(((lr, lt) for lr, lt in satirlar
                              if -3 <= lr.x0 - r.x1 < 40 and r.y0 - 4 < lr.y0 < r.y1 and lt[:1].islower()),
                             key=lambda x: x[0].y0)
                if sag:
                    # Harfin kutusu alttaki tam genişlikli satıra taşabilir: silme alanı o satırın üstünde biter,
                    # sağdaki satırlara da değmez (yoksa komşu harfler de silinir).
                    alttaki = [lr.y0 for lr, _ in satirlar if lr.y0 > r.y0 + 2 and lr.x0 < r.x1 - 1 and lr.x1 > r.x0 + 1
                               and not (abs(lr.x0 - r.x0) < 1 and abs(lr.y0 - r.y0) < 1)]
                    alan = pymupdf.Rect(r.x0, r.y0, r.x1 - 1, min([r.y1] + [y - 0.5 for y in alttaki]))
                    sonuc.append((alan, t, " ".join(re.findall(r"\S+", sag[0][1])[:3])))
    return sonuc


def bas_harfleri_yerlestir(metin, bas_harfler):
    """Çıkarılan (redakte edilen) baş harfi kendi kelimesinin başına koyar: "atabases and database" →
    "Databases and database". Satır bulunamazsa metne dokunmaz."""
    for _, harf, parca in bas_harfler:
        desen = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in parca.split())
        metin = re.sub(desen, lambda m: harf + m.group(0), metin, count=1)
    return metin


def tire_duzelt(govde, ham_metin):
    """Satır sonunda bölünen BİRLEŞİK kelimelerin tiresi metin çıkarılırken yutuluyor:
    "service-⏎centric" → "servicecentric". Ham PDF metnindeki satır sonu tirelerine bakıp gerçek
    birleşik kelimelerin tiresini geri koyar. Hece bölmesine ("devel-⏎opment") dokunmaz.
    Birleşik sayılma ölçütü: ikinci parça büyük harfle başlıyor ve kelime metinde tek parça geçmiyor
    ("Addison-Wesley", "CD-ROM"; ama "DIF-FERENCE" değil), aynı kelime metinde
    satır içinde tireli geçiyor ya da ön/son ek listede."""
    satir_ici = set(re.findall(r"\b([A-Za-z]+-[A-Za-z]+)\b", ham_metin.replace("-\n", "")))
    # Satır içinde tek parça geçen kelimeler: "DIF-⏎FERENCE" metinde başka yerde "DIFFERENCE" olarak geçiyorsa
    # hece bölmesidir (büyük harf kuralı onu birleşik sanmasın); "CD-⏎ROM", "Addison-⏎Wesley" tek parça geçmez.
    tek_parca = set(re.findall(r"(?<![-\w])([A-Za-z]+)(?![-\w])", ham_metin))
    for a, b in sorted(set(re.findall(r"([A-Za-z]+)-\n\s*([A-Za-z]+)", ham_metin))):   # sıralı: çıktı her çalıştırmada aynı
        tireli = f"{a}-{b}"
        buyuk_harf = b[0].isupper() and a + b not in tek_parca
        if not (buyuk_harf or tireli in satir_ici or tireli.lower() in {t.lower() for t in satir_ici}
                or a.lower() in BIRLESIK_ON or b.lower() in BIRLESIK_SON):
            continue
        if a.lower() + b == "lifetime":          # yaygın tek kelimeler
            continue
        govde = re.sub(rf"\b{a}{b}\b", tireli, govde)
    return govde


def madde_isareti_duzelt(govde):
    """Bazı kitaplarda madde işareti (■) özel bir fontla basılır ve metne "I" olarak çıkar:
    "- I understand ...". Art arda en az 2 madde "I " ile başlıyorsa bu harf işarettir, silinir.
    Tek başına "- I think ..." gibi gerçek zamirlere dokunulmaz."""
    satirlar = govde.split("\n")
    maddeler = [i for i, l in enumerate(satirlar) if l.startswith("- ")]
    seri = []
    for i in maddeler + [None]:
        ardisik = seri and i is not None and all(not satirlar[k].strip() for k in range(seri[-1] + 1, i))
        if i is not None and re.match(r"- I [A-Za-z]", satirlar[i]) and (not seri or ardisik):
            seri.append(i)
            continue
        if len(seri) >= 2:
            for k in seri:
                satirlar[k] = "- " + satirlar[k][4:]
        seri = [i] if i is not None and re.match(r"- I [A-Za-z]", satirlar[i]) else []
    return "\n".join(satirlar)


def sekil_yazilari(sayfa, kutu, engeller=()):
    """Şeklin içindeki yazıları (kutu/etiket adları) PDF'ten metin olarak çıkarır: 'a · b · c'.
    Alt alta duran satırlar (ör. 'Requirements' + 'definition') tek etikette birleştirilir.
    Model etiketleri görselden okumak/tahmin etmek zorunda kalmaz."""
    satirlar = []
    for bl in sayfa.get_text("dict", clip=pymupdf.Rect(kutu) + (-2, -2, 2, 2))["blocks"]:
        for l in bl.get("lines", []):
            t = "".join(sp["text"] for sp in l["spans"]).strip()
            lr = pymupdf.Rect(l["bbox"])
            orta = pymupdf.Point((lr.x0 + lr.x1) / 2, (lr.y0 + lr.y1) / 2)
            if t and not any(pymupdf.Rect(e).contains(orta) for e in engeller):   # alt yazı / gövde metni değil
                satirlar.append([lr, t])
    satirlar.sort(key=lambda x: (x[0].y0, x[0].x0))
    etiketler = []                                   # [[kutu, metin]]
    for r, t in satirlar:
        for e in etiketler:
            ek, _ = e
            if -0.6 * r.height <= r.y0 - ek.y1 < 0.7 * r.height and abs((r.x0 + r.x1) / 2 - (ek.x0 + ek.x1) / 2) < 25:
                e[1] = e[1][:-1] + t if e[1].endswith("-") and t[:1].islower() else e[1] + " " + t
                e[0] = ek | r
                break
        else:
            etiketler.append([r, t])
    etiketler.sort(key=lambda e: (round(e[0].y0 / 8), e[0].x0))
    sonuc = []
    for _, t in etiketler:
        t = re.sub(r"\s+", " ", t).strip()
        if t not in sonuc:
            sonuc.append(t)
    return " · ".join(sonuc)[:1500]


def sekil_tablosu(sayfa, kutu):
    """Şekil aslında bir metin tablosuysa (ör. 'Workflow | Description') onu markdown tablo olarak döndürür;
    değilse None. Hücre metinleri PDF'teki kelimelerden yeniden kurulur (bitişik yazım, kopuk satır olmaz).
    İşaret/simge içeren matrisler (doluluk düşük) tablo sayılmaz — onlar görsel + yazı listesiyle kalır."""
    if len(sayfa.get_text("words", clip=pymupdf.Rect(kutu))) < 15:
        return None                                 # tablo sayılmak için zaten en az 15 kelime gerekir
    try:
        tablolar = sayfa.find_tables(clip=pymupdf.Rect(kutu) + (-2, -2, 2, 2)).tables
    except Exception:
        return None
    if not tablolar:
        return None
    # find_tables kırpma alanının dışındaki (komşu şeklin) tablosunu da döndürebilir: yalnız kutunun içindekiler
    tablolar = [x for x in tablolar if (pymupdf.Rect(kutu) + (-6, -6, 6, 6)).contains(pymupdf.Rect(x.bbox))]
    if not tablolar:
        return None
    t = max(tablolar, key=lambda x: pymupdf.Rect(x.bbox).get_area())
    ref = next((r for r in t.rows if all(r.cells)), None)
    if t.col_count < 2 or t.row_count < 3 or ref is None:
        return None
    sutunlar = [(c[0], c[2]) for c in ref.cells]
    kelimeler = sayfa.get_text("words", clip=pymupdf.Rect(t.bbox) + (-1, -1, 1, 1))
    satirlar, birlesik_satir = [], False
    for r in t.rows:
        y0, y1 = r.bbox[1], r.bbox[3]
        hucreler, satir_sayilari = [], []
        for x0, x1 in sutunlar:
            ws = sorted((w for w in kelimeler if x0 <= (w[0] + w[2]) / 2 < x1 and y0 <= (w[1] + w[3]) / 2 < y1),
                        key=lambda w: (round(w[1] / 3), w[0]))
            metin = " ".join(w[4] for w in ws)
            # hücredeki satırlardan BÜYÜK harfle başlayanlar (yeni bir öğe); sarılmış cümle küçük harfle sürer
            satir_basi = {}
            for w in ws:
                satir_basi.setdefault(round(w[1] / 3), w[4])
            satir_sayilari.append(sum(1 for t in satir_basi.values() if t[:1].isupper() or t[:1].isdigit()))
            # hücre içinde satır sonu tiresi: "off- site" → "off-site" (birleşik kelimenin tiresi korunur;
            # hece bölmesi olursa "devel-opment" kalır — anlam kaybı yok, uydurma kelime de oluşmaz)
            metin = re.sub(r"(\w)- ([a-z])", r"\1-\2", metin)
            hucreler.append(metin.replace("|", "/"))
        cok = [n for n in satir_sayilari if n >= 3]
        if len(cok) >= 2 and max(cok) - min(cok) <= 1 and len(set(cok)) <= 2 and min(cok) >= 3:
            birlesik_satir = True               # birkaç tablo satırı tek satıra yığılmış: güvenilmez
        if any(hucreler):
            satirlar.append(hucreler)
    if len(satirlar) < 2 or birlesik_satir:
        return None                             # güvenilmezse tablo yapma: görsel + yazı listesi kalır
    doluluk = sum(1 for r in satirlar for h in r if h) / (len(satirlar) * len(sutunlar))
    if doluluk < 0.6 or sum(len(h.split()) for r in satirlar for h in r) < 15:
        return None
    md = ["| " + " | ".join(satirlar[0]) + " |", "|" + "---|" * len(sutunlar)]
    md += ["| " + " | ".join(r) + " |" for r in satirlar[1:]]
    return "\n".join(md)


def _sekil_dosya_adi(sekil):
    return f"{'tablo' if sekil['tur'] == 'tablo' else 'sekil'}-{sekil['no'].replace('.', '-')}.png"


def bolum_sekilleri(doc, sayfa_listesi, no, govde, sekil_klasoru, uyarilar=None):
    """Bölümün bütün şekillerini bulur, kırpar (sekil_klasoru/), şekil içi yazıları/tabloları çıkarır.
    Döndürür: {sayfa_indeksi: [şekil, …]}. Uyarılar ekrana basılır ve 'uyarilar' listesine eklenir.
    kitap_paketle ve sekil_cikar aynı fonksiyonu kullanır (aynı dosya adları, aynı kırpma)."""
    uyarilar = [] if uyarilar is None else uyarilar

    def uyar(m):
        print(m)
        uyarilar.append(m.strip())

    sekiller, adlar = {}, set()
    for idx in sayfa_listesi:
        bulunan = sayfa_sekilleri(doc[idx], govde)
        for sk in [x for x in bulunan if x.get("bulunamadi")]:
            uyar(f"    ⚠ {'Tablo' if sk['tur'] == 'tablo' else 'Şekil'} {sk['no']} (PDF s. {idx + 1}): alt yazısı var "
                 f"ama şeklin kendisi bulunamadı — alt yazı metinde kaldı, bu şekli kitaptan kontrol et")
        bulunan = [x for x in bulunan if not x.get("bulunamadi")]
        if not bulunan:
            continue
        os.makedirs(sekil_klasoru, exist_ok=True)
        for sk in bulunan:
            dosya, n = _sekil_dosya_adi(sk), 2              # "Figure 4.13 (continued)" gibi tekrarlar ezilmesin
            while dosya in adlar:
                dosya = _sekil_dosya_adi(sk)[:-4] + f"-{n}.png"
                n += 1
            adlar.add(dosya)
            sk["dosya"], sk["sayfa"] = dosya, idx
            kirp(doc[idx], sk["kutu"], os.path.join(sekil_klasoru, dosya), engeller=sk.get("engeller", ()),
                 altyazilar=sk.get("altyazilar", ()))
            sk["tablo_md"] = sekil_tablosu(doc[idx], sk["kutu"])
            sk["yazilar"] = None if sk["tablo_md"] else sekil_yazilari(doc[idx], sk["kutu"], sk.get("engeller", ()))
            if sk.get("kenar_uyari"):
                uyar(f"    ⚠ Şekil {sk['no']} (PDF s. {idx + 1}): yanında şekle alınmamış bir çizim var — "
                     f"sekiller/{dosya} dosyasına bir göz at")
        sekiller[idx] = bulunan
    # Bütünlük: metinde adı geçen ama kırpılmamış şekil/tablo var mı? ("Figure 7.3 shows…")
    bulunan_nolar = {sk["no"] for v in sekiller.values() for sk in v}
    anilan = set()
    for idx in sayfa_listesi:
        anilan |= {m.group(2) for m in re.finditer(r"\b(Figure|Fig\.|Table|Şekil|Tablo)\s+((?:\d+|[A-Z])\.\d{1,2})(?!\d)", doc[idx].get_text())
                   if m.group(2).split(".")[0] == str(no)}
    eksik = sorted(anilan - bulunan_nolar, key=lambda x: [int(p) for p in x.split(".")])
    if eksik:
        uyar(f"    ⚠ Metinde adı geçen ama kırpılamayan şekil/tablo: {', '.join(eksik)} — kitaptan kontrol et")
    return sekiller


def bolumu_yaz(doc, kitap_adi, no, baslik, bas, bit, klasor, kayma=None, govde=None):
    sayfa_listesi = list(range(bas, bit + 1))
    ad = dosya_adi(no, baslik)[:-3]
    klasor = os.path.join(klasor, ad)                 # her bölüm kendi klasöründe
    shutil.rmtree(klasor, ignore_errors=True)
    os.makedirs(klasor)
    sekil_klasoru = os.path.join(klasor, "sekiller")

    # 1) Şekilleri bul, kırp; metinden çıkarmak için bölgelerini karart (redaksiyon) — böylece şekil içi
    #    etiketler ("Requirements definition", "Locate error") metne karışmaz.
    govde = govde or govde_fontu(doc, sayfa_listesi)
    kopya = pymupdf.open(doc.name)
    sekiller = bolum_sekilleri(doc, sayfa_listesi, no, govde, sekil_klasoru)
    # Süslü baş harfler metinden çıkarılır, sonra kendi kelimesinin başına geri konur (yanlış satıra düşmesin)
    bas_harfler = {}
    for idx in sayfa_listesi:
        bh = bas_harfleri(doc[idx], govde[1])
        if bh:
            bas_harfler[idx] = bh
            for r, _, _ in bh:
                kopya[idx].add_redact_annot(r)
            if idx not in sekiller:
                kopya[idx].apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
    for idx, bulunan in sekiller.items():
        for sk in bulunan:
            for kutu in (sk["kutu"], sk["alt_yazi_kutu"]):
                kopya[idx].add_redact_annot(pymupdf.Rect(kutu) + (-2, -2, 2, 2))
        try:
            kopya[idx].apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        except (TypeError, AttributeError):
            kopya[idx].apply_redactions()

    # 2) Metin (şekiller çıkarılmış kopyadan)
    try:
        parcalar = pymupdf4llm.to_markdown(kopya, pages=sayfa_listesi, page_chunks=True, show_progress=False)
        sayfalar = [p["text"] for p in parcalar]
    except Exception:
        sayfalar = [kopya[i].get_text() for i in sayfa_listesi]   # yedek: düz metin

    # 3) Sayfa işareti + şekil bağlantıları: şekil sayfanın üst yarısındaysa sayfa başına, değilse sonuna
    ekler = []
    for idx in sayfa_listesi:
        basili = (idx - kayma + 1) if kayma is not None else None
        isaret = f"<!-- PDF s. {idx + 1}" + (f" · kitap s. {basili}" if basili else "") + " -->"
        once, sonra = [isaret], []
        for sk in sekiller.get(idx, []):
            etiket = ("Table" if sk["tur"] == "tablo" else "Figure") + f" {sk['no']}: {sk['baslik']}".rstrip(": ")
            satir = f"![{etiket}](sekiller/{sk['dosya']})"
            if sk.get("tablo_md"):
                satir += f"\n\n<!-- Şekil {sk['no']} bir metin tablosu; içeriği PDF'ten aşağıda: -->\n\n{sk['tablo_md']}"
            elif sk.get("yazilar"):
                satir += f"\n\n<!-- Şekil {sk['no']} içindeki yazılar (PDF'ten): {sk['yazilar']} -->"
            (once if (sk["kutu"].y0 + sk["kutu"].y1) / 2 < doc[idx].rect.height / 2 else sonra).append(satir)
        ekler.append(("\n\n".join(once), "\n\n".join(sonra)))
    govde_md = sayfalari_temizle(sayfalar, sayfa_listesi, kayma, ekler)
    govde_md = tire_duzelt(govde_md, "".join(doc[i].get_text() for i in sayfa_listesi))
    govde_md = bas_harfleri_yerlestir(govde_md, [x for i in sorted(bas_harfler) for x in bas_harfler[i]])

    etiket = f"Ek {no}" if isinstance(no, str) else "Sözlük" if no == 99 else f"Bölüm {no}"
    sekil_sayisi = sum(len(v) for v in sekiller.values())
    ust = (f"# {etiket}: {baslik}\n\n"
           f"> Kaynak: {kitap_adi} — PDF sayfa {bas + 1}–{bit + 1}"
           + (f" (kitap s. {bas - kayma + 1}–{bit - kayma + 1})" if kayma is not None else "")
           + f" · {sekil_sayisi} şekil/tablo\n\n")
    yol = os.path.join(klasor, ad + ".md")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(ust + govde_md + "\n")
    n_parca = parcalari_yaz(yol, kitap_adi, etiket, baslik)
    talimat_yaz(klasor, ad, etiket, baslik, n_parca)
    kelime = len(re.sub(r"<!--.*?-->", "", govde_md).split())
    print(f"  ✓ {os.path.basename(yol):50s} s.{bas + 1}–{bit + 1}  (~{kelime:,} kelime, {sekil_sayisi} şekil)")
    return yol


# ============================================================
# Terim sözlüğü — kalıcı tercihler (eski çalışmalardan; düzeltilenler "yanlış:" ile)
# Yalnızca bölüm metninde geçen terimler o bölümün promptuna eklenir. Yeni tercihleri buraya ekle.
# ============================================================
TERIMLER = [
    # --- Süreç ve modeller (Bölüm 4)
    ("software process", "yazılım süreci", ""),
    ("process model", "süreç modeli", ""),
    ("specification", "belirtim", "software specification: yazılımın belirtilmesi"),
    ("implementation", "gerçekleştirim", ""),
    ("validation", "geçerleme", "verification ile karıştırma"),
    ("verification", "doğrulama", "validation ile karıştırma"),
    ("evolution", "evrim", "software evolution: yazılımın evrimi"),
    ("waterfall model", "şelale modeli", ""),
    ("evolutionary development", "evrimsel geliştirme", ""),
    ("exploratory development", "keşfedici geliştirme", "yanlış: keşif amaçlı geliştirme"),
    ("throw-away prototyping / throwaway prototyping", "geçici prototipleme", "yanlış: atılacak prototipleme"),
    ("formal development", "biçimsel geliştirme", ""),
    ("component-based software engineering", "bileşen temelli yazılım mühendisliği", ""),
    ("iteration", "yineleme", "increment ile karıştırma"),
    ("increment", "artım", "işlevselliğin teslim edilen bir bölümü"),
    ("incremental delivery", "artımlı teslim", ""),
    ("spiral model", "spiral model", ""),
    ("process standardisation", "süreç standardizasyonu", ""),
    ("critical systems", "kritik sistemler", ""),
    ("agile", "çevik", ""),
    ("extreme programming", "aşırı programlama (XP)", "yanlış: uç programlama"),
    # --- Faaliyetler ve araçlar
    ("requirements engineering", "gereksinim mühendisliği", ""),
    ("feasibility study", "fizibilite (yapılabilirlik) çalışması", ""),
    ("elicitation and analysis", "ortaya çıkarma ve analiz", ""),
    ("architectural design", "mimari tasarım", ""),
    ("interface specification", "arayüz belirtimi", ""),
    ("debugging", "hata ayıklama", ""),
    ("component testing", "bileşen testi", ""),
    ("system testing", "sistem testi", ""),
    ("acceptance testing", "kabul testi", ""),
    ("alpha testing", "alfa testi", "müşteriyle sistemin kabul edilebilirliğini değerlendirme; yanlış: geliştirici tarafında deneme"),
    ("beta testing", "beta testi", "potansiyel müşterilerde gerçek kullanım ortamında deneme"),
    ("inception", "başlangıç", "RUP evresi"),
    ("elaboration", "ayrıntılandırma", "RUP evresi; yanlış: olgunlaştırma"),
    ("construction", "inşa", "RUP evresi; yanlış: yapım"),
    ("transition", "geçiş", "RUP evresi"),
    ("static view / dynamic view", "statik görünüm / dinamik görünüm", "yanlış: durağan görünüm"),
    ("workflow", "iş akışı", "RUP evresiyle aynı sınıflandırma değil"),
    ("CASE / computer-aided software engineering", "bilgisayar destekli yazılım mühendisliği (CASE)", ""),
    ("workbench", "çalışma tezgâhı", "tool: araç, environment: ortam"),
    ("process-centred environment / process-centered environment", "süreç merkezli ortam", ""),
    # --- Proje yönetimi (Bölüm 5)
    ("project management", "proje yönetimi", ""),
    ("project planning", "proje planlama", ""),
    ("project scheduling / scheduling", "proje zaman çizelgeleme / zaman çizelgeleme", "planlama ile eşitleme"),
    ("project schedule", "proje zaman çizelgesi", ""),
    ("proposal", "teklif", ""),
    ("project monitoring", "proje izleme", ""),
    ("project review", "proje gözden geçirmesi", ""),
    ("milestone", "kilometre taşı", "tanınabilir ve raporlanabilir faaliyet bitişi"),
    ("deliverable", "teslim edilecek çıktı", "müşteriye verilen proje sonucu"),
    ("work breakdown", "işin faaliyetlere ayrılması", ""),
    ("activity network / activity chart", "faaliyet ağı / faaliyet çizelgesi", ""),
    ("bar chart / Gantt chart", "çubuk grafik / Gantt grafiği", ""),
    ("critical path", "kritik yol", "proje bitişini belirleyen zincir; 'kritik'i 'en önemli' diye kullanma"),
    ("float / slack", "esneklik payı", ""),
    ("resource allocation", "kaynak dağılımı", ""),
    ("staff allocation", "personel ataması", ""),
    ("risk management", "risk yönetimi", ""),
    ("project risk", "proje riski", "neyi etkiliyor? sınıfı"),
    ("product risk", "ürün riski", "neyi etkiliyor? sınıfı"),
    ("business risk", "iş riski", "neyi etkiliyor? sınıfı"),
    ("risk identification", "riskleri belirleme", ""),
    ("risk analysis", "risk analizi", ""),
    ("risk planning", "risk planlama", ""),
    ("risk monitoring", "risk izleme", ""),
    ("avoidance strategy / avoidance strategies", "kaçınma stratejisi", ""),
    ("minimisation strategy / minimisation strategies", "etkiyi azaltma stratejisi", ""),
    ("contingency plan / contingency plans", "yedek plan", ""),
    ("contingency", "beklenmedik durum payı", "planlama bağlamında; contingency plan = yedek plan"),
    ("technology risks", "teknoloji riskleri", "nereden doğuyor? sınıfı"),
    ("people risks", "insan riskleri", ""),
    ("organisational risks", "kuruluş riskleri", ""),
    ("tools risks", "araç riskleri", ""),
    ("requirements risks", "gereksinim riskleri", ""),
    ("estimation risks", "tahmin riskleri", ""),
    ("intangible / intangibility", "somut olmayan / somut olmama", ""),
    ("quality plan", "kalite planı", ""),
    ("validation plan", "geçerleme planı", ""),
    ("configuration management plan", "yapılandırma yönetimi planı", ""),
    ("maintenance plan", "bakım planı", ""),
    ("staff development plan", "personel geliştirme planı", ""),
    ("traceability", "izlenebilirlik", ""),
    ("information hiding", "bilgi gizleme", ""),
    ("catastrophic / serious / tolerable / insignificant", "yıkıcı / ciddi / katlanılabilir / önemsiz", "risk etkisi düzeyleri"),
]


def bolum_terimleri(metin):
    """TERIMLER içinden bölüm metninde geçenleri prompt satırları olarak döndürür."""
    satirlar = []
    for en, tr, notu in TERIMLER:
        varyantlar = [v.strip() for v in en.split("/") if v.strip()]
        for v in varyantlar:
            desen = re.escape(v).replace("isation", "i[sz]ation").replace("centred", "cent(?:red|ered)")
            if re.search(rf"(?i)(?<![A-Za-z]){desen}", metin):
                satirlar.append(f"- {en} → {tr}" + (f" ({notu})" if notu else ""))
                break
    return "\n".join(satirlar)


# ============================================================
# LLM parçaları — çalışma sözleşmesi (kullanıcının eski sohbetteki istek ve revizyonlarından)
# ============================================================
PROMPT_SABLONU = """Bir ders kitabından ("{kitap}", {etiket}: {baslik}) bir parçayı Türkçe çalışma dokümanına dönüştürüyorsun. Bu parça: {aralik} ({parca_no}/{parca_sayisi}. parça).
{gorsel_notu}
AMAÇ: Okuyucu kitabın İngilizcesini rahat okuyamayan bir bilgisayar mühendisliği öğrencisi. İngilizcesi mükemmel olsaydı kitabı okurken edineceği kavrayışın aynısını edinmeli: anlatılanı kendi cümleleriyle açıklayabilmeli, benzer kavramları ayırt edebilmeli, bir örnek durumda kullanabilmeli. Başarı ölçütü sayfa sayısı değil, bu açıklık. Token tasarrufu için kısaltma, özetleme ya da sayfa birleştirme YAPMA.

Bölümün ana hatları (bağlam için; yalnızca bu parçadaki sayfaları işle):
{ana_hatlar}

Metindeki <!-- PDF s. … --> satırları kaynak sayfaların başlangıcını gösterir. Her kaynak sayfa ayrı bir öğretim birimidir; sayfaya özgü fikri genel bir anlatıma eritme. HER kaynak sayfa için tam olarak şu yapıyı üret:

# Kitap s. Y • <sayfanın fikrini ya da sorusunu söyleyen kısa Türkçe başlık; konu etiketi değil ("Şelale evreleri" değil, "Şelale evreleri ve erken kararların bedeli")>
Kaynak: PDF s. X / kitap s. Y.

## A • Tam çeviri
<sayfanın sadık ve eksiksiz çevirisi; şekil varsa bağlantı değil, yalnızca "Şekil N - Ad. <etiket dökümü>" satırı>

## C • Şimdi bunu anlayalım
**Ek açıklama:** <ilk paragraf>

![…](….png)   ← sayfada şekil varsa: kaynaktaki bağlantının AYNISI, tek başına bir satırda

<şekli okutan ve kavramı açan paragraflar (etiketsiz)>

---PAGE---

A • TAM ÇEVİRİ — "Kitap ne diyor?"
- Sayfanın TAMAMINI çevir: seçilmiş kritik cümleler ya da özet değil. Başlıkları (numaralarıyla: "4.1.2 Evrimsel geliştirme (Evolutionary development)"), maddeleri, numaralı listeleri, tabloları, koşulları, istisnaları, neden-sonuç bağlarını ve örnekleri koru.
- Teknik terimin İngilizce aslını ilk geçtiği yerde parantezde ver: yazılım süreci (software process). Aşağıdaki terim listesine uy.
- Kaynaktaki ihtiyatı, belirsizliği ve varsayımı koru ("olabilir", "genellikle", "bence"). Yazarın birinci tekil anlatımını koru ("…Bölüm 28'de ele alıyorum"). Nicelikleri değiştirme (hız ≠ süre, olasılık ≠ etki).
- Kaynakta olmayan hiçbir şeyi A'ya ekleme: yorum, güncel bilgi, düzeltme, genel kural yok. Kaynaktaki varsayımsal örneği sessizce düzeltme; sınırını C'de açıkla.
- Şekil bağlantısını (![…](….png)) A'ya KOYMA; aynen C'ye taşı (aşağıya bak). A'da, şeklin metindeki yerinde, şeklin çevirisini yaz: "Şekil 4.2 - Evrimsel geliştirme. <şekildeki kutu/etiket/ok adlarının Türkçesi, İngilizcesi parantezde>". Şekildeki yazılar bağlantının altındaki "<!-- Şekil … içindeki yazılar (PDF'ten): … -->" satırında metin olarak var; etiketleri oradan al, görselden okumaya çalışma. Orada da görselde de olmayan bir etiketi tahmin etme. Okların yönünü ve şeklin düzenini görselden oku. Şekil bir metin tablosuysa içeriği bağlantının altında markdown tablo olarak verilmiştir: A'da o tabloyu aynı satır/sütun yapısında, hücre hücre çevir (özetleme, satır atlama yok).
- Sayfa sonunda bölünen cümleyi bu sayfada tamamla ve A'nın sonuna yaz: "Çeviri notu: Son cümle PDF s. Z / kitap s. W'deki devamıyla tamamlandı." Bir sonraki sayfa o cümlenin devamıyla başlıyorsa onu tekrar çevirme, oradan devam et.
- Kitabın dönemine ait ifadeler ("bugün", "önümüzdeki yıllarda", teknoloji öngörüleri) varsa Çeviri notu'nda "kitabın yazıldığı dönemin değerlendirmesidir" diye belirt; güncel gerçek gibi genişletme.
- Kaynakta okunamayan ya da eksik görünen kısım varsa tahminle doldurma; açıkça yaz.

C • ŞİMDİ BUNU ANLAYALIM — "Bunu nasıl anlayıp kullanmalıyım?" (her sayfada ZORUNLU)
Ölçüt: Öğrenci C'yi okuyunca kavramı kendi cümleleriyle açıklayabilmeli, benzerinden ayırabilmeli ve örnekte sonucun NEDEN öyle olduğunu gösterebilmeli. Aşağıdaki kurallar bu ölçüte hizmet eder.
- A'yı özetleme. A'da açık kalan düşünme basamaklarını tamamla: hangi problem var, kavram nasıl işliyor, sonuç neden böyle, hangi koşulda yetersiz kalır, benzer kavramdan farkı ne. Bunları başlık listesine çevirme; bağlantılı düzyazı kur. Kaynakta tek cümle olan bir fikri gerekirse birkaç paragrafla aç.
- ÖRNEK: Başlangıç durumunu, kararı ya da değişikliği ve sonucunu göster; kavramın adını örneğe yapıştırmakla yetinme. Bölüm boyunca TEK bir ortak örnek kullan (TALIMAT'taki plan.md'de yazılı; plan.md yoksa ilk parçada sen seç ve sonraki parçalarda aynısını kullan). Ortak örnek bir kavramı zorluyorsa kısa başka bir örnek kullan. Kitabın kendi örneğinin neyi göstermek istediğini ve adımlarını açıklamayı ihmal etme; sayısal hesap varsa adımları ve dayandığı tablo/şekli yaz.
- KARIŞIKLIK: Gerçek bir yanlış okuma riski varsa yanlış yorumu adıyla söyle ve nedeniyle düzelt ("'Geçici' sözcüğü boşa gitti demek değildir; …"). Karışabilecek iki kavramı aynı yerde, zıt bir örnekle ayır. Aynı kalıbı her sayfada tekrarlama; risk yoksa zorlama. Alternatif yaklaşımlar karşılaştırılıyorsa küçük bir tablo kullanabilirsin (güçlü yanı / sınırlılığı / uygun koşul).
- ŞEKİL: Sayfada şekil varsa bağlantısını C'nin ilk paragrafından sonra tek başına bir satırda ver. Önce görseli gerçekten incele; sonra nereden okunmaya başlanacağını, kutuların, okların ve geri dönüşlerin ne anlattığını ve şeklin metindeki fikri nasıl gösterdiğini anlat. Etiketleri sıralamakla yetinme; görselde olmayan ilişki ya da ok ekleme; yönünden emin olmadığın oku "belirsiz" diye yaz. Öz ol: şekli adım adım izlerken ana ilişkiyi kaybettirecek kadar uzatma. Farklı şekil/tabloların verilerini birbirine karıştırma.
- KALIN: Her C'de etiketler dışında anlam taşıyan kalın vurgu olmalı: sayfanın ana çıkarımı ya da kritik ayrımı kalın bir cümle olur; şekil varsa okuma yönünü veren cümle de kalın olur. Seçici ol; paragrafın tamamını kalın yazma.
- BİTİŞ: "Sonraki sayfada X'i göreceğiz" gibi salt konu duyurusu YASAK (kontrol aracı işaretler). Sayfa sonlarını tek kalıba da bağlama; her sayfa "…malısın / …gerekir" öğüdüyle bitmesin. Sayfanın ihtiyacına göre bazen bir sonuç taşı ("… ise …; değilse …"), bazen açık kalan bir soru sor, bazen sonraki konunun neden gerekli olduğunu gerekçesiyle söyle.
- ETİKET: "**Ek açıklama:**" yalnızca C'nin ilk paragrafında bulunur; sonraki paragraflar etiketsiz devam eder. Kitapta olmayan örnek ve yorumları paragraf düzeyinde "**Ek örnek:**", kaynak dışı güncel/dış bilgiyi ve kaynaktaki metin-şekil tutarsızlıklarını "**Ek not:**" ile ayır; her cümleye etiket ekleme. Tutarsızlığı sessizce düzeltme.
- UZUNLUK: C'nin uzunluğunu A'ya göre kısıtlama; genellikle A'ya yakındır, zor bir sayfada daha uzun olur. Dolgu cümlesi yazma. Son sayfaların C'leri ilk sayfalar kadar özenli olur.
- ÜSLUP: Sade, doğrudan, teknik olarak doğru Türkçe. Her zaman "sen" diye hitap et ("oku", "dikkat et", "izle"); "okuyun", "bakın" gibi "siz" biçimi kullanma. Küçümseme, yapay övgü, aşırı basitleştirme yok.

STİL ÖRNEĞİ (başka bir kitabın başka bir bölümünden; konuyu, cümleleri ve örnekleri KOPYALAMA, düşünme biçimini ve kalın kullanımını gör):
**Ek açıklama:** Bazen müşteri ihtiyacını yalnızca konuşarak tam anlatamaz; bir şey kullanınca neyin eksik olduğunu fark eder. Evrimsel geliştirme bu öğrenmeyi sürecin içine alır: ilk çalışan örnek sonraki gereksinimlerin öğrenilmesini sağlar.
<şekil bağlantısı>
**Şekilde ortadaki üç faaliyetin arasındaki çift yönlü bağlantılara bak.** Belirtimden geliştirmeye gidilip bir daha dönülmeyen bir sıra yok. Kullanıcıya gösterilen sürümden geri bildirim alınır; ne yapılacağı ve yapılanın yeterliliği birlikte netleşir.
**İki türün farkı, ilk örneğin sonradan ne olacağıdır.** Keşfedici geliştirmede başlangıç sistemi teslim edilecek ürüne dönüşür; geçici prototiplemede asıl kazanç gereksinimi öğrenmektir.
**Ek örnek:** Ders kayıt kurallarını bildiğin için çalışan bir başlangıç geliştirip sürdürüyorsan keşfedici geliştirmeye yaklaşırsın. Öğrencilerin hangi ekranı anlayacağını öğrenmek için geçici bir arayüz deniyorsan amaç bilgi kazanmaktır.
"Geçici" sözcüğü yapılan işin boşa gittiği anlamına gelmez: atılan şey kod olabilir, kazanılan anlayış sonraki tasarımı yönlendirir. Peki sürekli değiştirilen bir ürünün yapısı nasıl korunacak?

KURALLAR
- A = yalnızca kaynak. Senin eklediğin her şey C'de ve etiketli ("Ek açıklama", "Ek örnek", "Ek not", "Çeviri notu").
- Kitapta olmayan şema, tablo ya da görsel üretme. Ek hesap ya da ek tablo yaparsan kitaptan olmadığını yaz.
- Terimler bu parça boyunca ve önceki parçalarla tutarlı olsun. Aşağıdaki kalıcı terim tercihlerini A'da, C'de ve tablolarda AYNEN kullan; kendi karşılığını koyma. "yanlış:" yazan karşılıklar kontrol aracında hata olarak işaretlenir:
{terimler}
- Parçanın en sonuna, bu parçada geçen terimler için tablo ekle: | İngilizce terim | Türkçe karşılık | Kısa açıklama ve kaynak (PDF s. / kitap s.) |
{ozel_not}
KAYDETMEDEN ÖNCE (kendi içinde kontrol et; eksik varsa düzelt, sonra kaydet):
- Her kaynak sayfada A ve C var; A eksiksiz çeviri; şekil bağlantısı C'de.
- Her C sonucun NEDEN oluştuğunu açıklıyor; A'yı özetlemiyor; ortak örnek tutarlı.
- Her C'de etiket dışı anlam taşıyan kalın cümle var; "**Ek açıklama:**" yalnız ilk paragrafta.
- Hiçbir C "Sonraki sayfada … göreceğiz" diye bitmiyor; bitişler tek kalıpta değil; "sen" hitabı.
- Son sayfanın C'si ilk sayfalarınki kadar özenli.

=== KAYNAK METİN ===

{metin}
"""

ILK_PARCA_NOTU = """- Bu ilk parça. İlk sayfada:
  · Kaynak satırının sonuna kitabın adını ve baskısını ekle.
  · A'da bölüm başlığını, amaçları (Objectives) "Bölümü okuduğunda: … anlayacaksın" biçiminde ve içindekileri çevir.
  · C'de bölümün genel tanıtımını yap: bölüm hangi gerçek problemi çözmek için var, hangi soruya cevap arıyor, hangi sırayla ilerleyecek. Bölümün ortak örneğini burada kısaca tanıt. Ardından "**Okuma düzeni:**" (her sayfada A tam çeviri, C kaynak dışı öğretici açıklama; ek açıklamalar etiketli, terimler parantezde, sözlük-tekrar-sorular sonda) ve "**Kaynak notu:**" (kapsam: PDF/kitap sayfa aralığı; metindeki dönem ifadeleri güncel iddia değildir) paragraflarını yaz.
"""

SON_PARCA_NOTU = """- Bu son parça. Bölümün son kaynak sayfasının C'sine, bölümün ana kavramlarını ortak örnekte birleştiren kısa bir sentez paragrafı ekle. Sentezde yalnızca kavramları sıralama: bölüm alternatif yöntemler veya yaklaşımlar içeriyorsa hangisinin hangi koşulda seçileceğini de ortak örnek üzerinden bağla.
"""

SON_PROMPT = """"{kitap}" kitabının {etiket} ({baslik}) bölümünün sayfa sayfa Türkçe çevirisi ve anlatımı tamamlandı.
Şimdi bölümün SONUNA eklenecek tekrar kısmını üret. Kitapta olmayan bilgiyi kitaptanmış gibi yazma. Her bölümün ilk
satırı "Ek çalışma notu. Dayanak: PDF s. a-b / kitap s. c-d." olsun; maddelerin sonuna ilgili "Kaynak: PDF s. / kitap s."
yaz. Her başlık yeni sayfada başlasın (araya ---PAGE--- koy). Üslup parçalardakiyle aynı ("sen" hitabı, sade, doğrudan).

# Kavramları ayırt et • <alt başlık>
Bölümde birbirine karıştırılabilecek yaklaşımları/kavramları tablolarla karşılaştır:
| Kavram (English) | Güçlü yanı ve uygun koşul | Sınırlılığı / bedeli |
Tablonun altına "Karışan nokta:" paragraflarıyla sık yapılan yanlış yorumları ve farkı nasıl anlayacağını yaz.
"Uygun koşul" kesin bir seçim kuralı değil, gerekçenin başlangıcıdır — bunu belirt.
---PAGE---
# Temel kavramlar sözlüğü • <tema>
Bütün terimleri tekrarsız, konu temalarına göre gruplanmış tablolarda topla: | İngilizce terim | Türkçe karşılığı | Kısa açıklama |
Parçalarda kullanılan Türkçe karşılığı aynen kullan (aynı terim için tek karşılık). Sözlüğü yalnız karşılık listesine indirme; açıklama yaz.
---PAGE---
# Tekrar notları • Bölümün omurgası
"Ek tekrar aracı; yeni konu içermez." Bölümün omurgasını sırasıyla, her biri 1-2 cümlelik, tekrar edilebilir maddelerle ver;
her maddede bir "karıştırma" uyarısı ya da bağlantı olabilir. Her madde sonunda kaynak sayfa.
---PAGE---
# Kendini test et • Önce sen cevapla
"Ek çalışma soruları. Kitabın sorularından ayrı olarak hazırlanmıştır. Cevaplar sonraki bölümde."
6-8 soru. Tanım sorma; senaryo, iddia düzeltme, karşılaştırma ve uygulama iste. Her sorunun başına türünü kalın yaz —
"**Neden?**", "**Farkı ne?**", "**Hangisini seçerdin?**", "**İddiayı düzelt:**", "**Uygulama:**". Mümkünse senaryoyu bölümün ortak örneğine kur.
Soruların altına puanlama ölçütü ekle: 0 = kavramlar karışmış; 1 = doğru sonuç, gerekçe eksik; 2 = doğru sonuç, açık gerekçe ve ilgili sınır.
Cevapları buraya YAZMA.
---PAGE---
# Kendini test et • Cevaplar
"Ek açıklama: Bunlar örnek cevaplardır; ezberlenecek tek bir ifade değildir." Cevap biçimi sorunun türüne uysun; her cevapta
gerekçe, ilgili koşul ve kaynak sayfa olsun. Seçim sorusunda "Şunu seçiyorum; çünkü …; şu koşul değişirse …" kalıbını kullan.
Senaryo kitaptan değilse "… ek nottur" de.
---PAGE---
# Kitabın alıştırmaları • Örnek çözümler
"Ek öğretim notu. Sorular: PDF s. … / kitap s. … Bunlar resmî cevap anahtarı değil, örnek çözümlerdir."
Bölüm sonundaki her alıştırma (Exercises) için: "4.4 - <kısa başlık>. <çözüm> Dayanak: PDF s. / kitap s." Alıştırma bir şekle
dayanıyorsa şeklin bağlantısını (sekiller/ içinden, ![…](sekiller/….png)) tekrar koy ve nasıl okunacağını yaz. Ayrıntısı
verilmeyen dış vakaları uydurma; yöntem ve gerekçeyle sınırlı kal. Varsayımlarını açıkça yaz ve kararı değiştirecek koşulu belirt.
Gerçek gözlem isteyen sorularda (yerel bir aracı, kurumu inceleme vb.) veri uydurma: yöntemi ver ve tabloyu "örnektir, kendi
gözleminle doldur" diye işaretle.

Ana hatlar:
{ana_hatlar}

Kalıcı terim tercihleri:
{terimler}

Terim tabloları: parca-*-cevap.md dosyalarının sonundaki tablolar (sohbette elle çalışıyorsan buraya yapıştır).
"""


def parcalari_yaz(md_yolu, kitap_adi, etiket, baslik):
    """Bölüm metnini sayfa sınırlarından ~PARCA_KELIME kelimelik parçalara böler; her parçaya hazır prompt yazar."""
    metin = open(md_yolu, encoding="utf-8").read()
    sayfalar = re.split(r"(?=<!-- PDF s\. )", metin)
    sayfalar = [x for x in sayfalar if x.startswith("<!-- PDF s.")]
    klasor = os.path.join(os.path.dirname(md_yolu), "parcalar")
    shutil.rmtree(klasor, ignore_errors=True)
    os.makedirs(klasor)
    parcalar, mevcut, kelime = [], [], 0
    for sy in sayfalar:
        k = len(re.sub(r"!\[[^\]]*\]\([^)]*\)|<!--.*?-->", "", sy).split())
        if mevcut and kelime + k > PARCA_KELIME:
            parcalar.append(mevcut)
            mevcut, kelime = [], 0
        mevcut.append(sy)
        kelime += k
    if mevcut:
        parcalar.append(mevcut)
    ana_hatlar = "\n".join(f"- {re.sub(r'[#*]', '', b).strip()}" for b in re.findall(r"(?m)^#{2,4} .+$", metin)
                            if not re.search(r"(?i)objectives|contents|key points|further reading|exercises", b))
    terimler = bolum_terimleri(metin)
    for n, parca in enumerate(parcalar, 1):
        govde = "".join(parca).strip()
        gorseller = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", govde)
        isaretler = re.findall(r"<!-- (PDF s\. \d+(?: · kitap s\. \d+)?) -->", govde)
        aralik = f"{isaretler[0]} – {isaretler[-1]}" if len(isaretler) > 1 else (isaretler[0] if isaretler else "?")
        notu = ("Ekteki görseller bu aralıktaki şekillerdir: " + ", ".join(os.path.basename(g) for g in gorseller)
                + ".\n") if gorseller else ""
        bas_notu = (f"<!-- EKLENECEK GÖRSELLER: {', '.join(os.path.basename(g) for g in gorseller)} "
                    f"(bölüm klasöründeki sekiller/ içinden) -->\n" if gorseller else "<!-- Bu parçada görsel yok -->\n")
        with open(os.path.join(klasor, f"parca-{n:02d}.md"), "w", encoding="utf-8") as f:
            ozel = (ILK_PARCA_NOTU if n == 1 else "") + (SON_PARCA_NOTU if n == len(parcalar) else "")
            f.write(bas_notu + PROMPT_SABLONU.format(kitap=kitap_adi, etiket=etiket, baslik=baslik, aralik=aralik,
                                                       parca_no=n, parca_sayisi=len(parcalar), gorsel_notu=notu,
                                                       ana_hatlar=ana_hatlar or "-", ozel_not=ozel, metin=govde,
                                                       terimler=terimler or "- (bu bölümde kayıtlı terim yok)"))
    with open(os.path.join(klasor, "parca-son.md"), "w", encoding="utf-8") as f:
        f.write("<!-- Bütün parçalar bittikten sonra kullan: cevapların sonundaki terim tablolarını aşağıya yapıştır. "
                "Cevabı parca-son-cevap.md olarak kaydet. -->\n"
                + SON_PROMPT.format(kitap=kitap_adi, etiket=etiket, baslik=baslik, ana_hatlar=ana_hatlar or "-",
                                   terimler=terimler or "- (bu bölümde kayıtlı terim yok)"))
    return len(parcalar)


TALIMAT = """# Görev: {etiket} ({baslik}) — Türkçe çalışma dokümanı

Bu klasörde bir ders kitabı bölümünün hazır paketi var. Metin kaynaktan doğrulanarak çıkarıldı, şekiller kırpıldı.
Senin işin yalnızca ÇEVİRİ ve ANLATIM; geri kalan her şey hazır. Hedef: kitabın İngilizcesini rahat okuyamayan
öğrencinin, her sayfayı hem tam çeviriyle (A) hem de "neden böyle?" sorusunu cevaplayan öğretici açıklamayla (C)
öğrenmesi. Kalite ölçütü ve kurallar her parça dosyasının içinde yazılı.

## Klasör
- `{ad}.md` — bölümün temiz metni (bilgi için; çeviriyi parçalardan yap)
- `parcalar/parca-01.md … parca-{son:02d}.md` — her biri ayrıntılı talimat + o parçanın kaynak metni
- `parcalar/parca-son.md` — bölüm sonu (ayırt etme, sözlük, tekrar, sorular, alıştırma çözümleri) talimatı
- `sekiller/` — şekillerin kırpılmış görselleri
- `calisma_pdf.py` — kontrol (eksik sayfa, kısa çeviri, şekil, anlatım kalitesi) + PDF üretimi

## Adımlar
1. Plan: `parcalar/parca-01.md`'deki bölüm ana hatlarına ve ilk sayfaların kaynak metnine göz at. Bölümün bütün
   kavramlarına uyan, öğrencinin tanıdığı TEK bir ortak örnek (somut bir sistem) seç. Bunu ve bölümde birbirine
   karışabilecek kavram çiftlerini `plan.md` dosyasına 3-6 satırda yaz. Ortak örnek kitabın kendi örneklerinin yerine
   geçmez; onlarla birlikte kullanılır.
2. `parcalar/parca-01.md`'den başlayarak SIRAYLA her parçayı işle: dosyadaki talimata ve kalite kurallarına birebir
   uy (her parçada kuralları yeniden oku; ilk parçalarda ne kadar özenliysen son parçada da o kadar ol). En üst
   satırda listelenen görselleri `sekiller/` içinden aç (yalnızca onları). Cevabı `parcalar/parca-NN-cevap.md`
   dosyasına yaz. Uzun bir parçayı dosyaya birkaç adımda ekleyebilirsin; ama hiçbir sayfayı atlama, kısaltma,
   özetleme. Terimleri ve ortak örneği parçalar boyunca tutarlı tut.
3. Bütün parçalar bitince `parcalar/parca-son.md`'deki talimatla bölüm sonunu üret. Terim tablolarını cevap
   dosyalarının sonlarından kendin topla. Cevabı `parcalar/parca-son-cevap.md` dosyasına yaz.
4. Çalıştır: `pip install reportlab pillow` (gerekirse) ve `python3 calisma_pdf.py .`
5. Kontrol raporunda (ekran çıktısı ve `{ad}_kontrol.md`) ⚠ olan sayfalar varsa YALNIZCA o sayfaları ilgili cevap
   dosyasında düzelt ve 4. adımı tekrarla (en fazla 2 tur). Rapor yalnızca eksikleri değil anlatım sorunlarını da
   gösterir: A'yı özetleyen kısa C, etiket dışı kalın vurgusu olmayan C, tekrar eden "Ek açıklama:", "Sonraki sayfada
   … göreceğiz" türü salt duyuru, A'da kalmış şekil bağlantısı. Bunları da kurallara göre düzelt; uyarıyı susturmak
   için anlamsız kalın ya da yapay cümle ekleme.
6. Bana `{ad}_calisma.pdf` dosyasını ve kontrol raporunun son hâlini ver.

## Yarıda kalırsa
- Limit ya da kesinti olursa önce `plan.md`'yi oku, sonra kaldığın parçadan devam et: var olan `-cevap.md`
  dosyalarını yeniden yazma.
- Model değişse bile tamamlanmış cevapları baştan yazma; yalnızca kontrolde ⚠ çıkan sayfaları düzelt.

## Yapma (hepsi hazır ya da gereksiz; boşa token harcar)
- Kitap PDF'ini açma, metni yeniden çıkarma, sayfa görüntüsü üretme.
- Yeni build, kırpma ya da kontrol betiği yazma; `calisma_pdf.py`'yi değiştirme.
- Üretilen PDF'in sayfalarını görsel olarak inceleme, contact sheet üretme.
- Kitapta olmayan şema çizme.
- Token ya da süre kazanmak için çeviriyi kısaltma, sayfaları birleştirme, C bölümünü atlama. Kalite önce gelir.
"""

CALISMA_PDF_KODU = """
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
1oelT44+MmqS6CQB0xS0ltvW3P8CF/CVGA==
"""


def talimat_yaz(klasor, ad, etiket, baslik, n_parca):
    """Bölüm klasörünü kendi kendine yeten hâle getirir: ajan talimatı + calisma_pdf.py kopyası."""
    import base64
    import zlib
    with open(os.path.join(klasor, "TALIMAT.md"), "w", encoding="utf-8") as f:
        f.write(TALIMAT.format(etiket=etiket, baslik=baslik, ad=ad, son=n_parca))
    with open(os.path.join(klasor, "calisma_pdf.py"), "wb") as f:
        f.write(zlib.decompress(base64.b64decode("".join(CALISMA_PDF_KODU.split()))))


def tek_bolum(doc):
    """Yer imi ve içindekiler yoksa (ör. kitaptan ayrılmış tek bölüm) PDF'in tamamını bir bölüm sayar.
    Numara/başlık üst bilgiden ('Chapter 4 ■ Software processes') ya da ilk sayfadan bulunur."""
    no, baslik = None, None
    sayac = Counter()
    for i in range(min(doc.page_count, 12)):
        for satir in doc[i].get_text().splitlines():
            m = re.search(r"(?:Chapter|Bölüm)\s+(\d{1,3})\s*[■•|:\-–—]?\s*(.+)", satir.strip(), re.I)
            if m and len(m.group(2)) < 60:
                sayac[(int(m.group(1)), m.group(2).strip())] += 1
    if sayac:
        (no, _), _ = sayac.most_common(1)[0]
        basliklar = Counter(b for (n, b), c in sayac.items() if n == no for _ in range(c))
        baslik = basliklar.most_common(1)[0][0]
    if no is None:
        satirlar = [x.strip() for x in doc[0].get_text().splitlines() if x.strip()]
        no = next((int(x) for x in satirlar[:5] if x.isdigit() and int(x) < 100), 1)
        baslik = next((x for x in satirlar[:5] if not x.isdigit()), "Bolum")
    return [(no, baslik, 0, doc.page_count - 1)], None


KULLANIM = """# Kullanım

## A) Dosya okuyup komut çalıştırabilen bir LLM ortamında (önerilen)
Bölüm klasörünü (ör. `04_Software_processes/`) LLM'e ver ve "TALIMAT.md'deki görevi yap" de.
Model parçaları sırayla çevirir, cevapları dosyalara yazar, `calisma_pdf.py` ile kontrol edip PDF'i üretir.
Her bölüm için yeni bir sohbet aç.

## B) Elle (dosya yazamayan sohbet ortamında)
Her bölüm için:

1. `<bölüm>/parcalar/parca-01.md` dosyasını aç. En üst satırda bu parçaya eklenecek görseller yazar.
2. YENİ bir sohbet aç; dosyanın tamamını yapıştır, yazan görselleri `<bölüm>/sekiller/` klasöründen ekle.
3. Cevabı aynı klasöre `parca-01-cevap.md` adıyla kaydet. Sonraki parça için yine YENİ sohbet aç.
4. Bütün parçalar bitince: `python3 calisma_pdf.py "<bölüm klasörü>"` → kontrol raporu + çalışma PDF'i
   (bölüm klasörünün içine yazılır).

Neden her parça yeni sohbette? Sohbet uzadıkça model her adımda öncekilerin hepsini yeniden okur;
limitin hızlı bitmesinin ana nedeni budur. Parça kısa olunca çeviri de özetlemeye kaymaz.
"""


def bolum_klasoru_adi(kitap_adi):
    return re.sub(r"\s+", "_", kitap_adi) + "_Bolumler"


def kitabi_bol(pdf_yolu, cikti_ust=None, bolum_bitti=None):
    """bolum_bitti: her bölüm klasörü yazılır yazılmaz çağrılır (Colab'de Drive'a anında yükleme için)."""
    doc = pymupdf.open(pdf_yolu)
    kitap_adi = os.path.splitext(os.path.basename(pdf_yolu))[0]
    print(f"\n📖 {kitap_adi}  ({doc.page_count} sayfa)")

    sonuc = yer_imlerinden(doc)
    yontem = "PDF yer imleri"
    if not sonuc:
        sonuc = icindekilerden(doc)
        yontem = "basılı içindekiler + sayfa kayması"
    if not sonuc:
        sonuc = tek_bolum(doc)
        yontem = "tek bölüm (yer imi/içindekiler yok — PDF'in tamamı)"
    if not sonuc:
        raise SystemExit(
            "❌ Bölümler bulunamadı: PDF'te yer imi yok ve içindekiler sayfasında\n"
            "   'Chapter N  Başlık  sayfa' biçiminde satır okunamadı.\n"
            "   (Taranmış/resim PDF olabilir.) Bana ilk 20 sayfayı gönderirsen ayarlarım.")
    bolumler, sozluk = sonuc
    n_ek = sum(isinstance(b[0], str) for b in bolumler)
    print(f"   🔎 Yöntem: {yontem}  →  {len(bolumler) - n_ek} bölüm"
          f"{f' + {n_ek} ek' if n_ek else ''}{' + sözlük' if sozluk and SOZLUGU_DAHIL_ET else ''}")

    klasor = os.path.join(cikti_ust or os.path.dirname(os.path.abspath(pdf_yolu)),
                          bolum_klasoru_adi(kitap_adi))
    shutil.rmtree(klasor, ignore_errors=True)
    os.makedirs(klasor)

    kayma = sayfa_kaymasi(doc)   # sayfa no satırlarını silmek için (yer imli PDF'te de)
    govde = govde_fontu(doc, range(doc.page_count))
    isler = []
    for no, baslik, bas, bit in bolumler:
        if bit < bas:
            print(f"  ⚠ Bölüm {no} atlandı (sayfa aralığı geçersiz: {bas + 1}–{bit + 1})")
            continue
        isler.append((no, baslik, bas, bit))
    if sozluk and SOZLUGU_DAHIL_ET and sozluk[3] >= sozluk[2]:
        isler.append(tuple(sozluk))
    yazilan = _bolumleri_isle(pdf_yolu, doc, kitap_adi, isler, klasor, kayma, govde, bolum_bitti)
    with open(os.path.join(klasor, "KULLANIM.md"), "w", encoding="utf-8") as f:
        f.write(KULLANIM)
    with open(os.path.join(klasor, f"_surum_{SURUM}.txt"), "w") as f:
        f.write(SURUM)

    print(f"\n✅ {len(yazilan)} dosya → {klasor}")
    return klasor, yazilan


PARALEL_ISLEM = True      # bölümleri işlemcinin bütün çekirdeklerinde aynı anda işle


def _bolum_iscisi(is_):
    """Ayrı süreçte bir bölümü işler (her süreç PDF'i kendisi açar)."""
    pdf_yolu, kitap_adi, (no, baslik, bas, bit), klasor, kayma, govde = is_
    return bolumu_yaz(pymupdf.open(pdf_yolu), kitap_adi, no, baslik, bas, bit, klasor, kayma, govde)


def _bolumleri_isle(pdf_yolu, doc, kitap_adi, isler, klasor, kayma, govde, bolum_bitti):
    """Bölümleri çekirdek sayısı kadar paralel işler; biten her bölümü hemen bildirir (Drive'a yükleme).
    Paralel çalışamazsa (ör. ortam izin vermezse) sessizce sıralı işlemeye döner. Çıktı her iki yolda aynıdır."""
    cekirdek = os.cpu_count() or 1
    if PARALEL_ISLEM and cekirdek > 1 and len(isler) > 1:
        try:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor, as_completed
            baglam = mp.get_context("fork" if sys.platform.startswith("linux") else "spawn")
            sonuc = {}
            with ProcessPoolExecutor(max_workers=min(cekirdek, len(isler)), mp_context=baglam) as havuz:
                gorevler = {havuz.submit(_bolum_iscisi, (pdf_yolu, kitap_adi, i, klasor, kayma, govde)): n
                            for n, i in enumerate(isler)}
                for f in as_completed(gorevler):
                    sonuc[gorevler[f]] = f.result()
                    _bildir(bolum_bitti, sonuc[gorevler[f]])
            return [sonuc[n] for n in range(len(isler))]
        except Exception as e:
            print(f"  ℹ Paralel işleme kullanılamadı ({type(e).__name__}); bölümler sırayla işleniyor.")
            shutil.rmtree(klasor, ignore_errors=True)
            os.makedirs(klasor)
    yazilan = []
    for no, baslik, bas, bit in isler:
        yazilan.append(bolumu_yaz(doc, kitap_adi, no, baslik, bas, bit, klasor, kayma, govde))
        _bildir(bolum_bitti, yazilan[-1])
    return yazilan


def _bildir(bolum_bitti, md_yolu):
    if bolum_bitti:
        try:
            bolum_bitti(os.path.dirname(md_yolu))
        except Exception as e:                 # yükleme hatası bölmeyi durdurmasın
            print(f"    ⚠ {os.path.basename(os.path.dirname(md_yolu))} Drive'a yüklenemedi ({e}); zip'te olacak.")


# ============================================================
# Colab akışı — ses script'iyle AYNI klasör linki
# ============================================================
# Yalnızca bu adlı klasörün DOĞRUDAN içindeki PDF'ler kitap sayılır.
# Büyük/küçük harf, Türkçe karakter ve boşluk fark etmez ("Kitap", "kitaplar").
# Slayt sistemi 'Slaytlar' klasörünü kullanır; iki sistem birbirine karışmaz.
KITAP_KLASORLERI = {"kitap", "kitaplar"}


def _klasor_anahtari(ad):
    ad = ad.translate(str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")).lower()
    return re.sub(r"[^a-z0-9]", "", ad)


def colab_calistir():
    _kur("-U", "gdown")
    import gdown

    print("=" * 60)
    print("📘 KİTAPLARI BÖLÜMLERE AYIR")
    print("=" * 60)
    print("Ses script'inde kullandığın AYNI klasör linkini yapıştır.")
    print("(Yalnızca 'Kitap' klasörünün DOĞRUDAN içindeki PDF'ler işlenir;\n"
          " Slaytlar vb. başka klasörlere dokunulmaz.)\n")
    link = input("🔗 Drive klasör linki: ").strip()
    if "folders/" in link:
        klasor_id = link.split("folders/")[1].split("?")[0].split("/")[0]
    elif "id=" in link:
        klasor_id = link.split("id=")[1].split("&")[0]
    else:
        klasor_id = link

    calisma = "/content/kitap"
    shutil.rmtree(calisma, ignore_errors=True)
    os.makedirs(calisma)

    print("\n🔍 Klasör listeleniyor...")
    try:
        liste = gdown.download_folder(id=klasor_id, output=calisma + os.sep,
                                      skip_download=True, quiet=True)
    except Exception as e:
        raise SystemExit(f"❌ Klasör okunamadı: {e}\n"
                         "   Linkin 'Bağlantıya sahip olan herkes' olarak paylaşıldığından emin ol.")

    yollar = {f.path.replace("\\", "/") for f in (liste or [])}
    isler, atlanan = [], []
    for f in liste or []:
        yol = f.path.replace("\\", "/")
        parcalar = yol.split("/")
        if not yol.lower().endswith(".pdf"):
            continue
        ust_klasorler = [_klasor_anahtari(p) for p in parcalar[:-1]]
        # Kitap klasöründe değilse (ör. Slaytlar) dokunma
        if not any(k in KITAP_KLASORLERI for k in ust_klasorler):
            continue
        # Kendi çıktı klasörlerimizin veya başka bir sistemin alt
        # klasörlerindeki PDF'lere dokunma: PDF doğrudan kitap klasöründe olmalı
        if ust_klasorler[-1] not in KITAP_KLASORLERI:
            continue
        kitap_adi = os.path.splitext(parcalar[-1])[0]
        md_on_ek = "/".join(parcalar[:-1] + [bolum_klasoru_adi(kitap_adi)]).lstrip("/") + "/"
        if (md_on_ek + f"_surum_{SURUM}.txt") in yollar:     # bu sürümle işlenmiş; eskiler yeniden işlenir
            atlanan.append(yol)
        else:
            isler.append(f)

    print(f"\n📚 {len(isler) + len(atlanan)} kitap PDF'i  |  ✅ {len(atlanan)} zaten bölünmüş  "
          f"|  🆕 {len(isler)} bölünecek")
    for y in atlanan:
        print(f"      ✅ {y}")
    for f in isler:
        print(f"      🆕 {f.path}")
    if not isler and not atlanan:
        raise SystemExit("\n⚠ 'Kitap' klasörünün doğrudan içinde PDF bulunamadı.\n"
                         "   Beklenen yer: <Ders>/DersKaynaklari/Kitap/<kitap>.pdf")
    if not isler:
        raise SystemExit("\n✨ Bölünecek yeni kitap yok.")

    # Drive izni: uzun iş başlamadan en başta
    servis = None
    if DRIVE_A_YUKLE:
        print("\n☁️  Drive'a yükleme için izin isteniyor (istemezsen pencereyi kapat)...")
        try:
            from google.colab import auth
            from googleapiclient.discovery import build
            auth.authenticate_user()
            import logging
            logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)   # zararsız uyarıyı gizle
            servis = build("drive", "v3", cache_discovery=False)
            print("✅ Drive izni alındı.")
        except Exception as e:
            print(f"⚠ Drive izni alınamadı ({e}). Sorun değil, sonuçlar zip olarak inecek.")

    cikti = "/content/kitap_bolumleri"
    shutil.rmtree(cikti, ignore_errors=True)
    os.makedirs(cikti)

    for f in isler:
        try:
            os.makedirs(os.path.dirname(f.local_path), exist_ok=True)
            print(f"\n⏬ İndiriliyor: {f.path}")
            if not _indir(servis, f.id, f.local_path, gdown):
                raise RuntimeError("PDF indirilemedi (birkaç dakika sonra yeniden dene).")
            yukleyici = None
            if servis:
                try:
                    kitap_adi = os.path.splitext(os.path.basename(f.local_path))[0]
                    yukleyici = DriveYukleyici(servis, f.id, bolum_klasoru_adi(kitap_adi),
                                               servis_uret=lambda: build("drive", "v3", cache_discovery=False))
                except Exception as e:
                    print(f"  ⚠ Drive klasörü hazırlanamadı ({e}). Sonuçlar zip'te olacak.")
            klasor, yazilan = kitabi_bol(f.local_path, cikti, yukleyici.bolum if yukleyici else None)
            os.remove(f.local_path)
            if yukleyici:
                try:
                    yukleyici.bitir(klasor)
                except Exception as e:
                    print(f"  ⚠ Kök dosyalar Drive'a yüklenemedi ({e}). Zip'te olacak.")
        except SystemExit as e:
            print(e)
        except Exception as e:
            print(f"  ❌ {f.path}: {e}")

    if os.listdir(cikti):
        zip_yolu = shutil.make_archive("/content/kitap_bolumleri", "zip", cikti)
        try:
            from google.colab import files
            files.download(zip_yolu)
            print(f"\n⬇️  {os.path.basename(zip_yolu)} indiriliyor.")
        except Exception:
            print(f"\n⬇️  Sol paneldeki 📁'den {zip_yolu} dosyasını indir.")


def _indir(servis, dosya_id, hedef, gdown_modulu, deneme=3):
    """İzin varsa kimlikli Drive API ile indirir (gdown'ın 'çok fazla erişim' kısıtına takılmaz)."""
    import time
    for i in range(deneme):
        try:
            if servis:
                from googleapiclient.http import MediaIoBaseDownload
                with open(hedef, "wb") as f:
                    indirici = MediaIoBaseDownload(f, servis.files().get_media(fileId=dosya_id, supportsAllDrives=True),
                                                   chunksize=16 * 1024 * 1024)
                    bitti = False
                    while not bitti:
                        _, bitti = indirici.next_chunk()
                return True
            if gdown_modulu.download(id=dosya_id, output=hedef, quiet=True):
                return True
        except Exception:
            time.sleep(2 * (i + 1))
    return False


KLASOR_TIPI = "application/vnd.google-apps.folder"
KORUNANLAR = ("-cevap.md", "_calisma.pdf", "_calisma.md", "_kontrol.md")   # LLM cevapları ve çıktıları


def _kacis(x):
    return x.replace("\\", "\\\\").replace("'", "\\'")


class DriveYukleyici:
    """Bölüm klasörlerini Drive'da PDF'in yanındaki '<kitap>_Bolumler' klasörüne, her bölüm biter bitmez yükler.
    Aynı adlı dosyaların üzerine yazar; bölüm klasörlerinde eskiden kalanları çöpe atar ama LLM cevaplarına
    ve çalışma PDF'lerine (KORUNANLAR) dokunmaz. Sürüm dosyası en sona yazılır: iş yarıda kesilirse kitap
    bir sonraki çalıştırmada yeniden işlenir."""

    def __init__(self, servis, pdf_id, ad, servis_uret=None, paralel=6):
        """servis_uret: her iş parçacığı için ayrı Drive bağlantısı üreten fonksiyon (Colab'de verilir).
        Verilirse dosyalar 'paralel' kadar eşzamanlı yüklenir; verilmezse sırayla."""
        self.servis, self.ad = servis, ad
        self.servis_uret, self.paralel = servis_uret, paralel
        import threading
        self._yerel = threading.local()
        self._kilit = threading.Lock()
        ust = servis.files().get(fileId=pdf_id, fields="parents", supportsAllDrives=True).execute()["parents"][0]
        q = (f"'{ust}' in parents and name = '{_kacis(ad)}' and "
             f"mimeType = '{KLASOR_TIPI}' and trashed = false")
        var = servis.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                                  includeItemsFromAllDrives=True).execute()["files"]
        self.hedef = var[0]["id"] if var else servis.files().create(
            body={"name": ad, "mimeType": KLASOR_TIPI, "parents": [ust]},
            fields="id", supportsAllDrives=True).execute()["id"]
        self.yuklenen = 0

    def _icerik(self, uzak_id):
        mevcut, sayfa = {}, None
        while True:
            r = self.servis.files().list(q=f"'{uzak_id}' in parents and trashed = false",
                                         fields="nextPageToken, files(id, name, mimeType, md5Checksum)", pageSize=1000,
                                         pageToken=sayfa, supportsAllDrives=True,
                                         includeItemsFromAllDrives=True).execute()
            mevcut.update({x["name"]: x for x in r["files"]})
            sayfa = r.get("nextPageToken")
            if not sayfa:
                return mevcut

    def _dosya(self, yol, uzak_id, mevcut):
        from googleapiclient.http import MediaFileUpload
        dad = os.path.basename(yol)
        eski = mevcut.get(dad)
        if eski and eski.get("md5Checksum"):           # Drive'daki dosya birebir aynıysa yükleme (çok hızlandırır)
            import hashlib
            with open(yol, "rb") as fh:
                if hashlib.md5(fh.read()).hexdigest() == eski["md5Checksum"]:
                    with self._kilit:
                        self.atlanan = getattr(self, "atlanan", 0) + 1
                    return
        tur = {".md": "text/markdown", ".png": "image/png", ".pdf": "application/pdf"}.get(
            os.path.splitext(dad)[1], "text/plain")
        medya = MediaFileUpload(yol, mimetype=tur)
        servis = self._is_servisi()
        import time
        for deneme in range(4):                         # geçici ağ/kota hatasında birkaç kez dene
            try:
                if dad in mevcut and mevcut[dad]["mimeType"] != KLASOR_TIPI:
                    servis.files().update(fileId=mevcut[dad]["id"], media_body=medya, supportsAllDrives=True).execute()
                else:
                    servis.files().create(body={"name": dad, "parents": [uzak_id]}, media_body=medya,
                                          fields="id", supportsAllDrives=True).execute()
                return
            except Exception:
                if deneme == 3:
                    raise
                time.sleep(2 * (deneme + 1))

    def _is_servisi(self):
        """İş parçacığına özel Drive bağlantısı (googleapiclient bağlantıları iş parçacıkları arasında paylaşılamaz)."""
        if not self.servis_uret:
            return self.servis
        s = getattr(self._yerel, "servis", None)
        if s is None:
            s = self._yerel.servis = self.servis_uret()
        return s

    def _klasor(self, ad, uzak_ust, mevcut):
        x = mevcut.get(ad)
        if x and x["mimeType"] == KLASOR_TIPI:
            return x["id"]
        return self.servis.files().create(body={"name": ad, "mimeType": KLASOR_TIPI, "parents": [uzak_ust]},
                                          fields="id", supportsAllDrives=True).execute()["id"]

    def _aynala(self, yerel, uzak_id, isler=None):
        """Klasör yapısını sırayla kurar, dosya yüklemelerini toplayıp (en üst çağrıda) paralel yürütür."""
        ust_cagri = isler is None
        isler = [] if ust_cagri else isler
        mevcut = self._icerik(uzak_id)
        adlar = set()
        for dad in sorted(os.listdir(yerel)):
            adlar.add(dad)
            yol = os.path.join(yerel, dad)
            if os.path.isdir(yol):
                self._aynala(yol, self._klasor(dad, uzak_id, mevcut), isler)
            else:
                isler.append((yol, uzak_id, mevcut))
        for dad, x in mevcut.items():            # bölüm içinde eskiden kalanlar çöpe (cevaplar hariç)
            if dad not in adlar and not dad.endswith(KORUNANLAR):
                self.servis.files().update(fileId=x["id"], body={"trashed": True}, supportsAllDrives=True).execute()
        if not ust_cagri:
            return
        if self.servis_uret and self.paralel > 1 and len(isler) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(self.paralel) as havuz:
                for f in [havuz.submit(self._dosya, *i) for i in isler]:
                    f.result()                      # hata varsa burada yükselir
        else:
            for i in isler:
                self._dosya(*i)

    def bolum(self, bolum_klasoru):
        """Tek bir bölüm klasörünü yükler (kitabi_bol her bölümden sonra çağırır)."""
        ad = os.path.basename(bolum_klasoru)
        self._aynala(bolum_klasoru, self._klasor(ad, self.hedef, self._icerik(self.hedef)))
        self.yuklenen += 1
        print(f"    ☁️  Drive'a yüklendi → {self.ad}/{ad}/")

    def bitir(self, klasor):
        """Kök dosyaları (KULLANIM.md, sürüm) yükler; sürüm dosyası EN SONA."""
        mevcut = self._icerik(self.hedef)
        dosyalar = sorted((d for d in os.listdir(klasor) if os.path.isfile(os.path.join(klasor, d))),
                          key=lambda d: d.startswith("_surum_"))
        for d in dosyalar:
            self._dosya(os.path.join(klasor, d), self.hedef, mevcut)
        print(f"  ☁️  Drive: {self.yuklenen} bölüm klasörü → PDF'in yanındaki {self.ad}/"
              + (f" ({self.atlanan} dosya zaten aynıydı, yeniden yüklenmedi)" if getattr(self, "atlanan", 0) else ""))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        kitabi_bol(sys.argv[1])            # Mac / lokal kullanım
    elif COLAB:
        colab_calistir()
    else:
        print('Kullanım: python3 kitap_bol.py "kitap.pdf"')