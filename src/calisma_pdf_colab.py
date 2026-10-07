"""CalismaPdf (Colab) — LLM'in yazdığı cevap dosyalarından çalışma PDF'ini ve kontrol raporunu üretir.

Kullanım: Colab'de yeni bir not defteri aç, bu dosyanın tamamını tek hücreye yapıştır, çalıştır.
Sana iki yol sorulur:
  1) ENTER'a bas → bölüm klasör(ler)inin ZIP'ini yükle (ör. 04_Software_processes.zip).
     Sonuçlar (PDF + kontrol raporu) zip olarak iner.
  2) Drive klasör linki yapıştır (ders klasörü, Kitap klasörü ya da <kitap>_Bolumler) →
     cevap dosyası olan bölümleri Drive'da bulur, PDF'i ve raporu o bölüm klasörüne yazar.
     PDF'i cevaplardan daha yeni olan bölümler atlanır (yalnızca değişenler yeniden üretilir).

Bölüm klasörü = içinde parcalar/ (parca-NN.md + parca-NN-cevap.md) ve sekiller/ olan klasör
(kitap_paketle.py'nin ürettiği yapı). PDF üretimi ve kontrol, bölüm klasöründeki calisma_pdf.py ile aynıdır.
"""
import base64
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
import zlib

SURUM = "1.2"
CIKTI_ADLARI = ("_calisma.pdf", "_calisma.md", "_kontrol.md")

CALISMA_PDF_KODU = """
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
"""


def _kur(*paketler):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *paketler], check=False)


def calisma_pdf_modulu():
    """Gömülü calisma_pdf.py'yi modül olarak yükler."""
    import types
    kod = zlib.decompress(base64.b64decode("".join(CALISMA_PDF_KODU.split()))).decode("utf-8")
    modul = types.ModuleType("calisma_pdf")
    modul.__file__ = "/content/calisma_pdf.py"
    exec(compile(kod, "calisma_pdf.py", "exec"), modul.__dict__)
    return modul


def bolum_klasorleri(kok):
    """Kökün altında içinde parcalar/*-cevap.md olan bölüm klasörlerini bulur."""
    sonuc = []
    for yol, klasorler, dosyalar in os.walk(kok):
        klasorler[:] = [k for k in klasorler if k != "__MACOSX"]       # Mac "Sıkıştır" artığı
        if os.path.basename(yol) == "parcalar" and any(d.endswith("-cevap.md") and not d.startswith("._")
                                                       for d in dosyalar):
            sonuc.append(os.path.dirname(yol))
    return sorted(sonuc)


def bolumu_isle(cp, bolum):
    ad = os.path.basename(bolum)
    print("\n" + "─" * 60 + f"\n📖 {ad}\n" + "─" * 60)
    try:
        sorun = cp.calistir(bolum)
    except SystemExit as e:
        print(f"  ❌ {e}")
        return None
    except Exception as e:
        print(f"  ❌ {ad}: {e}")
        return None
    return [os.path.join(bolum, ad + s) for s in CIKTI_ADLARI if os.path.exists(os.path.join(bolum, ad + s))], sorun


# ------------------------------------------------------------------ 1) ZIP yolu
def zip_yolu(cp):
    from google.colab import files
    calisma = "/content/calisma_girdi"
    shutil.rmtree(calisma, ignore_errors=True)
    os.makedirs(calisma)
    print("\n📤 Bölüm klasörünün zip'ini seç (birden fazla zip seçebilirsin)...")
    yuklenen = files.upload()
    for ad, veri in yuklenen.items():
        if ad.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(veri)) as z:
                z.extractall(os.path.join(calisma, os.path.splitext(ad)[0]))
        else:
            print(f"  ⚠ {ad} zip değil, atlandı.")
    bolumler = bolum_klasorleri(calisma)
    if not bolumler:
        raise SystemExit("⚠ Zip'te cevap dosyası (parcalar/parca-NN-cevap.md) olan bölüm klasörü bulunamadı.")
    cikti = "/content/calisma_sonuclari"
    shutil.rmtree(cikti, ignore_errors=True)
    os.makedirs(cikti)
    ozet = []
    for b in bolumler:
        r = bolumu_isle(cp, b)
        if r:
            for y in r[0]:
                shutil.copy(y, cikti)
            ozet.append((os.path.basename(b), r[1]))
    _ozet_yaz(ozet)
    if os.listdir(cikti):
        z = shutil.make_archive("/content/calisma_sonuclari", "zip", cikti)
        files.download(z)
        print(f"\n⬇️  {os.path.basename(z)} indiriliyor (PDF + kontrol raporu).")


# ------------------------------------------------------------------ 2) Drive yolu
KLASOR = "application/vnd.google-apps.folder"


