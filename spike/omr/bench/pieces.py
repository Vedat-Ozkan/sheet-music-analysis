M21 = "https://github.com/cuthbertLab/music21/tree/master/music21/corpus/"
M21_LIC = ("Work public domain. Encoding: music21 corpus; per-file licences are not uniform and some encodings may be "
           "non-commercial (https://github.com/cuthbertLab/music21/blob/master/music21/corpus/license.txt). NOT individually verified.")
LIED = "https://github.com/OpenScore/Lieder/tree/main/scores/"
SQ = "https://github.com/OpenScore/StringQuartets/tree/main/scores/"
CC0 = "CC0 1.0 (OpenScore)"

P = [
    ("bach-chorale-269", "chorale", ("truth", "bach-269.mxl"), M21 + "bach/bwv269.mxl", M21_LIC, None, ["ms", "vr"]),
    ("bach-prelude-846", "keyboard", ("m21", "bach/bwv846.mxl"), M21 + "bach/bwv846.mxl", M21_LIC, None, ["ms", "ly"]),
    ("mozart-k545-1", "keyboard", ("truth", "mozart-k545-1.mxl"),
     "https://github.com/MarkGotham/When-in-Rome/tree/master/Corpus/Piano_Sonatas/Mozart,_Wolfgang_Amadeus/K545/1/score.mxl",
     "Work public domain. Encoding: When-in-Rome corpus (licence NOT verified).", None, ["ms", "ly", "scan"]),
    ("chopin-prelude-4", "keyboard", ("truth", "chopin-prelude-4.mxl"),
     "https://raw.githubusercontent.com/musetrainer/library/master/scores/Prlude_No._4_in_E_Minor_Op._28_-_Frdric_Chopin.mxl",
     "Work public domain; file marked 'Public Domain' (musetrainer library).", None, ["ms", "vr", "scan"]),
    ("joplin-maple-leaf-rag", "keyboard", ("m21", "joplin/maple_leaf_rag.mxl"), M21 + "joplin/maple_leaf_rag.mxl", M21_LIC, None, ["ms", "ly"]),
    ("clara-schumann-polonaise-1", "keyboard", ("m21", "schumann_clara/polonaise_op1n1.mxl"), M21 + "schumann_clara/polonaise_op1n1.mxl", M21_LIC, None, ["ms", "vr"]),
    ("clara-schumann-polonaise-3", "keyboard", ("m21", "schumann_clara/polonaise_op1n3.mxl"), M21 + "schumann_clara/polonaise_op1n3.mxl", M21_LIC, None, ["ms", "ly", "scan"]),
    ("clara-schumann-polonaise-4", "keyboard", ("m21", "schumann_clara/polonaise_op1n4.mxl"), M21 + "schumann_clara/polonaise_op1n4.mxl", M21_LIC, None, ["ms", "vr"]),
    ("cpe-bach-h186", "keyboard", ("m21", "cpebach/h186.mxl"), M21 + "cpebach/h186.mxl", M21_LIC, None, ["ms", "ly", "scan"]),
    ("faisst-op18-2-lied-der-nacht", "song", ("lieder", "Faisst,_Clara_Mathilda/4_Lieder,_Op.18/2_Lied_der_Nacht"), LIED + "Faisst,_Clara_Mathilda/4_Lieder,_Op.18/2_Lied_der_Nacht/", CC0, None, ["ms", "vr", "scan"]),
    ("lehmann-golden-bridges", "song", ("lieder", "Lehmann,_Liza/Songs_of_Love_and_Spring/06a_Golden_Bridges"), LIED + "Lehmann,_Liza/Songs_of_Love_and_Spring/06a_Golden_Bridges/", CC0, None, ["ms", "ly"]),
    ("hensel-op7-1-nachtwanderer", "song", ("lieder", "Hensel,_Fanny/6_Lieder,_Op.7/1_Nachtwanderer"), LIED + "Hensel,_Fanny/6_Lieder,_Op.7/1_Nachtwanderer/", CC0, None, ["ms", "vr"]),
    ("schumann-op96-4-gesungen", "song", ("lieder", "Op.96/4_Gesungen"), LIED + "Schumann,_Robert/Lieder_und_Gesänge,_Vol.IV,_Op.96/4_Gesungen/", CC0, None, ["ms", "ly"]),
    ("kinkel-op8-5-trennung", "song", ("lieder", "Kinkel,_Johanna/6_Gedichte,_Op.8/5_Trennung"), LIED + "Kinkel,_Johanna/6_Gedichte,_Op.8/5_Trennung/", CC0, None, ["ms", "vr", "scan"]),
    ("schubert-die-stadt", "song", ("lieder", "Schwanengesang,_D.957/11_Die_Stadt"), LIED + "Schubert,_Franz/Schwanengesang,_D.957/11_Die_Stadt/", CC0, None, ["ms", "ly"]),
    ("schubert-ave-maria", "song", ("lieder", "Ellens_Gesang_III"), LIED + "Schubert,_Franz/Op.52/6_Ellens_Gesang_III,_D.839_(Ave_Maria)/", CC0, None, ["ms", "vr"]),
    ("beethoven-op52-2-feuerfarb", "song", ("lieder", "Op.52/2_Feuerfarb"), LIED + "Beethoven,_Ludwig_van/8_Lieder,_Op.52/2_Feuerfarb/", CC0, None, ["ms", "ly"]),
    ("haydn-canzonet-she-never-told", "song", ("lieder", "She_never_told_her_love"), LIED + "Haydn,_Joseph/10_Canzonets/09_She_never_told_her_love,_Hob.XXVIa34/", CC0, None, ["ms", "vr"]),
    ("beethoven-op48-5-gottes-macht", "song", ("lieder", "Op.48/5_Gottes_Macht"), LIED + "Beethoven,_Ludwig_van/6_Lieder,_Op.48/5_Gottes_Macht_und_Vorsehung/", CC0, None, ["ms", "ly", "scan"]),
    ("haydn-quartet-op20-6", "quartet", ("sq", "Op.20_No.6"), SQ + "Haydn,_Joseph/String_Quartet_in_A_major,_Hob.III36,_Op.20_No.6/", CC0, 28, ["ms", "vr"]),
    ("mozart-quartet-k155", "quartet", ("sq", "K.155134a"), SQ + "Mozart,_Wolfgang_Amadeus/String_Quartet_No.2_in_D_major,_K.155134a/", CC0, 28, ["ms", "ly"]),
    ("mozart-quartet-k80", "quartet", ("sq", "K.8073f"), SQ + "Mozart,_Wolfgang_Amadeus/String_Quartet_No.1_in_G_major,_K.8073f/", CC0, 28, ["ms", "vr", "scan"]),
    ("mayer-quartet-op14", "quartet", ("sq", "Op.14/sq7082029"), SQ + "Mayer,_Emilie/String_Quartet_in_G_minor,_Op.14/sq7082029.mxl", CC0, 28, ["ms", "ly"]),
]
REAL = [
    ("mozart-k545-1", "lilypond-mutopia", "spike/omr/mutopia/mozart-k545-1-mutopia.pdf"),
    ("chopin-prelude-4", "lilypond-mutopia", "spike/omr/mutopia/chopin-28-4-mutopia.pdf"),
    ("mozart-k545-1", "real-scan-peters", "spike/omr/scans/mozart-k545-1-scan.pdf"),
    ("chopin-prelude-4", "real-scan-schirmer", "spike/omr/scans/chopin-prelude-4-scan.pdf"),
]
