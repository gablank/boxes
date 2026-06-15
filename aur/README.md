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

## Adding / removing a vendored package

- **Add:** `box vendor-aur <new-pkgbase>`, review, then add its build step to the
  AUR section of `Containerfile.base`.
- **Remove:** delete `aur/<pkgbase>/`, drop its row from `manifest.tsv`, and
  remove its build step from `Containerfile.base`.
