#!/usr/bin/env python3
"""Generate an ATC-radar-scope visualization of the contribution calendar.

Design: real air-traffic-control radar scopes show concentric range rings,
a continuously rotating sweep beam, and blips at each contact's bearing/
range. Here, each day of the year is a "contact": angle = day-of-year
(so one full sweep = one year, Jan at 12 o'clock going clockwise), and
each day's position spirals outward from center (Jan) to the rim (most
recent day) so the whole year is visible at once with no overlap. Blip
size/brightness = that day's actual contribution count.
"""
import json
import math
import os
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
            "User-Agent": "radar-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


THEMES = {
    "dark": {
        "bg": "#0A1128",
        "ring": "#1B3A6B",
        "ring_bright": "#22D3EE",
        "fg": "#F3F7FC",
        "muted": "#7C8BAE",
        "sweep": "#22D3EE",
        "blip_stops": [(0.0, "#12204A"), (0.35, "#1B3A6B"), (0.6, "#06B6D4"), (0.85, "#22D3EE"), (1.0, "#A78BFA")],
    },
    "light": {
        "bg": "#F3F7FC",
        "ring": "#C7D2E5",
        "ring_bright": "#06B6D4",
        "fg": "#0A1128",
        "muted": "#5B6B8C",
        "sweep": "#7C3AED",
        "blip_stops": [(0.0, "#E4EAF3"), (0.35, "#B8C7DE"), (0.6, "#06B6D4"), (0.85, "#22D3EE"), (1.0, "#7C3AED")],
    },
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, round(c))) for c in rgb])


def lerp_color(stops, t):
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            lt = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            r0, r1 = hex_to_rgb(c0), hex_to_rgb(c1)
            return rgb_to_hex([r0[j] + (r1[j] - r0[j]) * lt for j in range(3)])
    return stops[-1][1]


SIZE = 460
CX = SIZE / 2
CY = SIZE / 2
R_MIN = 34
R_MAX = 205


