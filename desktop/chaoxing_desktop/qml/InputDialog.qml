import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Dialog {
    id: dialog
    objectName: "manualDialog"
    property var selected: []
    property string hint: ""
    property var previousFocus: null
    function focusFirst(item) {
        if (!item.visible || !item.enabled) return false
        if (item.activeFocusOnTab) {
            item.forceActiveFocus()
            let p = item.parent
            while (p) {
                if (p.contentY !== undefined && p.contentItem) {
                    p.contentY = Math.max(0, Math.min(p.contentHeight - p.height, item.mapToItem(p.contentItem, 0, 0).y - 20))
                    break
                }
                p = p.parent
            }
            return true
        }
        for (let child of item.children || []) if (focusFirst(child)) return true
        return false
    }
    function revealFocused() {
        let item = dialog.parent.Window.window.activeFocusItem
        if (!item) return
        let p = item.parent
        while (p) {
            if (p.contentY !== undefined && p.contentItem) {
                p.contentY = Math.max(0, Math.min(p.contentHeight - p.height, item.mapToItem(p.contentItem, 0, 0).y - 20))
                return
            }
            p = p.parent
        }
    }
    onOpened: Qt.callLater(function() { dialog.focusFirst(dialog.contentItem); Qt.callLater(dialog.revealFocused) })
    onClosed: if (previousFocus && previousFocus.visible && previousFocus.enabled) previousFocus.forceActiveFocus()
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(760, parent ? parent.width - 80 : 760)
    height: Math.min(640, parent ? parent.height - 80 : 640)
    modal: false
    closePolicy: Popup.NoAutoClose
    padding: 20
    background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6"; border.width: 1 }
    title: bridge.input.kind === "choice" ? "章节处理" : "人工补全"
    Connections {
        target: bridge
        function onInputChanged() {
            if (Object.keys(bridge.input).length > 0) {
                if (!dialog.opened) dialog.previousFocus = dialog.parent.Window.window.activeFocusItem
                dialog.selected = []; answer.text = ""; dialog.hint = ""
                for (let i = 0; i < blanks.count; ++i) blanks.itemAt(i).clear()
                dialog.open()
            }
            else dialog.close()
        }
    }
    contentItem: ColumnLayout {
        spacing: 12
        Text { text: bridge.input.message || "检查题干与选项，填写答案后继续。"; color: "#627086"; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
        ScrollView {
            id: content; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: content.availableWidth; spacing: 14
                Text { text: bridge.input.title || ""; color: "#17243a"; font.pixelSize: 17; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
                Repeater {
                    model: bridge.input.images || []
                    ColumnLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        Image { id: preview; source: modelData; sourceSize.width: 1024; sourceSize.height: 1024; asynchronous: true; fillMode: Image.PreserveAspectFit; Layout.fillWidth: true; Layout.preferredHeight: status === Image.Ready ? Math.min(220, sourceSize.height) : 40 }
                        Text { visible: preview.status === Image.Error; text: "图片加载失败，请在学习平台查看原题。"; color: "#b45309"; font.pixelSize: 12 }
                        Text { visible: preview.status === Image.Loading; text: "正在加载题目图片…"; color: "#627086"; font.pixelSize: 12 }
                    }
                }
                ButtonGroup { id: singleGroup }
                Repeater {
                    model: bridge.input.options || []
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        CheckBox {
                            objectName: "manual_multi_" + modelData.value
                            visible: bridge.input.type === "multiple"; text: modelData.value; Accessible.name: modelData.value + " " + modelData.label
                            onToggled: { let next = dialog.selected.filter(v => v !== modelData.value); if (checked) next.push(modelData.value); dialog.selected = next }
                        }
                        RadioButton {
                            objectName: "manual_single_" + modelData.value
                            visible: bridge.input.type !== "multiple"; text: modelData.value; ButtonGroup.group: singleGroup; Accessible.name: modelData.value + " " + modelData.label
                            onToggled: if (checked) dialog.selected = [modelData.value]
                        }
                        Text { text: modelData.label; color: "#34435a"; font.pixelSize: 14; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
                    }
                }
                Repeater {
                    id: blanks
                    model: bridge.input.type === "completion" && bridge.input.blankCount > 0 ? bridge.input.blankCount : 0
                    ColumnLayout {
                        required property int index
                        Layout.fillWidth: true
                        Text { text: "第 " + (index + 1) + " 空"; color: "#34435a"; font.pixelSize: 13 }
                        TextArea {
                            id: blankAnswer
                            objectName: "manual_blank_" + index
                            Layout.fillWidth: true; Layout.preferredHeight: 72
                            placeholderText: "填写这一空的完整答案"; wrapMode: TextEdit.Wrap
                            Accessible.name: "第 " + (index + 1) + " 空答案"
                        }
                        function value() { return blankAnswer.text.trim() }
                        function clear() { blankAnswer.text = "" }
                    }
                }
                TextArea { id: answer; objectName: "manual_answer"; visible: bridge.input.kind !== "choice" && !(bridge.input.options || []).length && blanks.count === 0; Layout.fillWidth: true; Layout.preferredHeight: 120; placeholderText: bridge.input.type === "completion" ? "平台空位数量未知，建议跳过并在平台核对" : "填写答案"; wrapMode: TextEdit.Wrap; Accessible.name: "人工答案" }
                Repeater {
                    model: bridge.input.choices || []
                    ActionButton { required property var modelData; objectName: "manual_choice_" + modelData.value; text: modelData.label; tone: "connect"; onClicked: bridge.reply(String(modelData.value), false) }
                }
            }
        }
        NoticeBanner { message: dialog.hint || (bridge.input.random ? "跳过后，选择题和判断题将按随机补全设置处理。" : "跳过后，此题保持待处理。"); visible: bridge.input.kind !== "choice"; tone: dialog.hint ? "danger" : "warning"; maximumHeight: 100; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { objectName: "manual_skip"; visible: bridge.input.kind !== "choice"; text: "跳过此题"; tone: "warning"; subtle: true; onClicked: bridge.reply("", false) }
            Item { Layout.fillWidth: true }
            ActionButton { objectName: "manual_stop"; text: "停止任务"; tone: "danger"; onClicked: bridge.reply("", true) }
            ActionButton {
                objectName: "manual_send"; visible: bridge.input.kind !== "choice"; text: "使用答案"; tone: "execute"
                onClicked: {
                    let value
                    if (blanks.count > 0) {
                        let parts = []
                        for (let i = 0; i < blanks.count; ++i) {
                            let part = blanks.itemAt(i).value()
                            if (!part) { dialog.hint = "请填写第 " + (i + 1) + " 空，也可跳过此题。"; return }
                            parts.push(part)
                        }
                        value = JSON.stringify(parts)
                    } else value = dialog.selected.length ? dialog.selected.slice().sort().join("") : answer.text.trim()
                    if (value) bridge.reply(value, false)
                    else dialog.hint = "请先选择或填写答案，也可跳过此题。"
                }
            }
        }
    }
}
