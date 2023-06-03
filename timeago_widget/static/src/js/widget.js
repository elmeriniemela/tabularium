/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component, onWillStart } from "@odoo/owl";
export class TimeagoField extends Component {

    setup() {
        // onWillStart(async () => {
        //     await loadJS("/timeago_widget/static/src/lib/jquery.timeago.js");
        // });
    }
    get isoValue() {
        var date = new Date(this.props.value);
        return date.toISOString()
    }

    get formattedValue() {
        jQuery.timeago.settings.allowFuture = true;
        var date = new Date(this.props.value);
        return jQuery.timeago(date)
    }
}
TimeagoField.template = "timeago_widget.TimeagoField";
TimeagoField.displayName = _lt("Timeago");
registry.category("fields").add("timeago", TimeagoField);
