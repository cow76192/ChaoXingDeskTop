import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    property bool logsOpen: true
    property bool followLogs: true
    function mediaTime(seconds) {
        let value = Math.max(0, Math.floor(seconds || 0))
        return Math.floor(value / 60) + ":" + (value % 60 < 10 ? "0" : "") + value % 60
    }
    spacing: page.height < 540 ? 10 : 16
    RowLayout {
        Layout.fillWidth: true; spacing: 14
        Repeater {
            model: [{label: "本轮章节", key: "total", color: "#2563eb"}, {label: "已核验章节", key: "success", color: "#15803d"}, {label: "待完成 / 未核验章节", key: "pending", color: "#b45309"}, {label: "失败章节", key: "failed", color: "#dc2626"}]
            Rectangle {
                required property var modelData
                Layout.fillWidth: true; Layout.preferredHeight: 80; radius: 10; color: "white"; border.color: "#e2e7ef"
                Column {
                    anchors { left: parent.left; top: parent.top; margins: 16 } spacing: 8
                    Text { text: modelData.label; font.pixelSize: 12; color: "#627086" }
                    Text { text: bridge.summary[modelData.key]; font.pixelSize: 28; font.bold: true; color: modelData.color }
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "本轮处理进度"; color: "#34435a"; font.pixelSize: 13 }
        Basic.ProgressBar {
            id: totalBar; Layout.fillWidth: true; Layout.preferredHeight: 10; value: bridge.summary.progress / 100
            background: Rectangle { color: "#cbd5e1"; radius: 5 }
            contentItem: Item { Rectangle { width: parent.width * totalBar.visualPosition; height: parent.height; color: "#2563eb"; radius: 5 } }
        }
        Text { text: bridge.summary.progress + "%"; font.bold: true; color: "#2563eb" }
    }
    Text { text: "按章节统计，同一章节可含多个任务点；处理进度 100% 表示本轮结束，待完成 / 未核验章节请在平台确认。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#627086"; font.pixelSize: 12 }
    SplitView {
        Layout.fillWidth: true; Layout.fillHeight: true; orientation: Qt.Vertical
        Rectangle {
            SplitView.fillHeight: true; SplitView.minimumHeight: page.height < 540 ? 140 : 190; color: "white"; radius: 12; border.color: "#e2e7ef"
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 16; spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    TabBar {
                        id: resultTabs; objectName: "resultTabs"; Layout.fillWidth: true
                        TabButton { text: "章节任务" }
                        TabButton { text: "逐题结果（" + bridge.summary.questionCount + "）" }
                    }
                    Text { text: bridge.summary.busy ? "运行中" : "当前任务"; font.pixelSize: 12; color: "#627086" }
                }
                ListView {
                    visible: resultTabs.currentIndex === 0
                    id: taskList; objectName: "taskList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: bridge.taskModel
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        property var media: modelData.media || ({})
                        width: taskList.width - 10; height: media.name ? 96 : 52; color: index % 2 ? "#f8f9fc" : "white"
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            RowLayout {
                            Layout.fillWidth: true; spacing: 18
                            Text { text: modelData.course; Layout.fillWidth: true; Layout.preferredWidth: 1; elide: Text.ElideRight; font.pixelSize: 13; color: "#34435a" }
                            ActionButton { text: "题目"; subtle: true; onClicked: { questions.taskId = modelData.id; resultTabs.currentIndex = 1 } }
                            Text { text: modelData.title; Layout.fillWidth: true; Layout.preferredWidth: 1; elide: Text.ElideRight; font.pixelSize: 13; color: "#34435a" }
                            Rectangle {
                                Layout.preferredWidth: 136; Layout.preferredHeight: 28; radius: 6
                                color: modelData.status === "success" ? "#e3f4e9" : modelData.status === "failed" ? "#ffe9e9" : modelData.status === "running" ? "#e4edff" : modelData.status === "pending" || modelData.status === "processed" || modelData.status === "retry" ? "#fff0d8" : "#edf0f5"
                                Text { anchors.centerIn: parent; text: modelData.statusText; color: modelData.status === "success" ? "#15803d" : modelData.status === "failed" ? "#dc2626" : modelData.status === "running" ? "#2563eb" : "#627086"; font.pixelSize: 12 }
                            }
                            }
                            RowLayout {
                                visible: !!media.name; Layout.fillWidth: true; spacing: 10
                                Text { text: (media.kind === "Audio" ? "音频 · " : "视频 · ") + (media.name || ""); Layout.fillWidth: true; elide: Text.ElideRight; color: "#17243a"; font.pixelSize: 13 }
                                Text { text: page.mediaTime(media.position) + " / " + page.mediaTime(media.duration) + " · " + (media.percent || 0) + "%"; font.bold: true; color: "#1d4ed8" }
                                Text { objectName: "media_status_" + modelData.id; text: media.statusText || ""; color: "#92400e"; font.pixelSize: 12 }
                            }
                            Basic.ProgressBar {
                                id: mediaBar
                                objectName: "media_" + modelData.id
                                visible: !!media.name; Layout.fillWidth: true; Layout.preferredHeight: 8
                                value: media.duration > 0 ? media.position / media.duration : 0
                                background: Rectangle { color: "#cbd5e1"; radius: 4 }
                                contentItem: Item { Rectangle { width: parent.width * mediaBar.visualPosition; height: parent.height; radius: 4; color: "#2563eb" } }
                            }
                        }
                    }
                    Text { visible: taskList.count === 0; anchors.centerIn: parent; text: "选择课程后，章节任务将在这里显示"; color: "#627086"; font.pixelSize: 14 }
                }
                QuestionResults { id: questions; visible: resultTabs.currentIndex === 1; Layout.fillWidth: true; Layout.fillHeight: true }
            }
        }
        Rectangle {
            SplitView.preferredHeight: page.logsOpen ? 240 : 56
            SplitView.minimumHeight: page.logsOpen ? 160 : 56
            SplitView.maximumHeight: page.logsOpen ? 10000 : 56
            color: "#152339"; radius: 10
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "运行日志"; color: "white"; font.bold: true; font.pixelSize: 14; Layout.fillWidth: true }
                    ActionButton { text: "清空显示"; onClicked: bridge.clearLogs() }
                    ActionButton { text: "删除日志记录"; tone: "danger"; onClicked: deleteLogsDialog.open() }
                    ActionButton { text: "导出保留日志"; tone: "save"; subtle: true; onClicked: bridge.fileAction("export_logs") }
                    ActionButton { text: page.logsOpen ? "收起" : "展开"; onClicked: page.logsOpen = !page.logsOpen }
                }
                Text { visible: page.logsOpen; text: bridge.summary.logSaveError || ("保存目录：" + bridge.summary.logDirectory); color: bridge.summary.logSaveError ? "#fca5a5" : "#e2e8f0"; Layout.fillWidth: true; elide: Text.ElideMiddle; font.pixelSize: 12 }
                RowLayout {
                    visible: page.logsOpen; Layout.fillWidth: true
                    Basic.TextField { id: logSearch; objectName: "logSearch"; Layout.fillWidth: true; placeholderText: "搜索当前保留日志"; Accessible.name: "搜索日志"; onTextEdited: logFilterTimer.restart() }
                    ChoiceBox { id: logLevel; model: ["全部级别", "警告及错误", "仅错误"]; Accessible.name: "日志级别"; onActivated: logFilterTimer.restart() }
                    Basic.CheckBox {
                        id: followCheck; text: "跟随最新"; checked: page.followLogs; onToggled: page.followLogs = checked
                        contentItem: Text { text: followCheck.text; color: "#e2e8f0"; leftPadding: followCheck.indicator.width + followCheck.spacing; verticalAlignment: Text.AlignVCenter }
                    }
                    ActionButton { text: "到底部"; onClicked: { page.followLogs = true; logList.positionViewAtEnd() } }
                }
                Timer { id: logFilterTimer; interval: 150; onTriggered: bridge.filterLogs(logLevel.currentIndex === 1 ? "WARNING" : logLevel.currentIndex === 2 ? "ERROR" : "", logSearch.text) }
                ListView {
                    id: logList; objectName: "logList"
                    visible: page.logsOpen; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: bridge.logModel
                    ScrollBar.vertical: ScrollBar {}
                    onMovementStarted: page.followLogs = false
                    onCountChanged: Qt.callLater(function() { if (page.logsOpen && page.followLogs) logList.positionViewAtEnd() })
                    onVisibleChanged: if (visible && page.followLogs) Qt.callLater(positionViewAtEnd)
                    delegate: TextEdit {
                        required property string modelData
                        width: logList.width - 14; text: modelData
                        readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText
                        color: modelData.indexOf("ERROR") >= 0 ? "#fca5a5" : modelData.indexOf("WARNING") >= 0 ? "#fde68a" : "#e2e8f0"; font.family: "Consolas"; font.pixelSize: 13; wrapMode: TextEdit.Wrap
                    }
                    Text {
                        visible: logList.count === 0; width: parent.width
                        text: "暂无日志。离线演示和真实任务的记录将在这里显示。"
                        color: "#c7d4e8"; font.pixelSize: 12; wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
    Dialog {
        id: deleteLogsDialog; parent: Overlay.overlay; anchors.centerIn: parent; modal: true
        title: "删除当前目录的应用日志？"; width: Math.min(540, page.width); height: 260
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: Label { text: "将删除下列目录中由本应用命名的日志文件，并清空当前显示。此操作无法撤销。\n\n" + bridge.summary.logDirectory; wrapMode: Text.Wrap }
        onAccepted: bridge.deleteLogs()
    }
}
