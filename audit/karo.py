# Geliştirme sırasında kullanılan denetim betiği. Kitap PDF yolu: KITAP_PDF ortam değişkeni (varsayılan: çalışılan klasördeki "Software engineering.pdf").
import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'); sys.path.insert(0, _K)
import sys;  import pymupdf, kitap_paketle as k
from PIL import Image, ImageDraw
d=pymupdf.open('Software engineering.pdf'); g=k.govde_fontu(d,range(d.page_count))
istek=[x.split(':') for x in sys.argv[3:]]; dpi=int(sys.argv[2]); karolar=[]
for p,no in istek:
  s=d[int(p)-1]; a=[x for x in k.sayfa_sekilleri(s,g) if x['no']==no][0]; kk=a['kutu']
  clip=(kk+(-45,-45,45,45))&s.rect
  pg=pymupdf.open(); pp=pg.new_page(width=s.rect.width,height=s.rect.height); pp.show_pdf_page(pp.rect,d,int(p)-1)
  pp.draw_rect(kk,color=(1,0,0),width=1.2)
  px=pp.get_pixmap(dpi=dpi,clip=clip); im=Image.frombytes('RGB',(px.width,px.height),px.samples)
  ImageDraw.Draw(im).text((3,3),f'{no} s.{p}',fill=(255,0,0)); karolar.append(im)
sut=int(sys.argv[1]); W=max(i.width for i in karolar); satirlar=[karolar[i:i+sut] for i in range(0,len(karolar),sut)]
H=sum(max(i.height for i in r) for r in satirlar); c=Image.new('RGB',(W*sut,H),(80,80,80)); y=0
for r in satirlar:
  for j,i in enumerate(r): c.paste(i,(j*W,y))
  y+=max(i.height for i in r)
c.save('karo.png'); print(c.size)
