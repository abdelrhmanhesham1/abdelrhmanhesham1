#!/usr/bin/env python3
"""Generate the combined flight-path + real contribution-snake visualization.

The snake grid is the REAL, unmodified output of Platane/snk (github.com/
Platane/snk) -- this script does not reimplement or alter it in any way.
It is embedded as a nested <svg> (only `x`/`y` placement attributes are
added to its root tag; every byte of its internal markup, CSS, and
animation is untouched) directly below a flight-path visualization whose
plane flies at an altitude driven by each week's real contribution total,
aligned to snk's own real column positions (parsed from its actual output,
not assumed).

Design references (researched, not guessed):
- FlightRadar24: trail color encodes altitude -- applied as a per-segment
  gradient along the flight path, colored by that week's contribution volume.
- Primary Flight Display (PFD): a vertical altitude tape with tick marks.
"""
import json
import os
import re
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
            local_t = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            r0 = hex_to_rgb(c0)
            r1 = hex_to_rgb(c1)
            return rgb_to_hex([r0[j] + (r1[j] - r0[j]) * local_t for j in range(3)])
    return stops[-1][1]


THEMES = {
    "dark": {
        "bg": "#0A1128",
        "bg2": "#0D1638",
        "fg": "#F3F7FC",
        "muted": "#7C8BAE",
        "altitude_stops": [(0.0, "#1B3A6B"), (0.45, "#06B6D4"), (0.75, "#22D3EE"), (1.0, "#A78BFA")],
        "tape_line": "#2A4A80",
        "plane_fill": "#F3F7FC",
        "plane_stroke": "#22D3EE",
        "marker": "#FF8A3D",
    },
    "light": {
        "bg": "#F3F7FC",
        "bg2": "#EBF1FA",
        "fg": "#0A1128",
        "muted": "#5B6B8C",
        "altitude_stops": [(0.0, "#8CA3C7"), (0.45, "#06B6D4"), (0.75, "#22D3EE"), (1.0, "#7C3AED")],
        "tape_line": "#C7D2E5",
        "plane_fill": "#0A1128",
        "plane_stroke": "#06B6D4",
        "marker": "#F4572E",
    },
}

TAPE_W = 34
SKY_H = 118
SKY_TOP_PAD = 20

PLANE_PATH = (
    "M 11,0 L 4,1.6 L -3,11 L -5.2,11 L -2,1.8 L -9,2.6 L -11.5,6 L -13,6 "
    "L -10.8,0 L -13,-6 L -11.5,-6 L -9,-2.6 L -2,-1.8 L -5.2,-11 L -3,-11 "
    "L 4,-1.6 Z"
)


