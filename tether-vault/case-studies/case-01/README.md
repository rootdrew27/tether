# Case Study 01

A simple update of two source files.
## Setting

- A source file exposing a CLI (`cli.py`)
- A source file defining the CLI functions (`common.py`)
- A markdown document describing the interface and how to use it (`usage.md`)
- A tether between `cli.py` and `usage.md`

**Tether Creation Command:**
```bash
uv run tether add --description "docs/usage.md documents the CLI surface defined in cli.py (add/sub/mul/div); changes to argparse subcommands or arg types must be reflected in the usage examples." cli.py docs/usage.md
```

## The Prompt

```
Update the common.py source file to include the modulo operation and then update the cli interface in cli.py
```