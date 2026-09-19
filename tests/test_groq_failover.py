"""
Unit tests verifying the Multi-Cloud Resilient Diagnostic Cascade in LoopGuard Orchestrator:
Tier 1: Amazon Bedrock (Primary)
Tier 2: Groq Llama 3.3 70B (Active Failover)
Tier 3: Deterministic Fallback Engine (Backstop)
"""

import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch

# Mock boto3 and botocore if not installed locally
if "boto3" not in sys.modules:
    mock_boto3 = MagicMock()
    mock_botocore = MagicMock()
    sys.modules["boto3"] = mock_boto3
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.exceptions"] = mock_botocore.exceptions
    mock_botocore.exceptions.ClientError = Exception

sys.path.insert(0, os.path.abspath("src"))

import orchestrator.app as orchestrator_app
from orchestrator.app import (
    DiagnosticResult,
    generate_fallback_diagnostic,
    invoke_bedrock_diagnostic,
    invoke_groq_diagnostic,
    invoke_groq_rca
)


class TestGroqFailoverCascade(unittest.TestCase):

    def setUp(self):
        self.function_name = "LoopGuard-TargetFunction"
        self.stagnation_ratio = 0.876
        self.is_stagnant = True
        self.logs = [
            '{"session_id": "sess-test", "query_payload": "SELECT 1 FROM orders WHERE id=10"}',
            '{"session_id": "sess-test", "query_payload": "SELECT 1 FROM orders WHERE id=10"}'
        ]

    def test_tier3_deterministic_fallback_schema(self):
        """Verify Tier 3 deterministic fallback returns complete schema."""
        diag = generate_fallback_diagnostic(
            function_name=self.function_name,
            stagnation_ratio=self.stagnation_ratio,
            is_stagnant=self.is_stagnant
        )
        self.assertIsInstance(diag, DiagnosticResult)
        self.assertIn("LoopGuard-TargetFunction", diag.root_cause_summary)
        self.assertEqual(diag.detected_pattern, "SEMANTIC_RETRY_STAGNATION")
        self.assertIn("invocations/min", diag.estimated_burn_rate)
        self.assertTrue(len(diag.recommended_action) > 10)

    @patch.object(orchestrator_app, "GROQ_API_KEY", "gsk_dummy_test_key_12345")
    @patch("urllib.request.urlopen")
    def test_tier2_groq_success(self, mock_urlopen):
        """Verify Tier 2 Groq succeeds with valid JSON from Llama-3.3-70B."""
        mock_response = MagicMock()
        mock_response.status = 200
        groq_body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "root_cause_summary": "Database connection deadlock caused repeated retry loop.",
                            "detected_pattern": "SEMANTIC_RETRY_STAGNATION",
                            "estimated_burn_rate": "$0.45/min (60 invocations/min)",
                            "recommended_action": "Apply surgical session lock to isolate rogue agent session."
                        })
                    }
                }
            ]
        }
        mock_response.read.return_value = json.dumps(groq_body).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        diag = invoke_groq_diagnostic(
            function_name=self.function_name,
            stagnation_ratio=self.stagnation_ratio,
            is_stagnant=self.is_stagnant,
            recent_logs=self.logs
        )
        self.assertIsNotNone(diag)
        self.assertIn("deadlock", diag.root_cause_summary)
        self.assertEqual(diag.detected_pattern, "SEMANTIC_RETRY_STAGNATION")

        # Test alias invoke_groq_rca
        diag_alias = invoke_groq_rca("\n".join(self.logs), self.stagnation_ratio)
        self.assertIsNotNone(diag_alias)
        self.assertEqual(diag_alias.detected_pattern, "SEMANTIC_RETRY_STAGNATION")

    @patch.object(orchestrator_app, "GROQ_API_KEY", "gsk_dummy_test_key_12345")
    @patch("urllib.request.urlopen")
    def test_tier2_groq_failure_returns_none_cleanly(self, mock_urlopen):
        """Verify Tier 2 Groq failure (e.g. HTTP 500 or timeout) degrades gracefully without throwing."""
        mock_urlopen.side_effect = Exception("Cloudflare 403 Forbidden or Timeout")

        diag = invoke_groq_diagnostic(
            function_name=self.function_name,
            stagnation_ratio=self.stagnation_ratio,
            is_stagnant=self.is_stagnant,
            recent_logs=self.logs
        )
        self.assertIsNone(diag)

    def test_tier2_groq_without_key_returns_none(self):
        """Verify invoke_groq_diagnostic returns None if GROQ_API_KEY is unset."""
        with patch.object(orchestrator_app, "GROQ_API_KEY", ""):
            diag = invoke_groq_diagnostic(
                function_name=self.function_name,
                stagnation_ratio=self.stagnation_ratio,
                is_stagnant=self.is_stagnant,
                recent_logs=self.logs
            )
            self.assertIsNone(diag)


if __name__ == "__main__":
    unittest.main()
