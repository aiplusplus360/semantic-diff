"""Diff two prompt versions by what they *do*, not by which characters moved.

A line diff on a prompt is noise. Reflowing one sentence marks six lines
changed; renaming a variable marks two. The changes that actually alter
behaviour are a different set:

- an output format changed (`JSON` → `YAML`);
- a constraint was removed (`never invent citations`);
- the role changed (`you are a reviewer` → `you are an editor`);
- the examples disappeared.

This splits each prompt into clauses, classifies each clause by the job it does,
and compares the clause sets per category. Reworded clauses become ``changed``
rather than one removal plus one addition, so review is about behaviour.

>>> result = diff("You are a helpful assistant. Return JSON.",
...               "You are a helpful assistant. Return JSON. Never add commentary.")
>>> result.severity
'medium'
>>> [change.category for change in result.added]
['constraint']
>>> result.breaking
[]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = [
    "Change",
    "PromptDiff",
    "clauses",
    "classify",
    "extract_formats",
    "diff",
    "SIMILARITY_THRESHOLD",
]

SIMILARITY_THRESHOLD = 0.6
SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}

_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WS = re.compile(r"\s+")

_ROLE = re.compile(r"\b(you are|you're|act as|your role|assume the role)\b")
_EXAMPLE = re.compile(r"\b(example|input|output|user|assistant|question|answer)\s*:")
_FORMAT = re.compile(r"\b(json|yaml|yml|csv|tsv|xml|markdown|md|html|schema|"
                     r"bullet(?:ed)? list|numbered list|table|plain text)\b")
_CONSTRAINT = re.compile(r"\b(must|must not|never|always|only|do not|don't|"
                         r"should|avoid|at most|at least|no more than|exactly|"
                         r"limit(?:ed)? to)\b")
_TONE = re.compile(r"\b(concise|formal|friendly|professional|tone|verbose|"
                   r"terse|neutral|casual)\b")
_NEGATION = re.compile(r"\b(not|never|don't|do not|avoid|no)\b")

_FORMAT_KINDS = {"json", "yaml", "yml", "csv", "tsv", "xml", "markdown", "md",
                 "html", "table", "plain text"}

_SEVERITY = {
    ("format", "changed"): "high",
    ("format", "removed"): "high",
    ("role", "removed"): "high",
    ("role", "changed"): "high",
    ("constraint", "removed"): "high",
    ("example", "removed"): "medium",
    ("format", "added"): "medium",
    ("constraint", "added"): "medium",
    ("constraint", "changed"): "medium",
    ("role", "added"): "medium",
    ("example", "changed"): "low",
    ("tone", "changed"): "low",
}


@dataclass(frozen=True)
class Change:
    """One behavioural difference between two prompt versions."""

    category: str
    action: str
    before: str
    after: str
    severity: str

    def as_dict(self) -> Dict[str, str]:
        return {"category": self.category, "action": self.action,
                "before": self.before, "after": self.after,
                "severity": self.severity}


@dataclass
class PromptDiff:
    """The full difference, with the worst severity surfaced."""

    added: List[Change] = field(default_factory=list)
    removed: List[Change] = field(default_factory=list)
    changed: List[Change] = field(default_factory=list)
    formats_before: Set[str] = field(default_factory=set)
    formats_after: Set[str] = field(default_factory=set)

    @property
    def severity(self) -> str:
        worst = "none"
        for change in self.all_changes:
            if SEVERITY_ORDER[change.severity] > SEVERITY_ORDER[worst]:
                worst = change.severity
        return worst

    @property
    def all_changes(self) -> List[Change]:
        return self.added + self.removed + self.changed

    @property
    def breaking(self) -> List[Change]:
        return [change for change in self.all_changes if change.severity == "high"]

    def __bool__(self) -> bool:
        return bool(self.all_changes)

    def as_dict(self) -> Dict[str, object]:
        return {
            "severity": self.severity,
            "breaking": [change.as_dict() for change in self.breaking],
            "added": [change.as_dict() for change in self.added],
            "removed": [change.as_dict() for change in self.removed],
            "changed": [change.as_dict() for change in self.changed],
            "formats_before": sorted(self.formats_before),
            "formats_after": sorted(self.formats_after),
        }

    def summary(self) -> str:
        if not self.all_changes:
            return "no behavioural change"
        parts = ["%d added, %d removed, %d changed"
                 % (len(self.added), len(self.removed), len(self.changed))]
        if self.breaking:
            parts.append("%d breaking" % len(self.breaking))
        return "%s (severity: %s)" % (", ".join(parts), self.severity)


def _normalise(text: str) -> str:
    text = _WS.sub(" ", text.strip().lower())
    return text.rstrip(" .;:!?")


def clauses(text: str) -> List[str]:
    """Split a prompt into normalised clauses (bullets, sentence boundaries).

    >>> clauses("Be concise. Never invent facts.")
    ['be concise', 'never invent facts']
    """
    expanded = _BULLET.sub("\n", text)
    pieces: List[str] = []
    for line in expanded.splitlines():
        line = line.strip()
        if not line:
            continue
        for sentence in _SENTENCE_END.split(line):
            normalised = _normalise(sentence)
            if normalised:
                pieces.append(normalised)
    return pieces


def classify(clause: str) -> str:
    """Category of a clause, by the job it does.

    >>> [classify(c) for c in ["You are a reviewer", "Return JSON",
    ...                        "Never invent facts", "Example: 1 + 1"]]
    ['role', 'format', 'constraint', 'example']
    """
    text = clause.lower()
    if _ROLE.search(text):
        return "role"
    if _EXAMPLE.search(text):
        return "example"
    if _FORMAT.search(text):
        return "format"
    if _CONSTRAINT.search(text):
        return "constraint"
    if _TONE.search(text):
        return "tone"
    return "other"


def extract_formats(text: str) -> Set[str]:
    """Output formats named anywhere in the prompt.

    >>> sorted(extract_formats("Return JSON. Never return YAML."))
    ['json', 'yaml']
    """
    found = set()
    for match in _FORMAT.finditer(text.lower()):
        value = match.group(1)
        if value in _FORMAT_KINDS:
            found.add(value)
    return found


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _pair(before: List[str], after: List[str], category: str,
          threshold: float = SIMILARITY_THRESHOLD
          ) -> Tuple[List[Change], List[Change], List[Change]]:
    """Pair reworded clauses within a category; the rest are pure add/remove."""
    added: List[Change] = []
    removed: List[Change] = []
    changed: List[Change] = []
    remaining_before = list(before)
    remaining_after = list(after)
    # Clauses present in both versions are not a change at all.
    for left in list(remaining_before):
        if left in remaining_after:
            remaining_before.remove(left)
            remaining_after.remove(left)
    for left in list(remaining_before):
        best: Optional[str] = None
        best_score = 0.0
        for right in remaining_after:
            score = _similarity(left, right)
            if score > best_score:
                best, best_score = right, score
        if best is not None and best_score >= threshold:
            removed_negation = bool(_NEGATION.search(left)) and not bool(_NEGATION.search(best))
            severity = _SEVERITY.get((category, "changed"), "low")
            if category == "constraint" and removed_negation:
                severity = "high"
            changed.append(Change(category, "changed", left, best, severity))
            remaining_before.remove(left)
            remaining_after.remove(best)
    for left in remaining_before:
        severity = _SEVERITY.get((category, "removed"), "low")
        removed.append(Change(category, "removed", left, "", severity))
    for right in remaining_after:
        severity = _SEVERITY.get((category, "added"), "low")
        added.append(Change(category, "added", "", right, severity))
    return added, removed, changed


def diff(before: str, after: str, similarity: float = SIMILARITY_THRESHOLD) -> PromptDiff:
    """Classify the behavioural difference between two prompts.

    >>> result = diff("Return JSON.", "Return YAML.")
    >>> result.severity
    'high'
    >>> diff("Be concise.", "Be concise.").severity
    'none'
    """
    grouped_before: Dict[str, List[str]] = {}
    grouped_after: Dict[str, List[str]] = {}
    for clause in clauses(before):
        grouped_before.setdefault(classify(clause), []).append(clause)
    for clause in clauses(after):
        grouped_after.setdefault(classify(clause), []).append(clause)

    result = PromptDiff(formats_before=extract_formats(before),
                        formats_after=extract_formats(after))
    for category in sorted(set(grouped_before) | set(grouped_after)):
        added, removed, changed = _pair(grouped_before.get(category, []),
                                        grouped_after.get(category, []),
                                        category, similarity)
        result.added.extend(added)
        result.removed.extend(removed)
        result.changed.extend(changed)

    # A format named in the prompt but never in a clause ("output must be
    # valid" -> "output must be valid YAML") is still a format change.
    if not any(change.category == "format" for change in result.all_changes):
        for kind in sorted(result.formats_after - result.formats_before):
            result.added.append(Change("format", "added", "", kind, "medium"))
        for kind in sorted(result.formats_before - result.formats_after):
            result.removed.append(Change("format", "removed", kind, "", "high"))
    return result
