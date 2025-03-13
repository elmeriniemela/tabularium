/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class TimeagoField extends Component {
    static template = "timeago_widget.TimeagoField";
    static props = { ...standardFieldProps };

    setup() {
        jQuery.timeago.settings.strings = {
            prefixAgo: null,
            prefixFromNow: null,
            suffixAgo: "",
            suffixFromNow: "",
            seconds: "1m",
            minute: "1m",
            minutes: "%dm",
            hour: "1h",
            hours: "%dh",
            day: "1d",
            days: "%dd",
            month: "1mo",
            months: "%dmo",
            year: "1yr",
            years: "%dyr",
            wordSeparator: " ",
            numbers: []
        };
    }

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