def _listele(servis, ust_id):
    sonuc, sayfa = [], None
    while True:
        r = servis.files().list(q=f"'{ust_id}' in parents and trashed = false",
                                fields="nextPageToken, files(id, name, mimeType, modifiedTime)", pageSize=1000,
                                pageToken=sayfa, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        sonuc += r["files"]
        sayfa = r.get("nextPageToken")
        if not sayfa:
            return sonuc


def _indir(servis, dosya_id, hedef):
    from googleapiclient.http import MediaIoBaseDownload
    with open(hedef, "wb") as f:
        indirici = MediaIoBaseDownload(f, servis.files().get_media(fileId=dosya_id, supportsAllDrives=True))
        bitti = False
        while not bitti:
            _, bitti = indirici.next_chunk()


def drive_bolumleri(servis, kok_id, derinlik=6):
    """Drive'da içinde parcalar/ altında -cevap.md olan bölüm klasörlerini bulur: [(ad, id, icerik)]."""
    bulunan, sira = [], [(kok_id, None, 0)]
    while sira:
        kid, ad, d = sira.pop(0)
        icerik = _listele(servis, kid)
        parcalar = next((x for x in icerik if x["name"] == "parcalar" and x["mimeType"] == KLASOR), None)
        if parcalar:
            pc = _listele(servis, parcalar["id"])
            if any(x["name"].endswith("-cevap.md") for x in pc):
                bulunan.append((ad or "bolum", kid, icerik, parcalar, pc))
            continue
        if d < derinlik:
            sira += [(x["id"], x["name"], d + 1) for x in icerik if x["mimeType"] == KLASOR
                     and x["name"] not in ("sekiller", "Slaytlar", "Jsonlar")]
    return bulunan


def drive_yolu(cp, link):
    from google.colab import auth
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    kok_id = link.split("folders/")[1].split("?")[0].split("/")[0] if "folders/" in link else \
        (link.split("id=")[1].split("&")[0] if "id=" in link else link)
    print("\n☁️  Drive izni isteniyor...")
    auth.authenticate_user()
    servis = build("drive", "v3", cache_discovery=False)
    print("🔍 Cevap dosyası olan bölümler aranıyor...")
    bolumler = drive_bolumleri(servis, kok_id)
    if not bolumler:
        raise SystemExit("⚠ Bu klasörün altında cevap dosyası (parcalar/parca-NN-cevap.md) olan bölüm yok.\n"
                         "   LLM'in yazdığı -cevap.md dosyalarını Drive'daki bölüm klasörünün parcalar/ klasörüne koy.")
    calisma = "/content/calisma_drive"
    shutil.rmtree(calisma, ignore_errors=True)
    ozet = []
    for ad, bid, icerik, parcalar, pc in bolumler:
        son_cevap = max(x["modifiedTime"] for x in pc if x["name"].endswith("-cevap.md"))
        pdf = next((x for x in icerik if x["name"] == ad + "_calisma.pdf"), None)
        if pdf and pdf["modifiedTime"] > son_cevap:
            print(f"  ✅ {ad}: PDF güncel, atlandı")
            continue
        yerel = os.path.join(calisma, ad)
        os.makedirs(os.path.join(yerel, "parcalar"))
        os.makedirs(os.path.join(yerel, "sekiller"))
        print(f"  ⏬ {ad}: indiriliyor...")
        for x in pc:
            if x["name"].endswith(".md"):
                _indir(servis, x["id"], os.path.join(yerel, "parcalar", x["name"]))
        sek = next((x for x in icerik if x["name"] == "sekiller" and x["mimeType"] == KLASOR), None)
        if sek:
            for x in _listele(servis, sek["id"]):
                if x["mimeType"] != KLASOR:
                    _indir(servis, x["id"], os.path.join(yerel, "sekiller", x["name"]))
        r = bolumu_isle(cp, yerel)
        if not r:
            continue
        ozet.append((ad, r[1]))
        mevcut = {x["name"]: x["id"] for x in icerik}
        for y in r[0]:
            dad = os.path.basename(y)
            tur = "application/pdf" if dad.endswith(".pdf") else "text/markdown"
            medya = MediaFileUpload(y, mimetype=tur)
            if dad in mevcut:
                servis.files().update(fileId=mevcut[dad], media_body=medya, supportsAllDrives=True).execute()
            else:
                servis.files().create(body={"name": dad, "parents": [bid]}, media_body=medya,
                                      fields="id", supportsAllDrives=True).execute()
        print(f"  ☁️  {ad}: PDF ve kontrol raporu Drive'daki bölüm klasörüne yazıldı.")
    _ozet_yaz(ozet)


def _ozet_yaz(ozet):
    if not ozet:
        print("\n✨ Üretilecek yeni PDF yok.")
        return
    print("\n" + "=" * 60 + "\n📋 ÖZET\n" + "=" * 60)
    for ad, sorun in ozet:
        print(f"  {'✅' if not sorun else '⚠'} {ad}: " + ("sorun yok" if not sorun else
              f"{sorun} sorun — <bölüm>_kontrol.md'deki sayfaları LLM'e yeniden yazdır, sonra bunu tekrar çalıştır"))


def main():
    print("=" * 60 + f"\n📄 ÇALIŞMA PDF'İ ÜRET (CalismaPdf v{SURUM})\n" + "=" * 60)
    _kur("reportlab", "pillow")
    cp = calisma_pdf_modulu()
    print("Bölüm klasörünü zip olarak yükleyeceksen ENTER'a bas.")
    print("Bölümler Drive'daysa (cevap dosyalarıyla birlikte) klasör linkini yapıştır.\n")
    link = input("🔗 Drive klasör linki (boş = zip yükle): ").strip()
    if link:
        drive_yolu(cp, link)
    else:
        zip_yolu(cp)


if __name__ == "__main__":
    main()
