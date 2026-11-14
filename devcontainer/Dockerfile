FROM ubuntu:24.04

# Fallback for raw docker builds. The launcher/CI override this from VERSION.
ARG IMAGE_VERSION=0.1.0
ARG INSTALL_NODE=false
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    CC=clang CXX=clang++ \
    COLORTERM=truecolor \
    STARSHIP_CONFIG=/etc/dev/starship.toml \
    HOME=/home/dev USER=dev LOGNAME=dev
LABEL org.opencontainers.image.title="Development toolchain" \
    org.opencontainers.image.description="Ubuntu C++ and Python tools with optional personal Neovim configuration" \
    org.opencontainers.image.version="${IMAGE_VERSION}"

# Ubuntu's minimal image excludes most documentation. fzf's functional shell
# integration lives under doc/, so explicitly preserve it before installation.
RUN printf 'path-include=/usr/share/doc/fzf\npath-include=/usr/share/doc/fzf/*\n' \
      > /etc/dpkg/dpkg.cfg.d/zz-fzf-integration \
    && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    bash zsh zsh-autosuggestions zsh-syntax-highlighting fzf \
    git openssh-client curl ca-certificates unzip xz-utils ripgrep fd-find \
    build-essential cmake ninja-build pkg-config gdb \
    clang-18 clangd-18 clang-format-18 clang-tidy-18 \
    python3 python3-pip python3-venv sudo util-linux \
    && test -r /usr/share/doc/fzf/examples/key-bindings.zsh \
    && test -r /usr/share/doc/fzf/examples/completion.zsh \
    && rm -rf /var/lib/apt/lists/* \
    && for tool in clang clang++ clangd clang-format clang-tidy; do \
         ln -s "/usr/bin/${tool}-18" "/usr/local/bin/${tool}"; \
       done \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd

COPY devcontainer/container/install-tools.sh devcontainer/container/checksums.txt /tmp/dev-tools/
RUN bash /tmp/dev-tools/install-tools.sh "${INSTALL_NODE}" && rm -rf /tmp/dev-tools

# Ubuntu's base image may already have a user with UID 1000.
RUN if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
    && if ! getent group 1000 >/dev/null; then groupadd --gid 1000 dev; fi \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/bin/zsh dev \
    && printf 'dev ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/dev \
    && chmod 0440 /etc/sudoers.d/dev \
    && mkdir -p /etc/dev /home/dev/.config /home/dev/.local/share/nvim /home/dev/.local/state /workspace \
    && chown -R dev:1000 /home/dev /workspace \
    && printf 'Host *\n    UserKnownHostsFile /home/dev/.local/state/ssh/known_hosts\n' > /etc/ssh/ssh_config.d/90-dev.conf

COPY devcontainer/container/zshrc /home/dev/.zshrc
COPY devcontainer/container/starship.toml /etc/dev/starship.toml
COPY --chmod=755 devcontainer/container/entrypoint.sh /usr/local/bin/dev-entrypoint
COPY --chmod=755 devcontainer/scripts/check-container.sh /usr/local/bin/dev-check
COPY --chmod=755 devcontainer/scripts/diagnose.py /opt/dev-environment/scripts/diagnose.py
COPY devcontainer/scripts/diagnose-init.lua devcontainer/scripts/diagnose-nvim.lua /opt/dev-environment/scripts/
RUN ln -s /opt/dev-environment/scripts/diagnose.py /usr/local/bin/dev-diagnose
USER root
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/dev-entrypoint"]
CMD ["sleep", "infinity"]
