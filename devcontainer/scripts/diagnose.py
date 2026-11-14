#!/usr/bin/env python3
"""Run inside the dev container; write a shareable report without installing tools."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class Report:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w", encoding="utf-8")
        self.counts = Counter()

    def write(self, text=""):
        text = ANSI.sub("", str(text))
        self.file.write(text + "\n")
        self.file.flush()
        print(text, flush=True)

    def result(self, status, title, detail=""):
        self.counts[status] += 1
        self.write(f"[{status}] {title}")
        if detail:
            self.write(detail)

    def command(self, title, args, timeout=30, env=None, cwd=None):
        self.write("\n--- " + title + " ---")
        self.write("Command: " + " ".join(str(arg) for arg in args))
        try:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       errors="replace", start_new_session=True)
            try:
                output, _ = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    output, _ = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    output, _ = process.communicate()
                self.write(output[-16000:])
                self.result("FAIL", title, f"Timed out after {timeout}s; process group stopped.")
                return False
            self.write(output[-16000:].rstrip())
            self.result("PASS" if process.returncode == 0 else "FAIL", title,
                        f"Exit code: {process.returncode}")
            return process.returncode == 0
        except OSError as error:
            self.result("FAIL", title, str(error))
            return False


def diagnose(report):
    report.write("Development container diagnostic report")
    report.write("UTC: " + datetime.now(timezone.utc).isoformat())
    report.write("No remote Git operations or system/package installation are performed.")
    if sys.platform != "linux" or not Path("/.dockerenv").exists():
        report.result("FAIL", "Container context", "Run this script inside the Ubuntu development container.")
        return
    report.result("PASS", "Container context", "Linux Docker container detected.")
    report.write("\n--- Environment ---")
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    report.write("OS: " + release.get("PRETTY_NAME", "unknown").strip('"'))
    report.result("PASS" if release.get("VERSION_ID", "").strip('"') == "24.04" else "FAIL", "Ubuntu 24.04")
    name = pwd.getpwuid(os.getuid()).pw_name
    report.result("PASS" if name == "dev" and os.getuid() != 0 else "FAIL", "Non-root dev user",
                  f"user={name}; uid={os.getuid()}; gid={os.getgid()}; arch={os.uname().machine}")
    report.result("PASS" if os.environ.get("LANG") == "C.UTF-8" else "WARN", "UTF-8 locale",
                  "LANG=" + os.environ.get("LANG", "unset"))
    home = Path.home()
    mount_targets = {line.split()[4] for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    for directory in (Path("/workspace"), home / ".local/share/nvim", home / ".local/state"):
        writable = directory.is_dir() and os.access(directory, os.W_OK)
        report.result("PASS" if writable else "FAIL", f"Writable directory: {directory}")
        report.result("PASS" if str(directory) in mount_targets else "WARN", f"Mount point: {directory}")
    report.write("Mount checks cannot prove that data survives container recreation.")
    report.command("Passwordless sudo", ["sudo", "-n", "true"])

    report.write("\n--- Required executables ---")
    tools = ("zsh", "starship", "fzf", "nvim", "tree-sitter", "rg", "fd", "clang", "clang++",
             "clangd", "clang-format", "clang-tidy", "gdb", "cmake", "ninja", "make", "g++",
             "pkg-config", "python3", "git", "ssh", "curl", "unzip", "xz")
    for tool in tools:
        path = shutil.which(tool)
        report.result("PASS" if path else "FAIL", tool, str(path or "not found"))
    for tool in ("nvim", "clang", "clangd", "clang-format", "clang-tidy", "cmake", "python3", "tree-sitter"):
        if shutil.which(tool):
            report.command(tool + " version", [tool, "--version"])
    for tool in ("node", "npm"):
        path = shutil.which(tool)
        report.result("INFO", "Optional " + tool, path or "Absent; allowed with INSTALL_NODE=false.")

    report.command("Zsh configuration and widgets", ["zsh", "-ic", r'''
print -r -- "HISTFILE=$HISTFILE"
(( $+widgets[fzf-history-widget] )) || exit 1
(( $+functions[_zsh_autosuggest_start] )) || exit 1
(( $+functions[_zsh_highlight] )) || exit 1
[[ -d ${HISTFILE:h} && -w ${HISTFILE:h} ]] || exit 1
print -r -- 'fzf history, suggestions, highlighting, and writable history directory found'
'''])

    report.write("\n--- Git and SSH readiness (no network authentication) ---")
    if shutil.which("git"):
        for key in ("user.name", "user.email"):
            check = subprocess.run(["git", "-C", "/workspace", "config", "--get", key],
                                   capture_output=True, text=True)
            report.result("PASS" if check.returncode == 0 and check.stdout.strip() else "WARN",
                          "Git " + key, "Configured." if check.stdout.strip() else "Not configured.")
    if os.environ.get("SSH_AUTH_SOCK") and shutil.which("ssh-add"):
        try:
            result = subprocess.run(["ssh-add", "-l"], capture_output=True, timeout=10)
            report.result("PASS" if result.returncode == 0 else "WARN", "Forwarded SSH identities",
                          "Agent exposes identities." if result.returncode == 0 else "Agent has no identities or is inaccessible.")
        except (OSError, subprocess.TimeoutExpired) as error:
            report.result("WARN", "Forwarded SSH identities", str(error))
    else:
        report.result("WARN", "Forwarded SSH identities", "Not forwarded; allowed for local development.")

    with tempfile.TemporaryDirectory(prefix="robots-diagnostic-") as temp:
        work = Path(temp)
        (work / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.22)\nproject(robot_diag LANGUAGES CXX)\n"
            "add_executable(robot_diag main.cpp)\n")
        (work / "main.cpp").write_text(
            "int add(int a, int b) {\n  return a + b;\n}\n"
            "struct Robot {\n  int speed;\n  void stop() {}\n};\n"
            "int main() {\n  Robot robot{};\n  int result = add(2, 3);\n"
            "  return result == 5 ? 0 : 1;\n}\n")
        configured = report.command("CMake with Clang and compile database", [
            "cmake", "-S", str(work), "-B", str(work / "build"), "-G", "Ninja",
            "-DCMAKE_CXX_COMPILER=clang++", "-DCMAKE_BUILD_TYPE=Debug",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"])
        database = work / "build/compile_commands.json"
        if database.is_file():
            (work / "compile_commands.json").symlink_to(database)
            report.result("PASS", "Compilation database generated")
        else:
            report.result("FAIL", "Compilation database generated")
        built = configured and report.command("Compile C++ project", ["cmake", "--build", str(work / "build")])
        if built:
            executable = work / "build/robot_diag"
            report.command("Run compiled C++ executable", [str(executable)])
            report.command("GDB breakpoint and execution", ["gdb", "-q", "-batch",
                "-ex", "break main", "-ex", "run",
                "-ex", "python assert gdb.selected_frame().name() == 'main', 'Did not stop in main'",
                "--args", str(executable)])
        else:
            report.result("SKIP", "Executable and debugger tests", "The C++ project did not build.")
        if configured:
            report.command("clang-tidy analysis", ["clang-tidy", "-p", str(work / "build"), str(work / "main.cpp")])
        report.command("clang-format execution (no source edits)", ["clang-format", "--style=LLVM", str(work / "main.cpp")])
        venv = work / "venv"
        if report.command("Create Python virtual environment", ["python3", "-m", "venv", str(venv)]):
            report.command("Virtual environment pip", [str(venv / "bin/python"), "-m", "pip", "--version"])
            report.command("Python script execution", [str(venv / "bin/python"), "-c", "assert sum([1, 2, 3]) == 6; print('Python OK')"])

        if shutil.which("nvim"):
            config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "nvim"
            if not any((config / name).is_file() for name in ("init.lua", "init.vim")):
                report.result("WARN", "Personal Neovim configuration", "Plain Neovim mode; personal LSP tests skipped.")
            elif not database.is_file():
                report.result("SKIP", "Personal Neovim and clangd tests", "Missing compilation database.")
            else:
                scripts = Path(__file__).resolve().parent
                env = dict(os.environ, DIAG_WORK=str(work), DIAG_RESULT=str(work / "nvim-results.json"),
                           DIAG_CONFIG=str(config), DIAG_PROBE=str(scripts / "diagnose-nvim.lua"))
                result_path = work / "nvim-results.json"
                report.command("Actual Neovim configuration and clangd integration", [
                    "nvim", "--headless", "-i", "NONE", "-n", "-u", str(scripts / "diagnose-init.lua"),
                    "-c", "lua vim.schedule(function() dofile(vim.env.DIAG_PROBE) end)"],
                    timeout=120, env=env, cwd=work)
                if result_path.exists():
                    try:
                        records = json.loads(result_path.read_text())
                        for record in records:
                            report.result(record["status"], record["title"], record.get("detail", ""))
                    except (ValueError, KeyError, TypeError) as error:
                        report.result("FAIL", "Neovim structured report", str(error))
                else:
                    report.result("FAIL", "Neovim structured report", "No result file was produced; inspect startup output above.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("/workspace/.dev-reports/dev-report.txt"),
                        help="Output text file (overwritten); default: /workspace/.dev-reports/dev-report.txt")
    args = parser.parse_args()
    report_path = args.report.expanduser().resolve()
    try:
        report = Report(report_path)
    except OSError as error:
        parser.error(f"Cannot open report: {error}")
    try:
        diagnose(report)
    except Exception as error:
        import traceback
        report.result("FAIL", "Unexpected diagnostic error", traceback.format_exc())
    finally:
        report.write("\n=== Summary ===")
        report.write(" ".join(f"{key}={report.counts[key]}" for key in ("PASS", "FAIL", "WARN", "SKIP", "INFO")))
        report.write("Not tested: interactive key/clipboard behavior, remote Git authentication, persistence across recreation.")
        report.write("Python LSP is not required yet; this stage tests Python execution and C++ editor integration.")
        report.write("Report saved to: " + str(report_path))
        report.file.close()
    return 1 if report.counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
