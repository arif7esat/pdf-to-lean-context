# Geliştirme sırasında kullanılan denetim betiği. Kitap PDF yolu: KITAP_PDF ortam değişkeni (varsayılan: çalışılan klasördeki "Software engineering.pdf").
import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kaynak'); sys.path.insert(0, _K)
import sys, re, glob, os, collections
import pymupdf, kitap_paketle as k
d=pymupdf.open(os.environ.get('KITAP_PDF','Software engineering.pdf')); g=k.govde_fontu(d,range(d.page_count))
b,soz=k.icindekilerden(d); kay=k.sayfa_kaymasi(d)
sorun=collections.Counter(); ornek=collections.defaultdict(list)
tablo_icerik=collections.defaultdict(list)
def kel(t): return re.findall(r"[A-Za-z]{3,}", t.lower())
for no,bas_,bas,bit in b:
  for i in range(bas,bit+1):
    s=d[i]; bul=k.sayfa_sekilleri(s,g)
    kutular=[x['kutu'] for x in bul if x.get('kutu')]
    # (5) aynı sayfadaki iki kırpma çakışıyor mu
    for x in range(len(kutular)):
      for y in range(x+1,len(kutular)):
        ov=(kutular[x]&kutular[y]).get_area()
        if ov>0.05*min(kutular[x].get_area(),kutular[y].get_area()): sorun['çakışan kırpma']+=1; ornek['çakışan kırpma'].append(i+1)
    for x in bul:
      if not x.get('kutu'): continue
      tm=k.sekil_tablosu(s,x['kutu'])
      if tm:
        # (1) tablo kelimeleri kutu içinde mi
        ic=set(kel(s.get_text('text',clip=x['kutu']+(-3,-3,3,3)))); tk=set(kel(tm))
        if tk-ic: sorun['tablo dışarıdan kelime']+=1; ornek['tablo dışarıdan kelime'].append(x['no'])
        tablo_icerik[tm].append(x['no'])
for t,v in tablo_icerik.items():
  if len(v)>1: sorun['aynı tablo iki şekilde']+=1; ornek['aynı tablo iki şekilde'].append(v)
# (4) metin kapsaması: md'deki gövde kelimeleri vs PDF
for md in sorted(glob.glob('Software_engineering_Bolumler/*/*.md')):
  if os.path.basename(md)[:2]=='99': continue
  t=open(md).read()
  for blok in re.split(r'(?=<!-- PDF s\. )',t):
    m=re.match(r'<!-- PDF s\. (\d+)',blok)
    if not m: continue
    p=int(m.group(1))-1; s=d[p]
    govde=re.sub(r'<!--.*?-->|!\[[^\]]*\]\([^)]*\)','',blok,flags=re.S)
    govde=re.sub(r'(?m)^\|.*\|$','',govde)        # şekil tabloları
    mdk=collections.Counter(kel(govde))
    bul=k.sayfa_sekilleri(s,g); H=s.rect.height
    alan=pymupdf.Rect(0,H*0.07,s.rect.width,H*(1-0.042))
    pk=collections.Counter()
    for w in s.get_text('words',clip=alan):
      r=pymupdf.Rect(w[:4])
      if any(x.get('kutu') and r.intersects(x['kutu']) for x in bul) or any(r.intersects(x['alt_yazi_kutu']) for x in bul): continue
      pk.update(kel(w[4]))
    if not pk: continue
    kayip=sum((pk-mdk).values()); fazla=sum((mdk-pk).values()); top=sum(pk.values())
    if kayip>0.03*top+3: sorun['metinde eksik kelime']+=1; ornek['metinde eksik kelime'].append((p+1,kayip,top))
    if fazla>0.03*top+3: sorun['metinde fazla kelime']+=1; ornek['metinde fazla kelime'].append((p+1,fazla,top))
print(dict(sorun)); 
for kk,v in ornek.items(): print(kk, v[:12])
