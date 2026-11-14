# Reusable development toolchain

One Ubuntu 24.04 tools image for many independent C++ and Python projects.
It includes Neovim, Git, Clang/clangd, formatting and analysis tools, GDB,
CMake/Ninja, Python with venv, and a colorful Zsh terminal with fuzzy search.
Your projects own their source, build configuration, tests, and dependencies.
Your Neovim configuration and credentials remain personal.

## Layout

```text
dev-environment/          # This repository; its local folder name is your choice
├── dev                  # Shared host launcher
├── VERSION              # Tools image release version
├── devcontainer/        # Image source, runtime Compose defaults, checks
├── templates/project/   # Small files to copy into an application repository
├── docs/maintenance.md  # Building, publishing, upgrades, migration
├── reports/             # Archived local reports; not included in the image
├── .github/workflows/   # Tests and versioned multi-architecture publication
└── AGENTS.md            # Design constraints and expansion guidance
```

Keep a single checkout of this repository alongside your application repositories.
Do not copy the Dockerfile and maintenance scripts into each project.

To change a toolbox release, edit **`VERSION`**. The launcher overrides the
Dockerfile's `ARG IMAGE_VERSION` fallback automatically. See the
[versioning guide](docs/versioning.md) for building, testing, publishing, and
upgrading an application independently.

## Requirements

Use Docker CLI and Compose with a running local engine. On macOS, Docker Desktop
supplies the Linux VM; start it from the terminal with `docker desktop start`.
On Linux, Docker Engine and the Compose plugin are sufficient. `docker run` and
`docker compose build` need an engine; they do not replace one. Colima's macOS
SSH-agent integration is not implemented here.

## Start with a locally built image

From this repository, build the shared tools image once:

```sh
./dev build                     # Produces dev-toolchain:0.1.0
```

Then select an **existing** application directory on your host:

```sh
./dev up --workspace /absolute/path/to/robot-controller
./dev shell --workspace /absolute/path/to/robot-controller
```

Inside the container, that application is `/workspace`. The tools repository is
not mounted there. Source changes are saved to the application directory.
Use another `shell` command for another terminal. `exit` leaves the shell while
the container keeps running. Without `--workspace`, the current directory is used.

**`up` never builds.** Build again only when changing the tools image. A missing
registry image is pulled automatically; use `pull` to request a fresh pull.

## Use a published image in each project

Copy [templates/project/compose.dev.yaml](templates/project/compose.dev.yaml) into
the application root and replace its illustrative image with your actual release:

```yaml
services:
  dev:
    image: ghcr.io/your-owner/dev-environment:0.1.0
```

Commit that file in the application repository. Each project chooses its own
image version (or immutable digest). The launcher automatically merges the
selected workspace's `compose.dev.yaml` with shared editor, Git, and storage
settings. It does not load the application's production `compose.yaml` implicitly.
Use `--compose path/to/file.yaml` to choose a different project overlay.

```sh
/path/to/dev-environment/dev up --workspace /path/to/application
/path/to/dev-environment/dev shell --workspace /path/to/application
```

The image must be built/published first: no GHCR package has been created by this
setup. See the [project template guide](templates/project/README.md) and
[maintenance guide](docs/maintenance.md). `--image dev-toolchain:0.1.0` overrides a
project's registry pin for local testing without changing its committed file.

## Commands

Use the same workspace and optional project-name settings for every command.

| Command | Action |
| --- | --- |
| `./dev --help` | Show commands and options. |
| `./dev build` | Build the shared tools image locally. |
| `./dev up --workspace PATH` | Start the project's selected image; never build. |
| `./dev pull --workspace PATH` | Pull the selected image. |
| `./dev shell --workspace PATH` | Open Zsh as the non-root `dev` user. |
| `./dev status --workspace PATH` | Show this workspace's containers. |
| `./dev check --workspace PATH` | Run the image's toolchain smoke checks. |
| `./dev diagnose --workspace PATH` | Write `PATH/.dev-reports/dev-report.txt`. |
| `./dev config --workspace PATH` | Inspect merged runtime settings without an engine. |
| `./dev project-build --workspace PATH` | Build a project-specific derived image, if its overlay defines one. |
| `./dev down --workspace PATH` | Remove this project's containers; retain saved state. |
| `./dev reset --yes --workspace PATH` | Also delete this project's editor/history/trust volumes. |

Containers and volumes are isolated per canonical workspace path and architecture.
The image layers are reused. Reset preserves source and host editor configuration,
**but deletes saved editor downloads, history, and SSH server trust records**.
After stopping your projects, `docker desktop stop` stops the macOS backend for
all projects using it.

## Personal editor and settings

Inside any tools container, run `nvim`. The launcher optionally mounts your host
`~/.config/nvim` at `/home/dev/.config/nvim`; editing it inside the container also
updates your host copy. Missing configuration gives a message and plain Neovim.
Linux plugins and Mason tools stay in project-scoped Docker volumes, separate
from your host's Neovim data. Themes with icons may need a host Nerd Font.

If you want LazyVim and have no existing configuration, run on the host:

```sh
git clone --depth 1 https://github.com/LazyVim/starter ~/.config/nvim
```

Recreate the selected container with `up`, open `nvim`, allow initial plugin
installation, and run `:LazyHealth`. C++ support is a personal `lang.clangd` extra;
[an optional override](devcontainer/examples/neovim/clangd.lua) selects the image's
clangd. No editor extras are forced into everyone's configuration.

Optional settings go in the **selected application's** untracked `.env`. Copy
[devcontainer/.env.example](devcontainer/.env.example) as a starting point:

```dotenv
NVIM_CONFIG_PATH=/absolute/path/to/my/nvim
FORWARD_SSH_AGENT=true
# DEV_IMAGE=ghcr.io/your-owner/dev-environment:0.1.0
```

Shell settings override `.env`; `--image` and `--project-name` override their
corresponding settings. An explicit image selection overrides the project pin.
`INSTALL_NODE=false` is the shared image build default. If a plugin needs Node.js,
build with it enabled and select the `0.1.0-node` variant; see the maintenance guide.
Changing Node.js is an image change, not something a container restart installs.

Git commits/pulls/pushes run inside the container. Git author defaults come from
the selected host project, and SSH authentication uses the host agent when
available. Keys are not copied. Missing SSH identities allow local development.
Docker registry login (`docker login`) is separate from Git SSH authentication.
For registry `401 / incorrect username or password` errors, refresh the host's
login with `docker logout` followed by `docker login`, then retry the operation.

Zsh shortcuts: **Ctrl+R** searches history, **Ctrl+T** selects files, **Alt+C** changes
directory, and **Right Arrow** accepts a suggestion. On macOS, Option may need to
send Alt/Meta. Use `rg` for text and `fd` for file search.

Runtime processes and launcher shells run as `dev`. The entrypoint briefly runs
as root to map Linux UID/GID and prepare managed storage; it never chowns the
application workspace or personal editor configuration. Passwordless sudo remains
a development convenience. Keep permanent project dependencies in a derived
image, not in interactive installs or the shared baseline.

The previous workspace-bound setup passed 70 diagnostic checks. This reusable
refactor passed 30 local regression tests plus configuration/syntax checks. It
needs a fresh image build and runtime verification; no registry image has been
published by this session.
