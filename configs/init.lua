------------------------------------------------------------
-- Insert mode: jf → Normal mode
------------------------------------------------------------
vim.keymap.set("i", "jf", "<Esc>", { noremap = true })

------------------------------------------------------------
-- Basic editor settings
------------------------------------------------------------
vim.opt.number = true
vim.opt.expandtab = true
vim.opt.shiftwidth = 4
vim.opt.tabstop = 4
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.writebackup = false

------------------------------------------------------------
-- Bootstrap lazy.nvim
------------------------------------------------------------
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

------------------------------------------------------------
-- Plugins (pinned for Neovim 0.9.5)
------------------------------------------------------------
require("lazy").setup({
  {
    "neovim/nvim-lspconfig",
    version = "v0.1.7",
  },
  "hrsh7th/cmp-nvim-lsp",
  "hrsh7th/nvim-cmp",
"hrsh7th/cmp-nvim-lsp",
"L3MON4D3/LuaSnip",

})

------------------------------------------------------------
-- Autocomplete setup
------------------------------------------------------------
local cmp = require("cmp")

cmp.setup({
  snippet = {
    expand = function(args)
      require("luasnip").lsp_expand(args.body)
    end,
  },
  mapping = cmp.mapping.preset.insert({
    ["<Tab>"] = cmp.mapping.select_next_item(),
    ["<S-Tab>"] = cmp.mapping.select_prev_item(),
    ["<CR>"] = cmp.mapping.confirm({ select = false }),
  }),
  sources = {
    { name = "nvim_lsp" },
  },
})

------------------------------------------------------------
-- LSP setup
------------------------------------------------------------
local lspconfig = require("lspconfig")
local capabilities =
  require("cmp_nvim_lsp").default_capabilities()

-- C++
lspconfig.clangd.setup({
  capabilities = capabilities,
})

-- Python
lspconfig.pyright.setup({
  capabilities = capabilities,
})

------------------------------------------------------------
-- LSP keybindings
------------------------------------------------------------
vim.keymap.set("n", "gd", vim.lsp.buf.definition)
vim.keymap.set("n", "K", vim.lsp.buf.hover)
vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename)

