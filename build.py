#!/usr/bin/env python3
"""
Builds your animated GitHub profile README.

    python build.py            # build everything into ./out  and refresh README.md
    python build.py --no-live  # skip the GitHub API call (use numbers from config.json)

Your inputs:
    config.json                      all text / details
    assets/video/hello.mp4           your short intro video  (hero, right side)
    assets/photos/id-photo.jpg       photo on the swinging ID badge
    assets/photos/connect.png        half-body photo for "Let's connect" (transparent PNG is best)
"""
import argparse, base64, html, io, json, math, os, re, shutil, subprocess, sys, tempfile, urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("Missing dependency. Run: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
TPL = ROOT / "templates"
OUT = ROOT  # SVGs are written next to README.md so relative links work on GitHub
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ICONS = json.loads((TPL / "icons.json").read_text(encoding="utf-8"))
WARN = []

# ----------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=False).replace("·", "&#183;")

def fill(tpl, mapping):
    """Replace {{token}} placeholders; fail loudly on missing ones."""
    def r(m):
        k = m.group(1)
        if k not in mapping:
            raise KeyError(f"template token not provided: {k}")
        return str(mapping[k])
    return re.sub(r"\{\{(\w+)\}\}", r, tpl)

def b64(b):
    return base64.b64encode(b).decode()

# ---- text measuring using the fonts embedded in the templates -----------
class Measure:
    def __init__(self):
        self.fonts = {}
        self.ok = True
        try:
            from fontTools.ttLib import TTFont
            head = (TPL / "hero.svg").read_text(encoding="utf-8")
            for name, data in re.findall(r"font-family:'(\w+)';src:url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\)", head):
                f = TTFont(io.BytesIO(base64.b64decode(data)))
                self.fonts[name] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
        except Exception as e:  # fontTools / brotli missing -> rough estimate
            self.ok = False
            WARN.append(f"text-fit is approximate (fonttools/brotli not available: {e})")

    def w(self, text, font, size):
        text = html.unescape(text)
        if font in ("JBM", "JBMB"):
            return len(text) * 0.6 * size
        if not self.ok or font not in self.fonts:
            return len(text) * 0.56 * size
        cmap, hmtx, upm = self.fonts[font]
        total = 0
        for ch in text:
            g = cmap.get(ord(ch))
            total += hmtx[g][0] if g else upm * 0.5
        return total / upm * size

    def fit(self, text, font, size, max_w, min_size=9, spacing=0.0):
        s = size
        while s > min_size and self.w(text, font, s) + spacing * len(text) > max_w:
            s -= 0.5
        return s

M = Measure()

def warn_width(label, text, font, size, max_w, spacing=0.0):
    w = M.w(text, font, size) + spacing * len(text)
    if w > max_w:
        WARN.append(f"'{label}' is {w:.0f}px wide but only ~{max_w:.0f}px fit — shorten it: {text!r}")

# ----------------------------------------------------------------- GitHub live stats
def github_stats(user, use_live=True):
    fb = CFG["dashboard"]["stats_fallback"]
    fallback_repos = CFG["dashboard"]["featured_repos_fallback"]
    stats = dict(fb)
    repos = list(fallback_repos)
    if not use_live or not user or user.startswith("TODO"):
        return stats, repos, False
    def get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "profile-builder", "Accept": "application/vnd.github+json"})
        tok = os.environ.get("GITHUB_TOKEN")
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    try:
        u = get(f"https://api.github.com/users/{user}")
        rp = get(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner&sort=pushed")
        own = [r for r in rp if not r.get("fork")]
        stats = {
            "repos": u.get("public_repos", len(rp)),
            "stars": sum(r.get("stargazers_count", 0) for r in own),
            "forks": sum(r.get("forks_count", 0) for r in own),
            "followers": u.get("followers", 0),
        }
        top = sorted(own, key=lambda r: (-r.get("stargazers_count", 0), r["name"]))[:5]
        if top:
            repos = [{"name": r["name"], "stars": r.get("stargazers_count", 0)} for r in top]
        return stats, repos, True
    except Exception as e:
        WARN.append(f"could not reach GitHub API ({e}); using numbers from config.json")
        return stats, repos, False

# ----------------------------------------------------------------- placeholder media
def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def placeholder_portrait(w, h, label):
    img = Image.new("RGB", (w, h), (23, 26, 44))
    d = ImageDraw.Draw(img)
    for y in range(h):  # soft gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(30 + 40 * t), int(26 + 20 * t), int(60 + 60 * t)))
    cx = w // 2
    d.ellipse([cx - w * .17, h * .22, cx + w * .17, h * .22 + w * .34], fill=(236, 238, 246))
    d.ellipse([cx - w * .34, h * .62, cx + w * .34, h * 1.25], fill=(236, 238, 246))
    f = _font(max(12, w // 12))
    tw = d.textlength(label, font=f)
    d.text(((w - tw) / 2, h * .92), label, font=f, fill=(167, 139, 250))
    return img

def placeholder_frames(n, size=(724, 540)):
    frames = []
    W, H = size
    f = _font(26)
    for i in range(n):
        img = Image.new("RGB", size, (13, 14, 22))
        d = ImageDraw.Draw(img)
        t = i / max(1, n - 1)
        cx = W * (0.35 + 0.3 * t)
        d.ellipse([cx - 70, 120, cx + 70, 260], fill=(236, 238, 246))
        d.ellipse([cx - 150, 270, cx + 150, 700], fill=(236, 238, 246))
        txt = "YOUR VIDEO HERE"
        d.text(((W - d.textlength(txt, font=f)) / 2, 40), txt, font=f, fill=(34, 211, 238))
        txt2 = "assets/video/hello.mp4"
        d.text(((W - d.textlength(txt2, font=f)) / 2, 76), txt2, font=f, fill=(141, 147, 171))
        frames.append(img)
    return frames

# ----------------------------------------------------------------- hero
FPS = 24

def extract_frames(video, start, seconds, size):
    ffmpeg_path = r"C:\Users\jenis\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
    if ffmpeg_path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_path
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required to read your video. Install it (https://ffmpeg.org) and re-run.")
    tmp = Path(tempfile.mkdtemp())
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(seconds), "-i", str(video),
           "-vf", f"fps={FPS}", "-start_number", "0", str(tmp / "f%04d.png")]
    subprocess.run(cmd, check=True)
    files = sorted(tmp.glob("f*.png"))
    if not files:
        sys.exit("No frames could be read from the video (check start_seconds / file).")
    frames = [Image.open(f).convert("RGB") for f in files]
    shutil.rmtree(tmp, ignore_errors=True)
    return frames

def cover(img, size, focus_y):
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, focus_y))

def jpeg_bytes(img, q):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
    return buf.getvalue()

def build_video_block(loop_out):
    v = CFG["video"]
    path = ROOT / v["file"]
    size = (724, 540)
    if path.exists():
        frames = extract_frames(path, v.get("start_seconds", 0), min(float(v.get("seconds", 2.0)), 2.5), size)
        src = "your video"
    else:
        frames = placeholder_frames(36, size)
        src = "PLACEHOLDER"
        WARN.append(f"no video at {v['file']} -> using a placeholder. Drop your clip there and re-run.")
    frames = [cover(f, size, v.get("focus_y", 0.2)) for f in frames][:60]
    
    # Keep it at 100% scale and high quality (HD)
    scale = 1.0
    q = 85
    data = [jpeg_bytes(f, q) for f in frames]
    total = sum(len(d) for d in data) * 4 / 3
    
    print(f"  hero video: {len(frames)} frames from {src}, jpeg q={q}, scale={scale:.2f}, ~{total/1024:.0f} KB")
    
    n = len(data)
    # Exact seamless loop duration without pauses
    L = round(n / FPS, 3) 
    if L == 0:
        L = 1.0
        
    def kt(i):
        return i / n

    imgs = []
    for i, d in enumerate(data):
        uri = "data:image/jpeg;base64," + b64(d)
        if n == 1:
            anim = ""
        elif i == 0:
            anim = f'<animate attributeName="opacity" calcMode="discrete" values="1;0" keyTimes="0;{kt(1):.4f}" dur="{L}s" repeatCount="indefinite"/>'
        elif i == n - 1:
            anim = f'<animate attributeName="opacity" calcMode="discrete" values="0;1" keyTimes="0;{kt(i):.4f}" dur="{L}s" repeatCount="indefinite"/>'
        else:
            anim = f'<animate attributeName="opacity" calcMode="discrete" values="0;1;0" keyTimes="0;{kt(i):.4f};{kt(i+1):.4f}" dur="{L}s" repeatCount="indefinite"/>'
        imgs.append(f'<image x="560" y="0" width="724" height="540" href="{uri}" opacity="{1 if i == 0 else 0}" preserveAspectRatio="none">{anim}</image>')
    
    # Remove overall fade-out animation for a seamless loop
    block = ('<g mask="url(#vmask)"><g mask="url(#vmaskB)">\n    <g>\n'
             + "".join(imgs) + "\n    </g>\n  </g></g>")
    loop_out.append(L)
    return block

ICON_META = {
    "pin": '<path d="M0-8a6 6 0 0 1 6 6c0 4.5-6 10-6 10s-6-5.5-6-10a6 6 0 0 1 6-6z" fill="none" stroke="{c}" stroke-width="1.8"/><circle cy="-2" r="2" fill="{c}"/>',
    "briefcase": '<rect x="-7" y="-5" width="14" height="11" rx="2" fill="none" stroke="{c}" stroke-width="1.8"/><path d="M-3-5v-2.5h6V-5" fill="none" stroke="{c}" stroke-width="1.8"/>',
    "star": '<path d="M0-8l2.4 5 5.4.6-4 3.7 1.1 5.4L0 4 -4.9 6.7-3.8 1.3-7.8-2.4l5.4-.6z" fill="none" stroke="{c}" stroke-width="1.7" stroke-linejoin="round"/>',
}

def build_meta():
    colors = ["#22d3ee", "#a78bfa", "#f472b6"]
    delays = [3.0, 3.15, 3.3]
    x = 72
    out = []
    for i, item in enumerate(CFG["meta"][:3]):
        text = esc(item["text"])
        icon = ICON_META.get(item.get("icon", "pin"), ICON_META["pin"]).format(c=colors[i])
        tx = x + 16
        out.append(f'<g class="fu" style="animation-delay:{delays[i]}s"><g transform="translate({x},453)">{icon}</g>'
                   f'<text class="jb" x="{tx}" y="458" font-size="14.5" fill="#8d93ab">{text}</text></g>')
        x = tx + M.w(item["text"], "JBM", 14.5) + 52
    if x - 52 > 740:
        WARN.append("hero info row runs into the video — shorten the 'meta' texts in config.json")
    return "".join(out)

def build_hero():
    name = CFG["name"]
    n = len(name)
    w1 = M.w(name, "SG", 1.0)
    fs = min(76.0, (680 + 1.5 * n) / w1)
    loop = []
    video = build_video_block(loop)
    roles = CFG["roles"] + [""] * 4
    for i in range(4):
        warn_width(f"role {i+1}", roles[i], "JBM", 21, 640)
    for i in (0, 1):
        warn_width(f"tagline {i+1}", CFG["tagline"][i], "SGM", 18, 676)
    m = {
        "name": esc(name), "title": esc(CFG["title"]), "name_clip_w": 700, "name_fs": f"{fs:.1f}",
        "role1": esc(roles[0]), "role2": esc(roles[1]), "role3": esc(roles[2]), "role4": esc(roles[3]),
        "tagline1": esc(CFG["tagline"][0]), "tagline2": esc(CFG["tagline"][1]),
        "META": build_meta(), "VIDEO": video, "loop": loop[0],
    }
    return fill((TPL / "hero.svg").read_text(encoding="utf-8"), m)

# ----------------------------------------------------------------- photos
def load_or_placeholder(rel, size, label):
    p = ROOT / rel
    if p.exists():
        return Image.open(p), True
    WARN.append(f"no photo at {rel} -> using a placeholder. Drop your photo there and re-run.")
    return placeholder_portrait(size[0], size[1], label), False

def build_id_photo():
    P = CFG["photos"]
    img, real = load_or_placeholder(P["id_badge"], (272, 336), "YOUR PHOTO")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (272, 336), method=Image.LANCZOS, centering=(0.5, P.get("id_badge_focus_y", 0.25)))
    return "data:image/jpeg;base64," + b64(jpeg_bytes(img, 86))

