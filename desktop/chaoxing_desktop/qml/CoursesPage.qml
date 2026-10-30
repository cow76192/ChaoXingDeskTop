import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    readonly property var workbenchSummary: bridge.summary
    id: page
    property bool accountOpen: workbenchSummary.courseCount === 0
    property bool showIds: false
    spacing: page.height < 540 ? 10 : 16
    ScrollView {
        id: accountScroll
        objectName: "accountScroll"
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
        description: workbenchSummary.demo ? "离线演示已连接 · 当前均为示例数据" : "多个账号可同时保留登录会话，Cookie 按账号加密保存。切换后读取课程即可使用；密码仅用于当前会话。"
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
                        if (model[i].id === workbenchSummary.activeAccount) return i
                    return -1
                }
                displayText: currentIndex < 0 ? "新账号 · 浏览器登录或导入 Cookie" : currentText
                enabled: !workbenchSummary.busy && !workbenchSummary.accountError
                Accessible.name: "切换学习账号"
                onActivated: function(index) { bridge.switchAccount(model[index].id) }
            }
            ActionButton { objectName: "account_add"; text: "添加账号"; enabled: !workbenchSummary.busy && !workbenchSummary.accountError; onClicked: { bridge.addAccount(); page.accountOpen = true } }
            ActionButton { objectName: "account_delete"; text: "删除账号"; tone: "danger"; subtle: true; enabled: !workbenchSummary.busy && workbenchSummary.activeAccount !== ""; onClicked: deleteAccountDialog.open() }
        }
        Text { visible: workbenchSummary.busy; text: workbenchSummary.browserLogin ? "请在浏览器完成登录，程序将自动连接账号。" : "任务执行中，停止后可切换账号。"; color: "#627086"; font.pixelSize: 12 }
        Text { visible: !!workbenchSummary.accountError; text: workbenchSummary.accountError; color: "#be123c"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { objectName: "account_browser_login"; text: "浏览器登录"; tone: "connect"; glyph: "user"; enabled: !workbenchSummary.busy && !workbenchSummary.accountError; onClicked: bridge.browserLogin() }
            ActionButton { objectName: "account_browser_cancel"; visible: !!workbenchSummary.browserLogin; text: "取消浏览器登录"; onClicked: bridge.cancelBrowserLogin() }
            Text { Layout.fillWidth: true; text: "支持扫码 / 网页登录，成功后自动获取 Cookie 并读取课程"; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.accountOpen && workbenchSummary.activeAccount !== ""
            Basic.TextField {
                id: accountLabel
                objectName: "account_label"
                Layout.fillWidth: true
                implicitHeight: 36
                placeholderText: "账号备注"
                text: accounts.currentIndex >= 0 ? accounts.model[accounts.currentIndex].label : ""
                enabled: !workbenchSummary.busy
                Accessible.name: "账号备注"
            }
            ActionButton { text: "保存备注"; enabled: !workbenchSummary.busy; onClicked: bridge.renameAccount(accountLabel.text) }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.accountOpen
            Basic.TextField { id: username; objectName: "account_username"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: "手机号 / 账号"; text: bridge.values.common.username; enabled: !workbenchSummary.busy; readOnly: workbenchSummary.activeAccount !== ""; Accessible.name: "学习账号"; onTextEdited: bridge.setValue("common", "username", text) }
            Basic.TextField { id: password; objectName: "account_password"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: "登录密码"; text: bridge.values.common.password; echoMode: TextInput.Password; enabled: !workbenchSummary.busy; Accessible.name: "登录密码"; onTextEdited: bridge.setValue("common", "password", text) }
            ActionButton { objectName: "account_login"; text: workbenchSummary.busy && workbenchSummary.courseCount === 0 ? "读取中…" : "登录并读取"; tone: "connect"; glyph: "user"; enabled: !workbenchSummary.busy && !workbenchSummary.accountError; onClicked: bridge.fetchCourses() }
        }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { text: page.accountOpen ? "收起账户" : "重新连接"; onClicked: page.accountOpen = !page.accountOpen }
            CheckBox { visible: page.accountOpen; text: "Cookie 登录"; checked: bridge.values.common.use_cookies === "true"; enabled: !workbenchSummary.busy; onToggled: bridge.setValue("common", "use_cookies", checked ? "true" : "false") }
            ActionButton { visible: page.accountOpen; text: "导入 Cookie"; enabled: !workbenchSummary.busy; onClicked: bridge.fileAction("import_cookie") }
            ActionButton { visible: page.accountOpen && workbenchSummary.cookie; text: "清除 Cookie"; tone: "danger"; subtle: true; enabled: !workbenchSummary.busy; onClicked: bridge.fileAction("clear_cookie") }
            Item { Layout.fillWidth: true }
            ActionButton { text: "离线演示"; tone: "test"; subtle: true; glyph: "play"; enabled: !workbenchSummary.busy; onClicked: bridge.loadDemo() }
        }
    }
    }
    ActionDialog {
        id: deleteAccountDialog; objectName: "deleteAccountDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "删除当前账号？"
        width: Math.min(550, page.width); height: 280
        primaryText: "删除此账号"; primaryTone: "danger"
        contentItem: NoticeBanner { tone: "warning"; message: "将删除「" + accounts.currentText + "」及其本机 Cookie。其他账号不受影响，再次使用需重新登录。" }
        onAccepted: { bridge.removeAccount(); page.accountOpen = true }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "我的课程"; font.pixelSize: 19; font.bold: true; color: "#17243a" }
        Text { text: workbenchSummary.courseCount + " 门"; color: "#627086"; font.pixelSize: 13 }
        Item { Layout.fillWidth: true }
        Basic.TextField { Layout.preferredWidth: 240; Layout.minimumWidth: 140; placeholderText: "搜索课程名称或 ID"; text: workbenchSummary.courseSearch; Accessible.name: "搜索课程"; onTextEdited: bridge.searchCourses(text) }
        ActionButton { objectName: "courses_select_all"; text: "全选可见"; tone: "connect"; enabled: !workbenchSummary.busy; onClicked: bridge.selectVisible(true) }
        ActionButton { objectName: "courses_clear_selection"; text: "取消选择"; tone: "warning"; subtle: true; enabled: !workbenchSummary.busy; onClicked: bridge.selectVisible(false) }
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
                CheckBox { checked: modelData.selected; enabled: !workbenchSummary.busy; Accessible.name: "选择 " + modelData.title; onToggled: bridge.selectCourse(String(modelData.courseId), String(modelData.clazzId), checked) }
                Rectangle {
                    Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 10; color: ["#e2eaff", "#ece6ff", "#dff2eb"][index % 3]
                    Image { anchors.centerIn: parent; width: 22; height: 22; source: "../../assets/icons/book.svg" }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 5
                    Text { text: modelData.title; font.pixelSize: 15; font.bold: true; color: "#17243a"; elide: Text.ElideRight; Layout.fillWidth: true; ToolTip.visible: titleHover.hovered; ToolTip.text: modelData.title; HoverHandler { id: titleHover } }
                    Text { text: (modelData.teacher ? modelData.teacher + " · " : "") + (modelData.desc || ("班级 " + modelData.clazzId)) + (page.showIds ? "  · 课程 " + modelData.courseId + " / 班级 " + modelData.clazzId : ""); font.pixelSize: 12; color: "#627086"; elide: Text.ElideRight; Layout.fillWidth: true }
                }
                ColumnLayout {
                    objectName: "course_progress_" + modelData.courseId + "_" + modelData.clazzId
                    Layout.preferredWidth: 175
                    Layout.minimumWidth: 175
                    Layout.maximumWidth: 175
                    spacing: 5
                    property var progress: modelData.progress || ({})
                    property bool hasProgress: progress.total !== undefined
                    Text {
                        Layout.alignment: Qt.AlignRight
                        text: workbenchSummary.demo ? "示例课程" : parent.hasProgress
                              ? (parent.progress.total === 0 ? "暂无章节" : "已完成 " + parent.progress.completed + " / " + parent.progress.total + " 章")
                              : parent.progress.loading ? "统计中…" : parent.progress.failed ? "统计失败" : "待统计"
                        color: parent.hasProgress && parent.progress.total > 0 && parent.progress.completed === parent.progress.total ? "#16804a" : "#627086"
                        font.pixelSize: 12
                        Accessible.name: modelData.title + " · " + text
                    }
                    ProgressBar {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        visible: !workbenchSummary.demo && parent.hasProgress && parent.progress.total > 0
                        from: 0; to: Math.max(1, parent.progress.total || 0); value: parent.progress.completed || 0
                        Layout.preferredHeight: 5
                    }
                    Text {
                        Layout.alignment: Qt.AlignRight
                        visible: !workbenchSummary.demo && parent.hasProgress
                        text: parent.progress.loading ? (parent.progress.cached ? "缓存 · 统计中…" : "统计中…")
                              : parent.progress.failed ? "更新失败 · 保留上次统计"
                              : parent.progress.cached ? "本地缓存" : "已更新"
                        color: "#8290a3"; font.pixelSize: 10
                        ToolTip.visible: progressHover.hovered
                        ToolTip.text: parent.progress.checked_at ? "章节进度更新时间：" + parent.progress.checked_at : ""
                        HoverHandler { id: progressHover }
                    }
                }
            }
        }
        Column {
            visible: courseList.count === 0
            anchors.centerIn: parent
            spacing: 12
            width: courseList.width
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: workbenchSummary.courseCount ? "没有匹配的课程" : "从连接账户开始"; color: "#17243a"; font.pixelSize: 18; font.bold: true }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; text: workbenchSummary.courseCount ? "尝试其他关键词；隐藏课程的选择会保留。" : "读取课程，或点击「离线演示」体验完整流程。"; color: "#627086"; font.pixelSize: 12 }
        }
    }
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 76; radius: 12; color: "#172c4b"
        RowLayout {
            anchors.fill: parent; anchors.margins: 18; spacing: 18
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Text { text: "已选择 " + workbenchSummary.selectedCount + " 门课程"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true }
                Text { text: workbenchSummary.hiddenCount ? "包含 " + workbenchSummary.hiddenCount + " 门被搜索隐藏的已选课程" : workbenchSummary.demo ? "演示过程不会连接超星" : "按当前学习与答案策略处理所选课程"; color: "#b8c8df"; font.pixelSize: 12; Layout.fillWidth: true }
            }
            ActionButton { objectName: "strategy_button"; text: "查看本轮策略"; onClicked: { strategy.confirming = false; strategy.content = bridge.strategySummary; strategy.open() } }
            ActionButton { text: "开始所选课程"; tone: "execute"; glyph: "play"; enabled: workbenchSummary.selectedCount > 0 && !workbenchSummary.busy; onClicked: bridge.startTasks() }
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
        primaryText: confirming ? "按此策略开始" : ""; primaryTone: "execute"; cancelText: confirming ? "返回检查" : "关闭"
        noticeMessage: confirming ? "本轮包含自动提交策略。请核对以下账号、课程和独立提交开关后再开始。" : ""
        noticeTone: "warning"
        bodyText: strategy.content
        onAccepted: if (confirming) bridge.confirmStartTasks()
        onRejected: bridge.cancelStartTasks()
    }
}
