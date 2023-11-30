"""Routes."""

from django.urls import path

from moonmining.views import extractions, moons, reports

from .views import general

app_name = "moonmining"

urlpatterns = [
    # general
    path("", general.index, name="index"),
    path("add_owner", general.add_owner, name="add_owner"),
    path("modal_loader_body", general.modal_loader_body, name="modal_loader_body"),
    path("tests", general.tests, name="tests"),
    # extractions
    path("extractions", extractions.extractions, name="extractions"),
    path(
        "extractions_data/<str:category>",
        extractions.extractions_data,
        name="extractions_data",
    ),
    path(
        "extraction/<int:extraction_pk>",
        extractions.extraction_details,
        name="extraction_details",
    ),
    path(
        "extraction_ledger/<int:extraction_pk>",
        extractions.extraction_ledger,
        name="extraction_ledger",
    ),
    # moons
    path("moons", moons.moons, name="moons"),
    path("upload_survey", moons.upload_survey, name="upload_survey"),
    path(
        "moons_data/<str:category>",
        moons.MoonListJson.as_view(),
        name="moons_data",
    ),
    path(
        "moons_fdd_data/<str:category>",
        moons.moons_fdd_data,
        name="moons_fdd_data",
    ),
    path("moon/<int:moon_pk>", moons.moon_details, name="moon_details"),
    # reports
    path("reports", reports.reports, name="reports"),
    path(
        "report_owned_value_data",
        reports.report_owned_value_data,
        name="report_owned_value_data",
    ),
    path(
        "report_user_mining_data",
        reports.report_user_mining_data,
        name="report_user_mining_data",
    ),
    path(
        "report_user_uploaded_data",
        reports.report_user_uploaded_data,
        name="report_user_uploaded_data",
    ),
    path(
        "report_ore_prices_data",
        reports.report_ore_prices_data,
        name="report_ore_prices_data",
    ),
]
