import importlib
import os
import unittest
from unittest import mock


class BotConfigTests(unittest.TestCase):
    def reload_bot(self, env):
        with mock.patch.dict(os.environ, env, clear=True):
            import bot

            return importlib.reload(bot)

    def test_empty_action_vars_fall_back_to_defaults(self):
        bot = self.reload_bot(
            {
                "PARTY_SIZE": "5",
                "EARLIEST_HOUR": "",
                "LATEST_HOUR": "",
                "TARGET_DAYS": "Saturday,Sunday",
                "PREFERRED_TIMES": "",
            }
        )

        self.assertEqual(bot.PARTY_SIZE, 5)
        self.assertEqual(bot.EARLIEST_HOUR, 17)
        self.assertEqual(bot.LATEST_HOUR, 19)
        self.assertEqual(bot.TARGET_DAYS, {"Saturday", "Sunday"})
        self.assertEqual(bot.PREFERRED_TIMES, ["1700", "1730", "1800", "1830", "1900"])
        self.assertFalse(bot.FAIL_ON_NO_SLOT)

    def test_latest_hour_includes_exact_boundary(self):
        bot = self.reload_bot({})

        self.assertTrue(bot.is_preferred_time("5:00 pm"))
        self.assertTrue(bot.is_preferred_time("7:00 pm"))
        self.assertFalse(bot.is_preferred_time("7:30 pm"))

    def test_fail_on_no_slot_parses_boolean_values(self):
        bot = self.reload_bot({"FAIL_ON_NO_SLOT": "yes"})

        self.assertTrue(bot.FAIL_ON_NO_SLOT)


if __name__ == "__main__":
    unittest.main()
