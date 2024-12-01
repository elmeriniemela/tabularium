/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
export class TimeagoField extends Component {
    static template = "timeago_widget.TimeagoField";

    get isoValue() {
        var date = new Date(this.props.record.data[this.props.name]);
        return date.toISOString()
    }

    get formattedValue() {
        jQuery.timeago.settings.allowFuture = true;
        var date = new Date(this.props.record.data[this.props.name]);
        return jQuery.timeago(date)
    }
}

export const timeagoField = {
    component: TimeagoField,
    displayName: _t("Timeago"),
    supportedTypes: ["datetime"],
    isEmpty: () => false,
};

registry.category("fields").add("timeago", timeagoField);
