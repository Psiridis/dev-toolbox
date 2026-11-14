-- Diagnostic-only startup: load personal settings without updating plugins/tools.
_G.robot_diagnostic = { records = {}, blocked = {}, async_errors = {} }
local diag = _G.robot_diagnostic
-- Scheduled callback errors otherwise print to stderr without failing Neovim.
local original_schedule = vim.schedule
vim.schedule = function(callback)
  return original_schedule(function()
    local ok, err = xpcall(callback, debug.traceback)
    if not ok then
      table.insert(diag.async_errors, tostring(err))
      io.stderr:write(tostring(err) .. "\n")
    end
  end)
end
local function note(status, title, detail)
  table.insert(diag.records, { status = status, title = title, detail = detail or "" })
end
vim.opt.swapfile = false
vim.opt.shadafile = "NONE"
local config = vim.env.DIAG_CONFIG
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if vim.fn.isdirectory(lazypath) == 0 then
  diag.startup_error = "lazy.nvim is not installed. Open Neovim normally and complete initial installation first."
  return
end
vim.opt.rtp:prepend(lazypath)
local lazy = require("lazy")
local original_setup = lazy.setup
lazy.setup = function(opts)
  opts = vim.deepcopy(opts or {})
  diag.configured_rocks = (opts.rocks or {}).enabled
  opts.install = vim.tbl_extend("force", opts.install or {}, { missing = false })
  opts.checker = vim.tbl_extend("force", opts.checker or {}, { enabled = false })
  opts.change_detection = vim.tbl_extend("force", opts.change_detection or {}, { enabled = false })
  opts.rocks = vim.tbl_extend("force", opts.rocks or {}, { enabled = false })
  local lockfile = config .. "/lazy-lock.json"
  opts.lockfile = vim.env.DIAG_WORK .. "/lazy-lock.json"
  if vim.fn.filereadable(lockfile) == 1 then
    vim.fn.writefile(vim.fn.readfile(lockfile), opts.lockfile)
  end
  opts.spec = opts.spec or {}
  table.insert(opts.spec, {
    "mason-org/mason.nvim",
    opts = function(_, mason_opts)
      mason_opts.ensure_installed = {}
      -- Read the installed registry; do not refresh it or start package installs.
      local registry = require("mason-registry")
      registry.refresh = function(callback)
        if callback then
          return callback(true, {})
        end
        return true, {}
      end
      require("mason-core.package").install = function(self)
        local name = self.name or (self.spec or {}).name or "unknown"
        table.insert(diag.blocked, "Mason installation suppressed: " .. name)
      end
    end,
  })
  table.insert(opts.spec, {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, tree_opts)
      tree_opts.ensure_installed = {}
      tree_opts.auto_install = false
    end,
  })
  return original_setup(opts)
end
local init = config .. "/init.lua"
local ok, err = xpcall(function()
  if vim.fn.filereadable(init) == 1 then
    dofile(init)
  else
    vim.cmd("source " .. vim.fn.fnameescape(config .. "/init.vim"))
  end
end, debug.traceback)
if not ok then
  diag.startup_error = err
end
note("INFO", "Diagnostic startup", "Personal init loaded; Lazy installs/updates and known Mason/Tree-sitter automatic installers are suppressed for this process. Normal caches/logs may be written. The plugin lockfile is copied to the temporary directory.")
