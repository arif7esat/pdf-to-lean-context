# Geliştirme sırasında kullanılan denetim betiği. Kitap PDF yolu: KITAP_PDF ortam değişkeni (varsayılan: çalışılan klasördeki "Software engineering.pdf").
import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kaynak'); sys.path.insert(0, _K)
import sys,re,glob,os,collections
import pymupdf, kitap_paketle as k
d=pymupdf.open(os.environ.get('KITAP_PDF','Software engineering.pdf')); g=k.govde_fontu(d,range(d.page_count))
def kel(t): return re.findall(r"[A-Za-z]{3,}", t.lower())
sec=sys.argv[1:]
T=[0,0,0]
for md in sorted(glob.glob('Software_engineering_Bolumler/*/[0-9][0-9]_*.md')):
  ad=os.path.basename(md)
  if ad[:2]=='99' or (sec and ad[:2] not in sec): continue
  t=open(md).read(); mdk=collections.Counter(); pk=collections.Counter(); sayfa_metinleri=[]
  for blok in re.split(r'(?=<!-- PDF s\. )',t):
    m=re.match(r'<!-- PDF s\. (\d+)',blok)
    if not m: continue
    p=int(m.group(1))-1; s=d[p]
    govde=re.sub(r'<!--.*?-->|!\[[^\]]*\]\([^)]*\)','',blok,flags=re.S); govde=re.sub(r'(?m)^\|.*\|$','',govde); govde=govde.replace('-',' ')
    mdk.update(kel(govde))
    bul=k.sayfa_sekilleri(s,g); H=s.rect.height; alan=pymupdf.Rect(0,H*0.07,s.rect.width,H*(1-0.042))
    ws=[w for w in s.get_text('words',clip=alan,sort=True) if not (any(x.get('kutu') and pymupdf.Rect(w[:4]).intersects(x['kutu']) for x in bul) or any(pymupdf.Rect(w[:4]).intersects(x['alt_yazi_kutu']) for x in bul))]
    metin=' '.join(w[4] for w in ws)
    sayfa_metinleri.append(metin)
  mdset=set(mdk)
  for metin in sayfa_metinleri:
    metin=re.sub(r"([A-Za-z]+)- ([a-z]+)", lambda m: (m.group(1)+m.group(2)) if (m.group(1)+m.group(2)).lower() in mdset else m.group(1)+' '+m.group(2), metin)
    pk.update(kel(metin.replace('-',' ')))
  n=sum(pk.values())
  if not n: print(ad,'sayfa işareti bulunamadı?'); continue
  ek=pk-mdk; fz=mdk-pk
  T[0]+=n; T[1]+=sum(ek.values()); T[2]+=sum(fz.values())
  print(f"{ad[:30]:30s} {n:6d}  eksik {sum(ek.values()):4d} ({100*sum(ek.values())/n:.2f}%)  fazla {sum(fz.values()):4d}  | eksik örn: {ek.most_common(6)} | fazla örn: {fz.most_common(4)}")
print('TOPLAM', T, f'{100*T[1]/max(1,T[0]):.2f}%')
