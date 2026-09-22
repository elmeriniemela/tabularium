/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

export class BBQrDecoder {
    constructor() {
        this.header = null;
        this.parts = [];
        this.partLength = null;
    }

    async receive(value) {
        if (!value.startsWith("B$")) {
            if (this.header) {
                throw new Error(_t("Expected another BBQr part."));
            }
            return { complete: true, value };
        }

        const match = /^B\$([H2Z])([A-Z])([0-9A-Z]{2})([0-9A-Z]{2})([0-9A-Z]+)$/.exec(
            value
        );
        if (!match) {
            throw new Error(_t("Invalid BBQr part."));
        }

        const [, encoding, fileType, totalText, indexText, payload] = match;
        const total = parseInt(totalText, 36);
        const index = parseInt(indexText, 36);
        if (!total || index >= total) {
            throw new Error(_t("Invalid BBQr part."));
        }

        const header = value.slice(0, 6);
        if (this.header && this.header !== header) {
            throw new Error(_t("BBQr parts do not belong to the same sequence."));
        }
        this.header = header;

        if (encoding === "H") {
            BBQrDecoder.decodeHex(payload);
        } else {
            BBQrDecoder.decodeBase32(payload);
        }

        if (index < total - 1) {
            if (this.partLength !== null && payload.length !== this.partLength) {
                throw new Error(_t("BBQr parts have inconsistent lengths."));
            }
            this.partLength = payload.length;
            if (this.parts[total - 1]?.length > this.partLength) {
                throw new Error(_t("BBQr parts have inconsistent lengths."));
            }
        } else if (this.partLength !== null && payload.length > this.partLength) {
            throw new Error(_t("BBQr parts have inconsistent lengths."));
        }

        if (this.parts[index] && this.parts[index] !== payload) {
            throw new Error(_t("A scanned BBQr part conflicts with an earlier part."));
        }
        this.parts[index] = payload;

        const received = this.parts.filter(Boolean).length;
        if (received !== total) {
            return { complete: false, received, total };
        }

        const byteParts = this.parts.map((part) =>
            encoding === "H" ? BBQrDecoder.decodeHex(part) : BBQrDecoder.decodeBase32(part)
        );
        const bytes = new Uint8Array(byteParts.reduce((size, part) => size + part.length, 0));
        let offset = 0;
        for (const part of byteParts) {
            bytes.set(part, offset);
            offset += part.length;
        }

        const raw = encoding === "Z" ? await BBQrDecoder.inflate(bytes) : bytes;
        return { complete: true, value: BBQrDecoder.toText(raw, fileType) };
    }

    static decodeHex(value) {
        if (value.length % 2 || !/^[0-9A-F]+$/.test(value)) {
            throw new Error(_t("Invalid hexadecimal BBQr data."));
        }
        return Uint8Array.from(value.match(/../g), (byte) => parseInt(byte, 16));
    }

    static decodeBase32(value) {
        if (!/^[A-Z2-7]+$/.test(value) || ![0, 2, 4, 5, 7].includes(value.length % 8)) {
            throw new Error(_t("Invalid Base32 BBQr data."));
        }

        const bytes = [];
        let bits = 0;
        let buffer = 0;
        for (const character of value) {
            buffer = (buffer << 5) | "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(character);
            bits += 5;
            if (bits >= 8) {
                bits -= 8;
                bytes.push((buffer >> bits) & 0xff);
                buffer &= (1 << bits) - 1;
            }
        }
        if (buffer) {
            throw new Error(_t("Invalid Base32 BBQr data."));
        }
        return Uint8Array.from(bytes);
    }

    static async inflate(bytes) {
        if (!window.DecompressionStream) {
            throw new Error(_t("This browser cannot decompress BBQr data."));
        }
        const input = new window.ReadableStream({
            start(controller) {
                controller.enqueue(bytes);
                controller.close();
            },
        });
        const reader = input
            .pipeThrough(new window.DecompressionStream("deflate-raw"))
            .getReader();
        const chunks = [];
        let size = 0;
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            chunks.push(value);
            size += value.length;
        }
        const output = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) {
            output.set(chunk, offset);
            offset += chunk.length;
        }
        return output;
    }

    static toText(bytes, fileType) {
        if (fileType === "J" || fileType === "U") {
            return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        }
        if (fileType === "T") {
            return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
        }

        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 32768) {
            binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
        }
        return btoa(binary);
    }
}
