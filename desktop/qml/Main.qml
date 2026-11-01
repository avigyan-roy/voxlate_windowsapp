import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 600
    height: 760
    minimumWidth: 520
    minimumHeight: 640
    visible: true
    title: "Voxlate"
    color: "#0f1218"
    Material.theme: Material.Dark
    Material.accent: "#13a89e"
    Material.primary: "#13a89e"

    readonly property var st: backend.st
    readonly property var devs: st.devices ? st.devices : null
    readonly property var cable: devs && devs.cable ? devs.cable : null
    readonly property string engineState: st.state ? st.state.state : "Starting"
    readonly property bool translating: engineState === "Translating"
    readonly property bool modelsReady: st.models !== undefined && st.models.status === "ready"
    readonly property bool hasProfile: st.profile !== undefined && st.profile.exists
    readonly property bool workerReady: st.hello !== undefined   // worker process is up (models may still load)
    readonly property var reasonText: ({ "cable_not_found": "Virtual cable not found", "device_busy": "Audio device busy",
                                         "mic_blocked": "Microphone access blocked by Windows", "no_signal": "No signal received",
                                         "leak": "Other audio is on the virtual microphone", "timeout": "Engine not responding",
                                         "error": "Check failed" })
    readonly property var langNames: ({ "hi": "Hindi", "en": "English" })

    property string page: "confirm"        // confirm -> pathcheck -> enroll -> dashboard
    property string mic: ""
    property string src: backend.setting("src", "hi")
    property string tgt: src === "hi" ? "en" : "hi"
    property string mode: backend.setting("mode", "translated")
    property bool muted: false
    property bool checking: false
    property var pathResult: null
    onWorkerReadyChanged: if (!workerReady) checking = false
    property bool firstRun: false

    onClosing: (close) => { close.accepted = false; root.hide(); backend.notifyHidden() }

    function startTranslation() {
        if (!cable) { page = "pathcheck"; return }
        backend.send({ cmd: "start", mic: mic, cable: cable.playback, src: src, tgt: tgt, mode: mode })
    }
    function toggleTranslation() {
        if (page !== "dashboard") { root.show(); root.raise(); return }
        if (translating || engineState === "Starting") backend.send({ cmd: "stop" })
        else startTranslation()
    }
    function swapLanguages() {
        src = tgt
        backend.setSetting("src", src)
        if (translating) backend.send({ cmd: "set_languages", src: src, tgt: tgt })
    }
    function afterConfirm() {
        backend.setSetting("mic", mic)
        backend.send({ cmd: "load_models" })
        firstRun = !backend.setting("pathCheckOk", false) || !hasProfile
        page = !backend.setting("pathCheckOk", false) ? "pathcheck" : (!hasProfile ? "enroll" : "dashboard")
    }
    function stateColor(s) {
        return s === "Translating" ? "#22c55e" : s === "Error" ? "#ef4444" : s === "Starting" ? "#f59e0b" : "#94a3b8"
    }

    Connections {
        target: backend
        function onTrayToggle() { root.toggleTranslation() }
        function onWorkerEvent(ev) {
            if (ev.ev === "path_check") {
                root.checking = false
                root.pathResult = ev
                if (ev.ok) backend.setSetting("pathCheckOk", true)
            } else if (ev.ev === "enroll" && ev.phase === "saved" && root.page === "enroll") {
                root.page = "dashboard"
            } else if (ev.ev === "muted") {
                root.muted = ev.on
            }
        }
    }

    component Card: Pane {
        Layout.fillWidth: true
        padding: 16
        Material.elevation: 2
        background: Rectangle { color: "#171c25"; radius: 12; border.color: "#232a36" }
    }
    component Caption: Label { color: "#94a3b8"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    component Title: Label { font.pixelSize: 15; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
    // Inline components use the backend context property, not ids of this file.
    component EngineError: ColumnLayout {
        id: engineError
        readonly property var s: backend.st.state ? backend.st.state : ({})
        visible: s.state === "Error"
        Layout.fillWidth: true
        Caption { text: engineError.s.detail || ""; color: "#ef4444" }
        RowLayout {
            Button { text: "Retry"; highlighted: true; onClicked: backend.restartWorker() }
            Button { text: "Open logs"; flat: true; onClicked: backend.openLogs() }
        }
    }
    component MicPrivacyWarning: ColumnLayout {
        visible: !!backend.st.devices && !!backend.st.devices.mic_blocked
        Layout.fillWidth: true
        Caption {
            color: "#f59e0b"
            text: "Windows is blocking microphone access, so Voxlate and the virtual cable only receive silence.\n"
                  + "Fix: Settings > Privacy & security > Microphone > turn on \"Microphone access\" and "
                  + "\"Let desktop apps access your microphone\", then press Refresh / Retry."
        }
        Button { text: "Open microphone privacy settings"; flat: true; onClicked: Qt.openUrlExternally("ms-settings:privacy-microphone") }
    }

    header: ToolBar {
        background: Rectangle { color: "#0b0e13" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            Label { text: "VOXLATE"; font.pixelSize: 18; font.bold: true; font.letterSpacing: 3 }
            Item { Layout.fillWidth: true }
            Rectangle { width: 10; height: 10; radius: 5; color: root.stateColor(root.engineState) }
            Label { text: root.engineState; color: root.stateColor(root.engineState); font.bold: true }
        }
    }

    StackLayout {
        anchors.fill: parent
        anchors.margins: 16
        currentIndex: ["confirm", "pathcheck", "enroll", "dashboard"].indexOf(root.page)

        // ------------------------------------------------------------ 1. confirm microphone (every launch)
        ColumnLayout {
            spacing: 14
            Title { text: "Confirm your microphone"; font.pixelSize: 20 }
            Caption { text: "Pick the physical microphone you will speak into. Virtual cables are hidden here on purpose so audio can never loop back." }
            Card {
                ColumnLayout {
                    width: parent.width
                    BusyIndicator { visible: !root.devs; running: visible; Layout.alignment: Qt.AlignHCenter }
                    ComboBox {
                        id: micBox
                        visible: !!root.devs
                        Layout.fillWidth: true
                        model: root.devs ? root.devs.inputs : []
                        onModelChanged: {
                            const saved = backend.setting("mic", "")
                            const i = model.indexOf(saved)
                            currentIndex = i >= 0 ? i : 0
                        }
                    }
                    Caption {
                        visible: !!root.devs && root.devs.inputs.length === 0
                        text: root.devs && root.devs.error ? root.devs.error : "No microphone found. Plug one in and press Refresh."
                        color: "#ef4444"
                    }
                    MicPrivacyWarning {}
                    RowLayout {
                        Button { text: "Refresh"; flat: true; onClicked: backend.send({ cmd: "list_devices" }) }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: "Confirm microphone"
                            highlighted: true
                            enabled: micBox.currentText !== ""
                            onClicked: { root.mic = micBox.currentText; root.afterConfirm() }
                        }
                    }
                }
            }
            Card {
                ColumnLayout {
                    width: parent.width
                    Title { text: "Virtual microphone" }
                    Caption {
                        text: root.cable ? "Found: Voxlate plays into “" + root.cable.playback + "”. In Google Meet choose “" + root.cable.recording + "” as the microphone."
                                         : "VB-CABLE not found. Install it (see README), reboot, then press Refresh."
                        color: root.cable ? "#94a3b8" : "#f59e0b"
                    }
                }
            }
            Caption { visible: root.engineState === "Starting"; text: root.st.state ? root.st.state.detail || "" : "" }
            EngineError {}
            Item { Layout.fillHeight: true }
        }

        // ------------------------------------------------------------ 2. audio path check
        ColumnLayout {
            spacing: 14
            Title { text: "Audio path check"; font.pixelSize: 20 }
            Caption { text: "Voxlate plays a short test sweep into the virtual cable and listens on the cable's recording side, which is what Google Meet will hear. You will not hear anything." }
            Card {
                ColumnLayout {
                    width: parent.width
                    spacing: 10
                    Caption {
                        visible: !root.cable
                        color: "#f59e0b"
                        text: "VB-CABLE is not installed or not detected. Install it from vb-audio.com/Cable, reboot, then press Detect again."
                    }
                    Button { visible: !root.cable; text: "Detect again"; enabled: root.workerReady; onClicked: backend.send({ cmd: "list_devices" }) }
                    RowLayout {
                        visible: !!root.cable
                        Button {
                            text: !root.workerReady ? "Waiting for engine…" : root.checking ? "Checking…"
                                  : (root.pathResult && !root.pathResult.ok ? "Retry" : "Run audio path check")
                            highlighted: true
                            enabled: root.workerReady && !root.checking && !root.translating
                            onClicked: {
                                root.checking = true
                                root.pathResult = null
                                checkTimeout.restart()
                                backend.send({ cmd: "path_check", playback: root.cable.playback, recording: root.cable.recording })
                            }
                        }
                        BusyIndicator { running: root.checking || (!root.workerReady && root.engineState !== "Error"); visible: running; implicitHeight: 32 }
                    }
                    Timer {  // safety net: the worker answers within ~6 s, so never spin longer than this
                        id: checkTimeout
                        interval: 15000
                        onTriggered: if (root.checking) {
                            root.checking = false
                            root.pathResult = { ok: false, reason: "timeout", hint: "The engine did not answer within 15 s. Press Retry; if it repeats, use Open logs." }
                        }
                    }
                    Label {
                        visible: !!root.pathResult
                        text: root.pathResult ? (root.pathResult.ok ? "✔ Signal reached the virtual microphone"
                                                 : "✖ " + (root.reasonText[root.pathResult.reason] || "Check failed")) : ""
                        color: root.pathResult && root.pathResult.ok ? "#22c55e" : "#ef4444"
                        font.bold: true
                    }
                    Caption {
                        visible: !!root.pathResult
                        text: !root.pathResult ? "" : (root.pathResult.score !== undefined
                              ? "match " + root.pathResult.score + " · cable delay " + root.pathResult.delay_ms + " ms · idle level " + root.pathResult.silence_dbfs + " dBFS" : "")
                              + (root.pathResult.hint ? (root.pathResult.score !== undefined ? "\n" : "") + root.pathResult.hint : "")
                    }
                    MicPrivacyWarning {}
                }
            }
            EngineError {}
            RowLayout {
                Button { text: "Back"; flat: true; onClicked: root.page = root.firstRun ? "confirm" : "dashboard" }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Skip for now"
                    flat: true
                    visible: !(root.pathResult && root.pathResult.ok)
                    onClicked: skipDlg.open()
                }
                Button {
                    text: "Continue"
                    highlighted: true
                    enabled: !!root.pathResult && root.pathResult.ok
                    onClicked: root.page = root.hasProfile ? "dashboard" : "enroll"
                }
            }
            Item { Layout.fillHeight: true }
        }

        // ------------------------------------------------------------ 3. voice enrollment
        ColumnLayout {
            id: enrollPage
            spacing: 12
            readonly property var en: root.st.enroll ? root.st.enroll : ({ phase: "idle" })
            readonly property var q: en.quality ? en.quality : null
            Title { text: "Set up your voice (one time)"; font.pixelSize: 20 }
            Caption { text: "Read the script below aloud in your normal speaking voice (about 45–60 seconds). It stays on this computer, encrypted to your Windows account. You can re-record or delete it any time." }
            Card {
                Layout.fillHeight: true
                ScrollView {
                    anchors.fill: parent
                    clip: true
                    Label {
                        width: parent.width
                        text: root.st.profile ? root.st.profile.script : ""
                        wrapMode: Text.Wrap
                        font.pixelSize: 15
                        lineHeight: 1.3
                    }
                }
            }
            RowLayout {
                CheckBox { id: consent }
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "This is my own voice and I consent to Voxlate storing it locally to speak translations in my voice."
                }
            }
            RowLayout {
                visible: enrollPage.en.phase === "recording"
                Label { text: "● Recording " + (enrollPage.en.seconds || 0).toFixed(0) + " s"; color: "#ef4444" }
                ProgressBar { Layout.fillWidth: true; value: Math.min(1, Math.sqrt(enrollPage.en.level || 0) * 3) }
            }
            ColumnLayout {
                visible: enrollPage.en.phase === "review" && !!enrollPage.q
                Label {
                    text: enrollPage.q && enrollPage.q.ok ? "✔ Good recording" : "Recording needs attention"
                    color: enrollPage.q && enrollPage.q.ok ? "#22c55e" : "#f59e0b"
                    font.bold: true
                }
                Caption {
                    text: enrollPage.q ? ("Speech " + enrollPage.q.voiced_s + " s · SNR " + enrollPage.q.snr_db + " dB · clipping " + enrollPage.q.clipping_pct + "%"
                                      + (enrollPage.q.problems.length ? "\n• " + enrollPage.q.problems.join("\n• ") : "")) : ""
                }
            }
            RowLayout {
                Button {
                    text: "Record"
                    highlighted: true
                    visible: enrollPage.en.phase !== "recording" && enrollPage.en.phase !== "review"
                    enabled: consent.checked
                    onClicked: backend.send({ cmd: "enroll_start", mic: root.mic })
                }
                Button { text: "Stop"; highlighted: true; visible: enrollPage.en.phase === "recording"; onClicked: backend.send({ cmd: "enroll_stop" }) }
                Button { text: "Play back"; visible: enrollPage.en.phase === "review"; onClicked: backend.send({ cmd: "enroll_play" }) }
                Button { text: "Re-record"; visible: enrollPage.en.phase === "review"; onClicked: backend.send({ cmd: "enroll_discard" }) }
                Item { Layout.fillWidth: true }
                Button {
                    text: enrollPage.q && enrollPage.q.ok ? "Save voice" : "Save anyway"
                    highlighted: !!enrollPage.q && enrollPage.q.ok
                    visible: enrollPage.en.phase === "review"
                    onClicked: backend.send({ cmd: "enroll_save" })
                }
                Button {
                    text: "Cancel"
                    flat: true
                    visible: root.hasProfile && enrollPage.en.phase !== "recording"
                    onClicked: { backend.send({ cmd: "enroll_discard" }); root.page = "dashboard" }
                }
            }
            Caption { visible: enrollPage.en.phase === "error"; text: enrollPage.en.detail || ""; color: "#ef4444" }
        }

        // ------------------------------------------------------------ 4. dashboard
        ScrollView {
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 12

                Card {
                    RowLayout {
                        width: parent.width
                        ColumnLayout {
                            Layout.fillWidth: true
                            Title { text: root.translating ? "Translating" : (root.engineState === "Starting" ? "Starting…" : "Translation is off") }
                            Caption {
                                text: root.st.state && root.st.state.detail ? root.st.state.detail
                                      : (root.modelsReady ? "Ready" : (root.st.models ? root.st.models.detail || "" : "Loading…"))
                                color: root.engineState === "Error" ? "#ef4444" : "#94a3b8"
                            }
                        }
                        Switch {
                            id: power
                            checked: root.translating || root.engineState === "Starting"
                            enabled: root.mic !== "" && !!root.cable
                            onToggled: { checked = Qt.binding(() => root.translating || root.engineState === "Starting"); root.toggleTranslation() }
                            scale: 1.4
                        }
                    }
                }

                Card {
                    ColumnLayout {
                        width: parent.width
                        Caption { text: "LANGUAGE" }
                        RowLayout {
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["Hindi", "English"]
                                currentIndex: root.src === "hi" ? 0 : 1
                                onActivated: (i) => { if ((i === 0 ? "hi" : "en") !== root.src) root.swapLanguages() }
                            }
                            Button { text: "⇄"; font.pixelSize: 18; onClicked: root.swapLanguages(); ToolTip.visible: hovered; ToolTip.text: "Swap languages" }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["Hindi", "English"]
                                currentIndex: root.tgt === "hi" ? 0 : 1
                                onActivated: (i) => { if ((i === 0 ? "hi" : "en") !== root.tgt) root.swapLanguages() }
                            }
                        }
                        Caption { text: "You speak " + root.langNames[root.src] + " · the meeting hears " + root.langNames[root.tgt] }
                    }
                }

                Card {
                    ColumnLayout {
                        width: parent.width
                        Caption { text: "WHAT THE MEETING HEARS" }
                        Repeater {
                            model: [["translated", "Translated only (recommended)"], ["original", "Original voice only (no translation)"], ["both", "Both (translation may overlap your voice)"]]
                            RadioButton {
                                required property var modelData
                                text: modelData[1]
                                checked: root.mode === modelData[0]
                                onToggled: if (checked) {
                                    root.mode = modelData[0]
                                    backend.setSetting("mode", root.mode)
                                    backend.send({ cmd: "set_mode", mode: root.mode })
                                }
                            }
                        }
                    }
                }

                Card {
                    GridLayout {
                        width: parent.width
                        columns: 2
                        columnSpacing: 12
                        Caption { text: "Microphone"; Layout.fillWidth: false }
                        ProgressBar { Layout.fillWidth: true; value: root.st.level ? Math.min(1, Math.sqrt(root.st.level.mic) * 3) : 0 }
                        Caption { text: "To meeting"; Layout.fillWidth: false }
                        ProgressBar { Layout.fillWidth: true; value: root.st.level ? Math.min(1, Math.sqrt(root.st.level.out) * 3) : 0 }
                        Caption { text: "Delay"; Layout.fillWidth: false }
                        Label {
                            Layout.fillWidth: true
                            text: root.st.delay ? ("≈ " + root.st.delay.p50.toFixed(1) + " s   (p95 " + root.st.delay.p95.toFixed(1) + " s, last " + root.st.delay.last.toFixed(1) + " s)")
                                                : "measured after the first translated phrase"
                            color: root.st.level && root.st.level.delayed ? "#f59e0b" : "#e2e8f0"
                        }
                    }
                }

                RowLayout {
                    Button {
                        Layout.fillWidth: true
                        text: root.muted ? "Unmute" : "Mute"
                        highlighted: root.muted
                        Material.accent: "#ef4444"
                        onClicked: backend.send({ cmd: "mute", on: !root.muted })
                    }
                    Button {
                        Layout.fillWidth: true
                        text: "Test audio path"
                        enabled: !root.translating
                        onClicked: { root.pathResult = null; root.page = "pathcheck" }
                    }
                }

                Card {
                    ColumnLayout {
                        width: parent.width
                        Caption { text: "VOICE" }
                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            text: root.hasProfile ? ("Your voice profile · recorded " + (root.st.profile.created || "").replace("T", " ")) : "No voice profile — translations will use a generic voice."
                            color: root.hasProfile ? "#e2e8f0" : "#f59e0b"
                        }
                        Caption { visible: root.modelsReady; text: root.modelsReady ? "Speaking with: " + root.st.models.voice : "" }
                        RowLayout {
                            Button {
                                text: root.hasProfile ? "Re-record voice" : "Set up voice"
                                enabled: !root.translating
                                onClicked: { backend.send({ cmd: "enroll_discard" }); root.page = "enroll" }
                            }
                            Button { text: "Play my sample"; visible: root.hasProfile; flat: true; onClicked: backend.send({ cmd: "enroll_play" }) }
                            Item { Layout.fillWidth: true }
                            Button { text: "Delete"; visible: root.hasProfile; flat: true; enabled: !root.translating; onClicked: deleteDlg.open() }
                        }
                    }
                }

                Card {
                    ColumnLayout {
                        width: parent.width
                        Caption { text: "SETUP" }
                        Label { Layout.fillWidth: true; elide: Text.ElideRight; text: "Mic: " + root.mic }
                        Caption { text: root.cable ? "In Google Meet → Settings → Audio → Microphone: “" + root.cable.recording + "”" : "Virtual cable missing" }
                        Caption {
                            visible: root.modelsReady
                            text: root.modelsReady ? (root.st.models.device + (root.st.models.gpu ? " (" + root.st.models.gpu + ")" : "") + " · " + root.st.models.asr + " · " + root.st.models.mt + " · " + root.st.models.tts) : ""
                        }
                        Caption { visible: !!root.st.warning; text: root.st.warning ? "⚠ " + root.st.warning.detail : ""; color: "#f59e0b" }
                        RowLayout {
                            Button { text: "Change microphone"; flat: true; enabled: !root.translating; onClicked: root.page = "confirm" }
                        }
                        EngineError {}
                    }
                }
            }
        }
    }

    Dialog {
        id: skipDlg
        anchors.centerIn: parent
        title: "Skip the audio path check?"
        standardButtons: Dialog.Yes | Dialog.No
        Label {
            width: 420
            wrapMode: Text.Wrap
            text: "If the virtual cable path does not work, the meeting will hear nothing. You can run the check later from the dashboard (Test audio path)."
        }
        onAccepted: root.page = root.hasProfile ? "dashboard" : "enroll"
    }

    Dialog {
        id: deleteDlg
        anchors.centerIn: parent
        title: "Delete voice profile?"
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: "Your recorded sample and voice data will be removed from this computer." }
        onAccepted: backend.send({ cmd: "profile_delete" })
    }
}
