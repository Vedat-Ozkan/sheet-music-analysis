import glob, re, sys
import xml.etree.ElementTree as ET
from PIL import Image
book, bars, out = sys.argv[1], [int(b) for b in sys.argv[2].split(",")], sys.argv[3]
index = 0
for f in sorted(glob.glob(book + "/book/sheet#*/sheet#*.xml"), key=lambda p: int(re.search(r"sheet#(\d+)\.xml", p).group(1))):
    root = ET.parse(f).getroot()
    sheet = re.search(r"sheet#(\d+)\.xml", f).group(1)
    for system in root.iter("system"):
        ys = [int(float(p.get("y"))) for line in system.iter("line") for p in line.iter() if p.get("y")]
        top, bottom = (min(ys), max(ys)) if ys else (0, 3000)
        for stack in system.iter("stack"):
            index += 1
            if index in bars:
                img = Image.open(f"{book}/book/sheet#{sheet}/BINARY.png")
                img.crop((int(stack.get("left")) - 40, max(0, top - 150), int(stack.get("right")) + 40, min(img.size[1], bottom + 150))).save(f"{out}-bar{index}.png")
                print(index, "sheet", sheet, "x", stack.get("left"), stack.get("right"), "y", top, bottom)
