import sys,os
import onnxruntime as ort
real=ort.InferenceSession
n=int(os.environ.get("LEAN_THREADS","2"))
def limited(path,sess_options=None,**kw):
    o=sess_options or ort.SessionOptions()
    o.intra_op_num_threads=n;o.inter_op_num_threads=1
    o.enable_cpu_mem_arena=False;o.enable_mem_pattern=False
    o.add_session_config_entry("session.intra_op.allow_spinning","0")
    return real(path,sess_options=o,**kw)
ort.InferenceSession=limited
import homr.music_xml_generator as g
d=g.mxl.XMLDuration
g.mxl.XMLDuration=lambda value_:d(value_=max(1,value_))
from homr.main import main
sys.exit(main())
