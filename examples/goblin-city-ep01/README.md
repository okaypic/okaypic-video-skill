# GOBLIN CITY · Episode 1 · The Liquidation

A real episode made with this skill on 2026-10-03: 28 shots × 10 s, two takes each, 56/56
renders succeeded, about US$6 in API calls, assembled to a 4:49 episode with English and
Chinese captions.

**Logline.** In Meridian, a near-future megacity where your face is your wallet and your key, a
founder who can't raise his Series B bets everything on a meme coin called GoblinCoin on a tip
from an investor. He is liquidated at 3:33 a.m., wakes up as a goblin, is thrown out of his own
building, and is led down a manhole into Undertown — where the goblins are celebrating his
liquidation on a chalkboard. "Welcome. Drinks are on you."

Files:

- `cast.json` — six reference sheets (the founder as a human and as a goblin, the investor, a
  hostess, a delivery rider, the goblin doorman). Note the retained anchors: the red tie, the
  curls between the ears, the loose gold watch.
- `shots.json` — the 28-shot script. Shots 26–28 were added after watching the first cut (the
  user wanted an angry phone call and a moment of despair between the liquidation and the
  morning); their ids are out of order on purpose, the array order is the cut.
- `edit.json` — picks (two shots use take `b`: one because the other seed put two goblins in
  frame), full en/zh captions with timings, the end card.

Things this episode taught us, now baked into the skill:

- Character consistency across ~50 clips is good when every clip gets the full reference sheet.
- One seed out of fifty duplicated the main character; the other seed was fine. Always render two.
- H3's loudness varies ±15 dB between takes → per-clip levelling in `edit.py`.
- Investor and founder came out looking like the same actor until the investor got a bald head,
  beard and glasses. Make leads visually orthogonal.
- Readable chalkboard text doesn't render; overlay it or lock a painted first frame (ref_mode `okay`).
