"""Keep one graph thread in Postgres.

ponytail: one connection per database URL for the process. A pool is
unnecessary until more than one API process writes checkpoints.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver

from northstar.graph import _compile

_OPEN: dict[str, tuple[object, object]] = {}


def graph_for(conninfo: str):
    cached = _OPEN.get(conninfo)
    if cached is not None:
        return cached[1]
    context = PostgresSaver.from_conn_string(conninfo)
    saver = context.__enter__()
    saver.setup()
    compiled = _compile(saver)
    _OPEN[conninfo] = (context, compiled)
    return compiled
