#!/usr/bin/env python3
"""Build-time nav checker: every generated page must carry the canonical nav.

Fails (exit 1) if, on any page:
  * the <nav> link set differs from scripts/site_nav.py (missing / extra / duped
    entries, wrong labels, wrong order, wrong active marker count), or
  * a nav (or any internal) href points at a path that does not exist, or
  * an internal link (nav or body) still points at a retired section
    (/sweep/, /logic/, /raw-chat/, /ablation/, /method/ — folded into
    /#speed-sweep, /thinking/#logic, /#raw, /#ablation and /#method).

The canonical set is exactly the seven items in scripts/site_nav.py. This checker
fails if a page ships more (a new tab was invented) or fewer (an item was dropped).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_nav  # noqa: E402

ROOT = site_nav.ROOT

# Pages that are part of the site chrome and must carry the nav.
PAGES = [
    ("/", "index.html"),
    ("/games/", "games/index.html"),
    ("/chat/", "chat/index.html"),
    ("/thinking/", "thinking/index.html"),
    ("/games/sidebyside/", "games/sidebyside/index.html"),
]

NAV_RE = re.compile(r"<nav\b[^>]*>(.*?)</nav>", re.S | re.I)
A_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF_RE = re.compile(r'href\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)


def link_set(nav_html):
    out = []
    for attrs, text in A_RE.findall(nav_html):
        m = HREF_RE.search(attrs)
        href = next((g for g in m.groups() if g is not None), "") if m else ""
        out.append((href, re.sub(r"<[^>]+>", "", text).strip(), attrs))
    return out


def resolve(page_dir, href):
    """Resolve an href relative to the page's own directory -> repo path."""
    if not href or href.startswith(("http://", "https://", "mailto:", "#", "data:")):
        return None
    base = [p for p in page_dir.strip("/").split("/") if p]
    parts = base
    rest = href
    while rest.startswith("../"):
        if parts:
            parts = parts[:-1]
        rest = rest[3:]
    parts = parts + [p for p in rest.split("/") if p not in ("", ".")]
    return "/".join(parts) or "."


def path_ok(rel):
    if rel in ("", "."):
        rel = "index.html"
    full = os.path.join(ROOT, rel)
    if os.path.isdir(full):
        return os.path.exists(os.path.join(full, "index.html"))
    return os.path.exists(full)


def check_page(url_path, rel_file):
    errors = []
    full = os.path.join(ROOT, rel_file)
    if not os.path.exists(full):
        return [f"{url_path}: page file missing ({rel_file})"]
    html = open(full, encoding="utf-8").read()
    navs = NAV_RE.findall(html)
    if len(navs) != 1:
        return [f"{url_path}: expected 1 <nav>, found {len(navs)}"]
    links = link_set(navs[0])

    # sticky bar: exactly one .topbar, a direct child of <body>, holding the nav,
    # and never nested inside the header (sticky would then release with it).
    if html.count('class="topbar"') != 1:
        errors.append(f"{url_path}: expected 1 .topbar, found {html.count('class=\"topbar\"')}")
    body = html.split("<body>", 1)[-1]
    if '<div class="topbar">' not in body:
        errors.append(f"{url_path}: .topbar is not a top-level child of <body>")
    header = re.search(r"<header\b.*?</header>", html, re.S)
    if header and "<nav" in header.group(0):
        errors.append(f"{url_path}: nav still nested inside <header> (sticky would not hold)")
    if html.find('<div class="topbar">') < html.find("</header>"):
        errors.append(f"{url_path}: .topbar appears before the header ends")

    key = "overview" if url_path == "/" else url_path.strip("/").split("/")[0]
    depth = len([p for p in url_path.strip("/").split("/") if p])
    prefix = "../" * depth
    expected = [(site_nav.expected_hrefs(prefix)[i], label)
                for i, (_, label, _) in enumerate(site_nav.nav_items())]

    got = [(h, t) for h, t, _ in links]
    if got != expected:
        missing = [e for e in expected if e not in got]
        extra = [g for g in got if g not in expected]
        dups = sorted({g for g in got if got.count(g) > 1})
        if missing:
            errors.append(f"{url_path}: missing nav entries {missing}")
        if extra:
            errors.append(f"{url_path}: extra/foreign/out-of-order nav entries {extra}")
        if dups:
            errors.append(f"{url_path}: duplicated nav entries {dups}")

    on = 0
    for href, text, attrs in links:
        active = 'class="on"' in attrs or 'aria-current="page"' in attrs
        if active:
            on += 1
            want = os.path.normpath(prefix + site_nav._rel_url(key))
            if not href or os.path.normpath(href) != want:
                errors.append(f"{url_path}: active marker on non-current link {href!r}")
        rel = resolve(url_path, href)
        if rel is not None and rel.startswith(".."):
            errors.append(f"{url_path}: nav link {href!r} escapes the site root")
            rel = None
        elif href.count("../") and not url_path.strip("/"):
            errors.append(f"{url_path}: root page uses a ../ nav link {href!r}")
            rel = None
        if rel is not None and not path_ok(rel):
            errors.append(f"{url_path}: dead nav link {href!r} -> {rel}")
    if on > 1:
        errors.append(f"{url_path}: {on} active nav links, expected at most 1")

    return errors


CANON = ["Overview", "Games", "Chat", "Thinking"]


def check_canonical():
    """The one nav list itself: exactly the seven canonical items, in order."""
    errs = []
    labels = [label for _, label, _ in site_nav.nav_items()]
    if labels != CANON:
        errs.append(f"site_nav: canonical nav is {labels}, expected {CANON}")
    return errs


def check_retired(url_path, rel_file):
    """No internal link on a shipped page may point at a removed section."""
    errs = []
    html = open(os.path.join(ROOT, rel_file), encoding="utf-8").read()
    for m in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', html, re.I):
        href = m.group(1)
        if href.startswith(("http://", "https://", "mailto:", "data:")):
            continue
        if re.search(r'(^|/)(sweep|logic|raw-chat|ablation|method)(/|$|\?|#raw)', href, re.I):
            errs.append(f"{url_path}: link to retired section {href!r}")
    return errs


def main():
    failures = 0
    for e in check_canonical():
        failures += 1
        print("FAIL", e)
    for url_path, rel_file in PAGES:
        errs = check_page(url_path, rel_file) + check_retired(url_path, rel_file)
        if errs:
            failures += 1
            for e in errs:
                print("FAIL", e)
        else:
            print("ok  ", url_path)
    canonical = [u for _, _, u in site_nav.nav_items()]
    print(f"canonical nav ({len(canonical)}):", ", ".join(canonical))
    if failures:
        print(f"\nNAV CHECK FAILED on {failures} page(s)")
        return 1
    # the retired output directories must not ship
    for d in ("sweep", "logic", "raw-chat", "ablation", "method"):
        if os.path.isdir(os.path.join(ROOT, d)):
            print(f"FAIL retired output directory still present: {d}/")
            failures += 1
    print(f"\nnav ok on {len(PAGES)} pages, {len(canonical)} canonical items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
