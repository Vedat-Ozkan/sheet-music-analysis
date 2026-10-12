PDF warning regression fixtures are unchanged final production readings and one
correct score from the local OMR benchmarks. No recognition is rerun in these tests.

- `schubert_die_stadt_audiveris.musicxml`: `bench/cache/runs/results-final--schubert-die-stadt--ms.musicxml`.
  Source: https://github.com/OpenScore/Lieder/tree/main/scores/Schubert,_Franz/Schwanengesang,_D.957/11_Die_Stadt/
  Licence: CC0 1.0 (OpenScore)
  SHA256: `c37fd27d053bc9c2f6e0071db2770bfa344ee591b55446ce28ccd131ba5de447`.
- `schubert_die_stadt.mxl`: `bench/truth/schubert-die-stadt.mxl`.
  Source: https://github.com/OpenScore/Lieder/tree/main/scores/Schubert,_Franz/Schwanengesang,_D.957/11_Die_Stadt/
  Licence: CC0 1.0 (OpenScore)
  SHA256: `fe0330f5f21461402df45d8b2de6fd1fa1e6470d8705e4b200eb4c7d22e161cb`.
- `haydn_she_never_told_audiveris.musicxml`: `bench/cache/runs/results-final--haydn-canzonet-she-never-told--ms.musicxml`.
  Source: https://github.com/OpenScore/Lieder/tree/main/scores/Haydn,_Joseph/10_Canzonets/09_She_never_told_her_love,_Hob.XXVIa34/
  Licence: CC0 1.0 (OpenScore)
  SHA256: `b69d67a453fa7f42a4439c74903a8e6002c9440c851c9d07cf43786557250a6d`.
- `lang_auf_der_reise_audiveris.musicxml`: `bench-heldout3/cache/runs/results-final--h3-lang-auf-der-reise--ms.musicxml`.
  Source: https://github.com/OpenScore/Lieder/tree/main/scores/Lang,_Josephine/_/Auf_der_Reise,_Op.22/
  Licence: CC0 1.0 (OpenScore)
  SHA256: `d2f0933220365715b4c7c098c6036486cda5f31d9822ba803250ce91fc18900d`.

Fix round 2 fixtures:

- `haydn_she_never_told.pdf`: unchanged `bench/pdfs/haydn-canzonet-she-never-told--ms.pdf`, same OpenScore source/licence as the Haydn reading above. SHA256: `1f5ae7c5a9ab152179dde319b75507e31b2a3ea36988b6e02e7d1abc4e00036c`.
- `haydn_she_never_told_variant0.mxl`: unchanged `bench/cache/raw/8a4f7a667f301327e52dad69632f4575.mxl`, Audiveris settings variant 0; no skipped pages. Same Haydn source/licence. SHA256: `95e68d319ed19fdb889c0cce0fd0de59606c0978b91c7dfa0151ce591a678b47`.
- `haydn_she_never_told_variant1.mxl`: unchanged `bench/cache/raw/4c7eb9d6699b21f958645b3020c8d137.mxl`, Audiveris settings variant 1; no skipped pages. Same Haydn source/licence. SHA256: `2e6670272e322b9098cf3ce058c9ff001b7dae58913ce88dac4911874dcbba56`.
- `haydn_she_never_told_variant2.mxl`: unchanged `bench/cache/raw/cb8fdad041ea4102bb0ce37588d41006.mxl`, Audiveris settings variant 2; no skipped pages. Same Haydn source/licence. SHA256: `18536e97502d7d8fe0003e0221c1cf55574ce00adb9a2f79bbaa3e58dcc4ada8`.
- `fractional_durations.musicxml`: reviewer reproduction, two voices of four eighth notes in 2/4, divisions=1 and duration=0.5; backup=2. Constructed valid MusicXML, not an OMR output. SHA256: `9b042f405674518caf32e749e26aa8d688abb37a94dde06bb9a99cd77ac7965c`.
