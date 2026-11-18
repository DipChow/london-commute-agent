import unittest
from unittest.mock import patch

from commute_agent.commute import discover, profile_key


class CommuterDiscoveryTests(unittest.TestCase):
    def test_address_only_profile_skips_bus_corridor_lookup(self):
        profile = {
            "id": "noah",
            "origin": {"address": "Example home", "stop_id": None},
            "interchange_search": None,
        }

        with patch(
            "commute_agent.commute.api.get_stop_details"
        ) as lookup:
            result = discover(profile)

        lookup.assert_not_called()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["coverage"], "saved_journeys_only")
        self.assertEqual(result["key"], profile_key(profile))

    def test_stop_without_interchange_skips_bus_corridor_lookup(self):
        profile = {
            "id": "noah",
            "origin": {"stop_id": "example_stop"},
            "interchange_search": None,
        }

        with patch(
            "commute_agent.commute.api.get_stop_details"
        ) as lookup:
            result = discover(profile)

        lookup.assert_not_called()
        self.assertEqual(result["coverage"], "saved_journeys_only")


if __name__ == "__main__":
    unittest.main()