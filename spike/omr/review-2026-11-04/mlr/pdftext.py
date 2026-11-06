import sys, pypdf
r = pypdf.PdfReader(sys.argv[1])
print("\n".join((p.extract_text() or "") for p in r.pages))
