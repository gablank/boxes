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

The same re-vendoring also runs nightly at 21:28 UTC in
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

**Who this is defending against.** The upstream developers are trusted: if a
recipe downloads a release from the vendor's own server and checks it against a
checksum, what is inside that download is not what this review is for. The **AUR
packager is not trusted.** Everything the packager controls is text in the diff,
and that text runs at moments that matter -- `*.install` scriptlets run as root
during the image build, `google-cloud-cli.sh` is installed to `/etc/profile.d`
and sourced by every login shell in every box, `rg.sh` is installed *over*
ripgrep inside Cursor, and the `herdr-bin` completion files are sourced into
every interactive shell. Reading that text is the whole control.

Note what the provenance check does and does not prove. It establishes that the
vendored copy is byte-identical to upstream AUR at the pinned commit -- that we
are reviewing what the packager actually published, not something injected in
transit. It says nothing about whether the packager should be trusted, which is
the question this audit exists to answer.

The mechanical checks run in `aur-bump.yml`: the tier classifier checks paths,
modes, every added/removed line and whether versions move forward, and a
separate provenance check compares vendored files against their pinned AUR
commits. Neither executes a recipe. A failed gate does **not** discard the
candidate.

### Review tiers

`scripts/validate-aur-diff.py` sorts every change into one of three tiers, and
the tier decides who reads it. Run it yourself on a manual bump:

```bash
python3 scripts/validate-aur-diff.py --worktree
```

| Tier | What it is | Who reads it |
| --- | --- | --- |
| **A** | Every changed line a complete literal version/checksum/manifest update in an existing PKGBUILD, every version moving forward | Isolated review against `.github/aur-vet-prompt.md`, then merged |
| **B** | Bounded packager-authored recipe content: text edits or additions inside an already-vendored package, ≤400 changed lines and ≤20 files | Isolated review against `.github/aur-review-prompt.md` with the diff **and the whole of every changed file**, then merged on PASS |
| **C** | Everything else | A human, always |

Tier A is safe to merge on a grammar check for a specific reason: no `source=`
line can change without leaving the tier, so the download host stays pinned to
the value a human reviewed. What a packager *can* still do within those pinned
URLs is choose an older artifact, since `pkgver` and `_commit` are interpolated
into them -- which is why tier A also requires every version to move strictly
forward, using a `vercmp` port (CI runs on Ubuntu, which has no pacman).

Tier C is not a fallback for "unusual"; these shapes are excluded from model
review deliberately:

- deletions, renames, mode or type changes, binary content, symlinks;
- a brand-new vendored package (adding one is a manual pull request);
- control characters in a changed line, or content that is not valid UTF-8;
- more than 400 changed lines or 20 files -- a long, plausible refactor in which
  every line is individually benign is the shape a line-by-line reviewer misses;
- a version that does not move forward: telling a downgrade attack from a
  legitimate upstream revert needs the upstream history, which the isolated
  reviewer is deliberately not given;
- a `SKIP` checksum being introduced, which disables integrity checking;
- a non-literal `pkgver`/`pkgrel`/`_commit`/`sha*sums` assignment -- the
  2026-09-08 finding, `pkgver=1.2.3$(...)`, which is both a version and a
  command. There is no legitimate form of that line, so trusted code rejects it
  rather than asking anyone's judgment;
- any change to a `source=`, `noextract=`, `install=` or `validpgpkeys=`
  assignment. These decide where an artifact comes from and what runs as root at
  install time. They change roughly once a year per package, so the cost of
  always sending them to a human is one review a year, and the cost of getting
  one wrong is every image.

Do not widen tier A or route tier C to the model to reduce noise. If tier B is
producing too many reviews, the answer is to look at what is landing there.

<a id="where-the-vetter-lives"></a>

**Where the vetter lives.** Review runs inside the AUR GitHub Actions workflow,
using Claude Code with subscription OAuth. The five jobs are:

1. **audit:** invokes the script behind `box vendor-aur --all`, detects changes,
   runs the tier/provenance checks and exports a patch. This job holds
   no write token. A partial fetch failure with usable changes produces a
   candidate marked incomplete; failure before any changes produces no PR.
2. **publish:** applies the patch to an isolated Git index, checks the entire
   change stays under `aur/`, and reclassifies the candidate itself rather than
   trusting the audit job's tier. It creates a commit with `git commit-tree`
   and pushes it without checking out candidate files. Tier A and B produce an
   open `aur-bump` PR and a successful `aur-bump/eligible` status. Tier C, a
   failed provenance check, or incomplete vendoring produce a **draft** PR
   labelled `aur-bump` + `needs-review`, with explanations in its body and a
   failing eligibility status. The complete change is in Files changed.