def parse_snake_svg(path):
    """Read the real, unmodified Platane/snk output and pull out only its
    layout facts (viewBox, width, height, real column x-positions) -- the
    markup itself (style/rects/animations) is never touched, only wrapped."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    m = re.search(r'<svg[^>]*\bviewBox="([^"]+)"[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', content)
    if not m:
        m2 = re.search(r'<svg[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"[^>]*\bviewBox="([^"]+)"', content)
        width, height, viewbox = int(m2.group(1)), int(m2.group(2)), m2.group(3)
    else:
        viewbox, width, height = m.group(1), int(m.group(2)), int(m.group(3))

    min_x = float(viewbox.split()[0])

    xs = sorted(set(int(v) for v in re.findall(r'<rect class="c[^"]*" x="(\d+)"', content)))

    return {
        "raw": content,
        "width": width,
        "height": height,
        "viewbox": viewbox,
        "min_x": min_x,
        "columns": xs,
    }


def embed_snake(raw_svg_content, x, y):
    """Add ONLY x/y placement attributes to the snk SVG's own root tag so it
    can sit inside a larger canvas -- no other byte of it is changed."""
    return re.sub(r"<svg ", f'<svg x="{x}" y="{y}" ', raw_svg_content, count=1)


def build_svg(calendar, theme_name, snake_info):
    theme = THEMES[theme_name]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    n_weeks = len(weeks)

    columns = snake_info["columns"]
    if len(columns) != n_weeks:
        # Fall back to evenly spaced columns if snk's week count ever
        # differs from the GraphQL calendar's (shouldn't happen in practice
        # since both derive from the same real contribution history).
        columns = [columns[0] + i * 16 for i in range(n_weeks)] if columns else [i * 16 for i in range(n_weeks)]

    # snk's own rendered pixel x for column i is (raw_x - min_x); that's
    # exactly where the plane must fly to stay above the real column.
    col_px = [c - snake_info["min_x"] for c in columns]

    snake_w = snake_info["width"]
    snake_h = snake_info["height"]
    width = snake_w + TAPE_W + 10
    sky_top = SKY_TOP_PAD
    sky_bottom = sky_top + SKY_H
    height = sky_bottom + snake_h

    week_totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    max_week_total = max(week_totals) if week_totals else 1
    peak_week_idx = week_totals.index(max_week_total)

    # ---------- flight path control points, aligned to snk's real columns ----------
    points = []
    for wi, wtotal in enumerate(week_totals):
        x = col_px[wi] + 6  # +6 = to the center of a 12px-wide snk cell
        ratio = wtotal / max_week_total if max_week_total else 0
        y = sky_bottom - ratio * (sky_bottom - sky_top)
        points.append((x, y, ratio))

    def smooth_path(pts):
        p = [(x, y) for x, y, _ in pts]
        d = f"M {p[0][0]:.1f} {p[0][1]:.1f} "
        for i in range(len(p) - 1):
            x0, y0 = p[i]
            x1, y1 = p[i + 1]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            d += f"Q {x0:.1f} {y0:.1f} {mx:.1f} {my:.1f} "
        d += f"T {p[-1][0]:.1f} {p[-1][1]:.1f}"
        return d

    full_path_d = smooth_path(points)

    trail_segments = []
    for i in range(1, len(points)):
        x0, y0, _ = points[i - 1]
        x1, y1, r1 = points[i]
        color = lerp_color(theme["altitude_stops"], r1)
        trail_segments.append(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" opacity="0.9"/>'
        )

    dots = []
    for i, (x, y, r) in enumerate(points):
        if i % 4 == 0 or i == len(points) - 1:
            color = lerp_color(theme["altitude_stops"], r)
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{color}"/>')

    path_length = sum(
        ((points[i][0] - points[i - 1][0]) ** 2 + (points[i][1] - points[i - 1][1]) ** 2) ** 0.5
        for i in range(1, len(points))
    )
    duration = max(16, min(30, round(path_length / 32)))

    # ---------- altitude tape (PFD-style vertical scale), to the right of the snake grid ----------
    tape_x = snake_w + 4
    tape_ticks = []
    n_ticks = 5
    for i in range(n_ticks + 1):
        frac = i / n_ticks
        y = sky_bottom - frac * (sky_bottom - sky_top)
        label_val = round(frac * max_week_total)
        tick_len = 8 if i in (0, n_ticks, n_ticks // 2) else 5
        tape_ticks.append(
            f'<line x1="{tape_x}" y1="{y:.1f}" x2="{tape_x + tick_len}" y2="{y:.1f}" '
            f'stroke="{theme["tape_line"]}" stroke-width="1"/>'
        )
        if i in (0, n_ticks):
            tape_ticks.append(
                f'<text x="{tape_x + 11}" y="{y + 3:.1f}" font-size="8" '
                f'fill="{theme["muted"]}">{label_val}</text>'
            )
    tape_ticks.append(
        f'<line x1="{tape_x}" y1="{sky_top}" x2="{tape_x}" y2="{sky_bottom}" '
        f'stroke="{theme["tape_line"]}" stroke-width="1"/>'
    )
    tape_label = (
        f'<text x="{tape_x + 11}" y="{sky_top - 6}" font-size="7.5" fill="{theme["muted"]}">commits</text>'
        f'<text x="{tape_x + 11}" y="{sky_top + 4}" font-size="7.5" fill="{theme["muted"]}">/week</text>'
    )

    start_x, start_y, _ = points[0]
    cur_x, cur_y, _ = points[-1]
    start_marker = (
        f'<g transform="translate({start_x:.1f},{sky_bottom + 4:.1f})">'
        f'<line x1="0" y1="-9" x2="0" y2="0" stroke="{theme["muted"]}" stroke-width="1" stroke-dasharray="2 2"/>'
        f'<circle r="2" fill="none" stroke="{theme["muted"]}" stroke-width="1"/>'
        f'</g>'
        f'<text x="{start_x - 8:.1f}" y="{sky_bottom + 18:.1f}" font-size="7.5" fill="{theme["muted"]}">start</text>'
    )
    current_marker = (
        f'<g transform="translate({cur_x:.1f},{cur_y:.1f})">'
        f'<circle r="7" fill="{theme["marker"]}" opacity="0.18"/>'
        f'<circle r="3.2" fill="{theme["marker"]}"/>'
        f'</g>'
        f'<text x="{cur_x - 10:.1f}" y="{sky_top - 6:.1f}" font-size="8" fill="{theme["marker"]}">now</text>'
    )

    peak_x, peak_y, _ = points[peak_week_idx]
    peak_callout = (
        f'<text x="{peak_x:.1f}" y="{peak_y - 8:.1f}" font-size="8" text-anchor="middle" '
        f'fill="{theme["fg"]}" opacity="0.9">{max_week_total} in one week</text>'
    )

    hud = f'''
    <g transform="translate(6,{sky_top - 12})">
      <text x="0" y="0" font-size="9" letter-spacing="1.5" fill="{theme["muted"]}">TOTAL CONTRIBUTIONS</text>
      <text x="0" y="12" font-size="15" font-weight="600" fill="{theme["fg"]}">{total}</text>
    </g>
    '''

    plane_g = (
        f'<defs><g id="plane">'
        f'<path d="{PLANE_PATH}" fill="{theme["plane_fill"]}" stroke="{theme["plane_stroke"]}" stroke-width="0.6"/>'
        f'</g></defs>'
    )

    embedded_snake = embed_snake(snake_info["raw"], 0, sky_bottom)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>text {{ font-family: "Segoe UI", "Ubuntu", Helvetica, Arial, sans-serif; }}</style>
  <rect width="{width}" height="{height}" fill="{theme['bg']}"/>
  <rect x="0" y="0" width="{width}" height="{sky_bottom}" fill="{theme['bg2']}"/>

  {hud}
  {tape_label}
  {''.join(tape_ticks)}

  {''.join(trail_segments)}
  {''.join(dots)}
  {peak_callout}
  {start_marker}
  {current_marker}

  {plane_g}
  <use href="#plane">
    <animateMotion dur="{duration}s" repeatCount="indefinite" rotate="auto" path="{full_path_d}"/>
  </use>

  {embedded_snake}
</svg>'''
    return svg


def main():
    calendar = fetch_calendar(USERNAME)
    out_dir = "flight-path"
    os.makedirs(out_dir, exist_ok=True)

    snake_files = {
        "dark": os.environ.get("SNAKE_DARK_PATH", "dist/snake-dark.svg"),
        "light": os.environ.get("SNAKE_LIGHT_PATH", "dist/snake.svg"),
    }

    for theme_name in ("dark", "light"):
        snake_info = parse_snake_svg(snake_files[theme_name])
        svg = build_svg(calendar, theme_name, snake_info)
        path = os.path.join(out_dir, f"flight-path-{theme_name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
