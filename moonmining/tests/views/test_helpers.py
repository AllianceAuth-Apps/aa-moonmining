from typing import NamedTuple

from django.test import TestCase

from app_utils.views import BootstrapStyleBS5

from moonmining.views._helpers import fontawesome_modal_button_html


class TestFontawesomeModalButtonHtml(TestCase):
    def test_all(self):
        class Case(NamedTuple):
            name: str
            want: str
            ajax_url: str = None
            tooltip: str = None
            style: BootstrapStyleBS5 = None

        cases = [
            Case(
                "default",
                want='<button type="button" class="btn btn-secondary" data-bs-toggle="modal" data-bs-target="#modalExample" ><i class="fas fa-hammer"></i></button>',
            ),
            Case(
                "ajax url",
                ajax_url="/example/my-view",
                want='<button type="button" class="btn btn-secondary" data-ajax_url="/example/my-view" data-bs-toggle="modal" data-bs-target="#modalExample" ><i class="fas fa-hammer"></i></button>',
            ),
            Case(
                "tooltip",
                tooltip="this is a tooltip",
                want='<button type="button" class="btn btn-secondary" data-bs-toggle="modal" title="this is a tooltip" data-bs-target="#modalExample" ><i class="fas fa-hammer"></i></button>',
            ),
            Case(
                "style",
                style=BootstrapStyleBS5.DANGER,
                want='<button type="button" class="btn btn-danger" data-bs-toggle="modal" data-bs-target="#modalExample" ><i class="fas fa-hammer"></i></button>',
            ),
            Case(
                "all features",
                ajax_url="/example/my-view",
                style=BootstrapStyleBS5.DANGER,
                tooltip="this is a tooltip",
                want='<button type="button" class="btn btn-danger" data-ajax_url="/example/my-view"  data-bs-toggle="modal" title="this is a tooltip" data-bs-target="#modalExample" ><i class="fas fa-hammer"></i></button>',
            ),
        ]

        for tc in cases:
            params = {
                "modal_id": "modalExample",
                "fa_code": "fas fa-hammer",
            }
            if tc.ajax_url:
                params["ajax_url"] = tc.ajax_url
            if tc.tooltip:
                params["tooltip"] = tc.tooltip
            if tc.style:
                params["style"] = tc.style

            got = fontawesome_modal_button_html(**params)
            self.assertHTMLEqual(got, tc.want, msg=tc.name)
