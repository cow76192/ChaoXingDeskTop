import QtQuick
import QtQuick.Layouts

Rectangle {
    id: panel
    property string title: ""
    property string description: ""
    default property alias content: body.data
    color: "white"
    radius: 12
    border.color: "#e2e7ef"
    implicitHeight: column.implicitHeight + 40
    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
        spacing: 6
        Text { visible: panel.title !== ""; text: panel.title; font.pixelSize: 17; font.bold: true; color: "#17243a"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Text { visible: panel.description !== ""; text: panel.description; font.pixelSize: 12; color: "#627086"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        ColumnLayout { id: body; Layout.fillWidth: true; Layout.topMargin: panel.title ? 12 : 0; spacing: 16 }
    }
}
