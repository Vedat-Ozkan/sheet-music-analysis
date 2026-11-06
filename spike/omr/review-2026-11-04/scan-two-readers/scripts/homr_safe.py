import sys
import homr.music_xml_generator as g
real = g.mxl.XMLDuration
g.mxl.XMLDuration = lambda value_: real(value_=max(1, value_))
from homr.main import main
sys.exit(main())
