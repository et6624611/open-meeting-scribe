"""core/agent_memory — 智能体长期记忆（写入 / 检索 / 注入）。

入口约定：
  - 写入只经 ``store.upsert`` / ``store.close`` / ``store.delete`` 等显式函数；
  - 读取经 ``retrieve.search`` 与 ``retrieve.select_core``；
  - 注入经 ``inject.build_blocks`` 与 ``inject.build_core_prompt``。
"""

from core.agent_memory import inject, retrieve, schema, store  # noqa: F401
