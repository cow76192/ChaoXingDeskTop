import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Dialog {
    id: editor; objectName: "draftEditor"
    property var copy: ({})
    parent: Overlay.overlay; anchors.centerIn: parent; modal: true
    width: Math.min(800, parent.width - 50); height: Math.min(650, parent.height - 50)
    title: "人工编辑副本 · 仅本地"
    closePolicy: Popup.NoAutoClose
    background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6" }
    Connections {
        target: bridge
        function onDraftOpened(row) { editor.copy = row; discussion.text = row.content; editor.open() }
        function onQuestionsReset() { editor.close(); editor.copy = ({}) }
    }
    contentItem: ColumnLayout {
        Label { text: "独立副本，人工编辑来源。正文按账号保存在本机，未加密；不会覆盖原始草稿或防重意图。关闭前请保存副本。"; color: "#627086"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: editor.copy.source ? editor.copy.source.title : ""; wrapMode: Text.Wrap; Layout.fillWidth: true; font.bold: true }
        Label { visible: !bridge.draftEditable; text: "当前来源或账号未核实，副本只读；可复制或导出。"; color: "#995a0d"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        ScrollView {
            visible: editor.copy.kind === "discussion"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            TextArea {
                id: discussion; objectName: "draftDiscussionText"; readOnly: !bridge.draftEditable
                wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; selectByMouse: true
                Accessible.name: "编辑讨论正文副本"
                onTextChanged: if (activeFocus) bridge.setDraftContent(text)
            }
        }
        ListView {
            id: questions; objectName: "draftQuestions"
            visible: editor.copy.kind === "activity"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 16
            model: editor.copy.source && editor.copy.kind === "activity" ? editor.copy.source.questions : []
            ScrollBar.vertical: ScrollBar {}
            delegate: ColumnLayout {
                id: question
                required property var modelData
                required property int index
                property var initial: bridge.draftAnswer(modelData.id)
                property var selected: initial.option_ids || []
                width: questions.width - 18; spacing: 5
                Label { text: (question.index + 1) + ". " + question.modelData.title; wrapMode: Text.Wrap; Layout.fillWidth: true; font.bold: true }
                Label { text: "ID " + question.modelData.id + " · " + (question.modelData.required ? "必答" : "可选") + (question.modelData.type === "text" ? " · 字符 " + question.modelData.min_length + "–" + question.modelData.max_length : " · 选项数量 " + question.modelData.minimum + "–" + question.modelData.maximum); wrapMode: Text.Wrap; color: "#627086"; Layout.fillWidth: true }
                Repeater {
                    model: question.modelData.options
                    Basic.CheckBox {
                        required property var modelData
                        objectName: "draftOption_" + question.modelData.id + "_" + modelData.id
                        Layout.fillWidth: true; enabled: bridge.draftEditable
                        checked: question.selected.indexOf(modelData.id) >= 0
                        text: modelData.text; Accessible.name: modelData.text
                        contentItem: Text { text: parent.text; wrapMode: Text.Wrap; color: "#17243a"; leftPadding: parent.indicator.width + parent.spacing; verticalAlignment: Text.AlignVCenter }
                        onToggled: {
                            let values = question.selected.slice()
                            if (checked) values = question.modelData.type === "single" ? [modelData.id] : values.concat([modelData.id])
                            else values = values.filter(function(v) { return v !== modelData.id })
                            question.selected = values
                            bridge.setDraftAnswer(question.modelData.id, {option_ids: values})
                        }
                    }
                }
                ScrollView {
                    visible: question.modelData.type === "text"; Layout.fillWidth: true; Layout.preferredHeight: 140; clip: true
                    TextArea {
                        objectName: "draftText_" + question.modelData.id
                        readOnly: !bridge.draftEditable; text: question.initial.text || ""; wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText; selectByMouse: true; Accessible.name: "编辑第 " + (question.index + 1) + " 题副本"
                        onTextChanged: if (activeFocus) bridge.setDraftAnswer(question.modelData.id, {text: text})
                    }
                }
            }
        }
        ScrollView {
            Layout.fillWidth: true; Layout.preferredHeight: 82; clip: true; contentWidth: availableWidth
            TextArea { text: bridge.draftFeedback; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: "#995a0d"; background: null; textFormat: TextEdit.PlainText }
        }
    }
    footer: RowLayout {
        spacing: 8
        ActionButton { objectName: "saveDraftCopy"; text: "保存本机副本"; enabled: bridge.draftEditable; onClicked: bridge.saveDraftCopy() }
        ActionButton { text: "复制副本"; onClicked: bridge.exportDraftCopy(true) }
        ActionButton { text: "导出副本…"; onClicked: bridge.exportDraftCopy(false) }
        Item { Layout.fillWidth: true }
        ActionButton { objectName: "closeDraftEditor"; text: "关闭"; onClicked: editor.close() }
    }
}
