# Sentetik test: ayrık aktörler, alt yazıyla ayrılmış üst üste şekiller, açık gri zemin, uzak resim, devam eden tablo.
import os, sys; _K = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'); sys.path.insert(0, _K)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import sys; pass
W,H=A4
c=canvas.Canvas("kenar.pdf",pagesize=A4)
def govde(y,n=5):
    c.setFont("Times-Roman",10)
    for i in range(n): c.drawString(130,y-i*13,"Body text of the chapter that explains the figure in detail, see Figure 9.1 and Figure 9.2.")
    return y-n*13-12
def aktor(x,yy,ad):
    c.circle(x,yy,6); c.line(x,yy-6,x,yy-26); c.line(x-10,yy-14,x+10,yy-14); c.line(x,yy-26,x-8,yy-40); c.line(x,yy-26,x+8,yy-40)
    c.setFont("Helvetica",8); c.drawCentredString(x,yy-52,ad)
def cap(y,no,t):
    c.setFont("Helvetica-Bold",8); c.drawString(46,y,f"Figure {no}"); c.setFont("Helvetica",8); c.drawString(46,y-10,t)
# Sayfa 1: iki şekil üst üste, aralarında yalnızca alt yazı ve 22pt boşluk
y=govde(H-80); t=y-10
cap(t-5,"9.1","Top figure")
aktor(150,t-20,"User"); c.line(200,t-30,290,t-30); c.ellipse(300,t-42,380,t-18); c.setFont("Helvetica",8); c.drawCentredString(340,t-54,"Login"); aktor(470,t-20,"Admin"); c.line(390,t-30,445,t-30)
t2=t-90
cap(t2-5,"9.2","Second figure right below")
c.setFillColorRGB(0.93,0.93,0.93); c.rect(140,t2-110,360,100,fill=1,stroke=0); c.setFillColorRGB(0,0,0)   # açık gri zemin paneli
c.rect(160,t2-60,80,30); c.rect(380,t2-60,80,30); c.line(240,t2-45,380,t2-45)
c.setFont("Helvetica",8); c.drawString(170,t2-48,"Client"); c.drawString(390,t2-48,"Server"); c.drawString(150,t2-100,"Note: light panel edge")
govde(t2-130)
c.showPage()
# Sayfa 2: resim alt yazıdan uzak (alt yazı altta, 30pt boşluk) + 'continued' tablo
y=govde(H-80)
from PIL import Image, ImageDraw
im=Image.new("RGB",(500,200),"white"); d=ImageDraw.Draw(im); d.rectangle((10,10,490,190),outline="black",width=4); d.text((200,90),"RASTER",fill="black"); im.save("r.png")
c.drawImage("r.png",150,y-160,300,120)
cap(y-195,"9.3","Raster figure caption below")
y=govde(y-230)
c.setLineWidth(0.5); c.line(130,y,520,y); c.setFont("Helvetica",8)
for i in range(4): c.drawString(140,y-14-i*13,f"Row {i}"); c.drawString(300,y-14-i*13,"value text in cell")
c.line(130,y-66,520,y-66); cap(y-80,"9.4","Table (continued)")
c.save()
import pymupdf, kitap_paketle as k
d=pymupdf.open("kenar.pdf"); g=k.govde_fontu(d,[0,1])
for i in range(2):
    for x in k.sayfa_sekilleri(d[i],g):
        print(i+1, x["no"], x.get("kutu"), "uyarı:", x.get("kenar_uyari"), "bulunamadı:", x.get("bulunamadi",False))
        if x.get("kutu"): k.kirp(d[i], x["kutu"], f"k_{x['no']}.png", engeller=x["engeller"])
