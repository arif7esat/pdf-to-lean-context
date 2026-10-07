# Sürüm geçmişi

Bu proje, İngilizce ders kitaplarını ve ders slaytlarını Türkçe, sayfa sayfa öğretici çalışma
dokümanlarına dönüştüren bir hat (pipeline) kurar. Geliştirme Ian Sommerville, *Software Engineering*
(8. baskı) üzerinde yapıldı ve kitabın tamamında (865 sayfa, 32 bölüm + sözlük, 432 şekil) doğrulandı.

> Not: Depoda yalnızca son sürümler ve iki ara anlık görüntü (v3.2, v3.3) kod olarak bulunur. Daha
> eski sürümlerin kodu saklanmadı; aşağıda ne değiştiği belgelenmiştir.

## SlaytPaketle

- **v1.x → v1.9** — Ders slaytlarını (PPTX/PDF) LLM'e verilecek pakete dönüştürür: slayt metni,
  görsel içeren slaytların resimleri, görsel kontrol mekanizması, kalite raporu (`Slaytlar/Jsonlar`),
  PDF slaytlar için aynı seviyede çıktı, Drive indirmesinde "çok fazla erişim" hatasına karşı Drive API.

## kitap_paketle (kitabı bölümlere ayırır, şekilleri kırpar, LLM parçaları ve talimatı üretir)

- **v2.2** — Her bölüm kendi klasöründe: temiz metin (sayfa işaretli `<!-- PDF s. N · kitap s. M -->`),
  `sekiller/`, `parcalar/` (≈1800 kelimelik hazır promptlar + bölüm sonu), `TALIMAT.md` (LLM ajanı için
  adımlar), gömülü `calisma_pdf.py`. Şekiller alt yazıdan ("Figure 4.1") bulunur; şekil bölgeleri metinden
  redaksiyonla çıkarılır. Bölüm sınırları: PDF yer imleri → basılı içindekiler + sayfa kayması → tek bölüm.
- **v2.3** — Özel fontlu madde işaretinin metne "I" olarak çıkması düzeltildi; satır sonunda bölünen
  birleşik kelimelerin tiresi geri konur ("service-centric").
- **v2.4** — Eski sohbetteki kalite kuralları "çalışma sözleşmesi" olarak prompta işlendi (A • Tam çeviri /
  C • Şimdi bunu anlayalım, beş soru, şekil okuma, etiketler, üslup, bölüm sonu yapısı). Kalıcı terim
  listesi (`TERIMLER`, yalnız bölümde geçenler prompta girer, "yanlış:" karşılıklar işaretli).
- **v2.5–2.6** — `calisma_pdf`: eksik glifler (→ ≤ ✓) için yedek yazı tipi; "yanlış:" terim kullanımını
  parçalarda ve bölüm sonunda yakalayan kontrol. Promptta terim kuralı sertleştirildi.
- **v2.7** — Colab'de her bölüm biter bitmez Drive'a yüklenir; sürüm dosyası en sona yazılır (yarıda
  kalan iş yeniden işlenir); LLM cevapları ve çalışma PDF'leri asla silinmez.
- **v2.8** — Sıfır kalınlıktaki çizgiler (ok, aktör figürü, tablo çizgisi) artık atılmıyor; kırpma kutusu
  şekle ait taşan/yakın her parçayı içine alacak şekilde büyür; kenar payına düşen metin beyazlatılır;
  şeklin içindeki yazılar PDF'ten metin olarak prompta eklenir.
- **v2.9** — İki aşamalı kırpma: (1) PDF nesneleri, (2) bağımsız piksel denetimi (sayfa çizilir, gövde
  metni/alt yazılar silinir, kalan mürekkep bölgeleri şekle katılır; kutu yalnız büyür). Uyarılar:
  alt yazısı olup şekli bulunamayan, metinde adı geçip kırpılamayan, yanında dışarıda kalan çizim olan.
  "(continued)" şekilleri ayrı dosya adı alır.
- **v3.0** — Metin tablosu olan şekiller ayrıca markdown tablo olarak verilir (işaretli matrisler hariç).
  Şekil işleme `bolum_sekilleri()` fonksiyonunda toplandı (sekil_cikar ile ortak).
- **v3.1** — Kitabın tamamında test: içindekilerdeki "Part N" satırının sayfa sanılması (1. bölüm tek sayfa
  çıkıyordu); alıştırma cümlelerinin alt yazı sanılması (alıştırma metni siliniyordu); üst üste duran
  iki şeklin tek resimde birleşmesi; tablo alt kenarının kesilmesi; alt yazı parçalarının şekil yazısına
  karışması; satırları yığılmış tabloların reddi.
- **v3.2** — Kenar sütunundaki vaka simgeleri (kitap, şırınga) kırpmadan çıkarılır (yalnız güvenliyse);
  alt yazılar kırpılan resimde hiç görünmez.
- **v3.3** — Hız: Drive yüklemesi paralel (6 kanal) ve Drive'daki aynı dosyalar yeniden yüklenmez (md5);
  kümeleme algoritması O(n³)'ten sıralı taramaya (aynı sonuç, 300 rastgele testle doğrulandı); tablo
  araması yalnız yazılı şekillerde; bölümler çok çekirdekte paralel işlenir (çıktı birebir aynı).
  Düzeltme: tablo bulucu komşu şeklin tablosunu döndürebiliyordu (6.14, 26.12, 28.2) — artık yalnız
  kırpma alanındaki tablo kabul edilir.
- **v3.4** — Tablo hücrelerinde satır sonu tiresi korunur ("off-site"; önceden "offsite").

### v3.4 doğrulaması (kitabın tamamı)
- 32 bölüm + sözlük, doğru sınırlar; 432 şekil, her bölümde numaralar kesintisiz, metinde anılan her
  şekil kırpılmış, çakışan kırpma yok, 0 uyarı.
- 82 metin tablosunun tüm kelimeleri kendi şeklinin içinden; aynı tablo iki şekle bağlı değil.
- Metin kapsaması: 198.826 kelimenin tamamı md'de (kalan farklar satır sonu bölünmesi kaynaklı).

## sekil_cikar (yalnız şekiller + görsel denetim + çevrilmiş bölümleri güncelleme)

- **v1.0** — Kitabın bütün şekillerini kitap_paketle ile aynı kodla çıkarır; her şekil için kontrol
  sayfası (kırpılan resim + kitap sayfasında kırmızı çerçeve); rapor. `--guncelle`: çevrilmiş bölümün
  eski şekillerini karşılaştırır (yalnız gerçek içerik farkı), değiştirir, `SEKIL_DUZELT.md` yazar.
- **v1.1–1.4** — Gömülü kitap_paketle güncellemeleri; çevirisi olmayan klasör verilirse hiçbir şeye
  dokunmadan durur; klasör adı ne olursa olsun (Codex görev klasörü dahil) doğru bölümü kendisi bulur.

## calisma_pdf / calisma_pdf_colab

- LLM cevaplarını denetler (her kaynak sayfa var mı, A ve C bölümleri var mı, çeviri özetlenmiş mi,
  şekil bağlantıları korunmuş mu, yasaklı terim kullanılmış mı) ve Türkçe çalışma PDF'ini üretir
  (yer imleri, tablolar, şekiller). `calisma_pdf_colab.py`: aynı iş Colab'de (zip yükleyerek ya da Drive'dan).
