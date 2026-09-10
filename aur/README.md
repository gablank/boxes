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
below and opens a PR carrying the report, including a draft for rejected changes. The manual command
stays for one-off bumps and for bumping a single stale package mid-day.

## Auditing a `vendor-aur` bump

Review the full diff, including version/checksum assignments and file modes.
PKGBUILDs are shell programs: a line beginning with `pkgver=`, `_commit=`, or a
checksum assignment can execute commands. A routine bump changes only validated
literal values, not arbitrary text on lines with those prefixes. Work through
these from the repo root with the re-vendored changes unstaged. If the bump is
already committed, add the range to each `git diff`/`git show` (`HEAD~1..HEAD`,
`HEAD~1:aur/...`).

The mechanical checks run in `aur-bump.yml`: the literal-diff validator checks
paths, modes and added/removed lines, and a separate provenance check compares
vendored files against their pinned AUR commits. Neither executes a recipe.
These checks cover the mechanical parts of the manual audit below; they do not
establish that a new binary release is trustworthy. Binary changes, new scripts,
source URL changes, symlinks, executable files and nonliteral assignments all
require human review. A failed gate does **not** discard the candidate.

<a id="where-the-vetter-lives"></a>

**Where the vetter lives.** Review runs inside the AUR GitHub Actions workflow,
using Claude Code with subscription OAuth. The five jobs are:

1. **audit:** invokes the script behind `box vendor-aur --all`, detects changes,
   runs the mechanical/provenance checks and exports a patch. This job holds
   no write token. A partial fetch failure with usable changes produces a
   candidate marked incomplete; failure before any changes produces no PR.
2. **publish:** applies the patch to an isolated Git index, checks the entire
   change stays under `aur/`, and reruns the trusted literal validator. It
   creates a commit with `git commit-tree` and pushes it without checking out
   candidate files. Successful checks produce an open `aur-bump` PR and a
   successful `aur-bump/eligible` status. Failed checks produce a **draft** PR
   labelled `aur-bump` + `needs-review`, with explanations in its body and a
   failing eligibility status. The complete change is in Files changed.
3. **prepare:** for eligible PRs only, independently verifies bot author,
   same head/base repo, main target, exact publisher branch/SHA, labels and
   status creator/run binding. It requires main's status rule to be bound to
   GitHub Actions (integration `15368`), fetches the candidate as Git objects,
   verifies its single parent is the publisher source, and reruns the trusted
   validator. It builds a diff with zero unchanged context, including removal
   of the source text Git normally appends to hunk headers.
4. **review:** launches a pinned Claude Code CLI in an empty temporary directory,
   with a fresh configuration directory and an explicit environment containing
   subscription OAuth but **no GitHub credentials**. `--safe-mode` disables
   auto-loaded instructions, hooks, skills and plugins; `--tools ""`,
   `--disallowedTools "*"` and an explicitly empty strict MCP configuration
   remove tool access. The model sees only the saved policy and the diff.
   PR descriptions, comments, reviews, commit messages, identifiers and
   unchanged repository content are not model input. It returns JSON containing
   only `verdict` and `reason`. Do not substitute `--allowedTools`, which only
   grants permission, or `--bare`, which does not support subscription OAuth.
   Execution or output errors fail the review job. Its result artifact is still
   uploaded after failure so the finish job can post a fixed diagnostic.
5. **finish:** uses ordinary code and a separate GitHub token to revalidate
   eligibility, the exact diff and the prompt, and match the request digest to
   the review result. PASS rechecks metadata immediately before an atomic
   SHA-bound squash merge, then explicitly dispatches `build.yml`: merges with
   `GITHUB_TOKEN` do not cause another push-triggered workflow. FAIL or missing/
   invalid/error output leaves the PR open, sets the eligibility status to
   failure, adds `needs-review` and posts an escaped explanation. Model output
   never selects a target, becomes shell code, or supplies arbitrary API fields.

The trusted implementation is `scripts/aur-review.py`; the policy is
[`.github/aur-vet-prompt.md`](../.github/aur-vet-prompt.md), loaded directly from
the same trusted workflow source revision. There is no separately deployed
prompt to synchronize. The CLI itself remains a trusted dependency: isolation
limits model tool access, not vulnerabilities in the executable or platform.
A false PASS about an eligible malicious release remains possible; human review
is the stronger control for semantic judgments that mechanical checks cannot
establish.

