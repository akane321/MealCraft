# Hero film

`hero.mp4` is the home page's background film: muted, looping, 1920×1080, 30 fps,
35.5 s, H.264 at about 20 Mbit/s, of fruit, vegetables and dishes. The project
owner chose it and asked for it as supplied: no filter and no loss of quality.
`hero-poster.jpg` is the frame at 0.5 s, shown until the video can play.

The video stream is the owner's file unchanged. Only the container was
rewritten: the unused audio track dropped and the index moved to the front
(fast start), so the browser can start playing before the whole file arrives:

```bash
ffmpeg -i master.mp4 -map 0:v:0 -c:v copy -an -movflags +faststart hero.mp4
ffmpeg -ss 0.5 -i hero.mp4 -frames:v 1 -q:v 2 hero-poster.jpg
```

Keep replacements without text or watermarks. GitHub refuses files over
100 MB.
