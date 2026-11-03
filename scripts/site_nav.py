#!/usr/bin/env python3
"""ONE source of truth for the llmbench section nav.

Every page builder imports ``render_nav`` / ``nav_items`` from here, so a new
tab cannot appear on one page and be forgotten on another. ``scripts/check_nav.py``
renders every built page and fails if its link set drifts from this list.

Adding a section: append it to ``ITEMS`` once, make sure its directory (with an
``index.html``) exists, rebuild, run the checker. Items whose path does not
exist in the worktree are omitted, so a half-built section can never ship a
dead nav link.

Order (canonical):
    Overview, Games, Chat, Thinking, Ablation, Logic, Method, Raw data

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
    ("ablation", "Ablation"),
    ("logic", "Logic"),
    ("method", "Method"),
    ("raw", "Raw data"),
]

# Raw data has no landing index.html; the entry point is the chat JSONs.
URL_PATHS = {"raw": "raw-chat/"}


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


def render_nav(prefix="", current=None, style="tabs"):
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


def expected_hrefs(prefix=""):
    """Canonical href set for a page at ``prefix`` depth (checker helper)."""
    return [_href(prefix, key) for key, _, _ in nav_items()]
