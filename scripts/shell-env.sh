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

# --- Host session D-Bus and PulseAudio ---
# These live here, not in shell-init.sh, because of a strict ordering
# requirement: distrobox's own /etc/profile.d/distrobox_profile.sh defaults
# DBUS_SESSION_BUS_ADDRESS to unix:path=/run/user/$UID/bus and then calls
# `host-spawn` four times to import XAUTHORITY/XAUTHLOCALHOSTNAME/
# WAYLAND_DISPLAY/DISPLAY from the host. host-spawn reaches the host over that
# very bus. In a NO-INIT box (dev) the guess happens to be right: distrobox
# bind-mounts the host's /run/user/$UID, so the socket is there. In an INIT box
# (priv, work) /run is a fresh tmpfs and the host's runtime dir is only under
# /run/host, so every login shell opened with
#   dial unix /run/user/1000/bus: connect: no such file or directory
# and the display variables were silently lost. (Before host-spawn was shipped
# in the image the same shells printed "command not found: host-spawn" instead
# — installing it turned a missing binary into a failing one.)
# shell-init.sh sets the same variable correctly but is sourced from ~/.zshrc,
# which runs *after* /etc/profile.d — too late. /etc/zsh/zshenv is read before
# anything else by every zsh, and box-env.sh sorts before distrobox_profile.sh
# in /etc/profile.d, so setting it here wins in both shells.
#
# Pointing at the host's bus is also what makes xdg-desktop-portal work
# (screen sharing, notifications); /etc/environment carries the same value for
# desktop-launched apps, which bypass shell init entirely.
_box_host_runtime="/run/host${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -S "${_box_host_runtime}/bus" ]; then
    DBUS_SESSION_BUS_ADDRESS="unix:path=${_box_host_runtime}/bus"
    export DBUS_SESSION_BUS_ADDRESS
fi
# The container's own /run/user/$UID/pulse socket is created by distrobox-enter
# but connected to nothing in an init box, so aim clients at the host's.
if [ -S "${_box_host_runtime}/pulse/native" ]; then
    PULSE_SERVER="unix:${_box_host_runtime}/pulse/native"
    export PULSE_SERVER
fi
unset _box_host_runtime
