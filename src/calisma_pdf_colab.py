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
eNrlPF1zG0dy7/wVo9VVYZcCl1/6hAWxKIrSsUhTKpE+lwJCuAEwIPew2MXtBymQYsoPF1/u7S52Va4SJ7pKJfFr9OJUqvwU0n9E
vyA/Id09M/sNkLJTeTFKNndnZ7p7unv6a2b3JluYX2A9v+94hw0WR4OF+9gyZxjGXI+7TjjinXF/YI8n7MMXX7OdnU9ZTxzzscuD
y/fe5Xs29L0o8F0m+iJgx4LtX3wfDC++FeziW+5evv/h3YizF0+e1hzPYfBIRE5gz5nd2HH7nd4RH0cimAfoddY7ur1IzXT3W05/
AjFwPCGx/zvrwuihKwKA5bEJ/hUsEkPGA37xrW3NzW1/trOzvrv16RyD33gSHfneKitMw3g4dCI+ftR57LvxCKAtLt3u7PmD6IQH
ojMO/J4IQxEajH5m9+I79+L7ERu6PLz4Lrj4HtHI675gYx70+MLSsj3qM3PIJx4fslsMgIzGkYXs0B0WiGvUTfOwe/neAi45gwin
xHx3hAyzNXQ24ePL9+Hl+wZ7qIh4tEjggPeLzJSQd3cR5i2m7xI8hD0dGIqh4+JkbfYMgIcCb1jfDyd8jvdBlJwdQrtg3diNvTj4
RIo54kOHTUC8wGlgVxBy+BPGnj03d/H7re39rQoGefCPOTAxT1gkiEr+dpRYbBAL9Pnw5R+zGtP3hwCTo4KZR0CoYm3IJwMOkgdd
oss+r6MeMGfkOtfBBaxSuLpO4Iof3jlDNgKl8maMVQqeGatVPuBjP4hBHZ7v7r98vrOz+VLrgMuB4uCHd5fvXf7Du+jyfTDin+Di
gWXAhsLrO6DLE5we8f37Y5iROxKncg4LbJugEPNx9nLaJiwjFtps19KyYV2ADiwbglBgDQzZMQ/Y6PL9mgLzSz22z5mxDkvoX9g+
HwGfxbETOAZqiLFBzT/8szNCokD0jHsun6AkRkYR4DpT0lZSjk9jz40v38U5AU20Ll186w/ZEJSYExBmAj9D55RdfHcqQOlHoG3C
dYLICZ38zDXVav4/vEPtTWZtQh9QDNXHSoiEWVC/Lr9853IvotXDNmqwTkdOMgWYHTwZMXPDarD12hRi6wxtjYhYHzUS7RxyxGPH
cXAYa4x1ZmyC9bn4FkTg8hFvGGiOAngo+s7Ehz5xfU7aEWPP9wKcj5YH2jNC3BOX75xTgx06XXzqRqhfMevHkziIwzgVwdwzEYih
6zTY2BmvMscLI+6CFgrQwsjlXWh2Xf+ETLczwkZ2FI1cfe2H+ioQ+iqchHNzz/9qc7+zubf1bIs12ZJ95w5LfjezEgfFdR2QGcxA
cnYxvyyLj1GZPAYTAr71+QT4Gk/Qa8xtdLa39tYzKG9nEG5UoFm/NmyQah2FCldayZwf3uHy6DqgaRas1RcvPwOkgbB7YKQdV5iB
Ya45VqjkY641aDpv1bzfDgnjyDo4mW+9tg+89tlSfXlp6XzNmGPlHwJrZOT6Vl0PQ8d7K1zBSI14jw/VHVxegn6dvuVSMV16RjfJ
I8frQeeJBqkVjsBYhjW3ub+1vblfnNVroATUs/V6voE03146b7y9+D0tfeb5Udx4+3wYo629+P4U7E9j7a1afPRwzfoFQF7vPF7f
29naLsG+efMgnF8/6Broo+1PLRDqrJ4bmZ5766+erndAA14C3cXuD28sLDAydAc2Mw/6tyyYBfvv/2TktNNWa40tLDwCCp89f7m3
uVMEc+OgZbZeH7Tb89ZB+8CEa6t9yzpAZs3N9cVAKVQHRG1GVoMkGQEQCc0O465pAMGRlTwB8NgqKbTn1wD729c3b9nzv3j7+uDt
Wmuh8Za1b8HVL2Acja2zgcsPw6acNSmHiOLAY67wTGiEyKYPCxhAHpzcImRI3E324esvfib/YLLb0pf+vKYtNZAWW4eMDXhvRwZ0
HYjcpDqCGc+GeB++/Dt2BrGSHNCASAMXhLyryyDGOoeokEJP8mPgNBhZFAg/LBu9AoKlnqDPGpsdjl0nMo1ms8m211/trm+zTzf3
L/9jl0ELaOWy1VpYbtNQMJFxr86cEAIkjFkBytl5nUFoFZm5RU2q7UBkb0q6pPYPwCE6QCp4Lia8eCQCHgkzgaamrRAB7ORJy4EA
d7ltg78LItNizoBRC3tISymFwIQbCmqTeLMA417L8SJzZB8Gfjw2ly2rDTiS+xVLMbE1siE+M60GjGnnli0BUeaDQpGM7Og+FdyG
DO9Z7SarJUGaTJn63GNd18c7Tr5VQKxN0TKEKTUd4tXYoYAwDeJoF90rRpA6TtEhFviHgPBBgDxCTGrsbQwtakw1bkuzabO7dynQ
w7BjUUVZjcKQLpIxcqySrhFjzhMVIkaQ8Om2y0PXwflAE+mCsm2kAOgADkKwkqBKxCTlBWapRAKwpBLJkytUIoWQqoQUUQIQZQAQ
qRVkrgCR1FOkyu4LWCtHMBXll8CfkQ+CKSGUVuP20lI7hQy0hI1cbEAMAzARqA6P3chETQxTTUSHYZVHtArd2uxWkzBO00pguDPS
CYsJ0aEz4uCGtJqm+rmNUUgPFJRGkNRESBpoQFZCSRjEshDDCgbhk1xeHkVSOq2R+syGsetiGuOOcIyMwjW6BjvzfK08qe4EkDKQ
rrQkoxWZ0KCuZlskq7XUTnRHeOA2A9SenD8110bW6wVm2rfWpDLDlYUaqDBk9Aqh4JSdsAQl4QSD8OETjB8QQlYp8dcXofDKAeXD
GwcnlgEqCe0i7PGxMCUa0LTAGZsodHi0lRc75LLSrrY8ogym10O6NEttWFOjUOo7Ida62bPaOUDwXMJqlIJULQGbj8do6UzZEdgK
AYtBCtFgtbM8tee1gqjrkKJfvqMEpXYWBUpmNWbWUEDQ3TwT3rnkfmWgPPV3i2EAZf/GdzxzYCgLdQYahJPy2I0mM0DnDbmw5SWx
ismaEPoBq2C35YR15CeXR0dEKllXhildHY+dAN3jxbdcGmYJQa8SiJe/8yBmDuBfg7XMxE7WM5mg1bana/wwBJRoW0ohgGyw6lP8
S6L3nl9XAYB2/Tj7Yaj1I5W6ymKbLMNK/xwVE5irYFArXZ1bxGXZKhls5Ayb52N2gMh6JRtXUCukcWCcSQLOG2nNIlb54qvn24aV
1/8eyMbxYpE0opvphS3Pb+epiJjOTNIV8JH01EoFkVom1534wyxxCunGT0Y6q9wyAz8HPpRnnD7ukBaA3nR0fGdQGpKdAM/T2htB
r9KEQIll/JMXDE/g9lqqA0h0lPW/AC/1tQVz1MsM7+kAq50dZeSNhFoZsDZ5B910Jl2T+l7PNinqrKIJ1FDYoya7vQSc7hO4hyxT
8phPel3DVBbFqRRHlY3MM4B+rmsVSXXkTCNAc/jF17ow4eUqE8WVgKyRsyqT1SuypFc1fy11Of3lFTn/Hs0/V4GZxz6NSht9JQM2
kqn3clNfZ8QLOeHp9ZjirKXoXdKU1pBM3bDklw/mD+bJteOFkei8pReprIbY4OdBoYeJv21XcQf7E8IfO38sLs6qFMI6Zib3OCPX
gBnASHdQBX+rigmp+CGqiCEMNObn86XG+XnDYo/Y8o8kvJaHVpMzOcsjrZWR1iyU8unH+PSBAaGPC5HDKWUz4Fn5YcAHEZ/JgaE/
DmJQAyrYJeZphqLTgB/JjYqy6/DiuzG4+AZo8DdnBFsF4ktWq3EPQhxImT588U9Z0lFdO3XaLgGdVaUkrbeS8Dx9vA8T9EN7zKMj
G3IW4fERxIm+W7IF0FP73R9hplT9HIuQQ5nc8f55kemwdBOlk6YyxZlvxatptum6tKzXsAauSGFmWrInRawzn0qTqeqFtNvoMblp
0i/rThJmQY6Uz4OSKC9UARQ/ddGfwohI9E1Iy0x4xBYYXg1DBQ+YQR2zKWhharu+B5QaQ7VZQyQBfSq8yaX9DWbMCGyT+JUwTg9f
f2a1QWDRz7AuOAC1xZi/A3rVF5EO5geBP0r3enDXFA0GUxs5cAsLMnB64YzOdhQh8FAP2t9/Crdz0hLxicpREn03jcW9CaQ8o8Ud
pxvwYLKI3cPFvXg8xs07D7LpxV+JoA/uDUGjdl9/BHvsu305LDUiHzN+C5P5HkGw6lmi4zBYDI94IBZptotREItoMhaLffEbfhwv
PoE/v4r3uBcmVF9/yEI12R8B4HnXdX4biyzhqhASTBrX9ak3GYQ3Y9ePXKfLJPDaJKbNUsiBwZObGxhjsT4/clyLRRwjkyDNBqQC
pDCSJ8OMRyJLlfaxD0XU6fOId/CpiVUrmixykCaTpiNSmxJDCfZ/eF7me7E5w9vysxzbJCrxpifGEO/RH8fPeKMxD8NMshyAq6jL
OK/OxKFDMaUispFLkcBR69mLN5Dvh+Ybi4C8wSFmBSir4NOxM+8nUYBpGk9hOnIgsAxuHxsKgLzdMqoB0TySZW0H0AeWRoArwpQr
11R4Co58yqCnfOS4kyw5TbruAtObkiqHllRT0oTtW7rhcaE+ub3+cn17f/PlzubLFkDBUjp6zwxqUBaiEZ5a9oD3hN2D9bHvP3Mn
46M8sJtsHdbzhJ9iQdIZUx1S+9Kk/BgwE8KFOvvwh3+F/33zFZasLVWfmYi+GGYAlAQiO0DPFm8ttaWMMjrQWm602+CfW9exP+uB
w132mef0/L4oWoKP/BkFRGXY7UZVrFvQUZqeReGZnOmNphJxdTyMlmYqzVfonPH0lVGXaCqi9mr9eDVbQV5dqSHZXzcQfFj5dLo9
KM1R24dk255iLRl2cQf8qtSDzTdYiE6OtA3xkE1ENUYH9yIwiRUeniVCX5pRQHmKCsLWPh5J0B5rwsEeK2vN0KhZNu1HZ5gld1XW
9za2tjrQvLcld9TPDNB9A4LIhUdobT98+Ue8ebggb76WN/LR76lfU93Ifk15I/upR1/+Ce9ey+uv8Pq4UpENWHAZIH/4N7x5pG7+
gjc31M3f4s1f0/U3BPCWvP46c/33eP1GXv85ub5QzeeqRNtJtvScTj8+FW6UbNIbhlE2FoeQujiJychJqWgaJq5QciAmZ/Yz8KgF
GAOSq9pYg+Q9lKcXIwH2ELc/4ihmH/78R53Op/uqKOBmVu9Rwcn6zWVqDdAr1UoV4MsIrOcMIyetEaOJ6h2hjYpyHsoP+mbvyGIP
2dKblaWlJWhI2ihD4ywZaRx4RqHmh0i0W+5lFhklfxk45XngqjeLPioHb2A8xHiAYRLbrD19VXt01js6f0gR0SMjiysUM8DklZ+w
945ASdaMfF5kqFSKButjHSGPnKDj9JzcqQ48BqV3YSKwamMXrI1pfPjiT6h9Cxpw7phHscoUGA+7jw6WHy52H005GIKbPq2Dk/k2
DDHXbhyEFo2nvaBQtZ1YEpRDoJxZoKBvpwym8xFQfk0Dfy37kmjQyjZrG34cOCKo0WgpnQSAYm7lClQ8xg2PGB6aIwg/gPtOWGeH
Ph4p7eAZUEhX62qjNpu6vNja0WHn1ogfCsZDbKPrqpwFA1vVv+e7AH5KJzuMYE0nOc0LWV0aH+1hc2Uy5HKIzONkhEkk1Nm2EON9
H9QNgug6wDkUj9HT1FOQdbYHY1zxxO/tixHCgWF7Y+BpcL0QYJ93XRhCf4g+vaNTyPioFXTUORZBBDzmo0O/C74Y+BygjZAMsX8p
3mzglWncXH6wunr7voE7R6VnS0v3Nu/fq352Z+Xuyr1ltThD1J6zZCbG0TKY5TxDTWysE8W7uMxl3Ii3e86paC7fqTNXcDxM3lxZ
AqUSbyJC1UxnEyLD1gdgoJsPsIovxp870dEu9GzuQ9aUyeUAV6+Sgt7/IwkrVRSszCJgJSVg+W6WgIwciYLHAqy8aN7NEXTvKoJW
qwhanUXQkp3hyfLtLEmgTznsd6/APq5APs7jzqPOIrZXrhTHvSwyCJ/6ogKhbP+/Q0rcGURbEEp4Eclv4ARhtON4QrUtPMjShblb
5FQQph7kKNvKkvYgJ4lVvJsui3sFsvIkRJX4oxnI72dQL89CfD+nb3EvqBKCbJ8qhPu5mVbKIIulOw1NtwLP42siUubu5MiJtBJD
hEkBB/ipkD0W7qEwSzY9E+NQMNpxPCfqdExwcIM6m+fw3/ywuPEbj0VgWnbSWXfL9wII9mGMp3mTw0xzOWQcBfDU9U/QRSiMgwIu
POsU0ulvAGQOMg5KpoAD6RJtjMNYsynteLlQn6NlgHHWC5c73j6wzyxnXxBYHkVUIBwY3TMHoj3r3KgG2uPesd31/eGIB0P0o6Ya
bM3oD0v6eRzB+hGbHqSnZoa8VuMBnk1RQFDYx8JtwiLvuX4o+s2nHAJKq4KPhBsBFaNWSkYV5vwTO+TH4JrxFFqe2pM66+hhY4Ab
gu4Vh4poLwr8oZDOtexsNx48WX/ytHTmwcZZm7dhQquwRE/YApPXVhm+rqjU2b2qp47rSlywoovP+wE/AfJglRCqFfQ6OR7faVcN
eekcHkVqnCaNxkaBmTCjNKNAhBG4Ns1IevpscxcYeOfBHXvlPgC6v0StRw4EPRAT0d5UR4aRlAXVdSakDktiY5fSoq7aEZZHjgLj
9UE4v7Cw8GL92Sb8gRs86YWxaeb4NS6art4KTjOsriOP8BXOH0qMVi7x6jp5JZKE66QlCRezBycoGZGkI0iNXhKOQg8zSoYm2Pc6
0ijIa3V+oMmW6sXjHGDTIJF11HFHjaholFBh1aOW09b45yr2wEPMGkN5nCM8Ae9v0jl3o6Im6eAO23L5UELx6A4dNk6P1Mvt+LCE
fVTGgKXTQhW6mF+UNk3Tc7zVu+nFipnvWtXlIVjoR4Bdpya2D/Kl7nZpyeuf7/YEimkEhKKWLyKQVcjNFxnkDMv2EhJwArLCNjrt
8qC6vJXXqWxCYraIGiQETITTj46aJ2xeYgaCBa7S5pFusXRaYoKfX7U+vj6ZeBQzTagzJ6dxK5POMelzxHRgzECr0KIgpG21K8RQ
TvyTJ5nVr6f/cSKuWpJ6DgOjpd55zNblGuwsWxfIQD9v56Zi/aQlgKeBc+vqbdWikmzWJwyTKlBOMauXPLn8ilV+NU5iGUZX6sjp
sR5KpvFYnjutgot/EaQ+qAuX7UrouuiFx3aEPYhdV1qBwGisLZyt1M8ba8Dp4wzChB4YemxNL+Dm+KUlrgdXa8cUoeFRoxF/Y9JL
OZKSIJm6xmBdLbCA9g+MNqxB0wP/JuFNA1jml3yVEs1IC8mBSADNyV0w/Ql1rWF7KoEKkzwtxT0wFV6FUA6F56B/QSxoqeZZDEYq
jEemQi+hxAhFtZSBHAsqQrRaVVbi2JJLR8XtKEfsDT5MnfOT7e2MzIP2VDHTZMEzBnkHnZ96eXgE0bMPJFKhxUR6qfbxOdrNsKmZ
gAewx4JHL/2TsAmG8mjddQ69prGz+XTfsKqByiAPM5O0iGO2Kuk3jcfrG9vPXj7/bPcJ1k5Bkku447ewLC+SagBtA/5qfWfr2W6x
38Iy7rLuP39hTDHiJlH7Yv3Jk63dZ5Wj7xL4l1vPfnlVtykIAPusgXcI/uPn+/vPP72i3xQEL59/nnJqTw1ezg1ulYPpp0tP7z7N
VrUozWtP59PW7ubjzZ3nn1dSt2TfriqPPbm7uboJSCrdmXI3kC+h8WmRfmQd732rbV3bR4B91Lbx9c2z1frd8wPcWA8rbOA0N5cu
wtB2lZW+aViZFw5wYR6tllwaFf/zTurmTVYZ++UIzbzZGSo/lESwjfR9XjyUcAo+18u9uP9J/pgU7r6ol6fpLYNghodHQ97KRNz1
ynglpUXPfLmHgck0T5VG3NPdzjVYn0BRWMfGDN2ZBai12mhryleuJbNKkU1NKsLWSqNdLx68vi5xKylxy9XEZTW6tTAP4WL7o1Xa
wCATT85Vo5aFwCuxH/RvtWyr/VMW1NUI87J4ZPzEhfsIhGnpKJSqimWsVdF0iRIVohtygVKud4Wi57XkJ3CrrPqZGKyLxTdAIItw
ahtJV1aapqwTgBG9vWzff2DJUuinPDh0vCbWIALMeDL3kT9Wd6t38OxKFPkj/fhBlU+IIAUXTb0yeBwd+UHTqPp6TfotEhUVEOk2
favGlNzI7Z1lk5mf36FN3J3nQ2Tdz/DsJn1nBpaBepdblSuUKciXNXg3pGN0uZ52oJb/oq4SdvEjRfpxZnjfCZLD4tn6Ru4UOVV/
9SeD1Btz0C6/jpTFWyy35LDWMzByhxn0ECfsT5ly9XmaxxVfDMKsgpnJe9AaYS3tlJz4to0Ma66gvMSW3HPF43xx6Spe6C8pKSr0
B3+C9ET5gPKWAeYsAAk1oswfFUplc2L5tj84qwN71MctDivH7QTRLNYWv0wlvx1An3nCz6ZM/KHmHn28qJ58zIssqMtHHfmuIwRY
AyP5OoP60hG9zHNWzVLrnAqUVLaFcDqpsA6JDRW09wb4DtMgPY0hJ20kH7DKpGCJN6JiXE46Oa7WASC4CuHJ75k1DfqeGYTAECf2
zdLbfIWa4Cy4vUHx6AuxJD36ssA+/OPXbH7+bDg4n59XbzvmGI/vSA3UG1HdWL9gioeLBDt0gpHoO4WsMyeRUvGi/K4kobwGk3rX
YlLmvdWpr8zOTSOVSlQKQP7NeNV4FTP/4S8ZZp7lwJ1LIAVmEQjKDAaG/NLTGVevVnTq8rSnhtCecRSpTMk3X2UoidBu6ddy62x9
cUO/s0mnzY6Fer8FS1gR5DyjDJV6qSXnr0jRdXY2l37lYJbslJWAjsWFUi5yQ6f8FxSStzBJRaBhuhqUNguK1Cfgcl/Z6KRv819v
FvmFLl/cOeIRvfXMim/yaLI7yacNppFfZ2f0angjnTYsvYO52bsCGdDqwxGt3HvHefKupcLJRBM9zgP5CG1OTGWNXpwCmLU6k9f6
G3z4MYiaVVD7PML2TBNTQeB1F0uyVnJTBm90CqQN2aL+NNoiTRgNixi6+Ck8NfU8+BLo3/0XK6u+tKsax6LEsKjhp29TEya0sJZC
NsI374wD78DL7BzCnT5TqJQ90zlzNq9R3HC0sJaNzqsCIG5FWpnvpFS98Sc9aOoKOwiLKVIxjZMLVgY8t5iR+Z4h9jwxKhYCnq8b
ZL5zYZ8ETiRM+lgkHgxVTKdXApv5M31lPPDYmHrIj15WVQzLrRpoJ/hTpKoXiT5fq7Zm8AjvYfKJSlg0qOVSLAQN1Hu631meyrL0
M44fyzIjUQsi38oxcBzgR1qKXbLPBvDwrPbhm79he0QlxmA1HYLk6CfeDWrIk7PsA2UiKHKYxPQSMX0aUYYQ9H4hldb6+L0giAXt
2nnqE7RkMi/HKLL+591Xv2NnxKHznKRz2WyWEMhmHTwQg0rb6VB20emMuON1OuqECTwmXz0JbUi+jy18E2FlRsBa21ZfFRk1rv+9
1oelT44+MmqS6CQB0xS0ltvW3P8CF/CVGA==
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
