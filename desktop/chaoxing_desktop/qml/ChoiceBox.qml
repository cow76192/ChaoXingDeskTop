import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.ComboBox {
    id: control
    implicitHeight: 40
    implicitWidth: 180
    leftPadding: 12
    rightPadding: 36
    hoverEnabled: true
    // Scrolling a form must not silently change its current setting.
    wheelEnabled: false

    contentItem: Text {
        text: control.displayText
        font: control.font
        color: control.enabled ? "#17243a" : "#64748b"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        text: control.popup.visible ? "▴" : "▾"
        x: control.width - width - 12
        y: (control.height - height) / 2
        color: control.enabled ? "#34435a" : "#64748b"
        font.pixelSize: 18
    }
    background: Rectangle {
        radius: 6
        color: control.enabled ? "white" : "#f0f2f6"
        border.width: control.activeFocus || control.popup.visible ? 2 : 1
        border.color: control.activeFocus || control.popup.visible ? "#2563eb" : control.hovered ? "#64748b" : "#94a3b8"
    }
    delegate: Basic.ItemDelegate {
        id: option
        required property int index
        readonly property bool selected: index === control.currentIndex
        objectName: control.objectName + "_option_" + index
        width: ListView.view.width
        implicitHeight: 40
        text: control.textAt(index)
        highlighted: control.highlightedIndex === index
        hoverEnabled: true
        contentItem: Text {
            text: option.text
            leftPadding: 28
            rightPadding: 10
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.bold: option.selected
            color: option.selected ? "white" : "#17243a"
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 4
            color: option.selected ? "#2563eb" : option.highlighted || option.hovered ? "#e8efff" : "white"
            border.width: option.highlighted ? 2 : 0
            border.color: option.selected ? "#1e40af" : "#93b4fb"
        }
        Canvas {
            visible: option.selected
            x: 8
            width: 16
            height: 16
            anchors.verticalCenter: parent.verticalCenter
            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.strokeStyle = "white"
                context.lineWidth = 2
                context.lineCap = "round"
                context.lineJoin = "round"
                context.beginPath()
                context.moveTo(3, 8)
                context.lineTo(7, 12)
                context.lineTo(13, 4)
                context.stroke()
            }
        }
    }
    popup: Basic.Popup {
        y: control.height + 4
        width: control.width
        height: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 320,
                         control.Window.height - topMargin - bottomMargin)
        topMargin: 12
        bottomMargin: 12
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            highlightMoveDuration: 0
            boundsBehavior: Flickable.StopAtBounds
            Basic.ScrollBar.vertical: Basic.ScrollBar {}
        }
        background: Rectangle { color: "white"; radius: 7; border.color: "#94a3b8" }
    }
}
