import os, sys
import onnxruntime as ort
threads = int(os.environ["ORT_THREADS"])
real = ort.InferenceSession
def limited(path, sess_options=None, **kw):
    o = sess_options or ort.SessionOptions()
    o.intra_op_num_threads = threads
    o.inter_op_num_threads = 1
    o.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return real(path, sess_options=o, **kw)
ort.InferenceSession = limited
import homr.music_xml_generator as g
d = g.mxl.XMLDuration
g.mxl.XMLDuration = lambda value_: d(value_=max(1, value_))
from homr.main import main
sys.exit(main())
