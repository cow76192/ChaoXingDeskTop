import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    required property var groups
    property bool migration: false
    clip: true
    contentWidth: availableWidth
    ColumnLayout {
        width: page.availableWidth
        spacing: 18
        Repeater {
            model: page.groups
            Panel {
                required property var modelData
                Layout.fillWidth: true
                title: modelData.title
                description: modelData.description
                GridLayout {
                    Layout.fillWidth: true
                    columns: page.width > 820 ? 2 : 1
                    columnSpacing: 28
                    rowSpacing: 18
                    Repeater { model: modelData.fields; Field { required property var modelData; spec: modelData } }
                }
            }
        }
        Panel {
            visible: page.migration
            Layout.fillWidth: true
            title: "配置迁移与备份"
            description: "旧版 INI 可直接导入。导出完整配置包含当前密码与密钥，请妥善保管。"
            RowLayout {
                ActionButton { text: "导入 INI"; tone: "save"; subtle: true; glyph: "import"; enabled: !bridge.summary.busy; onClicked: bridge.fileAction("import_config") }
                ActionButton { text: "导出完整 INI"; tone: "save"; subtle: true; glyph: "export"; enabled: !bridge.summary.busy; onClicked: bridge.fileAction("export_config") }
            }
        }
        Item { Layout.preferredHeight: 8 }
    }
}
