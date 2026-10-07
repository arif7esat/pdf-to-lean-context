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
bölümden ayrılmış bir PDF verilebilir. Glossary/Sözlük bulunursa ayrı dosya olarak çıkar.
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
SURUM = "3.2"            # çıktı biçimi değişince artar; Colab eski sürümle bölünmüş kitapları yeniden işler
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


def yer_imlerinden(doc):
    """PDF yer imlerinden [(no, başlık, ilk_sayfa_idx, son_sayfa_idx)] çıkarır."""
    toc = doc.get_toc(simple=True)  # [seviye, başlık, sayfa(1'den)]
    if not toc:
        return None

    bolumler, sozluk = [], None
    for i, (seviye, baslik, sayfa) in enumerate(toc):
        baslik = " ".join(baslik.split())
        m = BOLUM_BASLIK.match(baslik)
        if m or SOZLUK_BASLIK.match(baslik):
            # Bitiş: bundan sonra gelen, aynı ya da daha üst seviyedeki ilk girdi
            son = doc.page_count
            for sv2, _, sy2 in toc[i + 1:]:
                if sv2 <= seviye and sy2 > sayfa:
                    son = sy2 - 1
                    break
            kayit = (int(m.group(1)) if m else 99,
                     (m.group(2).strip() if m else baslik) or f"Bolum {m.group(1)}",
                     sayfa - 1, son - 1)
            if m:
                bolumler.append(kayit)
            else:
                sozluk = kayit
    if len(bolumler) < 2:
        return None
    return bolumler, sozluk


