/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import * as QRCodeScanner from "./qrcode_scanner";

export class QRCodeTextField extends CharField {
    static template = "qrcode_widget.QRCodeTextField";

    async scanQRCode() {
        const value = await QRCodeScanner.scanQRCode(this.env);
        if (value) {
            await this.props.record.update({ [this.props.name]: value });
        }
    }
}

export const qrcodeTextField = {
    ...charField,
    component: QRCodeTextField,
    displayName: _t("QR Code Text"),
};

registry.category("fields").add("qrcode_text", qrcodeTextField);
