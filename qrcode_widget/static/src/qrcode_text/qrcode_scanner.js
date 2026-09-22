/** @odoo-module **/

/* global BarcodeDetector */

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    status,
    useRef,
    useState,
} from "@odoo/owl";
import * as assets from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { BBQrDecoder } from "./bbqr_decoder";

export class QRCodeScanner extends Component {
    static template = "qrcode_widget.QRCodeScanner";
    static props = ["onResult", "onError"];

    setup() {
        this.video = useRef("video");
        this.stream = null;
        this.timeout = null;
        this.detecting = false;

        onWillStart(async () => {
            await assets.loadJS("/web/static/lib/zxing-library/zxing-library.js");
            const reader = new window.ZXing.QRCodeReader();
            const hints = new Map([[window.ZXing.DecodeHintType.TRY_HARDER, true]]);
            const canvas = document.createElement("canvas");
            const context = canvas.getContext("2d", { willReadFrequently: true });
            const nativeDetector = window.BarcodeDetector
                ? new BarcodeDetector({ formats: ["qr_code"] })
                : null;
            this.detector = {
                async detect(video) {
                    if (nativeDetector) {
                        const results = await nativeDetector.detect(video);
                        if (results.length) {
                            return results;
                        }
                    }
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    context.drawImage(video, 0, 0);
                    const decode = () => {
                        const source = new window.ZXing.HTMLCanvasElementLuminanceSource(canvas);
                        const bitmap = new window.ZXing.BinaryBitmap(
                            new window.ZXing.HybridBinarizer(source)
                        );
                        try {
                            return reader.decode(bitmap, hints).getText();
                        } catch (error) {
                            if (
                                error instanceof window.ZXing.NotFoundException ||
                                error instanceof window.ZXing.ChecksumException ||
                                error instanceof window.ZXing.FormatException
                            ) {
                                return false;
                            }
                            throw error;
                        }
                    };
                    let result = decode();
                    if (result) {
                        return [{ rawValue: result }];
                    }
                    const size = Math.floor(Math.min(video.videoWidth, video.videoHeight) / 2);
                    canvas.width = size;
                    canvas.height = size;
                    context.drawImage(
                        video,
                        (video.videoWidth - size) / 2,
                        (video.videoHeight - size) / 2,
                        size,
                        size,
                        0,
                        0,
                        size,
                        size
                    );
                    result = decode();
                    if (result) {
                        return [{ rawValue: result }];
                    }
                    context.globalCompositeOperation = "difference";
                    context.fillStyle = "white";
                    context.fillRect(0, 0, size, size);
                    context.globalCompositeOperation = "source-over";
                    result = decode();
                    if (result) {
                        return [{ rawValue: result }];
                    }
                    return [];
                },
            };
        });
        onMounted(async () => {
            let stream;
            try {
                stream = await browser.navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        facingMode: { ideal: "environment" },
                    },
                });
            } catch (error) {
                const messages = {
                    NotFoundError: _t("No camera was found."),
                    NotAllowedError: _t("Camera access was not allowed."),
                };
                this.props.onError(
                    new Error(
                        messages[error.name] ||
                            _t("Could not start the camera: %(message)s", {
                                message: error.message,
                            })
                    )
                );
                return;
            }
            if (status(this) === "destroyed") {
                stream.getTracks().forEach((track) => track.stop());
                return;
            }
            this.stream = stream;
            this.video.el.srcObject = stream;
        });
        onWillUnmount(() => this.stop());
    }

    stop() {
        clearTimeout(this.timeout);
        this.timeout = null;
        if (this.stream) {
            this.stream.getTracks().forEach((track) => track.stop());
            this.stream = null;
        }
    }

    async detect() {
        if (this.detecting || !this.stream) {
            return;
        }
        this.detecting = true;
        try {
            const [result] = await this.detector.detect(this.video.el);
            if (result) {
                const complete = await this.props.onResult(result.rawValue);
                if (complete !== false) {
                    this.stop();
                } else if (this.stream) {
                    this.timeout = setTimeout(() => this.detect(), 200);
                }
            } else if (this.stream) {
                this.timeout = setTimeout(() => this.detect(), 200);
            }
        } catch (error) {
            this.stop();
            this.props.onError(error);
        } finally {
            this.detecting = false;
        }
    }
}

export class QRCodeDialog extends Component {
    static template = "qrcode_widget.QRCodeDialog";
    static components = { Dialog, QRCodeScanner };
    static props = ["close", "onResult"];

    setup() {
        this.decoder = new BBQrDecoder();
        this.state = useState({
            supported: Boolean(browser.navigator.mediaDevices?.getUserMedia),
            error: _t("Camera scanning is not supported by this browser."),
            progress: false,
        });
    }

    async onResult(result) {
        const decoded = await this.decoder.receive(result);
        if (!decoded.complete) {
            this.state.progress = _t("BBQr: %(received)s of %(total)s parts scanned", {
                received: decoded.received,
                total: decoded.total,
            });
            return false;
        }
        this.props.close();
        this.props.onResult(decoded.value);
        return true;
    }

    onError(error) {
        this.state.supported = false;
        this.state.error = error.message;
    }
}

export function scanQRCode(env) {
    return new Promise((resolve) => {
        env.services.dialog.add(QRCodeDialog, { onResult: resolve });
    });
}
