/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component, onWillStart, markup } from "@odoo/owl";

export class DiffField extends Component {

    setup() {
    }

    get formattedValue() {
        var configuration = {
            drawFileList: true,
            fileListToggle: false,
            fileListStartVisible: false,
            fileContentToggle: false,
            matching: 'lines',
            outputFormat: 'side-by-side',
            synchronisedScroll: true,
            highlight: true,
            renderNothingWhenEmpty: false,
        };
        if (this.props.value) {
            var diffHtml = Diff2Html.html(this.props.value, configuration);
            return markup(diffHtml);
        } else {
            return '';
        }
    }
}
DiffField.template = "diff_widget.DiffField";
DiffField.displayName = _lt("Diff");
registry.category("fields").add("diff", DiffField);
