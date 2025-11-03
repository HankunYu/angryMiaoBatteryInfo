const { plugin, logger } = require("@eniac/flexdesigner");
const { readBatteryPercentage } = require("./hidReader");

const BATTERY_CID = "com.hankun.mousebattery.status";
const DEFAULT_CONFIG = {
    hidPath: "",
    vid: "",
    pid: "",
    pollIntervalSeconds: 30,
    initDelayMs: 50,
    retryCount: 3
};
const MIN_POLL_INTERVAL_MS = 5000;
const CONFIG_RETRY_BASE_DELAY_MS = 1000;
const CONFIG_RETRY_MAX_DELAY_MS = 10000;

/** @type {ReturnType<typeof buildConfig>} */
let pluginConfig = buildConfig();
/** @type {Map<string, { serialNumber: string, key: any }>} */
const batteryKeys = new Map();
let pollTimer = null;
let pollIntervalMs = pluginConfig.pollIntervalSeconds * 1000;
let pollInFlight = false;
let latestStatus = { kind: "unknown", label: "waiting" };
let configRetryTimer = null;
let configRetryAttempts = 0;
let pendingForcedRefresh = false;

function buildConfig(raw) {
    const merged = { ...DEFAULT_CONFIG };
    if (!raw || typeof raw !== "object") {
        return merged;
    }

    if (typeof raw.hidPath === "string") {
        merged.hidPath = raw.hidPath.trim();
    }
    if (typeof raw.vid === "string" || typeof raw.vid === "number") {
        merged.vid = String(raw.vid).trim();
    }
    if (typeof raw.pid === "string" || typeof raw.pid === "number") {
        merged.pid = String(raw.pid).trim();
    }
    if (typeof raw.initDelayMs === "string" || typeof raw.initDelayMs === "number") {
        const parsedDelay = Number(raw.initDelayMs);
        if (!Number.isNaN(parsedDelay) && parsedDelay >= 0) {
            merged.initDelayMs = parsedDelay;
        }
    }
    if (typeof raw.retryCount === "string" || typeof raw.retryCount === "number") {
        const parsedRetry = Number(raw.retryCount);
        if (!Number.isNaN(parsedRetry) && parsedRetry >= 1) {
            merged.retryCount = Math.floor(parsedRetry);
        }
    }

    const pollValue = Number(raw.pollIntervalSeconds);
    if (!Number.isNaN(pollValue) && pollValue > 0) {
        merged.pollIntervalSeconds = pollValue;
    }

    return merged;
}

async function loadInitialConfig() {
    try {
        const stored = await plugin.getConfig();
        pluginConfig = buildConfig(stored);
        pollIntervalMs = getPollIntervalMs(pluginConfig);
        configRetryAttempts = 0;
        if (configRetryTimer) {
            clearTimeout(configRetryTimer);
            configRetryTimer = null;
        }
        logger.info("[mouse-battery] Config loaded.");
    } catch (error) {
        if (isTransportNotReadyError(error)) {
            scheduleConfigRetry();
            logger.debug("[mouse-battery] Transport not ready, retrying config load soon.");
        } else {
            logger.warn(`[mouse-battery] Unable to load config, using defaults. ${error instanceof Error ? error.message : error}`);
        }
        pluginConfig = buildConfig();
        pollIntervalMs = getPollIntervalMs(pluginConfig);
    } finally {
        ensurePolling();
    }
}

function makeKeyId(serialNumber, uid) {
    return `${serialNumber}:${uid}`;
}

function getPollIntervalMs(config) {
    return Math.max(
        MIN_POLL_INTERVAL_MS,
        Math.round(config.pollIntervalSeconds * 1000)
    );
}

function isTransportNotReadyError(error) {
    if (!error) {
        return false;
    }
    const message = error instanceof Error ? error.message : String(error);
    return message.includes("Cannot read properties of null") && message.includes("send");
}

function scheduleConfigRetry() {
    if (configRetryTimer) {
        return;
    }
    const delay = Math.min(
        CONFIG_RETRY_BASE_DELAY_MS * Math.pow(2, configRetryAttempts),
        CONFIG_RETRY_MAX_DELAY_MS
    );
    configRetryAttempts += 1;
    configRetryTimer = setTimeout(() => {
        configRetryTimer = null;
        loadInitialConfig();
    }, delay);
}

function statusesEqual(a, b) {
    if (a.kind !== b.kind) {
        return false;
    }
    if (a.kind === "value" && b.kind === "value") {
        return a.value === b.value;
    }
    if (a.kind === "error" && b.kind === "error") {
        return a.label === b.label && a.detail === b.detail;
    }
    return true;
}

