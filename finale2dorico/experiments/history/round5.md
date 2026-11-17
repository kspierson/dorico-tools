# Round 5: Willow hairpin ends

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round5\`

Regenerate: `python3 -m f2d convert "/mnt/c/Users/kspie/Documents/HPCaptures/finale/scores/Willow.musx" -o experiments/round5/12-willow-full.dorico`

Change: Finale stores a hairpin's end wherever it was dragged. In bar 1 every woodwind/trumpet
crescendo ends somewhere inside the last quintuplet note (Flute 1 at beat 3.88, Oboe 1 at 3.90 …),
so snapping to the *nearest* note sent some to the barline and some to the note before; Oboe 1 and
Trumpet 1 then "hung over" and couldn't be linked. Now a hairpin end inside a note covers that
note (ends at the next note or barline), unless it sits right on a note start; and a hairpin that
overhangs the next dynamic by up to half a beat is trimmed so it joins the group.

| Check | Result |
|---|---|
| Bar 1: the woodwind/trumpet crescendos all end at the barline and are linked (Oboe 1 / Trumpet 1 included)? | |
| Anything else that should be linked or grouped but isn't? | |

Question: in that passage the f (beat 2) and the cresc (beat 4) are separate groups because they
are two beats apart (the grouping rule allows up to one beat, from your 07 example). Should a
dynamic and the next hairpin be grouped across a larger gap, e.g. anywhere within the same bar?
