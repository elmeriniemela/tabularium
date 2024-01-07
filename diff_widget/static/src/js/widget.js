/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component, markup } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class DiffField extends Component {

    setup() {
    }

    get formattedValue() {
        if (!this.props.value) {
            return '';
        }
        if (this.props.maxLength && this.props.value.length > this.props.maxLength) {
            return markup(`<p>diff: maxLength ${this.props.maxLength} exceeded: ${this.props.value.length}</p>`);
        }
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
            diffMaxChanges: 500,
            diffMaxLineLength: 500,
            diffTooBigMessage: "Diff is too big to show.",
        };
        var diffHtml = Diff2Html.html(this.props.value, configuration);
        return markup(diffHtml);
    }
}
DiffField.template = "diff_widget.DiffField";
DiffField.displayName = _lt("Diff");
DiffField.supportedTypes = ["text"];
DiffField.props = {
    ...standardFieldProps,
    maxLength: { type: Number, optional: true },
};

DiffField.extractProps = ({ attrs }) => {
    return {
        maxLength: attrs.options.maxLength,
    };
};
registry.category("fields").add("diff", DiffField);
