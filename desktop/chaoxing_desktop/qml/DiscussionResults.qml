import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: pane
    property string selectedId: ""
    property var selected: {
        let state = bridge.summary
        return selectedId ? bridge.discussionDetail(selectedId) : ({})
    }
    function applyFilter() { bridge.filterDiscussions(search.text, statuses.currentValue || "") }
    Connections {
        target: bridge
        function onQuestionsReset() { pane.selectedId = ""; detail.close(); search.text = ""; statuses.currentIndex = 0; pane.applyFilter() }
    }
    spacing: 8
    RowLayout {
        Layout.fillWidth: true
        Basic.TextField { id: search; objectName: "discussionSearch"; Layout.fillWidth: true; placeholderText: "搜索讨论主题、课程或原因"; Accessible.name: "搜索讨论记录"; onTextEdited: filterTimer.restart() }
        ChoiceBox {
            id: statuses; textRole: "label"; valueRole: "value"; Accessible.name: "讨论发布状态"
            model: [{label: "全部记录", value: ""}, {label: "本地草稿", value: "draft"}, {label: "已发布", value: "published"}, {label: "本人已回复", value: "existing"}, {label: "发布未知", value: "publish_unknown"}, {label: "待处理", value: "pending"}]
            onActivated: pane.applyFilter()
        }
    }
    Timer { id: filterTimer; interval: 150; onTriggered: pane.applyFilter() }
    Text {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#627086"; font.pixelSize: 12
        text: {
            let s = bridge.summary.discussionStats
            return "记录 " + bridge.summary.discussionCount + " · 草稿 " + (s.draft || 0) + " · 本人已有回复 " + (s.existing || 0) +
                " · 本轮发布确认 " + (s.published || 0) + " · 发布未知 " + (s.publish_unknown || 0) + " · 任务点确认 " + bridge.summary.discussionConfirmed +
                " · 待处理 " + (s.pending || 0) + "。发布与任务完成分开；成绩未知。" +
                (bridge.summary.discussionEvicted ? " 已淘汰 " + bridge.summary.discussionEvicted + " 条旧显示记录。" : "")
        }
    }
    ListView {
        id: results; objectName: "discussionResults"
        Layout.fillWidth: true; Layout.fillHeight: true; model: bridge.discussionModel; clip: true
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: results.width - 12; height: 87
            onClicked: { pane.selectedId = modelData.id; detail.open() }
            background: Rectangle { radius: 6; color: parent.hovered ? "#eaf1fd" : index % 2 ? "#f8f9fc" : "white" }
            contentItem: ColumnLayout {
                spacing: 4
                RowLayout {
                    Text { text: modelData.title; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#17243a"; font.pixelSize: 13 }
                    Text { text: modelData.stageText + " · 任务" + modelData.taskText; color: modelData.task_status === "confirmed" ? "#15803d" : "#b45309"; font.pixelSize: 12 }
                }
                Text { text: modelData.course + " / " + modelData.chapter; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#627086"; font.pixelSize: 11 }
                Text { text: modelData.levelText + " · " + modelData.sourceText + " · " + modelData.elapsed_ms + " ms · " + modelData.reason; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#627086"; font.pixelSize: 12 }
            }
        }
        Text { visible: results.count === 0; anchors.centerIn: parent; text: "暂无讨论记录；可先在题库与 AI → 讨论任务中预览"; color: "#627086"; font.pixelSize: 12 }
    }
    ActionDialog {
        id: detail; objectName: "discussionDetail"; parent: Overlay.overlay; anchors.centerIn: parent
        cancelText: "关闭"
        title: "讨论草稿与处理详情"; modal: true
        width: Math.min(760, pane.Window.width - 60); height: Math.min(580, pane.Window.height - 100)
        onOpened: bridge.clearUiFeedback("record")
        contentItem: ColumnLayout {
            OperationNotice { scope: "record"; Layout.fillWidth: true }
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                TextArea {
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#17243a"
                    text: (pane.selected.title || "记录已清除或淘汰") + "\n\n" + (pane.selected.course || "") + " / " + (pane.selected.chapter || "") +
                        "\n\n发布：" + (pane.selected.stageText || "") + "\n任务点：" + (pane.selected.taskText || "") + "\n成绩：未知" +
                        "\n来源：" + (pane.selected.sourceText || "") + " / " + (pane.selected.levelText || "") + "\n原因：" + (pane.selected.reason || "") +
                        "\n\n正文：\n" + (pane.selected.content || "尚无正文")
                }
            }
            ActionButton { text: "复制讨论正文"; enabled: !!pane.selected.content; onClicked: bridge.copyDiscussion(pane.selectedId) }
            ActionButton { objectName: "editDiscussionCopy"; text: "编辑本地副本…"; tone: "connect"; enabled: pane.selected.stage === "draft" && !bridge.summary.busy; onClicked: { detail.close(); bridge.openDraftCopy("discussion", pane.selectedId) } }
        }
    }
}
