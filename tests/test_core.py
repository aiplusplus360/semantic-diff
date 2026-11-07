import json
import unittest

from semanticdiff.core import Change, PromptDiff, classify, clauses, diff, extract_formats


class ClauseTests(unittest.TestCase):
    def test_sentences(self):
        self.assertEqual(clauses("Be concise. Never invent facts."),
                         ["be concise", "never invent facts"])

    def test_bullets(self):
        self.assertEqual(clauses("- one\n- two"), ["one", "two"])

    def test_numbered(self):
        self.assertEqual(clauses("1. first\n2. second"), ["first", "second"])

    def test_normalises_case_and_space(self):
        self.assertEqual(clauses("  STOP   shouting  "), ["stop shouting"])

    def test_strips_trailing_punctuation(self):
        self.assertEqual(clauses("Do it now!"), ["do it now"])

    def test_blank_and_punctuation_only(self):
        self.assertEqual(clauses("\n\n ... \n"), [])


class ClassifyTests(unittest.TestCase):
    def test_role(self):
        self.assertEqual(classify("You are a reviewer"), "role")

    def test_role_contraction(self):
        self.assertEqual(classify("You're an editor"), "role")

    def test_format(self):
        self.assertEqual(classify("Return JSON"), "format")

    def test_constraint(self):
        self.assertEqual(classify("Never invent facts"), "constraint")

    def test_constraint_must(self):
        self.assertEqual(classify("You must cite sources"), "constraint")

    def test_example(self):
        self.assertEqual(classify("Example: 1 + 1"), "example")

    def test_tone(self):
        self.assertEqual(classify("Keep a friendly tone"), "tone")

    def test_other(self):
        self.assertEqual(classify("The document is about taxes"), "other")

    def test_role_beats_format(self):
        # "you are" is the stronger signal even when a format is mentioned.
        self.assertEqual(classify("You are a JSON generator"), "role")


class FormatTests(unittest.TestCase):
    def test_collects_all_formats(self):
        self.assertEqual(extract_formats("Return JSON, never YAML"), {"json", "yaml"})

    def test_ignores_non_formats(self):
        self.assertEqual(extract_formats("Return the value"), set())

    def test_markdown_synonyms(self):
        self.assertEqual(extract_formats("Use Markdown"), {"markdown"})


class DiffTests(unittest.TestCase):
    def test_identical(self):
        result = diff("Be concise.", "Be concise.")
        self.assertEqual(result.severity, "none")
        self.assertFalse(result)

    def test_added_constraint_is_medium(self):
        result = diff("You are a reviewer. Return JSON.",
                      "You are a reviewer. Return JSON. Never invent citations.")
        self.assertEqual(result.severity, "medium")
        self.assertEqual([c.category for c in result.added], ["constraint"])
        self.assertEqual(result.breaking, [])

    def test_removed_constraint_is_breaking(self):
        result = diff("Never invent citations. Be concise.",
                      "Be concise.")
        self.assertEqual(result.severity, "high")
        self.assertEqual([c.category for c in result.removed], ["constraint"])

    def test_format_change_is_breaking(self):
        result = diff("Return JSON.", "Return YAML.")
        self.assertEqual(result.severity, "high")
        self.assertEqual(result.changed[0].category, "format")

    def test_removed_format_is_breaking(self):
        result = diff("Return JSON. Be concise.", "Be concise.")
        self.assertEqual(result.severity, "high")

    def test_role_change_is_breaking(self):
        result = diff("You are a reviewer.", "You are an editor.")
        self.assertEqual(result.severity, "high")
        self.assertEqual(result.changed[0].category, "role")

    def test_removed_example_is_medium(self):
        result = diff("Example: 1 + 1. Return JSON.", "Return JSON.")
        self.assertEqual(result.severity, "medium")

    def test_reworded_clause_is_changed_not_added_removed(self):
        result = diff("Answer in a concise way.", "Answer in a concise manner.")
        self.assertEqual(result.changed[0].action, "changed")
        self.assertEqual(result.added, [])
        self.assertEqual(result.removed, [])

    def test_unrelated_additions_are_low(self):
        result = diff("The document is about taxes.", "The document is about taxes. "
                                                      "It is long.")
        self.assertEqual(result.severity, "low")

    def test_custom_threshold(self):
        result = diff("alpha beta gamma", "alpha beta delta", similarity=0.99)
        self.assertTrue(result.added and result.removed)

    def test_negation_removed_is_high(self):
        # Same words, but "never" disappears: the constraint inverted.
        result = diff("Never mention pricing.", "Mention pricing.")
        self.assertEqual(result.severity, "high")


class ReportTests(unittest.TestCase):
    def test_dict_is_json_serialisable(self):
        payload = diff("Return JSON.", "Return YAML.").as_dict()
        json.dumps(payload)
        self.assertEqual(payload["severity"], "high")
        self.assertEqual(len(payload["breaking"]), 1)

    def test_summary(self):
        self.assertIn("severity", diff("Return JSON.", "Return YAML.").summary())

    def test_empty_summary(self):
        self.assertEqual(diff("same", "same").summary(), "no behavioural change")

    def test_change_dict_shape(self):
        change = Change("format", "changed", "json", "yaml", "high")
        self.assertEqual(set(change.as_dict()), {"category", "action", "before",
                                                 "after", "severity"})

    def test_prompt_diff_defaults(self):
        self.assertEqual(PromptDiff().severity, "none")


if __name__ == "__main__":
    unittest.main()
