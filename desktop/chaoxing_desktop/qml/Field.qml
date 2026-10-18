import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: field
    required property var spec
    property string value: bridge.values[spec.section][spec.key]
    property bool revealed: false
    property bool invalidNumber: (spec.kind === "integer" || spec.kind === "number") && !edit.acceptableInput
    spacing: 5
    enabled: !bridge.summary.busy
    Layout.fillWidth: true
    onEnabledChanged: if (!enabled) revealed = false
    RowLayout {
        Layout.fillWidth: true
        Text { text: field.spec.title; font.pixelSize: 13; color: "#34435a"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Text { visible: field.spec.kind === "bool"; text: field.value.toLowerCase() === "true" ? "已启用" : "已关闭"; color: field.value.toLowerCase() === "true" ? "#15803d" : "#475569"; font.pixelSize: 12 }
        Switch {
            visible: field.spec.kind === "bool"
            checked: field.value.toLowerCase() === "true"
            Accessible.name: field.spec.title
            onToggled: bridge.setValue(field.spec.section, field.spec.key, checked ? "true" : "false")
        }
    }
    RowLayout {
        visible: field.spec.kind !== "bool"
        Layout.fillWidth: true
        Basic.TextField {
            id: edit
            objectName: "field_" + field.spec.section + "_" + field.spec.key
            visible: field.spec.kind !== "choice" && field.spec.kind !== "multiline"
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            text: field.value
            color: enabled ? "#17243a" : "#64748b"
            placeholderTextColor: "#58677d"
            placeholderText: field.spec.hint || ""
            selectByMouse: true
            echoMode: field.spec.kind === "secret" && !field.revealed ? TextInput.Password : TextInput.Normal
            Accessible.name: field.spec.title
            inputMethodHints: field.spec.kind === "integer" || field.spec.kind === "number" ? Qt.ImhFormattedNumbersOnly : Qt.ImhNone
            validator: field.spec.kind === "integer" ? integerValidator : field.spec.kind === "number" ? numberValidator : null
            IntValidator { id: integerValidator; bottom: field.spec.low; top: field.spec.high }
            DoubleValidator { id: numberValidator; bottom: field.spec.low; top: field.spec.high; decimals: 3; notation: DoubleValidator.StandardNotation; locale: "C" }
            onTextEdited: bridge.setValue(field.spec.section, field.spec.key, text)
            background: Rectangle { radius: 6; color: edit.enabled ? "white" : "#f0f2f6"; border.color: field.invalidNumber ? "#dc2626" : edit.activeFocus ? "#2563eb" : "#94a3b8"; border.width: edit.activeFocus ? 2 : 1 }
        }
        Basic.ComboBox {
            id: choice
            objectName: "choice_" + field.spec.section + "_" + field.spec.key
            visible: field.spec.kind === "choice"
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            model: field.spec.choices
            textRole: "label"
            valueRole: "value"
            currentIndex: { for (let i = 0; i < field.spec.choices.length; i++) if (field.spec.choices[i].value === field.value) return i; return -1 }
            Accessible.name: field.spec.title
            onActivated: bridge.setValue(field.spec.section, field.spec.key, currentValue)
            indicator: Text { text: "▾"; x: choice.width - width - 12; y: (choice.height - height) / 2; color: "#34435a"; font.pixelSize: 18 }
            background: Rectangle { radius: 6; color: choice.enabled ? "white" : "#f0f2f6"; border.color: choice.activeFocus ? "#2563eb" : "#94a3b8"; border.width: choice.activeFocus ? 2 : 1 }
        }
        ActionButton { visible: field.spec.kind === "secret"; text: field.revealed ? "隐藏" : "显示"; onClicked: field.revealed = !field.revealed }
        ActionButton { visible: field.spec.kind === "directory"; text: "选择目录"; onClicked: bridge.chooseLogDirectory() }
    }
    ScrollView {
        visible: field.spec.kind === "multiline"
        Layout.fillWidth: true; Layout.preferredHeight: 140; clip: true
        TextArea {
            objectName: "field_" + field.spec.section + "_" + field.spec.key + "_multiline"
            text: field.value; wrapMode: TextEdit.Wrap; selectByMouse: true
            color: "#17243a"; Accessible.name: field.spec.title
            onTextChanged: if (activeFocus) bridge.setValue(field.spec.section, field.spec.key, text)
        }
    }
    Text {
        visible: field.invalidNumber
        text: field.spec.title + "应在 " + field.spec.low + "–" + field.spec.high + " 范围内"
        color: "#b42323"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap
    }
    Text {
        visible: field.spec.hint !== "" && field.spec.kind !== "text" && field.spec.kind !== "secret"
        text: field.spec.hint
        color: field.spec.key === "submit" || field.spec.key === "random_fallback" ? "#a35f12" : "#627086"
        font.pixelSize: 12
        wrapMode: Text.Wrap
        Layout.fillWidth: true
    }
}
