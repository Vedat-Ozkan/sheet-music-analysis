import sys,pypdfium2 as pdfium
src,dst,dpi=sys.argv[1],sys.argv[2],int(sys.argv[3])
pdf=pdfium.PdfDocument(src)
ims=[pdf[i].render(scale=dpi/72).to_pil().convert("L") for i in range(len(pdf))]
ims[0].save(dst,"PDF",resolution=dpi,save_all=True,append_images=ims[1:])
