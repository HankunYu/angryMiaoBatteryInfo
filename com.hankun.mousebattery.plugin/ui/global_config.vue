<template>
    <v-container class="mouse-battery-config pa-4" fluid tag="div">
        <v-card class="mouse-battery-card">
            <v-card-title class="d-flex align-center">
                <v-icon class="mr-2">mdi-battery-high</v-icon>
                <span>Mouse Battery Settings</span>
                <v-spacer />
                <v-btn
                    color="primary"
                    prepend-icon="mdi-content-save"
                    :loading="isSaving"
                    :disabled="isSaving"
                    @click="saveConfig"
                >
                    Save
                </v-btn>
            </v-card-title>
            <v-divider />
            <v-card-text class="mouse-battery-body mouse-battery-scroll pt-6">
                <v-row>
                    <v-col cols="12" md="6">
                        <v-text-field
                            v-model="localConfig.hidPath"
                            label="HID device path (optional)"
                            placeholder="\\?\HID#VID_3151&PID_5007..."
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                    <v-col cols="12" md="3">
                        <v-text-field
                            v-model="localConfig.vid"
                            label="USB vendor ID"
                            placeholder="0x3151"
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                    <v-col cols="12" md="3">
                        <v-text-field
                            v-model="localConfig.pid"
                            label="USB product ID"
                            placeholder="0x5007"
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                </v-row>
                <v-row>
                    <v-col cols="12" md="6">
                        <v-text-field
                            v-model.number="localConfig.pollIntervalSeconds"
                            label="Poll interval (seconds)"
                            type="number"
                            min="5"
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                    <v-col cols="12" md="6">
                        <v-text-field
                            v-model.number="localConfig.initDelayMs"
                            label="Delay after init (ms)"
                            type="number"
                            min="0"
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                </v-row>
                <v-row>
                    <v-col cols="12" md="6">
                        <v-text-field
                            v-model.number="localConfig.retryCount"
                            label="Retry attempts"
                            type="number"
                            min="1"
                            hide-details="auto"
                            variant="outlined"
                        />
                    </v-col>
                </v-row>
            </v-card-text>
            <v-divider />
            <v-card-actions class="justify-end">
                <v-btn
                    variant="text"
                    prepend-icon="mdi-restore"
                    :disabled="isSaving"
                    @click="resetToDefaults"
                >
                    Reset
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-container>
</template>

<script>
const DEFAULT_CONFIG = {
    hidPath: "",
    vid: "",
    pid: "",
    pollIntervalSeconds: 30,
    initDelayMs: 50,
    retryCount: 3
};

export default {
    props: {
        modelValue: {
            type: Object,
            required: true
        }
    },
    data() {
        return {
            localConfig: { ...DEFAULT_CONFIG },
            isSaving: false
        };
    },
    watch: {
        modelValue: {
            immediate: true,
            deep: true,
            handler(newVal) {
                const incoming = (newVal && newVal.config) || {};
                this.localConfig = {
                    ...DEFAULT_CONFIG,
                    ...incoming
                };
            }
        }
    },
    methods: {
        async saveConfig() {
            if (this.isSaving) {
                return;
            }
            this.isSaving = true;
            const sanitized = this.normalizeConfig(this.localConfig);
            try {
                await this.$fd.setConfig(sanitized);
                if (this.modelValue && this.modelValue.config) {
                    Object.assign(this.modelValue.config, sanitized);
                }
                this.localConfig = { ...sanitized };
                this.$fd.showSnackbarMessage("success", "Config updated");
            } catch (error) {
                const message = error?.message || "Failed to save config";
                this.$fd.showSnackbarMessage("error", message);
                console.error("[mouse-battery] Failed to save config:", error);
            } finally {
                this.isSaving = false;
            }
        },
        resetToDefaults() {
            this.localConfig = { ...DEFAULT_CONFIG };
        },
        normalizeConfig(config) {
            const poll = Number(config.pollIntervalSeconds);
            const initDelay = Number(config.initDelayMs);
            const retryCount = Number(config.retryCount);
            return {
                hidPath: (config.hidPath || "").trim(),
                vid: (config.vid ?? "").toString().trim(),
                pid: (config.pid ?? "").toString().trim(),
                pollIntervalSeconds: Number.isFinite(poll) && poll > 0 ? poll : DEFAULT_CONFIG.pollIntervalSeconds,
                initDelayMs: Number.isFinite(initDelay) && initDelay >= 0 ? initDelay : DEFAULT_CONFIG.initDelayMs,
                retryCount: Number.isFinite(retryCount) && retryCount >= 1 ? Math.floor(retryCount) : DEFAULT_CONFIG.retryCount
            };
        }
    }
};
</script>

<style scoped>
.mouse-battery-config {
    height: 100%;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.mouse-battery-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    max-height: 100%;
}

.mouse-battery-body {
    flex: 1;
    overflow-y: auto;
}

.mouse-battery-scroll {
    max-height: calc(100vh - 220px);
}
</style>
