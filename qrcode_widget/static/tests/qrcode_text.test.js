/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import { animationFrame, manuallyDispatchProgrammaticEvent, queryOne } from "@odoo/hoot-dom";
import {
    clickSave,
    contains,
    defineModels,
    fields,
    mountWithCleanup,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import * as QRCodeScanner from "@qrcode_widget/qrcode_text/qrcode_scanner";
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
    patchWithCleanup(QRCodeScanner, {
        scanQRCode: async () => values.shift(),
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
    patchWithCleanup(QRCodeScanner, {
        scanQRCode: async () => false,
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

test("requests a 1080p camera stream and scans QR codes", async () => {
    patchWithCleanup(browser.navigator, {
        mediaDevices: {
            async getUserMedia(constraints) {
                expect.step(JSON.stringify(constraints));
                const stream = document.createElement("canvas").captureStream();
                stream.getTracks()[0].stop = () => expect.step("camera stopped");
                return stream;
            },
        },
    });
    patchWithCleanup(window, {
        BarcodeDetector: class {
            constructor(options) {
                expect.step(JSON.stringify(options));
            }

            async detect() {
                return [{ rawValue: "Scanned QR" }];
            }
        },
    });
    await mountWithCleanup(QRCodeScanner.QRCodeScanner, {
        props: {
            onResult: (result) => expect.step(result),
            onError: (error) => expect.step(error.message),
        },
    });

    await animationFrame();
    await manuallyDispatchProgrammaticEvent(queryOne("video"), "loadeddata");
    await animationFrame();

    expect.verifySteps([
        '{"formats":["qr_code"]}',
        '{"audio":false,"video":{"facingMode":{"ideal":"environment"},"width":{"ideal":1920},"height":{"ideal":1080}}}',
        "camera stopped",
        "Scanned QR",
    ]);
});
