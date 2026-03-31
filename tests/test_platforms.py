import unittest
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import patch

from bot.utils.platforms import (
    PLATFORM_OPTS,
    PLATFORMS,
    _apply_cookie_options,
    all_platforms,
    detect_platform,
    get_platform_info,
)


class PlatformSupportTests(unittest.TestCase):
    def test_new_platforms_are_registered_in_platform_system(self):
        self.assertIn("reddit", all_platforms())
        self.assertIn("google_drive", all_platforms())
        self.assertIn("linkedin", all_platforms())

    def test_detect_platform_supports_reddit_google_drive_and_linkedin_urls(self):
        cases = {
            "https://www.reddit.com/r/python/comments/abc123/example_post/": "reddit",
            "https://drive.google.com/file/d/abc123/view?usp=sharing": "google_drive",
            "https://www.linkedin.com/posts/example-company_demo-post-activity-1234567890-abcdef/": "linkedin",
        }
        for url, platform in cases.items():
            with self.subTest(url=url):
                detected_url, detected_platform = detect_platform(f"check this {url}")
                self.assertEqual(detected_url, url)
                self.assertEqual(detected_platform, platform)

    def test_detect_platform_supports_instagram_profile_urls(self):
        url = "https://www.instagram.com/film4.vibes/"
        detected_url, detected_platform = detect_platform(f"profile {url}")
        self.assertEqual(detected_url, url)
        self.assertEqual(detected_platform, "instagram")

    def test_new_platforms_use_admin_toggle_keys(self):
        self.assertEqual(get_platform_info("reddit")["db_key"], "reddit_enabled")
        self.assertEqual(get_platform_info("google_drive")["db_key"], "google_drive_enabled")
        self.assertEqual(get_platform_info("linkedin")["db_key"], "linkedin_enabled")
        self.assertFalse(PLATFORMS["google_drive"]["default_enabled"])
        self.assertFalse(PLATFORMS["linkedin"]["default_enabled"])

    def test_all_registered_platforms_have_explicit_download_formats(self):
        missing = sorted(platform for platform in all_platforms() if platform not in PLATFORM_OPTS)
        self.assertEqual(missing, [])

    def test_apply_cookie_options_uses_cookiefile_and_browser_profile(self):
        with NamedTemporaryFile() as cookie_file:
            opts = {}
            with patch("bot.utils.platforms.load_settings", return_value=SimpleNamespace(
                ytdlp_cookies_file=cookie_file.name,
                ytdlp_cookies_from_browser="firefox:default-release",
            )):
                _apply_cookie_options(opts)
            self.assertEqual(opts["cookiefile"], cookie_file.name)
            self.assertEqual(opts["cookiesfrombrowser"], ("firefox", "default-release"))
