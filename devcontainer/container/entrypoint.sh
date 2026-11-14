#!/usr/bin/env bash
set -euo pipefail
# A published image cannot bake in every Linux developer's UID/GID. Bootstrap as
# root, map dev once at startup, then execute the requested command as dev.
[[ $(id -u) == 0 ]] || { echo 'Run the image entrypoint as root; it drops privileges to dev.' >&2; exit 1; }
target_uid=${DEV_HOST_UID:-1000}
target_gid=${DEV_HOST_GID:-1000}
for value in "$target_uid" "$target_gid"; do
    [[ "$value" =~ ^[0-9]+$ && "$value" -gt 0 ]] || { echo 'Host UID/GID must be positive non-root integers.' >&2; exit 1; }
done
existing=$(getent passwd "$target_uid" | cut -d: -f1 || true)
[[ -z "$existing" || "$existing" == dev ]] || { echo "Host UID $target_uid conflicts with image user $existing." >&2; exit 1; }
if ! getent group "$target_gid" >/dev/null; then
    groupadd --gid "$target_gid" "host-${target_gid}"
fi
if [[ $(id -u dev) != "$target_uid" ]]; then
    # usermod normally chowns the home recursively. Temporarily detach the home
    # so it cannot traverse the developer's mounted personal configuration.
    usermod --home /nonexistent dev
    usermod --uid "$target_uid" dev
    usermod --home /home/dev dev
fi
if [[ $(id -g dev) != "$target_gid" ]]; then
    usermod --gid "$target_gid" dev
fi
for directory in /home/dev /home/dev/.config /home/dev/.local /home/dev/.local/share; do
    chown "$target_uid:$target_gid" "$directory"
done
for directory in /home/dev/.local/share/nvim /home/dev/.local/state; do
    if [[ $(stat -c '%u:%g' "$directory") != "$target_uid:$target_gid" ]]; then
        chown -R "$target_uid:$target_gid" "$directory"
    fi
done
mkdir -p /home/dev/.local/state/zsh /home/dev/.local/state/ssh
chown "$target_uid:$target_gid" /home/dev/.local/state/zsh /home/dev/.local/state/ssh
chmod 700 /home/dev/.local/state/ssh
as_dev=(setpriv --reuid=dev --regid="$target_gid" --init-groups env HOME=/home/dev USER=dev LOGNAME=dev)
# Generate only identity defaults; never import host helpers, config files, or keys.
if [[ -n ${HOST_GIT_NAME:-} ]]; then "${as_dev[@]}" git config --global user.name "$HOST_GIT_NAME"; fi
if [[ -n ${HOST_GIT_EMAIL:-} ]]; then "${as_dev[@]}" git config --global user.email "$HOST_GIT_EMAIL"; fi
exec "${as_dev[@]}" "$@"
