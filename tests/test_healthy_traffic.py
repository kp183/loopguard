"""
Unit test verifying that healthy, diverse user traffic does not trigger false positives.
Evaluates 10 realistic eCommerce queries against difflib.SequenceMatcher.
Proves S_stagnant stays well below the 0.70/0.80 thresholds (expected ~0.28 - 0.35).
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

sys.path.insert(0, os.path.abspath("src"))

from orchestrator.app import compute_stagnation_ratio, compute_semantic_stagnation


class TestHealthyTrafficFalsePositives(unittest.TestCase):

    def test_varied_ecommerce_queries_do_not_trip_stagnation(self):
        """
        Simulates 10 normal user actions in an eCommerce checkout workflow.
        Verifies that legitimate, diverse queries maintain S_stagnant << 0.70.
        """
        healthy_queries = [
            "SELECT item_id, price FROM catalog WHERE category = 'electronics' LIMIT 20",
            "INSERT INTO customer_cart (cart_id, item_id, quantity) VALUES ('c-101', 'item-99', 1)",
            "SELECT promo_code, discount_pct FROM coupons WHERE code = 'FALL2026'",
            "UPDATE customer_cart SET discount_applied = 0.15 WHERE cart_id = 'c-101'",
            "SELECT address_line, postal_code FROM user_addresses WHERE user_id = 'usr-884'",
            "POST /v1/shipping/rates origin=94016 destination=98101 weight=1.4",
            "INSERT INTO checkout_sessions (session_id, total) VALUES ('sess-clean', 142.50)",
            "POST /v1/payments/authorize amount=14250 currency=USD token=tok_visa_4242",
            "UPDATE inventory SET stock = stock - 1 WHERE item_id = 'item-99'",
            "INSERT INTO audit_log (event, session_id) VALUES ('ORDER_PLACED', 'sess-clean')"
        ]

        ratio, is_stagnant = compute_stagnation_ratio(healthy_queries)
        is_stagnant_alias, ratio_alias = compute_semantic_stagnation(healthy_queries)

        print(f"\n[Healthy Traffic Test] Computed Ratio across 10 varied calls: {ratio} (stagnant={is_stagnant})")
        self.assertFalse(is_stagnant, "Healthy traffic was incorrectly flagged as stagnant!")
        self.assertFalse(is_stagnant_alias, "Alias flagged healthy traffic as stagnant!")
        self.assertEqual(ratio, ratio_alias)
        self.assertLess(ratio, 0.45, f"Expected ratio < 0.45, got {ratio}")


if __name__ == "__main__":
    unittest.main()
