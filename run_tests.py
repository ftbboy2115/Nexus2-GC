"""
Unified Test Runner for Nexus
-----------------------------

Runs all tests inside the /test/ directory using Python's built-in unittest
discovery mechanism.

Usage:
    python run_tests.py
"""

import os
import sys
import unittest


def main():
    # Ensure project root is on sys.path
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    # Test directory
    test_dir = os.path.join(root, "test")

    if not os.path.exists(test_dir):
        print("ERROR: /test/ directory not found.")
        sys.exit(1)

    print("Discovering tests in:", test_dir)

    # Discover all tests
    suite = unittest.defaultTestLoader.discover(test_dir)

    print("Running tests...\n")

    runner = unittest.TextTestRunner(
        verbosity=2,
        failfast=False,
        buffer=False
    )
    result = runner.run(suite)

    print("\nTest Summary")
    print("------------")
    print(f"Ran: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\nAll tests passed successfully.")
        sys.exit(0)
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()