import sys
from itertools import count
from importlib.resources import files
from multiprocessing.connection import Connection

import verovio


def serve(requests: Connection, replies: Connection) -> None:
    toolkits: dict[int, verovio.toolkit] = {}
    handles = count(1)
    while True:
        try:
            handle, method, args = requests.recv()
        except EOFError:
            return
        try:
            if method == "new":
                handle = next(handles)
                toolkits[handle] = verovio.toolkit(False)
                toolkits[handle].setResourcePath(str(files("verovio") / "data"))
                replies.send(("ok", handle))
            elif method == "drop":
                for dropped in args:
                    toolkits.pop(dropped, None)
                replies.send(("ok", None))
            else:
                replies.send(("ok", getattr(toolkits[handle], method)(*args)))
        except Exception as error:
            replies.send(("error", f"{type(error).__name__}: {error}"))


if __name__ == "__main__":
    serve(Connection(int(sys.argv[1]), writable=False), Connection(int(sys.argv[2]), readable=False))
