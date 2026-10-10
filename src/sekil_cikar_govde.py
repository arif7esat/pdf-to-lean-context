"""SekilCikar — kitaptan YALNIZCA şekilleri ve tabloları çıkarır, her birini görsel olarak denetlenebilir kılar.

Ne üretir (<kitap>_Sekiller/ klasörü):
  <bölüm>/sekiller/*.png        kırpılmış şekiller — kitap_paketle ile AYNI dosya adları ve AYNI kırpma
  <kitap>_sekil_kontrol.pdf     her şekil için bir sayfa: üstte kırpılan görsel, altta kitabın o sayfası
                                (kırmızı çerçeve = kırpılan alan, mavi = alt yazı). Bütün kitabı birkaç
                                dakikada gözle tarayıp "bu kırpma tam mı?" diye bakabilirsin.
  <kitap>_sekil_raporu.md       bölüm bölüm şekil sayıları ve bütün ⚠ uyarılar

Kullanım
  Colab:  dosyanın tamamını bir hücreye yapıştır, çalıştır, Drive klasör linkini ver (kitap_paketle ile aynı).
  Mac:    python3 sekil_cikar.py "Software engineering.pdf"
          python3 sekil_cikar.py "Software engineering.pdf" --guncelle 06_Requirements 07_Requirements_engineering
              → verilen (çevirisi yapılmış) bölüm klasörlerinin şekillerini yenileriyle değiştirir
                (eskileri sekiller_eski/ içine yedekler), hangi şekillerin değiştiğini bulur ve
                LLM'e verilecek hazır düzeltme talimatını SEKIL_DUZELT.md olarak yazar.
"""
import base64
import os
import re
import shutil
import sys
import types
import zlib

SURUM = "1.7"
KP_KODU = """
__KP_BLOB__
"""
_kp = None


def kp():
    """Gömülü kitap_paketle modülü (şekil bulma/kırpma kodunun TEK kaynağı)."""
    global _kp
    if _kp is None:
        kod = zlib.decompress(base64.b64decode("".join(KP_KODU.split()))).decode("utf-8")
        m = types.ModuleType("kitap_paketle")
        m.__file__ = "kitap_paketle.py"
        sys.modules["kitap_paketle"] = m
        exec(compile(kod, "kitap_paketle.py", "exec"), m.__dict__)
        _kp = m
    return _kp


def bolumleri_bul(doc):
    k = kp()
    sonuc = k.yer_imlerinden(doc) or k.icindekilerden(doc) or k.tek_bolum(doc)
    if not sonuc:
        raise SystemExit("❌ Bölümler bulunamadı (yer imi / içindekiler yok).")
    bolumler, sozluk = sonuc
    if sozluk and k.SOZLUGU_DAHIL_ET and sozluk[3] >= sozluk[2]:
        bolumler = list(bolumler) + [sozluk]
    return bolumler


