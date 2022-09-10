odoo.define('timeago_widget.timeago_widget', function (require) {
    "use strict";

    var fieldRegistry = require('web.field_registry');
    var AbstractField = require('web.AbstractField');
    var core = require('web.core');
    var session = require('web.session');

    var _lt = core._lt;

    const FieldTimeago = AbstractField.extend({
        description: _lt("Timeago"),
        supportedFieldTypes: ['datetime'],
        template: 'FieldTimeago',
        jsLibs: [
            '/timeago_widget/static/src/lib/jquery.timeago.js',
        ],
        _getValue: function () {
            return this.$('time.timeago').attr('datetime');
        },
        _onChange: function () {
            if (!this.$silent) {
                if (this.mode === 'edit' && this.$('input').val() !== '') {
                    this._setValue(this._getValue());
                }
            }
        },
        _render: function () {
            var $timeago = this.$('time.timeago');
            var date = new Date(this.value);
            $timeago.attr("datetime", date.toISOString());
            $timeago.html(jQuery.timeago(date));
            $timeago.attr("disabled", this.mode === 'readonly');


            const nowUTC = moment().utc();
            const nowUserTZ = nowUTC.clone().add(session.getTZOffset(nowUTC), 'minutes');
            const fieldValue = this.value.clone().add(session.getTZOffset(this.value), 'minutes');
            const diffMins = fieldValue.diff(nowUserTZ, 'minutes')
            // this.$el.toggleClass('font-weight-bold', diffMins <= 0);
            this.$el.toggleClass('text-danger', diffMins < -(2*24*60));
            this.$el.toggleClass('text-warning', diffMins <= -15);
            this.$el.toggleClass('text-success', diffMins > -15);
        },
    });

    fieldRegistry.add('timeago', FieldTimeago);
});
