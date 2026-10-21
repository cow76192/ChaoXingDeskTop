import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: pane
    property string selectedId: ""
    property var selected: {
        let state = bridge.summary
        return selectedId ? bridge.activityDetail(selectedId) : ({})
    }
    function applyFilter() { bridge.filterActivities(search.text, statuses.currentValue || "") }
    Connections {
        target: bridge
        function onQuestionsReset() { pane.selectedId = ""; detail.close(); search.text = ""; statuses.currentIndex = 0; pane.applyFilter() }
    }
    spacing: 8
    RowLayout {
        Layout.fillWidth: true
        Basic.TextField { id: search; objectName: "activitySearch"; Layout.fillWidth: true; placeholderText: "搜索活动、课程、章节或处理原因"; Accessible.name: "搜索投票问卷记录"; onTextEdited: filterTimer.restart() }
        ChoiceBox {
            id: statuses; textRole: "label"; valueRole: "value"; Accessible.name: "活动处理状态"
            model: [{label: "全部记录", value: ""}, {label: "本地草稿", value: "draft"}, {label: "已确认提交", value: "submitted"}, {label: "本人已参与", value: "existing"}, {label: "提交未知", value: "submit_unknown"}, {label: "待处理", value: "pending"}, {label: "平台拒绝", value: "rejected"}]
            onActivated: pane.applyFilter()
        }
    }
    Timer { id: filterTimer; interval: 150; onTriggered: pane.applyFilter() }
    Text {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#627086"; font.pixelSize: 12
        text: {
            let s = bridge.summary.activityStats, a = bridge.summary.activitySources
            return "记录 " + bridge.summary.activityCount + " · 草稿 " + (s.draft || 0) + " · 已提交 " + (s.submitted || 0) + " · 已参与 " + (s.existing || 0) +
                " · 提交未知 " + (s.submit_unknown || 0) + " · 待处理 " + (s.pending || 0) + " · 任务点确认 " + bridge.summary.activityConfirmed +
                "\n已解决答案来源：AI " + (a.ai || 0) + " · 随机 " + (a.random || 0) + " · 固定好 " + (a.fixed || 0) + "。答案生成、提交与任务完成分别记录。" +
                (bridge.summary.activityEvicted ? " 已淘汰 " + bridge.summary.activityEvicted + " 条旧显示记录。" : "")
        }
    }
    ListView {
        id: results; objectName: "activityResults"
        Layout.fillWidth: true; Layout.fillHeight: true; model: bridge.activityModel; clip: true
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: results.width - 12; height: 101
            onClicked: { pane.selectedId = modelData.id; detail.open() }
            background: Rectangle { radius: 6; color: parent.hovered ? "#eaf1fd" : index % 2 ? "#f8f9fc" : "white" }
            contentItem: ColumnLayout {
                spacing: 4
                RowLayout {
                    Text { text: modelData.title; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#17243a"; font.pixelSize: 13 }
                    Text { text: modelData.stageText; color: modelData.submit_status === "confirmed" || modelData.submit_status === "existing" ? "#15803d" : "#b45309"; font.pixelSize: 12 }
                }
                Text { text: modelData.course + " / " + modelData.chapter; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#8490a4"; font.pixelSize: 11 }
                Text { text: "已解决 " + modelData.solved + " / " + modelData.questionCount + " 题（必答 " + modelData.requiredCount + "） · " + modelData.sourceText + " · " + modelData.elapsed_ms + " ms"; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#627086"; font.pixelSize: 12 }
                Text { text: "提交：" + modelData.submitText + " · 任务点：" + modelData.taskText + " · " + modelData.reason; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: "#627086"; font.pixelSize: 12 }
            }
        }
        Text { visible: results.count === 0; anchors.centerIn: parent; text: "暂无活动记录；可在题库与 AI → 投票／问卷中设置策略与预览"; color: "#627086"; font.pixelSize: 12 }
    }
    Dialog {
        id: detail; objectName: "activityDetail"; parent: Overlay.overlay; anchors.centerIn: parent
        title: "投票／问卷 · 逐题答案与核验详情"; modal: true
        width: Math.min(780, pane.Window.width - 60); height: Math.min(630, pane.Window.height - 100)
        background: Rectangle { color: "white"; radius: 12; border.color: "#dbe3ef" }
        footer: Item {
            implicitHeight: 58
            ActionButton { anchors.right: parent.right; anchors.rightMargin: 20; anchors.verticalCenter: parent.verticalCenter; text: "关闭"; onClicked: detail.close() }
        }
        contentItem: ColumnLayout {
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                TextArea {
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#17243a"
                    text: pane.selected.detailText || "记录已清除或淘汰"
                }
            }
            ActionButton { text: "复制逐题草稿"; enabled: !!pane.selected.detailText; onClicked: bridge.copyActivity(pane.selectedId) }
        }
    }
}
