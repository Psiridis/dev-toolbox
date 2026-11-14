-- Optional personal override; copy into ~/.config/nvim/lua/plugins/clangd.lua.
-- Requires the lang.clangd extra. The image does not install this configuration.
return {
  {
    "neovim/nvim-lspconfig",
    opts = function(_, opts)
      local executable = "/usr/local/bin/clangd"
      if vim.fn.executable(executable) == 1 then
        opts.servers.clangd.mason = false
        opts.servers.clangd.cmd[1] = executable
      end
    end,
  },
}
