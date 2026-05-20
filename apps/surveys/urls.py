"""URLs for surveys app"""

from django.urls import path

from . import views

app_name = "surveys"

urlpatterns = [
    path("", views.survey_list, name="list"),
    path("s/<slug:slug>/", views.survey_intro, name="intro"),
    path("s/<slug:slug>/start/", views.start_survey, name="start"),
    path("s/<slug:slug>/step/<int:step>/", views.step, name="step"),
    path("s/<slug:slug>/step/<int:step>/back/", views.step_back, name="step_back"),
    path("s/<slug:slug>/resume/<str:token>/", views.resume, name="resume"),
    path("s/<slug:slug>/done/", views.done, name="done"),
    path("s/<slug:slug>/preview/", views.preview, name="preview"),
    path("s/<slug:slug>/preview/step/<int:step>/", views.preview_step, name="preview_step"),
    path(
        "s/<slug:slug>/preview/step/<int:step>/back/",
        views.preview_step_back,
        name="preview_step_back",
    ),
    path("admin-results/<int:survey_id>/", views.results_dashboard, name="results"),
    path("admin-results/<int:survey_id>/raw/", views.results_raw, name="results_raw"),
    path("admin-results/<int:survey_id>/export.csv", views.export_csv, name="export_csv"),
    path("admin-results/<int:survey_id>/export.json", views.export_json, name="export_json"),
]
