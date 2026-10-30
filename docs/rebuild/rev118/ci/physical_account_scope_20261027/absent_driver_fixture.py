"""Explicit simulation of the cognitive worker's absent optional PG driver."""
import importlib.abc
import sys


class AbsentOptionalPostgresDriver(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'psycopg' or fullname.startswith('psycopg.'):
            raise ModuleNotFoundError("No module named 'psycopg' (controlled absent-driver fixture)", name=fullname)
        return None


sys.meta_path.insert(0, AbsentOptionalPostgresDriver())
