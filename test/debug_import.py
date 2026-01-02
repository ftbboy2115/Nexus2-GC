import core.strategy_engine_v2 as m
import inspect
print("Loaded from:", m.__file__)
print("First 200 chars:")
print(inspect.getsource(m)[:200])