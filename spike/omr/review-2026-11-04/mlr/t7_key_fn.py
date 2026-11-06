import sys, collections, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
ORDER_SHARP = "FCGDAEB"
ORDER_FLAT = "BEADGCF"
def key_alter(fifths, step):
    if fifths > 0:
        return 1 if step in ORDER_SHARP[:fifths] else 0
    if fifths < 0:
        return -1 if step in ORDER_FLAT[:-fifths] else 0
    return 0
def scan(data):
    root = root_of(data)
    red = collections.Counter(); tot_nat = 0
    keys_seen = collections.Counter(); perpart = []
    for pi, part in enumerate(root.iter("part")):
        fifths = 0
        prev_bar_altered = set()
        pk = []
        for m in part.iter("measure"):
            mem = {}
            altered = set()
            for ch in m:
                if ch.tag == "attributes":
                    for k in ch.findall("key"):
                        f = k.findtext("fifths")
                        if f is not None:
                            fifths = int(f)
                            pk.append(fifths)
                elif ch.tag == "note":
                    p = ch.find("pitch")
                    if p is None:
                        continue
                    step, oc = p.findtext("step"), p.findtext("octave")
                    alter = int(round(float(p.findtext("alter") or 0)))
                    acc = ch.findtext("accidental")
                    if acc == "natural":
                        tot_nat += 1
                        if key_alter(fifths, step) == 0 and (step, oc) not in mem and step not in prev_bar_altered and not any(s == step for s, _ in mem):
                            red[(fifths, step)] += 1
                    if acc is not None or alter != key_alter(fifths, step):
                        mem[(step, oc)] = alter
                        if alter != key_alter(fifths, step):
                            altered.add(step)
            prev_bar_altered = altered
        perpart.append(pk)
    return red, tot_nat, perpart
