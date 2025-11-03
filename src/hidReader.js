const HID = require("node-hid");

/**
 * @typedef {Object} BatteryConfig
 * @property {string} hidPath
 * @property {string|number} vid
 * @property {string|number} pid
 * @property {number} pollIntervalSeconds
 * @property {number} initDelayMs
 * @property {number} retryCount
 */

const DEFAULT_VENDOR_ID = 0x3151;
const DEFAULT_PRODUCT_ID = 0x5007;
const ANGRY_MIAO_INIT_FEATURE = (() => {
    const data = new Array(65).fill(0);
    data[1] = 0xf7;
    return data;
})();
const ANGRY_MIAO_REPORT_ID = 0xf7;
const DEFAULT_BUFFER_LENGTH = 65;

/**
 * @param {unknown} raw
 * @returns {number | undefined}
 */
function parseConfigInt(raw) {
    if (raw === null || raw === undefined) {
        return undefined;
    }
    if (typeof raw === "number" && Number.isFinite(raw)) {
        return Math.trunc(raw);
    }
    if (typeof raw !== "string") {
        return undefined;
    }
    const value = raw.trim().toLowerCase();
    if (!value) {
        return undefined;
    }
    if (value.startsWith("0x")) {
        const parsedHex = Number.parseInt(value.slice(2), 16);
        return Number.isNaN(parsedHex) ? undefined : parsedHex;
    }
    if (value.endsWith("h")) {
        const parsedSuffix = Number.parseInt(value.slice(0, -1), 16);
        return Number.isNaN(parsedSuffix) ? undefined : parsedSuffix;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? undefined : parsed;
}

/**
 * @returns {Promise<void>}
 */
function wait(ms) {
    if (ms <= 0) {
        return Promise.resolve();
    }
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

/**
 * @param {string | Buffer | undefined} path
 * @returns {string | undefined}
 */
function normalisePath(path) {
    if (!path) {
        return undefined;
    }
    if (typeof path === "string") {
        return path;
    }
    if (Buffer.isBuffer(path)) {
        return path.toString("utf-8");
    }
    return undefined;
}

/**
 * @param {number} vid
 * @param {number} pid
 * @returns {string | undefined}
 */
function findDevicePath(vid, pid) {
    let devices;
    try {
        devices = HID.devices();
    } catch (error) {
        throw new Error(`Unable to enumerate HID devices: ${error instanceof Error ? error.message : String(error)}`);
    }
    const matches = [];
    for (const info of devices) {
        if (info.vendorId !== vid || info.productId !== pid) {
            continue;
        }
        const devicePath = normalisePath(info.path);
        if (!devicePath) {
            continue;
        }
        matches.push({ info, devicePath });
    }
    if (matches.length === 0) {
        return undefined;
    }

    const exactInterface = matches.find(({ info }) => {
        const iface = info.interface ?? info.interfaceNumber;
        return iface === 2;
    });
    if (exactInterface) {
        return exactInterface.devicePath;
    }

    const preferredPath = matches.find(({ devicePath }) =>
        devicePath.toLowerCase().includes("mi_02")
    );
    if (preferredPath) {
        return preferredPath.devicePath;
    }

    return matches[0].devicePath;
}

/**
 * @param {BatteryConfig} config
 * @returns {Promise<number>}
 */
async function readBatteryPercentage(config) {
    const retryCount = Math.max(1, Math.trunc(config.retryCount || 1));
    const initDelay = Math.max(0, Math.trunc(config.initDelayMs || 0));
    const targetVid = parseConfigInt(config.vid) ?? DEFAULT_VENDOR_ID;
    const targetPid = parseConfigInt(config.pid) ?? DEFAULT_PRODUCT_ID;

    let targetPath = (config.hidPath || "").trim();
    if (!targetPath) {
        const resolved = findDevicePath(targetVid, targetPid);
        if (!resolved) {
            throw new Error(
                `Device not found (VID 0x${targetVid.toString(16).padStart(4, "0")}, PID 0x${targetPid
                    .toString(16)
                    .padStart(4, "0")})`
            );
        }
        targetPath = resolved;
    }

    let lastError = null;
    for (let attempt = 1; attempt <= retryCount; attempt += 1) {
        let device;
        try {
            device = new HID.HID(targetPath);
        } catch (error) {
            lastError = new Error(
                `Unable to open HID device: ${error instanceof Error ? error.message : String(error)}`
            );
            continue;
        }

        try {
            device.sendFeatureReport(ANGRY_MIAO_INIT_FEATURE);
        } catch (error) {
            lastError = new Error(
                `Failed to send init feature (attempt ${attempt}): ${
                    error instanceof Error ? error.message : String(error)
                }`
            );
            safeClose(device);
            await wait(initDelay);
            continue;
        }

        await wait(initDelay);

        try {
            const data = device.getFeatureReport(ANGRY_MIAO_REPORT_ID, DEFAULT_BUFFER_LENGTH);
            if (!data || data.length < 4 || data[0] !== ANGRY_MIAO_REPORT_ID) {
                const payload = data ? Buffer.from(data).toString("hex") : "null";
                lastError = new Error(`Unexpected feature report: ${payload}`);
                safeClose(device);
                continue;
            }
            safeClose(device);
            const battery = data[3];
            if (!Number.isFinite(battery)) {
                lastError = new Error("Battery value missing in report");
                continue;
            }
            return Math.min(100, Math.max(0, battery));
        } catch (error) {
            lastError = new Error(
                `Failed to read feature report (attempt ${attempt}): ${
                    error instanceof Error ? error.message : String(error)
                }`
            );
        } finally {
            safeClose(device);
        }
    }

    throw lastError || new Error("Unable to read battery percentage");
}

/**
 * @param {import("node-hid").HID | undefined} device
 */
function safeClose(device) {
    if (!device) {
        return;
    }
    try {
        device.close();
    } catch (error) {
        // Ignore close errors
    }
}

module.exports = {
    readBatteryPercentage
};
