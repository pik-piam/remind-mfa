"""Merge two BibTeX files into `docs/all_refs.bib`, keeping only unique entries.

This module deduplicates by BibTeX key. It first reads entries from
`mrmfa_sources.bib`, then `custom_refs.bib` (skipping duplicate keys).

"""

from typing import List, Tuple, Dict, Optional
import re


def _split_entries(text: str) -> List[str]:
    """Split raw bibtex file content into individual entry strings.

    This finds occurrences of '@' starting an entry and slices between them.
    """
    # Find all start indices of entries (an '@' followed by word chars)
    starts = [m.start() for m in re.finditer(r"@\w+\s*\(", text)]
    # Also allow entries that use brace style: @article{key,
    starts += [m.start() for m in re.finditer(r"@\w+\s*\{", text)]
    starts = sorted(set(starts))
    if not starts:
        return []
    entries = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        entries.append(text[s:end].strip())
    return entries


def _extract_key(entry: str) -> Optional[str]:
    """Extract the BibTeX key from an entry, or None if not found."""
    m = re.match(r"@\w+\s*[\{\(]\s*([^,\s]+)", entry, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def merge_bib_files(src_paths: List[str], out_path: str) -> Tuple[int, int, int]:
    """Merge bib files from src_paths into out_path.

    Returns a tuple: (total_entries_read, duplicates_skipped, total_written)
    """
    seen_keys: Dict[str, str] = {}
    all_entries: List[str] = []
    total_read = 0
    duplicates = 0

    for path in src_paths:
        try:
            text = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            # If a source file is missing, just continue (keeps behaviour simple)
            continue
        entries = _split_entries(text)
        for entry in entries:
            total_read += 1
            key = _extract_key(entry)

            # If key present and already seen, skip
            if key and key in seen_keys:
                duplicates += 1
                continue

            # Accept this entry
            all_entries.append(entry)
            if key:
                seen_keys[key] = entry

    # Write merged file with entries separated by a blank line
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(all_entries))

    written = len(all_entries)
    return total_read, duplicates, written


def on_startup(command=None, dirty=None):
    """Compatibility wrapper used previously; merges two default files."""
    src1 = "docs/mrmfa_sources.bib"
    src2 = "docs/custom_refs.bib"
    out = "docs/all_refs.bib"
    total_read, duplicates, written = merge_bib_files([src1, src2], out)
    print(f"Bib merge: read={total_read}, duplicates_skipped={duplicates}, written={written}")
