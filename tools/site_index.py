"""Versioned site layout on gh-pages: a folder per release, latest/, next/ and the root files.

latest/ shows the newest final release, or the newest release of any kind until there is a final.
The root redirects to latest/ (next/ before the first release) and its 404 page sends old links on.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from release import Version, latest  # noqa: E402

DRAFT = "next"
LATEST = "latest"


def versions_in(names: list[str]) -> list[Version]:
    """Release versions among folder names, newest first."""
    found = {v for v in map(Version.parse, names) if v}
    return sorted(found, key=Version.key, reverse=True)


def site_latest(versions: list[Version]) -> Version | None:
    return latest(v for v in versions if v.channel == "final") or latest(versions)


def folders_at(ref: str, top: Path) -> list[str]:
    """Top-level folder names on a branch, or none if it doesn't exist."""
    try:
        out = subprocess.check_output(["git", "ls-tree", "-d", "--name-only", ref], cwd=top,
                                      text=True, encoding="utf-8", stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    return out.split()


def base_path(repository: str) -> str:
    """URL path of the Pages site: / for <owner>.github.io, else /<repo>/."""
    name = repository.rsplit("/", 1)[-1]
    return "/" if name.endswith(".github.io") else f"/{name}/"


def versions_json(versions: list[Version]) -> str:
    top = site_latest(versions)
    return json.dumps({"latest": str(top) if top else None,
                       "versions": [{"version": str(v), "channel": v.channel} for v in versions]},
                      indent=2) + "\n"


def index_html(versions: list[Version]) -> str:
    target = (LATEST if versions else DRAFT) + "/"
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            f'<meta http-equiv="refresh" content="0; url={target}">\n<title>IMT Doctrine</title></head>\n'
            f'<body><p><a href="{target}">IMT Doctrine</a></p></body></html>\n')


def not_found_html(versions: list[Version], base: str) -> str:
    # GitHub Pages serves this for every missing path. Pages from before the site kept versions
    # move under latest/; a page missing from one version goes to that version's front page.
    default = LATEST if versions else DRAFT
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Page not found - IMT Doctrine</title>
<script>
(() => {{
  const base = {json.dumps(base)}, fallback = {json.dumps(default)};
  const folder = /^(next|latest|pr-preview|v\\d+\\.\\d+\\.\\d+(-rc\\.\\d+|-demo)?)$/;
  const path = location.pathname.startsWith(base) ? location.pathname.slice(base.length) : "";
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return;
  if (!folder.test(parts[0])) location.replace(base + fallback + "/" + path + location.search + location.hash);
  else if (parts.length > 1) location.replace(base + parts[0] + "/");
}})();
</script></head>
<body><h1>Page not found</h1><p><a href="{base}{default}/">Go to the IMT Doctrine</a></p></body></html>
"""


def write_root(out: Path, versions: list[Version], base: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "versions.json").write_text(versions_json(versions), encoding="utf-8")
    (out / "index.html").write_text(index_html(versions), encoding="utf-8")
    (out / "404.html").write_text(not_found_html(versions, base), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--pages-ref", default="origin/gh-pages", help="git ref of the published site")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("root", help="write the root files for the site")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--base-path", help="URL path of the site (default from GITHUB_REPOSITORY)")
    i = sub.add_parser("is-latest", help="print true if VERSION should also be published as latest/")
    i.add_argument("version")
    args = ap.parse_args(argv)

    versions = versions_in(folders_at(args.pages_ref, args.top))
    if args.cmd == "is-latest":
        version = Version.parse(args.version)
        if version is None:
            print(f"error: {args.version} is not a release version", file=sys.stderr)
            return 1
        print(str(site_latest(versions_in([str(v) for v in versions] + [str(version)])) == version).lower())
        return 0
    base = args.base_path or base_path(os.environ.get("GITHUB_REPOSITORY", "schmidtnz/imt-doctrine"))
    write_root(args.out, versions, base)
    print(f"{len(versions)} versions; latest: {site_latest(versions) or 'none, so next/'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
