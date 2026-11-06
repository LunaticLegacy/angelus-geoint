"""Lifecycle coverage for typed plugins, settings, and CSS theme packs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from llmfetcher import Tool, ToolSchema
from llmfetcher.tool_handler import ToolCallValidationError

from angelus.modules.plugin_module import PluginManager, PluginUiActionResult
from angelus.modules.tool_module import (
    ToolCategory,
    ToolDefinition,
    ToolPolicy,
    ToolProviderRegistration,
    ToolRegistry,
)

_TOOL_PLUGIN_SOURCE = (
    "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
    "class Provider:\n"
    "    def materialize(self, session_id, policy, role): return []\n"
    "class Plugin:\n"
    "    def setup(self, runtime):\n"
    "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('ping', 'utility', 'Ping', 'Ping helper', frozenset({'coordinator'})),)))\n"
    "    def teardown(self): pass\n"
    "angelus_plugin = Plugin()\n"
)

_REAL_TOOL_PLUGIN_SOURCE = (
    "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
    "from llmfetcher import Tool, ToolParameter, ToolSchema\n"
    "class Provider:\n"
    "    def materialize(self, session_id, policy, role):\n"
    "        return [\n"
    "            Tool('plugin.real-tools.ping', 'Ping', ToolSchema(properties=[ToolParameter('value')]), lambda value='': f'ping:{value}:{session_id}:{role}'),\n"
    "            Tool('plugin.real-tools.manager', 'Manager', ToolSchema(), lambda: 'manager'),\n"
    "        ]\n"
    "class Plugin:\n"
    "    def setup(self, runtime):\n"
    "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (\n"
    "            PluginToolDefinition('ping', 'utility', 'Ping', 'Ping helper', frozenset({'coordinator'})),\n"
    "            PluginToolDefinition('manager', 'utility', 'Manager', 'Manager helper', frozenset({'coordinator', 'worker'})),\n"
    "        )))\n"
    "    def teardown(self): pass\n"
    "angelus_plugin = Plugin()\n"
)
_ASYNC_TOOL_PLUGIN_SOURCE = (
    "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
    "from llmfetcher import Tool, ToolParameter, ToolSchema\n"
    "def _awaiting(session_id, role):\n"
    "    async def handler(value=''):\n"
    "        return f'async-ping:{value}:{session_id}:{role}'\n"
    "    return handler\n"
    "def _blocking(session_id, role):\n"
    "    def handler(value=''):\n"
    "        return f'sync-ping:{value}:{session_id}:{role}'\n"
    "    return handler\n"
    "class Provider:\n"
    "    def materialize(self, session_id, policy, role):\n"
    "        return [\n"
    "            Tool('plugin.live-tools.await_ping', 'Await ping', ToolSchema(properties=[ToolParameter('value')]), _awaiting(session_id, role)),\n"
    "            Tool('plugin.live-tools.sync_ping', 'Sync ping', ToolSchema(properties=[ToolParameter('value')]), _blocking(session_id, role)),\n"
    "        ]\n"
    "class Plugin:\n"
    "    def setup(self, runtime):\n"
    "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (\n"
    "            PluginToolDefinition('await_ping', 'utility', 'Await ping', 'Awaitable helper', frozenset({'coordinator'})),\n"
    "            PluginToolDefinition('sync_ping', 'utility', 'Sync ping', 'Blocking helper', frozenset({'coordinator'})),\n"
    "        )))\n"
    "    def teardown(self): pass\n"
    "angelus_plugin = Plugin()\n"
)


_BAD_NAMESPACE_PLUGIN_SOURCE = (
    "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
    "from llmfetcher import Tool, ToolSchema\n"
    "class Provider:\n"
    "    def materialize(self, session_id, policy, role):\n"
    "        return [Tool('outside.ping', 'Escaped', ToolSchema(), lambda: 'escaped')]\n"
    "class Plugin:\n"
    "    def setup(self, runtime):\n"
    "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('escaped', 'utility', 'Escaped', 'Namespacing probe', frozenset({'coordinator'})),)))\n"
    "    def teardown(self): pass\n"
    "angelus_plugin = Plugin()\n"
)


class PluginManagerTests(unittest.TestCase):
    """Assert discovery never executes code and loaded packages stay bounded."""

    def test_theme_pack_registers_settings_and_serves_only_whitelisted_css(self) -> None:
        """A theme pack exposes multiple skins without executable entry code.

        Returns:
            ``None`` after validating lifecycle, settings, and static bounds.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "aurora-pack"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "aurora-pack", "display_name": "Aurora", "version": "1.0.0", "api_version": "1", "kind": "theme_pack",
                "frontend": {
                    "assets": ["dark.css", "light.css"], "settings": True,
                    "themes": [
                        {"id": "dark", "title": "Aurora Dark", "asset": "dark.css", "mode": "dark"},
                        {"id": "light", "title": "Aurora Light", "asset": "light.css", "mode": "light"},
                    ],
                },
                "settings_schema": [{"key": "contrast", "type": "integer", "title": "Contrast", "default": 2, "minimum": 1, "maximum": 3}],
            })
            (package / "dark.css").write_text(":root { --accent: aqua; }", encoding="utf-8")
            (package / "light.css").write_text(":root { --accent: blue; }", encoding="utf-8")
            manager = _manager(root, ToolRegistry())

            self.assertEqual("discovered", manager.statuses()[0]["state"])
            registered = manager.register("aurora-pack")
            self.assertFalse(registered["enabled"])
            active = manager.load("aurora-pack", grant_permissions=False)
            self.assertEqual("active", active["state"])
            self.assertEqual(2, len(active["themes"]))
            self.assertTrue(manager.static_asset("aurora-pack", "dark.css").is_file())
            self.assertIsNone(manager.static_asset("aurora-pack", "missing.css"))
            self.assertEqual(2, manager.settings("aurora-pack")["settings"]["contrast"])
            self.assertEqual(3, manager.replace_settings("aurora-pack", {"contrast": 3})["settings"]["contrast"])
            with self.assertRaises(ValueError):
                manager.replace_settings("aurora-pack", {"contrast": 4})

    def test_tool_plugin_registers_only_namespaced_provider_after_explicit_load(self) -> None:
        """A tool plugin executes only at load and publishes host namespaced tools.

        Returns:
            ``None`` after asserting the registry receives its contribution.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "echo-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "echo-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Echo', 'Echo helpers'),), (PluginToolDefinition('echo', 'utility', 'Echo', 'Echo safely', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("echo-tools")
            self.assertEqual((), registry.definitions())
            manager.load("echo-tools", grant_permissions=False)
            self.assertEqual(["plugin.echo-tools.echo"], [item.id for item in registry.definitions()])
            manager.unload("echo-tools")
            self.assertEqual((), registry.definitions())

    def test_loaded_plugin_tools_respect_policy_grants_and_receiving_role(self) -> None:
        """A real plugin provider publishes host Tools gated by policy and role.

        Returns:
            ``None`` after asserting denied grants publish nothing, a coordinator
            receives its coordinator-only Tool, and a worker receives only the
            Tool whose declared roles include ``worker``.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "real-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "real-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_REAL_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("real-tools")
            manager.load("real-tools", grant_permissions=False)
            session = _session()

            self.assertEqual([], registry.materialize(session, ToolPolicy(frozenset(), frozenset()), "coordinator"))
            granted = ToolPolicy(
                frozenset({"plugin.real-tools.utility"}),
                frozenset({"plugin.real-tools.ping", "plugin.real-tools.manager"}),
            )
            self.assertEqual(
                ["plugin.real-tools.ping", "plugin.real-tools.manager"],
                [item.name for item in registry.materialize(session, granted, "coordinator")],
            )
            self.assertEqual(
                ["plugin.real-tools.manager"],
                [item.name for item in registry.materialize(session, granted, "worker")],
            )
            self.assertEqual([], registry.materialize(session, granted, "unprivileged"))
            ping = registry.materialize(session, granted, "coordinator")[0]
            self.assertEqual("ping:value:session-one:coordinator", ping.handler(value="value"))

    def test_plugin_provider_rejects_tools_outside_its_namespace(self) -> None:
        """A plugin provider cannot smuggle a Tool past the host namespace.

        Returns:
            ``None`` after asserting materialization fails loudly instead of
            publishing ``outside.ping``.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "bad-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "bad-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_BAD_NAMESPACE_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("bad-tools")
            manager.load("bad-tools", grant_permissions=False)
            policy = ToolPolicy(frozenset({"plugin.bad-tools.utility"}), frozenset({"plugin.bad-tools.escaped"}))

            with self.assertRaises(RuntimeError):
                registry.materialize(_session(), policy, "coordinator")

    def test_definition_without_declared_roles_stays_unrestricted(self) -> None:
        """Omitting ``roles`` keeps a provider Tool available to every role.

        Returns:
            ``None`` after asserting the default empty role set does not filter
            Workers out of a provider that never declared role gating.
        """
        registry = ToolRegistry()
        registry.register(ToolProviderRegistration(
            "inline",
            _InlineProvider(),
            (ToolCategory("inline", "Inline", "Inline tools"),),
            (ToolDefinition("shared_tool", "inline", "Shared", "Shared tool", "inline"),),
        ))
        policy = ToolPolicy(frozenset({"inline"}), frozenset({"shared_tool"}))

        self.assertEqual(["shared_tool"], [item.name for item in registry.materialize(_session(), policy, "worker")])

    def test_unload_revokes_materialized_tools_and_bumps_registry_revision(self) -> None:
        """Unloading stops future calls on Tools an Agent already received.

        Returns:
            ``None`` after asserting definitions disappear, the registry revision
            forces a rebuild, previously materialized handlers reject calls, and
            a repeated unload stays idempotent.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "real-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "real-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_REAL_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("real-tools")
            manager.load("real-tools", grant_permissions=False)
            policy = ToolPolicy(frozenset({"plugin.real-tools.utility"}), frozenset({"plugin.real-tools.ping"}))
            ping = registry.materialize(_session(), policy, "coordinator")[0]
            self.assertEqual("ping:value:session-one:coordinator", ping.handler(value="value"))
            revision = registry.revision

            self.assertEqual("inactive", manager.unload("real-tools")["state"])

            self.assertEqual((), registry.definitions())
            self.assertGreater(registry.revision, revision)
            self.assertEqual([], registry.materialize(_session(), policy, "coordinator"))
            with self.assertRaises(ToolCallValidationError):
                ping.handler(value="value")
            self.assertEqual("inactive", manager.unload("real-tools")["state"])

    def test_settings_schema_exposes_user_parameters_to_runtime(self) -> None:
        """Persist declared user parameters and expose them through runtime access.

        Returns:
            ``None`` after verifying a plugin receives its validated configured
            string parameter during setup.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "parameter-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "parameter-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": True},
                "settings_schema": [{"key": "instructions", "type": "string", "title": "Instructions", "format": "textarea", "placeholder": "Optional instructions", "default": "default instructions"}],
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        assert runtime.setting('instructions') == 'user instructions'\n"
                "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('parameter', 'utility', 'Parameter', 'Reads settings', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = _manager(root, ToolRegistry())
            registered = manager.register("parameter-tools")
            self.assertEqual("default instructions", manager.settings(registered["id"])["settings"]["instructions"])
            manager.replace_settings(registered["id"], {"instructions": "user instructions"})
            manager.load(registered["id"], grant_permissions=False)

    def test_declarative_panel_validates_inputs_and_invokes_registered_action(self) -> None:
        """Render-safe panel declarations dispatch only matching plugin actions.

        Returns:
            ``None`` after validating transient panel input and its typed action
            result without persisting the submitted value as a setting.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "panel-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "panel-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False, "panels": [{
                    "id": "lookup", "title": "Lookup", "action": "lookup", "submit_label": "Find",
                    "fields": [{"key": "query", "type": "string", "title": "Query", "required": True}],
                }]},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginUiActionResult\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        runtime.register_ui_action('lookup', lambda request: PluginUiActionResult('Result', str(request.value('query')), 'success'))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = _manager(root, ToolRegistry())
            registered = manager.register("panel-tools")
            manager.load(registered["id"], grant_permissions=False)
            result = manager.invoke_panel(registered["id"], "lookup", {"query": "heap"})
            self.assertEqual(PluginUiActionResult("Result", "heap", "success"), result)
            self.assertEqual((), manager.store.get(registered["id"]).settings)
            with self.assertRaises(ValueError):
                manager.invoke_panel(registered["id"], "lookup", {"unexpected": "value"})

    def test_sensitive_panel_field_is_transient_and_settings_remain_secret_free(self) -> None:
        """Allow a password panel field without permitting persisted secrets.

        Returns:
            ``None`` after proving a sensitive panel value reaches only its
            action handler and a credential-shaped settings key is rejected.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "login-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "login-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False, "panels": [{
                    "id": "login", "title": "Login", "action": "login", "fields": [
                        {"key": "password", "type": "string", "format": "password", "sensitive": True, "required": True},
                    ],
                }]},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginUiActionResult\n"
                "class Plugin:\n"
                "    def setup(self, runtime): runtime.register_ui_action('login', lambda request: PluginUiActionResult('OK', 'authenticated', 'success'))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = _manager(root, ToolRegistry())
            manager.register("login-tools")
            manager.load("login-tools", grant_permissions=False)
            self.assertEqual("authenticated", manager.invoke_panel("login-tools", "login", {"password": "never-persist"}).content)
            self.assertEqual((), manager.store.get("login-tools").settings)

    @unittest.skipUnless(
        (Path.cwd() / "plugins" / "gzctf").is_dir(),
        "bundled gzctf plugin is absent from this checkout",
    )
    def test_gzctf_migration_loads_provider_and_sensitive_login_panel(self) -> None:
        """Load the migrated bundled GZCTF plugin through the v1 runtime.

        Returns:
            ``None`` after asserting all GZCTF Tools publish and the password
            is exposed only as a marked transient panel field.
        """
        with TemporaryDirectory() as directory:
            manager = PluginManager(Path(directory), ToolRegistry(), Path.cwd() / "plugins")
            manager.register("gzctf")
            active = manager.load("gzctf", grant_permissions=True)
            password = active["panels"][0]["fields"][2]
            self.assertTrue(password["sensitive"])
            self.assertEqual("password", password["format"])
            definitions = [item.id for item in manager._tool_registry.definitions() if item.id.startswith("plugin.gzctf.")]
            self.assertEqual(11, len(definitions))

    def test_development_packages_are_discovered_and_can_be_loaded(self) -> None:
        """Repository-style development packages remain inert until enabled.

        Returns:
            ``None`` after verifying discovery and explicit tool publication.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-plugins" / "hello"
            source.mkdir(parents=True)
            _json(source / "manifest.json", {
                "name": "hello", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (source / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime): runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('hello', 'utility', 'Hello', 'Hello helper', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = PluginManager(root, ToolRegistry(), source.parent)
            self.assertEqual("discovered", manager.statuses()[0]["state"])
            manager.register("hello")
            manager.load("hello", grant_permissions=False)
            self.assertEqual(["plugin.hello.hello"], [item.id for item in manager._tool_registry.definitions()])

    def test_repository_plugin_manifests_match_current_contract(self) -> None:
        """Every bundled source plugin is valid and POFP tools can publish.

        Returns:
            ``None`` after asserting all manifests validate and the migrated
            POFP tool plugin publishes its two namespaced definitions.
        """
        with TemporaryDirectory() as directory:
            manager = PluginManager(Path(directory), ToolRegistry(), Path.cwd() / "plugins")
            statuses = manager.statuses()
            self.assertFalse(any(item["state"] == "error" for item in statuses))
            pofp = next(item for item in statuses if item["name"] == "pofp-ctf")
            self.assertEqual("discovered", pofp["state"])
            manager.register("pofp-ctf")
            manager.load("pofp-ctf", grant_permissions=True)
            self.assertEqual(
                ["plugin.pofp-ctf.ctf_read", "plugin.pofp-ctf.ctf_search"],
                sorted(item.id for item in manager._tool_registry.definitions()),
            )

    def test_canonical_package_layout_resolves_without_deprecation_warning(self) -> None:
        """The current ``package/`` home resolves names and stays warning-free.

        Returns:
            ``None`` after proving discovery, registration, and loading from the
            canonical layout never reports the legacy-layout deprecation.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "canonical-pack"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "canonical-pack", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            manager = _manager(root, ToolRegistry())

            with self.assertNoLogs("angelus.modules.plugin_module.manager", level="WARNING"):
                statuses = manager.statuses()
                registered = manager.register("canonical-pack")
                active = manager.load("canonical-pack", grant_permissions=False)
            self.assertEqual(["canonical-pack"], [item["name"] for item in statuses])
            self.assertEqual("inactive", registered["state"])
            self.assertEqual("active", active["state"])

    def test_legacy_packages_layout_is_still_resolved_with_one_warning(self) -> None:
        """Packages left in the pre-refactor ``packages/`` home keep working.

        Returns:
            ``None`` after proving the deprecated directory still resolves the
            requested name for registration and loading, while warning once.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "legacy-pack"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "legacy-pack", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            manager = _manager(root, ToolRegistry())

            with self.assertLogs("angelus.modules.plugin_module.manager", level="WARNING") as logs:
                statuses = manager.statuses()
                manager.statuses()
                registered = manager.register("legacy-pack")
                active = manager.load("legacy-pack", grant_permissions=False)

            self.assertEqual(1, len(logs.records))
            self.assertIn("deprecated", logs.records[0].getMessage())
            self.assertEqual(["legacy-pack"], [item["name"] for item in statuses])
            self.assertEqual("inactive", registered["state"])
            self.assertEqual("active", active["state"])
            self.assertEqual(["plugin.legacy-pack.ping"], [item.id for item in manager._tool_registry.definitions()])

    def test_async_plugin_tool_handler_is_rejected_once_its_plugin_unloads(self) -> None:
        """An awaitable plugin Tool answers while loaded and dies after unload.

        Returns:
            ``None`` after awaiting one real ``async def`` Tool handler, then
            asserting the identical awaited call raises
            :class:`~llmfetcher.tool_handler.ToolCallValidationError` naming the
            unloaded plugin instead of running plugin code.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "live-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "live-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_ASYNC_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("live-tools")
            manager.load("live-tools", grant_permissions=False)
            policy = ToolPolicy(
                frozenset({"plugin.live-tools.utility"}),
                frozenset({"plugin.live-tools.await_ping"}),
            )
            await_ping = registry.materialize(_session(), policy, "coordinator")[0]

            self.assertEqual("async-ping:value:session-one:coordinator", asyncio.run(await_ping.handler(value="value")))

            self.assertEqual("inactive", manager.unload("live-tools")["state"])

            self.assertEqual([], registry.materialize(_session(), policy, "coordinator"))
            with self.assertRaises(ToolCallValidationError) as rejected:
                asyncio.run(await_ping.handler(value="value"))
            message = str(rejected.exception)
            self.assertIn("no longer available", message)
            self.assertIn("its plugin was unloaded", message)
            self.assertIn("plugin.live-tools.await_ping", message)

    def test_held_sync_handler_reference_is_guarded_rather_than_dropped(self) -> None:
        """A captured sync handler is guarded, not merely un-materializable.

        Returns:
            ``None`` after asserting the already-materialized handler works while
            loaded, that re-materialization already returns no Tools, and that
            the very same reference still raises the unload rejection, so the
            guard lives in the wrapper instead of in materialization.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "live-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "live-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_ASYNC_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("live-tools")
            manager.load("live-tools", grant_permissions=False)
            policy = ToolPolicy(
                frozenset({"plugin.live-tools.utility"}),
                frozenset({"plugin.live-tools.sync_ping"}),
            )
            sync_ping = registry.materialize(_session(), policy, "coordinator")[0]
            self.assertEqual("sync-ping:value:session-one:coordinator", sync_ping.handler(value="value"))

            manager.unload("live-tools")

            self.assertEqual([], registry.materialize(_session(), policy, "coordinator"))
            with self.assertRaises(ToolCallValidationError) as rejected:
                sync_ping.handler(value="value")
            message = str(rejected.exception)
            self.assertIn("no longer available", message)
            self.assertIn("its plugin was unloaded", message)
            self.assertIn("plugin.live-tools.sync_ping", message)

    def test_repeated_unload_and_repeated_revoke_stay_quiet_and_revoked(self) -> None:
        """Repeated unload and duplicate revoke neither raise nor revive Tools.

        Returns:
            ``None`` after asserting a second unload of the same plugin stays
            inactive, that a reload publishes a fresh working generation while
            the stale handler stays rejected, and that one provider observes
            exactly one revoke for two unregister attempts.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "package" / "live-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "live-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(_ASYNC_TOOL_PLUGIN_SOURCE, encoding="utf-8")
            registry = ToolRegistry()
            manager = _manager(root, registry)
            manager.register("live-tools")
            manager.load("live-tools", grant_permissions=False)
            policy = ToolPolicy(
                frozenset({"plugin.live-tools.utility"}),
                frozenset({"plugin.live-tools.sync_ping"}),
            )
            stale = registry.materialize(_session(), policy, "coordinator")[0]

            self.assertEqual("inactive", manager.unload("live-tools")["state"])
            self.assertEqual("inactive", manager.unload("live-tools")["state"])
            self.assertEqual([], registry.materialize(_session(), policy, "coordinator"))
            with self.assertRaises(ToolCallValidationError):
                stale.handler(value="value")

            manager.load("live-tools", grant_permissions=False)
            fresh = registry.materialize(_session(), policy, "coordinator")[0]
            self.assertIsNot(stale.handler, fresh.handler)
            self.assertEqual("sync-ping:value:session-one:coordinator", fresh.handler(value="value"))
            with self.assertRaises(ToolCallValidationError):
                stale.handler(value="value")
            manager.unload("live-tools")

            probe = _RevokeProbeProvider()
            registry.register(ToolProviderRegistration(
                "revoke-probe",
                probe,
                (ToolCategory("revoke-probe", "Probe", "Probe tools"),),
                (ToolDefinition("revoke_probe", "revoke-probe", "Probe", "Probe tool", "revoke-probe"),),
            ))
            probe_policy = ToolPolicy(frozenset({"revoke-probe"}), frozenset({"revoke_probe"}))
            self.assertEqual(["revoke_probe"], [item.name for item in registry.materialize(_session(), probe_policy, "coordinator")])
            registry.unregister("revoke-probe")
            registry.unregister("revoke-probe")
            self.assertEqual(1, probe.revocations)
            self.assertEqual((), registry.definitions())
            self.assertEqual([], registry.materialize(_session(), probe_policy, "coordinator"))




def _json(path: Path, value: object) -> None:
    """Write a test fixture manifest.

    Args:
        path: Destination temporary JSON file.
        value: JSON-safe fixture object.

    Returns:
        None.
    """
    path.write_text(json.dumps(value), encoding="utf-8")


class _InlineProvider:
    """Minimal host provider used to exercise registry-level role defaults."""

    def materialize(self, session: object, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        """Return one un-gated Tool for every Agent role.

        Args:
            session: Unused Session aggregate.
            policy: Unused effective policy; the registry already filtered by it.
            role: Unused receiving Agent role.
            agent_name: Unused Agent identity.

        Returns:
            One concrete Tool without declared role gating.
        """
        return [Tool("shared_tool", "Shared", ToolSchema(), lambda: "shared")]


class _RevokeProbeProvider:
    """Minimal provider counting how often teardown reaches its revoke hook."""

    def __init__(self) -> None:
        """Start with no observed revocation.

        Returns:
            ``None``. Revocation attempts are counted in ``revocations``.
        """
        self.revocations = 0

    def materialize(self, session: object, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        """Return one Probe Tool regardless of policy and role.

        Args:
            session: Unused Session aggregate.
            policy: Unused effective policy.
            role: Unused receiving Agent role.
            agent_name: Unused Agent identity.

        Returns:
            One concrete Tool owned by the probe provider.
        """
        return [Tool("revoke_probe", "Probe", ToolSchema(), lambda: "probe")]

    def revoke(self) -> None:
        """Record one revocation request from the registry.

        Returns:
            None. Repeated calls stay harmless and observable.
        """
        self.revocations += 1



def _session(session_id: str = "session-one") -> object:
    """Build the minimal Session shape plugin providers dereference.

    Args:
        session_id: Session identity exposed through ``session.execution``.

    Returns:
        Stub aggregate whose ``execution.session_id`` mirrors a live Session.
    """
    return SimpleNamespace(execution=SimpleNamespace(session_id=session_id))


def _manager(root: Path, registry: ToolRegistry) -> PluginManager:
    """Create a manager that scans only the supplied temporary state root.

    Args:
        root: Temporary state root holding ``plugins/package`` fixtures.
        registry: Tool registry receiving loaded contributions.

    Returns:
        Manager whose development root is an empty directory inside ``root``, so
        repository ``plugins/`` packages can never leak into an assertion.
    """
    development = root / "development"
    development.mkdir(exist_ok=True)
    return PluginManager(root, registry, development)


if __name__ == "__main__":
    unittest.main()
