# pdf-to-lean-context

İngilizce ders kitaplarını ve ders slaytlarını, LLM'e temiz metin ve kırpılmış şekillerle verip Türkçe, sayfa sayfa öğretici çalışma dokümanlarına dönüştürmek için bir araç seti.

## Ne yapar

İngilizce ders kitabı veya slaytı → Türkçe, sayfa sayfa **"A • Tam çeviri + C • Şimdi bunu anlayalım"** çalışma PDF'i.

## Akış

```mermaid
flowchart TD
    A["Kitap PDF (Drive)"] --> B["kitap_paketle.py (Colab)"]
    B --> C["Bölüm klasörü: md + şekiller + parçalar + TALIMAT.md"]
    C --> D["LLM ajanı (Codex vb.) TALIMAT.md'yi uygular"]
    D --> E["calisma_pdf.py: kontrol + çalışma PDF'i"]
    C -.-> F["sekil_cikar.py: şekil denetimi / çevrilmiş bölümleri güncelleme"]
    F -.-> D
    S["Ders slaytı (PPTX/PDF)"] --> G["slayt_paketle.py"]
    G --> D
```

Yan dal: `sekil_cikar.py` (şekil denetimi / çevrilmiş bölümleri güncelleme). Ayrı dal: `slayt_paketle.py`.

## Neden böyle

- **Doğruluk:** Metin PDF'ten programla çıkarılır; LLM yalnızca çevirir ve anlatır.
- **Şekiller:** İki bağımsız yöntemle kırpılır (PDF nesneleri + piksel denetimi).
- **Denetim:** Her adım otomatik kontrol edilir.
- **Token verimliliği:** LLM'e PDF değil, temiz metin ve kırpılmış şekiller gider.

## Dosyalar

| Dosya | Ne işe yarar | Nerede çalışır |
|---|---|---|
| `src/kitap_paketle.py` (v3.4) | Kitabı bölümlere ayırır, şekilleri kırpar, LLM parçalarını ve `TALIMAT.md`'yi üretir | Colab / Yerel |
| `src/calisma_pdf.py` | LLM cevaplarını denetler, Türkçe çalışma PDF'ini üretir | Yerel |
| `src/calisma_pdf_colab.py` (v1.2) | `calisma_pdf` işini Colab'de yapar | Colab |
| `src/sekil_cikar_govde.py` | `sekil_cikar.py`'nin gövdesi (derlemede gömülü kopyalar buradan üretilir) | — |
| `src/sekil_cikar.py` (v1.4) | Yalnız şekilleri çıkarır, görsel kontrol PDF'i üretir, çevrilmiş bölümleri günceller | Yerel / Colab |
| `src/slayt_paketle.py` (v1.9) | Ders slaytlarını (PPTX/PDF) LLM paketine dönüştürür | Colab |
| `tools/derle.py` | Gömülü kopyaları kaynaktan üretir | Yerel |
| `tests/` | Sentetik test kitabı ve kenar durumu testleri | Yerel |
| `audit/` | Geliştirmede kullanılan denetim betikleri | Yerel |
| `CHANGELOG.md` | Sürüm geçmişi (İngilizce) | — |
| `docs/USAGE.md` | Adım adım kullanım kılavuzu (İngilizce) | — |

## Doğrulama

Kitabın tamamında (865 sayfa, 32 bölüm + sözlük, 432 şekil) yapılan v3.4 doğrulaması için [`CHANGELOG.md`](CHANGELOG.md) içindeki "v3.4 doğrulaması" bölümüne bakın.

## Geliştirme

- Kaynak dosyayı değiştirince `python3 tools/derle.py` çalıştırın (gömülü kopyalar güncellenir).
- Her dosyanın kendi sürüm numarası vardır.
- Çıktı değişirse `SURUM` artırılır; böylece Colab bölümleri yeniden işler.
- Eski sürümlere tag ile dönülebilir: `git checkout kitap-v3.2`

## Sınırlar

- Numarasız şekiller bulunamaz.
- Taranmış (metin katmanı olmayan) PDF'ler desteklenmez.
- Farklı bölüm adlandırması kullanan kitaplarda bölüm sınırları elle gözden geçirilmelidir.
- Prompt ve terim listesi İngilizce→Türkçe ve yazılım mühendisliği odaklıdır.

## Türkçe belgeler

[Türkçe belgeler](docs/tr/): [Sürüm geçmişi](docs/tr/SURUMLER.md), [Kullanım kılavuzu](docs/tr/KULLANIM.md).
