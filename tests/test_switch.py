import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import tomlkit

from codex_http_switch import core
from codex_http_switch.cli import main, verify

SAMPLE = '''# keep this comment
model = "example-model" # chosen by user
model_context_window = 1000000

[features]
respect_system_proxy = true

[mcp_servers.my-tool]
command = "example"
'''


class ConfigTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('OPENAI_API_KEY', None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.toml"
        self.path.write_text(SAMPLE)
        (self.path.parent / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "SYNTHETIC_SECRET"}}))

    def values(self):
        return tomlkit.parse(self.path.read_text()).unwrap()

    def test_plan_never_writes_or_exposes_credentials(self):
        original = self.path.read_bytes()
        r = core.plan(self.path)
        self.assertEqual(r['status'], 'change-proposed')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / core.BACKUPS).exists())
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(r))

    def test_apply_preserves_comments_settings_and_is_idempotent(self):
        before = self.values()
        r = core.apply(self.path)
        after = self.values()
        after.pop('model_provider')
        after['model_providers'].pop(core.ALIAS)
        after.pop('model_providers')
        self.assertEqual(after, before)
        self.assertIn('# keep this comment', self.path.read_text())
        self.assertIn('# chosen by user', self.path.read_text())
        self.assertEqual(Path(r['backup']).read_text(), SAMPLE)
        files = list((self.path.parent / core.BACKUPS).iterdir())
        self.assertEqual(core.apply(self.path)['status'], 'already-http')
        self.assertEqual(list((self.path.parent / core.BACKUPS).iterdir()), files)
        if os.name != 'nt':
            self.assertEqual(Path(r['backup']).stat().st_mode & 0o777, 0o600)
            self.assertEqual((self.path.parent / core.BACKUPS).stat().st_mode & 0o777, 0o700)

    def test_restore_keeps_later_model_and_mcp_changes(self):
        r = core.apply(self.path)
        d = tomlkit.parse(self.path.read_text())
        d['model'] = 'later-model'
        d['mcp_servers']['later'] = {'command': 'later-command'}
        self.path.write_text(tomlkit.dumps(d))
        core.restore(self.path, Path(r['receipt']))
        v = self.values()
        self.assertNotIn('model_provider', v)
        self.assertNotIn('model_providers', v)
        self.assertEqual(v['model'], 'later-model')
        self.assertEqual(v['mcp_servers']['later']['command'], 'later-command')

    def test_explicit_default_selection_restored(self):
        self.path.write_text('model_provider = "openai"\n' + SAMPLE)
        r = core.apply(self.path)
        core.restore(self.path, Path(r['receipt']))
        self.assertEqual(self.values()['model_provider'], 'openai')

    def test_changed_owned_profile_blocks_restore_without_writes(self):
        r = core.apply(self.path)
        d = tomlkit.parse(self.path.read_text())
        d['model_providers'][core.ALIAS]['supports_websockets'] = True
        self.path.write_text(tomlkit.dumps(d))
        original = self.path.read_bytes()
        with self.assertRaises(core.SwitchError):
            core.restore(self.path, Path(r['receipt']))
        self.assertEqual(self.path.read_bytes(), original)

    def test_changed_selection_blocks_restore(self):
        r = core.apply(self.path)
        self.path.write_text(self.path.read_text().replace(f'model_provider = "{core.ALIAS}"', 'model_provider = "later-provider"'))
        with self.assertRaises(core.SwitchError):
            core.restore(self.path, Path(r['receipt']))

    def test_tampered_backup_is_rejected(self):
        r = core.apply(self.path)
        Path(r['backup']).write_text('model = "tampered"')
        with self.assertRaises(core.SwitchError):
            core.restore(self.path, Path(r['receipt']))

    def test_receipt_cannot_restore_another_config(self):
        r = core.apply(self.path)
        other = self.path.parent / 'other.toml'
        other.write_text(self.path.read_text())
        with self.assertRaises(core.SwitchError):
            core.restore(other, Path(r['receipt']))

    def test_custom_provider_and_endpoint_are_preserved(self):
        for text in ['model_provider = "other"\n' + SAMPLE,
                     'openai_base_url = "https://example.invalid/v1"\n' + SAMPLE]:
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(core.SwitchError):
                    core.apply(self.path)
                self.assertEqual(self.path.read_text(), text)
                self.assertFalse((self.path.parent / core.BACKUPS).exists())

    def test_api_key_login_is_not_rerouted(self):
        (self.path.parent / 'auth.json').write_text('{"auth_mode":"apikey","OPENAI_API_KEY":"SYNTHETIC_KEY"}')
        with self.assertRaises(core.SwitchError):
            core.apply(self.path)
        with self.assertRaises(core.SwitchError):
            core.apply(self.path, 'chatgpt')
        self.assertEqual(self.path.read_text(), SAMPLE)

    def test_api_key_environment_is_not_rerouted(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'SYNTHETIC_KEY'}):
            with self.assertRaises(core.SwitchError):
                core.apply(self.path, 'chatgpt')

    def test_existing_http_with_api_key_is_not_online_ready(self):
        core.apply(self.path)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'SYNTHETIC_KEY'}):
            self.assertEqual(core.doctor(self.path)['status'], 'needs-attention')

    def test_edit_during_planning_is_preserved(self):
        original_plan = core.plan
        def changed(path, mode):
            result = original_plan(path, mode)
            path.write_text('model_provider="changed-elsewhere"\n')
            return result
        with patch('codex_http_switch.core.plan', side_effect=changed):
            with self.assertRaises(core.SwitchError):
                core.apply(self.path)
        self.assertEqual(self.path.read_text(), 'model_provider="changed-elsewhere"\n')
        self.assertFalse((self.path.parent / core.BACKUPS).exists())

    def test_malformed_receipt_backup_names_are_rejected(self):
        r = core.apply(self.path)
        receipt = Path(r['receipt'])
        state = json.loads(receipt.read_text())
        for bad in [123, ['file'], '../elsewhere']:
            state['backup_file'] = bad
            receipt.write_text(json.dumps(state))
            with self.subTest(name=bad), self.assertRaises(core.SwitchError):
                core.restore(self.path, receipt)

    def test_online_probe_refuses_an_unrelated_config(self):
        core.apply(self.path)
        with patch.dict(os.environ, {'CODEX_HOME': str(self.path.parent / 'different')}), \
             patch('codex_http_switch.cli.subprocess.Popen') as popen:
            with self.assertRaises(core.SwitchError):
                verify(self.path, True, 'fake-codex', 5)
            popen.assert_not_called()

    def test_keychain_login_needs_explicit_declaration(self):
        (self.path.parent / 'auth.json').unlink()
        with self.assertRaises(core.SwitchError):
            core.plan(self.path)
        self.assertEqual(core.plan(self.path, 'chatgpt')['status'], 'change-proposed')

    def test_alias_conflict_is_preserved(self):
        self.path.write_text(SAMPLE + '\n[model_providers.openai-http-switch]\nname="User profile"\n')
        before = self.path.read_bytes()
        with self.assertRaises(core.SwitchError):
            core.apply(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_unrelated_existing_http_alias_is_a_noop(self):
        d = tomlkit.parse(SAMPLE)
        d['model_provider'] = 'existing-http'
        d['model_providers'] = {'existing-http': core.PROFILE}
        self.path.write_text(tomlkit.dumps(d))
        self.assertEqual(core.apply(self.path)['status'], 'already-http')
        self.assertFalse((self.path.parent / core.BACKUPS).exists())

    def test_builtin_override_is_not_mistaken_for_http(self):
        d = tomlkit.parse(SAMPLE)
        d['model_providers'] = {'openai': core.PROFILE}
        self.path.write_text(tomlkit.dumps(d))
        self.assertEqual(core.plan(self.path)['status'], 'change-proposed')

    def test_invalid_toml_and_lock_never_modify_config(self):
        self.path.write_text('invalid = [')
        with self.assertRaises(core.SwitchError):
            core.apply(self.path)
        self.assertEqual(self.path.read_text(), 'invalid = [')
        self.path.write_text(SAMPLE)
        lock = self.path.with_name(self.path.name + '.http-switch.lock')
        lock.write_text('another operation')
        with self.assertRaises(core.SwitchError):
            core.apply(self.path)
        self.assertEqual(lock.read_text(), 'another operation')

    def test_concurrent_edit_prevents_replace(self):
        self.path.write_text('model="concurrent edit"')
        with self.assertRaises(core.SwitchError):
            core.replace(self.path, SAMPLE.encode(), b'model="replacement"')
        self.assertEqual(self.path.read_text(), 'model="concurrent edit"')

    def test_symlink_is_not_replaced(self):
        link = self.path.parent / 'linked.toml'
        try:
            link.symlink_to(self.path)
        except OSError:
            self.skipTest('Symlinks not available for this Windows account')
        with self.assertRaises(core.SwitchError):
            core.apply(link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.path.read_text(), SAMPLE)

    def test_doctor_json_does_not_leak_auth_or_raw_log_body(self):
        db = self.path.parent / 'logs.sqlite'
        with contextlib.closing(sqlite3.connect(db)) as c, c:
            c.execute('CREATE TABLE logs(id INTEGER PRIMARY KEY,ts INTEGER,target TEXT,feedback_log_body TEXT)')
            c.execute('INSERT INTO logs VALUES(1,?,?,?)', (int(time.time()), 'codex_core::responses_retry',
                      'PRIVATE_PROMPT SYNTHETIC_SECRET websocket closed by server before response.completed'))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['doctor', '--config', str(self.path), '--logs-db', str(db), '--json'])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result['logs']['matching_websocket_errors'], 1)
        self.assertNotIn('PRIVATE_PROMPT', out.getvalue())
        self.assertNotIn('SYNTHETIC_SECRET', out.getvalue())

    def test_verify_offline_does_not_start_codex(self):
        core.apply(self.path)
        with patch('codex_http_switch.cli.subprocess.Popen') as popen:
            self.assertEqual(verify(self.path, False, None, 5)['status'], 'config-valid')
            popen.assert_not_called()

    def test_online_verify_requires_completed_turn_and_expected_output(self):
        core.apply(self.path)
        events = '\n'.join(json.dumps(x) for x in [
            {'type':'item.completed','item':{'type':'agent_message','text':'CODEX_HTTP_SWITCH_OK'}},
            {'type':'turn.completed'}])
        proc = unittest.mock.Mock(returncode=0)
        proc.communicate.return_value = (events, '')
        with patch.dict(os.environ, {'CODEX_HOME': str(self.path.parent)}), \
             patch('codex_http_switch.cli.subprocess.Popen', return_value=proc):
            self.assertEqual(verify(self.path, True, 'fake-codex', 5)['status'], 'probe-passed')
            proc.communicate.return_value = (json.dumps({'type':'turn.started'}), '')
            self.assertEqual(verify(self.path, True, 'fake-codex', 5)['status'], 'probe-failed')
            proc.communicate.return_value = (events, 'stream disconnected - retrying sampling')
            self.assertEqual(verify(self.path, True, 'fake-codex', 5)['status'], 'probe-failed')

    def test_non_table_settings_fail_cleanly(self):
        for text in ['model_provider=[]', 'model_providers=[]', '[model_providers]\nopenai=3']:
            self.path.write_text(text)
            with self.subTest(text=text), self.assertRaises(core.SwitchError):
                core.plan(self.path)


if __name__ == '__main__':
    unittest.main()
