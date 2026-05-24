"""SYSTEM_CONTRACT campaign validation gate."""

import json
import unittest
from pathlib import Path

from src.trading.competition.replay.validation_contract import (
    CANONICAL_IN_PROGRESS_CAMPAIGN,
    STATUS_DEVELOPMENT_ONLY,
    STATUS_FORMAL,
    default_development_validation_record,
    is_formal_strategy_performance,
    load_campaign_validation_status,
    merge_validation_into_meta,
    validation_status_path,
)


class TestValidationContract(unittest.TestCase):
    def test_canonical_campaign_is_development_only(self):
        v = load_campaign_validation_status(CANONICAL_IN_PROGRESS_CAMPAIGN)
        self.assertEqual(v["performanceStatus"], STATUS_DEVELOPMENT_ONLY)
        self.assertFalse(v["formalStrategyPerformanceAllowed"])
        self.assertFalse(is_formal_strategy_performance(CANONICAL_IN_PROGRESS_CAMPAIGN))
        ids = {item["id"] for item in v["unverifiedItems"]}
        self.assertIn("C_SUPPLY_HISTORICAL", ids)
        self.assertIn("UNIVERSE_AS_OF_DATE", ids)
        self.assertIn("RISK_AS_OF_DATE", ids)

    def test_docs_validation_status_file_exists(self):
        path = validation_status_path(CANONICAL_IN_PROGRESS_CAMPAIGN)
        self.assertTrue(path.is_file(), str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["performanceStatus"], STATUS_DEVELOPMENT_ONLY)

    def test_merge_validation_into_meta(self):
        meta = merge_validation_into_meta({"campaignId": CANONICAL_IN_PROGRESS_CAMPAIGN}, CANONICAL_IN_PROGRESS_CAMPAIGN)
        self.assertEqual(meta["performanceStatus"], STATUS_DEVELOPMENT_ONLY)
        self.assertFalse(meta["formalStrategyPerformanceAllowed"])
        self.assertIn("C_SUPPLY_HISTORICAL", meta["unverifiedItemIds"])

    def test_unknown_campaign_defaults_formal(self):
        v = load_campaign_validation_status("month_20990101_20990131_unknown")
        self.assertEqual(v["performanceStatus"], STATUS_FORMAL)
        self.assertTrue(v["formalStrategyPerformanceAllowed"])

    def test_default_record_has_three_items(self):
        rec = default_development_validation_record(CANONICAL_IN_PROGRESS_CAMPAIGN)
        self.assertEqual(len(rec["unverifiedItems"]), 3)


if __name__ == "__main__":
    unittest.main()
