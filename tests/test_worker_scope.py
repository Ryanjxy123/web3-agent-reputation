"""Offline checks: a scoped worker never enables other registrations."""

from contextlib import redirect_stderr
from io import StringIO
import unittest
from unittest.mock import patch

from reputation_platform.worker import main


class WorkerScopeTests(unittest.TestCase):
    def test_only_authorized_identity_enables_public_reads(self):
        canonical = "eip155:8453:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2290"
        for reference, expected in ((canonical, True), (canonical[:-4] + "2291", False)):
            with self.subTest(reference=reference), patch("sys.argv", [
                "worker", "--once", "--enable-public-readonly", "--proxy", "http://127.0.0.1:7897",
                "--public-reference", "https://8004scan.io/agents/base/2290",
            ]), patch("reputation_platform.worker.load_database_url", return_value="unused"), patch(
                "reputation_platform.worker.Repository",
            ) as repository, patch("reputation_platform.worker.evaluate") as evaluate:
                repository.return_value.claim_job.return_value = {"reference": reference}
                main()
                self.assertEqual(evaluate.call_args.kwargs["enabled"], expected)

    def test_invalid_or_disabled_scope_is_rejected_before_database_access(self):
        for arguments in (["--public-reference", "https://8004scan.io/agents/base/2290"],
                          ["--enable-public-readonly", "--proxy", "http://127.0.0.1:7897",
                           "--public-reference", "https://127.0.0.1/"]):
            with self.subTest(arguments=arguments), patch("sys.argv", ["worker", *arguments]), patch(
                "reputation_platform.worker.Repository",
            ) as repository, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main()
            repository.assert_not_called()

    def test_long_timeout_requires_bounded_scoped_execution(self):
        for arguments in (["--public-request-timeout", "45"],
                          ["--once", "--enable-public-readonly", "--proxy", "http://127.0.0.1:7897",
                           "--public-request-timeout", "45"],
                          ["--public-request-timeout", "nan"], ["--public-request-timeout", "46"]):
            with self.subTest(arguments=arguments), patch("sys.argv", ["worker", *arguments]), patch(
                "reputation_platform.worker.Repository",
            ) as repository, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main()
            repository.assert_not_called()
