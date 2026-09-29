"""
tests/test_settings_i18n_vocab.py — REQ-SETTINGS-IA AC-4 五词表 lint + AC-1 唯一写入口静态检查

裁决-4 定五词：离线 / 联网 / 体验配额 / 自带 Key / 本机端点。
用户可见文案（设置域 i18n 源文件）禁止出现：托管 / 体验代理 / 自持 Key / 自接端点 / 平台代理 / 降级。
（proxy / cloud / direct / engine_mode_* 等工程值仅允许出现在专家注释层代码，不在 i18n 用户词内。）

同时静态检查 AC-1：
  - AccessModeCards.vue 不存在内联自动保存路径（saveServices / saveVoiceprint）
  - SettingsView.vue 引擎页不存在可写 mode dropdown（engine_mode_select / onSaveEngineMode）

运行：pytest tests/test_settings_i18n_vocab.py -v
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "frontend" / "src" / "i18n" / "locales"

# 本单治理的设置域用户可见文案文件（zh-CN；英文侧无禁词表，按对应语义另行点验）
SETTINGS_DOMAIN_FILES = [
    LOCALES / "zh-CN" / "settings.json",
    LOCALES / "zh-CN" / "common.json",
    LOCALES / "zh-CN" / "topbar.json",
    LOCALES / "zh-CN" / "ai-panel.json",
]

BANNED_TERMS = ["托管", "体验代理", "自持 Key", "自接端点", "平台代理", "降级", "兜底", "fallback"]

FIVE_TERMS = ["离线", "联网", "体验配额", "自带 Key", "本机端点"]


def _iter_strings(node):
    """遍历 i18n JSON 的可渲染文案值（键名是工程标识不计入用户可见文案）。"""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_strings(v)


@pytest.mark.parametrize("path", SETTINGS_DOMAIN_FILES, ids=lambda p: p.name)
def test_no_banned_vocabulary_in_user_visible_text(path):
    assert path.exists(), f"i18n 源文件缺失: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    offenders = []
    for text in _iter_strings(data):
        for term in BANNED_TERMS:
            if term in text:
                offenders.append((term, text[:60]))
    assert not offenders, f"{path.name} 用户可见文案含禁词: {offenders}"


def test_five_terms_all_present_in_settings_zh():
    """五词表正向检查：裁决-4 的五词均应出现在设置域中文文案。"""
    data = json.loads((LOCALES / "zh-CN" / "settings.json").read_text(encoding="utf-8"))
    text = json.dumps(data, ensure_ascii=False)
    missing = [term for term in FIVE_TERMS if term not in text]
    assert not missing, f"五词表缺失: {missing}"


def test_voiceprint_keys_removed_from_settings_locale():
    """AC-3（UI 侧）：声纹 provider/云配置键不存在于 i18n schema。"""
    data = json.loads((LOCALES / "zh-CN" / "settings.json").read_text(encoding="utf-8"))
    assert "voiceprint_provider" not in data
    assert "voiceprint_cloud_base_url" not in data
    assert "voiceprint_cloud_api_key" not in data
    # 幽灵枚举随删除
    assert "engine_mode_cloud" not in data


def test_access_mode_card_has_no_inline_autosave():
    """AC-1：AccessModeCards 孤儿组件已随逐能力化删除，内联自动保存路径随之消失。"""
    path = ROOT / "frontend" / "src" / "components" / "settings" / "AccessModeCards.vue"
    assert not path.exists(), "AccessModeCards 孤儿组件应已删除（逐能力真相源已取代它）"


def test_settings_view_engine_mode_dropdown_is_readonly():
    """AC-1：引擎页 mode 可写 dropdown 已改只读徽章。

    REQ-COMPUTE-CENTER 后引擎资产面从 SettingsView 迁出到 LocalEnginePanel；
    只读徽章（engine_mode_readonly）随迁到该组件。可写 dropdown 在两个文件中均不得出现。
    """
    view = (ROOT / "frontend" / "src" / "views" / "SettingsView.vue").read_text(encoding="utf-8")
    panel = (ROOT / "frontend" / "src" / "components" / "settings" / "LocalEnginePanel.vue").read_text(encoding="utf-8")
    assert "onSaveEngineMode" not in view
    assert not re.search(r"v-model=[\"']engineModeDraft", view)
    assert not re.search(r"v-model=[\"']engineModeDraft", panel)
    assert "engine_mode_readonly" in panel  # 只读徽章文案已接线（引擎页迁至 LocalEnginePanel）


def test_access_mode_write_entry_single():
    """AC-1：决策卡唯一写入口 = 切换事务端点（api/access 不再携带旧 mock 影子态）。"""
    src = (ROOT / "frontend" / "src" / "api" / "access.ts").read_text(encoding="utf-8")
    assert "/api/settings/access-mode" in src
    assert "oms_access_mode" not in src  # mock 影子态已废除
