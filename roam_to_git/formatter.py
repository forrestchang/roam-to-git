import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Match, Tuple


def read_markdown_directory(raw_directory: Path) -> Dict[str, str]:
    contents = {}
    for file in raw_directory.iterdir():
        if file.is_dir():
            # We recursively add the content of sub-directories.
            # They exist when there is a / in the note name.
            for child_name, content in read_markdown_directory(file).items():
                contents[f"{file.name}/{child_name}"] = content
        if not file.is_file():
            continue
        content = file.read_text(encoding="utf-8")
        parts = file.parts[len(raw_directory.parts) :]
        file_name = os.path.join(*parts)
        contents[file_name] = content
    return contents


def get_back_links(contents: Dict[str, str]) -> Dict[str, List[Tuple[str, Match]]]:
    forward_links = {
        file_name: extract_links(content) for file_name, content in contents.items()
    }
    return _build_back_links(forward_links)


def format_markdown(contents: Dict[str, str]) -> Dict[str, str]:
    forward_links = {
        file_name: extract_links(content) for file_name, content in contents.items()
    }
    back_links = _build_back_links(forward_links)
    unlinked_links = _build_unlinked_links(contents, forward_links)
    # Format and write the markdown files
    out = {}
    for file_name, content in contents.items():
        # We add the backlinks first, because they use the position of the characters
        # of the regex matches
        content = add_back_links(content, back_links[file_name])
        content = add_unlinked_links(content, unlinked_links[file_name])

        # Format content. Backlinks content will be formatted automatically.
        content = format_to_do(content)
        link_prefix = "../" * sum("/" in char for char in file_name)
        content = format_link(content, link_prefix=link_prefix)
        if len(content) > 0:
            out[file_name] = content

    return out


def format_to_do(contents: str):
    contents = re.sub(r"{{\[\[TODO\]\]}} *", r"[ ] ", contents)
    contents = re.sub(r"{{\[\[DONE\]\]}} *", r"[x] ", contents)
    return contents


def _build_back_links(
    forward_links: Dict[str, List[Match]]
) -> Dict[str, List[Tuple[str, Match]]]:
    back_links: Dict[str, List[Tuple[str, Match]]] = defaultdict(list)
    for file_name, links in forward_links.items():
        for link in links:
            back_links[f"{link.group(1)}.md"].append((file_name, link))
    return back_links


def _build_unlinked_links(
    contents: Dict[str, str], forward_links: Dict[str, List[Match]]
) -> Dict[str, List[Tuple[str, str, Match]]]:
    """Find plain-text mentions of pages (including aliases) that are not already linked."""
    unlinked: Dict[str, List[Tuple[str, str, Match]]] = defaultdict(list)
    page_names = []
    aliases: Dict[str, List[str]] = defaultdict(list)
    for file_name, content in contents.items():
        name = file_name[:-3]
        page_names.append((file_name, name))
        aliases[file_name] = _extract_aliases(content)

    for source_file, content in contents.items():
        spans = _link_spans(forward_links[source_file])
        url_spans = _url_spans(content)
        for target_file, target_name in page_names:
            if target_file == source_file:
                continue
            terms = _unique_terms([target_name] + aliases.get(target_file, []))
            seen_spans = set()
            for term in terms:
                for match in _find_mentions_outside_links(
                    content, term, spans, url_spans
                ):
                    key = (match.start(), match.end())
                    if key in seen_spans:
                        continue
                    seen_spans.add(key)
                    unlinked[target_file].append((source_file, term, match))
    return unlinked


def extract_links(string: str) -> List[Match]:
    out = list(re.finditer(r"\[\[" r"([^\]\n]+)" r"\]\]", string))
    # Match hashtags as links
    out.extend(re.finditer(r"#([a-zA-Z-_0-9]+)", string))
    # Match attributes
    out.extend(
        re.finditer(
            r"(?:^|\n) *- "
            r"((?:[^:\n]|:[^:\n])+)"  # Match everything except ::
            r"::",
            string,
        )
    )
    return out


def add_back_links(content: str, back_links: List[Tuple[str, Match]]) -> str:
    if not back_links:
        return content
    files = sorted(
        set((file_name[:-3], match) for file_name, match in back_links),
        key=lambda e: (e[0], e[1].start()),
    )
    new_lines: List[str] = []
    file_before = None
    for file, match in files:
        if file != file_before:
            new_lines.append(f"## [{file}](<{file}.md>)")
        file_before = file

        context = _extract_line_with_children(match.string, match.start(), match.end())

        new_lines.extend([context, ""])
    backlinks_str = "\n".join(new_lines)
    return f"{content}\n# Backlinks ({len(back_links)})\n{backlinks_str}\n"


