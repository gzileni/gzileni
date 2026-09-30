#!/usr/bin/env python3
"""Generate self-hosted GitHub stats cards (SVG) in the Claude palette.

Requires GITHUB_TOKEN (or `gh auth token`) and USERNAME env vars.
Set STATS_TOKEN (a PAT with read:user) to include private contributions.
"""
import datetime as dt
import json
import os
import subprocess
import urllib.request
from html import escape

USER = os.environ.get("USERNAME", "gzileni")
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")

CREAM, CORAL, INK, MUTED, SAND = "#F0EEE6", "#D97757", "#191919", "#6B6757", "#E3DFD0"
FONT = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

# Notebooks, markup and build/config files would skew the language breakdown
EXCLUDE_LANGS = {"Jupyter Notebook", "HTML", "CSS", "SCSS", "Dockerfile", "Makefile", "Shell"}

QUERY = """
query($login:String!){
  user(login:$login){
    followers{totalCount}
    pullRequests{totalCount}
    issues{totalCount}
    repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){totalCount}
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}
    }
    repositories(ownerAffiliations:OWNER,isFork:false,first:100,privacy:PUBLIC){
      totalCount
      nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}
    }
  }
}"""


def token():
    t = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return t or subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


def svg(w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="14" fill="{CREAM}" stroke="{CORAL}" stroke-width="2"/>'
        f"{body}</svg>"
    )


def title(text):
    return f'<text x="28" y="40" font-family="{FONT}" font-size="18" font-weight="600" fill="{CORAL}">{escape(text)}</text>'


def write(name, content):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(content)


def days_of(u):
    cal = u["contributionsCollection"]["contributionCalendar"]
    return [d for w in cal["weeks"] for d in w["contributionDays"]]


def streaks(days):
    today = dt.date.today().isoformat()
    days = [d for d in days if d["date"] <= today]
    best = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        best = max(best, run)
    cur = 0
    for d in reversed(days):
        if d["contributionCount"]:
            cur += 1
        elif d["date"] != today:  # today may still be empty
            break
    return cur, best


def stats_card(u):
    cc = u["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in u["repositories"]["nodes"])
    rows = [
        ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
        ("Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("Pull requests", u["pullRequests"]["totalCount"]),
        ("Issues", u["issues"]["totalCount"]),
        ("Stars earned", stars),
        ("Public repos", u["repositories"]["totalCount"]),
        ("Contributed to", u["repositoriesContributedTo"]["totalCount"]),
        ("Followers", u["followers"]["totalCount"]),
    ]
    body = title("GitHub Stats")
    for i, (label, val) in enumerate(rows):
        y = 76 + i * 28
        body += (
            f'<circle cx="34" cy="{y-5}" r="4" fill="{CORAL}"/>'
            f'<text x="48" y="{y}" font-family="{FONT}" font-size="14" fill="{MUTED}">{label}</text>'
            f'<text x="372" y="{y}" text-anchor="end" font-family="{MONO}" font-size="15" font-weight="700" fill="{INK}">{val:,}</text>'
        )
    write("stats.svg", svg(400, 76 + len(rows) * 28, body))


def langs_card(u):
    totals, colors = {}, {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n in EXCLUDE_LANGS:
                continue
            totals[n] = totals.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or MUTED
    top = sorted(totals.items(), key=lambda x: -x[1])[:6]
    total = sum(v for _, v in top) or 1
    body = title("Top Languages")
    x, bar_w = 28, 344
    body += f'<clipPath id="c"><rect x="{x}" y="58" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#c)">'
    for n, v in top:
        w = bar_w * v / total
        body += f'<rect x="{x:.1f}" y="58" width="{w:.1f}" height="10" fill="{colors[n]}"/>'
        x += w
    body += "</g>"
    for i, (n, v) in enumerate(top):
        cx, cy = 28 + (i % 2) * 176, 100 + (i // 2) * 28
        body += (
            f'<circle cx="{cx+5}" cy="{cy-5}" r="5" fill="{colors[n]}"/>'
            f'<text x="{cx+18}" y="{cy}" font-family="{FONT}" font-size="14" fill="{INK}">{escape(n)}'
            f'<tspan fill="{MUTED}" dx="6">{100*v/total:.1f}%</tspan></text>'
        )
    rows = (len(top) + 1) // 2
    write("langs.svg", svg(400, 100 + rows * 28 - 4, body))


def streak_card(u):
    days = days_of(u)
    cur, best = streaks(days)
    total = sum(d["contributionCount"] for d in days)
    cols = [(total, "Total contributions"), (cur, "Current streak (days)"), (best, "Longest streak (days)")]
    body = ""
    for i, (val, label) in enumerate(cols):
        cx = 100 + i * 200
        big = CORAL if i == 1 else INK
        body += (
            f'<text x="{cx}" y="80" text-anchor="middle" font-family="{MONO}" font-size="38" font-weight="700" fill="{big}">{val:,}</text>'
            f'<text x="{cx}" y="108" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{MUTED}">{label}</text>'
        )
        if i:
            body += f'<line x1="{cx-100}" y1="48" x2="{cx-100}" y2="118" stroke="{SAND}" stroke-width="2"/>'
    write("streak.svg", svg(600, 160, body + f'<text x="300" y="146" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Streaks measured over the last 12 months · updated {dt.date.today().isoformat()}</text>'))


def activity_card(u):
    days = days_of(u)[-31:]
    peak = max(d["contributionCount"] for d in days) or 1
    w, h, x0, base, top = 600, 220, 28, 172, 66
    step = (w - 2 * x0) / len(days)
    body = title("Activity — last 31 days")
    for i, d in enumerate(days):
        bh = max(3, (base - top) * d["contributionCount"] / peak)
        fill = CORAL if d["contributionCount"] else SAND
        body += f'<rect x="{x0+i*step+2:.1f}" y="{base-bh:.1f}" width="{step-4:.1f}" height="{bh:.1f}" rx="3" fill="{fill}"><title>{d["date"]}: {d["contributionCount"]}</title></rect>'
    body += (
        f'<text x="{x0}" y="196" font-family="{FONT}" font-size="11" fill="{MUTED}">{days[0]["date"]}</text>'
        f'<text x="{w-x0}" y="196" text-anchor="end" font-family="{FONT}" font-size="11" fill="{MUTED}">{days[-1]["date"]} · peak {peak}/day</text>'
    )
    write("activity.svg", svg(w, h, body))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    user = fetch()
    stats_card(user), langs_card(user), streak_card(user), activity_card(user)
    print("generated: stats, langs, streak, activity")
