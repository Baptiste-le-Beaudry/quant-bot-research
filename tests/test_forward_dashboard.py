import tempfile, threading, unittest
from pathlib import Path
from quant_bot.config import RISK_PROFILES
from quant_bot.dashboard.forward_dashboard import snapshot, HTML
from quant_bot.forward.store import ForwardStateStore

class ForwardDashboardTests(unittest.TestCase):
    def test_persistent_three_profile_snapshot_and_safety(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.sqlite3'; s=ForwardStateStore(p); s.initialize_accounts(RISK_PROFILES); s.close()
            a=snapshot(p); b=snapshot(p)
            self.assertEqual({x['profile'] for x in a['profiles']},set(RISK_PROFILES))
            self.assertEqual([x['realized_equity'] for x in a['profiles']],[x['realized_equity'] for x in b['profiles']])
            self.assertTrue(all(not x['live_enabled'] for x in RISK_PROFILES.values()))
            self.assertEqual(a['health']['live_orders'],'DISABLED')
    def test_required_ui_and_refresh(self):
        for text in ('FORWARD PAPER','OPEN POSITIONS','EXECUTION / HEALTH','SIGNAL STREAM','setInterval(L,10000)'):
            self.assertIn(text,HTML)