3. **prepare:** for eligible PRs only, independently verifies bot author,
   same head/base repo, main target, exact publisher branch/SHA, labels and
   status creator/run binding. It requires main's status rule to be bound to
   GitHub Actions (integration `15368`), fetches the candidate as Git objects,
   verifies its single parent is the publisher source, and reclassifies it a
   third time. For tier A it builds a diff with zero unchanged context,
   including removal of the source text Git normally appends to hunk headers.
   For tier B it builds the diff with context plus the complete current text of
   every changed file, since a hunk of packager-authored shell cannot be judged
   without its neighbours; every section is fenced with the candidate's own
   commit hash, which no file inside it can predict, so nothing in the content
   can pass itself off as trusted preamble. A tier C candidate has no policy and
   stops here.
4. **review:** launches a pinned Claude Code CLI in an empty temporary directory,
   with a fresh configuration directory and an explicit environment containing
   subscription OAuth but **no GitHub credentials**. `--safe-mode` disables
   auto-loaded instructions, hooks, skills and plugins; `--tools ""`,
   `--disallowedTools "*"` and an explicitly empty strict MCP configuration
   remove tool access. The model sees only the policy saved for that tier and
   the payload that tier defines. PR descriptions, comments, reviews, commit
   messages, identifiers and repository content outside the changed files are
   not model input. It returns JSON containing only `verdict` and `reason`. Do
   not substitute `--allowedTools`, which only grants permission, or `--bare`,
   which does not support subscription OAuth.
   Execution or output errors fail the review job. Its result artifact is still
   uploaded after failure so the finish job can post a fixed diagnostic.
5. **finish:** uses ordinary code and a separate GitHub token to revalidate
   eligibility, the tier, the exact payload and the prompt, and match the
   request digest to the review result. Because the digest covers the tier and
   its policy, a verdict earned under one tier can never be spent on another. PASS rechecks metadata immediately before an atomic
   SHA-bound squash merge, then explicitly dispatches `build.yml`: merges with
   `GITHUB_TOKEN` do not cause another push-triggered workflow. FAIL or missing/
   invalid/error output leaves the PR open, sets the eligibility status to
   failure, adds `needs-review` and posts an escaped explanation. Model output
   never selects a target, becomes shell code, or supplies arbitrary API fields.

The trusted implementation is `scripts/aur-review.py`; the policies are
[`.github/aur-vet-prompt.md`](../.github/aur-vet-prompt.md) for tier A and
[`.github/aur-review-prompt.md`](../.github/aur-review-prompt.md) for tier B,
loaded directly from the same trusted workflow source revision. There is no
separately deployed prompt to synchronize. The CLI itself remains a trusted dependency: isolation
limits model tool access, not vulnerabilities in the executable or platform.
A false PASS about an eligible malicious release remains possible; human review
is the stronger control for semantic judgments that mechanical checks cannot
establish.

**Schedule and authorization.** The cron is `28 21 * * *`: 21:28 UTC the evening
before, or 22:28 in Norwegian winter time and 23:28 in summer. That is ~5 hours
ahead of when the work should actually land, on purpose. GitHub's shared
scheduler has been creating these runs 4-5 hours after the cron fires, so the
cron absorbs that backlog instead of chasing it; a run that does fire on time
just finishes overnight, which costs nothing. Minute 28 avoids the busy start of
the hour, but GitHub may still delay or drop scheduled runs.
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
but its isolated review returned ERROR and correctly left it unmerged. After
correcting a line break in the OAuth secret, run `34513533988` reviewed and
merged PR #9 and dispatched the image build, verifying the complete pipeline.
The old trigger secret and variable
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
an unavailable or unusable candidate. A tier A diff exceeding 128 KiB, or a tier B
payload exceeding 384 KiB, is held for human review rather than truncated.

`scripts/test-aur-review.py` exercises rejected-candidate publication, binary/
symlink/scriptlet handling, model isolation, per-tier payloads and policies,
cross-tier verdict replay, unreadable candidate bytes, forged/stale/moved
targets, invalid verdicts, error comments, exact-SHA merges and image-build
dispatch. `scripts/test-aur-validator.sh` asserts the tier of every known change
shape -- a case drifting from C to B hands a human's decision to a model, and
from B to A removes the review altogether.
Both run offline in CI. A future reminder based on the OAuth token's recorded
expiry could automate annual credential maintenance without exposing the token.

**1. See which files changed.** A tier A bump touches only PKGBUILDs and the
manifest. Changes to `*.install`, `*.sh` or `*.patch` may be legitimate, but
they change executed build/install code, so they are tier B at best:

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

The classifier is what `aur-bump.yml` gates on. Run it yourself on a manual
bump: tier A means every changed line is a literal version, checksum or manifest
update and every version moves forward, which is the part worth automating. It
cannot tell you whether the new upstream release is trustworthy -- that is what
the rest of this list is for.

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
  `aur-builder` stage of `Containerfile.base`, ending in `mv ./*.pkg.tar* /out/` so
  the final stage installs it.
- **Remove:** delete `aur/<pkgbase>/`, drop its row from `manifest.tsv`, and
  remove its build step from `Containerfile.base`.
