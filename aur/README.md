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
its positive and adversarial regression tests and runs in CI. Literal indexed
checksum assignments such as Cursor's `sha512sums[0]=<hash>` are routine too:
the index must be a decimal integer and the checksum a literal value. Expressions
or variable names in an index are rejected because Bash evaluates array indexes
as arithmetic; adding `SKIP` remains forbidden.

The workflow is split so that the half handling upstream-controlled content holds
no write token at all (`contents: read`, `persist-credentials: false`); a
separate job holds the write tokens, runs only on PASS, and re-validates the
patch it receives rather than trusting the verdict. Validation proves a change
is *literal*, not that the new upstream release is trustworthy. The automated
reviewer reads only changed lines; it does not perform the full manual audit
below, including unchanged source relationships or references elsewhere.

The intended commit scope is `aur/`: the nightly vendor invocation targets
existing package directories, staging is limited to `aur/`, and gate 1 checks
allowed filenames. These mechanisms are not a sandbox against command execution
in the workflow. CODEOWNERS adds required review only when GitHub explicitly
requires Code Owner approval. Check live rules and bypass actors; having a
CODEOWNERS file or an unrelated status requirement is insufficient.

Because the repo is public, anyone can open a PR. The trusted caller checks
bot authorship, same head/base repository, main target, publisher branch and
exact SHA, the `aur-bump` label, absence of `needs-review`, and the actual creator
and run binding of the successful eligibility status. It runs only after the
workflow's audit and publish jobs succeed. These checks identify the delivery
path; they do not establish that a package release is safe. Ordinary outside
contributors cannot label PRs under GitHub's standard permissions, but triage
collaborators and suitably authorized apps can. Labels are not a merge permission.

<a id="where-the-vetter-lives"></a>

**Where the vetter lives.** The Claude Code cloud routine "Vet nightly AUR bump
PR" is started explicitly through its API by the workflow's `review` job. Only
`schedule` and `workflow_dispatch` on `main` can start the workflow; PR events
cannot start the caller. Instructions are reviewed in
[`.github/aur-vet-prompt.md`](../.github/aur-vet-prompt.md) and deployed separately
into the routine. CI cannot read the deployed copy back. The earlier seven-field
API prompt merged PR #4 on 2026-09-10; the eight-field, changes-only revision is
prepared here and still requires deployment. A successful prior merge does not
verify the current prompt, branch protections or identity permissions.

**API trigger setup.** Code changes alone do not configure Claude or GitHub:

1. Deploy the text below the separator in `.github/aur-vet-prompt.md`. Keep only
   the API trigger; remove the Pull request trigger. The revised prompt permits
   only one GitHub operation: a squash merge bound atomically to the supplied
   head SHA. It forbids GitHub reads, file reads, browsing, and comment/review/
   label writes. The merge tool must support an expected-head-SHA parameter.
2. For an enforced changes-only input boundary, the reviewer must have no
   repository checkout, auto-loaded repository instructions, or read tools.
   Prompt instructions alone do not remove these capabilities. A routine with
   an attached repository or broad GitHub connector cannot be claimed to meet
   this strict boundary without verifying its platform configuration. If those
   capabilities cannot be removed, use an isolated, tool-less reviewer and a
   separate deterministic merger; that architecture is not implemented here.
3. Configure GitHub environment `aur-review` with **Selected branches and tags**:
   only the **branch** `main`, no tag rule. Store `AUR_REVIEW_ROUTINE_TOKEN` in
   its secrets and `AUR_REVIEW_ROUTINE_ID` in its variables. The ID is the
   `trig_...` segment of the API URL. Never put the token at repository scope,
   in the prompt or in this public repo. The caller fixes the destination to
   `api.anthropic.com` and refuses redirects.
4. In Settings → Rules → Rulesets, edit the active main ruleset. Require
   `aur-bump/eligible` with **GitHub Actions** as its expected source (public
   GitHub integration ID `15368`). The caller checks this through the effective
   branch-rules API and refuses missing, unbound or differently bound checks.
   Claude's merge identity must have no bypass and no permission to edit the
   rule. Inspect authenticated bypass settings and the actual connected
   identity; public rule output alone does not establish this. Other trusted
   Actions workflows can still produce this status; protect workflow changes.
   Require Code Owner approval for workflow, scripts and prompt changes too;
   CODEOWNERS alone does not enable that requirement.
