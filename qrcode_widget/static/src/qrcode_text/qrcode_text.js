/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { TextField, textField } from "@web/views/fields/text/text_field";
import * as QRCodeScanner from "./qrcode_scanner";

export class QRCodeTextField extends TextField {
    static template = "qrcode_widget.QRCodeTextField";

    async scanQRCode() {
        const value = await QRCodeScanner.scanQRCode(this.env);
        if (value) {
            await this.props.record.update({ [this.props.name]: value });
        }
    }
}

export const qrcodeTextField = {
    ...textField,
    component: QRCodeTextField,
    displayName: _t("QR Code Text"),
    supportedTypes: ["char", "text"],
};

registry.category("fields").add("qrcode_text", qrcodeTextField);
