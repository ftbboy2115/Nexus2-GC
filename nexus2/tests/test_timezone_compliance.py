"""
Test for timezone utility usage compliance.

This test automatically catches direct datetime.now() and datetime.utcnow()
calls that bypass the centralized time_utils.py, preventing future timezone bugs.
"""

import os
import re
from pathlib import Path


def test_no_direct_datetime_now():
    """
    Ensure no code uses datetime.now() or datetime.utcnow() directly.
    
    All code should use nexus2.utils.time_utils instead.
    Allowed exceptions:
    - time_utils.py itself
    - test files
    - __pycache__
    """
    violations = []
    
    # Patterns that indicate timezone violations
    patterns = [
        r'datetime\.now\(\s*\)',  # datetime.now() with no args
        r'datetime\.utcnow\(\)',
        # default_factory patterns (function references without parentheses)
        r'default_factory\s*=\s*datetime\.now\b(?!\()',  # default_factory=datetime.now
        r'default_factory\s*=\s*datetime\.utcnow\b(?!\()',  # default_factory=datetime.utcnow
    ]
    
    # Files/dirs to skip
    skip_patterns = [
        'time_utils.py',  # The utility itself
        '__pycache__',
        'node_modules',
        '.git',
        'test_',  # Test files can use datetime.now() for setup
        '_test.py',
        'venv',
        '.venv',
        'scripts',  # Utility scripts (not trading-critical) - no slash for cross-platform
    ]
    
    nexus2_path = Path(__file__).parent.parent.parent / 'nexus2'
    
    for py_file in nexus2_path.rglob('*.py'):
        # Skip excluded files
        file_str = str(py_file)
        if any(skip in file_str for skip in skip_patterns):
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            for i, line in enumerate(content.splitlines(), 1):
                # Skip comments and strings (simple heuristic)
                if line.strip().startswith('#'):
                    continue
                
                # Strip inline comments to avoid false positives
                # e.g. "timestamp=now_utc(),  # Use now_utc() not datetime.now()"
                code_part = line.split('#')[0] if '#' in line else line
                    
                for pattern in patterns:
                    if re.search(pattern, code_part):
                        violations.append(f"{py_file.name}:{i}: {line.strip()}")
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")
    
    if violations:
        msg = (
            "Timezone violation: Use nexus2.utils.time_utils instead of direct datetime calls.\n"
            "Violations found:\n" + "\n".join(violations)
        )
        assert False, msg
