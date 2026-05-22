"""Filesystem path resolution for the server package.

The :mod:`server.storage` package holds exactly two modules:

- :mod:`server.storage.paths` — :class:`ServerPaths`, the top-level
  directory layout (flows, taxonomies, uploads, runs).
- :mod:`server.storage.run_paths` — :class:`RunPaths`, the per-run
  directory layout inside ``data_dir/runs/<run_id>/``.

No module in this package performs I/O beyond ``mkdir``. Reading and
writing the underlying files is the responsibility of services in
:mod:`server.services`.
"""
