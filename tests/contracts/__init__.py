# GAP-F-022 — makes `tests/contracts` a package so pytest's default (prepend) import mode
# gives its modules the dotted name `contracts.<module>` rather than a bare file stem.
# See `backend/tests/__init__.py` for the collision this resolves.
