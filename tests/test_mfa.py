import unittest
from unittest.mock import patch

from e37 import E37Error, mfa, web


LOGIN = '<input name="tbPassword">'
MFA = ('<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="{state}">'
       '<input name="tbVerifyCode"><input type="checkbox" name="cbStaySignedIn" checked>')
ACCOUNT = {"name": "test", "webshopId": "shop", "web": {"email": "test@example.org", "password": "secret"}}


class LoginTests(unittest.TestCase):
    def login(self, pages, prompt):
        with patch.object(web.Session, "_page", side_effect=pages) as page, \
                patch.object(web.Session, "_has_auth_cookie", return_value=True):
            session = web.Session(ACCOUNT, mfa_prompt=prompt)
        return session, page

    def test_without_mfa(self):
        prompt = unittest.mock.Mock()
        session, _ = self.login([("login", LOGIN), ("home", "home")], prompt)
        prompt.assert_not_called()
        self.assertEqual(session._home, "home")

    def test_app_and_email_challenge(self):
        for source in ("authenticator app", "e-post"):
            with self.subTest(source=source):
                prompt = unittest.mock.Mock(return_value=" 012345 ")
                session, page = self.login([
                    ("login", LOGIN), ("loginMfa", source + MFA.format(state="first")),
                    ("home", "home")], prompt)
                posted = page.call_args_list[2].args
                self.assertEqual(posted[0], "loginMfa")
                self.assertEqual(posted[1]["tbVerifyCode"], "012345")
                self.assertEqual(posted[1]["__VIEWSTATE"], "first")
                self.assertNotIn("cbStaySignedIn", posted[1])
                self.assertNotIn("tbPassword", posted[1])
                self.assertEqual(session._home, "home")

    def test_retry_uses_new_state(self):
        prompt = unittest.mock.Mock(side_effect=["111111", "222222"])
        _, page = self.login([
            ("login", LOGIN), ("loginMfa", MFA.format(state="first")),
            ("loginMfa", MFA.format(state="second")), ("home", "home")], prompt)
        self.assertEqual(page.call_args_list[3].args[1]["__VIEWSTATE"], "second")
        self.assertEqual(prompt.call_args_list[1].args, ("test", 2))

    def test_retries_bounded(self):
        prompt = unittest.mock.Mock(return_value="wrong")
        with self.assertRaisesRegex(E37Error, "tre försök"):
            self.login([("login", LOGIN)] + [("loginMfa", MFA.format(state="s"))] * 4, prompt)
        self.assertEqual(prompt.call_count, 3)

    def test_cancel_does_not_submit(self):
        with patch.object(web.Session, "_page", side_effect=[("login", LOGIN),
                   ("loginMfa", MFA.format(state="s"))]) as page:
            with self.assertRaisesRegex(E37Error, "avbröts"):
                web.Session(ACCOUNT, mfa_prompt=lambda *args: None)
        self.assertEqual(page.call_count, 2)

    def test_no_auth_cookie_is_not_success(self):
        with patch.object(web.Session, "_page", side_effect=[("login", LOGIN),
                   ("loginMfa", MFA.format(state="s")), ("home", "home")]), \
                patch.object(web.Session, "_has_auth_cookie", return_value=False):
            with self.assertRaisesRegex(E37Error, "misslyckades"):
                web.Session(ACCOUNT, mfa_prompt=lambda *args: "012345")

    def test_expired_challenge(self):
        with self.assertRaisesRegex(E37Error, "misslyckades"):
            self.login([("login", LOGIN), ("loginMfa", MFA.format(state="s")),
                        ("login", LOGIN)], lambda *args: "012345")


class PromptTests(unittest.TestCase):
    def test_agent_uses_dialog(self):
        with patch.dict("os.environ", {"E37_MFA_MODE": "auto"}), \
                patch("sys.stdin.isatty", return_value=False), \
                patch.object(mfa, "_dialog", return_value="012345") as dialog:
            self.assertEqual(mfa.ask_code("test"), "012345")
        dialog.assert_called_once()

    def test_terminal_hides_code(self):
        with patch.dict("os.environ", {"E37_MFA_MODE": "terminal"}), \
                patch("getpass.getpass", return_value="012345"):
            self.assertEqual(mfa.ask_code("test"), "012345")

    def test_no_echo_fallback(self):
        with patch.dict("os.environ", {"E37_MFA_MODE": "terminal"}), \
                patch("getpass.getpass", side_effect=mfa.getpass.GetPassWarning):
            with self.assertRaises(E37Error):
                mfa.ask_code("test")

    def test_noninteractive_mode(self):
        with patch.dict("os.environ", {"E37_MFA_MODE": "none"}):
            with self.assertRaisesRegex(E37Error, "kräver MFA"):
                mfa.ask_code("test")

    def test_dialog_cancel(self):
        with patch.dict("os.environ", {"E37_MFA_MODE": "dialog"}), \
                patch.object(mfa, "_dialog", return_value=None):
            with self.assertRaisesRegex(E37Error, "avbröts"):
                mfa.ask_code("test")

    def test_mac_fallback_secret_not_in_arguments(self):
        with patch.object(mfa.sys, "platform", "darwin"), \
                patch.object(mfa.subprocess, "run", return_value=
                    mfa.subprocess.CompletedProcess([], 0, "012345\n", "")) as run:
            self.assertEqual(mfa._fallback("Ange koden"), "012345")
        args = run.call_args.args[0]
        self.assertEqual(args[0], "osascript")
        self.assertIn("with hidden answer", args[2])
        self.assertNotIn("012345", " ".join(args))
        self.assertEqual(run.call_args.kwargs["timeout"], 190)

    def test_mac_cancel_and_timeout(self):
        with patch.object(mfa.sys, "platform", "darwin"), \
                patch.object(mfa.subprocess, "run", return_value=
                    mfa.subprocess.CompletedProcess([], 1, "", "cancelled")):
            self.assertIsNone(mfa._fallback("Ange koden"))
        with patch.object(mfa.sys, "platform", "darwin"), \
                patch.object(mfa.subprocess, "run", side_effect=
                    mfa.subprocess.TimeoutExpired("osascript", 190)):
            with self.assertRaises(E37Error):
                mfa._fallback("Ange koden")


if __name__ == "__main__":
    unittest.main()
