/** @odoo-module **/

import { advanceTime, expect, test } from "@odoo/hoot";
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
import * as assets from "@web/core/assets";
import { BBQrDecoder } from "@qrcode_widget/qrcode_text/bbqr_decoder";
import * as QRCodeScanner from "@qrcode_widget/qrcode_text/qrcode_scanner";
import "@qrcode_widget/qrcode_text/qrcode_text";

class QRCodeTest extends models.Model {
    _name = "qrcode.test";

    char_value = fields.Char();
    text_value = fields.Text();

    _records = [{ id: 1, char_value: "Initial", text_value: "Initial text" }];
}

defineModels([QRCodeTest]);

test("assembles out-of-order BBQr text parts", async () => {
    const decoder = new BBQrDecoder();

    expect(await decoder.receive("B$HU0201576F726C64")).toEqual({
        complete: false,
        received: 1,
        total: 2,
    });
    expect(await decoder.receive("B$HU0201576F726C64")).toEqual({
        complete: false,
        received: 1,
        total: 2,
    });
    expect(await decoder.receive("B$HU020048656C6C6F20")).toEqual({
        complete: true,
        value: "Hello World",
    });
});

test("decodes Base32 and compressed BBQr data", async () => {
    const base32Decoder = new BBQrDecoder();
    await base32Decoder.receive("B$2U0200JBSWY3DPEBLW64TM");
    expect(await base32Decoder.receive("B$2U0201MQ")).toEqual({
        complete: true,
        value: "Hello World",
    });

    const compressedDecoder = new BBQrDecoder();
    await compressedDecoder.receive("B$ZU0200OPHM6LJIJIWS4TSNKFYHECRM");
    expect(await compressedDecoder.receive("B$ZU0201KIUERLGMZFHUYAIA")).toEqual({
        complete: true,
        value: "Compressed BBQr payload",
    });
});

test("uses conventional text encodings for binary BBQr types", async () => {
    expect(await new BBQrDecoder().receive("B$HP010070736274FF")).toEqual({
        complete: true,
        value: "cHNidP8=",
    });
    expect(await new BBQrDecoder().receive("B$HT010001000000")).toEqual({
        complete: true,
        value: "01000000",
    });
});

test("rejects invalid and conflicting BBQr parts", async () => {
    await expect(new BBQrDecoder().receive("B$HU01004")).rejects.toThrow();

    const decoder = new BBQrDecoder();
    await decoder.receive("B$HU020048656C6C6F20");
    await expect(decoder.receive("B$HU0301576F726C64")).rejects.toThrow();
    await expect(decoder.receive("Not BBQr")).rejects.toThrow();
});

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

test("requests a camera stream and scans QR codes", async () => {
    let scans = 0;
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
                return [{ rawValue: ["First QR", "Final QR"][scans++] }];
            }
        },
    });
    await mountWithCleanup(QRCodeScanner.QRCodeScanner, {
        props: {
            onResult: (result) => {
                expect.step(result);
                return result === "Final QR";
            },
            onError: (error) => expect.step(error.message),
        },
    });

    await animationFrame();
    await manuallyDispatchProgrammaticEvent(queryOne("video"), "loadeddata");
    await animationFrame();
    await advanceTime(200);
    await animationFrame();

    expect.verifySteps([
        '{"formats":["qr_code"]}',
        '{"audio":false,"video":{"facingMode":{"ideal":"environment"}}}',
        "First QR",
        "Final QR",
        "camera stopped",
    ]);
});

test("tries a centered crop with ZXing TRY_HARDER", async () => {
    class NotFoundException extends Error {}
    let attempts = 0;
    patchWithCleanup(assets, { loadJS: async () => {} });
    patchWithCleanup(CanvasRenderingContext2D.prototype, { drawImage() {} });
    patchWithCleanup(browser.navigator, {
        mediaDevices: {
            async getUserMedia() {
                return document.createElement("canvas").captureStream();
            },
        },
    });
    patchWithCleanup(window, {
        BarcodeDetector: class {
            async detect() {
                return [];
            }
        },
        ZXing: {
            BinaryBitmap: class {},
            ChecksumException: class extends Error {},
            DecodeHintType: { TRY_HARDER: "try_harder" },
            FormatException: class extends Error {},
            HTMLCanvasElementLuminanceSource: class {},
            HybridBinarizer: class {},
            NotFoundException,
            QRCodeReader: class {
                decode(bitmap, hints) {
                    expect(hints.get("try_harder")).toBe(true);
                    attempts++;
                    if (attempts === 1) {
                        throw new NotFoundException();
                    }
                    return { getText: () => "Dense QR" };
                }
            },
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

    expect(attempts).toBe(2);
    expect.verifySteps(["Dense QR"]);
});
