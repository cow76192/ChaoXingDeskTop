import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    readonly property var workbenchSummary: bridge.summary
    id: page
    required property var groups
    property bool migration: false
    clip: true
    contentWidth: availableWidth
    PageWheelHandler { parent: page.contentItem; scrollTarget: page.contentItem }
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
            description: "分享排障信息请使用排障配置；完整 INI 含明文凭据，且不是全部数据备份。"
            RowLayout {
                ActionButton { text: "导入 INI"; tone: "save"; subtle: true; glyph: "import"; enabled: !workbenchSummary.busy; onClicked: bridge.fileAction("import_config") }
                ActionButton { objectName: page.migration ? "export_diagnostics" : ""; text: "导出排障配置"; tone: "save"; enabled: !workbenchSummary.busy; onClicked: bridge.fileAction("export_diagnostics") }
                ActionButton { text: "完整 INI（含凭据）"; tone: "warning"; subtle: true; glyph: "export"; enabled: !workbenchSummary.busy; onClicked: bridge.fileAction("export_config") }
            }
            NoticeBanner { tone: "warning"; message: "完整 INI 含明文密码和密钥，请仅自行保管。分享排障信息请使用「导出排障配置」。"; Layout.fillWidth: true }
            ActionButton { objectName: page.migration ? "data_explanation" : ""; text: "本机数据与备份说明"; onClicked: dataInfo.open() }
        }
        Item { Layout.preferredHeight: 8 }
    }
    ReadOnlyDialog {
        id: dataInfo; objectName: page.migration ? "dataInfoDialog" : ""; parent: Overlay.overlay; anchors.centerIn: parent; modal: true
        title: "本机数据与备份边界"; width: Math.min(660, page.width); height: Math.min(540, page.height)
        bodyText: bridge.dataExplanation
    }
}
