import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from requests.exceptions import ConnectionError, ReadTimeout

import aider
from aider.coders import Coder
from aider.commands import Commands
from aider.help import Help, fname_to_url
from aider.io import InputOutput
from aider.models import Model


class TestHelp(unittest.TestCase):
    @staticmethod
    def retry_with_backoff(func, max_time=60, initial_delay=1, backoff_factor=2):
        """
        Execute a function with exponential backoff retry logic.

        Args:
            func: Function to execute
            max_time: Maximum time in seconds to keep retrying
            initial_delay: Initial delay between retries in seconds
            backoff_factor: Multiplier for delay after each retry

        Returns:
            The result of the function if successful

        Raises:
            The last exception encountered if all retries fail
        """
        start_time = time.time()
        delay = initial_delay
        last_exception = None

        while time.time() - start_time < max_time:
            try:
                return func()
            except (ReadTimeout, ConnectionError) as e:
                last_exception = e
                time.sleep(delay)
                delay = min(delay * backoff_factor, 15)  # Cap max delay at 15 seconds

        # If we've exhausted our retry time, raise the last exception
        if last_exception:
            raise last_exception
        raise Exception("Retry timeout exceeded but no exception was caught")

    @classmethod
    def setUpClass(cls):
        io = InputOutput(pretty=False, yes=True)

        GPT35 = Model("gpt-3.5-turbo")

        coder = Coder.create(GPT35, None, io)
        commands = Commands(io, coder)

        help_coder_run = MagicMock(return_value="")
        aider.coders.HelpCoder.run = help_coder_run

        def run_help_command():
            try:
                commands.cmd_help("hi")
            except aider.commands.SwitchCoder:
                pass
            else:
                # If no exception was raised, fail the test
                assert False, "SwitchCoder exception was not raised"

        # Use retry with backoff for the help command that loads models
        cls.retry_with_backoff(run_help_command)

        help_coder_run.assert_called_once()

    def test_init(self):
        help_inst = Help()
        self.assertIsNotNone(help_inst.retriever)

    def test_ask_without_mock(self):
        help_instance = Help()
        question = "What is aider?"
        result = help_instance.ask(question)

        self.assertIn(f"# Question: {question}", result)
        self.assertIn("<doc", result)
        self.assertIn("</doc>", result)
        self.assertGreater(len(result), 100)  # Ensure we got a substantial response

        # Check for some expected content (adjust based on your actual help content)
        self.assertIn("aider", result.lower())
        self.assertIn("ai", result.lower())
        self.assertIn("chat", result.lower())

        # Assert that there are more than 5 <doc> entries
        self.assertGreater(result.count("<doc"), 5)

    def test_fname_to_url_unix(self):
        # Test relative Unix-style paths
        self.assertEqual(
            fname_to_url("website/docs/index.md"), "https://aider.chat/docs"
        )
        self.assertEqual(
            fname_to_url("website/docs/usage.md"), "https://aider.chat/docs/usage.html"
        )
        self.assertEqual(fname_to_url("website/_includes/header.md"), "")

        # Test absolute Unix-style paths
        self.assertEqual(
            fname_to_url("/home/user/project/website/docs/index.md"),
            "https://aider.chat/docs",
        )
        self.assertEqual(
            fname_to_url("/home/user/project/website/docs/usage.md"),
            "https://aider.chat/docs/usage.html",
        )
        self.assertEqual(
            fname_to_url("/home/user/project/website/_includes/header.md"), ""
        )

    def test_fname_to_url_windows(self):
        # Test relative Windows-style paths
        self.assertEqual(
            fname_to_url(r"website\docs\index.md"), "https://aider.chat/docs"
        )
        self.assertEqual(
            fname_to_url(r"website\docs\usage.md"), "https://aider.chat/docs/usage.html"
        )
        self.assertEqual(fname_to_url(r"website\_includes\header.md"), "")

        # Test absolute Windows-style paths
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\docs\index.md"),
            "https://aider.chat/docs",
        )
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\docs\usage.md"),
            "https://aider.chat/docs/usage.html",
        )
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\_includes\header.md"), ""
        )

    def test_fname_to_url_edge_cases(self):
        # Test paths that don't contain 'website'
        self.assertEqual(fname_to_url("/home/user/project/docs/index.md"), "")
        self.assertEqual(fname_to_url(r"C:\Users\user\project\docs\index.md"), "")

        # Test empty path
        self.assertEqual(fname_to_url(""), "")

        # Test path with 'website' in the wrong place
        self.assertEqual(fname_to_url("/home/user/website_project/docs/index.md"), "")


if __name__ == "__main__":
    unittest.main()


class TestHelpExtra(unittest.TestCase):
    def test_get_help_extra_package_local_checkout(self):
        """When pyproject.toml exists (local checkout), return .[help]."""

        from aider.help import get_help_extra_package

        # In the test environment, pyproject.toml exists at the repo root
        result = get_help_extra_package()
        self.assertEqual(result, ".[help]")

    def test_get_help_extra_package_pinned_release(self):
        """When pyproject.toml does not exist (installed package), return pinned version."""
        from unittest.mock import patch

        # Temporarily remove pyproject.toml to simulate installed package
        repo_root = Path(__file__).resolve().parent.parent.parent
        pyproject_path = repo_root / "pyproject.toml"
        self.assertTrue(
            pyproject_path.exists(), "Test precondition: pyproject.toml must exist"
        )

        # Mock Path.exists to return False for pyproject.toml
        with patch("aider.help.Path.exists") as mock_exists:
            # Make the specific check for pyproject.toml return False
            mock_exists.return_value = False

            from aider import __version__
            from aider.help import get_help_extra_package

            result = get_help_extra_package()
            expected = f"aider-chat[help]=={__version__}"
            self.assertEqual(result, expected)

    def test_install_help_extra_uses_get_help_extra_package(self):
        """install_help_extra passes the resolved package into check_pip_install_extra."""
        from unittest.mock import MagicMock, patch

        from aider.help import install_help_extra

        mock_io = MagicMock()

        with patch("aider.help.get_help_extra_package") as mock_get_pkg:
            mock_get_pkg.return_value = ".[help]"
            with patch("aider.help.utils.check_pip_install_extra") as mock_check:
                mock_check.return_value = True

                result = install_help_extra(mock_io)

                mock_get_pkg.assert_called_once()
                # Verify check_pip_install_extra was called with the right pip_install_cmd
                call_args = mock_check.call_args
                pip_install_cmd = call_args[0][3]  # 4th positional arg
                self.assertEqual(pip_install_cmd[0], ".[help]")
                self.assertIn("--extra-index-url", pip_install_cmd)
                self.assertIn("https://download.pytorch.org/whl/cpu", pip_install_cmd)
                self.assertTrue(result)
