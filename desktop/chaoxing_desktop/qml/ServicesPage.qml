import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    property var openSettings: ({})
    spacing: 16
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 78; radius: 12; color: "#edf2fc"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 16; spacing: 8
            Text { text: "01 题库查询     →     02 AI 补全     →     03 人工补全     →     04 随机补全"; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 14; font.bold: true; color: "#344d78" }
            Text { text: "仅处理前一步未解决的题目 · 随机补全默认关闭，自动提交独立控制"; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: "#475569" }
        }
    }
    RowLayout {
    Layout.fillWidth: true
    TabBar {
        id: tabs; objectName: "serviceTabs"; Layout.fillWidth: true
        TabButton { text: "服务连接" }
        TabButton { text: "答案处理" }
        TabButton { text: "结束通知" }
    }
    ActionButton { objectName: "service_ai_link"; text: "AI 设置"; visible: tabs.currentIndex === 0; onClicked: services.contentItem.contentY = Math.max(0, aiPanel.y - 8) }
    }
    StackLayout {
        Layout.fillWidth: true; Layout.fillHeight: true
        currentIndex: tabs.currentIndex
        ScrollView {
            id: services; clip: true; contentWidth: availableWidth
            GridLayout {
                width: services.availableWidth; columns: page.width > 880 ? 2 : 1; columnSpacing: 18; rowSpacing: 18
                Panel {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    title: "题库服务"
                    description: "勾选启用，按从上到下的顺序查询。可先填写凭据再启用。"
                    ActionButton { text: "离线协议自检"; enabled: !bridge.summary.busy; onClicked: bridge.offlineCheck() }
                    Text { text: bridge.summary.bankStatus; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#627086"; font.pixelSize: 12 }
                    Repeater {
                        model: bridge.providers
                        ColumnLayout {
                            required property var modelData
                            required property int index
                            property bool settingsOpen: !!page.openSettings[modelData.key]
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
                                ToolButton { text: "↑"; Accessible.name: "上移 " + modelData.title; enabled: !bridge.summary.busy && index > 0; onClicked: bridge.moveProvider(index, -1) }
                                ToolButton { text: "↓"; Accessible.name: "下移 " + modelData.title; enabled: !bridge.summary.busy && index < bridge.providers.length - 1; onClicked: bridge.moveProvider(index, 1) }
                            }
                            Field { spec: ({title: modelData.key === "TikuAdapter" ? "服务地址" : modelData.key === "TikuGo" ? "授权（可选）" : "Token", section: "question_bank", key: modelData.secret, kind: "secret", hint: "", low: 0, high: 100, choices: []}) }
                            ActionButton { objectName: "settings_" + modelData.key; text: parent.settingsOpen ? "收起独立设置" : "展开独立设置"; subtle: true; tone: "connect"; onClicked: { let next = Object.assign({}, page.openSettings); next[parent.modelData.key] = !parent.settingsOpen; page.openSettings = next } }
                            ColumnLayout {
                                visible: parent.settingsOpen; Layout.fillWidth: true
                                Repeater {
                                    model: bridge.schema[({TikuGo: "bank_go", TikuYanxi: "bank_yanxi", TikuLike: "bank_like", TikuAdapter: "bank_adapter", TikuDeclarative: "bank_declarative"})[modelData.key]][0].fields
                                    Field { required property var modelData; spec: modelData }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ActionButton { text: "真实连接检查…"; enabled: !bridge.summary.busy; onClicked: { bankConfirm.providerKey = modelData.key; bankConfirm.open() } }
                                ActionButton { visible: modelData.key === "TikuDeclarative"; text: "导入 JSON"; enabled: !bridge.summary.busy; onClicked: bridge.definitionAction("import") }
                                ActionButton { visible: modelData.key === "TikuDeclarative"; text: "导出模板"; enabled: !bridge.summary.busy; onClicked: bridge.definitionAction("export") }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#edf0f5" }
                        }
                    }
                }
                Panel {
                    id: aiPanel
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    title: "AI 补全"; description: "补全未解决的题目；需要服务与模型支持图片识别。"
                    Repeater { model: bridge.schema.ai[0].fields; Field { required property var modelData; spec: modelData } }
                    ActionButton { text: "测试 AI 连接"; tone: "test"; glyph: "test"; enabled: !bridge.summary.busy; onClicked: bridge.checkAi() }
                    Text { text: bridge.summary.aiStatus; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                Item { Layout.preferredHeight: 8 }
            }
        }
        FormPage { groups: bridge.schema.answers }
        FormPage { groups: bridge.schema.notification }
    }
    Dialog {
        id: bankConfirm; property string providerKey: ""
        title: "真实服务连接检查"; height: 200; modal: true; anchors.centerIn: parent; width: Math.min(page.width - 40, 520)
        background: Rectangle { color: "white"; radius: 12; border.color: "#dbe3ef" }
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: Text { text: "将发送一道最小测试题，可能消耗服务额度。检查不启动课程，也不保证后续命中或答案正确。"; wrapMode: Text.Wrap; color: "#34435a" }
        onAccepted: bridge.checkBank(providerKey)
    }
}
