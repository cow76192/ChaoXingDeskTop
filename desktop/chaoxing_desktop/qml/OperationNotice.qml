import QtQuick

NoticeBanner {
    property string scope: ""
    message: (bridge.uiFeedback[scope] || {}).message || ""
    tone: (bridge.uiFeedback[scope] || {}).tone || "info"
}
