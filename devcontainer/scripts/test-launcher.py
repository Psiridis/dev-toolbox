"""Shared launcher integration checks using Compose; no engine required."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REAL_DOCKER = shutil.which("docker")


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dev-tools-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for filename in ("dev", "VERSION", "devcontainer/compose.yaml", "devcontainer/compose.build.yaml",
                         "devcontainer/compose.image.yaml", "devcontainer/compose.nvim.yaml", "devcontainer/compose.ssh.yaml"):
            target = self.root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / filename, target)
        self.version = (self.root / "VERSION").read_text().strip()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.stub("ssh-add", "exit 1")
        self.stub("uname", 'case "$1" in -s) echo Darwin;; -m) echo arm64;; esac')
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(("DEV_", "COMPOSE_", "HOST_GIT_")) or key in (
                    "NVIM_CONFIG_PATH", "INSTALL_NODE", "FORWARD_SSH_AGENT", "RESOLVED_NVIM_CONFIG",
                    "DOCKER_DEFAULT_PLATFORM", "DOCKER_HOST", "DOCKER_CONTEXT"):
                self.env.pop(key, None)
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env["PATH"],
                        NVIM_CONFIG_PATH=str(self.root / "missing"))

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def workspace(self, relative="applications/robot-controller"):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_launcher(self, *args, cwd=None):
        return subprocess.run([str(self.root / "dev"), *args], cwd=cwd or self.root,
                              env=self.env, text=True, capture_output=True)

    def config(self, *args, cwd=None):
        result = self.run_launcher("config", *args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = subprocess.run([REAL_DOCKER, "compose", "-f", "-", "config", "--format", "json"],
                                input=result.stdout, text=True, capture_output=True, check=True)
        return json.loads(parsed.stdout), result.stderr

    def record_engine_calls(self):
        self.calls = self.root / "docker-calls.txt"
        self.env.update(REAL_DOCKER=REAL_DOCKER, TEST_DOCKER_CALLS=str(self.calls))
        self.stub("docker", '''
case "$1" in
  compose)
    for arg do
      case "$arg" in config|version) exec "$REAL_DOCKER" "$@";; esac
    done
    printf '%s\\n' "$@" >> "$TEST_DOCKER_CALLS"
    ;;
  info) if [ "$#" -gt 1 ]; then echo aarch64; fi ;;
  context) echo unix:///test-docker.sock ;;
  *) exit 1 ;;
esac''')

    def test_runtime_has_image_without_build(self):
        config, _ = self.config()
        service = config["services"]["dev"]
        self.assertEqual(service["image"], f"dev-toolchain:{self.version}")
        self.assertNotIn("build", service)
        self.assertEqual(service["user"], "root")  # bootstrap drops to dev
        self.assertEqual(service["environment"]["DEV_HOST_UID"], "1000")

    def test_missing_config_and_agent_are_optional(self):
        config, messages = self.config()
        targets = [m["target"] for m in config["services"]["dev"]["volumes"]]
        self.assertNotIn("/home/dev/.config/nvim", targets)
        self.assertNotIn("/run/host-ssh-agent", targets)
        self.assertIn("using plain Neovim", messages)
        self.assertFalse((self.root / "missing").exists())

    def test_empty_config_uses_plain_neovim(self):
        (self.root / "missing").mkdir()
        _, messages = self.config()
        self.assertIn("using plain Neovim", messages)

    def test_external_workspace_mounts_only_the_application(self):
        workspace = self.workspace("my projects/robot-controller")
        config, _ = self.config("--workspace", str(workspace))
        mount = next(m for m in config["services"]["dev"]["volumes"] if m["target"] == "/workspace")
        self.assertEqual(mount["source"], str(workspace))
        self.assertNotEqual(mount["source"], str(self.root))
        # Compose serializers may omit false-valued bind options entirely.
        self.assertFalse(mount.get("bind", {}).get("create_host_path", False))

    def test_current_directory_is_default_workspace(self):
        workspace = self.workspace()
        config, _ = self.config(cwd=workspace)
        mount = next(m for m in config["services"]["dev"]["volumes"] if m["target"] == "/workspace")
        self.assertEqual(mount["source"], str(workspace))

    def test_equal_basenames_get_distinct_namespaces(self):
        a, b = self.workspace("one/app"), self.workspace("two/app")
        first, _ = self.config("--workspace", str(a))
        again, _ = self.config("--workspace", str(a))
        other, _ = self.config("--workspace", str(b))
        self.assertEqual(first["name"], again["name"])
        self.assertNotEqual(first["name"], other["name"])
        self.assertNotEqual(first["volumes"]["nvim-data"]["name"], other["volumes"]["nvim-data"]["name"])

    def test_explicit_legacy_namespace_reuses_volume_names(self):
        config, _ = self.config("--project-name", "robots")
        self.assertEqual(config["name"], "robots")
        self.assertEqual(config["volumes"]["nvim-data"]["name"], "robots-nvim-data-arm64")

    def test_workspace_env_and_no_shell_execution(self):
        workspace = self.workspace()
        config_dir = self.root / "my editor config"
        config_dir.mkdir()
        (config_dir / "init.lua").write_text("-- personal config\n")
        sentinel = self.root / "must-not-be-created"
        self.env.pop("NVIM_CONFIG_PATH")
        (workspace / ".env").write_text(f'NVIM_CONFIG_PATH="{config_dir}"\nINSTALL_NODE=true\n'
                                        f'FORWARD_SSH_AGENT=false\nINERT=$(touch {sentinel})\n')
        config, _ = self.config("--workspace", str(workspace))
        self.assertEqual(config["services"]["dev"]["image"], f"dev-toolchain:{self.version}-node")
        mount = next(m for m in config["services"]["dev"]["volumes"] if m["target"] == "/home/dev/.config/nvim")
        self.assertEqual(mount["source"], str(config_dir))
        self.assertFalse(mount.get("read_only", False))
        self.assertFalse(sentinel.exists())

    def test_tools_repo_env_does_not_leak_into_another_project(self):
        (self.root / ".env").write_text("DEV_IMAGE=unrelated:9\nINSTALL_NODE=true\n")
        workspace = self.workspace()
        config, _ = self.config("--workspace", str(workspace))
        self.assertEqual(config["services"]["dev"]["image"], f"dev-toolchain:{self.version}")

    def test_project_image_pin_and_service_overlay(self):
        workspace = self.workspace()
        (workspace / "compose.dev.yaml").write_text("services:\n  dev:\n    image: ghcr.io/example/tools:2.3.4\n    environment:\n      PROJECT_SETTING: enabled\n")
        config, _ = self.config("--workspace", str(workspace))
        self.assertEqual(config["services"]["dev"]["image"], "ghcr.io/example/tools:2.3.4")
        self.assertEqual(config["services"]["dev"]["environment"]["PROJECT_SETTING"], "enabled")
        overridden, _ = self.config("--workspace", str(workspace), "--image", "local-tools:testing")
        self.assertEqual(overridden["services"]["dev"]["image"], "local-tools:testing")

    def test_workspace_image_env_overrides_project_default(self):
        workspace = self.workspace()
        (workspace / "compose.dev.yaml").write_text("services:\n  dev:\n    image: ghcr.io/example/tools:2.3.4\n")
        (workspace / ".env").write_text("DEV_IMAGE=local-tools:custom\n")
        config, _ = self.config("--workspace", str(workspace))
        self.assertEqual(config["services"]["dev"]["image"], "local-tools:custom")

    def test_relative_overlay_is_resolved_from_workspace(self):
        workspace = self.workspace()
        (workspace / "custom.yaml").write_text("services:\n  dev:\n    image: local-tools:overlay\n")
        config, _ = self.config("--workspace", str(workspace), "--compose", "custom.yaml")
        self.assertEqual(config["services"]["dev"]["image"], "local-tools:overlay")

    def test_agent_forwarding_and_opt_out(self):
        self.stub("ssh-add", "exit 0")
        config, _ = self.config()
        self.assertEqual(config["services"]["dev"]["environment"]["SSH_AUTH_SOCK"], "/run/host-ssh-agent")
        self.env["FORWARD_SSH_AGENT"] = "false"
        disabled, _ = self.config()
        self.assertNotIn("SSH_AUTH_SOCK", disabled["services"]["dev"]["environment"])

    def test_linux_identity_is_runtime_configuration(self):
        self.stub("uname", 'case "$1" in -s) echo Linux;; -m) echo x86_64;; esac')
        config, _ = self.config()
        env = config["services"]["dev"]["environment"]
        self.assertEqual(env["DEV_HOST_UID"], str(os.getuid()))
        self.assertEqual(env["DEV_HOST_GID"], str(os.getgid()))
        self.assertNotIn("build", config["services"]["dev"])

    def test_git_identity_is_read_from_selected_workspace(self):
        workspace = self.workspace()
        self.env["EXPECTED_GIT_WORKSPACE"] = str(workspace)
        self.stub("git", '[ "$2" = "$EXPECTED_GIT_WORKSPACE" ] || exit 9; case "$*" in *user.name) echo "Example Developer";; *user.email) echo "dev@example.test";; esac')
        config, _ = self.config("--workspace", str(workspace))
        env = config["services"]["dev"]["environment"]
        self.assertEqual(env["HOST_GIT_NAME"], "Example Developer")
        self.assertEqual(env["HOST_GIT_EMAIL"], "dev@example.test")

    def test_up_never_builds(self):
        self.record_engine_calls()
        result = self.run_launcher("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertIn("--no-build", calls)
        self.assertNotIn("--build", calls)

    def test_build_uses_tools_source_and_ignores_project_overlay(self):
        workspace = self.workspace()
        overlay = workspace / "compose.dev.yaml"
        overlay.write_text("services:\n  dev:\n    image: ghcr.io/example/consumer:1.0.0\n")
        self.record_engine_calls()
        result = self.run_launcher("build", "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertIn(str(self.root / "devcontainer/compose.build.yaml"), calls)
        self.assertNotIn(str(overlay), calls)
        self.assertIn(f"Built dev-toolchain:{self.version}", result.stdout)

    def test_shell_always_executes_as_dev(self):
        self.record_engine_calls()
        result = self.run_launcher("shell")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertIn("--user", calls)
        self.assertIn("zsh", calls)

    def test_diagnostics_are_bundled_in_image(self):
        self.record_engine_calls()
        result = self.run_launcher("diagnose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dev-diagnose", self.calls.read_text().splitlines())
        self.assertNotIn("/workspace/devcontainer", self.calls.read_text())

    def test_project_build_uses_application_overlay(self):
        workspace = self.workspace()
        overlay = workspace / "compose.dev.yaml"
        overlay.write_text("services:\n  dev:\n    image: app-dev:1.0.0\n    build:\n      context: .\n      dockerfile: Project.Dockerfile\n")
        config, _ = self.config("--workspace", str(workspace))
        self.assertEqual(config["services"]["dev"]["build"]["context"], str(workspace))
        self.assertEqual(config["services"]["dev"]["build"]["dockerfile"], "Project.Dockerfile")
        self.record_engine_calls()
        result = self.run_launcher("project-build", "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertIn(str(overlay), calls)
        self.assertNotIn(str(self.root / "devcontainer/compose.build.yaml"), calls)

    def test_symlink_workspace_resolves_to_same_namespace(self):
        workspace = self.workspace()
        link = self.root / "linked-project"
        link.symlink_to(workspace, target_is_directory=True)
        first, _ = self.config("--workspace", str(workspace))
        alias, _ = self.config("--workspace", str(link))
        self.assertEqual(first["name"], alias["name"])
        self.assertEqual(first["volumes"], alias["volumes"])

    def test_invalid_settings_and_missing_paths_are_rejected(self):
        self.env["INSTALL_NODE"] = "maybe"
        result = self.run_launcher("config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INSTALL_NODE must", result.stderr)
        self.env.pop("INSTALL_NODE")
        result = self.run_launcher("config", "--workspace", str(self.root / "nonexistent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Workspace does not exist", result.stderr)
        self.assertFalse((self.root / "nonexistent").exists())

    def test_non_native_platform_is_rejected(self):
        self.env["DOCKER_DEFAULT_PLATFORM"] = "linux/amd64"
        result = self.run_launcher("config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("native platform", result.stderr)

    def test_reset_requires_explicit_flag(self):
        result = self.run_launcher("reset")
        self.assertEqual(result.returncode, 2)
        self.assertIn("reset --yes", result.stderr)


if __name__ == "__main__":
    unittest.main()