def build_connect_photo():
    P = CFG["photos"]
    TW, TH = 736, 848  # 2x of the 368x424 slot
    img, real = load_or_placeholder(P["connect"], (TW, TH), "YOUR PHOTO")
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") and img.getchannel("A").getextrema()[0] < 250
    if not has_alpha and real and P.get("connect_remove_background", True):
        try:
            from rembg import remove  # optional: pip install rembg
            print("  connect photo: removing background with rembg …")
            img = remove(img.convert("RGB"))
            has_alpha = True
        except Exception:
            WARN.append("connect photo has no transparent background. For the floating cut-out look use a transparent PNG, "
                        "or `pip install rembg` and re-run. (Using a rounded photo card meanwhile.)")
    img = img.convert("RGBA")
    if has_alpha:
        bbox = img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if bbox:
            img = img.crop(bbox)
        img.thumbnail((TW, TH), Image.LANCZOS)
    else:
        img = ImageOps.fit(img.convert("RGB"), (TW, TH), method=Image.LANCZOS, centering=(0.5, 0.25)).convert("RGBA")
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=56, fill=255)
        img.putalpha(mask)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=88, method=6)
    return "data:image/webp;base64," + b64(buf.getvalue())

# ----------------------------------------------------------------- connect
def icon_of(slug):
    if slug not in ICONS:
        sys.exit(f"Unknown icon '{slug}'. Available: {', '.join(sorted(ICONS))}")
    i = ICONS[slug]
    return i["path"], "#" + i["hex"]

