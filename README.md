# start-tla+

A ready-to-fork starter for writing and model-checking [TLA+](https://lamport.azurewebsites.net/tla/tla.html) specs in VS Code, with a Makefile for command-line use.

## Prerequisites

- **Java 11+** (`java -version`). On macOS: `brew install --cask temurin`
- **VS Code** with the [TLA+ extension](https://marketplace.visualstudio.com/items?itemName=tlaplus.vscode-ide). VS Code will offer to install it from `.vscode/extensions.json`, or run `code --install-extension tlaplus.vscode-ide`.
- `make` and `curl` (preinstalled on macOS/Linux)

## Quick start

```sh
git clone <your-fork-url> && cd start-tla+
make setup     # downloads tools/tla2tools.jar
make check     # model-checks specs/Counter.tla
```

Expected result: `Model checking completed. No error has been found.`

## Layout

```
specs/          your .tla modules and their .cfg model configs
.vscode/        editor settings + recommended extension
tools/          tla2tools.jar (downloaded by `make setup`, git-ignored)
states/         TLC working state (git-ignored)
Makefile
```

Each spec `Foo` is a pair: `specs/Foo.tla` (the module; its name must match the filename) and `specs/Foo.cfg` (tells TLC the `SPECIFICATION`, `CONSTANT`s, and `INVARIANT`s/`PROPERTY`s to check).

## Writing a new spec

```sh
make new SPEC=MySpec     # creates specs/MySpec.tla + MySpec.cfg
make parse SPEC=MySpec   # syntax check
make check SPEC=MySpec   # run TLC
```

## Makefile targets

| Target | What it does |
| --- | --- |
| `make setup` | Verify Java, download `tla2tools.jar` |
| `make parse SPEC=X` | Parse and type-check with SANY |
| `make check SPEC=X` | Exhaustive model checking with TLC (alias: `make tlc`) |
| `make simulate SPEC=X` | Random-walk simulation, useful for large state spaces |
| `make pcal SPEC=X` | Translate a PlusCal algorithm into TLA+ |
| `make repl` | Interactive TLA+ REPL |
| `make new SPEC=X` | Scaffold a new module and config |
| `make clean` / `make distclean` | Remove TLC output / also remove the jar |

Variables: `SPEC` (default `Counter`), `WORKERS` (default `auto`), `TLA_JAR_URL` (to pin a specific tla2tools release, e.g. `make setup TLA_JAR_URL=https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar`).

## Using VS Code

Open the folder in VS Code, then open a `.tla` file. Useful commands (Command Palette, `Cmd/Ctrl+Shift+P`):

- **TLA+: Parse module**: syntax check
- **TLA+: Check model with TLC**: runs TLC using the `.cfg` beside the file
- **TLA+: Check model with TLC in the background**
- **TLA+: Evaluate selected expression**: quick REPL-like evaluation
- **TLA+: Visualize state graph / Show Unicode**: more in the extension docs

The extension bundles its own TLC, so VS Code works even before `make setup`; the Makefile is for terminal and CI use.

## Learning resources

- [Learn TLA+](https://learntla.com/) (practical, PlusCal-first)
- [Lamport's TLA+ Video Course](https://lamport.azurewebsites.net/video/videos.html)
- [Specifying Systems](https://lamport.azurewebsites.net/tla/book.html) (the book, free PDF)
- [TLA+ Examples](https://github.com/tlaplus/Examples)

## Troubleshooting

- **`java: command not found`**: install a JDK (see prerequisites).
- **`Cannot find config`**: `SPEC=X` needs both `specs/X.tla` and `specs/X.cfg`.
- **Module name mismatch error**: the `MODULE X` header must match the filename `X.tla`.
