#!/bin/sh
# Execution context: sourced by EVERY shell in the box — interactive or not,
# login or not, as any user. It is wired up in two places by Containerfile.base:
#   /etc/zsh/zshenv      → all zsh invocations, including `zsh -c ...`
#   /etc/profile.d/       → bash/sh login shells
#
# Because of that reach it must stay POSIX sh, silent, fast, and free of
# `set -e` (a failure here would break every shell in the box).
#
# Coverage, stated plainly: zsh is complete (zshenv is read by every zsh), bash
# and sh are login-only. The residual gap is a *non-login, non-interactive* bash
# whose ancestry never passed through a configured shell — a systemd user unit,
# say — because everything else inherits these vars through the environment.
# `BASH_ENV` would close it and is deliberately not used: ssh and sudo strip it,
# so it would not hold across exactly the hops that matter here, and it makes
# every non-interactive bash source a file, which surprises scripts. zsh is the
# login shell in every box, so the gap is theoretical today; if something real
# lands in it, the fix is a systemd user environment generator, not BASH_ENV.
#
# Only environment that NON-INTERACTIVE shells also need belongs here. Anything
# interactive — prompts, aliases, service startup, anything needing a TTY —
# belongs in shell-init.sh, which is sourced from ~/.zshrc instead.
#
# Changes take effect on the next base-image rebuild + `box upgrade <box>`.

# --- Per-box tmux server ---
# distrobox bind-mounts the host's /tmp into every box, and tmux derives its
# socket from $TMUX_TMPDIR (default /tmp) as $TMUX_TMPDIR/tmux-$UID/default. So
# out of the box the host and all boxes address the ONE SAME tmux server.
#
# That is not cosmetic: tmux forks new panes from the *server's* environment,
# not the client's. A pane opened from workbox while the server happened to be
# started from privbox inherits privbox's HOME and PATH — programs then run
# against the wrong home, find none of their config, and fail in confusing ways.
#
# Pointing TMUX_TMPDIR under $HOME gives each environment its own server,
# because every box mounts a different host directory as $HOME.
#
# Why $HOME and not $XDG_RUNTIME_DIR: that is a container-private tmpfs, so the
# box's socket would be invisible from the host and `ssh <host>` + `tmux attach`
# would stop working. Box homes live under ~/distrobox/<box>/home and are
# visible from the host at the same path, which keeps that workflow intact.
#
# Why .local/state and not ~/.tmux: ~/.tmux is already tmux's own namespace —
# ~/.tmux.conf is its config file and ~/.tmux/plugins/ is where TPM installs —
# so putting sockets there would give one directory two unrelated jobs. State
# is also the honest XDG category for a socket dir we cannot put in
# XDG_RUNTIME_DIR, and ~/.local/state is conventionally excluded from backups
# and snapshots, which a btrfs home would otherwise drag sockets into.
# Deliberately NOT $XDG_STATE_HOME: that variable is inherited by
# `distrobox enter`, so honouring it would let one environment's value point
# another environment's tmux at a shared directory — the same trap as
# inheriting TMUX_TMPDIR itself. Deriving strictly from $HOME is what makes the
# whole scheme hold. Set TMUX_TMPDIR directly to override.
#
# The assignment is deliberately unconditional rather than "only if unset":
# `distrobox enter` inherits the host's environment, so honouring an inherited
# TMUX_TMPDIR would put the box back on the host's server — the exact bug this
# fixes. Per-command overrides still work (`TMUX_TMPDIR=/tmp tmux attach`)
# because they set the variable on tmux itself, not on a shell.
if [ -n "${HOME:-}" ]; then
    TMUX_TMPDIR="$HOME/.local/state/tmux"
    export TMUX_TMPDIR
    [ -d "$TMUX_TMPDIR" ] || mkdir -p "$TMUX_TMPDIR" 2>/dev/null || true
fi