def light_if_dark(hexcol):
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#eceef6" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.28 else hexcol

def handle_of(user):
    return user if user and not user.startswith("TODO") else "your-github-username"

def build_connect():
    C = CFG["connect"]
    m = {
        "name": esc(CFG["name"]),
        "CONNECT_PHOTO": build_connect_photo(),
        "connect_sub": esc(C["sub"]), "quote": esc(C["quote"]),
        "github_handle": esc(handle_of(CFG["github_username"])),
        "email": esc(C["email"]),
    }
    for k, key in ((3, "card3"), (4, "card4")):
        path, col = icon_of(C[key]["icon"])
        col = light_if_dark(col)
        m[f"c{k}_color"] = col; m[f"c{k}_path"] = path
        m[f"c{k}_label"] = esc(C[key]["label"]); m[f"c{k}_handle"] = esc(C[key]["handle"])
        warn_width(f"{key} handle", C[key]["handle"], "JBM", 12.5, 300)
    warn_width("email", C["email"], "JBM", 12.5, 270)
    return fill((TPL / "connect.svg").read_text(encoding="utf-8"), m)

# ----------------------------------------------------------------- dashboard
def counter(x, final, k):
    vals = sorted(set([round(final * j / 4) for j in range(4)] + [final]))
    t0, step = 1.0, 0.22
    D = round(max(2.1 + 0.12 * k, t0 + len(vals) * step + 0.02), 2)
    out = []
    for idx, v in enumerate(vals):
        s, e = t0 + idx * step, t0 + (idx + 1) * step
        if idx == len(vals) - 1:
            out.append(f'<text class="sg" x="{x}" y="188" font-size="36" fill="#eceef6" opacity="1">{v}'
                       f'<animate attributeName="opacity" calcMode="discrete" values="0;1" keyTimes="0;{s/D:.4f}" dur="{D:.2f}s" begin="0s" fill="freeze"/></text>')
        else:
            out.append(f'<text class="sg" x="{x}" y="188" font-size="36" fill="#eceef6" opacity="0">{v}'
                       f'<animate attributeName="opacity" calcMode="discrete" values="0;1;0" keyTimes="0;{s/D:.4f};{e/D:.4f}" dur="{D:.2f}s" begin="0s" fill="freeze"/></text>')
    return "".join(out)

