from pathlib import Path
p = Path("app/src/main/java/org/audiveris/omr/score/PartwiseBuilder.java"); s = p.read_bytes().decode()
a = "            for (Staff traceStaff : measure.getPart().getStaves()) {"
assert a in s
s = s.replace(a, '            if (System.getenv("HEADTRACE") != null) for (Staff traceStaff : measure.getPart().getStaves()) {', 1)
p.write_bytes(s.encode())
