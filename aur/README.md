# Vendored AUR PKGBUILDs

Every AUR package in the images is built from a **PKGBUILD committed here** —
the image build never fetches PKGBUILDs from the AUR. Vendoring makes recipe
changes reviewable before they reach an image; its protection depends on the
review and merge controls. The nightly workflow and external automated reviewer
are part of that trust boundary, and both have known weaknesses: read
"Auditing a `vendor-aur` bump" below before relying on either.

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

## What vendoring pins

Most binary artifacts are downloaded from vendor URLs and checked against
committed checksums. An artifact differing from its expected checksum fails the
build. This checks identity against the reviewed value, not whether a new
artifact and its accompanying checksum are safe.

The recipe pins do not cover all downloaded content. `oh-my-zsh-git` fetches
floating upstream Git HEAD with `SKIP`; the gke-gcloud-auth-plugin split package
runs `gcloud components install` without a repository checksum pin. Claude's
license document is also unpinned, although its binary is checksummed. Cursor's
initial `SKIP` is overwritten with a checksum later in the recipe. Outside AUR,
the image installs unpinned npm dependencies and editor extensions. These are
additional upstream trust relationships.

## Refreshing / bumping a package

Versioned binary recipes can go stale and fail with a 404 or checksum mismatch.
A floating Git recipe can instead fetch new code without any recipe change.
To re-vendor and vet:

```bash
box vendor-aur <pkgbase>     # one package
box vendor-aur --all         # all of them
```

This re-clones from the AUR, prints a diff against the committed copy so you can
**review it before committing**, updates the files and `manifest.tsv`. Read the
diff, then `git add aur/ && git commit`. The wrapper is `scripts/vendor-aur.sh`.

The same re-vendoring also runs nightly at 03:00 UTC in
`.github/workflows/aur-bump.yml`, which runs the mechanical half of the audit
below as a hard gate and opens a PR carrying the report. The manual command
stays for one-off bumps and for bumping a single stale package mid-day.

## Auditing a `vendor-aur` bump

Review the full diff, including version/checksum assignments and file modes.
PKGBUILDs are shell programs: a line beginning with `pkgver=`, `_commit=`, or a
checksum assignment can execute commands. A routine bump changes only validated
literal values, not arbitrary text on lines with those prefixes. Work through
these from the repo root with the re-vendored changes unstaged. If the bump is
already committed, add the range to each `git diff`/`git show` (`HEAD~1..HEAD`,
`HEAD~1:aur/...`).

Steps 1-4 run automatically in `aur-bump.yml`, which aborts before opening a PR
if any of them fails. Step 2 is enforced there by `scripts/validate-aur-diff.py`,
a deterministic validator: every changed line must match an exact literal shape
(a version, a checksum, a manifest row) and anything else fails the run. It never
sources or executes the candidate recipe. `scripts/test-aur-validator.sh` holds
its adversarial regression tests and runs in CI.

The workflow is split so that the half handling upstream-controlled content holds
no write token at all (`contents: read`, `persist-credentials: false`); a
separate job holds the write tokens, runs only on PASS, and re-validates the
patch it receives rather than trusting the verdict. Step 5 still needs a reader:
validation proves a change is *literal*, not that the new upstream release is
trustworthy, so the PR carries the full diff.

The intended commit scope is `aur/`: the nightly vendor invocation targets
existing package directories, staging is limited to `aur/`, and gate 1 checks
allowed filenames. These mechanisms are not a sandbox against command execution
in the workflow. CODEOWNERS adds required review only when GitHub explicitly
requires Code Owner approval. Check live rules and bypass actors; having a
CODEOWNERS file or an unrelated status requirement is insufficient.

Because the repo is public, anyone can open a PR, and CODEOWNERS matches on path
rather than author — so a stranger's `aur/`-only PR is not covered by any of the
above. The supplied vetting routine checks the author `github-actions[bot]`,
head repo `gablank/boxes`, a dated `aur/bump-` branch, and the `aur-bump` label
before reading PR content. These identify the delivery path, not safe package
contents. The required `aur-bump/eligible` status provides an additional GitHub
gate for identities without bypass rights. It is not unique to this workflow:
other writers with status permission can post it. Bind the expected integration
and verify connector permissions separately. Review and merge must refer to the
same immutable head SHA.

