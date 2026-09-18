# Hero film

`hero.mp4` is the home page's background film: muted, looping, 854×480, 34 s,
made by the team for MealCraft and free to publish. `hero-poster.jpg` is its
first frame, shown until the video can play.

Re-encoded from the team's master file for the web (no audio track, H.264
CRF 25, fast start). Keep replacements dark-set, without text or watermarks,
and under about 10 MB:

```bash
ffmpeg -i master.mp4 -an -c:v libx264 -crf 25 -preset slow -pix_fmt yuv420p -movflags +faststart hero.mp4
ffmpeg -ss 0.5 -i hero.mp4 -frames:v 1 -q:v 3 hero-poster.jpg
```
