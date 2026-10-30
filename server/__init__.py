import sys
import time
from pathlib import Path

from engine import read_ahead

IMPORTS_BEGUN = time.monotonic()
SERVER_FILES = Path(__file__).with_name("server-files.txt")

if sys.argv[1:2] == ["--list-files"]:
    read_ahead.record()
else:
    read_ahead.start(SERVER_FILES)
