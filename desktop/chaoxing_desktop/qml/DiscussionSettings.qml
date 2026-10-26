import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    readonly property var workbenchSummary: bridge.summary
    id: page
    objectName: "discussionSettings"
    clip: true; contentWidth: availableWidth
    PageWheelHandler { parent: page.contentItem; scrollTarget: page.contentItem }
    GridLayout {
        width: page.availableWidth; columns: page.availableWidth > 880 ? 2 : 1
        columnSpacing: 18; rowSpacing: 18
        Panel {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            title: "讨论任务设置"
            description: "从章节识别话题、检查本人回复，再生成草稿并按设置发布。旧配置默认关闭。"
            Repeater { model: bridge.schema.discussion[0].fields; Field { required property var modelData; spec: modelData } }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                text: bridge.values.discussion.reply_level === "fixed_good" ? "固定发送单字好，AI 请求为 0。平台有字数要求时仍保留原文，不补字或换档。" : "精简 / 中等 / 详细复用 AI 连接；AI 不可用时保留待处理，不自动切换成固定好。"
                color: "#627086"; font.pixelSize: 12
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#e2e7ef" }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                text: "发布确认、任务点确认与讨论成绩分别记录。已有本人顶层回复不新增；提交结果未知时只读核验。运行中设置锁定，修改用于下一轮。"
                color: "#627086"; font.pixelSize: 12
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            title: "回复效果预览"
            contentSpacing: 10
            description: "前三档将发送下面的示例主题到 " + bridge.aiDestination + "，可能消耗额度；不读取课程或发布。固定好完全本地。"
            Label { text: "示例讨论主题"; color: "#34435a" }
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 75; clip: true
                TextArea {
                    id: topic; objectName: "discussionPreviewTopic"
                    text: "如何理解中国式现代化的中国特色？大学生如何为中国式现代化做贡献？"
                    enabled: !workbenchSummary.busy; wrapMode: TextEdit.Wrap; selectByMouse: true
                    textFormat: TextEdit.PlainText; color: "#17243a"; Accessible.name: "示例讨论主题"
                }
            }
            ActionButton {
                objectName: "discussionPreviewButton"
                text: bridge.values.discussion.reply_level === "fixed_good" ? "本地预览固定好" : "生成 AI 预览"
                tone: "connect"; enabled: !workbenchSummary.busy
                onClicked: bridge.previewDiscussion(topic.text)
            }
            Text { text: bridge.discussionPreview.reason; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 125; clip: true
                TextArea {
                    id: preview; objectName: "discussionPreviewContent"
                    text: bridge.discussionPreview.content; readOnly: true; selectByMouse: true
                    wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#17243a"
                    placeholderText: "生成后可在这里查看和选择复制完整正文"
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: Array.from(bridge.discussionPreview.content).length + " 字符"; color: "#627086"; font.pixelSize: 12; Layout.fillWidth: true }
                ActionButton { text: "复制预览"; enabled: !!preview.text; onClicked: { preview.selectAll(); preview.copy(); preview.deselect() } }
            }
        }
    }
}