def add_unlinked_links(content: str, unlinked_links: List[Tuple[str, str, Match]]) -> str:
    if not unlinked_links:
        return content
    grouped: Dict[str, List[Tuple[str, Match]]] = defaultdict(list)
    for source_file, term, match in unlinked_links:
        grouped[term].append((source_file, match))

    new_lines: List[str] = []
    display_count = 0
    for term in sorted(grouped.keys()):
        new_lines.append(f"## {term}")
        entries = sorted(
            grouped[term],
            key=lambda e: (e[0], e[1].start()),
        )
        file_before = None
        seen_blocks = set()
        for source_file, match in entries:
            file = source_file[:-3]
            if file != file_before:
                new_lines.append(f"### [{file}](<{file}.md>)")
            file_before = file
            context = _extract_line_with_children(
                match.string, match.start(), match.end()
            )
            block_key = (file, context)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            new_lines.extend([context, ""])
            display_count += 1
    if display_count == 0:
        return content
    backlinks_str = "\n".join(new_lines)
    return f"{content}\n# Unlinked references ({display_count})\n{backlinks_str}\n"


def _extract_line_with_children(text: str, start: int, end: int) -> str:
    """Return the line containing the match plus one level of children below it."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)

    current_line = text[line_start:line_end].rstrip()
    base_indent = len(current_line) - len(current_line.lstrip(" "))

    child_lines: List[str] = []
    pos = line_end + 1
    first_child_indent = None
    second_child_indent = None

    while pos < len(text):
        next_end = text.find("\n", pos)
        if next_end == -1:
            next_end = len(text)
        line = text[pos:next_end].rstrip("\n")

        if line.strip() == "":
            # Preserve blank lines directly under the current block
            child_lines.append(line)
            pos = next_end + 1
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent <= base_indent:
            break

        if first_child_indent is None:
            first_child_indent = indent
        elif indent < first_child_indent:
            break

        if indent > first_child_indent and second_child_indent is None:
            second_child_indent = indent

        if second_child_indent is not None and indent > second_child_indent:
            break

        child_lines.append(line)
        pos = next_end + 1

    lines = [current_line, *child_lines]
    if base_indent > 0:
        lines = [_strip_leading_spaces(l, base_indent) for l in lines]

    block = "\n".join(lines).rstrip("\n")
    return block


def _strip_leading_spaces(line: str, count: int) -> str:
    """Strip up to `count` leading spaces, preserving relative indentation."""
    if line.strip() == "":
        return line
    leading = len(line) - len(line.lstrip(" "))
    to_remove = min(leading, count)
    return line[to_remove:]


def _link_spans(matches: List[Match]) -> List[Tuple[int, int]]:
    return sorted([(m.start(), m.end()) for m in matches], key=lambda s: s[0])


def _find_mentions_outside_links(
    text: str,
    term: str,
    link_spans: List[Tuple[int, int]],
    url_spans: List[Tuple[int, int]],
) -> List[Match]:
    """Find plain-text mentions of term that are not inside [[link]] spans."""
    if not term:
        return []

    def inside(pos: int) -> bool:
        for start, end in link_spans:
            if start <= pos < end:
                return True
            if start > pos:
                break
        return False

    def inside_url(pos: int) -> bool:
        for start, end in url_spans:
            if start <= pos < end:
                return True
            if start > pos:
                break
        return False

    matches: List[Match] = []
    for match in re.finditer(re.escape(term), text):
        if inside(match.start()) or inside_url(match.start()):
            continue
        matches.append(match)
    return matches


def _url_spans(text: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"https?://\S+", text)]


def _extract_aliases(content: str) -> List[str]:
    """Extract comma-separated aliases from an Aliases:: attribute."""
    matches = re.findall(
        r"^ *- +Aliases:: *(.+)$", content, flags=re.MULTILINE | re.IGNORECASE
    )
    aliases: List[str] = []
    for match in matches:
        parts = [a.strip() for a in match.split(",") if a.strip()]
        aliases.extend(parts)
    return aliases


def _unique_terms(terms: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
    return out


def format_link(string: str, link_prefix="") -> str:
    """Transform a RoamResearch-like link to a Markdown link.

    @param link_prefix: Add the given prefix before all links.
        WARNING: not robust to special characters.
    """
    # Regex are read-only and can't parse [[[[recursive]] [[links]]]], but they do the job.
    # We use a special syntax for links that can have SPACES in them
    # Format internal reference: [[mynote]]
    string = re.sub(
        r"\[\["  # We start with [[
        # TODO: manage a single ] in the tag
        r"([^\]\n]+)" r"\]\]",  # Everything except ]
        rf"[\1](<{link_prefix}\1.md>)",
        string,
        flags=re.MULTILINE,
    )

    # Format hashtags: #mytag
    string = re.sub(
        r"#([a-zA-Z-_0-9]+)", rf"[\1](<{link_prefix}\1.md>)", string, flags=re.MULTILINE
    )

    # Format attributes
    string = re.sub(
        r"(^ *- )"  # Match the beginning, like '  - '
        r"(([^:\n]|:[^:\n])+)"  # Match everything except ::
        r"::",
        rf"\1**[\2](<{link_prefix}\2.md>):**",  # Format Markdown link
        string,
        flags=re.MULTILINE,
    )
    return string
