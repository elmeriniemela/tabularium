/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class TimeagoField extends Component {
    static template = "timeago_widget.TimeagoField";
    static props = { ...standardFieldProps };

    setup() {
        this.settings = {
            allowPast: true,
            allowFuture: true,
            strings: {
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
            }
        }
    }

    inWords(distanceMillis) {
        if (!this.settings.allowPast && !this.settings.allowFuture) {
            throw 'timeago allowPast and allowFuture settings can not both be set to false.';
        }

        var $l = this.settings.strings;
        var prefix = $l.prefixAgo;
        var suffix = $l.suffixAgo;
        if (this.settings.allowFuture) {
            if (distanceMillis < 0) {
                prefix = $l.prefixFromNow;
                suffix = $l.suffixFromNow;
            }
        }

        if (!this.settings.allowPast && distanceMillis >= 0) {
            return this.settings.strings.inPast;
        }

        var seconds = Math.abs(distanceMillis) / 1000;
        var minutes = seconds / 60;
        var hours = minutes / 60;
        var days = hours / 24;
        var years = days / 365;


        function isFunction(func) {
            return typeof func === "function";
        };

        function substitute(stringOrFunction, number) {
            var string = isFunction(stringOrFunction) ? stringOrFunction(number, distanceMillis) : stringOrFunction;
            var value = ($l.numbers && $l.numbers[number]) || number;
            return string.replace(/%d/i, value);
        }

        var words = seconds < 45 && substitute($l.seconds, Math.round(seconds)) ||
            seconds < 90 && substitute($l.minute, 1) ||
            minutes < 45 && substitute($l.minutes, Math.round(minutes)) ||
            minutes < 90 && substitute($l.hour, 1) ||
            hours < 24 && substitute($l.hours, Math.round(hours)) ||
            hours < 42 && substitute($l.day, 1) ||
            days < 30 && substitute($l.days, Math.round(days)) ||
            days < 45 && substitute($l.month, 1) ||
            days < 365 && substitute($l.months, Math.round(days / 30)) ||
            years < 1.5 && substitute($l.year, 1) ||
            substitute($l.years, Math.round(years));

        var separator = $l.wordSeparator || "";
        if ($l.wordSeparator === undefined) { separator = " "; }
        return [prefix, words, suffix].join(separator).trim();
    }

    get isoValue() {
        var date = new Date(this.props.record.data[this.props.name]);
        return date.toISOString()
    }

    get formattedValue() {
        var date = new Date(this.props.record.data[this.props.name]);
        function distance(date) {
            return (new Date().getTime() - date.getTime());
        };
        return this.inWords(distance(date));
    }
}

export const timeagoField = {
    component: TimeagoField,
    displayName: _t("Timeago"),
    supportedTypes: ["datetime"],
    isEmpty: () => false,
};

registry.category("fields").add("timeago", timeagoField);
