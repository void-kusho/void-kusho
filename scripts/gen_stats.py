#!/usr/bin/env python3
"""Render Tokyo Night stats SVGs from the GitHub API.

Writes img/stats.svg and img/activity.svg. No third-party service involved:
if GitHub is up, the profile renders.

Usage:  GH_TOKEN=$(gh auth token) python3 scripts/gen_stats.py
"""
import json, os, sys, urllib.request
from datetime import datetime
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "void-kusho")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GH_TOKEN or GITHUB_TOKEN required")

# Tokyo Night
BG, PANEL, LINE = "#1a1b26", "#16161e", "#292e42"
FG, DIM, ACCENT = "#c0caf5", "#565f89", "#7aa2f7"
MONO = '"Fira Code","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'

QUERY = """
{ user(login: "%s") {
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes { name isArchived stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } } } } }
    contributionsCollection { contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } } } } } }
""" % USER


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Authorization": f"bearer {TOKEN}",
                 "Content-Type": "application/json",
                 "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit("GraphQL error: %s" % body["errors"])
    return body["data"]["user"]


# linguist counts these, but they are vendored man pages and build glue, not work
NOISE = {"Roff", "Makefile", "M4", "Batchfile", "CMake", "Dockerfile", "Vim Script"}


def collect(u):
    repos = u["repositories"]["nodes"]
    live = [r for r in repos if not r["isArchived"]]
    langs = {}
    for r in live:                      # archived repos excluded: they are not current work
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name in NOISE:
                continue
            langs[name] = langs.get(name, 0) + e["size"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    return {
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "contribs": cal["totalContributions"],
        "langs": sorted(langs.items(), key=lambda x: -x[1])[:6],
        "lang_total": sum(langs.values()) or 1,
        "weeks": cal["weeks"],
    }


def stats_svg(d):
    W, H = 860, 230
    metrics = [("repositories", d["repos"]), ("followers", d["followers"]),
               ("contributions", d["contribs"]), ("stars", d["stars"])]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'role="img" aria-label="github stats">',
         f'<style>.m{{font-family:{MONO}}}</style>',
         f'<rect width="{W}" height="{H}" rx="10" fill="{BG}" stroke="{LINE}" stroke-width="1"/>']
    for i, (label, val) in enumerate(metrics):
        x = 28 + i * 208
        o.append(f'<text class="m" x="{x}" y="58" fill="{ACCENT}" font-size="30">{val}</text>')
        o.append(f'<text class="m" x="{x}" y="78" fill="{DIM}" font-size="11" letter-spacing="1.1">{label}</text>')
    o.append(f'<line x1="28" y1="100" x2="{W-28}" y2="100" stroke="{LINE}" stroke-width="1"/>')
    o.append(f'<text class="m" x="28" y="126" fill="{DIM}" font-size="11" letter-spacing="1.2">TOP LANGUAGES</text>')
    # one stacked bar, accent at stepped opacity (keeps the single-accent rule)
    bx, bw, by = 28, W - 56, 140
    cur = 0.0
    for i, (name, size) in enumerate(d["langs"]):
        frac = size / d["lang_total"]
        w = frac * bw
        op = round(1.0 - i * 0.14, 2)
        o.append(f'<rect x="{bx+cur:.1f}" y="{by}" width="{max(w-2,1):.1f}" height="14" rx="2" '
                 f'fill="{ACCENT}" opacity="{op}"/>')
        cur += w
    for i, (name, size) in enumerate(d["langs"]):
        pct = size * 100.0 / d["lang_total"]
        x = 28 + (i % 3) * 272
        y = 182 + (i // 3) * 20
        op = round(1.0 - i * 0.14, 2)
        o.append(f'<rect x="{x}" y="{y-9}" width="9" height="9" rx="2" fill="{ACCENT}" opacity="{op}"/>')
        o.append(f'<text class="m" x="{x+16}" y="{y}" fill="{FG}" font-size="12">{escape(name)}'
                 f'<tspan fill="{DIM}">  {pct:.1f}%</tspan></text>')
    o.append("</svg>")
    return "\n".join(o)


def activity_svg(d):
    W, H = 860, 190
    pad_l, pad_r, pad_t, pad_b = 28, 28, 46, 30
    weeks = [sum(x["contributionCount"] for x in w["contributionDays"]) for w in d["weeks"]]
    weeks = weeks[-52:] or [0]
    peak = max(weeks) or 1
    gw, gh = W - pad_l - pad_r, H - pad_t - pad_b
    step = gw / max(len(weeks) - 1, 1)
    pts = [(pad_l + i * step, pad_t + gh - (v / peak) * gh) for i, v in enumerate(weeks)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = line + f" L{pts[-1][0]:.1f},{pad_t+gh} L{pts[0][0]:.1f},{pad_t+gh} Z"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'role="img" aria-label="contribution activity">',
         f'<style>.m{{font-family:{MONO}}}</style>',
         f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.38"/>'
         f'<stop offset="100%" stop-color="{ACCENT}" stop-opacity="0.02"/></linearGradient></defs>',
         f'<rect width="{W}" height="{H}" rx="10" fill="{BG}" stroke="{LINE}" stroke-width="1"/>',
         f'<text class="m" x="28" y="30" fill="{DIM}" font-size="11" letter-spacing="1.2">'
         f'CONTRIBUTION ACTIVITY<tspan fill="{ACCENT}">  {d["contribs"]}</tspan>'
         f'<tspan fill="{DIM}"> in the last year · peak {peak}/wk</tspan></text>']
    for f in (0.0, 0.5, 1.0):
        y = pad_t + gh * f
        o.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W-pad_r}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
    o.append(f'<path d="{area}" fill="url(#g)"/>')
    o.append(f'<path d="{line}" fill="none" stroke="{ACCENT}" stroke-width="2" '
             f'stroke-linejoin="round" stroke-linecap="round"/>')
    o.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="{ACCENT}"/>')
    o.append(f'<text class="m" x="{pad_l}" y="{H-10}" fill="{DIM}" font-size="10">52 weeks ago</text>')
    o.append(f'<text class="m" x="{W-pad_r}" y="{H-10}" fill="{DIM}" font-size="10" text-anchor="end">today</text>')
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    d = collect(fetch())
    os.makedirs("img", exist_ok=True)
    for name, svg in (("img/stats.svg", stats_svg(d)), ("img/activity.svg", activity_svg(d))):
        open(name, "w", encoding="utf-8").write(svg + "\n")
        print("wrote", name)
    print(f"repos={d['repos']} followers={d['followers']} contribs={d['contribs']} "
          f"stars={d['stars']} langs={[l[0] for l in d['langs']]}")
