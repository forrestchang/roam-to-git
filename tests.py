#!/usr/bin/env python3
import os
import unittest
import mypy.api
from typing import List

from roam_to_git.formatter import (
    extract_links,
    format_link,
    format_markdown,
    format_to_do,
)


class TestFormatTodo(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_to_do(""), "")

    def test_no_link(self):
        self.assertEqual(format_to_do("string"), "string")

    def test_to_do(self):
        self.assertEqual(format_to_do("a\n- {{[[TODO]]}}string"), "a\n- [ ] string")

    def test_done(self):
        self.assertEqual(format_to_do("a\n- {{[[DONE]]}}string"), "a\n- [x] string")

    def test_something_else(self):
        self.assertEqual(
            format_to_do("a\n- {{[[ZZZ]]}}string"), "a\n- {{[[ZZZ]]}}string"
        )


class TestFormatLinks(unittest.TestCase):
    """Test that we correctly format the links"""

    def test_empty(self):
        self.assertEqual(format_link(""), "")

    def test_no_link(self):
        self.assertEqual(format_link("string"), "string")

    def test_one_link(self):
        self.assertEqual(format_link("string [[link]]."), "string [link](<link.md>).")

    def test_one_link_prefix(self):
        self.assertEqual(
            format_link("string [[link]].", link_prefix="../../"),
            "string [link](<../../link.md>).",
        )

    def test_two_links(self):
        self.assertEqual(
            format_link("[[link]] [[other]]"), "[link](<link.md>) [other](<other.md>)"
        )

    def test_one_hashtag(self):
        self.assertEqual(format_link("string #link."), "string [link](<link.md>).")

    def test_two_hashtag(self):
        self.assertEqual(
            format_link("#link #other"), "[link](<link.md>) [other](<other.md>)"
        )

    def test_attribute(self):
        self.assertEqual(
            format_link("  - string:: link"), "  - **[string](<string.md>):** link"
        )

    def test_attribute_then_attribute_like(self):
        self.assertEqual(
            format_link("- attrib:: string:: val"),
            "- **[attrib](<attrib.md>):** string:: val",
        )

    def test_attribute_with_colon(self):
        self.assertEqual(
            format_link("- attrib:is:: string"),
            "- **[attrib:is](<attrib:is.md>):** string",
        )

    def test_attribute_new_line(self):
        self.assertEqual(
            format_link("  - attrib:: string\n  " "- attrib:: string"),
            "  - **[attrib](<attrib.md>):** string\n "
            " - **[attrib](<attrib.md>):** string",
        )


class TestBacklinks(unittest.TestCase):
    def test_child_context_in_backlinks(self):
        contents = {
            "Source.md": "- Parent [[Target]]\n  - Child context\n    - Grandchild\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn(
            "- Parent [Target](<Target.md>)\n  - Child context",
            target,
        )

    def test_nested_indent_preserved(self):
        contents = {
            "Source.md": "  - Nested [[Target]]\n    - Child\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn(
            "  - Nested [Target](<Target.md>)\n    - Child",
            target,
        )

    def test_two_child_levels(self):
        contents = {
            "Source.md": "- Parent [[Target]]\n  - Child\n    - Grandchild\n      - Great grandchild\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn(
            "- Parent [Target](<Target.md>)\n  - Child\n    - Grandchild",
            target,
        )

    def test_dedents_base_indent_to_avoid_code_block(self):
        contents = {
            "Source.md": "    - Deep [[Target]]\n      - Child\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn(
            "- Deep [Target](<Target.md>)\n  - Child",
            target,
        )


class TestUnbacklinks(unittest.TestCase):
    def test_plain_text_mentions(self):
        contents = {
            "Source.md": "- Mention Target\n  - Child\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn("# Unlinked references", target)
        self.assertIn("- Mention Target\n  - Child", target)

    def test_ignores_existing_links(self):
        contents = {
            "Source.md": "- Parent [[Target]]\n  - Child\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertNotIn("# Unlinked references", target)

    def test_dedent_unlinked_block(self):
        contents = {
            "Source.md": "    - Deep Target mention\n      - Child\n",
            "Target.md": "Content",
        }
        formatted = format_markdown(contents)
        target = formatted["Target.md"]
        self.assertIn("- Deep Target mention\n  - Child", target)


def _extract_links(string) -> List[str]:
    return [m.group(1) for m in extract_links(string)]


class TestExtractLinks(unittest.TestCase):
    """Test that we correctly extract the links, for backreference"""

    def test_empty(self):
        self.assertEqual(_extract_links(""), [])

    def test_no_link(self):
        self.assertEqual(_extract_links("string"), [])

    def test_one_link(self):
        self.assertEqual(_extract_links("string [[link]]."), ["link"])

    def test_two_links(self):
        self.assertEqual(_extract_links("[[link]] [[other]]"), ["link", "other"])

    def test_one_hashtag(self):
        self.assertEqual(_extract_links("string [[link]]."), ["link"])

    def test_two_hashtag(self):
        self.assertEqual(_extract_links("[[link]] [[other]]"), ["link", "other"])

    def test_no_attribute(self):
        self.assertEqual(_extract_links("  - string: link"), [])

    def test_attribute(self):
        self.assertEqual(_extract_links("  - attrib:: link"), ["attrib"])

    def test_attribute_then_attribute_like(self):
        self.assertEqual(_extract_links("- attrib:: link:: val"), ["attrib"])

    def test_attribute_with_colon(self):
        self.assertEqual(_extract_links("- attrib:is:: link"), ["attrib:is"])

    def test_attribute_new_line(self):
        self.assertEqual(
            _extract_links("  - attrib:: link\n  " "- attrib2:: link"),
            ["attrib", "attrib2"],
        )


class TestMypy(unittest.TestCase):
    def _test_mypy(self, files: List[str]):
        stdout, stderr, exit_status = mypy.api.run(["--ignore-missing-imports", *files])
        self.assertEqual(exit_status, 0)

    def test_mypy_rtg(self):
        self._test_mypy(["roam_to_git"])

    def test_mypy_rtg_and_tests(self):
        self._test_mypy(["roam_to_git", "tests.py"])

    def test_mypy_all(self):
        self._test_mypy([str(f) for f in os.listdir(".")
                         if os.path.isfile(f) and f.endswith(".py")
                         and not f.startswith("setup")])


if __name__ == "__main__":
    unittest.main()
