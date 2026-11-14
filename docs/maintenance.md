# Maintain and release the shared environment

[README.md](../README.md) explains daily use. [AGENTS.md](../AGENTS.md) records
implementation constraints. This repository owns tools and their launcher;
consumer repositories own their applications, dependency choices, and image pins.

For the complete version-change procedure and the distinction between `VERSION`,
`ARG IMAGE_VERSION`, Docker tags, and Git release tags, see
[Toolbox versioning](versioning.md). Normal release builds require changing
`VERSION`, not the Dockerfile's fallback argument.

## Source, images, and projects

GitHub hosts the source repository. GHCR hosts a built image such as
`ghcr.io/your-owner/dev-environment:0.1.0`. Compose pulls the image, not a copy of
this repository. Keep one host checkout of the shared launcher and use it against
any existing application directory. The tools checkout and applications can be
siblings; the checkout's current local name does not matter.

`VERSION` controls the local image tag. Shared runtime Compose has no build
section. `compose.build.yaml` adds the tools build context only for `build`.
Application `compose.dev.yaml` overlays can select a pinned image, add services,
or define a derived image; `up --no-build` never rebuilds it implicitly.
Relative overlay paths resolve against the application directory. There is no
assumption that an application contains this repository's files.

## Local builds and optional Node.js

```sh
./dev build
./dev up --workspace /path/to/project --image dev-toolchain:0.1.0
./dev check --workspace /path/to/project --image dev-toolchain:0.1.0
./dev diagnose --workspace /path/to/project --image dev-toolchain:0.1.0
```

When a selected plugin requires Node.js/npm:

```sh
INSTALL_NODE=true ./dev build
./dev up --workspace /path/to/project --image dev-toolchain:0.1.0-node
```

Node is optional because some editor language servers need it even in C++/Python
projects. The published release includes base and `-node` variants. Setting
`INSTALL_NODE=true` does not change a committed registry pin automatically;
select the appropriate variant explicitly. Mention which tool needs Node when
adopting it. Neither variant installs anyone's personal Neovim configuration.

The image embeds `dev-check`, `dev-diagnose`, and its Lua probes under `/opt`.
Update the image and bump its release version when these bundled scripts change.
A launcher-only fix can be adopted by updating the shared host checkout. Keep
launcher and image versions from the same release when possible.

## Release and publication

Prepared workflows:

- `ci.yml`: launcher tests and image build/smoke checks for AMD64/ARM64, base/Node
  variants, diagnostic regression tests, and Linux UID/GID mapping.
- `release.yml`: after validation, publish both variants to
  `ghcr.io/<repository-owner>/<repository-name>` for a matching `vMAJOR.MINOR.PATCH` tag.
- Dependabot proposes GitHub Actions updates; review them with the normal checks.

To make publication available, first create your GitHub repository, push this
source, and enable Actions/package write permissions as required by your account.
The repository owner/name determines the image address automatically. The release
workflow uses its built-in `GITHUB_TOKEN`; do not put registry credentials in source.
Nothing has been uploaded or published by this local refactor.

When ready to release, deliberately update `VERSION`, commit the change, and
create/push a matching release tag. Tag pushes trigger publication, so do this
only when you intend to publish. The workflow checks that the tag and `VERSION`
match. It publishes explicit version tags, not `latest`; do not move or reuse
release tags. For stronger immutability, consumers can pin the published digest.

GHCR packages may initially be private. Set the intended visibility in GitHub;
private consumers need an authorized registry login on their host. Registry login
is independent of Git SSH-agent forwarding. Record a license before inviting
public reuse; none has been selected for this repository yet.

CI uses native `ubuntu-24.04` and `ubuntu-24.04-arm` runners; publishing assembles
AMD64/ARM64 images through Buildx/QEMU. Runner availability depends on the GitHub
account/repository. Adapt runner labels deliberately if native ARM runners are
unavailable. Workflows have been prepared locally; a successful GitHub run is
still required before claiming multi-architecture runtime support for a release.

## Isolation, persistence, and identity

Namespaces default to a readable workspace name plus checksum of its canonical
host path. Equal basenames in different directories therefore do not share
containers or volumes. Architecture is part of the volume name. A stable
`DEV_PROJECT_NAME` setting or `--project-name` is available when moving a project;
use it consistently for all commands and do not assign one name to concurrent
unrelated projects.

The Linux host's UID/GID is runtime configuration, not a per-developer image
build. Root bootstrap maps `dev` then uses `setpriv` to drop privileges. It
avoids recursive home ownership changes through the mounted editor configuration,
never chowns `/workspace`, and only repairs managed tool/state volumes. Launcher
shell/check/diagnostic exec commands explicitly use `dev`. Raw `docker exec` users
must also specify `--user dev`; do not assume the image's bootstrap user is the
interactive user. Passwordless sudo remains available for development; review
that separately for a mature project or runtime image.

Old workspace-bound volumes such as `robots-nvim-data-arm64` are **retained**.
New namespace defaults will create fresh storage; this is not data loss. To reuse
the previous maintenance workspace storage, select `--project-name robots` with
this original workspace, or set `DEV_PROJECT_NAME=robots` in its `.env`. Do not
reuse that namespace for all applications. No volume reset or migration is run
implicitly. After switching launchers, old containers can remain until explicitly
stopped with their old project name. Use `status` first and preserve data.

## Change and validation policy

Keep the shared baseline limited to generally useful development tools. Add
application libraries through derived images; personal keymaps/plugins belong
in the host configuration. Keep Ubuntu 24.04, native architecture, and stable
selected Neovim/LLVM versions unless the requirement calls for a deliberate change.
Ubuntu security package revisions are allowed to advance. Update matching release
checksums when changing downloaded binaries; use the same LLVM major throughout.

Before a launcher change:

```sh
bash -n dev devcontainer/container/*.sh devcontainer/scripts/check-container.sh
python3 devcontainer/scripts/test-launcher.py
python3 devcontainer/scripts/test-diagnose.py
./dev config --workspace /path/to/project
```

For image changes, build and run `check`; use `diagnose` with an installed personal
configuration to test LSP behavior. Verify permissions, UID remapping, missing
configuration fallback, optional SSH, separate workspace state, and persistence as
relevant. Reports are best-effort diagnostics, not proof of interactive clipboard
behavior, remote Git authorization, or survival across recreation.

The previous workspace-bound environment had a report with 70 passes and one
SSH-agent warning. Treat that as historical evidence for its tools, not proof
that this refactor's bootstrap, published images, or CI have run successfully.

The refactor passed 24 launcher tests and six diagnostic tests locally. Workflow
YAML, code syntax, image COPY inputs, and documentation links were validated.
Docker socket access prevented a local image build in this session; CI and
publication have not executed. Docker's reference for the prepared publication
approach is [multi-platform GitHub Actions builds](https://docs.docker.com/build/ci/github-actions/multi-platform/).
