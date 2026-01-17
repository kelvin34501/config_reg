import re

from typing import Optional


match_special = re.compile(r"^\?\((.*)\)$")


def extract_special(s: str) -> Optional[str]:
    """Extract content from special pattern ?(content).
    
    Args:
        s: String to check for special pattern.
        
    Returns:
        The content inside ?() if matched, None otherwise.
    """
    match_special_res = match_special.fullmatch(s)
    if match_special_res:
        return match_special_res.group(1)
    else:
        return None


match_special_part = re.compile(r"\?\((.*?)\)")


def extract_special_part(s: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Extract all special patterns ?(content) from a string.
    
    Args:
        s: String to search for special patterns.
        
    Returns:
        A tuple of (cmd_list, span_list) where cmd_list contains the extracted
        content and span_list contains the (start, end) positions.
    """
    cmd_list: list[str] = []
    span_list: list[tuple[int, int]] = []
    for match in match_special_part.finditer(s):
        cmd = match.group(1)
        span = match.span()
        cmd_list.append(cmd)
        span_list.append(span)
    return cmd_list, span_list


def replace_from_span(s: str, span_list: list[tuple[int, int]], replacement_list: list[str]) -> str:
    """Replace spans in a string with replacements.
    
    Args:
        s: The original string.
        span_list: List of (start, end) index tuples for each span in the original string.
        replacement_list: List of replacement strings, one for each span.
        
    Returns:
        A new string with all spans replaced.
        
    Raises:
        ValueError: If span_list and replacement_list have different lengths.
    """
    if len(span_list) != len(replacement_list):
        raise ValueError(f"span_list and replacement_list must have same length, got {len(span_list)} and {len(replacement_list)}")
    # sort by start index
    span_list = sorted(span_list, key=lambda x: x[0])
    # replace from end to start
    for i in range(len(span_list) - 1, -1, -1):
        start, end = span_list[i]
        s = s[:start] + replacement_list[i] + s[end:]
    return s


match_file = re.compile(r"^file:(.*)$")


def extract_file(s: str) -> Optional[str]:
    """Extract filename from file: prefix pattern.
    
    Args:
        s: String to check for file: pattern.
        
    Returns:
        The filename if matched, None otherwise.
    """
    match_file_res = match_file.fullmatch(s)
    if match_file_res:
        return match_file_res.group(1)
    else:
        return None
