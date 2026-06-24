# Recording the demo video

The deck's slide 10 embeds a video at `docs/assets/demo.mp4`. Until you
drop that file in, slide 10 will show a "video unavailable" icon. This
guide is the recipe — should take 10–15 min end-to-end.

## TL;DR

1. Pre-stage a branch with a buggy file on `rahulilla/python-simple-webapp`
2. Start the watcher + dashboard in one terminal: `./scripts/start.sh rahulilla/python-simple-webapp`
3. `Cmd+Shift+5` → "Record Selected Portion" → record the demo
4. Compress with the ffmpeg one-liner below
5. Drop the result at `docs/assets/demo.mp4`
6. Refresh slide 10, commit, push

---

## 1. Pre-stage the PR (so you can open it on camera)

You want the PR-creation moment in the video, not the pre-amble. Create
the branch + bad change *before* hitting Record:

```bash
cd ~/AI_Training/demo_webapp     # the python-simple-webapp clone
git checkout main && git pull
git checkout -b demo/sqli-leak

# Append a buggy function to app.py — something visually striking
cat >> app.py <<'EOF'

def lookup_user(db_conn, username: str):
    cursor = db_conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()
EOF

git commit -am "demo: add lookup_user (buggy)"
git push -u origin demo/sqli-leak
```

Don't open the PR yet — that's the on-camera moment.

## 2. Start the watcher + dashboard

```bash
cd ~/AI_Training
./scripts/start.sh rahulilla/python-simple-webapp
```

Wait for both banners to appear. The dashboard opens at
<http://localhost:8501>. Open it in a browser tab.

## 3. Set up your screen for the recording

Three windows visible (arrange before recording — re-arranging on camera looks rough):

- **Left half:** Browser at `github.com/rahulilla/python-simple-webapp`,
  on the **"Compare changes"** page for `main ← demo/sqli-leak`.
- **Right half top:** Terminal showing the watcher's `[watch]` /
  `[dash]` interleaved output.
- **Right half bottom (or new tab):** Streamlit dashboard at `localhost:8501`,
  on the **"Overview"** tab.

## 4. Record the demo

`Cmd + Shift + 5` opens the macOS capture toolbar.

- Click **"Record Selected Portion"** (the dashed-rectangle icon)
- Drag a box around the three windows
- **Options** → uncheck "Microphone" (we want no audio — the slide
  embeds with muted-autoplay)
- Hit **Record**

### The 2:45 shot list

| Time | What's on screen | What you do |
|---|---|---|
| 0:00 | Compare-changes page | Pause briefly so the viewer sees the diff |
| 0:10 | Same | Click **"Create pull request"** |
| 0:20 | New PR page | Add a one-line title like "Add lookup_user helper", click "Create pull request" |
| 0:35 | New PR page | Cut focus to the terminal |
| 0:40 | Terminal | Watcher prints `[watch] >>> new PR #N detected` |
| 0:50 | Terminal | Watch the agents log:`[orchestrator] parsed N chunks → [security] 1 finding → [bug] 4 → [style] N → [triage] flagging for human review → [patch] proposal generated → [test] suite generated → [pr] comment posted` |
| 1:30 | Browser | Refresh the PR page → the agent's comment is there. Slowly scroll through the severity table + the CWE-89 finding |
| 1:55 | Browser | Cmd+click the follow-up PR link in the comment → the new tab shows 2 changed files (fix + test) |
| 2:15 | Streamlit dashboard | Switch focus → KPIs have ticked up. Hover the recent-activity table |
| 2:30 | Dashboard | Click **"LLM Telemetry"** tab → show the Total Cost KPI ticked up by ~$0.14 |
| 2:45 | Dashboard | Stop recording (menu bar) |

## 5. Compress for the deck

The raw `.mov` is typically 100–400 MB. The slide needs ≤30 MB to
stay snappy on GitHub Pages. ffmpeg one-liner:

```bash
# Install ffmpeg first if needed: brew install ffmpeg
ffmpeg -i ~/Desktop/<recording>.mov \
       -an \
       -vf "scale=1280:-2" \
       -vcodec libx264 -crf 28 -preset medium \
       -movflags +faststart \
       ~/AI_Training/docs/assets/demo.mp4
```

What each flag does:
- `-an` — strip audio (we don't want it; saves ~3 MB)
- `-vf "scale=1280:-2"` — downscale to 1280px wide, height auto
- `-crf 28` — quality knob, 23=visually-lossless, 28=clearly compressed but still sharp on a projector
- `-preset medium` — balance encode time vs file size
- `-movflags +faststart` — moves the metadata to the start of the file so the browser can start playing before the whole file downloads

Expected output: 8–25 MB depending on motion. Verify:

```bash
ls -lh ~/AI_Training/docs/assets/demo.mp4
ffprobe -hide_banner ~/AI_Training/docs/assets/demo.mp4 2>&1 | head -20
```

If it's still over 30 MB, increase `-crf` to 30 or 32 (worse quality)
or drop resolution with `scale=960:-2`.

## 6. Verify on the slide

```bash
cd ~/AI_Training/docs && python3 -m http.server 8765
open http://localhost:8765/#10
```

The video should autoplay muted on loop. If you see a black box with
a slash-through-circle icon, the file isn't being served — check that
`docs/assets/demo.mp4` exists and the path matches.

## 7. Commit + push

```bash
cd ~/AI_Training
git add docs/assets/demo.mp4
git commit -m "docs(demo): record live demo video for slide 10"
git push origin main
```

GitHub Pages redeploys in 30–60s. Hard-refresh
<https://rahulilla.github.io/MultiAgentCodeReview/#10> to confirm.

## Common gotchas

- **Browser autoplay was blocked.** The video must be muted *and* have
  `autoplay` attribute *and* `playsinline`. All three are already in the
  HTML — if it still doesn't autoplay, your browser has a stricter
  autoplay policy than usual. Click the video once to start it; the loop
  will continue thereafter.
- **File over GitHub's 100 MB cap.** Re-encode with higher `-crf`
  (smaller file, lower quality). If you can't get under 100 MB, switch
  to unlisted YouTube or GitHub Releases and update the slide's
  `<video src=...>` to point at the new URL.
- **`Cmd+Shift+5` doesn't capture cursor.** Click "Options" in the
  toolbar → check "Show Mouse Pointer."
