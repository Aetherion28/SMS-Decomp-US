#!/usr/bin/env python3
"""Draw a progress treemap (like the one on decomp.dev) from the objdiff report.

Every box is one translation unit, sized by its code size.
  green      every function in the unit matches
  blue       partly matched; brighter means a higher fuzzy match
  dark grey  nothing decompiled yet (0% fuzzy)

Units are grouped by category (game, JSystem, SDK) and then by folder.
The script also refreshes the progress numbers in README.md between the
<!-- progress:start --> and <!-- progress:end --> markers.

It also writes assets/progress.html, the clickable version of the
map (saved independently in this repository and linked from README.md).

Usage: python3 tools/progress_treemap.py [report.json] [out.svg]
Run `ninja` first so build/GMSE01/report.json is current.
"""

import datetime
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "build", "GMSE01", "report.json")
OUT = os.path.join(ROOT, "assets", "progress.svg")
README = os.path.join(ROOT, "README.md")
PAGE_TEMPLATE = os.path.join(ROOT, "tools", "progress_page.html")
PAGE_OUT = os.path.join(ROOT, "assets", "progress.html")
DEMANGLE_CACHE = os.path.join(ROOT, "build", "progress", "demangle_cache.json")
DTK = os.path.join(ROOT, "build", "tools", "dtk.exe" if os.name == "nt" else "dtk")
REPO_URL = "https://github.com/Aetherion28/SMS-AI-Decomp-US"

W, H = 1000, 500
GREEN = (0, 200, 0)
BLUE = (0, 112, 192)
GREY = (52, 52, 52)


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def colour(unit):
    m = unit["measures"]
    total = int(m.get("total_code", 0) or 0)
    matched = int(m.get("matched_code", 0) or 0)
    fuzzy = m.get("fuzzy_match_percent", 0) or 0
    if total and matched >= total:
        return GREEN
    if fuzzy <= 0:
        return GREY
    # most units sit above 80% fuzzy, so stretch that range
    return mix(GREY, BLUE, 0.35 + 0.65 * (fuzzy / 100.0) ** 3)


# --- squarified treemap (Bruls, Huizing, van Wijk) ---------------------------


def worst(row, side):
    s = sum(a for a, _ in row)
    if s <= 0 or side <= 0:
        return float("inf")
    big = max(a for a, _ in row)
    small = min(a for a, _ in row)
    return max(side * side * big / (s * s), (s * s) / (side * side * small))


def layout_row(row, x, y, w, h):
    s = sum(a for a, _ in row)
    out = []
    if w >= h:  # lay the row out as a column on the left
        cw = s / h if h else 0
        cy = y
        for a, item in row:
            ch = a / cw if cw else 0
            out.append((item, x, cy, cw, ch))
            cy += ch
        return out, (x + cw, y, w - cw, h)
    rh = s / w if w else 0
    cx = x
    for a, item in row:
        cw = a / rh if rh else 0
        out.append((item, cx, y, cw, rh))
        cx += cw
    return out, (x, y + rh, w, h - rh)


def squarify(items, x, y, w, h):
    """items: list of (weight, item). Returns [(item, x, y, w, h)]."""
    total = sum(a for a, _ in items)
    if total <= 0 or w <= 0 or h <= 0:
        return []
    scale = w * h / total
    rest = sorted(((a * scale, it) for a, it in items if a > 0), key=lambda p: -p[0])
    out = []
    row = []
    rect = (x, y, w, h)
    while rest:
        side = min(rect[2], rect[3])
        cand = rest[0]
        if not row or worst(row + [cand], side) <= worst(row, side):
            row.append(cand)
            rest.pop(0)
        else:
            placed, rect = layout_row(row, *rect)
            out += placed
            row = []
    if row:
        placed, _ = layout_row(row, *rect)
        out += placed
    return out


# --- grouping ----------------------------------------------------------------


def size(unit):
    return int(unit["measures"].get("total_code", 0) or 0)


def folder(unit):
    path = unit.get("metadata", {}).get("source_path") or unit["name"]
    return os.path.dirname(path)


def build_tree(units):
    cats = {}
    for u in units:
        if size(u) <= 0:
            continue
        cat = (u.get("metadata", {}).get("progress_categories") or ["other"])[0]
        cats.setdefault(cat, {}).setdefault(folder(u), []).append(u)
    return cats


def draw(units, measures):
    tree = build_tree(units)
    rects = []  # (unit, x, y, w, h)
    groups = []  # outlines for categories
    cat_items = [(sum(size(u) for us in f.values() for u in us), c) for c, f in tree.items()]
    for cat, cx, cy, cw, ch in squarify(cat_items, 0, 0, W, H):
        groups.append((cx, cy, cw, ch))
        folders = tree[cat]
        f_items = [(sum(size(u) for u in us), f) for f, us in folders.items()]
        for f, fx, fy, fw, fh in squarify(f_items, cx, cy, cw, ch):
            u_items = [(size(u), u) for u in folders[f]]
            rects += squarify(u_items, fx, fy, fw, fh)

    p = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="sans-serif">'
    )
    p.append(f'<rect width="{W}" height="{H}" rx="8" fill="#222"/>')
    p.append(f'<clipPath id="r"><rect width="{W}" height="{H}" rx="8"/></clipPath>')
    p.append('<g clip-path="url(#r)" stroke="#000" stroke-width="0.6">')
    for u, x, y, w, h in rects:
        r, g, b = colour(u)
        m = u["measures"]
        name = u["name"].replace("mario/", "", 1)
        tip = (
            f"{name}: {m.get('fuzzy_match_percent', 0):.2f}% fuzzy, "
            f"{m.get('matched_code_percent', 0):.2f}% matched, "
            f"{size(u)} bytes"
        )
        p.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="rgb({r},{g},{b})"><title>{escape(tip)}</title></rect>'
        )
    p.append("</g>")
    p.append('<g fill="none" stroke="#000" stroke-width="2">')
    for x, y, w, h in groups:
        p.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/>')
    p.append("</g></svg>")
    return "\n".join(p)


