import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    objectName: "activitySettings"
    clip: true; contentWidth: availableWidth
    PageWheelHandler { parent: page.contentItem; scrollTarget: page.contentItem }
    GridLayout {
        width: page.availableWidth; columns: page.availableWidth > 880 ? 2 : 1
        columnSpacing: 18; rowSpacing: 18
        Panel {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            title: "投票／问卷任务设置"
            description: "发现章节活动 → 核实本人状态 → 生成草稿 → 校验与提交 → 分步核验"
            Repeater {
                model: bridge.schema.activity[0].fields
                Field {
                    required property var modelData
                    spec: modelData
                    enabled: !bridge.summary.busy && (modelData.key !== "reply_level" || bridge.values.activity.text_strategy === "ai")
                }
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                text: "选择题策略与文本策略分别生效。随机和固定好不调用 AI；前三档文本复用共享服务。主观选择只作建议，不代表个人真实观点，不显示虚构正确率或成绩。"
                color: "#627086"; font.pixelSize: 12
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#e2e7ef" }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                text: "整卷结构完整且所有题目通过约束校验才允许提交。提交结果未知时保留原意图，仅只读核验。运行中设置锁定，修改用于下一轮。"
                color: "#627086"; font.pixelSize: 12
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            title: "混合问卷示例预览"
            description: "AI 策略将发送下方示例题干与内置选项到 " + bridge.aiDestination + "，可能消耗额度；随机 + 固定好完全本地。预览不读取课程、不提交、不写活动记录。"
            Label { text: "示例文本题干"; color: "#34435a" }
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 75; clip: true
                TextArea {
                    id: topic; objectName: "activityPreviewTopic"
                    text: "你对本课程的学习体验有哪些建议？"
                    enabled: !bridge.summary.busy; wrapMode: TextEdit.Wrap; selectByMouse: true
                    textFormat: TextEdit.PlainText; color: "#17243a"; Accessible.name: "示例问卷文本题干"
                }
            }
            ActionButton {
                objectName: "activityPreviewButton"
                text: bridge.values.activity.choice_strategy === "random" && bridge.values.activity.text_strategy === "fixed_good" ? "生成本地示例" : "生成 AI 示例预览"
                tone: "connect"; enabled: !bridge.summary.busy
                onClicked: bridge.previewActivity(topic.text)
            }
            Text { text: bridge.activityPreview.reason; color: "#627086"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 290; clip: true
                TextArea {
                    id: preview; objectName: "activityPreviewContent"
                    text: bridge.activityPreview.content; readOnly: true; selectByMouse: true
                    wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; color: "#17243a"
                    placeholderText: "逐题显示题干、选项、所选答案或正文、来源与校验结果"
                }
            }
            ActionButton { text: "复制逐题预览"; enabled: !!preview.text; onClicked: { preview.selectAll(); preview.copy(); preview.deselect() } }
        }
    }
}