TOC_BOLUM = re.compile(r"^(?:chapter|bölüm|bolum)\s+(\d{1,3})\b\s*(.*)$", re.I)
TOC_SOZLUK = re.compile(r"^(glossary|sözlük|sozluk)\b\s*(\d{1,4})?$", re.I)
TOC_SON = re.compile(r"^(subject index|author index|index|dizin|kaynakça|references)\b\s*(\d{1,4})?$", re.I)
SAYI = re.compile(r"^\d{1,4}$")
TOC_KISIM = re.compile(r"^(part|kısım|kisim)\s+(\d{1,2})\b.*$", re.I)


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
    Dönüş: [(tür, no, başlık, basılı_sayfa)], tür: 'bolum' | 'sozluk' | 'son'"""
    girdiler = []
    for idx in range(min(40, doc.page_count)):
        satirlar = [" ".join(s.split()) for s in doc[idx].get_text().splitlines()]
        satirlar = [s for s in satirlar if s]
        i = 0
        while i < len(satirlar):
            s = satirlar[i]
            m = TOC_BOLUM.match(s)
            if m:
                no, kalan = int(m.group(1)), m.group(2).strip()
                sayfa = None
                son_sayi = re.search(r"\s(\d{1,4})$", " " + kalan)
                if son_sayi:                        # hepsi tek satırda
                    sayfa = int(son_sayi.group(1))
                    kalan = kalan[: son_sayi.start()].strip()
                j = i + 1
                if not kalan and j < len(satirlar) and not SAYI.match(satirlar[j]):
                    kalan = satirlar[j]              # başlık alt satırda
                    j += 1
                if sayfa is None and j < len(satirlar) and SAYI.match(satirlar[j]):
                    sayfa = int(satirlar[j])         # sayfa no alt satırda
                    j += 1
                if kalan and sayfa:
                    girdiler.append(("bolum", no, kalan, sayfa))
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

    sinirlar = ([g[2] for g in girdiler] + kisimlar
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
    sozluk = None
    if sozluk_bas:
        b = bitis(sozluk_bas)
        sozluk = (99, "Glossary", idx(sozluk_bas), idx(b) if b else doc.page_count - 1)
    return bolumler, sozluk


# ============================================================
# Şekil ve tablo bulma (alt yazıdan: "Figure 4.1", "Table 2.3")
# ============================================================
ALT_YAZI = re.compile(r"^\s*(Figure|Fig\.|Table|Şekil|Tablo)\s+(\d+(?:\.\d+)+)\s*(.*)$", re.I)


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


def _birlesik(kutular, bosluk):
    """Birbirine 'bosluk' kadar yakın kutuları tek kümede birleştirir."""
    kumeler = [pymupdf.Rect(k) for k in kutular]
    degisti = True
    while degisti:
        degisti = False
        for i in range(len(kumeler)):
            for j in range(i + 1, len(kumeler)):
                a, b = kumeler[i], kumeler[j]
                if (a + (-bosluk, -bosluk, bosluk, bosluk)).intersects(b):
                    kumeler[i] = a | b
                    del kumeler[j]
                    degisti = True
                    break
            if degisti:
                break
    return kumeler


def _nesne_sekilleri(sayfa, govde, ust_alt_pay=0.07):
    """1. aşama — PDF nesnelerinden (çizim, resim, küçük yazı) şekil kutuları. Döndürür:
    (bulunan, eşleşmeyen alt yazılar, gövde blokları, üst sınır, alt sınır)"""
    W, H = sayfa.rect.width, sayfa.rect.height
    govde_font, govde_boyut = govde
    ust, alt = H * ust_alt_pay, H * (1 - ust_alt_pay * 0.6)
    altyazilar, sekil_yazilari, govde_bloklari = [], [], []
    for b in sayfa.get_text("dict")["blocks"]:
        if b["type"] == 1:
            continue
        r = pymupdf.Rect(b["bbox"])
        metin = _blok_metni(b)
        if not metin or r.y1 < ust or r.y0 > alt:
            continue
        font, boyut = _blok_fontu(b)
        govde_mi = font == govde_font and abs(boyut - govde_boyut) < 1
        if govde_mi or boyut > govde_boyut + 0.5:
            govde_bloklari.append(r)          # gövde metni ya da başlık (metindeki "Figure 4.8 illustrates" dahil)
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
            while j < len(satirlar) and abs(satirlar[j][0].x0 - lr.x0) < 6 and \
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
            if ilk.islower() or ilk in "(,;" or devam:
                # "Figure 5.15 gives task durations…" — alıştırma/metin cümlesi, alt yazı DEĞİL
                # (gerçek alt yazının başlığı büyük harfle başlar: "Figure 5.15 Task durations")
                sekil_yazilari += [satirlar[x][0] for x in range(i, j)]
                i = j
                continue
            altyazilar.append({"tur": "tablo" if m.group(1).lower() in ("table", "tablo") else "sekil",
                               "no": m.group(2), "baslik": re.sub(r"\s+", " ", m.group(3)).strip(),
                               "alt_yazi_kutu": kutu})
            i = j
    if not altyazilar:
        return [], [], govde_bloklari, ust, alt
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
    for a in sorted(altyazilar, key=lambda a: a["alt_yazi_kutu"].y0):
        ak = a["alt_yazi_kutu"]
        en_iyi = None
        for i, k in enumerate(kumeler):
            if i in kullanilan:
                continue
            aday = min(abs(k.y0 - ak.y0), abs(ak.y0 - k.y1), abs(k.y0 - ak.y1))
            if aday < 40 and (en_iyi is None or aday < en_iyi[0]):
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
                baska = any(abs(k.y0 - b["alt_yazi_kutu"].y0) < 15 for b in altyazilar if b is not a)
                if dikey < 30 and yatay_ortusme and not baska:
                    kutu |= k
                    kullanilan.add(i)
                    degisti = True
        a["kutu"] = _tamamla(kutu, ogeler + uzun_cizgiler, n_yazi, govde_bloklari,
                             [b["alt_yazi_kutu"] for b in altyazilar if b is not a], [s["kutu"] for s in sonuc])
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
            uzaklik = min(abs(r.y0 - ak.y0), abs(ak.y0 - r.y1), abs(r.y0 - ak.y1))
            if uzaklik < 40:
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
SEKIL_ALTI = re.compile(r"^(Figure|Table|Şekil|Tablo)\s+\d+\.\d+\w*\s+[A-Z“\"(]")


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
    metin = re.sub(r"(?m)^[-*]\s+((?:Figure|Table)\s+\d+\.\d+)", r"\1", metin)
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
    sayfalar = [re.sub(r"(?m)^[-*]\s+((?:Figure|Table)\s+\d+\.\d+)", r"\1", s) for s in sayfalar]
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


def tire_duzelt(govde, ham_metin):
    """Satır sonunda bölünen BİRLEŞİK kelimelerin tiresi metin çıkarılırken yutuluyor:
    "service-⏎centric" → "servicecentric". Ham PDF metnindeki satır sonu tirelerine bakıp gerçek
    birleşik kelimelerin tiresini geri koyar. Hece bölmesine ("devel-⏎opment") dokunmaz.
    Birleşik sayılma ölçütü: ikinci parça büyük harfle başlıyor ("Addison-Wesley"), aynı kelime metinde
    satır içinde tireli geçiyor ya da ön/son ek listede."""
    satir_ici = set(re.findall(r"\b([A-Za-z]+-[A-Za-z]+)\b", ham_metin.replace("-\n", "")))
    for a, b in set(re.findall(r"([A-Za-z]+)-\n\s*([A-Za-z]+)", ham_metin)):
        tireli = f"{a}-{b}"
        if not (b[0].isupper() or tireli in satir_ici or tireli.lower() in {t.lower() for t in satir_ici}
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
    try:
        tablolar = sayfa.find_tables(clip=pymupdf.Rect(kutu) + (-2, -2, 2, 2)).tables
    except Exception:
        return None
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
            metin = re.sub(r"(\w)- (\w)", r"\1\2", metin) if re.search(r"\w- [a-z]", metin) else metin
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
        anilan |= {m.group(2) for m in re.finditer(r"\b(Figure|Fig\.|Table|Şekil|Tablo)\s+(\d+\.\d+)\b", doc[idx].get_text())
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

    etiket = "Sözlük" if no == 99 else f"Bölüm {no}"
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

# Kitap s. Y • <o sayfanın ana fikrini anlatan kısa Türkçe başlık>
Kaynak: PDF s. X / kitap s. Y.

## A • Tam çeviri
<sayfanın sadık ve eksiksiz çevirisi>

## C • Şimdi bunu anlayalım
**Ek açıklama:** <öğretici anlatım>

---PAGE---

A • TAM ÇEVİRİ — "Kitap ne diyor?"
- Sayfanın TAMAMINI çevir: seçilmiş kritik cümleler ya da özet değil. Başlıkları (numaralarıyla: "4.1.2 Evrimsel geliştirme (Evolutionary development)"), maddeleri, numaralı listeleri, tabloları, koşulları, istisnaları, neden-sonuç bağlarını ve örnekleri koru.
- Teknik terimin İngilizce aslını ilk geçtiği yerde parantezde ver: yazılım süreci (software process). Aşağıdaki terim listesine uy.
- Kaynaktaki ihtiyatı, belirsizliği ve varsayımı koru ("olabilir", "genellikle", "bence"). Yazarın birinci tekil anlatımını koru ("…Bölüm 28'de ele alıyorum"). Nicelikleri değiştirme (hız ≠ süre, olasılık ≠ etki).
- Kaynakta olmayan hiçbir şeyi A'ya ekleme: yorum, güncel bilgi, düzeltme, genel kural yok. Kaynaktaki varsayımsal örneği sessizce düzeltme; sınırını C'de açıkla.
- Şekil bağlantısını (![…](….png)) şeklin geçtiği sayfanın A bölümünde AYNEN koru. Hemen altına şeklin çevirisini yaz: "Şekil 4.2 - Evrimsel geliştirme. <şekildeki kutu/etiket/ok adlarının Türkçesi, İngilizcesi parantezde>". Şekildeki yazılar bağlantının altındaki "<!-- Şekil … içindeki yazılar (PDF'ten): … -->" satırında metin olarak var; etiketleri oradan al, görselden okumaya çalışma. Orada da görselde de olmayan bir etiketi tahmin etme. Okların yönünü ve şeklin düzenini görselden oku. Şekil bir metin tablosuysa içeriği bağlantının altında markdown tablo olarak verilmiştir: A'da o tabloyu aynı satır/sütun yapısında, hücre hücre çevir (özetleme, satır atlama yok).
- Sayfa sonunda bölünen cümleyi bu sayfada tamamla ve A'nın sonuna yaz: "Çeviri notu: Son cümle PDF s. Z / kitap s. W'deki devamıyla tamamlandı." Bir sonraki sayfa o cümlenin devamıyla başlıyorsa onu tekrar çevirme, oradan devam et.
- Kitabın dönemine ait ifadeler ("bugün", "önümüzdeki yıllarda", teknoloji öngörüleri) varsa Çeviri notu'nda "kitabın yazıldığı dönemin değerlendirmesidir" diye belirt; güncel gerçek gibi genişletme.
- Kaynakta okunamayan ya da eksik görünen kısım varsa tahminle doldurma; açıkça yaz.

C • ŞİMDİ BUNU ANLAYALIM — "Bunu nasıl anlayıp kullanmalıyım?" (her sayfada ZORUNLU)
- A'nın kısa tekrarı değil. Öğrencinin bu sayfadan ne anlaması ve nasıl kullanması gerektiğini öğret. Kaynakta tek cümle olan bir fikri gerekirse birkaç paragrafla aç.
- Sayfa önemli bir kavram tanıtıyorsa, akış içinde şu soruları cevaplanmış hâle getir (başlık listesi olarak değil): Hangi problemi çözüyor? Neden gerekli? Nasıl işliyor? Hangi durumda/varsayımda yetersiz kalıyor? Diğer kavramlarla bağlantısı ne?
- Neden-sonuç zincirini görünür yap. Karıştırılabilecek kavramları doğrudan ayır ("Yineleme ile artımı karıştırma: …"). Alternatif yaklaşımlar karşılaştırılıyorsa küçük bir tablo kullan (güçlü yanı / sınırlılığı / uygun koşul).
- Şekil varsa: ne gösterdiğini, nasıl okunacağını (hangi kutudan başlanır, oklar ne anlatır) ve metinle ilişkisini açıkla. "Şekilde görülüyor" deyip geçme. Şekilde olmayan ilişki ya da ok ekleme; yönünden emin olmadığın oku "belirsiz" diye yaz. Farklı şekil/tabloların verilerini birbirine karıştırma.
- Kitaptaki örneğin neyi göstermek istediğini ve adımlarını açıkla. Sayısal bir hesap varsa adımları ve hangi tablo/şekle dayandığını yaz.
- Kitapta olmayan, kavramı basitleştiren bir örnek ekleyebilirsin: ayrı paragrafta "**Ek örnek:**" ile başlat, öğrencinin tanıdığı somut bir durum seç (ör. üniversite ders kayıt sistemi), kavramın sınırını da göstersin, kaynakta olmayan yeni bir teoriye dönüşmesin.
- Kaynak dışı güncel/dış bilgi gerekiyorsa "**Ek not:**" ile ayır ve kısa tut.
- Sayfayı bir öncekine/sonrakine bağlayarak bitir ("Sonraki sayfada … göreceğiz") — yalnızca ana hatlarda gördüğün konularla.
- Üslup: sade, doğrudan, teknik olarak doğru Türkçe; öğrenciye "sen" diye hitap et. Ton öğretici ve sakin: küçümseme, yapay övgü, aşırı basitleştirme yok. "Bunu şöyle oku", "Bu iki kavramı karıştırma", "Burada kritik nokta …", "Bu sonuç şu varsayıma dayanır" gibi doğrudan ifadeler kullan.

KURALLAR
- A = yalnızca kaynak. Senin eklediğin her şey C'de ve etiketli ("Ek açıklama", "Ek örnek", "Ek not", "Çeviri notu").
- Kitapta olmayan şema, tablo ya da görsel üretme. Ek hesap ya da ek tablo yaparsan kitaptan olmadığını yaz.
- Terimler bu parça boyunca ve önceki parçalarla tutarlı olsun. Aşağıdaki kalıcı terim tercihlerini A'da, C'de ve tablolarda AYNEN kullan; kendi karşılığını koyma. "yanlış:" yazan karşılıklar kontrol aracında hata olarak işaretlenir:
{terimler}
- Parçanın en sonuna, bu parçada geçen terimler için tablo ekle: | İngilizce terim | Türkçe karşılık | Kısa açıklama ve kaynak (PDF s. / kitap s.) |
{ozel_not}
=== KAYNAK METİN ===

{metin}
"""

