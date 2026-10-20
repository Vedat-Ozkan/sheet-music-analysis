import sys, pikepdf
src = pikepdf.open(sys.argv[1]); dst = pikepdf.new() if False else pikepdf.Pdf.new()
for i in range(int(sys.argv[2]) - 1, int(sys.argv[3])): dst.pages.append(src.pages[i])
dst.save(sys.argv[4])
