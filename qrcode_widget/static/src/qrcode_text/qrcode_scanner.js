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
import { loadJS } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class QRCodeScanner extends Component {
    static template = "qrcode_widget.QRCodeScanner";
    static props = ["onResult", "onError"];

    setup() {
        this.video = useRef("video");
        this.stream = null;
        this.timeout = null;

        onWillStart(async () => {
            if ("BarcodeDetector" in window) {
                this.detector = new BarcodeDetector({ formats: ["qr_code"] });
                return;
            }
            await loadJS("/web/static/lib/zxing-library/zxing-library.js");
            const reader = new window.ZXing.BrowserQRCodeReader();
            this.detector = {
                detect(video) {
                    try {
                        return [{ rawValue: reader.decode(video).getText() }];
                    } catch (error) {
                        if (
                            error instanceof window.ZXing.NotFoundException ||
                            error instanceof window.ZXing.ChecksumException ||
                            error instanceof window.ZXing.FormatException
                        ) {
                            return [];
                        }
                        throw error;
                    }
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
                        width: { ideal: 1920 },
                        height: { ideal: 1080 },
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
        try {
            const [result] = await this.detector.detect(this.video.el);
            if (result) {
                this.stop();
                this.props.onResult(result.rawValue);
            } else if (this.stream) {
                this.timeout = setTimeout(() => this.detect(), 100);
            }
        } catch (error) {
            this.stop();
            this.props.onError(error);
        }
    }
}

export class QRCodeDialog extends Component {
    static template = "qrcode_widget.QRCodeDialog";
    static components = { Dialog, QRCodeScanner };
    static props = ["close", "onResult"];

    setup() {
        this.state = useState({
            supported: Boolean(browser.navigator.mediaDevices?.getUserMedia),
            error: _t("Camera scanning is not supported by this browser."),
        });
    }

    onResult(result) {
        this.props.close();
        this.props.onResult(result);
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
