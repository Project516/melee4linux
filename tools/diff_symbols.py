#!/usr/bin/env python3
"""
Compare two symbol map files and report matching virtual addresses with different names.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Type alias: address -> (name, fuzzy_percent)
# fuzzy_percent is always a float for JSON; for text it is None.
SymbolData = dict[int, tuple[str, float | None]]

SYMBOL_LINE = re.compile(
    r"(?P<name>[^\s=]+)\s*=\s*[^\s:]+\s*:\s*"
    r"(?P<address>0[xX][0-9a-fA-F]+)\s*;(?P<attributes>.*)"
)
TEXT_RANGE = re.compile(
    r"\.text\s+start:(?P<start>0[xX][0-9a-fA-F]+)\s+"
    r"end:(?P<end>0[xX][0-9a-fA-F]+)(?:\s+.*)?"
)
UNIT_HEADER = re.compile(r"(?P<name>[^\s:]+):(?:\s+.*)?")
LABEL_ATTRIBUTE = re.compile(r"\btype:\s*label\b")


def parse_text_symbols(content: str) -> SymbolData:
    result: SymbolData = {}
    for line_number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        parsed = SYMBOL_LINE.fullmatch(line)
        if parsed is None:
            raise ValueError(f"line {line_number}: expected a symbol assignment")
        if LABEL_ATTRIBUTE.search(parsed["attributes"]):
            continue
        addr = int(parsed["address"], 16)
        result.setdefault(addr, (parsed["name"], None))
    return result


def parse_text_units(content: str) -> SymbolData:
    """Use each unit's .text start address, ignoring section declarations and data."""
    result: SymbolData = {}
    unit_name = None
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.partition("//")[0].partition("#")[0].strip()
        if not line:
            continue
        if not raw_line[0].isspace():
            parsed = UNIT_HEADER.fullmatch(line)
            if parsed is None:
                raise ValueError(f"line {line_number}: expected a unit header")
            unit_name = parsed["name"]
            continue
        if unit_name is None:
            raise ValueError(f"line {line_number}: section has no unit header")
        if unit_name == "Sections" or line.split()[0] != ".text":
            continue
        parsed = TEXT_RANGE.fullmatch(line)
        if parsed is None:
            raise ValueError(f"line {line_number}: expected .text start and end addresses")
        addr = int(parsed["start"], 16)
        if int(parsed["end"], 16) < addr:
            raise ValueError(f"line {line_number}: .text ends before it starts")
        result.setdefault(addr, (unit_name, None))
    return result


def parse_report(content: str) -> dict:
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        raise ValueError("expected a report object with a units array")
    if any(not isinstance(unit, dict) for unit in data["units"]):
        raise ValueError("expected objects in the report's units array")
    return data


def parse_json_symbols(content: str) -> SymbolData:
    data = parse_report(content)

    result: SymbolData = {}
    for unit in data.get("units", []):
        for func in unit.get("functions", []):
            metadata = func.get("metadata", {})
            addr_str = metadata.get("virtual_address")
            if not addr_str:
                continue
            try:
                addr = int(addr_str)
            except ValueError:
                continue
            name = func.get("name")
            if not name:
                continue
            fuzzy = func.get("fuzzy_match_percent")
            if fuzzy is None:
                fuzzy = 100.0
            else:
                try:
                    fuzzy = float(fuzzy)
                except (TypeError, ValueError):
                    fuzzy = 0.0
            if addr not in result:
                result[addr] = (name, fuzzy)
    return result


def parse_json_units(content: str) -> SymbolData:
    data = parse_report(content)

    result: SymbolData = {}
    for unit in data.get("units", []):
        unit_name = unit.get("name")
        if not unit_name:
            continue
        sections = unit.get("sections", [])
        text_section = next((s for s in sections if s.get("name") == ".text"), None)
        if not text_section:
            continue
        metadata = text_section.get("metadata", {})
        addr_str = metadata.get("virtual_address")
        if not addr_str:
            continue
        try:
            addr = int(addr_str)
        except ValueError:
            continue
        fuzzy = unit.get("measures", {}).get("fuzzy_match_percent")
        if fuzzy is None:
            fuzzy = 100.0
        else:
            try:
                fuzzy = float(fuzzy)
            except (TypeError, ValueError):
                fuzzy = 0.0
        if addr not in result:
            result[addr] = (unit_name, fuzzy)
    return result


