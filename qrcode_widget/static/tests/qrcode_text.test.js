/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import {
    clickSave,
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import * as BarcodeScanner from "@web/core/barcode/barcode_dialog";
import "@qrcode_widget/qrcode_text/qrcode_text";

class QRCodeTest extends models.Model {
    _name = "qrcode.test";

    char_value = fields.Char();
    text_value = fields.Text();

    _records = [{ id: 1, char_value: "Initial", text_value: "Initial text" }];
}

defineModels([QRCodeTest]);

test("allows manual input", async () => {
    onRpc("qrcode.test", "web_save", ({ args }) => {
        expect(args[1].char_value).toBe("Manual value");
    });
    await mountView({
        type: "form",
        resModel: "qrcode.test",
        resId: 1,
        arch: '<form><field name="char_value" widget="qrcode_text"/></form>',
    });

    await contains('[name="char_value"] input').edit("Manual value");
    await clickSave();
});

test("scans into char and text fields", async () => {
    const values = ["Scanned char", "Scanned text"];
    patchWithCleanup(BarcodeScanner, {
        scanBarcode: async () => values.shift(),
    });
    await mountView({
        type: "form",
        resModel: "qrcode.test",
        resId: 1,
        arch: `
            <form>
                <field name="char_value" widget="qrcode_text"/>
                <field name="text_value" widget="qrcode_text"/>
            </form>`,
    });

    await contains('[name="char_value"] .o_qrcode_text_scan').click();
    expect('[name="char_value"] input').toHaveValue("Scanned char");
    await contains('[name="text_value"] .o_qrcode_text_scan').click();
    expect('[name="text_value"] input').toHaveValue("Scanned text");
});

test("keeps the current value when scanning returns no result", async () => {
    patchWithCleanup(BarcodeScanner, {
        scanBarcode: async () => false,
    });
    await mountView({
        type: "form",
        resModel: "qrcode.test",
        resId: 1,
        arch: '<form><field name="char_value" widget="qrcode_text"/></form>',
    });

    await contains(".o_qrcode_text_scan").click();
    expect('[name="char_value"] input').toHaveValue("Initial");
});
