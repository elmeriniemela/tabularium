/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component, markup, onWillStart } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { loadBundle } from "@web/core/assets";

export class DiffField extends Component {
    static template = "diff_widget.DiffField";
    static props = {
        ...standardFieldProps,
        maxLength: { type: Number, optional: true },
    };

    setup() {
        onWillStart(async () => {
            await loadBundle("diff_widget.diff2html");
        });
    }

    get formattedValue() {
        var value = this.props.record.data[this.props.name];
        if (!value) {
            return '';
        }
        if (this.props.maxLength && value.length > this.props.maxLength) {
            return markup(`<p>diff: maxLength ${this.props.maxLength} exceeded: ${value.length}</p>`);
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
        var diffHtml = Diff2Html.html(value, configuration);
        return markup(diffHtml);
    }
}

export const diffField = {
    component: DiffField,
    displayName: _t("Diff"),
    supportedTypes: ["text"],
    extractProps: ({ options }) => {
        return { maxLength: options.maxLength };
    },
};


registry.category("fields").add("diff", diffField);
