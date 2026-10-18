import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    property string tone: "neutral"
    property string glyph: ""
    property bool subtle: false
    property color accent: ({connect: "#2563eb", execute: "#15803d", save: "#0f766e", test: "#7c3aed", danger: "#dc2626", warning: "#b45309", neutral: "#475569"})[tone] || "#475569"
    implicitHeight: 40
    implicitWidth: Math.max(72, contentItem.implicitWidth + 32)
    leftPadding: 16
    rightPadding: 16
    hoverEnabled: true
    Accessible.name: text
    contentItem: Row {
        spacing: 8
        Image {
            visible: control.glyph !== ""
            width: visible ? 16 : 0
            height: 16
            anchors.verticalCenter: parent.verticalCenter
            source: visible ? "../../assets/icons/" + control.glyph + (control.subtle || control.tone === "neutral" ? "" : "-white") + ".svg" : ""
            opacity: control.enabled ? 1 : .4
        }
        Text {
            text: control.text
            font.pixelSize: 13
            font.bold: true
            color: !control.enabled ? "#8590a2" : control.subtle || control.tone === "neutral" ? control.accent : "white"
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        radius: 7
        color: !control.enabled ? "#edf0f5" : control.down ? (control.subtle || control.tone === "neutral" ? "#dde5f0" : Qt.darker(control.accent, 1.15)) : control.subtle || control.tone === "neutral" ? (control.hovered ? "#e9eef6" : "#f4f6fa") : (control.hovered ? Qt.darker(control.accent, 1.08) : control.accent)
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#2563eb" : control.subtle || control.tone === "neutral" ? "#dce3ee" : "transparent"
    }
}
