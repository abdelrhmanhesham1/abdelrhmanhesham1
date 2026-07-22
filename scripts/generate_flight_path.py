#!/usr/bin/env python3
"""Generate an aviation-themed contribution visualization: a dashed flight
path flies above the real contribution grid, with altitude driven by each
week's actual contribution total (busier weeks -> higher altitude).
"""
import json
import os
import sys
import urllib.request

USERNAME = os.environ.get("USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
TOKEN = os.environ["GITHUB_TOKEN"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_calendar(login):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "flight-path-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level_for_count(count, max_count):
    if count == 0:
        return 0
    if max_count <= 1:
        return 4
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


THEMES = {
    "dark": {
        "bg": "#0A1128",
        "fg": "#F3F7FC",
        "grid_colors": ["#12204A", "#1B3A6B", "#06B6D4", "#22D3EE", "#A78BFA"],
        "path_color": "#22D3EE",
        "plane_color": "#F3F7FC",
        "glow_color": "#A78BFA",
    },
    "light": {
        "bg": "#F3F7FC",
        "fg": "#0A1128",
        "grid_colors": ["#E4EAF3", "#B8C7DE", "#06B6D4", "#22D3EE", "#7C3AED"],
        "path_color": "#7C3AED",
        "plane_color": "#0A1128",
        "glow_color": "#06B6D4",
    },
}

CELL = 11
GAP = 3
STEP = CELL + GAP
MARGIN_X = 20
MARGIN_TOP = 90  # sky band height for the flight path
MARGIN_BOTTOM = 20


def build_svg(weeks, theme_name):
    theme = THEMES[theme_name]
    n_weeks = len(weeks)
    grid_w = n_weeks * STEP - GAP
    width = grid_w + MARGIN_X * 2
    grid_h = 7 * STEP - GAP
    height = MARGIN_TOP + grid_h + MARGIN_BOTTOM

    all_counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    max_count = max(all_counts) if all_counts else 1

    week_totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    max_week_total = max(week_totals) if week_totals else 1

    # --- grid of contribution squares ---
    rects = []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            level = level_for_count(day["contributionCount"], max_count)
            color = theme["grid_colors"][level]
            x = MARGIN_X + wi * STEP
            y = MARGIN_TOP + di * STEP
            rects.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}">'
                f'<title>{day["date"]}: {day["contributionCount"]} contributions</title></rect>'
            )

    # --- flight path control points: one per week, altitude by week activity ---
    sky_top = 18
    sky_bottom = MARGIN_TOP - 14
    points = []
    for wi, total in enumerate(week_totals):
        x = MARGIN_X + wi * STEP + CELL / 2
        ratio = total / max_week_total if max_week_total else 0
        y = sky_bottom - ratio * (sky_bottom - sky_top)
        points.append((x, y))

    # smooth-ish path using quadratic mid-point smoothing
    d = f"M {points[0][0]:.1f} {points[0][1]:.1f} "
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        d += f"Q {x0:.1f} {y0:.1f} {mx:.1f} {my:.1f} "
    d += f"T {points[-1][0]:.1f} {points[-1][1]:.1f}"

    path_length = sum(
        ((points[i][0] - points[i - 1][0]) ** 2 + (points[i][1] - points[i - 1][1]) ** 2) ** 0.5
        for i in range(1, len(points))
    )
    duration = max(14, min(28, round(path_length / 40)))

    plane_defs = (
        '<defs><g id="plane">'
        '<path d="M 0 -6 L 4 4 L 0 2 L -4 4 Z" fill="{c}"/>'
        '</g></defs>'
    ).format(c=theme["plane_color"])

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    text {{ font-family: "Segoe UI", "Ubuntu", Helvetica, Arial, sans-serif; }}
  </style>
  <rect width="{width}" height="{height}" fill="{theme['bg']}"/>
  <text x="{MARGIN_X}" y="16" font-size="12" fill="{theme['fg']}" opacity="0.85">Weekly activity, flown</text>

  <path id="flightpath" d="{d}" fill="none" stroke="{theme['path_color']}" stroke-width="1.6"
        stroke-dasharray="5 5" stroke-linecap="round" opacity="0.85">
    <animate attributeName="stroke-dashoffset" from="1000" to="0" dur="{duration}s" repeatCount="indefinite"/>
  </path>

  {plane_defs}
  <use href="#plane">
    <animateMotion dur="{duration}s" repeatCount="indefinite" rotate="auto">
      <mpath href="#flightpath"/>
    </animateMotion>
  </use>

  {''.join(rects)}
</svg>'''
    return svg


def main():
    calendar = fetch_calendar(USERNAME)
    weeks = calendar["weeks"]
    out_dir = "flight-path"
    os.makedirs(out_dir, exist_ok=True)
    for theme_name in ("dark", "light"):
        svg = build_svg(weeks, theme_name)
        path = os.path.join(out_dir, f"flight-path-{theme_name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
