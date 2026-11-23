import unittest

from grid_permissions import PermissionPolicy, classify_tool


class PermissionPolicyTests(unittest.TestCase):
    def test_risk_classes(self):
        self.assertEqual(classify_tool("system_info"), "read")
        self.assertEqual(classify_tool("screenshot"), "sensitive")
        self.assertEqual(classify_tool("write_file"), "local_write")
        self.assertEqual(classify_tool("email_send"), "external")
        self.assertEqual(classify_tool("micro"), "hardware")
        self.assertEqual(classify_tool("run_command"), "dangerous")
        self.assertEqual(classify_tool("mystery_tool"), "confirm")

    def test_read_only_runs_without_approval(self):
        policy = PermissionPolicy({"mode": "ask"})
        allowed, reason = policy.allow("system_info")
        self.assertTrue(allowed)
        self.assertEqual(reason, "read-only")

    def test_external_requires_approval(self):
        policy = PermissionPolicy({"mode": "ask"})
        allowed, reason = policy.allow("email_send", "a@example.com")
        self.assertFalse(allowed)
        self.assertIn("requires approval", reason)

    def test_callback_can_allow_once(self):
        calls = []
        policy = PermissionPolicy(
            {"mode": "ask"},
            approval_callback=lambda name, arg, risk: calls.append((name, risk)) or "y",
        )
        allowed, _ = policy.allow("email_send", "a@example.com")
        self.assertTrue(allowed)
        self.assertEqual(calls, [("email_send", "external")])

    def test_always_is_remembered_for_session(self):
        policy = PermissionPolicy(
            {"mode": "ask"},
            approval_callback=lambda name, arg, risk: "a",
        )
        self.assertTrue(policy.allow("email_send")[0])
        self.assertTrue(policy.allow("email_send")[0])
        self.assertIn("email_send", policy.session_approvals)

    def test_auto_mode_allows_external_but_asks_dangerous(self):
        calls = []
        policy = PermissionPolicy(
            {"mode": "auto"},
            approval_callback=lambda name, arg, risk: calls.append(name) or False,
        )
        self.assertTrue(policy.allow("email_send")[0])
        self.assertFalse(policy.allow("run_command")[0])
        self.assertEqual(calls, ["run_command"])

    def test_read_only_mode_blocks_external(self):
        policy = PermissionPolicy({"mode": "read_only"})
        allowed, reason = policy.allow("email_send")
        self.assertFalse(allowed)
        self.assertIn("read-only mode", reason)

    def test_deny_and_auto_approve(self):
        denied = PermissionPolicy({"deny": ["email_send"]})
        self.assertFalse(denied.allow("email_send")[0])
        approved = PermissionPolicy({"auto_approve": ["email_send"]})
        self.assertTrue(approved.allow("email_send")[0])


if __name__ == "__main__":
    unittest.main()
