import datetime as dt
import json

from django.core.cache import cache
from django.http import JsonResponse
from django.test import TestCase

from app_utils.testing import response_text


def json_response_to_python_2(response: JsonResponse, data_key="data") -> object:
    """Convert JSON response into Python object."""
    data = json.loads(response_text(response))
    return data[data_key]


def json_response_to_dict_2(response: JsonResponse, key="id", data_key="data") -> dict:
    """Convert JSON response into dict by given key."""
    return {x[key]: x for x in json_response_to_python_2(response, data_key)}


def datetime_to_ldap(my_dt: dt.datetime) -> int:
    """datetime.datetime to ldap"""
    return (
        ((my_dt - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).total_seconds())
        + 11644473600
    ) * 10000000


class TestCaseWithClearCache(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cache.clear()
