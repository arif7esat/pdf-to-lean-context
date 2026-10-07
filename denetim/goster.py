# Geliştirme sırasında kullanılan denetim betiği. Kitap PDF yolu: KITAP_PDF ortam değişkeni (varsayılan: çalışılan klasördeki "Software engineering.pdf").
import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kaynak'); sys.path.insert(0, _K)
import sys;  import pymupdf, kitap_paketle as k
d=pymupdf.open(os.environ.get('KITAP_PDF','Software engineering.pdf')); g=k.govde_fontu(d,range(40,120))
from PIL import Image
ims=[]
for p in map(int, sys.argv[2:]):
    s=d[p-1]; bul=k.sayfa_sekilleri(s,g)
    sh=s.get_pixmap(dpi=int(sys.argv[1]) if False else 70)
    pg=pymupdf.open(); pp=pg.new_page(width=s.rect.width,height=s.rect.height); pp.show_pdf_page(pp.rect,d,p-1)
    for x in bul:
        if x.get('kutu'): pp.draw_rect(x['kutu'],color=(1,0,0),width=1.5)
        pp.draw_rect(x['alt_yazi_kutu'],color=(0,0,1),width=1)
        print(p, x['no'], x.get('kutu'), 'uyarı' if x.get('kenar_uyari') else '', 'YOK' if x.get('bulunamadi') else '')
    px=pp.get_pixmap(dpi=int(sys.argv[1])); ims.append(Image.frombytes('RGB',(px.width,px.height),px.samples))
W=sum(i.width for i in ims); H=max(i.height for i in ims); c=Image.new('RGB',(W,H),'white'); x=0
for i in ims: c.paste(i,(x,0)); x+=i.width
c.save('goster.png')
