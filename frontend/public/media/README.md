# Hero film

`hero.mp4` is the home page's background film: muted, looping, 1280×720, 53 s,
a stop-motion short of fruit and vegetables. The project owner cleared it for
publication in this repository. `hero-poster.jpg` is its first frame, shown
until the video can play.

Trimmed so the black frames at the start and end are short and the loop is
smooth, then re-encoded for the web (no audio track, H.264, fast start). Keep
replacements without text or watermarks and under about 10 MB:

```bash
ffmpeg -i master.mp4 -an -c:v libx264 -crf 25 -preset slow -pix_fmt yuv420p -movflags +faststart hero.mp4
ffmpeg -ss 0.5 -i hero.mp4 -frames:v 1 -q:v 3 hero-poster.jpg
```
