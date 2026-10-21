# Event recap preset (music-only coverage)

Read before planning any event edit. Lessons from event recaps shot on phones and small handheld cameras.
A brand skill can add the event's own notes on top.

## Story and footage
- **Find the main person and feature them** (the host, the organiser): about one shot in six, spread through the
  video (not grouped), each entered with a whip.
- **Reveals:** when the host turns the camera to show someone, keep the shot running until that person is on screen.
- **Alone shots end before the camera spins.** Check the frames around each turn and cut before it starts.
- **One shot per guest.** Don't keep returning to the same guest: three shots of one guest is too many.
- **Key moments get room:** a hand-over or a surprise, then the reaction punched in on the face (`zoom` 2.4 with
  `focus`).
- **No repeated footage:** every source range is used once. A stage / mic shot appears once, very briefly.
- **No category labels** (THE VENUE, THE FOOD…). Only a big centred title (`kinetic`, `place: center`) at the start;
  end on the event's own logo backdrop if one was filmed.
- Up to one minute; shorter is fine when the footage runs out.

## Music and sound
- Free-licence music only (Mixkit, incompetech.com, freepd.com, freemusicarchive.org). Agree the track with the
  user at the start: send a shortlist as 20 s previews.
- Avoid bright, harsh synth leads: they tire fast under a minute of footage.
- **Cut exactly on the beat.** The engine keeps every cut within half a frame of its planned time.
- **Effects quiet**: `sfx_volume` 0.04, well under the music. Clip audio muted (`mute: true` on every segment).

## Colour
- Phone and pocket-camera footage indoors comes out **yellow and flat**. Use `"grade": {"look": "clean"}`: per-shot
  white balance, real blacks and whites, contrast on brightness only. Grade every event edit (default `clean`).
- **White balance must be on spot, not just less yellow.** `grade.white_balance` neutralises fully along the
  warm-cool axis (iterative grey-pixel search, bright surfaces weigh most); only the green-magenta part is capped
  (`TINT_LIMIT`) so coloured LED light doesn't turn skin sallow. Check a known white (banner, box, wall) in a still:
  it should read within about 3 ΔE of neutral.
- **No extra saturation.** `punchy` adds contrast and sharpening, not saturation.
- Relighting (brighten the person a little, dim the room a touch, via the person matte) works on stills; it is not
  in the renderer yet.

## Effects to offer
- The effects toolbox is installed (see the skill's "Effects toolbox"). Show stills or a short sample first.
- Candidates for events: beat zoom pulses, speed ramps on 60 fps footage, a freeze frame with a sticker cut-out
  of the person and a name tag, light-leak transitions, shake on hits, split screens on the beat.
