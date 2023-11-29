from typing import Callable, Iterable, Any
import json
from pathlib import Path
from itertools import groupby

import tensorflow as tf
import yaml
from django.conf import settings
from django.db.models import Max, Min
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render

from hackathon.models import Group, Submission


def get_encoded_categories() -> dict[int, tf.Tensor]:
    path = Path(settings.HACKATHON_DATA_DIR).resolve() / "dataset.yaml"
    with open(path, "r") as file:
        dataset = yaml.safe_load(file)

    # integer values of the categories
    category_indices = [key for key in dataset["names"]]
    one_hot_vectors = tf.one_hot(category_indices, len(category_indices))
    return {i: encoded for i, encoded in zip(category_indices, one_hot_vectors)}


def load_labels() -> dict[str, int]:
    labels = {}
    directory_path = Path(settings.HACKATHON_DATA_DIR).resolve() / "labels"

    for file_path in directory_path.iterdir():
        with open(file_path, "r") as file:
            # just first line is enough?
            line = file.readline()
            label_index = int(line.split()[0])
            # remove file extension
            labels[file_path.stem] = label_index
    return labels


def check_predictions_amount(predictions) -> None:
    labels_length = len(labels)
    predictions_length = len(predictions)
    if predictions_length != labels_length:
        raise ValueError(
            f"Length of the predictions list ({predictions_length}) and the actual "
            f"list ({labels_length}) are not equal"
        )


def get_best_results_grouped(
    results: Iterable[Any], max_groups: int, group_key: Callable[[Any], Any]
) -> list[Any]:
    """get up to max_results rows, group rows if the value in group_key is the same

    Args:
        results:
        max_groups:
        group_key: the key argument for itertools.groupby
    """
    groups = []
    for k, g in groupby(results, group_key):
        groups.append(list(g))

    limited_results = []
    for group_items in groups[:max_groups]:
        limited_results.extend(group_items)
    return limited_results


def process_predictions(
    predictions: dict[str, list[float]], group: Group
) -> JsonResponse:
    """calculate the quality of the predictions and save to db

    Args:
        predictions (dict[str, list[float]]):
        group (Group):

    Returns:
        JsonResponse: feedback or error
    """
    predictions = {Path(key).stem: value for key, value in predictions.items()}
    correct_predictions = 0
    y_true = []
    y_pred = []

    for file_name, label_index in labels.items():
        # category_vector = categories[label_index]
        # y_true.append(category_vector)
        # try:
        #     predicted_vector = predictions[file_name]
        #     y_pred.append(predicted_vector)
        # except KeyError as e:
        #     return JsonResponse(
        #         {
        #             "error": f"A prediction is missing for the file '{e.args[0]}(.jpg)'",
        #         },
        #         status=400,
        #     )

        # predicted_label_index = tf.math.argmax(predicted_vector)
        # if label_index == predicted_label_index:
        #     correct_predictions += 1

        category_vector = categories[label_index]
        predicted_vector = predictions.get(file_name)
        if predicted_vector:
            y_pred.append(predicted_vector)
            y_true.append(category_vector)

            predicted_label_index = tf.math.argmax(predicted_vector)
            if label_index == predicted_label_index:
                correct_predictions += 1

    # maybe calculate cce in the loop already for better error feedback?
    cce = tf.keras.losses.CategoricalCrossentropy()
    try:
        cce = cce(y_true, y_pred).numpy()
    except ValueError:
        # can I send the error message to user or could it leak info?
        return JsonResponse(
            {
                "error": "Failed to calculate the CCE. Make sure each file's prediction "
                "is a 1-dimensional list of floats",
            },
            status=400,
        )

    wrong_predictions = len(labels) - correct_predictions
    Submission.objects.create(
        group=group,
        right_predictions=correct_predictions,
        wrong_predictions=wrong_predictions,
        cce=cce,
    )

    return JsonResponse(
        {
            "message": f"Saved submission for group '{group.name}' with a CCE of {cce}, "
            f"{correct_predictions} classified correctly and {wrong_predictions} "
            "classified incorrectly."
        }
    )


# should this be passed as argument to functions that use it?
MAX_SUBMISSIONS_PER_GROUP = 4

categories = get_encoded_categories()
labels = load_labels()


# VIEWS
def index(request: HttpRequest):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            group_name = data["group"]
            predictions = data["predictions"]
        except KeyError as e:
            return JsonResponse(
                {
                    "error": f"Request is missing the parameter '{e.args[0]}'",
                },
                status=400,
            )
        except json.decoder.JSONDecodeError as e:
            return JsonResponse(
                {
                    "error": f"Failed to decode JSON: {e}",
                },
                status=400,
            )

        try:
            group = Group.objects.get(name__iexact=group_name)
            submissions_count = Submission.objects.filter(group=group).count()
        except Group.DoesNotExist:
            group = Group.objects.create(name=group_name)
            submissions_count = 0

        if submissions_count >= MAX_SUBMISSIONS_PER_GROUP:
            return JsonResponse(
                {
                    "error": f"Only {MAX_SUBMISSIONS_PER_GROUP} per group are allowed and "
                    f"group '{group.name} already submitted {submissions_count} time(s)'",
                },
                status=400,  # maybe a different status is better
            )

        # try:
        #     check_predictions_amount(predictions)
        # except ValueError as e:
        #     return JsonResponse({"error": str(e)}, status=400)

        response = process_predictions(predictions, group)
        return response
    elif request.method == "GET":
        # how many different rows (groups) should be shown in the table
        MAX_RESULTS_SHOWN = 3

        # maybe limit display of floats to n decimals
        # should the cce's display be "grouped" too?
        best_cce_predictions = (
            Submission.objects.values("group", "group__name")
            .annotate(min_cce=Min("cce"))
            .order_by("min_cce")[:MAX_RESULTS_SHOWN]
        )

        # for predictions where the correct category has highest probability
        most_right_predictions = (
            Submission.objects.values("group", "group__name")
            .annotate(max_right=Max("right_predictions"))
            .order_by("-max_right")
        )
        most_right_predictions = get_best_results_grouped(
            most_right_predictions, MAX_RESULTS_SHOWN, lambda x: x["max_right"]
        )

        context = {
            "best_cce": best_cce_predictions,
            "best_choices": most_right_predictions,
        }
        return render(request, "hackathon/index.html", context)
