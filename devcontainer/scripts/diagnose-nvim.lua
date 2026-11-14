-- Runs after startup/VimEnter so lazy-loaded configuration can be inspected.
local diag = _G.robot_diagnostic or { records = {}, blocked = {} }
local records = diag.records
local function note(status, title, detail)
  table.insert(records, { status = status, title = title, detail = detail or "" })
end
local function inspect(value)
  return vim.inspect(value)
end
local function check(title, fn)
  local ok, err = xpcall(fn, debug.traceback)
  if ok then
    note("PASS", title)
  else
    note("FAIL", title, tostring(err))
  end
  return ok
end
local function run()
  note("INFO", "Neovim version and paths", inspect({
    version = vim.version(),
    config = vim.fn.stdpath("config"),
    data = vim.fn.stdpath("data"),
    state = vim.fn.stdpath("state"),
    clangd_on_PATH = vim.fn.exepath("clangd"),
  }))
  if diag.startup_error then
    error("Personal configuration startup failed: " .. diag.startup_error)
  end
  if not check("Personal LazyVim configuration loaded", function()
    local config = require("lazy.core.config")
    assert(config.plugins.LazyVim, "LazyVim is not registered in the actual configuration")
    local settings = vim.json.decode(table.concat(vim.fn.readfile(vim.env.DIAG_CONFIG .. "/lazyvim.json"), "\n"))
    assert(vim.tbl_contains(settings.extras or {}, "lazyvim.plugins.extras.lang.clangd"), "lang.clangd extra is not enabled")
  end) then
    return
  end
  note(diag.configured_rocks == false and "PASS" or "WARN", "Personal LuaRocks setting",
    "Configured rocks.enabled=" .. tostring(diag.configured_rocks) .. "; diagnostic process disables rocks independently.")
  if not check("Load nvim-lspconfig before inspecting clangd", function()
    require("lazy").load({ plugins = { "nvim-lspconfig" } })
    assert(vim.lsp.config.clangd, "No clangd LSP configuration after explicit plugin loading")
  end) then
    return
  end
  local clangd = vim.lsp.config.clangd
  note("INFO", "Effective clangd configuration", inspect({
    cmd = clangd.cmd, mason = clangd.mason, root_markers = clangd.root_markers,
  }))
  check("Container clangd selected", function()
    assert(type(clangd.cmd) == "table", "clangd.cmd is not an executable argument list")
    assert(clangd.cmd[1] == "/usr/local/bin/clangd", "Expected /usr/local/bin/clangd; got " .. tostring(clangd.cmd[1]))
    assert(vim.fn.executable(clangd.cmd[1]) == 1, "Selected clangd is not executable")
  end)
  check("Mason management disabled for clangd", function()
    local opts = require("lazy.core.plugin").values(require("lazy.core.config").plugins["nvim-lspconfig"], "opts", false)
    assert(opts.servers.clangd.mason == false, "Resolved LazyVim server opts do not set mason=false")
  end)
  local source = vim.env.DIAG_WORK .. "/main.cpp"
  vim.cmd("edit " .. vim.fn.fnameescape(source))
  local bufnr = vim.api.nvim_get_current_buf()
  check("C++ filetype", function()
    assert(vim.bo[bufnr].filetype == "cpp", "Actual filetype: " .. vim.bo[bufnr].filetype)
  end)
  local client
  if not check("clangd attaches and initializes (30s maximum)", function()
    assert(vim.wait(30000, function()
      for _, candidate in ipairs(vim.lsp.get_clients({ bufnr = bufnr, name = "clangd" })) do
        if candidate.initialized then
          client = candidate
          return true
        end
      end
      return false
    end, 100), "clangd did not attach/initialize for the temporary CMake project")
  end) then
    note("INFO", "Clients and enabled configs", inspect(vim.lsp.get_clients()))
    return
  end
  note("INFO", "Attached clangd", inspect({
    id = client.id, cmd = client.config.cmd, root_dir = client.config.root_dir,
    server_info = client.server_info,
  }))
  check("Attached server uses the container binary", function()
    assert(client.config.cmd[1] == "/usr/local/bin/clangd", "An unexpected clangd client attached")
  end)
  check("C++ Tree-sitter parser", function()
    local parser = vim.treesitter.get_parser(bufnr, "cpp")
    assert(parser and parser:parse()[1], "C++ parser unavailable; complete normal parser installation")
  end)
  local uri = vim.uri_from_bufnr(bufnr)
  local line = vim.api.nvim_buf_get_lines(bufnr, 9, 10, false)[1]
  local column = assert(line:find("add", 1, true)) - 1
  local params = { textDocument = { uri = uri }, position = { line = 9, character = column } }
  local function request(method, request_params)
    local response, err = client:request_sync(method, request_params, 10000, bufnr)
    assert(response, "LSP request failed/timed out: " .. tostring(err))
    assert(not response.err, inspect(response.err))
    return response.result
  end
  check("LSP hover response", function()
    local result = request("textDocument/hover", params)
    assert(result and result.contents and not vim.tbl_isempty(result.contents), "Empty hover response")
  end)
  check("Go-to-definition resolves the local function", function()
    local result = request("textDocument/definition", params)
    local location = result and (result[1] or result)
    assert(location, "No definition returned")
    local target_uri = location.uri or location.targetUri
    local range = location.range or location.targetSelectionRange
    assert(target_uri == uri and range and range.start.line == 0, "Unexpected definition: " .. inspect(location))
  end)
  check("LSP publishes a real diagnostic", function()
    vim.api.nvim_buf_set_lines(bufnr, 10, 11, false, { "  return missing_symbol;" })
    assert(vim.wait(15000, function()
      for _, diagnostic in ipairs(vim.diagnostic.get(bufnr)) do
        if diagnostic.message:find("missing_symbol", 1, true) then
          return true
        end
      end
      return false
    end, 100), "No diagnostic for deliberately undefined missing_symbol")
  end)
  check("Member completion returns Robot fields", function()
    vim.api.nvim_buf_set_lines(bufnr, 10, 11, false, { "  robot." })
    local result = request("textDocument/completion", {
      textDocument = { uri = uri }, position = { line = 10, character = 8 },
      context = { triggerKind = 2, triggerCharacter = "." },
    })
    local items = result and (result.items or result) or {}
    for _, item in ipairs(items) do
      local label = item.filterText or item.label or ""
      if label:find("speed", 1, true) then
        return
      end
    end
    error("No speed member in completion response")
  end)
  -- Changes are confined to the temporary buffer and are never written.
  note("INFO", "Scope", "Tests use actual LazyVim clangd settings. Headless LSP responses do not prove that interactive popup/keymap/clipboard UI works.")