def build_svg(calendar, theme_name):
    theme = THEMES[theme_name]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]

    days = [d for w in weeks for d in w["contributionDays"]]
    n = len(days)
    max_count = max((d["contributionCount"] for d in days), default=1) or 1

    # range rings
    rings = []
    n_rings = 4
    for i in range(1, n_rings + 1):
        r = R_MIN + (R_MAX - R_MIN) * i / n_rings
        rings.append(f'<circle cx="{CX}" cy="{CY}" r="{r:.1f}" fill="none" stroke="{theme["ring"]}" stroke-width="1" opacity="0.55"/>')

    # crosshair spokes every 30 degrees (like a real radar scope)
    spokes = []
    for deg in range(0, 360, 30):
        rad = math.radians(deg - 90)
        x1, y1 = CX + R_MIN * math.cos(rad), CY + R_MIN * math.sin(rad)
        x2, y2 = CX + R_MAX * math.cos(rad), CY + R_MAX * math.sin(rad)
        spokes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{theme["ring"]}" stroke-width="0.6" opacity="0.35"/>')

    # month labels around the outer rim -- positioned at each REAL month
    # boundary found in the actual data (the calendar is a rolling 365-day
    # window ending today, not aligned to Jan-Dec, so a fixed 12-tick ring
    # would be wrong unless today happened to be exactly one year after Jan 1)
    month_abbr = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    month_labels = []
    last_month = None
    for i, d in enumerate(days):
        month = int(d["date"].split("-")[1])
        if month != last_month:
            frac = i / max(1, n - 1)
            deg = frac * 360
            rad = math.radians(deg - 90)
            r = R_MAX + 16
            x, y = CX + r * math.cos(rad), CY + r * math.sin(rad)
            month_labels.append(
                f'<text x="{x:.1f}" y="{y:.1f}" font-size="8" letter-spacing="1" '
                f'fill="{theme["muted"]}" text-anchor="middle" dominant-baseline="middle">{month_abbr[month - 1]}</text>'
            )
            last_month = month

    # spiral blips: angle = day-of-year fraction * 360 (Jan at top, clockwise);
    # radius = same fraction, spiraling outward so the year reads start->rim with no overlap
    blips = []
    last_x = last_y = None
    for i, d in enumerate(days):
        frac = i / max(1, n - 1)
        deg = frac * 360
        rad = math.radians(deg - 90)
        r = R_MIN + frac * (R_MAX - R_MIN)
        x, y = CX + r * math.cos(rad), CY + r * math.sin(rad)
        count = d["contributionCount"]
        level = count / max_count if max_count else 0
        color = lerp_color(theme["blip_stops"], level)
        radius = 1.1 + level * 3.2
        if count > 0:
            blips.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" opacity="0.92">'
                f'<title>{d["date"]}: {count} contributions</title></circle>'
            )
        last_x, last_y = x, y

    # sweep beam: a soft wedge that continuously rotates, classic ATC scan effect
    sweep_id = "sweepGrad"
    sweep_gradient = f'''
    <radialGradient id="{sweep_id}" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse"
        gradientTransform="translate({CX} {CY}) rotate(0) scale({R_MAX})">
      <stop offset="0" stop-color="{theme['sweep']}" stop-opacity="0.35"/>
      <stop offset="1" stop-color="{theme['sweep']}" stop-opacity="0"/>
    </radialGradient>
    '''
    sweep_wedge_path = (
        f'M {CX:.1f} {CY:.1f} '
        f'L {CX:.1f} {CY - R_MAX:.1f} '
        f'A {R_MAX} {R_MAX} 0 0 1 {CX + R_MAX * math.sin(math.radians(38)):.1f} '
        f'{CY - R_MAX * math.cos(math.radians(38)):.1f} Z'
    )

    # current-position marker at the rim (today)
    now_deg = (n - 1) / max(1, n - 1) * 360
    now_rad = math.radians(now_deg - 90)
    now_r = R_MAX
    now_x, now_y = CX + now_r * math.cos(now_rad), CY + now_r * math.sin(now_rad)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">
  <style>text {{ font-family: "Segoe UI", "Ubuntu", Helvetica, Arial, sans-serif; }}</style>
  <defs>{sweep_gradient}</defs>
  <rect width="{SIZE}" height="{SIZE}" fill="{theme['bg']}"/>

  <g>
    <path d="{sweep_wedge_path}" fill="url(#{sweep_id})">
      <animateTransform attributeName="transform" type="rotate"
        from="0 {CX} {CY}" to="360 {CX} {CY}" dur="10s" repeatCount="indefinite"/>
    </path>
  </g>

  {''.join(spokes)}
  {''.join(rings)}
  <circle cx="{CX}" cy="{CY}" r="{R_MAX}" fill="none" stroke="{theme['ring_bright']}" stroke-width="1.2" opacity="0.7"/>

  {''.join(blips)}

  <circle cx="{now_x:.1f}" cy="{now_y:.1f}" r="4" fill="{theme['sweep']}"/>
  <circle cx="{now_x:.1f}" cy="{now_y:.1f}" r="8" fill="{theme['sweep']}" opacity="0.25">
    <animate attributeName="r" values="6;12;6" dur="2s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="0.35;0.05;0.35" dur="2s" repeatCount="indefinite"/>
  </circle>

  {''.join(month_labels)}

  <text x="{CX}" y="{CY - 8}" font-size="9" letter-spacing="1.5" fill="{theme['muted']}" text-anchor="middle">CONTACTS</text>
  <text x="{CX}" y="{CY + 12}" font-size="20" font-weight="600" fill="{theme['fg']}" text-anchor="middle">{total}</text>
</svg>'''
    return svg


def main():
    calendar = fetch_calendar(USERNAME)
    out_dir = "radar"
    os.makedirs(out_dir, exist_ok=True)
    for theme_name in ("dark", "light"):
        svg = build_svg(calendar, theme_name)
        path = os.path.join(out_dir, f"radar-{theme_name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
