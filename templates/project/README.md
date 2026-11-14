# Connect an application to the shared tools

This is a consumer template, not another copy of the environment implementation.
Application code, CMake files, tests, and runtime services stay in this repository.
Each developer keeps one checkout of the shared tools repository on their host.

1. Copy `compose.dev.yaml` into the application root.
2. Replace `ghcr.io/your-owner/dev-environment:0.1.0` with the actual published
   tools release. Pin a version or digest rather than `latest`.
3. Add the patterns from this template's `.gitignore` to the application's
   existing ignore file; do not replace existing rules blindly.
4. Run the shared launcher:

```sh
/path/to/dev-environment/dev up --workspace /path/to/application
/path/to/dev-environment/dev shell --workspace /path/to/application
```

Or run `/path/to/dev-environment/dev up` from the application directory. Commands
use that current directory by default. No GitHub image is published yet; before
publication, build locally with `/path/to/dev-environment/dev build` and pass
`--image dev-toolchain:0.1.0` when using the template registry pin.

The launcher merges shared runtime defaults, this project's overlay, then optional
personal editor and SSH mounts. It uses the application's `.env`, Git identity,
and workspace. It does not mount the environment source into your application.
Do not add a fixed `container_name` or shared external editor volumes: the default
namespace keeps concurrent projects separate.

Inside the container:

```sh
nvim
# For an application that has a CMakeLists.txt:
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build
# For Python scripting:
python3 -m venv .venv
source .venv/bin/activate
```

For a diagnostic report, use the shared launcher `diagnose` command on the host,
or run `dev-diagnose` inside the container. The image contains the diagnostics;
the application does not need a scripts directory from the tools repository.
The report goes to `.dev-reports/dev-report.txt` in this application.

## Project-specific dependencies

Extend the tools image when only this application needs a library. For example,
create `.dev/Dockerfile` in the application:

```dockerfile
FROM ghcr.io/your-owner/dev-environment:0.1.0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libeigen3-dev \
    && rm -rf /var/lib/apt/lists/*
```

Then use an overlay like:

```yaml
services:
  dev:
    image: robot-controller-dev:0.1.0
    pull_policy: never
    build:
      context: .
      dockerfile: .dev/Dockerfile
```

Run `project-build`, then `up`, using the shared launcher and the same workspace.
`build` is reserved for the shared baseline; `project-build` builds this derivative.
The base image entrypoint still maps identity and drops privileges to `dev`.
Keep application runtime/deployment images separate from these development tools.
