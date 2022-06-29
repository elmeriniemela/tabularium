odoo.define('investment_portfolio.profit_widget', function (require) {
    "use strict";
    var widget = require('web.basic_fields');
    widget.NumericField.include({
        _render: function () {
            this._super();
            if (this.nodeOptions.is_profit) {
                if (this.value > 0) {
                    this.$el.addClass('text-success');
                    this.$el.removeClass('text-danger');
                } else if (this.value < 0) {
                    this.$el.addClass('text-danger');
                    this.$el.removeClass('text-success');
                } else {
                    this.$el.removeClass('text-success');
                    this.$el.removeClass('text-danger');
                }
            }
        }
    })
});
