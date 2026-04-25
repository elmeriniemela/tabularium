# -*- coding: utf-8 -*-

import odoo.tests
from werkzeug.urls import url_quote_plus


def unit_test_error_checker(message): # pragma: no cover
    return "[HOOT]" not in message


@odoo.tests.tagged("post_install", "-at_install")
class TestChartWidgetJS(odoo.tests.HttpCase):
    @odoo.tests.no_retry
    def test_unit_desktop(self):
        self.browser_js(
            f"/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&filter={url_quote_plus('@chart_widget/')}",
            "",
            "",
            login="admin",
            timeout=3600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )
