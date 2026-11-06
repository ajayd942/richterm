" Terminal editing: keep Vim's language rules and use the Ghostty palette.
set nocompatible
filetype plugin indent on
syntax enable
set background=dark
if exists('+termguicolors') && $TERM !=# 'linux'
  set termguicolors
endif
set number cursorline ruler showcmd
set incsearch hlsearch ignorecase smartcase
set wildmenu wildmode=longest:full,full
set completeopt=menuone,noselect
set laststatus=2 scrolloff=3 sidescrolloff=4
highlight Normal       ctermfg=White ctermbg=Black guifg=#ffffff guibg=#000000
highlight CursorLine   cterm=NONE ctermbg=234 gui=NONE guibg=#10191d
highlight LineNr       ctermfg=245 guifg=#87959e
highlight CursorLineNr cterm=bold ctermfg=Cyan gui=bold guifg=#00e5ff
highlight Comment      ctermfg=246 guifg=#96a4ae
highlight Statement    cterm=bold ctermfg=Magenta gui=bold guifg=#ff68e5
highlight PreProc      ctermfg=Magenta guifg=#ff8ced
highlight Type         ctermfg=Cyan guifg=#00e5ff
highlight Function     ctermfg=Green guifg=#39ff88
highlight Identifier   ctermfg=LightBlue guifg=#81caff
highlight Constant     ctermfg=LightRed guifg=#ffa65c
highlight String       ctermfg=Yellow guifg=#ffe66b
highlight Search       ctermfg=Black ctermbg=Yellow guifg=#000000 guibg=#ffe66b
highlight Visual       cterm=NONE ctermbg=24 gui=NONE guibg=#25405a
highlight StatusLine   cterm=bold ctermfg=Cyan ctermbg=Black gui=bold guifg=#66ffff guibg=#16252c
