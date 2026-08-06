# Vendored AUR PKGBUILDs

Every AUR package in the images is built from a **vetted PKGBUILD committed
here** — the build never fetches PKGBUILDs from the AUR. This is a deliberate
supply-chain control: the AUR is an attack surface (account-takeover campaigns
hijack orphaned packages and inject payloads into PKGBUILDs, e.g. the June 2026
"Atomic Arch" attack that poisoned 500+ packages). By building only from copies
reviewed in pull requests, a malicious upstream PKGBUILD change cannot reach an
image until a human has read the diff.

## Layout

```
aur/
  manifest.tsv          pkgbase <TAB> upstream-git-commit <TAB> fetch-date (provenance)
  <pkgbase>/            full AUR repo contents minus .git, .SRCINFO, .nvchecker.toml, .gitignore
    PKGBUILD            the only file makepkg strictly needs; everything else is a local source
    *.install *.sh *.patch ...
```

Directories are keyed by **pkgbase**, not pkgname (AUR git is keyed by pkgbase).
`google-cloud-cli` is a *split* pkgbase that produces several packages; the base
image installs only `google-cloud-cli` and
`google-cloud-cli-component-gke-gcloud-auth-plugin` from it.

`Containerfile.base` `COPY`s this whole tree in and runs `makepkg` against each
directory. `yay` itself is vendored and built here too, so it still ships in the
images for interactive `yay -S` after pulling — only the *image build* is locked
to vendored copies.

## How the build stays safe even though sources download at build time

`makepkg` still downloads each package's *upstream* artifact (the chrome `.deb`,
the vscode `.deb`, the claude binary, …) — but from the official vendor URL in
the vetted PKGBUILD, gated by the `sha256sums`/`sha512sums` committed alongside
it. A swapped upstream artifact fails the checksum and aborts the build.

One residual non-hermetic step: the gke-gcloud-auth-plugin split package runs
`gcloud components install` at build time, fetching that component from Google's
own servers (not the AUR, not checksum-pinned). That is the same trust boundary
as the gcloud tarball itself.

## Refreshing / bumping a package

Vendored `-bin`/`-git` PKGBUILDs go stale as upstream releases; a stale one
fails the build (404 or checksum mismatch) until bumped. To re-vendor and vet:

```bash
box vendor-aur <pkgbase>     # one package
box vendor-aur --all         # all of them
```

This re-clones from the AUR, prints a diff against the committed copy so you can
**review it before committing**, updates the files and `manifest.tsv`. Read the
diff, then `git add aur/ && git commit`. The wrapper is `scripts/vendor-aur.sh`.

## Auditing a `vendor-aur` bump

The vendoring is only worth anything if somebody actually reads the diff. A
routine bump should be **nothing but** `pkgver`/`_commit`/checksum lines plus
new `manifest.tsv` rows — anything else deserves a closer look. Work through
these from the repo root with the re-vendored changes unstaged. If the bump is
already committed, add the range to each `git diff`/`git show` (`HEAD~1..HEAD`,
`HEAD~1:aur/...`).

**1. Only PKGBUILDs and the manifest should have changed.** A bump that also
rewrites an `*.install`, `*.sh` or `*.patch` is the shape a poisoned package
takes:

```bash
git status --porcelain aur/
```

**2. Strip the routine lines and read what's left.** This is the core review —
whatever survives is the *actual* change in build behaviour:

```bash
git diff -U0 -- 'aur/*/PKGBUILD' aur/manifest.tsv | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' \
  | grep -viE "^[+-]\s*(pkgver=|_commit=|sha[0-9]+sums|md5sums)" \
  | grep -vE "^[+-]\s*'[0-9a-f]{40,128}'?\)?$" \
  | grep -vE '^[+-][a-z0-9-]+\s+[0-9a-f]{40}\s+[0-9]{4}-'
```

**3. No new download hosts.** Compare source URLs before and after, normalising
version numbers and commit hashes so only genuine URL changes show up:

```bash
urls() { grep -ohE 'https?://[^"'"'"' )]+' | sed -E 's/[0-9]+\.[0-9]+[0-9.]*/VER/g; s/[0-9a-f]{40}/COMMIT/g' | sort -u; }
for p in $(git diff --name-only -- 'aur/*/PKGBUILD' | cut -d/ -f2); do git show "HEAD:aur/$p/PKGBUILD"; done | urls > /tmp/before.txt
for p in $(git diff --name-only -- 'aur/*/PKGBUILD' | cut -d/ -f2); do cat "aur/$p/PKGBUILD"; done | urls > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

Every host must be the software vendor's own (`dl.google.com`,
`downloads.cursor.com`, `update.code.visualstudio.com`, `downloads.claude.ai`,
`gitlab.archlinux.org`, `github.com`). A new host, an IP literal, or a shortener
is a stop-and-investigate.

**4. Verify the vendored copies really are upstream at the pinned commits.**
This catches a local copy that drifted from what `manifest.tsv` claims:

```bash
tmp=$(mktemp -d); R=$PWD
while IFS=$'\t' read -r base commit _; do
  git clone --quiet "https://aur.archlinux.org/$base.git" "$tmp/$base"
  git -C "$tmp/$base" checkout --quiet "$commit" || { echo "BAD COMMIT: $base"; continue; }
  rm -rf "$tmp/$base/.git"; rm -f "$tmp/$base"/{.SRCINFO,.nvchecker.toml,.gitignore}
  diff -ruN "$R/aur/$base" "$tmp/$base" >/dev/null && echo "OK   $base" || echo "DIFF $base"
done < aur/manifest.tsv; rm -rf "$tmp"
```

**5. Red flags in the surviving diff** — any of these means read the upstream
AUR history before committing: a new `prepare()`/`build()` function or new lines
in an existing one; `curl`/`wget`/`eval`/`base64 -d` anywhere; a new `install=`
scriptlet; `sha*sums` entries changed to `'SKIP'`; sources added that aren't
downloads (a new local file appearing in `aur/<pkgbase>/`).

**What you do _not_ need to verify:** that the new checksums match the bytes the
vendor currently serves. A wrong checksum fails the build — it cannot install a
tampered artifact. Downloading several hundred MB to confirm sums buys nothing;
CI is the check. What matters is where the URLs point and what the build scripts
do.

**Structural changes are usually upstream, not an attack.** Arch-list splits
(`source=` → `source_x86_64=`/`source_aarch64=`) are common. When source order
changes, confirm the reordered `sha*sums` still line up with the local files —
`sha512sum aur/<pkgbase>/<file>` against the entry at that index.

**Knock-on check.** Nothing outside `aur/` should hardcode a vendored version;
confirm with `grep -rn <old-version> --exclude-dir=.git .` before committing.

## Adding / removing a vendored package

- **Add:** `box vendor-aur <new-pkgbase>`, review, then add its build step to the
  AUR section of `Containerfile.base`.
- **Remove:** delete `aur/<pkgbase>/`, drop its row from `manifest.tsv`, and
  remove its build step from `Containerfile.base`.
