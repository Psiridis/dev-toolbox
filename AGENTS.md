# Shared development toolchain: implementation guidance

Read this file before changing the environment. [README.md](README.md) is the
short user guide; [docs/maintenance.md](docs/maintenance.md) explains releases and
migration. Keep documentation consistent with implementation and observed results.

## Purpose and boundaries

This repository provides one reusable tools image and a shared host launcher for
many independent application repositories. It is not a robotics application or a
project-specific container template to duplicate in every application.

- Shared baseline: Ubuntu, terminal, Neovim executable, Git, C++ toolchain, Python,
  general search/download tools, diagnostics, and optional Node.js support.
- Consumer repositories: application code, CMake, tests, dependency declarations,
  project-specific derived images, runtime services, and versioned tools-image pin.
- Personal configuration: host Neovim settings/keymaps/plugins, Git identity, and
  credentials. Do not bake them into an image or commit local `.env` files.
- ROS 2, device/GPU access, VS Code integration, tmux, and unrelated languages are
  deferred. Add them when a concrete requirement exists, not to clear optional
  health warnings.
- Preserve the user's preference for incremental, explained changes. Reuse settled
  defaults; distinguish suggestions, implemented features, and verified behavior.
- Keep toolbox documentation application-agnostic. Use generic consumer examples;
  individual projects' names and specific setup instructions belong in their own repositories.

## Architecture and compatibility contract

| Decision | Requirement |
| --- | --- |
| Base | Ubuntu 24.04 LTS, `C.UTF-8`. |
| CPU | Native ARM64/AMD64, with multi-architecture releases. |
| Workspace | Selected external project bound to `/workspace`, the working directory. |
| User | Tools, shell, compiler, and editor run as `dev`, home `/home/dev`. |
| Bootstrap | Root only to map runtime UID/GID and prepare managed storage, then drop privileges. |
| Sudo | Passwordless for initial development; permanent changes belong in images. |
| Runtime | Local Docker Desktop on macOS or local native Docker on Linux. |
| State | Per-workspace and per-architecture containers/volumes; shared image layers. |
| Image release | Explicit stable version/digest; no default `latest`. |

`up` must not build the shared image. `build` must not depend on or build the
application's overlay. `project-build` deliberately builds a consumer's derived
image when configured. A consumer only needs its small project Compose overlay,
not the tools Dockerfile or copies of maintenance scripts.

The current launcher requires a shared host checkout. A published tools image
alone does not install the host launcher. The image itself embeds its checks and
can be used by other launchers with the documented workspace/user contract.

Forcing AMD64 can support proprietary dependencies or target testing, but adds
emulation cost and possible debugging limitations. This launcher currently
rejects conflicting `DOCKER_DEFAULT_PLATFORM`; do not claim emulated execution
is implemented. If adding it, isolate state/builds by the actual target
architecture and verify each affected tool. Do not infer portability from a
successful native ARM64 test alone.

## File responsibilities

| Location | Responsibility |
| --- | --- |
| `VERSION` | Stable shared image version and default local tag. |
| `dev` | Host detection, workspace/options, settings, Git/agent integration, lifecycle. |
| `devcontainer/Dockerfile` | Reusable image only; no application source. |
| `devcontainer/Dockerfile.dockerignore` | Allow only required image inputs from repository root context. |
| `devcontainer/container/` | Selected release installers/checksums, bootstrap, shell defaults. |
| `devcontainer/compose.yaml` | Image-based runtime defaults, no build configuration. |
| `devcontainer/compose.build.yaml` | Build context/arguments used only by shared `build`. |
| `devcontainer/compose.image.yaml` | Explicit CLI/env image override after project overlay. |
| `devcontainer/compose.nvim.yaml`, `compose.ssh.yaml` | Optional personal mounts. |
| `devcontainer/scripts/` | Smoke tests, diagnostic runner/Lua probes, local regression tests. |
| `devcontainer/examples/` | Optional personal settings; never automatically installed. |
| `templates/project/` | Consumer Compose example, ignore patterns, and usage/derivation guide. |
| `.github/workflows/ci.yml` | Native AMD64/ARM64 and base/Node image validation. |
| `.github/workflows/release.yml` | After validation, publish versioned GHCR images on release tags. |
| `docs/maintenance.md` | Release, upgrade, and migration instructions. |
| `docs/versioning.md` | Authoritative release-version flow and consumer upgrade procedure. |
| `reports/` | Git-ignored historical reports, retained for reference. |

Keep Bash compatible with macOS system Bash. Normal startup must not require
host Python, Neovim, Node.js, or GNU-only host tools. Python is allowed for tests.
Never source `.env`, use eval on settings, or interpolate configuration into
executable shell text. Preserve spaces in paths. Resolve workspaces canonically.

## Workspace and settings semantics

- Default workspace is the caller's current directory; `--workspace PATH` selects
  an existing external directory. Never create an accidentally misspelled path.
- `.env` is read from the selected workspace only. The tools repo's settings must
  not leak into other applications. Pass its env-file explicitly through Compose.
- Runtime merge order: shared defaults, auto-detected `compose.dev.yaml` or explicit
  `--compose`, explicit image override, optional Neovim and SSH integration.
