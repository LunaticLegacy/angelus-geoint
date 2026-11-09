"""文档防漂移测试：三份插件文档只能描述代码里真实存在的实现。

断言依据全部来自实现本身，而不是文档自己的说法：

- ``angelus/modules/plugin_module/manifest.py`` 的 ``load_manifest()`` 是
  ``manifest.json`` 的唯一判据，所以文档里的每个 ````json`` 块都必须是完整、
  可加载的 manifest——片段式样例一旦复制就会报 ``ManifestError``。
- 文档里的每个 ````python`` 块都必须能独立 ``compile()``（导入写在第 0 列），
  否则读者照抄即报错。
- ``docs/plugin-api.md`` 必须覆盖 ``plugin_module.__all__``、``PluginRuntime``
  的公开方法，以及 ``angelus/api/plugins.py`` 声明的每一条路由。
- 已删除的旧版插件 API 不得以代码示例的形式回流。
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

import angelus.modules.plugin_module as plugin_module
from angelus.modules.plugin_module.manifest import load_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "plugin-api": REPO_ROOT / "docs" / "plugin-api.md",
    "plugin-guide": REPO_ROOT / "docs" / "plugin-guide.md",
    "plugin-panel-manifest": REPO_ROOT / "docs" / "plugin-panel-manifest.md",
}
PLUGIN_ROUTES_SOURCE = REPO_ROOT / "angelus" / "api" / "plugins.py"

_FENCE = re.compile(r"^```(?P<info>[A-Za-z0-9_+-]*)$")
_ROUTE = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*\"(?P<path>[^\"]+)\"")

# 旧版插件 API 的痕迹：这些名称在实现里已经不存在，出现在示例里就是误导。
LEGACY_CODE_FRAGMENTS = (
    "from angelus.plugins import",
    "angelus.plugins.base",
    "angelus.plugin_manifest",
    '"commands"',
    "register_hook(",
    "register_route(",
    "register_connector(",
    "bridge_tools",
    "bridge_hooks",
    "bridge_routes",
    "bridge_connectors",
    "angelus plugin install",
    "angelus plugin list",
    "ANGELUS_PLUGIN_AUTORELOAD",
    "plugins.json",
)

# “会被拒绝的写法”一节用 ````text`` 块故意写出旧字段作为反例；
# ``frontend.commands`` 是唯一需要在那里出现的片段。
LEGACY_TEXT_BLOCK_ALLOWED = ('"commands"',)


def _doc(name: str) -> str:
    """返回文档全文（UTF-8）。"""
    return DOCS[name].read_text(encoding="utf-8")


def _code_blocks(name: str, language: str) -> list[str]:
    """按语言信息串提取围栏代码块文本。

    Args:
        name: ``DOCS`` 里的文档键。
        language: 围栏信息串，例如 ``"json"`` / ``"python"``；空串取无标注块。

    Returns:
        每个匹配代码块的内容（不含围栏行）。

    Raises:
        AssertionError: 文档里有未闭合的围栏。
    """
    blocks: list[str] = []
    current: list[str] | None = None
    info: str | None = None
    for line in _doc(name).splitlines():
        match = _FENCE.match(line.rstrip())
        if current is None:
            if match is not None:
                info = match.group("info")
                current = []
            continue
        if match is not None:
            if info == language:
                blocks.append("\n".join(current))
            current, info = None, None
            continue
        current.append(line)
    assert current is None, f"{DOCS[name]} 存在未闭合的 ```{info} 围栏"
    return blocks


@pytest.mark.parametrize("name", sorted(DOCS))
def test_every_json_block_is_a_loadable_manifest(name: str, tmp_path: Path) -> None:
    """每个 ```json 块都必须能被 ``load_manifest()`` 完整加载。"""
    blocks = _code_blocks(name, "json")
    assert blocks, f"{DOCS[name]} 至少应包含一个 manifest 示例"

    for index, block in enumerate(blocks, start=1):
        payload = json.loads(block)
        package = tmp_path / f"{name}-{index}"
        package.mkdir()
        (package / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

        manifest = load_manifest(package)

        assert manifest.name == payload["name"]
        assert manifest.version == payload["version"]
        assert manifest.api_version == "1"


@pytest.mark.parametrize("name", sorted(DOCS))
def test_every_python_block_compiles_standalone(name: str) -> None:
    """每个 ```python 块都必须能以第 0 列独立编译。"""
    blocks = _code_blocks(name, "python")
    assert blocks, f"{DOCS[name]} 至少应包含一个可运行示例"

    for index, block in enumerate(blocks, start=1):
        compile(block, f"{DOCS[name]}#python-{index}", "exec")


def test_api_doc_covers_every_public_export() -> None:
    """``plugin_module.__all__`` 里的每个名字都要在 API 文档出现。"""
    text = _doc("plugin-api")

    missing = [name for name in plugin_module.__all__ if name not in text]

    assert not missing, f"docs/plugin-api.md 未覆盖公开导出: {missing}"


def test_api_doc_covers_every_runtime_registration_method() -> None:
    """``PluginRuntime`` 的公开方法（注册/读取入口）都要在 API 文档出现。"""
    text = _doc("plugin-api")
    methods = [
        member
        for member, value in inspect.getmembers(plugin_module.PluginRuntime, inspect.isfunction)
        if not member.startswith("_")
    ]

    assert set(methods) == {
        "register_tool_provider",
        "register_context_provider",
        "register_ui_action",
        "setting",
    }
    missing = [method for method in methods if method not in text]

    assert not missing, f"docs/plugin-api.md 缺少 PluginRuntime 方法: {missing}"


def test_api_doc_lists_every_plugin_route() -> None:
    """``angelus/api/plugins.py`` 声明的每条路由都要出现在 API 文档。"""
    declared = [
        match.group("path").replace(":path", "")
        for match in _ROUTE.finditer(PLUGIN_ROUTES_SOURCE.read_text(encoding="utf-8"))
    ]
    assert declared, "未从 angelus/api/plugins.py 解析到任何路由"

    text = _doc("plugin-api")
    missing = [path for path in declared if path not in text]

    assert not missing, f"docs/plugin-api.md 未列出路由: {missing}"


def test_panel_doc_states_the_documented_invoke_route() -> None:
    """面板文档必须给出浏览器唯一可用的调用端点。"""
    text = _doc("plugin-panel-manifest")

    assert "POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke" in text
    assert "active plugin panel not found" in text


def test_panel_doc_marks_both_host_surfaces() -> None:
    """两套前端宿主的差异必须写明，避免把工作台桥当成通用能力。"""
    text = _doc("plugin-panel-manifest")

    assert "frontend/static/plugins.js" in text
    assert "frontend/geoint-src/components/plugin-panel.js" in text
    assert "mountPluginPanel" in text
    assert ".inspector-panels" in text


@pytest.mark.parametrize("name", sorted(DOCS))
def test_code_blocks_do_not_reintroduce_legacy_plugin_api(name: str) -> None:
    """示例代码里不得出现实现中不存在的旧版插件 API。

    ````text`` 块在“会被拒绝的写法”一节里故意写出旧字段作为反例，因此
    ``frontend.commands`` 片段只在示例代码块（json / python）里被禁止。
    """
    example_code = "\n".join(
        block
        for language in ("json", "python")
        for block in _code_blocks(name, language)
    )
    prose_code = "\n".join(_code_blocks(name, "text"))

    found = [fragment for fragment in LEGACY_CODE_FRAGMENTS if fragment in example_code]
    found += [
        fragment
        for fragment in LEGACY_CODE_FRAGMENTS
        if fragment not in LEGACY_TEXT_BLOCK_ALLOWED and fragment in prose_code
    ]

    assert not found, f"{DOCS[name]} 的代码块里仍出现旧版 API: {sorted(set(found))}"
