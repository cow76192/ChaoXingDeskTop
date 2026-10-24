import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: field
    required property var spec
    property string value: bridge.values[spec.section][spec.key]
    property bool revealed: false
    property var dependency: spec.depends || ({})
    property bool correcting: false
    property bool applicable: correcting || !dependency.key || bridge.values[dependency.section][dependency.key] === dependency.value
    property bool invalidNumber: (spec.kind === "integer" || spec.kind === "number") && !edit.acceptableInput
    spacing: 5
    Layout.fillWidth: true
    onEnabledChanged: if (!enabled) revealed = false
    Connections {
        target: bridge
        function onFieldRequested(section, key) {
            if (section !== field.spec.section || key !== field.spec.key) return
            field.correcting = true
            Qt.callLater(function() {
                let control = field.spec.kind === "choice" ? choice : field.spec.kind === "bool" ? boolSwitch : field.spec.kind === "multiline" ? multiEdit : edit
                control.forceActiveFocus()
                let item = field.parent
                while (item) {
                    if (item.contentY !== undefined && item.contentHeight !== undefined) {
                        item.contentY = Math.max(0, Math.min(item.contentHeight - item.height, field.mapToItem(item.contentItem, 0, 0).y - 20))
                        break
                    }
                    item = item.parent
                }
            })
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: field.spec.title; font.pixelSize: 13; color: "#34435a"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Text { visible: field.spec.kind === "bool"; text: field.value.toLowerCase() === "true" ? "已启用" : "已关闭"; color: field.value.toLowerCase() === "true" ? "#15803d" : "#475569"; font.pixelSize: 12 }
        Switch {
            id: boolSwitch
            enabled: !bridge.summary.busy && field.applicable
            visible: field.spec.kind === "bool"
            checked: field.value.toLowerCase() === "true"
            Accessible.name: field.spec.title
            onToggled: bridge.setValue(field.spec.section, field.spec.key, checked ? "true" : "false")
        }
    }
    RowLayout {
        visible: field.spec.kind !== "bool"
        enabled: !bridge.summary.busy && field.applicable
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
            onEditingFinished: if (acceptableInput) field.correcting = false
            background: Rectangle { radius: 6; color: edit.enabled ? "white" : "#f0f2f6"; border.color: field.invalidNumber ? "#dc2626" : edit.activeFocus ? "#2563eb" : "#94a3b8"; border.width: edit.activeFocus ? 2 : 1 }
        }
        ChoiceBox {
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
        }
        ActionButton { visible: field.spec.kind === "secret"; text: field.revealed ? "隐藏" : "显示"; onClicked: field.revealed = !field.revealed }
        ActionButton { visible: field.spec.kind === "directory"; text: "选择目录"; onClicked: bridge.chooseLogDirectory() }
    }
    ScrollView {
        enabled: !bridge.summary.busy && field.applicable
        visible: field.spec.kind === "multiline"
        Layout.fillWidth: true; Layout.preferredHeight: 140; clip: true
        TextArea {
            id: multiEdit
            objectName: "field_" + field.spec.section + "_" + field.spec.key + "_multiline"
            text: field.value; wrapMode: TextEdit.Wrap; selectByMouse: true
            color: "#17243a"; Accessible.name: field.spec.title
            onTextChanged: if (activeFocus) bridge.setValue(field.spec.section, field.spec.key, text)
        }
    }
    Text {
        visible: bridge.summary.busy || !field.applicable
        text: bridge.summary.busy ? "运行中锁定，结束后可编辑" : field.dependency.reason + "；已填写的值保留"
        color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
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
