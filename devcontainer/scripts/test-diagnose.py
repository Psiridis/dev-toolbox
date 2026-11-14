"""Tests for diagnostic reporting and safe Neovim startup failure handling."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("diagnose", SCRIPTS / "diagnose.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="robots-report-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "report.txt"
        self.report = module.Report(self.output)
        self.addCleanup(self.report.file.close)
        self.capture = patch("sys.stdout", new=io.StringIO())
        self.capture.start()
        self.addCleanup(self.capture.stop)

    def test_command_failure_is_recorded_and_later_checks_run(self):
        self.assertFalse(self.report.command("failure", [sys.executable, "-c", "print('failure evidence'); raise SystemExit(3)"]))
        self.assertTrue(self.report.command("next check", [sys.executable, "-c", "print('later evidence')"]))
        text = self.output.read_text()
        self.assertIn("failure evidence", text)
        self.assertIn("later evidence", text)
        self.assertEqual(self.report.counts["FAIL"], 1)
        self.assertEqual(self.report.counts["PASS"], 1)

    def test_missing_executable_is_reported(self):
        self.assertFalse(self.report.command("missing", [str(self.root / "nonexistent")]))
        self.assertIn("[FAIL] missing", self.output.read_text())

    def test_timeout_is_reported(self):
        self.assertFalse(self.report.command("bounded wait", [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.1))
        self.assertIn("Timed out", self.output.read_text())

    def test_host_run_refuses_container_checks(self):
        with patch.object(module.sys, "platform", "darwin"):
            module.diagnose(self.report)
        self.assertEqual(self.report.counts["FAIL"], 1)
        self.assertIn("Run this script inside", self.output.read_text())

    @unittest.skipUnless(shutil.which("nvim"), "Neovim is needed for callback integration test")
    def test_mason_refresh_stub_preserves_callback_contract(self):
        config = self.root / "config/nvim"
        config.mkdir(parents=True)
        module_dir = self.root / "data/nvim/lazy/lazy.nvim/lua/lazy"
        module_dir.mkdir(parents=True)
        (module_dir / "init.lua").write_text("""
return { setup = function(opts)
  for _, spec in ipairs(opts.spec) do
    if spec[1] == "mason-org/mason.nvim" then spec.opts(nil, {}) end
  end
end }
""")
        (config / "init.lua").write_text("""
package.preload["mason-registry"] = function() return {} end
package.preload["mason-core.package"] = function() return {} end
require("lazy").setup({ spec = {} })
local registry = require("mason-registry")
registry.refresh(function(success, updated)
  assert(success and type(updated) == "table" and #updated == 0)
end)
local success, updated = registry.refresh()
assert(success and type(updated) == "table" and #updated == 0)
vim.g.diagnostic_callback_contract = true
""")
        env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
                   XDG_DATA_HOME=str(self.root / "data"), XDG_STATE_HOME=str(self.root / "state"),
                   XDG_CACHE_HOME=str(self.root / "cache"), DIAG_CONFIG=str(config), DIAG_WORK=str(self.root))
        command = "lua local d = _G.robot_diagnostic; if d.startup_error or not vim.g.diagnostic_callback_contract then print(d.startup_error); vim.cmd('cquit 1') else vim.cmd('qa!') end"
        result = subprocess.run(["nvim", "--headless", "-i", "NONE", "-n", "-u", str(SCRIPTS / "diagnose-init.lua"), "-c", command],
                                env=env, cwd=self.root, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("nvim"), "Neovim is needed for startup failure integration test")
    def test_neovim_missing_bootstrap_writes_structured_failure(self):
        result_file = self.root / "nvim-results.json"
        env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
                   XDG_DATA_HOME=str(self.root / "data"), XDG_STATE_HOME=str(self.root / "state"),
                   XDG_CACHE_HOME=str(self.root / "cache"), DIAG_CONFIG=str(self.root / "config/nvim"),
                   DIAG_WORK=str(self.root), DIAG_RESULT=str(result_file),
                   DIAG_PROBE=str(SCRIPTS / "diagnose-nvim.lua"))
        result = subprocess.run(["nvim", "--headless", "-i", "NONE", "-n", "-u", str(SCRIPTS / "diagnose-init.lua"),
                                 "-c", "lua vim.schedule(function() dofile(vim.env.DIAG_PROBE) end)"],
                                env=env, cwd=self.root, text=True, capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result_file.exists(), result.stdout + result.stderr)
        records = json.loads(result_file.read_text())
        self.assertTrue(any(record["status"] == "FAIL" and "lazy.nvim is not installed" in record["detail"] for record in records))
        self.assertFalse((self.root / "data/nvim/lazy/lazy.nvim").exists(), "Diagnostics must not bootstrap plugins")
        # A scheduled exception must appear as FAIL even when ordinary Lua checks finish.
        result = subprocess.run(["nvim", "--headless", "-i", "NONE", "-n", "-u", str(SCRIPTS / "diagnose-init.lua"),
                                 "-c", "lua vim.schedule(function() error('intentional asynchronous test failure') end)",
                                 "-c", "lua vim.schedule(function() dofile(vim.env.DIAG_PROBE) end)"],
                                env=env, cwd=self.root, text=True, capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        records = json.loads(result_file.read_text())
        self.assertTrue(any(record["status"] == "FAIL" and record["title"] == "Asynchronous Neovim error"
                            and "intentional asynchronous test failure" in record["detail"] for record in records))


if __name__ == "__main__":
    unittest.main()
