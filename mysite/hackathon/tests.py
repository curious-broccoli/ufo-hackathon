import json
from typing import Any
from unittest.mock import patch

from django.http import JsonResponse
from django.test import TestCase

from hackathon.models import Group, Submission
from hackathon.views import categories


def get_response_error_message(input: JsonResponse | dict[str, Any]):
    if isinstance(input, JsonResponse):
        return json.loads(input.content)["error"]
    return input["error"]


def pad_list(to_pad: list[float], new_length: int = len(categories)):
    """pad with .0s for one-hot encoded arrays"""
    difference = new_length - len(to_pad)
    return to_pad + [0.0] * difference


class SubmitTestCase(TestCase):
    @patch("hackathon.views.MAX_SUBMISSIONS_PER_GROUP", 2)
    def test_too_many_submissions(self):
        group = Group.objects.create(name="foxes")
        Submission(
            group=group, right_predictions=7, wrong_predictions=3, cce=0.2
        ).save()
        Submission(
            group=group, right_predictions=4, wrong_predictions=6, cce=1.2
        ).save()

        data = {
            "group": group.name,
            "predictions": {
                "123.jpg": [0.19, 0.01],
                "456.jpg": [0.1, 0.1],
            },
        }
        response = self.client.post(
            "", json.dumps(data), content_type="application/json"
        )
        self.assertEqual(400, response.status_code)
        error = get_response_error_message(response)
        self.assertIn("2", error)
        self.assertIn("allowed", error)

    def test_proper(self):
        data = {
            "group": "abc",
            "predictions": {
                "0a2e4d3aae53cb9363f2fec08f934069.jpg": pad_list(
                    [0.19, 0.01, 0.3, 0.5]
                ),
                "0a4e61b5-efc8-44e8-9a82-65dbba7280ef.jpg": pad_list(
                    [0.1, 0.6, 0.1, 0.2]
                ),
            },
        }
        response = self.client.post(
            "", json.dumps(data), content_type="application/json"
        )
        print(json.loads(response.content))
        # TODO test number of correct and total predictions, response

    # can I test with mocked labels and categories files?
    # e.g., if DEBUG, load different files