def build_rows(repos):
    rows = repos[:5]
    mx = max([r["stars"] for r in rows] + [0])
    out = []
    for i, r in enumerate(rows):
        yt, yr = 311 + 34 * i, 300 + 34 * i
        name = r["name"] if len(r["name"]) <= 20 else r["name"][:19] + "…"
        W = 210.0 if mx and r["stars"] == mx else (round(max(8.0, 210.0 * r["stars"] / mx), 1) if mx else 8.0)
        d1, a1 = round(2.30 + 0.12 * i, 2), 1.4 + 0.12 * i
        d2, a2 = round(2.50 + 0.12 * i, 2), 2.2 + 0.12 * i
        out.append(
            f'<text class="jb" x="442" y="{yt}" font-size="12" fill="#8d93ab">{esc(name)}</text>'
            f'<rect x="592" y="{yr}" width="210" height="14" rx="7" fill="#ffffff" fill-opacity=".04"/>'
            f'<rect x="592" y="{yr}" width="{W}" height="14" rx="7" fill="url(#barG)"><animate attributeName="width" values="0;0;{W}" '
            f'keyTimes="0;{a1/d1:.4f};1" dur="{d1:.2f}s" begin="0s" fill="freeze" calcMode="spline" keySplines="0 0 1 1;.2 .8 .2 1"/></rect>'
            f'<text class="jbb" x="{round(592 + W + 10)}" y="{yt}" font-size="12" fill="#eceef6" opacity="1">{r["stars"]}'
            f'<animate attributeName="opacity" calcMode="discrete" values="0;1" keyTimes="0;{a2/d2:.4f}" dur="{d2:.2f}s" begin="0s" fill="freeze"/></text>')
    return "".join(out)

