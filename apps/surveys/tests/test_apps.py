""" Tests for surveys app config. """

from apps.surveys.apps import SurveysConfig


def test_surveys_app_config():
    assert SurveysConfig.name == "apps.surveys"
