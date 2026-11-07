# semantic-diff

**A prompt diff that says "the output format changed" instead of marking every reflowed sentence as a change.**

[![CI](https://github.com/aiplusplus360/semantic-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/aiplusplus360/semantic-diff/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](pyproject.toml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

```console
$ semantic-diff diff prompts/support-v3.txt prompts/support-v4.txt
2 added, 1 removed, 1 changed (severity: high)

  [high    format    ] 'return json' -> 'return yaml'
  [medium  constraint] 'never include personal data'
  [high    constraint] 'always cite the source document'
```

The first output is the change that broke production. The second is the instruction someone added. The third is the one that got deleted during the rewrite.

---

## Why this exists

A prompt is code, and a prompt diff is reviewed like code. But a line diff of prose is not a review tool:

- reflowing a paragraph marks every line changed;
- renaming `{{user}}` to `{{customer}}` marks three lines changed;
- the one deletion that mattered is somewhere in the middle, rendered identically to whitespace noise.

What a reviewer needs is not "what text moved" but "what behaviour changed". That is a classification problem, and it has a small, stable answer: role, format, constraints, examples, tone.

## How it works

1. **Split into clauses** — bullets, numbered items, and sentence boundaries, normalised (lowercase, collapsed whitespace, stripped trailing punctuation).
2. **Classify each clause** by the job it does, with a fixed priority: `role` > `example` > `format` > `constraint` > `tone` > `other`. `"You are a JSON generator"` is a role, not a format.
3. **Compare clause sets per category.** Identical clauses cancel. Remaining clauses are paired by similarity above a threshold and reported as `changed`; the unpaired ones are `added` or `removed`.
4. **Score severity.** A format change, a removed constraint, a role change or a removed example is `high`; an added constraint is `medium`; formatting of prose is `low`.

The pairing step is what makes this better than a set diff: `"Answer in a concise way"` → `"Answer in a concise manner"` is one `changed` clause, not one removal plus one addition.

### Negation is special

`"Never mention pricing."` → `"Mention pricing."` is nearly identical textually (similarity ~0.7) and completely opposite in effect. When a constraint loses its negation, the change is promoted to `high` regardless of similarity.

## Use it as a gate

```bash
semantic-diff diff old.txt new.txt --fail-on-breaking
```

Exit 1 when a breaking change is present, so a prompt PR that changes the output format cannot merge without a reviewer saying so. `--fail-on-change` is the stricter version for prompts where any behavioural drift needs sign-off.

## Install and use

No dependencies. Python 3.9+.

```bash
pip install git+https://github.com/aiplusplus360/semantic-diff
```

```bash
semantic-diff diff before.txt after.txt --json
semantic-diff classify prompt.txt        # see how each clause is categorised
```

`classify` exists because a classifier you cannot inspect is a classifier you cannot trust: when a change is miscategorised, this shows exactly which rule fired.

## Library use

```python
from semanticdiff import diff

result = diff(before, after)
if result.breaking:
    raise SystemExit("%d breaking change(s)" % len(result.breaking))
print(result.summary())
print(result.as_dict())     # JSON serialisable, for a review comment
```

## Tests

```bash
python -m unittest discover -s tests -v
```

34 core tests and 9 CLI tests: clause splitting for sentences, bullets and numbering, every category including the role-beats-format priority, format extraction, added/removed/changed pairing, severity for each change type, negation removal, custom similarity thresholds, JSON serialisability, and the CLI gates.
