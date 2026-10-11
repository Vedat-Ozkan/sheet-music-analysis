"""Cut page ranges (1-based, inclusive) from a downloaded PDF: extract_pages.py in.pdf first last out.pdf"""
import sys, pikepdf
src = pikepdf.open(sys.argv[1]); dst = pikepdf.new() if False else pikepdf.Pdf.new()
for i in range(int(sys.argv[2]) - 1, int(sys.argv[3])): dst.pages.append(src.pages[i])
dst.save(sys.argv[4])
