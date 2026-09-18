"""
LoopGuard Unit Tests: Module 3 Team-Based Alert Routing
Tests tag:GetResources resolution for Payments-Core, Infra-Core, unassigned, and API error fallback.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure src/orchestrator is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/orchestrator")))
sys.path.insert(0, os.path.abspath("src"))

import app


class TestTeamRouting(unittest.TestCase):

    def setUp(self):
        app.WEBHOOK_URL_PRIMARY = "https://discord.com/api/webhooks/payments-channel"
        app.WEBHOOK_URL_SECONDARY = "https://discord.com/api/webhooks/infra-channel"
        app.WEBHOOK_URL = "https://discord.com/api/webhooks/fallback-channel"
        app.AWS_ACCOUNT_ID = "740536073144"
        app.AWS_REGION = "us-east-1"

    @patch("app.tagging_client.get_resources")
    def test_payments_core_routing(self, mock_get_resources):
        mock_get_resources.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:lambda:us-east-1:740536073144:function:LoopGuard-TargetFunction",
                    "Tags": [{"Key": "Team", "Value": "Payments-Core"}]
                }
            ]
        }
        team, url = app.resolve_team_webhook("LoopGuard-TargetFunction")
        self.assertEqual(team, "Payments-Core")
        self.assertEqual(url, "https://discord.com/api/webhooks/payments-channel")

    @patch("app.tagging_client.get_resources")
    def test_infra_core_routing(self, mock_get_resources):
        mock_get_resources.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:lambda:us-east-1:740536073144:function:LoopGuard-TargetFunctionSecondary",
                    "Tags": [{"Key": "Team", "Value": "Infra-Core"}]
                }
            ]
        }
        team, url = app.resolve_team_webhook("LoopGuard-TargetFunctionSecondary")
        self.assertEqual(team, "Infra-Core")
        self.assertEqual(url, "https://discord.com/api/webhooks/infra-channel")

    @patch("app.tagging_client.get_resources")
    def test_unassigned_team_fallback(self, mock_get_resources):
        mock_get_resources.return_value = {"ResourceTagMappingList": []}
        team, url = app.resolve_team_webhook("LoopGuard-UntaggedFunction")
        self.assertEqual(team, "Unassigned")
        self.assertEqual(url, "https://discord.com/api/webhooks/payments-channel")

    @patch("app.tagging_client.get_resources")
    def test_api_exception_fallback(self, mock_get_resources):
        mock_get_resources.side_effect = Exception("AWS Resource Groups Tagging API Rate Exceeded")
        team, url = app.resolve_team_webhook("LoopGuard-TargetFunction")
        self.assertEqual(team, "Unassigned")
        self.assertEqual(url, "https://discord.com/api/webhooks/payments-channel")

    @patch("app.tagging_client.get_resources")
    def test_empty_primary_fallback_to_webhook_url(self, mock_get_resources):
        app.WEBHOOK_URL_PRIMARY = ""
        app.WEBHOOK_URL = "https://discord.com/api/webhooks/fallback-channel"
        mock_get_resources.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:lambda:us-east-1:740536073144:function:LoopGuard-TargetFunction",
                    "Tags": [{"Key": "Team", "Value": "Payments-Core"}]
                }
            ]
        }
        team, url = app.resolve_team_webhook("LoopGuard-TargetFunction")
        self.assertEqual(team, "Payments-Core")
        self.assertEqual(url, "https://discord.com/api/webhooks/fallback-channel")


if __name__ == "__main__":
    unittest.main()
