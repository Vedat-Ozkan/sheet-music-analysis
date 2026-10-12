The triplet regression fixtures are unchanged cleaned production readings from
`spike/omr/bench/results-prod2.json` (Audiveris signature recorded in that file).

- `triplet_mayer.musicxml`: Emilie Mayer, String Quartet Op.14, LilyPond PDF;
  cache `333d769a33d8acb75d0e7646ed1d86c1.musicxml`.
- `triplet_hensel.musicxml`: Fanny Hensel, Nachtwanderer Op.7/1, MuseScore PDF;
  cache `ccacfd27990df9c8eb15639a634b174c.musicxml`.

Both source scores are OpenScore CC0; source URLs and truth files are in the
benchmark manifest. Tests replace only external recognition, then exercise
`read_pdf`, `clean`, the post-fix, Verovio import and `ScoreIndex` on these readings.
