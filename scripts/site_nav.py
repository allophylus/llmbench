#!/usr/bin/env python3
"""ONE source of truth for the llmbench section nav.

Every page builder imports ``render_nav`` / ``nav_items`` from here, so a new
tab cannot appear on one page and be forgotten on another. ``scripts/check_nav.py``
renders every built page and fails if its link set drifts from this list.

Adding a section: append it to ``ITEMS`` once, make sure its directory (with an
``index.html``) exists, rebuild, run the checker. Items whose path does not
exist in the worktree are omitted, so a half-built section can never ship a
dead nav link.

Order (canonical, four items):
    Overview, Games, Chat, Thinking

The matched-context speed matrix is not a nav item: it is a section of the
overview's Speed view (/index.html#speed-sweep), and the logic-trap set is a
section of /thinking/ (/thinking/#logic); the accelerator ablation (#ablation), the
methodology (#method) and the downloadable raw records (#raw) are sections of the
overview. All of them used to be their own tabs.

Two visual flavours exist in the site CSS:

* ``style="tabs"``   -> ``<nav class="tabs">``  (pill tabs used by sub-pages;
                        ``.tabs a.on`` = active pill)
* ``style="site"``   -> ``<nav class="site-nav" aria-label="Sections">`` (the
                        header strip used by index.html; ``aria-current``)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (key, label) in canonical order. The URL for a key is conventionally
# "<key>/" relative to the site root, with "overview" at the root itself.
ITEMS = [
    ("overview", "Overview"),
    ("games", "Games"),
    ("chat", "Chat"),
    ("thinking", "Thinking"),
]

# Every section has a landing index.html; no overrides are needed today.
URL_PATHS = {}


def _rel_url(key):
    return URL_PATHS.get(key, "./" if key == "overview" else key + "/")


def _href(prefix, key):
    """Prefix a section URL without producing '.././' for the bare root."""
    if key == "overview" and prefix.endswith("../"):
        return prefix
    return prefix + _rel_url(key)


def _exists(key):
    """True if the section has a built landing page in the working tree."""
    d = os.path.join(ROOT, _rel_url(key).strip("./").rstrip("/"))
    if key == "overview":
        return os.path.exists(os.path.join(ROOT, "index.html"))
    return os.path.exists(os.path.join(d, "index.html"))


def nav_items():
    """[(key, label, rel_url)] for every section that actually exists."""
    return [(k, label, _rel_url(k)) for k, label in ITEMS if _exists(k)]


def render_nav(prefix="", current=None, style="site"):
    """Nav markup for a page ``prefix`` directory levels below the site root.

    prefix: "" for root pages, "../" for one-level pages, "../../" for deeper.
    current: section key to mark active (None = no active marker).
    style: "tabs" (pill tabs) or "site" (header strip).
    """
    if style == "site":
        parts = ['<nav class="site-nav" aria-label="Sections">']
        for key, label, url in nav_items():
            attrs = ' aria-current="page"' if key == current else ""
            parts.append(f'<a href="{_href(prefix, key)}"{attrs}>{label}</a>')
        parts.append("</nav>")
        return "".join(parts)

    parts = ['<nav class="tabs">']
    for key, label, url in nav_items():
        attrs = ' class="on"' if key == current else ""
        parts.append(f'<a href="{_href(prefix, key)}"{attrs}>{label}</a>')
    parts.append("</nav>")
    return "".join(parts)


# Self-contained sticky-bar CSS. Sub-pages ship their own inline <style> and do
# not link style.css, so every builder embeds TOPBAR_CSS to get identical bar
# behaviour on all pages. Keep in sync with the .topbar block in style.css.
# Sub-pages embed the stylesheet inline (they predate the shared <link>), so loading the
# REAL style.css at build time is the only way they cannot drift from the site styles.
# The previous hand-maintained copy drifted, and the nav collapsed to 0px height on every
# sub-page for exactly that reason.
def _load_css():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "style.css")
    try:
        with open(path, encoding="utf8") as fh:
            return fh.read()
    except OSError:
        return ""

TOPBAR_CSS = _load_css()


def render_topbar(prefix="", current=None, style="site"):
    """The persistent sticky bar: a top-level sibling of <header>, not inside it.

    Must be placed directly in <body> (never in a padded/short parent) so it can
    stick to the viewport for the whole page.
    """
    return ('<div class="topbar"><div class="wrap">'
            + render_nav(prefix, current, style=style) + "</div></div>")


def expected_hrefs(prefix=""):
    """Canonical href set for a page at ``prefix`` depth (checker helper)."""
    return [_href(prefix, key) for key, _, _ in nav_items()]


# ---- site brand header ----------------------------------------------------
# The overview used to be the only page with the logo + description, so every
# sub-page looked like a different site. One helper, used by every builder.
BRAND_TEXT = ("Raw, repeatable benchmark numbers for local models served by "
              "<strong>llama.cpp (Vulkan)</strong> on an AMD Radeon AI PRO R9700 "
              "32&nbsp;GiB box.")


def render_brand():
    return ('<header class="site-head"><div class="wrap"><h1>llmbench</h1>'
            '<p class="sub">' + BRAND_TEXT + '</p></div></header>')
