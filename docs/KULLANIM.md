# Kullanım kılavuzu

## Gerekli paketler

```
pip install pymupdf pymupdf4llm pillow numpy reportlab
```

## Adımlar

1. **Paketleme:** Colab'de `kitap_paketle.py`'yi çalıştırın ve istendiğinde kitabın bulunduğu Drive klasör linkini verin.
2. **İndirme:** Üretilen bölüm klasörünü bilgisayarınıza indirin.
3. **Çeviri:** LLM ajanına (Codex vb.) şunu söyleyin: "TALIMAT.md'deki görevi baştan sona uygula".
4. **Kontrol ve PDF:** Bölüm klasöründe `python3 calisma_pdf.py .` çalıştırın. ⚠ uyarısı varsa yalnız o sayfaları LLM'e düzelttirin ve komutu yeniden çalıştırın.
5. **Şekil sorunu:** Şekillerde sorun şüphesi varsa `sekil_cikar.py` çalıştırın; çevrilmiş bölümdeki şekilleri güncellemek için `--guncelle` kullanın.
