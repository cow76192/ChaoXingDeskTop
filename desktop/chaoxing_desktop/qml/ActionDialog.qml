import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Dialog {
    id: dialog
    property string primaryText: ""
    property string primaryTone: "connect"
    property string cancelText: "取消"
    property bool primaryEnabled: true
    property bool autoAccept: true
    signal primaryTriggered()
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    padding: 18
    closePolicy: Popup.CloseOnEscape
    background: Rectangle { color: "white"; radius: 12; border.color: "#cdd7e6" }
    onOpened: if (primaryTone === "danger") cancelButton.forceActiveFocus()
    footer: Item {
        implicitHeight: 66
        RowLayout {
            anchors.fill: parent; anchors.margins: 14; spacing: 10
            Item { Layout.fillWidth: true }
            ActionButton {
                id: cancelButton
                objectName: dialog.objectName + "_cancel"
                text: dialog.cancelText
                onClicked: dialog.reject()
            }
            ActionButton {
                objectName: dialog.objectName + "_primary"
                visible: dialog.primaryText !== ""
                text: dialog.primaryText; tone: dialog.primaryTone
                enabled: dialog.primaryEnabled
                onClicked: { dialog.primaryTriggered(); if (dialog.autoAccept) dialog.accept() }
            }
        }
    }
}
