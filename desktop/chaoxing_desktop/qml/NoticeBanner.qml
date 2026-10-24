import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: notice
    property string message: ""
    property string tone: "info"
    property real maximumHeight: 150
    readonly property string heading: ({danger: "操作失败", warning: "请注意", success: "已完成", info: "提示"})[tone] || "提示"
    readonly property color accent: ({danger: "#b42323", warning: "#8a4b08", success: "#187044", info: "#344d78"})[tone] || "#344d78"
    visible: message !== ""
    implicitHeight: visible ? Math.min(messageText.implicitHeight + 24, maximumHeight) : 0
    color: ({danger: "#ffecec", warning: "#fff3df", success: "#e8f4ed", info: "#edf2fb"})[tone] || "#edf2fb"
    radius: 8; border.color: accent
    Accessible.name: heading + "：" + message
    RowLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 10
        Text { text: notice.tone === "danger" || notice.tone === "warning" ? "!" : notice.tone === "success" ? "+" : "i"; color: notice.accent; font.bold: true; font.pixelSize: 19; Layout.alignment: Qt.AlignTop }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            TextArea {
                id: messageText
                text: notice.heading + " · " + notice.message
                readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                color: notice.accent; font.pixelSize: 13; padding: 0; background: null
                Accessible.name: text
            }
        }
    }
}
