import contextlib
import io
import json
import re
import sys
import time

import homr.main
import onnxruntime
from homr.main import ProcessingConfig, process_image
from homr.resize import calc_target_image_size
from homr.music_xml_generator import XmlGeneratorArguments

threads, images = int(sys.argv[1]), sys.argv[2:]
open_model = onnxruntime.InferenceSession


def open_without_busy_waiting(*args, **kwargs):
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return open_model(*args, sess_options=options, **kwargs)


crop = homr.main.autocrop_with_offset
cropped_widths = []


def crop_and_keep_width(image):
    cropped, offset = crop(image)
    cropped_widths.append(cropped.shape[1])
    return cropped, offset


onnxruntime.InferenceSession = open_without_busy_waiting
homr.main.autocrop_with_offset = crop_and_keep_width
onnxruntime.set_default_logger_severity(3)
config = ProcessingConfig(enable_debug=False, enable_cache=False, write_staff_positions=False, read_staff_positions=False,
                          selected_staff=-1, transformer_use_gpu=False, segnet_use_gpu=False, coreml_encoder=False,
                          title_detection=False)
for image in images:
    started = time.monotonic()
    printed = io.StringIO()
    try:
        with contextlib.redirect_stderr(printed):
            process_image(image, config, XmlGeneratorArguments())
        record = {"outcome": "done"}
    except Exception as error:
        record = {"outcome": "failed", "problem": str(error)[-300:]}
    note_head = re.search(r"Average note head height: ([\d.]+)", printed.getvalue())
    if note_head:
        width = cropped_widths[-1]
        record["note_head"] = float(note_head.group(1)) * width / calc_target_image_size(width, 1)[0]
    print(json.dumps({"image": image, **record, "seconds": round(time.monotonic() - started, 1)}), flush=True)