**Where the vetter lives.** It is a Claude Code *cloud routine* named "Vet
nightly AUR bump PR", woken by a webhook on every `pull_request` event in this
repo, not by a schedule. Its instructions are reviewed here as
[`.github/aur-vet-prompt.md`](../.github/aur-vet-prompt.md) and *deployed* into
the routine, which is where they actually execute — change that file in a pull
request first, then deploy. The two copies can drift and nothing in CI can read
the deployed one back, so re-read both whenever the audit above changes:
correcting this file does not correct the routine. Two properties of that
environment shape the prompt and are easy to rediscover the hard way: `gh` is
not installed and no GitHub credential is present, so every GitHub read and
write goes through the `mcp__github__*` MCP tools (loaded on demand via
`ToolSearch`); and the routine only has `Bash`, `Read`, `Grep`, `Glob` and
`PushNotification` locally, which reach the checkout but never GitHub.

**The webhook has never been observed to fire.** On 2026-09-08 neither a
bot-authored PR (#1, labelled `aur-bump`) nor a human-authored one (#2) woke the
routine, with the app installed on all repositories, no filter configured, and
the trigger registered for all `pull_request` events. Do not assume unattended
vetting is running because the routine exists; check its run list.

**1. Only PKGBUILDs and the manifest should have changed.** A bump that also
rewrites an `*.install`, `*.sh` or `*.patch` is the shape a poisoned package
takes:

```bash
git status --porcelain aur/
```

**2. Read the full diff, including purportedly routine lines.** Check complete
assignments, quoting, command substitutions, extra commands, file modes, source
expansions, and checksum-to-source mapping. Do not source or execute the candidate
PKGBUILD to inspect its values. Prefix-based line stripping cannot establish that
a recipe is safe: PKGBUILDs are shell, so `pkgver=1.2.3$(...)` is both a version
assignment and a command.

```bash
git diff --raw -- aur/                          # paths, modes, file types
git diff --no-ext-diff --no-textconv -- aur/    # the whole change
python3 scripts/validate-aur-diff.py --worktree # the mechanical half of this step
```

The validator is what `aur-bump.yml` gates on. Run it yourself on a manual bump:
a PASS means every changed line is a literal version, checksum or manifest
update, which is the part worth automating. It cannot tell you whether the new
upstream release is trustworthy -- that is what the rest of this list is for.

**3. Validate complete source origins and paths.** The comparison below is an
aid after validating package names and file types. Read raw URLs and their
variable expansions too; normalization can conceal meaningful changes.

```bash
urls() { grep -ohE 'https?://[^"'"'"' )]+' | sed -E 's/[0-9]+\.[0-9]+[0-9.]*/VER/g; s/[0-9a-f]{40}/COMMIT/g' | sort -u; }
audit_tmp=$(mktemp -d)
for p in $(git diff --name-only -- 'aur/*/PKGBUILD' | cut -d/ -f2); do git show "HEAD:aur/$p/PKGBUILD"; done | urls > "$audit_tmp/before.txt"
for p in $(git diff --name-only -- 'aur/*/PKGBUILD' | cut -d/ -f2); do cat "aur/$p/PKGBUILD"; done | urls > "$audit_tmp/after.txt"
diff "$audit_tmp/before.txt" "$audit_tmp/after.txt"
```

Every host must be the software vendor's own (`dl.google.com`,
`downloads.cursor.com`, `update.code.visualstudio.com`, `downloads.claude.ai`,
`gitlab.archlinux.org`, `github.com`). A new host, an IP literal, or a shortener
is a stop-and-investigate. Shared hosting domains such as `github.com` do not
identify a vendor: verify the exact repository and path as well as the hostname.

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

**5. Red flags in the full diff** — any of these means read the upstream
AUR history before committing: a new `prepare()`/`build()` function or new lines
in an existing one; `curl`/`wget`/`eval`/`base64 -d` anywhere; a new `install=`
scriptlet; `sha*sums` entries changed to `'SKIP'`; sources added that aren't
downloads (a new local file appearing in `aur/<pkgbase>/`).

**Checksum limits:** `makepkg` checks downloaded bytes against the supplied sums,
so duplicating that download is not a substitute for review. An attacker can
change both a payload and its checksum, or execute code before checking sources.
Review the checksum assignments themselves, exact source identity and paths,
and all executable recipe content.

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
