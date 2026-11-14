#!/usr/bin/env bash
set -euo pipefail
[[ $(id -un) == dev ]]
[[ $PWD == /workspace ]]
[[ $LANG == C.UTF-8 ]]
for tool in zsh starship fzf nvim tree-sitter rg fd clang clang++ clangd clang-format clang-tidy gdb cmake ninja make g++ pkg-config python3 git ssh curl unzip xz; do
    command -v "$tool" >/dev/null
done
for directory in /workspace /home/dev/.local/share/nvim /home/dev/.local/state; do
    [[ -w "$directory" ]]
done
sudo -n true
nvim --headless -u NONE '+lua assert(vim.fn.has("nvim-0.12") == 1)' +qa

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/CMakeLists.txt" <<'CMAKE'
cmake_minimum_required(VERSION 3.22)
project(dev_smoke LANGUAGES CXX)
add_executable(dev_smoke main.cpp)
CMAKE
cat > "$work/main.cpp" <<'CPP'
#include <iostream>
int main() {
    std::cout << "C++ toolchain works\n";
    return 0;
}
CPP
cmake -S "$work" -B "$work/build" -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$work/build"
"$work/build/dev_smoke"
clang-tidy -p "$work/build" "$work/main.cpp" --quiet
# Confirm that ptrace actually works, not just that GDB is installed.
if ! gdb -q -batch -ex 'break main' -ex run --args "$work/build/dev_smoke" > "$work/gdb.log" 2>&1; then
    cat "$work/gdb.log" >&2
    exit 1
fi
if ! rg -q 'Breakpoint 1, main' "$work/gdb.log"; then
    cat "$work/gdb.log" >&2
    exit 1
fi
python3 -m venv "$work/venv"
"$work/venv/bin/python" -m pip --version
"$work/venv/bin/python" -c 'print("Python virtual environment works")'
zsh -ic '[[ -n ${widgets[fzf-history-widget]:-} ]] && [[ -n ${ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE:-} ]]'
printf 'Toolchain smoke checks passed. Personal editor plugins and remote Git authentication need separate verification.\n'
