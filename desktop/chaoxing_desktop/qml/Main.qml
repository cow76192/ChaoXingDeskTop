import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    width: 1280; height: 860; minimumWidth: 980; minimumHeight: 700
    visible: true
    title: "超星学习工作台 · " + bridge.version
    color: "#f6f7fb"
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 14
    palette.window: "#f6f7fb"
    palette.windowText: "#17243a"
    palette.base: "white"
    palette.text: "#17243a"
    palette.buttonText: "#34435a"
    palette.placeholderText: "#627086"
    palette.button: "#f4f6fa"
    palette.highlight: "#2563eb"
    palette.highlightedText: "white"
    property int pageIndex: 0
    property var pages: [
        {title: "课程与账号", description: "连接账户，选择课程，开启学习任务。", icon: "book"},
        {title: "学习设置", description: "设置学习节奏与章节处理策略。", icon: "settings"},
        {title: "题库与 AI", description: "连接答题服务，配置你的补全流程。", icon: "services"},
        {title: "高级设置", description: "管理请求参数、识别规则与配置备份。", icon: "tools"},
        {title: "任务与日志", description: "关注处理进度，检查结果与待处理事项。", icon: "activity"}
    ]
    property bool discardedClose: false
    onClosing: close => {
        close.accepted = discardedClose || bridge.close()
        if (!close.accepted) closeFailure.open()
    }
    ActionDialog {
        id: closeFailure; objectName: "closeFailureDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        title: "退出前保存未完成"; modal: true; width: Math.min(550, window.width - 60); height: Math.min(370, window.height - 50)
        primaryText: "放弃修改并退出"; primaryTone: "danger"; cancelText: "返回修正"; autoAccept: false
        contentItem: ColumnLayout {
            NoticeBanner { message: bridge.summary.message; tone: "danger"; Layout.fillWidth: true }
            Label { text: "返回修正后可再次保存。放弃会停止后台并退出，磁盘上的原设置保留。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
        }
        onPrimaryTriggered: if (bridge.discardAndClose()) { window.discardedClose = true; window.close() }
    }
    Connections { target: bridge; function onPageRequested(index) { window.pageIndex = index } }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: window.width < 1100 ? 184 : 216; Layout.fillHeight: true; color: "#eef2f8"
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 8
                RowLayout {
                    Layout.topMargin: 18; spacing: 12
                    Rectangle { width: 40; height: 40; radius: 10; color: "#2563eb"; Image { anchors.centerIn: parent; width: 23; height: 23; source: "../../assets/icons/book-white.svg" } }
                    Column {
                        spacing: 3
                        Text { text: "超星"; font.bold: true; font.pixelSize: 21; color: "#17243a" }
                        Text { text: "学习工作台"; font.pixelSize: 12; color: "#627086" }
                    }
                }
                Text { text: "WORKSPACE"; font.pixelSize: 10; font.letterSpacing: 1.4; color: "#627086"; Layout.topMargin: 34; Layout.bottomMargin: 8 }
                Repeater {
                    model: window.pages
                    delegate: AbstractButton {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true; Layout.preferredHeight: 46
                        hoverEnabled: true
                        Accessible.name: modelData.title
                        onClicked: window.pageIndex = index
                        background: Rectangle { radius: 8; color: window.pageIndex === index ? "#dce8ff" : parent.hovered ? "#e5ebf5" : "transparent"; border.width: parent.activeFocus ? 2 : 0; border.color: "#2563eb" }
                        contentItem: Row {
                            spacing: 13; leftPadding: 14
                            Image { width: 18; height: 18; source: "../../assets/icons/" + modelData.icon + ".svg"; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData.title; font.pixelSize: 14; font.bold: window.pageIndex === index; color: window.pageIndex === index ? "#2563eb" : "#53637c"; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle {
                    visible: window.width >= 1100
                    Layout.fillWidth: true; Layout.preferredHeight: 90; radius: 10; color: "#e3eaf5"
                    Column { anchors.fill: parent; anchors.margins: 13; spacing: 8
                        Text { text: "本地运行 · 数据由你管理"; font.pixelSize: 12; font.bold: true; color: "#53637c" }
                        Text { text: "服务凭据在本机加密保存\n登录密码仅用于当前会话"; font.pixelSize: 11; color: "#627086"; lineHeight: 1.4 }
                    }
                }
                ActionButton { objectName: "release_info_button"; text: "v" + bridge.version + " · 版本与校验"; Layout.fillWidth: true; onClicked: releaseInfo.open() }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: window.height < 780 ? 16 : 24; spacing: window.height < 780 ? 10 : 16
            GridLayout {
                columns: window.width < 1100 ? 1 : 2
                Layout.fillWidth: true; columnSpacing: 14; rowSpacing: 6
                RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    Text { text: window.pages[window.pageIndex].title; font.pixelSize: 26; font.bold: true; color: "#17243a"; Layout.fillWidth: true }
                    Text { visible: window.width >= 1100; text: window.pages[window.pageIndex].description; font.pixelSize: 12; color: "#627086"; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                BusyIndicator { visible: bridge.summary.busy; running: visible; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
                Text { text: bridge.summary.mode; font.pixelSize: 12; color: bridge.summary.demo ? "#7c3aed" : "#627086"; Layout.maximumWidth: 160; elide: Text.ElideRight }
                }
                RowLayout {
                Layout.alignment: Qt.AlignRight
                ActionButton { visible: bridge.summary.busy; text: bridge.summary.paused ? "恢复" : "暂停后续"; enabled: !bridge.summary.stopping; onClicked: bridge.pause() }
                ActionButton { visible: bridge.summary.busy; text: bridge.summary.stopping ? "停止中…" : "停止任务"; tone: "danger"; glyph: "stop"; enabled: !bridge.summary.stopping; onClicked: bridge.stop() }
                ActionButton { text: "保存设置"; tone: "save"; glyph: "save"; enabled: !bridge.summary.busy; onClicked: bridge.save() }
                }
            }
            NoticeBanner { objectName: "globalNotice"; Layout.fillWidth: true; message: bridge.summary.message; tone: bridge.summary.tone; maximumHeight: 100 }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: window.pageIndex
                CoursesPage {}
                FormPage { groups: bridge.schema.learning }
                ServicesPage {}
                FormPage { objectName: "advancedScroll"; groups: bridge.schema.advanced; migration: true }
                MonitorPage {}
            }
            RowLayout {
                Layout.fillWidth: true
                Rectangle { width: 7; height: 7; radius: 4; color: bridge.summary.saveState.indexOf("失败") >= 0 ? "#dc2626" : bridge.summary.saveState.indexOf("未保存") >= 0 ? "#b45309" : "#15803d" }
                Text { text: bridge.summary.saveState; color: "#627086"; font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                Text { text: bridge.summary.demo ? "离线演示 · 所有课程与任务均为示例" : "学习工作台 · Qt Quick"; color: "#627086"; font.pixelSize: 11 }
            }
        }
    }
    InputDialog {}
    DraftEditor {}
    ReadOnlyDialog {
        id: releaseInfo; objectName: "releaseInfoDialog"
        title: "版本、发行说明与校验信息"; width: Math.min(720, window.width - 50); height: Math.min(610, window.height - 50)
        bodyText: bridge.releaseInfo
        onOpened: bridge.clearUiFeedback("release")
        footer: ColumnLayout {
            OperationNotice { objectName: "releaseNotice"; scope: "release"; Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18 }
            RowLayout {
            Layout.fillWidth: true; Layout.margins: 14
            ActionButton { objectName: "release_latest"; text: "检查版本网页…"; onClicked: bridge.releaseAction("latest") }
            ActionButton { text: "发行说明…"; onClicked: bridge.releaseAction("notes") }
            ActionButton { objectName: "copy_verification_info"; text: "复制校验说明"; onClicked: bridge.releaseAction("copy") }
            Item { Layout.fillWidth: true }
            ActionButton { text: "关闭"; onClicked: releaseInfo.close() }
            }
        }
    }
}