def build_dashboard(stats, repos, live):
    D = CFG["dashboard"]
    user = handle_of(CFG["github_username"])
    com = D["community"]
    def auto(v):
        if isinstance(v, str) and v.startswith("auto:"):
            return str(stats.get(v.split(":", 1)[1], 0))
        return str(v)
    path, col = icon_of(com["icon"])
    col = light_if_dark(col)
    fields = D["badge_fields"]
    m = {
        "ID_PHOTO": build_id_photo(),
        "COUNTER0": counter("438.0", stats["repos"], 0), "COUNTER1": counter("646.5", stats["stars"], 1),
        "COUNTER2": counter("855.0", stats["forks"], 2), "COUNTER3": counter("1063.5", stats["followers"], 3),
        "ROWS": build_rows(repos), "rows_caption": esc(D["rows_caption"]),
        "comm_title": esc(com["title"]), "comm_color": col, "comm_path": path,
        "comm_l1": esc(com["label1"]), "comm_v1": esc(auto(com["value1"])),
        "comm_l2": esc(com["label2"]), "comm_v2": esc(auto(com["value2"])),
        "comm_handle": esc("@" + user if com.get("handle", "auto") == "auto" else com["handle"]),
        "building": esc(D["building"]), "exploring": esc(D["exploring"]), "fuel": esc(D["fuel"]),
        "strap": esc(f"{CFG['nickname'].upper()}.DEV · {CFG['title'].upper()} · {CFG['nickname'].upper()}.DEV · {CFG['title'].upper()}"),
        "name": esc(CFG["name"]), "role_upper": esc(CFG["title"].upper()), "github_handle": esc(user),
    }
    warn_width("badge name", CFG["name"], "SG", 25, 270)
    for i, (lab, val) in enumerate(fields[:4], 1):
        m[f"f{i}_l"] = esc(lab); m[f"f{i}_v"] = esc(val)
        m[f"f{i}_v_fs"] = f"{M.fit(val, 'SGM', 13, 118, 10):.1f}"
    for key in ("building", "exploring", "fuel"):
        warn_width(key, D[key], "SGM", 13, 250)
    return fill((TPL / "id-dashboard.svg").read_text(encoding="utf-8"), m)

# ----------------------------------------------------------------- about / life
def build_about():
    A = CFG["about"]
    m = {"dev_heading": esc(A["dev_heading"]), "life_heading": esc(A["life_heading"]),
         "url_bar": esc(f"localhost:8000/{CFG['nickname'].lower()}")}
    warn_width("dev_heading", A["dev_heading"], "SG", 29, 560, -0.5)
    for i, s in enumerate(A["skills"][:3], 1):
        m[f"skill{i}_t"] = esc(s["title"]); m[f"skill{i}_d"] = esc(s["desc"])
        warn_width(f"skill {i} title", s["title"], "SG", 16, 520)
        warn_width(f"skill {i} desc", s["desc"], "JBM", 12.5, 520)
    for i, h in enumerate(A["hobbies"][:3], 1):
        lab = h["label"].upper()[:8]
        pw = 26 + 9 * len(lab)
        m[f"h{i}_label"] = esc(lab); m[f"h{i}_pw"] = pw; m[f"h{i}_tx"] = 688 + pw + 14
        m[f"h{i}_title"] = esc(h["title"]); m[f"h{i}_cap"] = esc(h["caption"])
        warn_width(f"hobby {i} caption", h["caption"], "SGM", 15.5, 560)
    for i, r in enumerate(A["rings"][:3], 1):
        m[f"ring{i}"] = esc(r)
    warn_width("life_heading", A["life_heading"], "SG", 29, 560, -0.5)
    return fill((TPL / "about-life.svg").read_text(encoding="utf-8"), m)

