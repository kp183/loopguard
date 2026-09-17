"""
LoopGuard Verification & Audit Unit Tests
Tests dimension extraction, recursive JSON unwrapping, difflib stagnation scoring,
and HMAC signature verification across orchestrator and remediation modules.
Uses sys.modules mocking for boto3/botocore when running in test environments without AWS SDK.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Mock boto3 and botocore if not installed locally
if "boto3" not in sys.modules:
    mock_boto3 = MagicMock()
    mock_botocore = MagicMock()
    sys.modules["boto3"] = mock_boto3
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.exceptions"] = mock_botocore.exceptions
    mock_botocore.exceptions.ClientError = Exception

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath("src"))

from orchestrator.app import (
    extract_target_function_name,
    unwrap_log_message,
    compute_stagnation_ratio,
    generate_hmac_token,
)
from remediation.app import verify_hmac_token


class TestLoopGuardDefensiveMechanisms(unittest.TestCase):

    def test_dimension_parsing_dict(self):
        event = {
            "detail": {
                "dimensions": {"FunctionName": "LoopGuard-TargetFunction"}
            }
        }
        self.assertEqual(extract_target_function_name(event), "LoopGuard-TargetFunction")

    def test_dimension_parsing_list(self):
        event = {
            "detail": {
                "dimensions": [
                    {"name": "InstanceId", "value": "i-12345"},
                    {"name": "FunctionName", "value": "LoopGuard-CustomTarget"}
                ]
            }
        }
        self.assertEqual(extract_target_function_name(event), "LoopGuard-CustomTarget")

    def test_dimension_parsing_configuration_metrics(self):
        event = {
            "detail": {
                "configuration": {
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {
                                    "dimensions": [
                                        {"name": "FunctionName", "value": "LoopGuard-DeepMetricTarget"}
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
        self.assertEqual(extract_target_function_name(event), "LoopGuard-DeepMetricTarget")

    def test_unwrap_log_message_raw(self):
        raw = '{"session_id": "sess-1", "query_payload": "SELECT 1"}'
        data, _ = unwrap_log_message(raw)
        self.assertIsNotNone(data)
        self.assertEqual(data.get("session_id"), "sess-1")
        self.assertEqual(data.get("query_payload"), "SELECT 1")

    def test_unwrap_log_message_nested_json_envelope(self):
        # Lambda LoggingConfig: LogFormat: JSON creates an outer envelope
        envelope = '{"timestamp": 1726589000, "level": "INFO", "message": "{\\"session_id\\": \\"sess-nested\\", \\"query_payload\\": \\"SELECT balance FROM users WHERE id = 10\\"}"}'
        data, _ = unwrap_log_message(envelope)
        self.assertIsNotNone(data)
        self.assertEqual(data.get("session_id"), "sess-nested")
        self.assertIn("SELECT balance", data.get("query_payload", ""))

    def test_stagnation_ratio_high_similarity(self):
        queries = [
            "SELECT account_id, balance, risk_score FROM ledger_transactions WHERE status = 'pending_verification' ORDER BY created_at DESC LIMIT 10",
            "SELECT account_id, balance, risk_score FROM ledger_transactions WHERE status = 'pending_verification' AND retry_counter = 1 ORDER BY created_at DESC LIMIT 10",
            "SELECT account_id, balance, risk_score FROM ledger_transactions WHERE status = 'pending_verification' AND retry_counter = 2 ORDER BY created_at DESC LIMIT 10"
        ]
        ratio, is_stagnant = compute_stagnation_ratio(queries)
        self.assertGreaterEqual(ratio, 0.70)
        self.assertTrue(is_stagnant)

    def test_stagnation_ratio_divergent_queries(self):
        queries = [
            "SELECT account_id FROM accounts",
            "DELETE FROM temporary_tokens WHERE expired = true",
            "UPDATE system_status SET operational = true"
        ]
        ratio, is_stagnant = compute_stagnation_ratio(queries)
        self.assertLess(ratio, 0.70)
        self.assertFalse(is_stagnant)

    def test_hmac_token_generation_and_validation(self):
        secret = "MyTestSecretKey123"
        msg = "INC-12345:session:sess-live-01"
        token = generate_hmac_token(secret, msg)
        self.assertTrue(verify_hmac_token(secret, token, msg))
        self.assertFalse(verify_hmac_token(secret, "tampered_token", msg))
        self.assertFalse(verify_hmac_token(secret, token, "INC-12345:global:LoopGuard-TargetFunction"))


if __name__ == "__main__":
    unittest.main()
