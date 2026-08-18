---
description: "Use when writing or editing Python source, tests, or any code in this repo. Covers the comment-block policy: prefer single-line comments in code, move explanatory detail to .github/instructions/*.instructions.md, and link from the code."
applyTo: "src/**/*.py, tests/**/*.py, docker/**/*.py, migrations/**/*.py"
---

# Comments — prefer single-line, move detail to instructions

## The rule

**Do not write big comment blocks in code.** If you feel the need to write a
multi-line comment block explaining a module, a function's rationale, a
non-obvious invariant, or the history behind a workaround, put that content
in a `.github/instructions/*.instructions.md` file and leave a single-line
comment in the code that points to it.

## What counts as "big"

A "big" comment block is any comment that:

- Spans more than 2-3 lines, **or**
- Explains *why* something exists (rationale, history, cross-repo contract,
  workaround origin) rather than *what* the next line does, **or**
- Duplicates content already covered in an instruction file or `AGENTS.md`.

Single-line `# ...` comments explaining the next statement are fine and
encouraged. Docstrings are fine (they're the API contract, not commentary)
— but keep them tight: parameters, returns, raises, and a one-line summary.
Don't bury rationale in a docstring's prose; link to the instructions
instead.

## Where the detail goes

Pick the instruction file whose `applyTo` matches the file you're editing.
For Python source under `src/autoboat_telemetry_server/`, that's
`python-source.instructions.md`. For tests, `tests.instructions.md`. For
Docker, `docker.instructions.md`. For workflows, `github-actions.instructions.md`.
For deployment docs and scripts, `deployment-docs.instructions.md`. For
tailscale, `tailscale.instructions.md`.

If no existing file fits, add a new section to the closest-matching file
rather than creating a new one. Instruction files are loaded into the agent
context automatically based on the `applyTo` glob, so the detail will reach
the next editor without cluttering the code.

## What the code comment should look like

A single line, pointing at the instruction file and (optionally) the section:

```python
# see .github/instructions/python-source.instructions.md#Lock decorators
# for why reads block and writes return 429
```

or even shorter when the section name is obvious from the file:

```python
# lock asymmetry: see .github/instructions/python-source.instructions.md
```

Do **not** restate the explanation in the comment — the whole point is that
the explanation lives in one place (the instruction file) and the code stays
scannable.

## Comment style: lowercase, no trailing period

Write all `#` comments in **lowercase** and **do not end them with a period**.
This matches common Python style (PEP 8 is silent on comment casing, but the
dominant convention in mature codebases is lowercase, no terminating period).

- `# see foo.instructions.md#Bar` — good
- `# See foo.instructions.md#Bar.` — bad (capital + period)
- `# increment the 429 counter` — good
- `# Increment the 429 counter.` — bad

Exception: identifiers, file paths, URLs, and section names keep their
original casing (e.g. `#CORS precedence`, `src/instance/config.py`). The
rule applies to the prose around them, not to proper nouns.

This applies to inline `# ...` comments only. Docstrings follow the numpy
convention (sentence case with periods) as configured in `ruff.toml`.

## Why

- Big comment blocks push the actual code below the fold. On a 130-column
  terminal, a 12-line comment block before a 3-line function makes the
  function hard to see.
- Rationale drifts from the code faster than the code drifts from the
  rationale. When the explanation lives in an instruction file that's
  loaded into agent context, it's more likely to stay correct and to
  actually be read.
- Instruction files are version-controlled alongside the code, so the
  detail isn't lost — it's just not in the way.

## Examples

### Bad (multi-line block in code)

```python
# The Cloudflare Tunnel is outbound-only — do not open inbound ports.
# The host does NOT accept inbound 80/443. `cloudflared` dials out to
# Cloudflare's edge; the edge terminates TLS and proxies back over the
# tunnel. Never reintroduce nginx, certbot, or any inbound-port-based
# ingress. History lesson (DNS-01 fixed cert issuance but not serving,
# because inbound 443 was still blocked; only a tunnel solves both) is
# in .github/instructions/deployment-docs.instructions.md under
# "Why a tunnel (history)".
```

### Good (single-line pointer in code, detail in instructions)

In code:

```python
# Tunnel is outbound-only — see .github/instructions/deployment-docs.instructions.md#Tunnel.
```

In `.github/instructions/deployment-docs.instructions.md`:

```markdown
## Why a tunnel (history)

The Cloudflare Tunnel is outbound-only — do not open inbound ports.
The host does NOT accept inbound 80/443. `cloudflared` dials out to
Cloudflare's edge; the edge terminates TLS and proxies back over the
tunnel. Never reintroduce nginx, certbot, or any inbound-port-based
ingress. (DNS-01 fixed cert issuance but not serving, because inbound
443 was still blocked; only a tunnel solves both.)
```

## Exception: module docstrings

A module docstring summarizing what the module does (1-5 lines) is fine and
often useful. The rule targets *comment blocks* (`#`-prefixed prose), not
docstrings. If a module docstring grows past ~5 lines, move the explanatory
prose to an instruction file and trim the docstring to a one-line summary.