function drawKey(serialNumber, key, status) {
    const drawKeyData = {
        ...key,
        style: {
            ...key.style,
            showIcon: false,
            showTitle: true
        },
        title: formatTitle(status)
    };

    if (status.kind === "error") {
        drawKeyData.style = {
            ...drawKeyData.style,
            titleColor: "#FF5555"
        };
    } else {
        drawKeyData.style = {
            ...drawKeyData.style,
            titleColor: "#FFFFFF"
        };
    }

    plugin.draw(serialNumber, drawKeyData, "draw");
}

function formatTitle(status) {
    if (status.kind === "value") {
        return `${status.value}%`;
    }
    if (status.kind === "error") {
        return "ERR";
    }
    return "--";
}

async function pollAndUpdate(forceRedraw = false, force = false) {
    if (pollInFlight) {
        if (force) {
            pendingForcedRefresh = true;
        }
        return;
    }
    if (batteryKeys.size === 0) {
        return;
    }
    pollInFlight = true;
    try {
        const result = await readBatteryOnce();
        const status = { kind: "value", value: result, label: `${result}%` };
        if (!statusesEqual(status, latestStatus) || forceRedraw) {
            latestStatus = status;
            logger.info(`[mouse-battery] Battery ${result}%`);
            renderAllKeys();
        }
    } catch (error) {
        const status = {
            kind: "error",
            label: "error",
            detail: error instanceof Error ? error.message : String(error)
        };
        if (!statusesEqual(status, latestStatus) || forceRedraw) {
            latestStatus = status;
            logger.warn(
                `[mouse-battery] Battery read failed: ${
                    status.detail || status.label
                }`
            );
            renderAllKeys();
        }
    } finally {
        pollInFlight = false;
        if (pendingForcedRefresh) {
            pendingForcedRefresh = false;
            pollAndUpdate(true, false);
        }
    }
}

function renderAllKeys() {
    for (const { serialNumber, key } of batteryKeys.values()) {
        drawKey(serialNumber, key, latestStatus);
    }
}

function ensurePolling() {
    if (batteryKeys.size === 0) {
        stopPolling();
        return;
    }

    const desiredInterval = getPollIntervalMs(pluginConfig);
    if (pollTimer && pollIntervalMs === desiredInterval) {
        return;
    }

    if (pollTimer) {
        clearInterval(pollTimer);
    }

    pollIntervalMs = desiredInterval;
    pollTimer = setInterval(() => {
        pollAndUpdate(false);
    }, pollIntervalMs);
    pollAndUpdate(true);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

function readBatteryOnce() {
    return readBatteryPercentage(pluginConfig);
}

plugin.on("plugin.config.updated", (payload) => {
    const rawConfig = payload && payload.config ? payload.config : payload;
    pluginConfig = buildConfig(rawConfig);
    pollIntervalMs = getPollIntervalMs(pluginConfig);
    logger.info("[mouse-battery] Config updated.");
    configRetryAttempts = 0;
    if (configRetryTimer) {
        clearTimeout(configRetryTimer);
        configRetryTimer = null;
    }
    ensurePolling();
});

plugin.on("plugin.alive", (payload) => {
    const serialNumber = payload.serialNumber;
    for (const key of payload.keys) {
        if (key.cid === BATTERY_CID) {
            const keyId = makeKeyId(serialNumber, key.uid);
            batteryKeys.set(keyId, { serialNumber, key });
            drawKey(serialNumber, key, latestStatus);
        }
    }
    ensurePolling();
});

plugin.on("plugin.data", (payload) => {
    const data = payload.data;
    if (!data || !data.key || data.key.cid !== BATTERY_CID) {
        return;
    }

    const serialNumber = payload.serialNumber;
    const keyId = makeKeyId(serialNumber, data.key.uid);
    if (!batteryKeys.has(keyId)) {
        batteryKeys.set(keyId, {
            serialNumber,
            key: {
                ...data.key,
                style: {
                    ...data.key.style
                }
            }
        });
    }

    pollAndUpdate(true, true);
    return {
        status: "success",
        message: "Battery refresh requested"
    };
});

plugin.on("plugin.destroy", (payload) => {
    const serialNumber = payload && payload.serialNumber;
    if (!serialNumber) {
        return;
    }

    for (const [keyId, keyData] of batteryKeys.entries()) {
        if (keyData.serialNumber === serialNumber) {
            batteryKeys.delete(keyId);
        }
    }

    if (batteryKeys.size === 0) {
        stopPolling();
    }
});

plugin.start();

setTimeout(() => {
    loadInitialConfig();
}, 0);
