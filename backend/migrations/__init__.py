"""Alembic migration scripts, shipped as a package so the artefact carries them.

This file holds no code and is never imported for its contents. It exists so
that ``migrations`` is a real package: importable by name, and therefore
installed into the environment by ``uv sync``/``pip install`` rather than left
behind in the source tree.

Two callers depend on that :

* ``app/core/readiness.py`` reads the head revision through
  ``importlib.resources.files("migrations")``. Before this file existed it
  computed the directory from its own location, which is correct in the source
  tree and wrong in ``backend/Dockerfile``'s wheel install.
* ``alembic`` itself, which loads ``env.py`` and ``versions/*.py`` by path and
  neither needs nor notices this file.

Do not add ``__init__.py`` to ``versions/``. Alembic treats every ``.py`` file
in that directory as a revision script and would fail to parse one.
"""
