import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ActionDialog {
    id: dialog
    property string bodyText: ""
    property string noticeMessage: ""
    property string noticeTone: "info"
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    padding: 18
    cancelText: "关闭"
    background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6" }
    contentItem: ColumnLayout {
        NoticeBanner { message: dialog.noticeMessage; tone: dialog.noticeTone; Layout.fillWidth: true }
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
