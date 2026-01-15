"""
Migration script to replace datetime.now()/datetime.utcnow() with time_utils.

Run with: python scripts/migrate_to_time_utils.py

This will:
1. Find all Python files with datetime.now() or datetime.utcnow()
2. Add the appropriate import from nexus2.utils.time_utils at TOP OF FILE ONLY
3. Replace the calls

DRY RUN by default - pass --apply to make changes.
"""

import os
import re
import sys
from pathlib import Path


# Files/dirs to skip
SKIP_PATTERNS = [
    'time_utils.py',
    '__pycache__',
    'node_modules',
    '.git',
    'test_',
    '_test.py',
    'conftest.py',
    'venv',
    '.venv',
    'migrate_to_time_utils.py',
]


def should_skip(filepath: str) -> bool:
    """Check if file should be skipped."""
    return any(skip in filepath for skip in SKIP_PATTERNS)


def find_top_level_import_position(lines: list) -> int:
    """
    Find the position to insert our import at the top of the file.
    
    Returns the line index AFTER the last top-level import.
    Only considers lines with NO leading whitespace as top-level.
    """
    last_import_idx = -1
    in_multiline = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            continue
        
        # Check if line has leading whitespace (indented = not top-level)
        if line[0:1].isspace():
            continue
        
        # Track multiline imports (with parentheses)
        if in_multiline:
            if ')' in line:
                in_multiline = False
                last_import_idx = i
            continue
        
        # Check for import statements at module level
        if stripped.startswith('import ') or stripped.startswith('from '):
            if '(' in stripped and ')' not in stripped:
                in_multiline = True
            last_import_idx = i
        elif last_import_idx >= 0:
            # Hit non-import code, stop here
            break
    
    return last_import_idx + 1 if last_import_idx >= 0 else 0


def migrate_file(filepath: Path, dry_run: bool = True) -> dict:
    """
    Migrate a single file to use time_utils.
    
    Returns dict with counts of changes made.
    """
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        return {"error": str(e)}
    
    original = content
    stats = {"utcnow_replaced": 0, "now_replaced": 0, "import_added": False}
    
    # Check what needs to be done
    has_utcnow = 'datetime.utcnow()' in content
    has_now = bool(re.search(r'datetime\.now\(\s*\)', content))
    
    if not has_utcnow and not has_now:
        return {"skipped": "no violations"}
    
    # Determine which imports to add
    needs_now_utc = has_utcnow
    needs_now_et = has_now
    
    # Build import line
    imports = []
    if needs_now_utc:
        imports.append("now_utc")
    if needs_now_et:
        imports.append("now_et")
    
    import_line = f"from nexus2.utils.time_utils import {', '.join(imports)}"
    
    # Check if import already exists
    if 'from nexus2.utils.time_utils import' in content:
        # Update existing import if needed
        old_import_match = re.search(r'^from nexus2\.utils\.time_utils import [^\n]+', content, re.MULTILINE)
        if old_import_match:
            existing = old_import_match.group()
            new_existing = existing
            for imp in imports:
                if imp not in existing:
                    new_existing = new_existing.rstrip() + f", {imp}"
            if new_existing != existing:
                content = content.replace(existing, new_existing)
    else:
        # Add import at top of file ONLY (after existing imports)
        lines = content.split('\n')
        insert_pos = find_top_level_import_position(lines)
        
        # Insert the import line
        lines.insert(insert_pos, import_line)
        content = '\n'.join(lines)
        stats["import_added"] = True
    
    # Replace datetime.utcnow() with now_utc()
    if has_utcnow:
        count = content.count('datetime.utcnow()')
        content = content.replace('datetime.utcnow()', 'now_utc()')
        stats["utcnow_replaced"] = count
    
    # Replace datetime.now() (with no args) with now_et()
    if has_now:
        new_content, count = re.subn(r'datetime\.now\(\s*\)', 'now_et()', content)
        content = new_content
        stats["now_replaced"] = count
    
    # Skip if no actual changes
    if content == original:
        return {"skipped": "no changes needed"}
    
    # Write or show diff
    if dry_run:
        print(f"\n{'='*60}")
        print(f"FILE: {filepath}")
        print(f"  - UTC replacements: {stats['utcnow_replaced']}")
        print(f"  - ET replacements: {stats['now_replaced']}")
        print(f"  - Import added: {stats['import_added']}")
    else:
        filepath.write_text(content, encoding='utf-8')
        print(f"UPDATED: {filepath.name} ({stats['utcnow_replaced']} utcnow, {stats['now_replaced']} now)")
    
    return stats


def main():
    dry_run = '--apply' not in sys.argv
    
    if dry_run:
        print("DRY RUN - no files will be modified. Pass --apply to make changes.\n")
    else:
        print("APPLYING CHANGES - files will be modified.\n")
    
    # Find nexus2 directory
    script_dir = Path(__file__).resolve().parent
    nexus2_path = script_dir.parent / 'nexus2'
    
    if not nexus2_path.exists():
        print(f"ERROR: nexus2 directory not found at {nexus2_path}")
        return 1
    
    total_utcnow = 0
    total_now = 0
    files_modified = 0
    
    for py_file in nexus2_path.rglob('*.py'):
        if should_skip(str(py_file)):
            continue
        
        stats = migrate_file(py_file, dry_run=dry_run)
        
        if 'error' in stats:
            print(f"ERROR: {py_file.name} - {stats['error']}")
        elif 'skipped' not in stats:
            total_utcnow += stats.get('utcnow_replaced', 0)
            total_now += stats.get('now_replaced', 0)
            files_modified += 1
    
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Files {'to be ' if dry_run else ''}modified: {files_modified}")
    print(f"  datetime.utcnow() replacements: {total_utcnow}")
    print(f"  datetime.now() replacements: {total_now}")
    
    if dry_run:
        print("\nRun with --apply to make these changes.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
