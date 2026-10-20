# 超星章节讨论协议记录

核实日期：2026-10-19。独立实现；来源为用户授权访问的标准学生网页、超星官方网页脚本和一次实际顶层回复验收。以下仅记录协议结构，不含账号、真实课程 ID、同学回复、Cookie、临时签名或原始页面。未引入浏览器运行依赖。

## 识别与身份

- 章节 cards HTML 中 `iframe` 的 pathname 为 `/ananas/modules/insertbbs/index.html`，忽略版本参数。读取 JSON `data`，通过 `mid` 匹配 `mArg.attachments[].property.mid`，不按标题或数组次序关联。
- 必做资格来自匹配附件明确的布尔 `job=true`；`false` 跳过，缺失 / 非布尔保留待处理。`isPassed=true` 不再发帖。`jobid` 与 `_jobid` 保留原语义。
- `/mooc-ans/bbscircle/chapter` 参数为 `mtopicid`、`jobid`、`isPortal=false`、`knowledgeid`、`ut=s`、`clazzId`、`enc`、`utenc`、`courseid`、`isJob=true`。`enc` 来自匹配附件；不以其他签名替代 `utenc`。所测官方模块在缺少 `top.utEnc` 时序列化为字符串 `undefined`，该分支已实际读通；有原值时优先使用原值。
- 入口返回 `#topicMainDiv[data]`，其 `data` 是详情地址；`input#isFinished` 是此服务器返回的关联任务状态。只接受标准 groupweb v3 路径 `/course/topic/v3/bbs/{bbsid}/{topicUUID}/replysList?courseId=…&classId=…`。
- 详情 HTML 的 `window.obj` 中包含 JSON 字面量 `user`、`topic`、`course`、`circle` 与字符串 `urlToken`。只解析这些字面量，不执行 JS。比较 `user.puid` 与当前平台账号 UID，校验 `course.courseId/classId`、`topic.chapterId`、`topic.uuid/bbsid`、`circle.bbsid`、`topic.quoteInfo.jobId`。模块 mid、话题 UUID、数值 `topic.id` 分开保存。

## 本人回复

官方 `topicInvitation.js` 使用 GET `/pc/invitation/getTopReplyList` 和 `/pc/invitation/getReplyList`。请求参数 `bbsid`、`uuid`、`order=2`、`tag=classId{当前班级}`；普通列表下一页携带响应 `poff.lastValue`，如存在则同时携带 `poff.lastAuxValue`。

要求 `status` 为布尔且为 true、`datas` 为列表。每条回复的 `bbsid`、`topic_id` 分别匹配空间和话题数值 ID；本人依据 `createrPuid`，顶层依据 `parent_id=-1`，不按昵称或 HTML 中“编辑”字样识别。只读本人的正文用于发布读回，其他学生正文不发送给模型、不作为回复素材。

先查置顶，再查普通列表，直到 `poff.lastPage=1`。分页预算为 20 页 / 每页至多 1000 条 / 60 秒；异常、缺字段、游标循环或预算耗尽表示无法确认，不作为零本人回复。

## 一次发布与核验

官方 `invitationEvent.js` 的 `.topicDetail_editContainer .addReply` 发送表单 POST `/pc/invitation/{topicUUID}/addReplys`。纯文本顶层字段：

| 字段 | 含义 |
| --- | --- |
| `courseId`, `classId` | 校验过的当前课程 / 班级 |
| `replyId` | `-1`，顶层回复 |
| `uuid` | 新建回复 UUID；网页同样生成 UUID 以避免重复提交，但不据此承诺服务器严格幂等 |
| `topic_content` | 先按 JS `encodeURIComponent` 编码，再交给表单编码，匹配网页行为 |
| `urlToken` | 本次重新读取详情提供的临时字段，只存内存 |
| `bbsid` | 原生讨论空间 ID |

无图片、附件或匿名时省略对应可选字段，不复制所有 Cookie 到手工头。独立 requests Session 继承受作用域约束的 CookieJar，HTTPS adapter 不重试，`allow_redirects=false`，响应有体积与读取期限限制；不修改共享媒体 / 测验 Session 的 adapter。

响应 `status=false` 为明确业务拒绝；`status=true` 且无 `datas` 为待审核，并不等于已公开发布。无论成功提示如何，最终以当前账号、话题、顶层关系及完全一致正文的回复读回确认发布。响应丢失、取消、审核中或读回未定保留发布意图 / 未知，只读核验。

发布意图在发送前原子落盘，整个话题处理持跨实例锁。发布后重新读取同一章节讨论入口的服务器 `isFinished` 字段，并保留 worker 最终章节复核。前端 `completeTopic`、绿色 CSS 和 `JC.completed` 均不作为完成证据。讨论成绩始终不推断。

## 范围与验收

实现只覆盖上述已核实合同；不遍历整课普通讨论区，不调用手机活动接口，旧版 / 镜像 / 结构变化保留待处理。首次真实验收确认：本人原先无回复 → 一次发布 97 字精简正文 → 本人正文完全读回 → 服务器任务点确认 → 章节完成确认 → 再次运行未发布新回复。验收正文来自预先审阅的生成器替身，未消费外部模型额度；生产路径使用独立 DiscussionGenerator 和现有 AIClient。

官方源码参考（只归纳协议，无整段复制）：[章节模块](https://mooc1.chaoxing.com/ananas/modules/insertbbs/index.html)、[话题初始化与详情](https://groupweb.chaoxing.com/res/course/js/discuss/topic/topicDetail.js?ctx=)、[回复查询](https://groupweb.chaoxing.com/res/course/js/invitation/topicInvitation.js?ctx=)、[顶层回复提交](https://groupweb.chaoxing.com/res/course/js/invitation/invitationEvent.js?ctx=)。这些资源会原地更新，当前样例不构成永久 API 保证。
