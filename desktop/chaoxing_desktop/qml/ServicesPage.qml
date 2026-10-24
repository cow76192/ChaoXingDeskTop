import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "servicesPage"
    property string serviceArea: "banks"
    property string selectedBank: ""
    ListModel { id: bankRows; dynamicRoles: true }
    function syncBanks() {
        let rows = bridge.providers
        for (let i = 0; i < rows.length; ++i) {
            let at = -1
            for (let j = i; j < bankRows.count; ++j) if (bankRows.get(j).modelData.key === rows[i].key) { at = j; break }
            if (at < 0) bankRows.insert(i, {modelData: rows[i]})
            else {
                if (at !== i) bankRows.move(at, i, 1)
                bankRows.setProperty(i, "modelData", rows[i])
            }
        }
    }
    Component.onCompleted: syncBanks()
    Connections { target: bridge; function onProvidersChanged() { page.syncBanks() } }
    spacing: 16
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 78; radius: 12; color: "#edf2fc"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 16; spacing: 8
            Text { text: tabs.currentIndex === 4 ? "01 发现活动     →     02 核实本人状态     →     03 逐题草稿     →     04 提交与分步核验" : tabs.currentIndex === 3 ? "01 识别话题     →     02 检查本人回复     →     03 生成草稿     →     04 发布与核验" : "01 题库查询     →     02 AI 补全     →     03 人工补全     →     04 随机补全"; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 14; font.bold: true; color: "#344d78" }
            Text { text: tabs.currentIndex === 4 ? "选择题与文本题分别配置 · 自动提交独立控制 · 提交未知时仅只读核验" : tabs.currentIndex === 3 ? "只处理章节必做讨论 · 发布与任务完成分别确认，未知结果不重复提交" : "仅处理前一步未解决的题目 · 随机补全默认关闭，自动提交独立控制"; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: "#475569" }
        }
    }
    RowLayout {
    Layout.fillWidth: true
    TabBar {
        id: tabs; objectName: "serviceTabs"; Layout.fillWidth: true
        TabButton { text: "服务连接" }
        TabButton { text: "答案处理" }
        TabButton { text: "结束通知" }
        TabButton { text: "讨论任务" }
        TabButton { text: "投票／问卷" }
    }
    ActionButton { objectName: "service_ai_link"; text: page.serviceArea === "ai" ? "题库列表" : "AI 设置"; visible: tabs.currentIndex === 0; onClicked: { page.serviceArea = page.serviceArea === "ai" ? "banks" : "ai"; services.contentItem.contentY = 0 } }
    }
    StackLayout {
        Layout.fillWidth: true; Layout.fillHeight: true
        currentIndex: tabs.currentIndex
        ScrollView {
            id: services; objectName: "servicesScroll"; clip: true; contentWidth: availableWidth
            PageWheelHandler { parent: services.contentItem; scrollTarget: services.contentItem }
            GridLayout {
                width: services.availableWidth; columns: page.width > 880 ? 2 : 1; columnSpacing: 18; rowSpacing: 18
                Panel {
                    visible: page.serviceArea === "banks"
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    title: "题库服务"
                    description: "勾选启用，按从上到下的顺序查询。可先填写凭据再启用。"
                    ActionButton { text: "离线协议自检"; enabled: !bridge.summary.busy; onClicked: bridge.offlineCheck() }
                    Text { text: bridge.summary.bankStatus; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#627086"; font.pixelSize: 12 }
                    Repeater {
                        model: bankRows
                        ColumnLayout {
                            id: bankEntry
                            required property var modelData
                            required property int index
                            property bool settingsOpen: page.selectedBank === modelData.key
                            Layout.fillWidth: true; spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Basic.CheckBox {
                                    id: bankCheck
                                    text: modelData.title; checked: modelData.enabled; enabled: !bridge.summary.busy; Layout.fillWidth: true; onToggled: bridge.toggleProvider(modelData.key, checked)
                                    indicator: Rectangle {
                                        implicitWidth: 20; implicitHeight: 20; x: bankCheck.leftPadding; y: (bankCheck.height - height) / 2
                                        radius: 4; color: bankCheck.checked ? "#2563eb" : "white"; border.color: bankCheck.activeFocus ? "#2563eb" : "#64748b"; border.width: 2
                                        Text { anchors.centerIn: parent; text: bankCheck.checked ? "✓" : ""; color: "white"; font.bold: true }
                                    }
                                }
                                Text { text: modelData.enabled ? "已启用" : "已关闭"; color: modelData.enabled ? "#15803d" : "#475569"; font.pixelSize: 12 }
                                ActionButton {
                                    objectName: "settings_" + modelData.key; text: parent.parent.settingsOpen ? "收起详情" : "配置详情"; subtle: true
                                    onClicked: {
                                        page.selectedBank = page.selectedBank === modelData.key ? "" : modelData.key
                                        if (page.selectedBank) Qt.callLater(function() {
                                            let view = services.contentItem
                                            view.contentY = Math.max(0, Math.min(view.contentHeight - view.height, bankEntry.mapToItem(view.contentItem, 0, 0).y - 8))
                                        })
                                    }
                                }
                                ToolButton { text: "↑"; Accessible.name: "上移 " + modelData.title; enabled: !bridge.summary.busy && index > 0; onClicked: bridge.moveProvider(index, -1) }
                                ToolButton { text: "↓"; Accessible.name: "下移 " + modelData.title; enabled: !bridge.summary.busy && index < bridge.providers.length - 1; onClicked: bridge.moveProvider(index, 1) }
                            }
                            Text { text: (index + 1) + " · " + (bridge.values.question_bank[modelData.secret] ? "已填写凭据 / 地址" : "凭据 / 地址未填") + " · " + bridge.serviceHealth[modelData.key]; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Field { visible: parent.settingsOpen; spec: ({title: modelData.key === "TikuAdapter" ? "服务地址" : modelData.key === "TikuGo" ? "授权（可选）" : "Token", section: "question_bank", key: modelData.secret, kind: "secret", hint: "", low: 0, high: 100, choices: []}) }
                            ColumnLayout {
                                visible: parent.settingsOpen; Layout.fillWidth: true
                                Repeater {
                                    model: bridge.schema[({TikuGo: "bank_go", TikuYanxi: "bank_yanxi", TikuLike: "bank_like", TikuAdapter: "bank_adapter", TikuDeclarative: "bank_declarative"})[modelData.key]][0].fields
                                    Field { required property var modelData; spec: modelData }
                                }
                            }
                            RowLayout {
                                visible: parent.settingsOpen
                                Layout.fillWidth: true
                                ActionButton { text: "真实连接检查…"; tone: "test"; subtle: true; enabled: !bridge.summary.busy; onClicked: { bankConfirm.providerKey = modelData.key; bankConfirm.providerTitle = modelData.title; bankConfirm.open() } }
                                ActionButton { visible: modelData.key === "TikuDeclarative"; text: "导入 JSON"; enabled: !bridge.summary.busy; onClicked: bridge.definitionAction("import") }
                                ActionButton { visible: modelData.key === "TikuDeclarative"; text: "导出模板"; enabled: !bridge.summary.busy; onClicked: bridge.definitionAction("export") }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#edf0f5" }
                        }
                    }
                }
                Panel {
                    id: aiPanel
                    visible: page.serviceArea === "ai" || page.width > 880
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    title: "AI 补全"; description: "补全未解决的题目；需要服务与模型支持图片识别。"
                    ActionButton { objectName: "ai_profiles_button"; text: "命名 AI 档案…"; enabled: !bridge.summary.busy; onClicked: { bridge.clearUiFeedback("profiles"); profiles.rows = bridge.listAiProfiles(); profiles.open() } }
                    Repeater { model: bridge.schema.ai[0].fields; Field { required property var modelData; spec: modelData } }
                    ActionButton { text: "测试 AI 连接…"; tone: "test"; glyph: "test"; enabled: !bridge.summary.busy; onClicked: aiConfirm.open() }
                    Text { text: bridge.serviceHealth.ai; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { text: "课程运行时，未解决题目的题干、选项及启用视觉后的图片链接会发往当前 AI 服务；讨论发送主题与正文，活动发送题干、选项与约束。不会自动切换服务。"; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { visible: !!bridge.aiWarning; text: bridge.aiWarning; color: "#995a0d"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                Item { Layout.preferredHeight: 8 }
            }
        }
        FormPage { objectName: "answersScroll"; groups: bridge.schema.answers }
        FormPage { objectName: "notificationScroll"; groups: bridge.schema.notification }
        DiscussionSettings {}
        ActivitySettings {}
    }
    ActionDialog {
        id: bankConfirm; objectName: "bankConfirmDialog"; property string providerKey: ""; property string providerTitle: ""
        title: "真实服务连接检查"; height: 280; modal: true; anchors.centerIn: parent; width: Math.min(page.width - 40, 520)
        background: Rectangle { color: "white"; radius: 12; border.color: "#dbe3ef" }
        primaryText: "发送测试题"; primaryTone: "test"
        contentItem: NoticeBanner { tone: "warning"; message: "检查服务：" + bankConfirm.providerTitle + "。将发送一道最小测试题，可能消耗服务额度。不会启动课程；连接可用不保证命中或答案正确。" }
        onAccepted: bridge.checkBank(providerKey)
    }
    ActionDialog {
        id: aiConfirm; objectName: "aiConfirmDialog"; parent: Overlay.overlay; anchors.centerIn: parent; modal: true
        title: "主动测试 AI 服务"; width: Math.min(page.width - 40, 520); height: 320
        primaryText: "发送测试请求"; primaryTone: "test"
        contentItem: NoticeBanner { tone: "warning"; message: "发送目标：" + bridge.aiDestination + "\n将发送“回复 OK”，可能消耗额度。不会读取课程、发送账号信息或提交答案。连接可用不代表答案正确或图片能力已验证。" }
        onAccepted: bridge.checkAi()
    }
    ActionDialog {
        id: profiles; objectName: "aiProfilesDialog"; property var rows: []
        parent: Overlay.overlay; anchors.centerIn: parent; modal: true
        title: "命名 AI 档案（本机加密）"; width: Math.min(660, page.width); height: Math.min(620, parent.height - 50)
        padding: 18
        background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6" }
        cancelText: "关闭"
        contentItem: ColumnLayout {
            Label { text: "现有 AI 配置继续可用，可保存为“默认档案”。档案含当前服务地址、模型、视觉声明、请求限制与独立凭据，均用 DPAPI 加密。最多 20 项，仅显式切换，不自动联网或切换提供商。视觉能力仍须主动测试。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Basic.TextField { id: profileName; objectName: "aiProfileName"; text: "默认档案"; maximumLength: 40; Layout.fillWidth: true; Accessible.name: "AI 档案名称" }
            ActionButton { objectName: "saveAiProfile"; text: "保存当前设置／覆盖同名档案"; tone: "save"; enabled: !bridge.summary.busy; onClicked: { bridge.aiProfileAction("save", profileName.text); profiles.rows = bridge.listAiProfiles() } }
            ChoiceBox { id: profileChoice; objectName: "aiProfileChoice"; enabled: profiles.rows.length > 0; model: profiles.rows; textRole: "name"; valueRole: "id"; Layout.fillWidth: true; Accessible.name: "选择 AI 档案" }
            RowLayout {
                ActionButton { objectName: "loadAiProfile"; text: "切换到所选档案"; tone: "connect"; enabled: !bridge.summary.busy && profiles.rows.length > 0; onClicked: bridge.aiProfileAction("load", profileChoice.currentValue || "") }
                ActionButton { objectName: "deleteAiProfile"; text: "删除所选档案…"; tone: "danger"; subtle: true; enabled: !bridge.summary.busy && profiles.rows.length > 0; onClicked: { bridge.clearUiFeedback("profiles"); deleteProfile.profileId = profileChoice.currentValue || ""; deleteProfile.profileName = profileChoice.currentText; deleteProfile.open() } }
            }
            NoticeBanner { visible: !profiles.rows.length && (bridge.uiFeedback.profiles || {}).tone !== "danger"; message: "暂无已保存的 AI 档案。填写名称后，可将当前配置保存为一个档案。"; Layout.fillWidth: true }
            OperationNotice { objectName: "profilesNotice"; scope: "profiles"; Layout.fillWidth: true }
            Label { text: "删除档案后保留当前已加载设置副本，不自动回退到其他服务。旧 INI 的当前配置不被替换，完整 INI 导出不包含这些加密档案；备份需同时保留 ai_profiles.json。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: "#627086" }
            Item { Layout.fillHeight: true }
        }
    }
    ActionDialog {
        id: deleteProfile; objectName: "deleteAiProfileDialog"
        property string profileId: ""; property string profileName: ""
        title: "删除 AI 档案？"; width: Math.min(550, page.width); height: Math.min(340, parent.height - 50)
        primaryText: "删除此档案"; primaryTone: "danger"; autoAccept: false
        contentItem: ColumnLayout {
            NoticeBanner { tone: "warning"; message: "将删除「" + deleteProfile.profileName + "」的本机加密档案，无法撤销。当前已加载设置保持，不会自动切换提供商。"; Layout.fillWidth: true }
            OperationNotice { scope: "profiles"; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
        }
        onPrimaryTriggered: if (bridge.aiProfileAction("delete", profileId)) { profiles.rows = bridge.listAiProfiles(); accept() }
    }
    ReadOnlyDialog {
        id: definitionPreview; objectName: "definitionPreview"
        property bool canImport: false
        title: canImport ? "导入前检查目标与映射" : "定义被拒绝（未导入）"
        width: Math.min(700, page.width); height: Math.min(560, parent.height - 50)
        primaryText: canImport ? "导入此定义" : ""; cancelText: canImport ? "取消" : "关闭"
        noticeMessage: canImport ? "请核对目标与映射，确认后替换当前定义；不会执行脚本或自动测试服务。" : "定义校验失败，尚未导入。请按下方原因修正文件后重试。"
        noticeTone: canImport ? "warning" : "danger"
        onAccepted: bridge.finishDefinitionImport(true)
        onRejected: bridge.finishDefinitionImport(false)
    }
    Connections {
        target: bridge
        function onDefinitionPreviewRequested(text, valid) {
            definitionPreview.canImport = valid; definitionPreview.bodyText = text; definitionPreview.open()
        }
        function onFieldRequested(section, key) {
            if (section === "ai") { tabs.currentIndex = 0; page.serviceArea = "ai" }
            else if (section === "notification") tabs.currentIndex = 2
            else if (section === "discussion") tabs.currentIndex = 3
            else if (section === "activity") tabs.currentIndex = 4
            else if (section === "desktop" || section === "matching" || section === "tiku") tabs.currentIndex = 1
            else if (section === "question_bank") {
                tabs.currentIndex = 0; page.serviceArea = "banks"
                for (let provider of bridge.providers) {
                    let groups = bridge.schema[({TikuGo: "bank_go", TikuYanxi: "bank_yanxi", TikuLike: "bank_like", TikuAdapter: "bank_adapter", TikuDeclarative: "bank_declarative"})[provider.key]]
                    if (provider.secret === key || groups[0].fields.some(function(spec) { return spec.key === key })) page.selectedBank = provider.key
                }
            }
        }
    }
}
