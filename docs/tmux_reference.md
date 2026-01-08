# Tmux Quick Reference

All commands start with **`Ctrl+B`** then the key.

## Sessions
| Command | Action |
|---------|--------|
| `tmux new -s name` | Create new session |
| `tmux attach -t name` | Attach to session |
| `tmux ls` | List sessions |
| `Ctrl+B` then `d` | Detach (leave running) |

## Panes (splits within a window)
| Command | Action |
|---------|--------|
| `Ctrl+B` then `"` | Split horizontal (top/bottom) |
| `Ctrl+B` then `%` | Split vertical (left/right) |
| `Ctrl+B` then `arrow` | Navigate between panes |
| `Ctrl+B` then `x` | Close current pane |
| `Ctrl+B` then `z` | Zoom pane (toggle fullscreen) |

## Scrolling
| Command | Action |
|---------|--------|
| `Ctrl+B` then `[` | Enter scroll mode |
| `Arrow keys` or `PgUp/PgDn` | Scroll |
| `q` | Exit scroll mode |

## Windows (tabs)
| Command | Action |
|---------|--------|
| `Ctrl+B` then `c` | New window |
| `Ctrl+B` then `w` | List windows (arrow + Enter to select) |
| `Ctrl+B` then `0-9` | Switch to window # |
| `Ctrl+B` then `n/p` | Next/previous window |