def kitabin_sekilleri(pdf_yolu, cikti_ust=None, bolum_bitti=None):
    import pymupdf
    k = kp()
    doc = pymupdf.open(pdf_yolu)
    kitap_adi = os.path.splitext(os.path.basename(pdf_yolu))[0]
    klasor = os.path.join(cikti_ust or os.path.dirname(os.path.abspath(pdf_yolu)),
                          re.sub(r"[^\w\-]+", "_", kitap_adi).strip("_") + "_Sekiller")
    shutil.rmtree(klasor, ignore_errors=True)
    os.makedirs(klasor)
    print(f"\n📖 {kitap_adi}  ({doc.page_count} sayfa) — yalnızca şekiller")
    govde = k.govde_fontu(doc, range(doc.page_count))
    kayma = k.sayfa_kaymasi(doc)
    kayitlar, rapor = [], [f"# Şekil raporu — {kitap_adi}", ""]
    toplam_uyari = 0
    for no, baslik, bas, bit in bolumleri_bul(doc):
        if bit < bas:
            continue
        ad = k.dosya_adi(no, baslik)[:-3]
        bolum_klasoru = os.path.join(klasor, ad)
        uyarilar = []
        sekiller = k.bolum_sekilleri(doc, list(range(bas, bit + 1)), no, govde,
                                     os.path.join(bolum_klasoru, "sekiller"), uyarilar)
        n = sum(len(v) for v in sekiller.values())
        print(f"  ✓ {ad:45s} {n:3d} şekil" + (f"  ⚠ {len(uyarilar)} uyarı" if uyarilar else ""))
        rapor.append(f"## {ad} — {n} şekil" + (f", ⚠ {len(uyarilar)} uyarı" if uyarilar else ", uyarı yok"))
        rapor += [f"- {u}" for u in uyarilar] + [""]
        toplam_uyari += len(uyarilar)
        for idx in sorted(sekiller):
            for sk in sekiller[idx]:
                kayitlar.append((ad, idx, sk))
        if n and bolum_bitti:
            bolum_bitti(bolum_klasoru)
    rapor.insert(2, f"**Toplam:** {len(kayitlar)} şekil, "
                    + ("uyarı yok ✅" if not toplam_uyari else f"{toplam_uyari} uyarı ⚠ (aşağıda)") + "\n")
    with open(os.path.join(klasor, f"{os.path.basename(klasor)[:-9]}_sekil_raporu.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rapor) + "\n")
    kontrol_pdf(doc, kayitlar, os.path.join(klasor, f"{os.path.basename(klasor)[:-9]}_sekil_kontrol.pdf"), kayma, klasor)
    print(f"\n✅ {len(kayitlar)} şekil → {klasor}"
          + ("" if not toplam_uyari else f"\n⚠ {toplam_uyari} uyarı — {os.path.basename(klasor)[:-9]}_sekil_raporu.md"))
    return klasor, kayitlar


def kontrol_pdf(doc, kayitlar, yol, kayma=None, klasor=None):
    """Her şekil için bir denetim sayfası: kırpılan görsel + kitabın sayfası üzerinde kırpma çerçevesi."""
    import pymupdf
    k = kp()
    out = pymupdf.open()
    W, H = 595, 842
    for ad, idx, sk in kayitlar:
        p = out.new_page(width=W, height=H)
        basili = f" / kitap s. {idx - kayma + 1}" if kayma is not None else ""
        baslik = (f"<b>{'Tablo' if sk['tur'] == 'tablo' else 'Şekil'} {sk['no']}</b> — {sk['baslik'][:90]}"
                  f"<br>{ad} · PDF s. {idx + 1}{basili} · {sk['dosya']}"
                  + ("<br><span style='color:#c00'>⚠ yanında şekle alınmamış çizim var — dikkatle bak</span>"
                     if sk.get("kenar_uyari") else ""))
        try:
            p.insert_htmlbox(pymupdf.Rect(30, 20, W - 30, 75), baslik, css="*{font-size:10px;font-family:sans-serif}")
        except Exception:
            p.insert_text((30, 35), f"{sk['no']} - PDF s. {idx + 1} - {sk['dosya']}", fontsize=9)
        # Üst yarı: kırpılan görsel (dosyadaki hali)
        sayfa = doc[idx]
        r = pymupdf.Rect(sk["kutu"])
        ust = pymupdf.Rect(30, 80, W - 30, 400)
        olcek = min(ust.width / r.width, ust.height / r.height, 2.0)
        hedef = pymupdf.Rect(ust.x0, ust.y0, ust.x0 + r.width * olcek, ust.y0 + r.height * olcek)
        png = os.path.join(klasor or "", ad, "sekiller", sk["dosya"])
        if os.path.exists(png):                       # diske yazılan dosyanın KENDİSİ gösterilir
            from PIL import Image
            w, h = Image.open(png).size
            olcek = min(ust.width / w, ust.height / h)
            hedef = pymupdf.Rect(ust.x0, ust.y0, ust.x0 + w * olcek, ust.y0 + h * olcek)
            p.insert_image(hedef, filename=png)
        else:
            p.show_pdf_page(hedef, doc, idx, clip=r + (-6, -6, 6, 6))
        p.draw_rect(hedef, color=(0.6, 0.6, 0.6), width=0.5)
        # Alt yarı: kitabın sayfası, kırpma çerçevesiyle
        alt = pymupdf.Rect(30, 415, W - 30, H - 25)
        o2 = min(alt.width / sayfa.rect.width, alt.height / sayfa.rect.height)
        hedef2 = pymupdf.Rect(alt.x0, alt.y0, alt.x0 + sayfa.rect.width * o2, alt.y0 + sayfa.rect.height * o2)
        p.show_pdf_page(hedef2, doc, idx)

        def donustur(x):
            x = pymupdf.Rect(x)
            return pymupdf.Rect(hedef2.x0 + x.x0 * o2, hedef2.y0 + x.y0 * o2, hedef2.x0 + x.x1 * o2, hedef2.y0 + x.y1 * o2)
        p.draw_rect(hedef2, color=(0.6, 0.6, 0.6), width=0.5)
        p.draw_rect(donustur(sk["alt_yazi_kutu"]), color=(0, 0.3, 1), width=1)
        p.draw_rect(donustur(r), color=(1, 0, 0), width=1.2)
    if len(out):
        out.set_toc([[1, f"{sk['no']} · {ad}", i + 1] for i, (ad, _, sk) in enumerate(kayitlar)])
        out.save(yol, garbage=3, deflate=True)
        print(f"🔍 Kontrol PDF'i: {os.path.basename(yol)} ({len(out)} sayfa)")


# ---------------------------------------------------------------- Çevirisi yapılmış bölümleri güncelle (Mac)
def _murekkep(yol):
    """Görseli gri yapar ve boş (beyaz) kenarlarını atar: kırpma payı farkları karşılaştırmayı bozmasın."""
    from PIL import Image, ImageOps
    g = Image.open(yol).convert("L")
    kutu = ImageOps.invert(g).point(lambda v: 255 if v > 40 else 0).getbbox()
    return g.crop(kutu) if kutu else g


def _ayni_mi(a, b):
    """İki kırpma aynı içeriği mi gösteriyor? (yalnızca beyaz kenar payı farkı 'aynı' sayılır)"""
    from PIL import ImageChops
    x, y = _murekkep(a), _murekkep(b)
    if abs(x.width - y.width) > max(8, 0.02 * x.width) or abs(x.height - y.height) > max(8, 0.02 * x.height):
        return False
    y = y.resize(x.size)
    fark = ImageChops.difference(x, y).point(lambda v: 255 if v > 80 else 0)
    return fark.histogram()[255] < 0.01 * x.width * x.height


def _bolum_klasorunu_bul(verilen, sekil_klasoru):
    """Klasör adı ne olursa olsun doğru bölümü bulur: verilen klasörün kendisi, içindeki bir alt klasör
    ya da içindeki 'NN_Ad.md' dosyasının adı bölümü belirler (Codex görev klasörü verilse de çalışır)."""
    verilen = os.path.abspath(verilen.rstrip("/"))
    bolumler = {d for d in os.listdir(sekil_klasoru) if os.path.isdir(os.path.join(sekil_klasoru, d))}
    adaylar = [verilen] + [os.path.join(kok, d) for kok, dirs, _ in os.walk(verilen) for d in dirs
                           if kok.count(os.sep) - verilen.count(os.sep) < 3]
    for a in adaylar:                                      # 1) adı birebir tutan klasör
        if os.path.basename(a) in bolumler and os.path.isdir(os.path.join(a, "parcalar")):
            return a
    for a in adaylar:                                      # 2) içinde parcalar/ olan klasör + NN_*.md
        if os.path.isdir(os.path.join(a, "parcalar")):
            for f in os.listdir(a):
                m = re.match(r"(\d{2}|Ek_[A-Z0-9]+)_.*\.md$", f)     # bölüm ("07_…") ya da ek ("Ek_A_…")
                if m and not f.endswith(("_calisma.md", "_kontrol.md")):
                    eslesen = [b for b in bolumler if b.startswith(m.group(1) + "_")]
                    if eslesen:
                        hedef = os.path.join(os.path.dirname(a), eslesen[0])
                        if os.path.basename(a) != eslesen[0]:
                            return _AdliKlasor(a, eslesen[0])
                        return a
    return verilen


class _AdliKlasor(str):
    """Klasörün adı bölüm adından farklıysa: yol aynı, ama 'ad' olarak bölüm adı kullanılır."""
    def __new__(cls, yol, ad):
        o = str.__new__(cls, yol)
        o.bolum_adi = ad
        return o


def guncelle(sekil_klasoru, bolum_klasoru, kayitlar):
    """Yeni şekilleri çevirisi yapılmış bölüm klasörüne koyar, değişenleri bulur, SEKIL_DUZELT.md yazar."""
    bolum_klasoru = _bolum_klasorunu_bul(bolum_klasoru, sekil_klasoru)
    ad = getattr(bolum_klasoru, "bolum_adi", None) or os.path.basename(os.path.abspath(bolum_klasoru.rstrip("/")))
    bolum_klasoru = str(bolum_klasoru)
    print(f"  📂 {ad}  ←  {bolum_klasoru}")
    yeni = os.path.join(sekil_klasoru, ad, "sekiller")
    eski = os.path.join(bolum_klasoru, "sekiller")
    if not os.path.isdir(yeni):
        print(f"  ⚠ {ad}: kitapta bu adla bölüm yok ya da şekli yok — atlandı")
        return
    parcalar_klasoru = os.path.join(bolum_klasoru, "parcalar")
    if not os.path.isdir(parcalar_klasoru) or not any(f.endswith("-cevap.md") for f in os.listdir(parcalar_klasoru)):
        print(f"  ❌ {ad}: bu klasörde çeviri yok (parcalar/*-cevap.md bulunamadı) — HİÇBİR ŞEY DEĞİŞTİRİLMEDİ.\n"
              f"     Codex'in çeviriyi yazdığı bölüm klasörünü ver: {os.path.abspath(bolum_klasoru)}")
        return
    degisen, eklenen = [], []
    for f in sorted(os.listdir(yeni)):
        hedef = os.path.join(eski, f)
        if not os.path.exists(hedef):
            eklenen.append(f)
        elif not _ayni_mi(hedef, os.path.join(yeni, f)):
            degisen.append(f)
    if not degisen and not eklenen:
        print(f"  ✅ {ad}: şekiller zaten doğru, değişiklik yok")
        return
    yedek = os.path.join(bolum_klasoru, "sekiller_eski")
    if os.path.isdir(eski) and not os.path.isdir(yedek):
        shutil.copytree(eski, yedek)
    os.makedirs(eski, exist_ok=True)
    for f in degisen + eklenen:
        shutil.copy(os.path.join(yeni, f), os.path.join(eski, f))
    # Hangi cevap sayfaları bu şekilleri kullanıyor?
    bilgi = {sk["dosya"]: (idx, sk) for a, idx, sk in kayitlar if a == ad}
    parcalar = os.path.join(bolum_klasoru, "parcalar")
    satirlar = [f"# Şekil düzeltmesi — {ad}", "",
                "Aşağıdaki şekillerin görselleri düzeltildi (önceki kırpmada kenarları eksikti). Yeni görseller "
                "`sekiller/` içinde. Her şekil için YALNIZCA şunları yeniden yaz: A bölümündeki \"Şekil X - …\" "
                "açıklama satırı (etiketleri aşağıdaki listeden al) ve C bölümünde o şekli anlatan kısım. "
                "Çevirinin geri kalanına, başka sayfalara ve dosyalara dokunma. Görselde ve listede olmayan bir "
                "etiketi tahmin etme. Daha önce yazdığın \"kırpma eksik / okunamıyor\" türü notları kaldır.",
                "Bitince: `python3 calisma_pdf.py .`", ""]
    for f in degisen + eklenen:
        idx, sk = bilgi.get(f, (None, {}))
        yerler = []
        if os.path.isdir(parcalar):
            for c in sorted(os.listdir(parcalar)):
                if c.endswith("-cevap.md") and f in open(os.path.join(parcalar, c), encoding="utf-8").read():
                    yerler.append(c)
        satirlar.append(f"## {f}" + (f" — Şekil {sk.get('no')} (PDF s. {idx + 1})" if idx is not None else ""))
        satirlar.append(f"- Cevap dosyası: {', '.join(yerler) if yerler else 'bulunamadı — şekil numarasıyla ara'}")
        if sk.get("tablo_md"):
            satirlar += ["- Şekil bir metin tablosu; içeriği (A'da aynı yapıda çevir):", "", sk["tablo_md"], ""]
        elif sk.get("yazilar"):
            satirlar.append(f"- Şekildeki yazılar (PDF'ten): {sk['yazilar']}")
        satirlar.append("")
    with open(os.path.join(bolum_klasoru, "SEKIL_DUZELT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(satirlar))
    print(f"  🔁 {ad}: {len(degisen)} şekil düzeltildi, {len(eklenen)} yeni şekil → SEKIL_DUZELT.md yazıldı "
          f"(eskiler sekiller_eski/ içinde)")


# ---------------------------------------------------------------- Colab
def colab_calistir():
    k = kp()
    k._kur("-U", "gdown")
    import gdown
    print("=" * 60 + f"\n🖼  KİTAPTAN ŞEKİLLERİ ÇIKAR (SekilCikar v{SURUM})\n" + "=" * 60)
    link = input("🔗 Drive klasör linki (kitap_paketle ile aynı): ").strip()
    kid = link.split("folders/")[1].split("?")[0].split("/")[0] if "folders/" in link else \
        (link.split("id=")[1].split("&")[0] if "id=" in link else link)
    calisma = "/content/sekil_kitap"
    shutil.rmtree(calisma, ignore_errors=True)
    os.makedirs(calisma)
    liste = gdown.download_folder(id=kid, output=calisma + os.sep, skip_download=True, quiet=True) or []
    isler = []
    for f in liste:
        parcalar = f.path.replace("\\", "/").split("/")
        if f.path.lower().endswith(".pdf") and len(parcalar) > 1 and \
                k._klasor_anahtari(parcalar[-2]) in k.KITAP_KLASORLERI:
            isler.append(f)
    if not isler:
        raise SystemExit("⚠ 'Kitap' klasörünün doğrudan içinde PDF bulunamadı.")
    servis = None
    try:
        from google.colab import auth
        from googleapiclient.discovery import build
        auth.authenticate_user()
        servis = build("drive", "v3", cache_discovery=False)
    except Exception as e:
        print(f"⚠ Drive izni alınamadı ({e}); sonuçlar zip olarak inecek.")
    cikti = "/content/sekil_sonuc"
    shutil.rmtree(cikti, ignore_errors=True)
    os.makedirs(cikti)
    for f in isler:
        os.makedirs(os.path.dirname(f.local_path), exist_ok=True)
        print(f"\n⏬ {f.path}")
        if not k._indir(servis, f.id, f.local_path, gdown):
            print("  ❌ indirilemedi")
            continue
        ad = re.sub(r"[^\w\-]+", "_", os.path.splitext(os.path.basename(f.local_path))[0]).strip("_") + "_Sekiller"
        yukleyici = None
        if servis:
            try:
                yukleyici = k.DriveYukleyici(servis, f.id, ad)
            except Exception as e:
                print(f"  ⚠ Drive klasörü hazırlanamadı ({e})")
        klasor, _ = kitabin_sekilleri(f.local_path, cikti, yukleyici.bolum if yukleyici else None)
        os.remove(f.local_path)
        if yukleyici:
            yukleyici.bitir(klasor)
    z = shutil.make_archive("/content/sekil_sonuc", "zip", cikti)
    try:
        from google.colab import files
        files.download(z)
    except Exception:
        print(f"⬇️  {z}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        pdf = sys.argv[1]
        klasor, kayitlar = kitabin_sekilleri(pdf)
        if "--guncelle" in sys.argv:
            print("\n🔁 Çevirisi yapılmış bölümler güncelleniyor:")
            for b in sys.argv[sys.argv.index("--guncelle") + 1:]:
                guncelle(klasor, b, kayitlar)
    elif "google.colab" in sys.modules or os.path.exists("/content"):
        colab_calistir()
    else:
        print(__doc__)
