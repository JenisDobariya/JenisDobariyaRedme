# Your animated GitHub profile: where everything goes

Same design as the reference. Only the photo, video and details are yours.

## 1. Drop your media in `assets/`

| What | Put it here | Shows up in |
|---|---|---|
| Intro video (waving / saying hi, ~2 s used) | `assets/video/hello.mp4` | `hero.svg`, the "video" on the right |
| Badge photo (any portrait) | `assets/photos/id-photo.jpg` | `id-dashboard.svg`, the swinging ID card |
| Half-body photo (transparent PNG is best) | `assets/photos/connect.png` | `connect.svg`, "Let's build something together" |

The "video" is JPEG frames animated inside the SVG (that's how the reference does it too, because GitHub READMEs can't play real video). `build.py` does the conversion for you.

## 2. Fill in `config.json`

Everything marked `TODO` is something only you can fill in:
`github_username`, `email`, Instagram/Threads handles, and your 3 hobbies.
Everything else is already filled from what I know about you. Edit freely.

## 3. Build

```bash
pip install -r requirements.txt     # needs ffmpeg installed too
python build.py                     # reads config + assets, writes README.md and the 5 .svg files
```
The build prints a list of anything still left to fix (placeholder media, text that is too long for its slot).
Open the `.svg` files in a browser to preview them.

## 4. Publish

1. On GitHub create a **public repo named exactly your username**.
2. Push everything in this folder to it (`main` branch).
3. Repo > **Actions** > run **"3D contribution city"** once (creates `profile-3d-contrib/`, used by the README).
4. Optional: **"rebuild profile"** runs daily and refreshes the live numbers (repos, stars, forks, followers, top repos) on the dashboard card.

## Notes
- The "MOST-STARRED PROJECTS" card uses your real top repos once `github_username` is set.
- Stack icons come from `templates/icons.json`. To add one, tell me the tool name.
- The two illustrations in `about-life.svg` (developer at laptop; hobby carousel) are part of the original design and are unchanged.
