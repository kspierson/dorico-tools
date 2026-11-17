## Have Yourself A Merry Little Christmas 2.dorico

**Rack:** DoricoBeep ×1, Kontakt ×9, Pianoteq 6 STAGE ×2, SWAM Bass Clarinet 64bit ×1, SWAM Clarinet 64bit ×1

**Channels**: buses, each rack slot's main output, and any output with inserts, a changed send or a moved fader. 520 further outputs are untouched (no inserts, usual fader, usual send). Usual fader: 0 dB (not stored); usual send: +0.0 dB (on) ("on" = stored without `enabled="0"`; that such sends really sound is assumed, not yet checked in Dorico). No pan is stored anywhere.

| Rack | Plug-in | Channel | Kind | Fader | Inserts | Sends |
|---|---|---|---|---|---|---|
|  |  | Out | output | 0 dB | 1: Altiverb 7<br>4: Compressor (off) |  |
|  |  | Video Audio | input | 0 dB |  |  |
|  |  | Fx Reverb | fx-return | -inf dB | 1: REVerence (off) |  |
| 1 | DoricoBeep | AudioOutput | instrument-return | 0 dB |  | Fx Reverb -26.0 dB |
| 7 | SWAM Clarinet 64bit | 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 9 | SWAM Bass Clarinet 64bit | 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 14 | Kontakt | Kt. st. 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 14 | Kontakt | Kt. aux 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb +0.0 dB |
| 14 | Kontakt | Kt. aux 2 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb +0.0 dB |
| 17 | Kontakt | Kt. st. 1 | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 18 | Kontakt | Kt. st. 1 | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 19 | Kontakt | Kt. st. 1 | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 21 | Kontakt | Kt. st. 1 | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 22 | Pianoteq 6 STAGE | Output | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 23 | Kontakt | Kt. st. 1 | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |
| 24 | Kontakt | Kt. st. 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 25 | Kontakt | Kt. st. 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 26 | Kontakt | Kt. st. 1 | instrument-return | 0 dB | 1: VirtualSoundStage2_x64 | Fx Reverb -6.0 dB |
| 27 | Pianoteq 6 STAGE | Output | instrument-return | 0 dB |  | Fx Reverb -6.0 dB |

**Altiverb**

| Channel | Slot | Settings |
|---|---|---|
| Out | 1 | IR MUSIC/studio-scoring/Todd-AO - California USA/15.7m wide s-s, dry/wet 0.55, direct gain 0, ER gain 0, tail gain 0, pre-delay 0, size 100, reverb time 1, direct on, ER off, tail on, stage positions off, bypass off |

**Virtual Sound Stage 2** (8 instances, front to back; x < 0 = left, y = metres back, facing 0 = toward the listener)

Shared room settings: room id 1399018306, level -3, dry/wet 0, seat 0

| Rack | Plug-in | Output | Pin | Preset | x | y | h | Width | Facing | ER | Direct | Gain | Air | Send |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 26 | Kontakt | Kt. st. 1 | T Sax | SWAM\Woodwinds\Saxophone (Orchestral) | 4.70 | 4.95 | 1.5 | point | -44° | 2 | 0 | 0 | 10 | Fx Reverb -6.0 dB |
| 9 | SWAM Bass Clarinet 64bit | 1 | Bs Cl | SWAM\Woodwinds\Bass Clarinet | -3.93 | 5.47 | 1.5 | point | 36° | 2 | 0 | 0 | 10 | Fx Reverb -6.0 dB |
| 25 | Kontakt | Kt. st. 1 | B Sax | SWAM\Woodwinds\Saxophone (Orchestral) | 3.55 | 5.60 | 1.5 | point | -24° | 2 | 0 | 0 | 10 | Fx Reverb -6.0 dB |
| 24 | Kontakt | Kt. st. 1 | A Sax | SWAM\Woodwinds\Saxophone (Orchestral) | 2.10 | 6.00 | 1.5 | point | -19° | 2 | 0 | 0 | 10 | Fx Reverb -6.0 dB |
| 14 | Kontakt | Kt. aux 2 | Tbn 3 | SWAM\Brass\Trombone 3 | 6.25 | 6.25 | 1.5 | point | -45° | 3 | 0 | 0 | 30 | Fx Reverb +0.0 dB |
| 7 | SWAM Clarinet 64bit | 1 | Cl 1 | SWAM\Woodwinds\Clarinet 1 | -2.53 | 6.27 | 1.5 | point | 22° | 2 | 0 | 0 | 10 | Fx Reverb -6.0 dB |
| 14 | Kontakt | Kt. aux 1 | Tbn 2 | SWAM\Brass\Trombone 2 | 4.70 | 7.25 | 1.5 | point | -34° | 3 | 0 | 0 | 30 | Fx Reverb +0.0 dB |
| 14 | Kontakt | Kt. st. 1 | Tbn 1 | SWAM\Brass\Trombone 1 | 3.20 | 7.95 | 1.5 | point | -22° | 3 | 0 | 0 | 30 | Fx Reverb -6.0 dB |