end
local ok, err = xpcall(run, debug.traceback)
if not ok then
  note("FAIL", "Neovim diagnostic execution", err)
end
for _, message in ipairs(diag.blocked or {}) do
  note("WARN", "Automatic install suppressed", message)
end
for _, message in ipairs(diag.async_errors or {}) do
  note("FAIL", "Asynchronous Neovim error", message)
end
local messages = vim.api.nvim_exec2("messages", { output = true }).output
if messages ~= "" then
  local error_trace = messages:find("stack traceback:", 1, true)
  note(error_trace and "FAIL" or "INFO", "Neovim startup messages", messages:sub(-10000))
end
local logpath = vim.fn.stdpath("state") .. "/nvim/lsp.log"
if vim.lsp.log and vim.lsp.log.get_filename then
  logpath = vim.lsp.log.get_filename()
end
if vim.fn.filereadable(logpath) == 1 then
  local lines = vim.fn.readfile(logpath)
  local tail = {}
  for i = math.max(1, #lines - 39), #lines do
    table.insert(tail, lines[i])
  end
  note("INFO", "LSP log tail (may include older sessions)", table.concat(tail, "\n"):sub(-10000))
end
local failed = false
for _, record in ipairs(records) do
  failed = failed or record.status == "FAIL"
end
local saved, save_error = pcall(vim.fn.writefile, { vim.json.encode(records) }, vim.env.DIAG_RESULT)
if not saved then
  io.stderr:write("Could not write Neovim diagnostic results: " .. tostring(save_error) .. "\n")
  failed = true
end
for _, client in ipairs(vim.lsp.get_clients()) do
  pcall(client.stop, client, true)
end
vim.cmd(failed and "cquit 1" or "qa!")
