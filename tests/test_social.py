import unittest

from grid_agent_social import _is_missing_parent


class SocialReplyTests(unittest.TestCase):
    def test_missing_parent_404_is_permanent(self):
        result = (
            'Error (404): {"statusCode": 404, "message": "Parent comment not '
            'found", "path": "/api/v1/posts/x/comments"}'
        )
        self.assertTrue(_is_missing_parent(result))

    def test_unrelated_404_is_not_a_missing_parent(self):
        self.assertFalse(_is_missing_parent('Error (404): post not found'))

    def test_success_is_not_a_missing_parent(self):
        self.assertFalse(_is_missing_parent('{"success":true}'))


if __name__ == "__main__":
    unittest.main()