# ----------------------------------------------------------------- stack
def ichip(entry, label=None):
    slug, lab = (entry if isinstance(entry, list) else (entry, None))
    path, col = icon_of(slug)
    return {"slug": slug, "label": lab or ICONS[slug]["title"], "path": path, "col": light_if_dark(col)}

def icon_use(path, col, scale, half):
    return (f'<g transform="translate({-half:.2f},{-half:.2f}) scale({scale})" color="{col}" style="color:{col}">'
            f'<path fill="currentColor" d="{path}"/></g>')

def build_stack():
    S = CFG["stack"]
    head = (TPL / "stack.head.txt").read_text(encoding="utf-8")
    head = re.sub(r'<desc>.*?</desc>', '<desc>Tech icons orbiting a core, and a grouped grid of the tools used.</desc>', head, flags=re.S)
    defs = (TPL / "stack.defs.txt").read_text(encoding="utf-8")
    cx, cy, rx, ry = 262, 290, 172, 105
    rots = [0, 60, 120]
    def pt(rot, theta):
        r = math.radians(rot)
        x, y = rx * math.cos(theta), ry * math.sin(theta)
        return cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r)
    orbit_paths, orbit_anim = "", ""
    draws = [(1.8, 0.111), (2.05, 0.220), (2.3, 0.304)]
    for i, rot in enumerate(rots):
        sx, sy = pt(rot, 0); ex, ey = pt(rot, math.pi)
        d = f"M{sx:.1f} {sy:.1f}A172 105 {rot} 1 1 {ex:.1f} {ey:.1f}A172 105 {rot} 1 1 {sx:.1f} {sy:.1f}Z"
        dur, k = draws[i]
        orbit_paths += (f'<path d="{d}" fill="none" stroke="#61dafb" stroke-opacity=".22" stroke-width="1.6" stroke-dasharray="1400" stroke-dashoffset="0">'
                        f'<animate attributeName="stroke-dashoffset" values="1400;1400;0" keyTimes="0;{k:.3f};1" dur="{dur}s" begin="0s" fill="freeze"/></path>')
    O = S["orbit"]
    planet, moons = ichip(O["planet"]), [ichip(x) for x in O["moons"]]
    others = [ichip(x) for x in O["others"]]
    if len(moons) != 2 or len(others) != 6:
        sys.exit("stack.orbit needs exactly 2 moons and 6 others in config.json")
    bodies = [dict(orb=0, dur=26, begin=0.0, ic=planet, moons=moons)]
    spec = [(0, 26, -26 / 3), (0, 26, -52 / 3), (1, 32, -3.0), (1, 32, -19.0), (2, 38, -6.0), (2, 38, -25.0)]
    for (orb, dur, begin), ic in zip(spec, others):
        bodies.append(dict(orb=orb, dur=dur, begin=begin, ic=ic, moons=None))
    anim = ""
    for k, b in enumerate(bodies):
        ent = round(1.5 + 0.15 * k, 2)
        ka, kb = (ent - 0.5) / ent, (ent - 0.1) / ent
        ic = b["ic"]
        def body(static):
            s = ""
            if b["moons"]:
                s += '<circle r="36" fill="none" stroke="#61dafb" stroke-opacity=".3" stroke-width="1.2" stroke-dasharray="4 5"/>'
                for mi, mo in enumerate(b["moons"]):
                    inner = (f'<circle r="13" fill="#171a2c" stroke="{mo["col"]}" stroke-opacity=".6" stroke-width="1.35"/>'
                             + icon_use(mo["path"], mo["col"], 0.3683, 4.42))
                    if static:
                        s += f'<g transform="translate({36 if mi == 0 else -36}.0,0.0)">{inner}</g>'
                    else:
                        s += (f'<g><animateMotion dur="7s" begin="-{3.5 * mi}s" repeatCount="indefinite"><mpath href="#moonPath"/></animateMotion>{inner}</g>')
            s += (f'<circle r="22" fill="#171a2c" stroke="{ic["col"]}" stroke-opacity=".6" stroke-width="1.35"/>'
                  + icon_use(ic["path"], ic["col"], 0.6233, 7.48))
            return s
        anim += (f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{ka:.3f};{kb:.3f};1" dur="{ent:.2f}s" begin="0s" fill="freeze"/>'
                 f'<animateMotion dur="{b["dur"]}s" begin="{b["begin"]:.1f}s" repeatCount="indefinite"><mpath href="#orb{b["orb"]}"/></animateMotion>{body(False)}</g>')
        th = 2 * math.pi * (-b["begin"]) / b["dur"]
        px, py = pt(rots[b["orb"]], th)
        anim += (f'<g transform="translate({px:.1f},{py:.1f})"><animate attributeName="opacity" to="0" dur=".01s" begin="0s" fill="freeze"/>{body(True)}</g>')
    core = ('\n\n<circle cx="262" cy="290" r="120" fill="url(#halo)"/>\n'
            '<circle cx="262" cy="290" r="46" fill="none" stroke="#f472b6" stroke-width="1.5">\n'
            '  <animate attributeName="r" values="46;78" dur="2.8s" repeatCount="indefinite"/><animate attributeName="opacity" values=".7;0" dur="2.8s" repeatCount="indefinite"/></circle>\n'
            '<g class="core"><circle cx="262" cy="290" r="46" fill="url(#coreG)"/>\n'
            '<text class="sg" x="262" y="300" font-size="28" fill="#fff" text-anchor="middle">&lt;/&gt;</text></g>\n')
    # chips
    cats = S["categories"][:4]
    nchips = sum(len(c["items"]) for c in cats)
    cyc = round(0.45 * max(nchips, 8), 2)
    t, k = 0.5, 0
    chips = ""
    for ci, c in enumerate(cats):
        ly = 128 + 80 * ci
        chips += (f'<g class="chip" style="animation-delay:{t:.2f}s"><rect x="552" y="{ly}" width="14" height="3" rx="1.5" fill="{c["color"]}"/>'
                  f'<text class="jbb" x="574" y="{ly+5}" font-size="11.5" fill="#8d93ab" letter-spacing="2">{esc(c["name"].upper())}</text></g>')
        t += 0.1
        x = 552.0
        for item in c["items"]:
            ic = ichip(item)
            w = round(7.7 * len(ic["label"]) + 55.5, 1)
            y = ly + 20
            chips += (
                f'<g class="chip" style="animation-delay:{t:.2f}s">'
                f'<rect x="{x:.1f}" y="{y}" width="{w}" height="40" rx="12" fill="{ic["col"]}" fill-opacity=".08"/>'
                f'<rect x="{x+.5:.1f}" y="{y+.5}" width="{w-2:.1f}" height="39" rx="11.5" fill="none" stroke="{ic["col"]}" stroke-opacity=".3">'
                f'<animate attributeName="stroke-opacity" values=".3;1;.3;.3" keyTimes="0;.04;.14;1" dur="{cyc}s" begin="{2.5 + 0.45 * k:.2f}s" repeatCount="indefinite"/></rect>'
                f'<g transform="translate({x+22:.1f},{y+20})">{icon_use(ic["path"], ic["col"], 0.8333, 10.0)}</g>'
                f'<text class="jb" x="{x+41:.1f}" y="{y+24.5}" font-size="13" fill="#eceef6">{esc(ic["label"])}</text></g>')
            t += 0.06; k += 1
            x += w + 8.5
        if x - 8.5 > 1252:
            WARN.append(f"stack row '{c['name']}' is too wide — remove an item or shorten labels")
    bg = (f'</defs>\n<rect width="1280" height="480" rx="24" fill="url(#cardbg)"/>\n<rect width="1280" height="480" rx="24" fill="url(#dots3)"/>\n'
          '<rect x=".75" y=".75" width="1278.5" height="478.5" rx="23.25" fill="none" stroke="url(#edge)" stroke-width="1.5"/>\n'
          f'<g class="fu" style="animation-delay:.1s">\n  <text class="jbb" x="40" y="54" font-size="12.5" fill="#22d3ee" letter-spacing="2.2">// TECH STACK</text>\n'
          f'  <text class="sg" x="40" y="94" font-size="29" fill="#eceef6" letter-spacing="-.5">{esc(S["heading"])}</text>\n</g>\n'
          '<line x1="520" y1="120" x2="520" y2="440" stroke="#262a42" stroke-width="1"/>\n')
    defs = defs.replace("</defs>", "")
    return head + defs + bg + orbit_paths + "\n" + anim + core + chips + "\n</svg>\n"

