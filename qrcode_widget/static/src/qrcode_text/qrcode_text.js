/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import * as BarcodeScanner from "@web/core/barcode/barcode_dialog";
import { CharField, charField } from "@web/views/fields/char/char_field";

export class QRCodeTextField extends CharField {
    static template = "qrcode_widget.QRCodeTextField";

    async scanQRCode() {
        const value = await BarcodeScanner.scanBarcode(this.env);
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
