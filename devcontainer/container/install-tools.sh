#!/usr/bin/env bash
set -euo pipefail

# Keep release URLs and checksums together when upgrading.
nvim_version=0.12.6
treesitter_version=0.27.2
starship_version=1.27.0
node_version=26.13.1
install_node=${1:-false}
case "$install_node" in true|false) ;; *) echo 'INSTALL_NODE must be true or false' >&2; exit 1;; esac
case "$(dpkg --print-architecture)" in
    arm64) nvim_arch=arm64; tree_arch=arm64; starship_arch=aarch64; node_arch=arm64 ;;
    amd64) nvim_arch=x86_64; tree_arch=x64; starship_arch=x86_64; node_arch=x64 ;;
    *) echo 'This image currently supports ARM64 and AMD64 only.' >&2; exit 1 ;;
esac
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
checksums=/tmp/dev-tools/checksums.txt
fetch() {
    local url=$1 file=$2
    curl --fail --location --retry 3 --output "$file" "$url"
    awk -v file="$file" '$2 == file { print; found=1 } END { if (!found) exit 1 }' "$checksums" | sha256sum --check --strict
}

file="nvim-linux-${nvim_arch}.tar.gz"
fetch "https://github.com/neovim/neovim/releases/download/v${nvim_version}/${file}" "$file"
mkdir -p /opt/nvim
tar -xzf "$file" --strip-components=1 -C /opt/nvim
ln -s /opt/nvim/bin/nvim /usr/local/bin/nvim

file="tree-sitter-linux-${tree_arch}.gz"
fetch "https://github.com/tree-sitter/tree-sitter/releases/download/v${treesitter_version}/${file}" "$file"
gzip -dc "$file" > /usr/local/bin/tree-sitter
chmod 755 /usr/local/bin/tree-sitter

file="starship-${starship_arch}-unknown-linux-musl.tar.gz"
fetch "https://github.com/starship/starship/releases/download/v${starship_version}/${file}" "$file"
tar -xzf "$file" -C /usr/local/bin starship

if [[ "$install_node" == true ]]; then
    file="node-v${node_version}-linux-${node_arch}.tar.xz"
    curl --fail --location --retry 3 --output "$file" "https://nodejs.org/dist/v${node_version}/${file}"
    curl --fail --location --retry 3 --output SHASUMS256.txt "https://nodejs.org/dist/v${node_version}/SHASUMS256.txt"
    awk -v file="$file" '$2 == file { print; found=1 } END { if (!found) exit 1 }' SHASUMS256.txt | sha256sum --check --strict
    tar -xJf "$file" --strip-components=1 -C /usr/local
fi
nvim --version | sed -n '1,3p'
tree-sitter --version
starship --version
