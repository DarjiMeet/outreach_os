"""Select source excerpts, without generating facts, for a small LLM input budget."""

import re
from dataclasses import dataclass


FACT_PATTERNS = {
    "business": r"\b(?:provides?|offers?|builds?|develops?|manufactures?|platform|software|products?|services?)\b",
    "customers": r"\b(?:customers?|retailers?|enterprises?|businesses|hospitals?|target market|serves?)\b",
    "location": r"\b(?:headquarters?|headquartered|based in|located in|offices?|address)\b",
    "employees": r"\b(?:employees?|headcount|team size|people)\b",
    "commercial": r"\b(?:pricing|subscription|per month|annually|B2B|B2C|SaaS)\b",
    "signals": r"\b(?:hiring|funding|raised|launched|founded|expansion)\b",
    "technology": r"\b(?:integrates?|integrations?|built with|powered by|technologies)\b",
}
NAVIGATION = re.compile(
    r"^(?:skip to .*|menu|home|sign in|sign up|log in|login|cookie (?:policy|preferences)|"
    r"privacy policy|terms (?:of use|of service|and conditions)|all rights reserved|"
    r"accept (?:all )?cookies|manage cookies|follow us|share|learn more|read more)[.!\s]*$", re.I,
)
SEPARATOR = "\n[...]\n"


@dataclass
class Excerpt:
    context: str
    text: str
    index: int

    @property
    def rendered(self) -> str:
        return "\n".join(part for part in (self.context, self.text) if part)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _features(text: str) -> set[str]:
    return {name for name, pattern in FACT_PATTERNS.items() if re.search(pattern, text, re.I)}


def _chunks(text: str, size: int = 550) -> list[str]:
    """Prefer complete sentences; split a very long sentence at word boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    chunks = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > size:
            chunks.append(current)
            current = ""
        while len(sentence) > size:
            cut = sentence.rfind(" ", 0, size + 1)
            if cut <= 0:
                # A huge indivisible token is not useful evidence.
                break
            # Do not split inside a Markdown company link.
            if sentence[:cut].count("[") > sentence[:cut].count(")"):
                close = sentence.find(")", cut)
                if close >= 0:
                    cut = close + 1
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        current = " ".join(part for part in (current, sentence) if part)
    if current:
        chunks.append(current)
    return chunks


def _excerpts(content: str) -> list[Excerpt]:
    excerpts = []
    headings: list[tuple[int, str]] = []
    table_header = ""
    table_rows: list[str] = []
    table_context = ""

    def add(text: str, context: str = "", *, atomic: bool = False):
        parts = [text] if atomic else _chunks(text)
        for index, part in enumerate(parts):
            if part:
                # Preserve the paragraph's subject in later unheaded fragments.
                subject = ""
                if index and not context:
                    subject = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", parts[0])[0]
                excerpts.append(Excerpt(context or subject, part, len(excerpts)))

    def flush_table():
        nonlocal table_header, table_rows
        if table_rows:
            add("\n".join(table_rows), "\n".join(filter(None, [table_context, table_header])), atomic=True)
        table_header = ""
        table_rows = []

    lines = [_clean(raw) for raw in content.splitlines() if raw.strip()]

    def cells(line: str) -> list[str]:
        # Remove only borders, not empty first cells used for continuation.
        return [cell.strip() for cell in line.removeprefix("|").removesuffix("|").split("|")]

    def separator(line: str) -> bool:
        return "|" in line and all(re.fullmatch(r":?-+:?", cell) for cell in cells(line))

    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+", line)
        if heading:
            flush_table()
            level = len(heading[1])
            headings = [(depth, value) for depth, value in headings if depth < level]
            headings.append((level, line))
            continue
        context = "\n".join(value for _, value in headings)
        # Keep directory rows intact and repeat their column labels.
        if line.count("|") >= 2:
            if separator(line):
                continue
            if index + 1 < len(lines) and separator(lines[index + 1]):
                flush_table()
                table_header = line
                table_context = context
            elif cells(line)[0]:
                if table_rows:
                    add("\n".join(table_rows), "\n".join(filter(None, [table_context, table_header])), atomic=True)
                table_context = context
                table_rows = [line]
            else:
                # An empty first cell commonly continues the preceding company row.
                table_rows.append(line)
            continue
        flush_table()
        label = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", line).strip(" *-|")
        if NAVIGATION.fullmatch(label):
            continue
        # Menus containing many links and almost no prose should not fill the window.
        links = re.findall(r"\[([^]]+)\]\([^)]*\)", line)
        remaining = re.sub(r"\[[^]]+\]\([^)]*\)", "", line).strip(" *-|/")
        if len(links) >= 3 and len(remaining) < 25:
            continue
        add(line, context)
    flush_table()
    if not excerpts and headings:
        add("\n".join(value for _, value in headings))
    return excerpts


def select_evidence(content: str | None, max_chars: int = 2000, *, query_terms: list[str] | tuple[str, ...] = ()) -> str | None:
    if not content:
        return None
    if max_chars <= 0:
        return ""
    terms = {token.lower() for term in query_terms for token in re.findall(r"\w{3,}", term)}
    candidates = []
    seen = set()
    for excerpt in _excerpts(content):
        key = _clean(excerpt.rendered).casefold()
        if key in seen:
            continue
        seen.add(key)
        features = _features(excerpt.rendered)
        words = set(re.findall(r"\w+", excerpt.rendered.lower()))
        score = 1 + 3 * len(features) + min(4, len(terms & words))
        if re.search(r"https?://|\bwww\.", excerpt.text):
            score += 2
        if "|" in excerpt.text:  # linked identities, column labels and facts travel together
            score += 3
        candidates.append((excerpt, features, score))

    # Bound selection work while scoring all available source blocks, including late ones.
    candidates = sorted(candidates, key=lambda item: (-item[2], item[0].index))[:150]
    selected = []
    used = 0
    covered = set()
    while candidates:
        candidates.sort(key=lambda item: (-(item[2] + 3 * len(item[1] - covered)), item[0].index))
        excerpt, features, _ = candidates.pop(0)
        cost = len(excerpt.rendered) + (len(SEPARATOR) if selected else 0)
        if used + cost > max_chars:
            continue  # never detach a company's facts or cut a Markdown link
        selected.append(excerpt)
        used += cost
        covered.update(features)
    # Restore source order; explicitly mark non-contiguous excerpts.
    return SEPARATOR.join(item.rendered for item in sorted(selected, key=lambda item: item.index))
