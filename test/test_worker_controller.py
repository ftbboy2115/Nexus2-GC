"""
⭐ What this test suite gives you
1. Confidence in WorkerController stability
You now know:
- Workers run
- Workers run in parallel
- Exceptions don’t break the controller
- Failures are tracked
- The controller resets cleanly
2. Protection against regressions
If you ever modify WorkerController (e.g., add timeouts, add logging, add concurrency limits), this suite will catch breakage immediately.
3. Zero dependencies
No external libraries, no scanners, no Strategy Engine — just pure controller logic.

"""


import unittest
import time
from core.worker_controller import WorkerController


class TestWorkerController(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. Basic worker execution
    # ---------------------------------------------------------
    def test_basic_worker_execution(self):
        controller = WorkerController()

        results = []

        def worker_fn():
            results.append("done")

        controller.add_worker("test_worker", worker_fn)
        controller.run_all()

        self.assertEqual(results, ["done"])

    # ---------------------------------------------------------
    # 2. Multiple workers run in parallel
    # ---------------------------------------------------------
    def test_parallel_workers(self):
        controller = WorkerController()

        order = []

        def worker_a():
            time.sleep(0.1)
            order.append("A")

        def worker_b():
            time.sleep(0.1)
            order.append("B")

        controller.add_worker("A", worker_a)
        controller.add_worker("B", worker_b)
        controller.run_all()

        # Both should complete, order doesn't matter
        self.assertCountEqual(order, ["A", "B"])

    # ---------------------------------------------------------
    # 3. Worker exception should not crash controller
    # ---------------------------------------------------------
    def test_worker_exception_handling(self):
        controller = WorkerController()

        results = []

        def good_worker():
            results.append("good")

        def bad_worker():
            raise ValueError("boom")

        controller.add_worker("good", good_worker)
        controller.add_worker("bad", bad_worker)

        controller.run_all()

        # Good worker should still run
        self.assertIn("good", results)

        # Controller should record the failure
        self.assertIn("bad", controller.failures)

    # ---------------------------------------------------------
    # 4. Workers should not block each other
    # ---------------------------------------------------------
    def test_non_blocking_workers(self):
        controller = WorkerController()

        results = []

        def slow_worker():
            time.sleep(0.2)
            results.append("slow")

        def fast_worker():
            results.append("fast")

        controller.add_worker("slow", slow_worker)
        controller.add_worker("fast", fast_worker)

        start = time.time()
        controller.run_all()
        end = time.time()

        # Both should complete
        self.assertCountEqual(results, ["fast", "slow"])

        # Total time should be close to slow worker only (parallel)
        self.assertLess(end - start, 0.25)

    # ---------------------------------------------------------
    # 5. Controller should reset between runs
    # ---------------------------------------------------------
    def test_reset_between_runs(self):
        controller = WorkerController()

        results = []

        def worker():
            results.append("run")

        controller.add_worker("w", worker)
        controller.run_all()

        # Reset and run again
        controller.reset()
        controller.add_worker("w2", worker)
        controller.run_all()

        self.assertEqual(results, ["run", "run"])


if __name__ == "__main__":
    unittest.main()