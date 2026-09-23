---
name: design-review
description: "Reviews TcOtlp Structured Text for design issues by spawning one read-only subagent per design check in checks/. Use when asked to check for design issues, run a design review, or audit the code against the design rules (e.g. no fixed-length arrays of objects)."
---

# Design Review

Checks the TwinCAT source against the project's design rules. Each rule is a **check**, one Markdown file in `checks/` next to this file. The review spawns one subagent per check, runs them in parallel, verifies what they report, and gives the user a single report.

The review is read-only. It reports findings and does not fix them unless the user asks for that afterward.

## Arguments

- No arguments: run every check in `checks/` against the default scope.
- Check names (file names without `.md`, e.g. `no-static-object-arrays`): run only those checks.
- A path: review that path instead of the default scope.
- `include-tests`: also review `TcOtlp/test/TEST/`, which is excluded by default.

## Default scope

- Review `TcOtlp/test/OTEL/` (production code).
- Exclude `TcOtlp/test/TEST/` (test suites and test doubles) unless `include-tests` is given.
- Review only Structured Text sources: `*.TcPOU`, `*.TcDUT`, `*.TcGVL`, `*.TcTLEO`. Code lives in the `<![CDATA[ ... ]]>` sections of the XML.

## Workflow

### 1. Collect the checks

List `.claude/skills/design-review/checks/*.md`, and keep only the ones the arguments select. Read each selected check file in full, because its text goes into the subagent prompt.

### 2. Spawn one subagent per check, in parallel

Send every Agent call in a **single message** so the checks run concurrently. Use `subagent_type: "general-purpose"`, and give each agent a prompt built from this template:

```text
You are reviewing TwinCAT 3 Structured Text in the TcOtlp repository at
<absolute repo root> for ONE design rule. This is a read-only review: do not
edit, create, or delete files, and do not run builds or tests.

Scope: <absolute scope paths>. Exclude: <excluded paths>.
Sources are *.TcPOU, *.TcDUT, *.TcGVL and *.TcTLEO XML files; code is inside
CDATA sections. Declarations are in <Declaration>, and bodies are in <ST>.
Methods and properties declare their own VAR blocks, so check those too.

Read CLAUDE.md at the repo root first for domain ownership and the
single-task, bounded-execution rules.

<full text of the check file>

Search exhaustively. Grep for every pattern the check lists, then open each
hit and judge it against the rule and its exceptions. Do not report a
pattern match you have not read in context.

Report every finding in exactly this form, one block per finding:

FINDING
file: <repo-relative path>
line: <1-based line number in the file>
element: <POU name>.<method/property or "declaration">: <variable name>
declaration: <the offending declaration, verbatim>
severity: violation | review
why: <one or two sentences tying it to the rule>
suggestion: <the replacement structure, named from the check's guidance>
END

After the findings, list the exception cases you saw and deliberately did
not report, one line each, as "EXEMPT <file>:<line> <reason>". If there are
no findings, say "NO FINDINGS" and still list the exemptions.
```

### 3. Verify

Subagents can be wrong. For each reported finding:

- Open the file at the reported line and confirm the declaration is really there.
- Re-judge it against the check's rule and exceptions. Drop anything that is exempt, and move anything that's borderline to `review`.
- Merge duplicates, such as the same array reported from both a declaration and a method.

Also scan the `EXEMPT` lines for anything that looks wrongly excused.

### 4. Report

Give the user one report, grouped by check and ordered by severity:

- For each check: its name, the number of findings, and a table with **Location** (`path:line`), **Declaration**, **Severity**, and **Suggested structure**.
- A short list of what was exempted and why, so the user can challenge an exemption.
- Checks with no findings get one line: "`<check>`: no findings".

End by offering to fix the findings. Fixing follows the normal change workflow in CLAUDE.md: work in the owning domain, keep pointer ownership explicit, update the `.plcproj` for new files, and run the TcUnit tests.

## Adding a check

Create `checks/<kebab-case-name>.md` with these sections:

- **Rule**: what is not allowed, stated so that an agent can apply it.
- **Why**: the design reason, tied to CLAUDE.md where possible.
- **What to look for**: concrete grep patterns and the shapes of declarations that break the rule.
- **Exceptions**: what is allowed, and why.
- **Preferred structures**: what to use instead, with existing examples from the codebase.
- **Severity**: when a finding is a `violation` and when it is only `review`.

The workflow picks up new check files automatically.