5. After both code and prompt updates, start a **new** AUR bump run on `main`.
   Rerunning an old run uses its original workflow/source and old payload schema.
   Do not deploy the new caller with the old prompt or vice versa. With eligible
   changes, check all three jobs and then Claude's result. A green `review` job
   means the API accepted a session, not that Claude approved or merged. With
   no changes there is no PR and no review request. Public logs do not print
   tokens, raw API responses or private session URLs.

**Exactly what Claude receives.** `scripts/trigger-aur-review.py` checks live
PR/status/rules metadata in ordinary code. It fetches the candidate as Git
objects without checking it out, verifies it is one commit directly on the
trusted source, checks all paths, and reruns the trusted literal-diff validator
using an isolated temporary index. The payload contains the seven fixed
identifiers (`repository`, `pr_number`, `head_branch`, `head_sha`, `source_sha`,
`run_id`, `publish_attempt`) plus `diff`: every added and removed line with diff
headers, but zero unchanged lines. Even the nearby source text Git normally
appends to hunk headers is removed. PR titles, descriptions, comments, reviews,
commit messages and repository files are not included. Oversized payloads fail
rather than being truncated. The routine must assess only this supplied diff;
it must not fetch additional context or claim a full-source audit.

The SHA-bound merge rejects a changed head, and GitHub enforces its required
status for identities without bypass. The label checks occur before invocation;
GitHub does not continuously enforce those labels through this status rule.
The caller's rule check detects a missing app binding, not the merger's bypass
or administration rights. Prompt restrictions are not a permissions sandbox.

**Recovery.** There is no automatic POST retry: a timeout can follow successful
acceptance and the API has no idempotency key. Check Claude's run list first.
If no run started and the deployed prompt matches that run's payload schema,
use **Re-run failed jobs** to retry only `review`, retaining the original
publisher PR/SHA/attempt. A full rerun creates a unique branch and can leave
multiple PRs open; it never force-pushes a reviewed branch. The caller refuses
an already closed PR. The seven-field `Review target:` log is diagnostic
metadata, not a complete payload: do not paste it into **Run now** or ask Claude
to find the diff. For a schema migration, start a new workflow run after updating
both code and prompt. Old date-only branches require human review. Keep branch
format, eight payload fields, status binding, script and deployed prompt in sync.

The old webhook did not fire for either a bot or human PR on 2026-09-08 despite
the app being installed and no filters configured. A manual Claude run on
2026-09-10 successfully reviewed and merged PR #3. That established execution
and GitHub-tool access, but did not verify webhook delivery; the explicit API
handoff replaces it. `scripts/test-aur-review-trigger.py` runs offline in CI
and covers hostile events, fork/spoofed PRs, head changes, stale/forged statuses,
payload isolation, redirects, ambiguous timeouts, required-app binding, and
real Git fixtures proving unchanged source and commit messages are excluded.

The first API attempt for PR #4 returned HTTP 401. Replacing the routine token
in the `aur-review` environment and rerunning the failed job started Claude;
the operator then confirmed the merge. Environment secrets are read when the
job starts, so this recovery used the updated token without republishing the PR.

**PR #4 exposed a fail-closed violation.** Its transcript says the MCP status
tool omitted `creator`; Claude substituted an inference from workflow source,
job success and timing, then merged despite step 1 explicitly requiring a hard
stop on missing status evidence. The API caller independently checked the actual
creator before invoking Claude, so that field was not entirely unchecked. This
is nevertheless a failure of the routine's merge rules, not evidence that they
are enforced. A successful handoff/merge does not prove safe unattended review.
The existing caller already blocks the outsider-created-PR trigger path. First
ensure that `aur-bump/eligible` is required from GitHub Actions and Claude's
identity cannot bypass or alter that rule. On 2026-09-10 the public effective
rules API listed this status requirement without an integration binding; the
earlier SSH push explicitly bypassed it. Claude's actual bypass rights still
need verification. Outsiders cannot directly apply repository labels under
GitHub's standard permissions, but can comment on an eligible public PR after
the caller's check. A label-only gate is weaker when the reviewer itself can
apply labels. The prepared changes-only payload excludes this discussion text.
A tool-less reviewer plus a separate deterministic merger would enforce the
read boundary if the routine platform cannot remove its existing capabilities. Adding
the missing field to the MCP tool fixes tool coverage, but cannot enforce the
model's decision to stop.

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