def parse_symbols_dispatch(
    content: str, *, text_mode: bool = False, unit_mode: bool = False
) -> SymbolData:
    match (text_mode, unit_mode):
        case (True, True):
            return parse_text_units(content)
        case (True, False):
            return parse_text_symbols(content)
        case (False, True):
            return parse_json_units(content)
        case (False, False):
            return parse_json_symbols(content)


def read_file_content(filename: str) -> str:
    """Read from a file or stdin if filename == '-'."""
    if filename == "-":
        return sys.stdin.read()
    try:
        return Path(filename).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        print(f"Error reading {filename}: {e}", file=sys.stderr)
        sys.exit(1)


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two symbol map files (report.json JSON format, "
            "or text format like symbols.txt / splits.txt) and report symbols "
            "that share a virtual address but have different names."
        )
    )

    parser.add_argument(
        "baseline", help="Baseline (old) symbol file (use '-' for stdin)"
    )
    parser.add_argument("current", help="Current (new) symbol file (use '-' for stdin)")

    parser.add_argument(
        "-t",
        "--text",
        action="store_true",
        help="Input is in text format (symbols.txt for functions; splits.txt when used with -u)",
    )
    parser.add_argument(
        "-u",
        "--units",
        action="store_true",
        help="Compare compilation units by .text section address (works with both text and JSON)",
    )
    parser.add_argument(
        "-p",
        "--percent",
        choices=["none", "eq", "ne", "lt", "gt"],
        default="none",
        help="Filter by fuzzy_match_percent (current vs baseline): "
        "eq (equal), ne (not equal), lt (current < baseline), gt (current > baseline). "
        "Default 'none' shows only name differences. (JSON only)",
    )

    args = parser.parse_args()

    if args.baseline == "-" and args.current == "-":
        print("Error: both input files cannot be stdin.", file=sys.stderr)
        sys.exit(1)

    if args.percent != "none" and args.text:
        print(
            "Error: --percent requires JSON input (do not use --text).", file=sys.stderr
        )
        sys.exit(1)

    baseline_content = read_file_content(args.baseline)
    current_content = read_file_content(args.current)

    try:
        baseline_data = parse_symbols_dispatch(
            baseline_content, text_mode=args.text, unit_mode=args.units
        )
    except ValueError as e:
        print(f"Error parsing {args.baseline}: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        current_data = parse_symbols_dispatch(
            current_content, text_mode=args.text, unit_mode=args.units
        )
    except ValueError as e:
        print(f"Error parsing {args.current}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.percent != "none":
        all_addrs = set(baseline_data.keys()) | set(current_data.keys())

        rows = []
        max_name_len = 0
        max_old_len = 0
        max_new_len = 0

        for addr in sorted(all_addrs):
            name1, _ = baseline_data.get(addr, ("", 0.0))
            name2, _ = current_data.get(addr, ("", 0.0))
            name = name2 if name2 else name1
            if not name:
                continue

            fuzzy_baseline = (
                baseline_data.get(addr, (None, 0.0))[1]
                if addr in baseline_data
                else 0.0
            )
            fuzzy_current = (
                current_data.get(addr, (None, 0.0))[1] if addr in current_data else 0.0
            )

            op = args.percent
            match op:
                case "eq":
                    show = fuzzy_baseline == fuzzy_current
                case "ne":
                    show = fuzzy_baseline != fuzzy_current
                case "lt":
                    show = fuzzy_current < fuzzy_baseline
                case "gt":
                    show = fuzzy_current > fuzzy_baseline
                case _:
                    assert False, f"Unexpected operator: {op}"

            if show:
                old_pct = format_percent(fuzzy_baseline)
                new_pct = format_percent(fuzzy_current)
                rows.append((name, old_pct, new_pct))
                max_name_len = max(max_name_len, len(name))
                max_old_len = max(max_old_len, len(old_pct))
                max_new_len = max(max_new_len, len(new_pct))

        for name, old_pct, new_pct in rows:
            print(
                f"{name:>{max_name_len}} | fuzzy_match  |   {old_pct:>{max_old_len}} -> {new_pct:>{max_new_len}}"
            )
    else:
        common_addrs = set(baseline_data.keys()) & set(current_data.keys())
        for addr in sorted(common_addrs):
            name1, _ = baseline_data[addr]
            name2, _ = current_data[addr]
            if name1 != name2:
                print(f"{name1}:{name2}")


if __name__ == "__main__":
    main()
