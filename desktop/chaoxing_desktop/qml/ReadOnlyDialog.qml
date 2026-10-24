import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Dialog {
    id: dialog
    property string bodyText: ""
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    padding: 18
    standardButtons: Dialog.Close
    background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6" }
    contentItem: ColumnLayout {
        ScrollView {
            id: scroll
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; contentWidth: availableWidth
            TextArea {
                text: dialog.bodyText
                readOnly: true; selectByMouse: true
                wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                color: "#17243a"; font.pixelSize: 14
                verticalAlignment: TextEdit.AlignTop
                background: null
            }
        }
    }
}