- Relative consumer overlay paths use the selected application as Compose project
  directory. Shared image builds use absolute `DEV_ENV_ROOT` as build context.
- Image selection: `--image` overrides `DEV_IMAGE`; either overrides the project's
  committed default. Otherwise use its pin, or local `dev-toolchain:<VERSION>`.
  `INSTALL_NODE=true` changes the local fallback to `<VERSION>-node`, not a
  consumer's committed registry pin.
- Namespace: `--project-name`, then `DEV_PROJECT_NAME`, otherwise workspace basename
  plus checksum of canonical absolute path. Equal basenames must not share state;
  symlink aliases of the same path must resolve to the same namespace.
- Architecture is part of volume names. Keep naming stable across lifecycle
  commands. Moving a workspace needs explicit namespace reuse or migration.
- Never add a fixed container name or a single shared mutable editor volume for
  all projects. Do not implicitly reset or migrate volumes.

The former default `robots-*` volumes remain untouched. `--project-name robots`
can reuse them for the original workspace, not for all new applications. Explain
this intentional namespace change; absence of old plugins in a new project is
fresh isolated storage, not evidence of deleted data.

## Identity, permissions, and credentials

A shared published image cannot encode every Linux developer's UID/GID. The
entrypoint starts as root, validates non-root numeric host IDs, rejects conflicts,
updates `dev`, and uses `setpriv` before executing commands. Linux supplies host
IDs; Docker Desktop on macOS uses 1000/1000. The launcher explicitly uses
`exec --user dev` for shell, checks, and diagnostics. Raw exec callers also need
to select `dev` because image bootstrap metadata is root.

Never recursively chown the host project or personal editor configuration.
When changing UID, detach the passwd home first in a separate command: usermod's
normal recursive home ownership behavior must not traverse the Neovim mount.
Chown only known image-owned home parents and managed tool/state volumes. CI
covers a non-default UID/GID with a read-only personal-config mount and writable
external workspace. Bootstrap changes require real runtime testing, not only
shell syntax checks.

Keep passwordless sudo as the accepted development policy. It can be removed and
the image rebuilt for mature projects, but Docker daemon access can still launch
root processes. A future deployed runtime is a separate image/security decision.
`SYS_PTRACE` is enabled for debugging; do not switch to privileged mode or disable
seccomp merely to suppress GDB's ASLR warning when breakpoints already work.

Git defaults come from the selected application's effective host author name and
email. Import those values only, not a whole host Git config or credential helpers.
Missing identity yields guidance. Forward a loaded host SSH agent optionally;
missing/inaccessible identities must not block startup. `FORWARD_SSH_AGENT=false`
opts out. Host private keys are never copied into images, workspaces, or volumes.
Use SSH remotes and retain server host-key checking. Forwarded sockets permit
agent operations from trusted container processes; do not forward to untrusted images.

Docker Desktop uses `/run/host-services/ssh-auth.sock`; native Linux uses the host
agent socket. Colima/remote-engine support is not implemented. `docker login`
for a registry is separate from Git SSH authentication and author identity.

## Personal editor and persistent data

Neovim is in the image; LazyVim comes from a personal configuration, not an
image-owned plugin setup. Default host path is `~/.config/nvim`; an absolute
`NVIM_CONFIG_PATH` overrides it. Mount only if `init.lua` or `init.vim` exists.
Missing/empty configuration gives a message and plain Neovim without creating
host directories. Invalid existing configurations stay visible for diagnosis;
do not replace them automatically.

Mount configuration writable at `/home/dev/.config/nvim` so personal edits and
`lazy-lock.json` changes persist on the host. Never mount host Neovim data/cache:
macOS binaries may not run on Linux. Linux plugins/Mason/parsers live in a named
volume at `.local/share/nvim`; editor state, Zsh history, and verified SSH server
trust live in a named `.local/state` volume. `.cache/nvim` is disposable.
Per-project volumes allow different projects/images to coexist without racing
updates to one shared binary/tool directory. Personal configurations must still
support the selected Linux/Neovim versions. Icon fonts belong in the host terminal.

`lang.clangd` and the optional example override use `/usr/local/bin/clangd` with
Mason management disabled while preserving the extra's flags. The user copied
that override and disabled unused LuaRocks support in personal settings. Those
are not universal image settings. Load `nvim-lspconfig` or open a C++ file before
inspecting lazy-loaded `vim.lsp.config.clangd`.

## Toolchain and releases

Preserve Zsh, Starship, fzf, suggestions, command highlighting, UTF-8, and history
search. fzf's functional Zsh files ship in Ubuntu's documentation tree: preserve
that dpkg exception and the image's build-time readability checks. Keep a compact
prompt without mandatory special fonts. `fd-find` must be exposed as `fd`.

C++: Clang/clang++, clangd, clang-format, clang-tidy, GDB, CMake, Ninja,
build-essential, pkg-config. Prefer Clang through CC/CXX, retaining GCC/G++.
Use Debug builds and compilation databases for editor/analysis flags. Project
format/analysis policies belong in `.clang-format`/`.clang-tidy`; keymaps are
personal. Python: python3, pip, venv; use project virtual environments, never
system pip installs, and do not reuse Mac virtual environments inside Linux.

