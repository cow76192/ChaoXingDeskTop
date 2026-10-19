import QtQuick

WheelHandler {
    required property Flickable scrollTarget
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: function(event) {
        const delta = event.pixelDelta.y !== 0 ? event.pixelDelta.y : event.angleDelta.y / 120 * 136
        if (delta === 0) {
            event.accepted = false
            return
        }
        scrollTarget.cancelFlick()
        const top = scrollTarget.originY
        const bottom = top + Math.max(0, scrollTarget.contentHeight - scrollTarget.height)
        scrollTarget.contentY = Math.max(top, Math.min(bottom, scrollTarget.contentY - delta))
        event.accepted = true
    }
}
