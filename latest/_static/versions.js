// Version menu (under the site title) and banner, from versions.json at the site root, one level
// above this build. Builds from before the menu existed get this file added by the backfill.
(() => {
  const buildRoot = new URL(document.documentElement.dataset.content_root || "./", location.href);
  const siteRoot = new URL("../", buildRoot);
  const here = buildRoot.pathname.split("/").filter(Boolean).pop();
  const page = location.pathname.slice(buildRoot.pathname.length);

  const show = (data) => {
    const latest = data.latest;
    const names = data.versions.map((v) => v.version);
    const options = [
      ...(latest ? [["latest", `latest (${latest})`]] : []),
      ["next", "next (working draft)"],
      ...names.map((n) => [n, n]),
    ];
    const brand = document.querySelector(".sidebar-brand");
    if (!brand || !options.some(([folder]) => folder === here)) return; // e.g. a pull request preview

    const menu = document.createElement("div");
    menu.className = "sidebar-versions";
    menu.innerHTML = '<label for="version-select">Version</label><select id="version-select"></select>';
    const select = menu.querySelector("select");
    for (const [folder, label] of options) {
      select.add(new Option(label, folder, false, folder === here));
    }
    select.addEventListener("change", () => {
      location.href = new URL(page + location.hash, new URL(select.value + "/", siteRoot)).href;
    });
    brand.after(menu);

    const link = latest && `<a href="${new URL("latest/", siteRoot).href}">${latest}</a>`;
    let text = "";
    if (here === "next") {
      text = "This is the working draft: changes merged but not yet released." +
        (link ? ` The latest release is ${link}.` : "");
    } else if (here !== "latest" && here !== latest && link) {
      const newer = names.indexOf(here) < names.indexOf(latest);
      text = newer
        ? `This is ${here}, a pre-release. The latest release is ${link}.`
        : `This is an older version, ${here}. The latest release is ${link}.`;
    }
    if (text) {
      const banner = document.createElement("div");
      banner.className = "admonition warning version-banner";
      banner.innerHTML = `<p class="admonition-title">Version</p><p>${text}</p>`;
      document.querySelector("article")?.prepend(banner);
    }
  };

  // Pages caches files for 10 minutes; revalidate so a new release shows at once.
  fetch(new URL("versions.json", siteRoot), { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => data && show(data))
    .catch(() => {});
})();