ILK_PARCA_NOTU = """- Bu ilk parça. İlk sayfada:
  · Kaynak satırının sonuna kitabın adını ve baskısını ekle.
  · A'da bölüm başlığını, amaçları (Objectives) "Bölümü okuduğunda: … anlayacaksın" biçiminde ve içindekileri çevir.
  · C'de bölümün genel tanıtımını yap: bölüm neyi ve neden anlatıyor (2-3 cümle), hangi soruya cevap arıyor, hangi sırayla ilerleyecek. Ardından "Okuma düzeni:" (her sayfada A + C, ek açıklamalar etiketli, terimler parantezde, sözlük-tekrar-sorular sonda) ve "Kaynak notu:" (kapsam: PDF/kitap sayfa aralığı; metindeki dönem ifadeleri güncel iddia değildir) paragraflarını yaz.
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
8-10 soru. Yalnız tanım sorma: her sorunun başına türünü yaz — "Neden?", "Farkı ne?", "Hangisini seçerdin?" (somut senaryo).
Cevapları buraya YAZMA.
---PAGE---
# Kendini test et • Cevaplar
"Ek açıklama: Bunlar örnek cevaplardır; ezberlenecek tek bir ifade değildir." Her cevapta gerekçe ve kaynak sayfa;
senaryo kitaptan değilse "… ek nottur" de.
---PAGE---
# Kitabın alıştırmaları • Örnek çözümler
"Ek öğretim notu. Sorular: PDF s. … / kitap s. … Bunlar resmî cevap anahtarı değil, örnek çözümlerdir."
Bölüm sonundaki her alıştırma (Exercises) için: "4.4 - <kısa başlık>. <çözüm> Dayanak: PDF s. / kitap s." Alıştırma bir şekle
dayanıyorsa şeklin bağlantısını (sekiller/ içinden, ![…](sekiller/….png)) tekrar koy ve nasıl okunacağını yaz. Ayrıntısı
verilmeyen dış vakaları uydurma; yöntem ve gerekçeyle sınırlı kal.

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
            ozel = ILK_PARCA_NOTU if n == 1 else ""
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
Senin işin yalnızca ÇEVİRİ ve ANLATIM; geri kalan her şey hazır.

## Klasör
- `{ad}.md` — bölümün temiz metni (bilgi için; çeviriyi parçalardan yap)
- `parcalar/parca-01.md … parca-{son:02d}.md` — her biri ayrıntılı talimat + o parçanın kaynak metni
- `parcalar/parca-son.md` — bölüm sonu (sözlük, tekrar, sorular, alıştırma çözümleri) talimatı
- `sekiller/` — şekillerin kırpılmış görselleri
- `calisma_pdf.py` — kontrol + PDF üretimi

## Adımlar
1. `parcalar/parca-01.md`'den başlayarak SIRAYLA her parçayı işle: dosyadaki talimata ve kalite kurallarına birebir
   uy (her parçada kuralları yeniden oku; ilk parçalarda ne kadar ayrıntılıysan son parçada da o kadar ol). En üst
   satırda listelenen görselleri `sekiller/` içinden aç (yalnızca onları). Cevabı `parcalar/parca-NN-cevap.md`
   dosyasına yaz. Uzun bir parçayı dosyaya birkaç adımda ekleyebilirsin; ama hiçbir sayfayı atlama, kısaltma,
   özetleme. Terimleri parçalar boyunca tutarlı tut: önceki parçalarda seçtiğin Türkçe karşılığı değiştirme.
2. Bütün parçalar bitince `parcalar/parca-son.md`'deki talimatla bölüm sonunu üret. Terim tablolarını cevap
   dosyalarının sonlarından kendin topla. Cevabı `parcalar/parca-son-cevap.md` dosyasına yaz.
3. Çalıştır: `pip install reportlab pillow` (gerekirse) ve `python3 calisma_pdf.py .`
4. Kontrol raporunda (ekran çıktısı ve `{ad}_kontrol.md`) ⚠ olan sayfalar varsa YALNIZCA o sayfaları ilgili cevap
   dosyasında yeniden yaz ve 3. adımı tekrarla (en fazla 2 tur).
5. Bana `{ad}_calisma.pdf` dosyasını ve kontrol raporunun son hâlini ver.

## Yarıda kalırsa
- Limit ya da kesinti olursa kaldığın parçadan devam et: var olan `-cevap.md` dosyalarını yeniden yazma.
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
    print(f"   🔎 Yöntem: {yontem}  →  {len(bolumler)} bölüm"
          f"{' + sözlük' if sozluk and SOZLUGU_DAHIL_ET else ''}")

    klasor = os.path.join(cikti_ust or os.path.dirname(os.path.abspath(pdf_yolu)),
                          bolum_klasoru_adi(kitap_adi))
    shutil.rmtree(klasor, ignore_errors=True)
    os.makedirs(klasor)

    kayma = sayfa_kaymasi(doc)   # sayfa no satırlarını silmek için (yer imli PDF'te de)
    govde = govde_fontu(doc, range(doc.page_count))
    yazilan = []
    for no, baslik, bas, bit in bolumler:
        if bit < bas:
            print(f"  ⚠ Bölüm {no} atlandı (sayfa aralığı geçersiz: {bas + 1}–{bit + 1})")
            continue
        yazilan.append(bolumu_yaz(doc, kitap_adi, no, baslik, bas, bit, klasor, kayma, govde))
        _bildir(bolum_bitti, yazilan[-1])
    if sozluk and SOZLUGU_DAHIL_ET and sozluk[3] >= sozluk[2]:
        yazilan.append(bolumu_yaz(doc, kitap_adi, *sozluk, klasor, kayma, govde))
        _bildir(bolum_bitti, yazilan[-1])
    with open(os.path.join(klasor, "KULLANIM.md"), "w", encoding="utf-8") as f:
        f.write(KULLANIM)
    with open(os.path.join(klasor, f"_surum_{SURUM}.txt"), "w") as f:
        f.write(SURUM)

    print(f"\n✅ {len(yazilan)} dosya → {klasor}")
    return klasor, yazilan


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
                    yukleyici = DriveYukleyici(servis, f.id, bolum_klasoru_adi(kitap_adi))
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

    def __init__(self, servis, pdf_id, ad):
        self.servis, self.ad = servis, ad
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
                    self.atlanan = getattr(self, "atlanan", 0) + 1
                    return
        tur = {".md": "text/markdown", ".png": "image/png", ".pdf": "application/pdf"}.get(
            os.path.splitext(dad)[1], "text/plain")
        medya = MediaFileUpload(yol, mimetype=tur)
        if dad in mevcut and mevcut[dad]["mimeType"] != KLASOR_TIPI:
            self.servis.files().update(fileId=mevcut[dad]["id"], media_body=medya, supportsAllDrives=True).execute()
        else:
            self.servis.files().create(body={"name": dad, "parents": [uzak_id]}, media_body=medya,
                                       fields="id", supportsAllDrives=True).execute()

    def _klasor(self, ad, uzak_ust, mevcut):
        x = mevcut.get(ad)
        if x and x["mimeType"] == KLASOR_TIPI:
            return x["id"]
        return self.servis.files().create(body={"name": ad, "mimeType": KLASOR_TIPI, "parents": [uzak_ust]},
                                          fields="id", supportsAllDrives=True).execute()["id"]

    def _aynala(self, yerel, uzak_id):
        mevcut = self._icerik(uzak_id)
        adlar = set()
        for dad in sorted(os.listdir(yerel)):
            adlar.add(dad)
            yol = os.path.join(yerel, dad)
            if os.path.isdir(yol):
                self._aynala(yol, self._klasor(dad, uzak_id, mevcut))
            else:
                self._dosya(yol, uzak_id, mevcut)
        for dad, x in mevcut.items():            # bölüm içinde eskiden kalanlar çöpe (cevaplar hariç)
            if dad not in adlar and not dad.endswith(KORUNANLAR):
                self.servis.files().update(fileId=x["id"], body={"trashed": True}, supportsAllDrives=True).execute()

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