**Schedule and authorization.** The existing cron is `03:00 UTC`, or 04:00 in
Norwegian winter time and 05:00 in summer; GitHub may delay scheduled starts.
Only schedule and authorized manual dispatch on `main` are accepted. Opening,
editing or commenting on an outsider PR cannot start this workflow; running a
fork's copy does not grant access to this repository's credentials. Branches
include the date, run ID and publisher attempt and are never force-updated.
Labels are checked before review and again before merge; the SHA is enforced
atomically by GitHub. A label change after the final check is not itself an
atomic merge condition. Ordinary outside contributors cannot label PRs, but
trusted triage collaborators and suitably authorized apps can.

**Setup and migration.** Keep GitHub environment `aur-review` restricted to the
**branch** `main` (no tag rule). Generate subscription credentials with
`claude setup-token` and store the result only as its environment secret
`CLAUDE_CODE_OAUTH_TOKEN`. It is a one-year token; replace it before expiry.
The review job uses `@anthropic-ai/claude-code@2.1.267` and model alias `opus`.
Changing the CLI version or isolation flags requires rerunning the isolation
regressions and checking the installed CLI's supported behavior.

Keep main's required `aur-bump/eligible` source bound to GitHub Actions. The
workflow's tokens must have no bypass rights; they do not receive repository
administration permission. Other trusted workflows can still create Actions
statuses, so protect changes to workflow code, scripts and policy. CODEOWNERS
only adds owner review when the corresponding GitHub review rule is enabled.

After this version reaches main, disable the old Claude cloud routine and revoke
its API trigger token. Remove the retired `AUR_REVIEW_ROUTINE_TOKEN` secret and
`AUR_REVIEW_ROUTINE_ID` variable; keep them until migration to avoid breaking
old runs prematurely. Start a **new** workflow run after migration: rerunning
an old run executes its old workflow and code. The first live run created PR #6
but its isolated review returned ERROR and correctly left it unmerged. Successful
subscription inference remains unverified. The old trigger secret and variable
have been removed; ensure the old cloud routine is also disabled, since its
authority is separate from these workflow controls.

**Human review and recovery.** Nonroutine drafts are intentionally ineligible
for automated merging even if someone marks them ready or removes the label.
Their failing status requires a separately authorized human merge path after
review, such as pushing the reviewed result using a local deploy key with
bypass. Emptying the bypass list also blocks the owner's ordinary new commits
and non-AUR PRs. A bypass for the owner's identity may also apply to an agent
using that identity; keep human bypass credentials separate from cloud agents.

There are no automatic retries of GitHub writes or model calls. Check the PR
and run before retrying an ambiguous failure; the finish phase refuses a moved,
held or already-closed PR. A failed image-build dispatch after a confirmed merge
requires manually dispatching `build.yml`, not repeating the merge. Authentication
or installation errors still leave the existing PR available for human review.
The review log reports a fixed error category and explanation (missing secret,
authentication, access, usage limit, service, CLI arguments/startup, timeout or
invalid output). It never prints raw CLI output, session data or credentials.
The finish job copies only recognized, request-bound error explanations into the
PR comment; unknown or missing results get a generic error. A review ERROR makes
the job red even when the finish job successfully posts that comment; a valid
FAIL verdict is a completed review, not an execution failure. After deploying a
fix, start a **new** run on main. A PR already held with `needs-review` and a
failing status is not automatically retried; review or close the superseded PR
manually after inspecting the new candidate.
Malformed artifacts, changes outside `aur/`, or a patch exceeding the 16 MiB
publication limit stop publication safely; no process can promise to publish
an unavailable or unusable candidate. A model diff exceeding 128 KiB is held for
human review rather than truncated.

`scripts/test-aur-review.py` exercises rejected-candidate publication, binary/
symlink/scriptlet handling, model isolation, forged/stale/moved targets, invalid
verdicts, error comments, exact-SHA merges and image-build dispatch. The existing
`scripts/test-aur-validator.sh` tests the literal grammar and adversarial inputs.
Both run offline in CI. A future reminder based on the OAuth token's recorded
expiry could automate annual credential maintenance without exposing the token.

**1. Routine bumps change only PKGBUILDs and the manifest.** Changes to
`*.install`, `*.sh` or `*.patch` may be legitimate, but need a full human audit
because they can change executed build/install code:

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