def summary(measures, categories):
    def pct(m, k):
        return f"{float(m.get(k, 0) or 0):.2f}%"

    lines = [
        "| | Code matched | Fuzzy | Functions matched | Units complete |",
        "|---|---|---|---|---|",
    ]
    rows = [("**Total**", measures)] + [(c["name"], c["measures"]) for c in categories]
    for name, m in rows:
        lines.append(
            f"| {name} | {pct(m, 'matched_code_percent')} | {pct(m, 'fuzzy_match_percent')} "
            f"| {m.get('matched_functions', 0)} / {m.get('total_functions', 0)} "
            f"| {m.get('complete_units', 0)} / {m.get('total_units', 0)} |"
        )
    return "\n".join(lines)


def update_readme(text):
    start, end = "<!-- progress:start -->", "<!-- progress:end -->"
    try:
        readme = open(README, encoding="utf-8").read()
    except OSError:
        return False
    if start not in readme or end not in readme:
        return False
    a = readme.index(start) + len(start)
    b = readme.index(end)
    new = readme[:a] + "\n" + text + "\n" + readme[b:]
    if new != readme:
        open(README, "w", encoding="utf-8").write(new)
    return True


def demangle_all(names):
    try:
        cache = json.load(open(DEMANGLE_CACHE))
    except (OSError, ValueError):
        cache = {}
    todo = [n for n in set(names) if n not in cache]

    def one(name):
        try:
            r = subprocess.run([DTK, "demangle", name], capture_output=True, text=True)
            out = r.stdout.strip()
            return name, out if r.returncode == 0 and out else name
        except OSError:
            return name, name

    if todo:
        with ThreadPoolExecutor(max_workers=16) as pool:
            for name, dem in pool.map(one, todo):
                cache[name] = dem
        os.makedirs(os.path.dirname(DEMANGLE_CACHE), exist_ok=True)
        json.dump(cache, open(DEMANGLE_CACHE, "w"))
    return cache


def write_page(data):
    names = [f["name"] for u in data["units"] for f in u.get("functions", []) if not f.get("metadata", {}).get("demangled_name")]
    dem = demangle_all(names)
    units = []
    for u in data["units"]:
        m = u["measures"]
        md = u.get("metadata", {})
        fns = sorted(u.get("functions", []), key=lambda f: int(f.get("address", 0) or 0))
        units.append({
            "n": u["name"].replace("mario/", "", 1),
            "p": md.get("source_path") or u["name"],
            "cat": (md.get("progress_categories") or ["other"])[0],
            "c": int(m.get("total_code", 0) or 0),
            "m": int(m.get("matched_code", 0) or 0),
            "f": round(float(m.get("fuzzy_match_percent", 0) or 0), 2),
            "fn": [[f.get("metadata", {}).get("demangled_name") or f.get("metadata", {}).get("demangled_name") or dem.get(f["name"], f["name"]), int(f.get("size", 0) or 0),
                    round(float(f["fuzzy_match_percent"]), 2) if "fuzzy_match_percent" in f else -1]
                   for f in fns],
        })
    tm = data["measures"]
    page = {
        "repo": REPO_URL,
        "built": datetime.date.today().isoformat(),
        "catNames": {c["id"]: c["name"] for c in data.get("categories", [])},
        "total": {
            "matched": float(tm["matched_code_percent"]),
            "fuzzy": float(tm["fuzzy_match_percent"]),
            "fns": int(tm["total_functions"]),
            "mfn": int(tm["matched_functions"]),
            "units": int(tm["total_units"]),
            "done": int(tm["complete_units"]),
        },
        "units": units,
    }
    html = open(PAGE_TEMPLATE, encoding="utf-8").read()
    blob = json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*DATA*/null", blob, 1)
    os.makedirs(os.path.dirname(PAGE_OUT), exist_ok=True)
    open(PAGE_OUT, "w", encoding="utf-8").write(html)


def main():
    report = sys.argv[1] if len(sys.argv) > 1 else REPORT
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    data = json.load(open(report))
    svg = draw(data["units"], data["measures"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(svg + "\n")
    update_readme(summary(data["measures"], data.get("categories", [])))
    write_page(data)
    m = data["measures"]
    print(
        f"wrote {os.path.relpath(out, ROOT)}: "
        f"{float(m['matched_code_percent']):.2f}% code matched, "
        f"{float(m['fuzzy_match_percent']):.2f}% fuzzy"
    )


if __name__ == "__main__":
    main()
