# Toolbox versions: change, build, test, publish, adopt

**For a normal release, change `VERSION`. You do not need to edit the Dockerfile's
`ARG IMAGE_VERSION` default.** This guide describes the current implementation;
no release or version bump is performed by documenting these steps.

## What the version values mean

| Value | Role |
| --- | --- |
| `VERSION` containing `0.2.0` | The tools repository's release version; the launcher and CI read it. |
| `ARG IMAGE_VERSION=0.1.0` | Dockerfile fallback when no build argument is supplied; used for the OCI version label. |
| `dev-toolchain:0.2.0` | Local image tag; the launcher normally derives it from `VERSION`. |
| `v0.2.0` | Git release tag; pushing it starts the publication workflow after validation. |
| `ghcr.io/owner/repository:0.2.0` | Published image tag created by that workflow. |
| An application's `TOOLBOX_IMAGE` | The parent image that the application deliberately chooses; it is independent of the toolbox repository's current version. |

The normal build path is:

```text
VERSION → dev launcher → DEV_VERSION → Compose IMAGE_VERSION build argument
                                        ↓
                               Docker image version label
```

The launcher also chooses `dev-toolchain:<VERSION>` as its default image tag.
An explicit `--image` or `DEV_IMAGE` overrides that tag. The release workflow
reads VERSION directly, passes IMAGE_VERSION, and verifies the Git tag matches.

Therefore the Dockerfile fallback can still say `0.1.0` while a normal release
build correctly produces and labels `0.2.0`. Changing IMAGE_VERSION alone does
not change the local image tag. Changing VERSION labels a release; it does not
upgrade Clang, Neovim, or other tools automatically. Actual tool changes belong
in their installer/package declarations, with matching checksums when applicable.

Use stable `MAJOR.MINOR.PATCH` numbers in VERSION, with no `v` prefix. The current
launcher does not accept prerelease suffixes. Our policy is patch for compatible
fixes, minor for compatible additions, and major for breaking changes or the
first declared stable release. Releases before 1.0 remain early development;
state any compatibility limits explicitly.

## 1. Prepare a new toolbox release

From the **dev-toolbox repository**, make the intended tool or configuration
changes, then edit VERSION. For example, to prepare `0.2.0`:

```sh
printf '0.2.0\n' > VERSION
```

Review the change, update relevant documentation, and run checks:

```sh
bash -n dev devcontainer/container/*.sh devcontainer/scripts/check-container.sh
python3 devcontainer/scripts/test-launcher.py
python3 devcontainer/scripts/test-diagnose.py
```

Do not bump an application's version merely because the toolbox has a new release.
Existing projects keep their selected parent until deliberately upgraded.

## 2. Build and inspect locally

Normally `./dev build` reads VERSION and builds `dev-toolchain:0.2.0`. For release
verification, explicitly select the variant and matching tag so an old DEV_IMAGE
or INSTALL_NODE setting cannot silently change the output:

```sh
INSTALL_NODE=false ./dev build --image dev-toolchain:0.2.0
# Optional Node.js variant:
INSTALL_NODE=true ./dev build --image dev-toolchain:0.2.0-node
```

Check the image label:

```sh
docker image inspect dev-toolchain:0.2.0 \
  --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```

Expected output: `0.2.0`. Building a new tag does not remove older tags. Do not
rebuild or retag a published release as though its contents were immutable;
issue a new version for changed release contents. A fresh checkout may need a
registry login and a running Docker engine before builds work.

Test the new image against a disposable workspace without overriding an
application's derived image:

```sh
toolbox_test_workspace=$(mktemp -d)
./dev up --workspace "$toolbox_test_workspace" --image dev-toolchain:0.2.0
./dev check --workspace "$toolbox_test_workspace" --image dev-toolchain:0.2.0
```

For editor checks, first open a shell there and start Neovim normally so your
personal plugins can finish their first installation in this workspace's volumes.
Then run `diagnose` against the same workspace/image. Tests with a missing
personal configuration use plain Neovim; they do not prove C++ editor integration.
Stop with `down` using the same options. Saved volumes are retained unless you
explicitly reset this disposable workspace's state; never reset existing user
volumes as part of a release test.

## Direct Docker builds

If you bypass the launcher, Docker does not read VERSION automatically. Pass
both the build argument and the tag yourself, from the toolbox repository:

```sh
toolbox_version=$(cat VERSION)
docker build --file devcontainer/Dockerfile \
  --build-arg IMAGE_VERSION="$toolbox_version" \
  --tag "dev-toolchain:$toolbox_version" .
```

A raw build without that argument uses the Dockerfile's fallback label, even if
you manually assign a different tag. Prefer the launcher to avoid that mismatch.

## 3. Publish when GitHub is configured

This requires a Git repository with the source changes committed, a GitHub remote,
and enabled Actions/package permissions. No publication is performed by this
guide. When intentionally releasing the verified source commit:

```sh
git tag -a v0.2.0 -m "Release toolbox 0.2.0"
git push origin main
git push origin v0.2.0
```

The tag push triggers validation and then the release workflow. It rejects a
mismatch between `v0.2.0` and VERSION. The image path is determined by the actual
GitHub owner/repository, lowercased; a repository named dev-toolbox publishes:

```text
ghcr.io/<owner>/dev-toolbox:0.2.0
ghcr.io/<owner>/dev-toolbox:0.2.0-node
```

Both variants target AMD64 and ARM64. Verify the workflow and package visibility
before telling another developer the image is available. Never move/reuse release
tags; consumers needing stronger immutability can pin the published image digest.

## 4. Upgrade a consumer independently

In that application's `compose.dev.yaml`, change the toolbox parent under
`build.args.TOOLBOX_IMAGE`, for example to `dev-toolchain:0.2.0` or its published
registry reference. If it is expressed through `${TOOLBOX_IMAGE:-...}`, check
whether the shell or application `.env` overrides that default. Use `.env` for a
local experiment and a committed default/pin for an upgrade shared with others.

Build a new application development-image tag as appropriate; its version is
independent of the toolbox version. For example, an application development image
`controller-dev:0.1.1` can extend toolbox `0.2.0`. Give different applications
different final image names so their builds cannot overwrite one another's local tags.

From the selected application directory:

```sh
../dev-toolbox/dev project-build
../dev-toolbox/dev up
../dev-toolbox/dev shell
```

Run the application's own smoke checks inside the container after upgrading.
`up` alone never rebuilds a derived image. Do not pass
`--image dev-toolchain:0.2.0` when intending to run a derived application image:
that selects the bare toolbox as the final container and bypasses the application's
additional dependencies.
Do not assume changing the toolbox VERSION upgrades existing pinned applications.

To roll back, restore the application's previous parent/image pin, rebuild its
derived image if needed, and recreate it with `up`. No automatic volume reset is
needed, although plugins or caches may need compatibility checks after a downgrade.