Selected upstream versions: Neovim 0.12.6, LLVM 18, Tree-sitter CLI 0.27.2,
Starship 1.27.0, optional Node.js 26.13.1 LTS. The installer and checksums are the
source of truth. Keep LLVM tools aligned. Deliberately upgrade compatible versions
and both architectures; allow Ubuntu security package revisions to advance.
Update release hashes with downloads. Optional Node uses its upstream release
checksum manifest; Neovim/Tree-sitter/Starship use recorded archive hashes.

`INSTALL_NODE=false` remains the default. Enable it only for an identified plugin
or language-server dependency and document that reason; arbitrary personal plugin
requirements are not automatically detectable. Publish separate base and `-node`
variants. Do not install Ruby, Go, Java, image/LaTeX tools, lazygit, or LuaRocks
merely because optional health checks mention them.

Keep releases versioned through `VERSION`. Tag pushes matching `v<VERSION>` invoke
validation then publish GHCR AMD64/ARM64 manifests and both variants. No `latest`
is published by default. Do not move/reuse release tags; recommend image digests
when consumers require stronger immutability. Workflows are prepared code, not
proof that GitHub exists or publication has happened. The user still needs a
GitHub repository, remote, appropriate package visibility, and an intended release.
Do not publish or push merely to test configuration. Do not invent a license.

For normal version changes, edit VERSION only; the launcher and CI pass its
value to IMAGE_VERSION, overriding the Dockerfile's fallback. IMAGE_VERSION
sets metadata, not installed tool versions or the image tag by itself. Raw
Docker builds must explicitly pass the matching argument/tag. For release checks,
select INSTALL_NODE and --image explicitly to avoid stale developer overrides.
Consumer TOOLBOX_IMAGE pins and application-image versions change separately.
Keep docs/versioning.md aligned with launcher/CI behavior. Do not bump versions,
build, tag, or publish merely to document this process.

## Validation and evidence

For launcher/config changes:

```sh
bash -n dev devcontainer/container/*.sh devcontainer/scripts/check-container.sh
python3 devcontainer/scripts/test-launcher.py
python3 devcontainer/scripts/test-diagnose.py
./dev config --workspace /path/to/existing/application
```

Validate effective runtime configuration has no shared build context, mounts the
application, reads its settings/identity, retains optional integration, and uses
isolated namespaces. Mocked engine tests verify command routing; they do not
prove root bootstrap or registry connectivity. For image changes, `./dev build`,
then `up`, `check`, and `diagnose` against an external workspace. CI prepares native
base/Node builds, real external-workspace launcher tests, and UID/GID assertions.
Only explicitly disposable CI fixture volumes can be reset during automated tests;
never delete existing user state as a routine verification step.

Compose JSON serialization varies between versions: false-valued bind options
such as create_host_path may be omitted. Assertions must accept that normalized
form without accepting an explicitly true value. The first GitHub host-check
failure exposed a direct optional-key lookup; it is corrected, and CI logs the
Compose version for future diagnosis. A local pass is not confirmation that the
subsequent GitHub image build or runtime checks have passed.

The image embeds `dev-check` and `dev-diagnose`; their support Lua scripts are under
`/opt/dev-environment/scripts`. Diagnostics write `.dev-reports/dev-report.txt`
in the selected application (Git-ignore it using the consumer template). They use
a temporary CMake project and real personal configuration for clangd selection,
attachment, hover, definition, completion, and intentional diagnostics. They also
check shell setup, permissions, compile/run, GDB, analysis/formatting, Python venv,
and local Git/agent readiness without remote authentication.

Suppress known Lazy/Mason/Tree-sitter installers/updates for the diagnostic
process, use a temporary lockfile, and preserve callback signatures. Scheduled
exceptions must fail the report, not just print and exit zero. Arbitrary personal
plugin startup is not sandboxed; caches/logs can change. Never edit host settings,
reset volumes, install dependencies, dump credentials, or push to a remote from
diagnostics. Interactive clipboard/UI and persistence across recreation need
separate verification. LSP log ERROR labels may contain informational stderr or
older sessions; interpret content rather than labels alone.

Historical evidence: the former workspace-bound setup produced 70 passes, zero
failures, one SSH-agent warning. Its fzf integration and diagnostic callback bugs
were fixed and verified in that report. This reusable-image refactor changes
bootstrap, mounting, image distribution, and namespaces: the old report does not
validate those new paths. Local regression checks and workflow YAML validation
are available, but a fresh image/runtime and GitHub run are still needed. The
current assistant session cannot access Docker's socket; report that limitation
rather than telling the user their running Docker engine is stopped.

Refactor validation: all **24 launcher tests and six diagnostic tests** passed
locally. Shell/Python syntax, workflow YAML, Dockerfile COPY inputs, and local
documentation links were checked. Engine-dependent launcher tests use a recording
stub; they are not image/runtime verification. An attempted shared build stopped
at Docker access, so root bootstrap, bundled image commands, CI, and GHCR
publication remain pending real execution.
