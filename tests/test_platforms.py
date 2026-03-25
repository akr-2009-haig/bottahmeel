import unittest

from bot.utils.platforms import PLATFORMS, all_platforms, detect_platform, get_platform_info


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
