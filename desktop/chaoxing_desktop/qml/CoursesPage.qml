import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    property bool accountOpen: bridge.summary.courseCount === 0
    property bool showIds: false
    spacing: page.height < 540 ? 10 : 16
    ScrollView {
        id: accountScroll
        Layout.fillWidth: true
        implicitHeight: 260
        Layout.minimumHeight: 150
        Layout.preferredHeight: Math.min(accountPanel.implicitHeight, page.Window.height < 780 ? 240 : 340)
        Layout.maximumHeight: Math.max(180, page.Window.height - 460)
        clip: true; contentWidth: availableWidth
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AlwaysOn }
    Panel {
        id: accountPanel
        width: accountScroll.availableWidth
        title: "学习账户"
        description: bridge.summary.demo ? "离线演示已连接 · 当前均为示例数据" : "多个账号可同时保留登录会话，Cookie 按账号加密保存。切换后读取课程即可使用；密码仅用于当前会话。"
        RowLayout {
            Layout.fillWidth: true
            ChoiceBox {
                id: accounts
                objectName: "account_selector"
                Layout.fillWidth: true
                implicitHeight: 40
                model: bridge.accountRows
                textRole: "display"
                currentIndex: {
                    for (let i = 0; i < model.length; ++i)
                        if (model[i].id === bridge.summary.activeAccount) return i
                    return -1
                }
                displayText: currentIndex < 0 ? "新账号 · 填写下方信息或导入 Cookie" : currentText
                enabled: !bridge.summary.busy && !bridge.summary.accountError
                Accessible.name: "切换学习账号"
                onActivated: function(index) { bridge.switchAccount(model[index].id) }
            }
            ActionButton { objectName: "account_add"; text: "添加账号"; enabled: !bridge.summary.busy && !bridge.summary.accountError; onClicked: { bridge.addAccount(); page.accountOpen = true } }
            ActionButton { objectName: "account_delete"; text: "删除账号"; tone: "danger"; subtle: true; enabled: !bridge.summary.busy && bridge.summary.activeAccount !== ""; onClicked: deleteAccountDialog.open() }
        }
        Text { visible: bridge.summary.busy; text: "任务执行中，停止后可切换账号。"; color: "#627086"; font.pixelSize: 12 }
        Text { visible: !!bridge.summary.accountError; text: bridge.summary.accountError; color: "#be123c"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        RowLayout {
            Layout.fillWidth: true
            visible: page.accountOpen && bridge.summary.activeAccount !== ""
            Basic.TextField {
                id: accountLabel
                objectName: "account_label"
                Layout.fillWidth: true
                implicitHeight: 36
                placeholderText: "账号备注"
                text: accounts.currentIndex >= 0 ? accounts.model[accounts.currentIndex].label : ""
                enabled: !bridge.summary.busy
                Accessible.name: "账号备注"
            }
            ActionButton { text: "保存备注"; enabled: !bridge.summary.busy; onClicked: bridge.renameAccount(accountLabel.text) }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.accountOpen
            Basic.TextField { id: username; objectName: "account_username"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: "手机号 / 账号"; text: bridge.values.common.username; enabled: !bridge.summary.busy; readOnly: bridge.summary.activeAccount !== ""; Accessible.name: "学习账号"; onTextEdited: bridge.setValue("common", "username", text) }
            Basic.TextField { id: password; objectName: "account_password"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: "登录密码"; text: bridge.values.common.password; echoMode: TextInput.Password; enabled: !bridge.summary.busy; Accessible.name: "登录密码"; onTextEdited: bridge.setValue("common", "password", text) }
            ActionButton { objectName: "account_login"; text: bridge.summary.busy && bridge.summary.courseCount === 0 ? "读取中…" : "登录并读取"; tone: "connect"; glyph: "user"; enabled: !bridge.summary.busy && !bridge.summary.accountError; onClicked: bridge.fetchCourses() }
        }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { text: page.accountOpen ? "收起账户" : "重新连接"; onClicked: page.accountOpen = !page.accountOpen }
            CheckBox { visible: page.accountOpen; text: "Cookie 登录"; checked: bridge.values.common.use_cookies === "true"; enabled: !bridge.summary.busy; onToggled: bridge.setValue("common", "use_cookies", checked ? "true" : "false") }
            ActionButton { visible: page.accountOpen; text: "导入 Cookie"; enabled: !bridge.summary.busy; onClicked: bridge.fileAction("import_cookie") }
            ActionButton { visible: page.accountOpen && bridge.summary.cookie; text: "清除 Cookie"; tone: "danger"; subtle: true; enabled: !bridge.summary.busy; onClicked: bridge.fileAction("clear_cookie") }
            Item { Layout.fillWidth: true }
            ActionButton { text: "离线演示"; tone: "test"; subtle: true; glyph: "play"; enabled: !bridge.summary.busy; onClicked: bridge.loadDemo() }
        }
    }
    }
    Dialog {
        id: deleteAccountDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "删除当前账号？"
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "将删除该账号及本机保存的 Cookie。\n其他账号不会受影响，再次使用需重新登录。"; wrapMode: Text.Wrap }
        onAccepted: { bridge.removeAccount(); page.accountOpen = true }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "我的课程"; font.pixelSize: 19; font.bold: true; color: "#17243a" }
        Text { text: bridge.summary.courseCount + " 门"; color: "#627086"; font.pixelSize: 13 }
        Item { Layout.fillWidth: true }
        Basic.TextField { Layout.preferredWidth: 240; Layout.minimumWidth: 140; placeholderText: "搜索课程名称或 ID"; text: bridge.summary.courseSearch; Accessible.name: "搜索课程"; onTextEdited: bridge.searchCourses(text) }
        ActionButton { objectName: "courses_select_all"; text: "全选可见"; tone: "connect"; enabled: !bridge.summary.busy; onClicked: bridge.selectVisible(true) }
        ActionButton { objectName: "courses_clear_selection"; text: "取消选择"; tone: "warning"; subtle: true; enabled: !bridge.summary.busy; onClicked: bridge.selectVisible(false) }
        ActionButton { objectName: "courses_show_ids"; text: checked ? "隐藏 ID" : "显示 ID"; tone: "test"; subtle: true; checkable: true; onToggled: page.showIds = checked }
    }
    ListView {
        id: courseList
        objectName: "courseList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 100
        clip: true
        spacing: 12
        model: bridge.courseRows
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        PageWheelHandler { scrollTarget: courseList }
        delegate: Rectangle {
            required property var modelData
            required property int index
            width: courseList.width - 12
            height: page.showIds ? 96 : 82
            radius: 10
            color: modelData.selected ? "#f0f5ff" : "white"
            border.color: modelData.selected ? "#9dbbff" : "#e2e7ef"
            RowLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 16
                CheckBox { checked: modelData.selected; enabled: !bridge.summary.busy; Accessible.name: "选择 " + modelData.title; onToggled: bridge.selectCourse(String(modelData.courseId), String(modelData.clazzId), checked) }
                Rectangle {
                    Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 10; color: ["#e2eaff", "#ece6ff", "#dff2eb"][index % 3]
                    Image { anchors.centerIn: parent; width: 22; height: 22; source: "../../assets/icons/book.svg" }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 5
                    Text { text: modelData.title; font.pixelSize: 15; font.bold: true; color: "#17243a"; elide: Text.ElideRight; Layout.fillWidth: true; ToolTip.visible: titleHover.hovered; ToolTip.text: modelData.title; HoverHandler { id: titleHover } }
                    Text { text: (modelData.teacher ? modelData.teacher + " · " : "") + (modelData.desc || ("班级 " + modelData.clazzId)) + (page.showIds ? "  · 课程 " + modelData.courseId + " / 班级 " + modelData.clazzId : ""); font.pixelSize: 12; color: "#627086"; elide: Text.ElideRight; Layout.fillWidth: true }
                }
                Text { text: bridge.summary.demo ? "示例课程" : "可选择"; color: bridge.summary.demo ? "#7c3aed" : "#627086"; font.pixelSize: 12 }
            }
        }
        Column {
            visible: courseList.count === 0
            anchors.centerIn: parent
            spacing: 12
            width: courseList.width
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: bridge.summary.courseCount ? "没有匹配的课程" : "从连接账户开始"; color: "#17243a"; font.pixelSize: 18; font.bold: true }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; text: bridge.summary.courseCount ? "尝试其他关键词；隐藏课程的选择会保留。" : "读取课程，或点击「离线演示」体验完整流程。"; color: "#627086"; font.pixelSize: 12 }
        }
    }
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 76; radius: 12; color: "#172c4b"
        RowLayout {
            anchors.fill: parent; anchors.margins: 18; spacing: 18
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Text { text: "已选择 " + bridge.summary.selectedCount + " 门课程"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true }
                Text { text: bridge.summary.hiddenCount ? "包含 " + bridge.summary.hiddenCount + " 门被搜索隐藏的已选课程" : bridge.summary.demo ? "演示过程不会连接超星" : "按当前学习与答案策略处理所选课程"; color: "#b8c8df"; font.pixelSize: 12; Layout.fillWidth: true }
            }
            ActionButton { objectName: "strategy_button"; text: "查看本轮策略"; onClicked: { strategy.confirming = false; strategy.content = bridge.strategySummary; strategy.open() } }
            ActionButton { text: "开始所选课程"; tone: "execute"; glyph: "play"; enabled: bridge.summary.selectedCount > 0 && !bridge.summary.busy; onClicked: bridge.startTasks() }
        }
    }
    Connections {
        target: bridge
        function onStartConfirmationRequested(text) { strategy.confirming = true; strategy.content = text; strategy.open() }
    }
    ReadOnlyDialog {
        id: strategy; objectName: "strategyDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        property bool confirming: false
        property string content: ""
        title: confirming ? "确认本轮提交策略" : "本轮策略摘要"
        modal: true; width: Math.min(620, page.width); height: Math.min(520, page.height)
        standardButtons: confirming ? Dialog.Ok | Dialog.Cancel : Dialog.Close
        bodyText: strategy.content
        onAccepted: if (confirming) bridge.confirmStartTasks()
        onRejected: bridge.cancelStartTasks()
    }
}