# ----------------------------------------------------------------- README
def build_readme(stats, live):
    R = CFG["readme"]
    user = CFG["github_username"]
    uh = handle_of(user)
    email = CFG["connect"]["email"]
    alt = f"Hi, I'm {CFG['name']} — {CFG['title']}"
    rows = []
    for p in R["projects"]:
        nm = f"[**{p['name']}**]({p['url']})" if p.get("url") else f"**{p['name']}**"
        st = " ".join(f"`{s}`" for s in p["stack"])
        rows.append(f"| {nm} | {p['what']} | {st} | {p.get('stars', '—')} |")
    badges = []
    for b in R["badges"]:
        url = b["url"].format(username=uh, email=email)
        logo = f"&logo={b['logo']}" if b.get("logo") else ""
        badges.append(f'<a href="{url}"><img src="https://img.shields.io/badge/{b["label"]}-{b["color"]}?style=for-the-badge{logo}&logoColor=0d0e16" alt="{b["label"]}"/></a>')
    md = f"""<div align="center">

<!-- 🎬 HERO — video intro + name -->
<img src="./hero.svg?v=1" alt="{alt}" width="100%"/>

<br/><br/>

<!-- 👨‍💻 LEFT: what I build   •   RIGHT: life outside code -->
<img src="./about-life.svg?v=1" alt="What I build, and life beyond the code" width="100%"/>

<br/><br/>

<!-- ⚙️ TECH STACK -->
<img src="./stack.svg?v=1" alt="Tech stack" width="100%"/>

<br/><br/>

<!-- 🪪 DEVELOPER ID + DASHBOARD -->
<img src="./id-dashboard.svg?v=1" alt="Developer ID and dashboard" width="100%"/>

<br/><br/>

</div>

## {R['featured_heading']}

| Project | What it is | Stack | Stars |
|:---|:---|:---|:---:|
""" + "\n".join(rows) + f"""

<div align="center">

<br/>

## 🌃 My contribution city

*Every commit builds another tower — rebuilt automatically every day.*

<img src="./profile-3d-contrib/profile-night-view.svg" alt="3D contribution city" width="100%"/>

<br/><br/>

<!-- 💌 LET'S CONNECT -->
<img src="./connect.svg?v=1" alt="Let's connect" width="100%"/>

""" + "\n".join(badges) + f"""

<br/><br/>

<img src="https://komarev.com/ghpvc/?username={uh}&color=a78bfa&style=for-the-badge&label=PROFILE+VIEWS" alt="Profile views"/>

<br/>

{R['footer']}

</div>
"""
    return md

# ----------------------------------------------------------------- main
def write(name, content):
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"  wrote {name:<18} {len(content.encode())/1024:7.0f} KB")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-live", action="store_true", help="don't call the GitHub API")
    args = ap.parse_args()
    print("Building profile for", CFG["name"])
    stats, repos, live = github_stats(CFG["github_username"], not args.no_live)
    print(f"  github stats: {'LIVE' if live else 'from config.json'} -> {stats}")
    write("hero.svg", build_hero())
    write("about-life.svg", build_about())
    write("stack.svg", build_stack())
    write("id-dashboard.svg", build_dashboard(stats, repos, live))
    write("connect.svg", build_connect())
    write("README.md", build_readme(stats, live))
    if WARN:
        print("\nTo fix before publishing:")
        for w in dict.fromkeys(WARN):
            print("  •", w)
    print("\nDone. Open README.md preview or the .svg files in a browser to check them.")

if __name__ == "__main__":
    main()
