using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Media;

namespace ChaoxingDesktop;

public sealed partial class MainWindow
{
    private FrameworkElement BuildCourses()
    {
        accounts = new ComboBox { PlaceholderText = "新账号 · 浏览器登录或导入 Cookie", DisplayMemberPath = "Display", HorizontalAlignment = HorizontalAlignment.Stretch };
        idleControls.Add(accounts);
        accounts.SelectionChanged += async (_, _) => { if (!refreshing && accounts.SelectedItem is AccountItem item) await Call("switchAccount", item.Id); };
        refreshers.Add(() =>
        {
            var rows = J.A(backend.State["accountRows"]).Select(n => new AccountItem(J.S(n, "id"), J.S(n, "display"))).ToArray();
            var old = (accounts.ItemsSource as AccountItem[]) ?? [];
            if (!old.SequenceEqual(rows)) accounts.ItemsSource = rows;
            accounts.SelectedItem = rows.FirstOrDefault(n => n.Id == J.S(Summary, "activeAccount"));
        });
        var add = Button("添加账号", async () => await Call("addAccount"), true);
        var remove = Button("删除账号", async () => { if (await Confirm("删除当前账号？", "将删除当前账号及其本机 Cookie，其他账号不受影响。", "删除此账号")) await Call("removeAccount"); }, true);
        var cancelLogin = Button("取消浏览器登录", async () => await Call("cancelBrowserLogin"));
        refreshers.Add(() => cancelLogin.Visibility = J.B(Summary, "browserLogin") ? Visibility.Visible : Visibility.Collapsed);
        var user = BoundText("手机号 / 账号", "common", "username");
        user.Width = 220;
        refreshers.Add(() => user.IsReadOnly = J.S(Summary, "activeAccount") != "");
        var password = BoundPassword("登录密码", "common", "password"); password.Width = 220;
        var label = new TextBox { PlaceholderText = "账号备注", Width = 220 };
        var detail = Column(
                new Border { Height = 1, Background = new SolidColorBrush(ParseColor("#E2E7EF")), Margin = new Thickness(0, 6, 0, 6) },
                Text("账户详情 / Cookie 登录", 16),
                Row(user, password, Button("登录并读取", async () => await Call("fetchCourses"), true, "#2563EB")),
                Row(label, Button("保存备注", async () => await Call("renameAccount", label.Text), true)),
                Row(BoundToggle("Cookie 登录", "common", "use_cookies"), Button("导入 Cookie", () => FileAction("fileAction", ["import_cookie"], false, "txt"), true),
                    Button("清除 Cookie", async () => { if (await Confirm("清除 Cookie？", "清除当前账号的本机会话，下次使用需要重新登录。", "清除 Cookie")) await Call("fileAction", "clear_cookie"); }, true)));
        var accountCard = Card(Column(Text("学习账户", 17), Text("多个账号可同时保留登录会话，Cookie 按账号加密保存。密码仅用于当前会话。", 12, true),
            StretchRow(accounts, Row(add, remove)),
            Row(Button("浏览器登录", async () => await Call("browserLogin"), true, "#2563EB"), cancelLogin,
                Button("重新读取课程", async () => await Call("fetchCourses"), true), Button("离线演示", async () => await Call("loadDemo"), true, "#7C3AED")), detail));
        accountCard.MaxWidth = 880;
        accountCard.HorizontalAlignment = HorizontalAlignment.Center;
        accountCard.VerticalAlignment = VerticalAlignment.Center;
        var accountScroll = Scroll(accountCard);
        accountScroll.VerticalContentAlignment = VerticalAlignment.Center;
        // ScrollViewer measures scrollable content differently from Grid.
        // Give the card a viewport-bounded width before centering it, so its
        // natural control widths cannot push the card outside the viewport.
        void FitAccountCard() => accountCard.Width = Math.Min(880, Math.Max(0, accountScroll.ActualWidth - 20));
        accountScroll.SizeChanged += (_, _) => FitAccountCard();
        FitAccountCard();
        accountConnectionCard = accountCard;
        var accountPage = new Grid();
        accountPage.Children.Add(accountScroll);
        returnToCourses = Button("返回我的课程 →", () => { ShowCourseView(true); return Task.CompletedTask; });
        returnToCourses.HorizontalAlignment = HorizontalAlignment.Right;
        returnToCourses.Visibility = Visibility.Collapsed;
        ((StackPanel)accountCard.Child).Children.Add(returnToCourses);
        courseCount = Text("我的课程", 19);
        var search = new TextBox { PlaceholderText = "搜索课程名称或 ID", Width = 210 };
        AutomationProperties.SetName(search, "搜索课程");
        search.TextChanged += async (_, _) => { if (!refreshing) await Call("searchCourses", search.Text); };
        var ids = new ToggleButtonCompat("显示 ID", value => { showIds = value; RefreshCourses(); });
        var toolbar = StretchRow(courseCount, Row(search, Button("全选可见", async () => await Call("selectVisible", true), true), Button("取消选择", async () => await Call("selectVisible", false), true), ids));
        courses = new ListView { SelectionMode = ListViewSelectionMode.None, ItemTemplate = (DataTemplate)Root.Resources["CourseTemplate"], HorizontalContentAlignment = HorizontalAlignment.Stretch };
        courses.ItemContainerStyle = StretchListStyle();
        emptyCourses = Text("从连接账户开始\n读取课程，或点击「离线演示」体验完整流程。", 16, true);
        emptyCourses.HorizontalAlignment = HorizontalAlignment.Center; emptyCourses.VerticalAlignment = VerticalAlignment.Center;
        var courseArea = new Grid(); courseArea.Children.Add(courses); courseArea.Children.Add(emptyCourses);
        selectedText = Text("已选择 0 门课程", 16); selectedText.Foreground = new SolidColorBrush(Microsoft.UI.Colors.White);
        var hint = Text("按当前学习与答案策略处理所选课程", 12); hint.Foreground = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 184, 200, 223));
        var start = Button("开始所选课程", async () => await Call("startTasks"), false, "#2563EB");
        refreshers.Add(() => { selectedText.Text = $"已选择 {J.I(Summary, "selectedCount")} 门课程"; courseCount.Text = $"我的课程 · {J.I(Summary, "courseCount")} 门"; start.IsEnabled = !Busy && J.I(Summary, "selectedCount") > 0; hint.Text = J.I(Summary, "hiddenCount") > 0 ? $"包含 {J.I(Summary, "hiddenCount")} 门被搜索隐藏的已选课程" : J.B(Summary, "demo") ? "演示过程不会连接超星" : "按当前学习与答案策略处理所选课程"; });
        var bottom = new Border { Background = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 23, 44, 75)), CornerRadius = new CornerRadius(12), Padding = new Thickness(18), Child = StretchRow(Column(selectedText, hint), Row(Button("查看本轮策略", async () => await ShowText("本轮策略摘要", J.S(backend.State, "strategySummary"))), start)) };
        var accountName = Text("", 13, true);
        refreshers.Add(() => accountName.Text = J.B(Summary, "demo") ? "离线演示 · 示例课程" : "当前账号：" + (accounts.SelectedItem is AccountItem active ? active.Display : "已连接"));
        var courseHeader = StretchRow(accountName, Row(Button("← 账号管理 / 切换账号", () => { ShowCourseView(false); return Task.CompletedTask; }, true), Button("重新读取课程", async () => await Call("fetchCourses"), true)));
        var grid = new Grid { RowSpacing = 14 };
        foreach (var height in new[] { GridLength.Auto, GridLength.Auto, new GridLength(1, GridUnitType.Star), GridLength.Auto }) grid.RowDefinitions.Add(new RowDefinition { Height = height });
        FrameworkElement[] rows2 = [courseHeader, toolbar, courseArea, bottom];
        for (int i = 0; i < rows2.Length; i++) { grid.Children.Add(rows2[i]); Grid.SetRow(rows2[i], i); }
        courseHost = new Grid();
        courseViews = [accountPage, grid];
        foreach (var view in courseViews) courseHost.Children.Add(view);
        ClipContent(courseHost);
        SwitchContent(courseHost, courseViews, 0, animate: false);
        return courseHost;
    }

    private static Style StretchListStyle()
    {
        var style = new Style(typeof(ListViewItem));
        style.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty, HorizontalAlignment.Stretch));
        style.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(0)));
        return style;
    }
    private void RefreshCourses()
    {
        if (courses == null) return;
        SyncRows("courses", courses, J.A(backend.State["courses"]).Select(n => new RecordRow(n, true, showIds)));
        if (emptyCourses != null) { emptyCourses.Visibility = courses.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed; emptyCourses.Text = J.I(Summary, "courseCount") > 0 ? "没有匹配的课程\n尝试其他关键词；隐藏课程的选择会保留。" : "从连接账户开始\n读取课程，或点击「离线演示」体验完整流程。"; }
    }
    private async void CourseChecked(object sender, RoutedEventArgs e)
    {
        if (!refreshing && sender is CheckBox { Tag: RecordRow row } check)
            await Call("selectCourse", J.S(row.Data, "courseId"), J.S(row.Data, "clazzId"), check.IsChecked == true);
    }

    private TextBox BoundText(string title, string section, string key, bool multiline = false)
    {
        var input = new TextBox { PlaceholderText = title, Text = Value(section, key), HorizontalAlignment = HorizontalAlignment.Stretch, AcceptsReturn = multiline, TextWrapping = multiline ? TextWrapping.Wrap : TextWrapping.NoWrap, MinHeight = multiline ? 130 : 38 };
        AutomationProperties.SetName(input, title); fields[section + "." + key] = input; idleControls.Add(input);
        input.TextChanged += async (_, _) => { if (!refreshing) await Call("setValue", section, key, input.Text); };
        refreshers.Add(() => { if (input.FocusState == FocusState.Unfocused && input.Text != Value(section, key)) input.Text = Value(section, key); });
        return input;
    }
    private PasswordBox BoundPassword(string title, string section, string key)
    {
        var input = new PasswordBox { Password = Value(section, key), PlaceholderText = title, HorizontalAlignment = HorizontalAlignment.Stretch };
        AutomationProperties.SetName(input, title); fields[section + "." + key] = input; idleControls.Add(input);
        input.PasswordChanged += async (_, _) => { if (!refreshing) await Call("setValue", section, key, input.Password); };
        refreshers.Add(() => { if (input.FocusState == FocusState.Unfocused && input.Password != Value(section, key)) input.Password = Value(section, key); });
        return input;
    }
    private ToggleSwitch BoundToggle(string title, string section, string key)
    {
        var input = new ToggleSwitch { Header = title, IsOn = Value(section, key) == "true", OnContent = "已启用", OffContent = "已关闭" };
        fields[section + "." + key] = input; idleControls.Add(input);
        input.Toggled += async (_, _) => { if (!refreshing) await Call("setValue", section, key, input.IsOn ? "true" : "false"); };
        refreshers.Add(() => input.IsOn = Value(section, key) == "true"); return input;
    }
    private StackPanel BuildGroups(string name)
    {
        var stack = Column();
        foreach (var group in J.A(backend.State["schema"]?[name]))
        {
            var content = Column(Text(J.S(group, "title"), 18), Text(J.S(group, "description"), 12, true));
            var form = new Grid { ColumnSpacing = 28, RowSpacing = 18 };
            foreach (var spec in J.A(group["fields"])) { fieldGroups[J.S(spec, "section") + "." + J.S(spec, "key")] = name; form.Children.Add(BuildField(spec)); }
            void Arrange()
            {
                int columns = form.ActualWidth > 780 ? 2 : 1;
                if (form.ColumnDefinitions.Count == columns) return;
                form.ColumnDefinitions.Clear(); form.RowDefinitions.Clear();
                for (int i = 0; i < columns; i++) form.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                for (int i = 0; i < (form.Children.Count + columns - 1) / columns; i++) form.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                for (int i = 0; i < form.Children.Count; i++) { Grid.SetRow((FrameworkElement)form.Children[i], i / columns); Grid.SetColumn((FrameworkElement)form.Children[i], i % columns); }
            }
            form.SizeChanged += (_, _) => Arrange(); Arrange(); content.Children.Add(form);
            stack.Children.Add(Card(content));
        }
        return stack;
    }
    private FrameworkElement BuildField(JsonNode spec)
    {
        var title = J.S(spec, "title"); var section = J.S(spec, "section"); var key = J.S(spec, "key"); var kind = J.S(spec, "kind");
        Control input;
        if (kind == "bool") input = BoundToggle(title, section, key);
        else if (kind == "secret") input = BoundPassword(title, section, key);
        else if (kind == "choice")
        {
            var choices = J.A(spec["choices"]).Select(n => new ChoiceItem(J.S(n, "label"), J.S(n, "value"))).ToArray();
            var combo = new ComboBox { ItemsSource = choices, DisplayMemberPath = "Label", SelectedItem = choices.FirstOrDefault(n => n.Value == Value(section, key)) };
            combo.SelectionChanged += async (_, _) => { if (!refreshing && combo.SelectedItem is ChoiceItem choice) await Call("setValue", section, key, choice.Value); };
            refreshers.Add(() => combo.SelectedItem = choices.FirstOrDefault(n => n.Value == Value(section, key)));
            fields[section + "." + key] = combo; idleControls.Add(combo); input = combo;
        }
        else input = BoundText(title, section, key, kind == "multiline");
        // Keep raw numeric text, including incomplete edits, in the shared
        // validation path. Save/start report and focus the offending field.
        var panel = kind == "bool" ? Column(input) : Column(Text(title), input);
        panel.Spacing = 5;
        if (kind == "directory") panel.Children.Add(Button("选择目录…", async () =>
        {
            var picker = new Windows.Storage.Pickers.FolderPicker(); picker.FileTypeFilter.Add("*");
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
            var folder = await picker.PickSingleFolderAsync();
            if (folder != null) await Call("setValue", section, key, folder.Path);
        }, true));
        if (J.S(spec, "hint") is { Length: > 0 } hint) panel.Children.Add(Text(hint, 12, true));
        if (kind is "integer" or "number") panel.Children.Add(Text($"范围：{J.S(spec, "low")}–{J.S(spec, "high")}", 11, true));
        if (spec["depends"] is JsonObject dependency && J.S(dependency, "key") != "")
            refreshers.Add(() => input.IsEnabled = !Busy && Value(J.S(dependency, "section"), J.S(dependency, "key")) == J.S(dependency, "value"));
        return panel;
    }

    private FrameworkElement BuildServices()
    {
        var bankStack = Column(Text("题库服务", 18), Text("按顺序查询已启用的题库；展开编辑独立参数。", 12, true));
        var bankMap = new Dictionary<string, string> { ["TikuGo"] = "bank_go", ["TikuYanxi"] = "bank_yanxi", ["TikuLike"] = "bank_like", ["TikuAdapter"] = "bank_adapter", ["TikuDeclarative"] = "bank_declarative" };
        var bankExpanders = new Dictionary<string, Expander>();
        foreach (var provider in J.A(backend.State["providers"]))
        {
            string key = J.S(provider, "key"), title = J.S(provider, "title"), secret = J.S(provider, "secret");
            var enabled = new ToggleSwitch { Header = title, IsOn = J.B(provider, "enabled") }; idleControls.Add(enabled);
            enabled.Toggled += async (_, _) => { if (!refreshing) await Call("toggleProvider", key, enabled.IsOn); };
            var health = Text(J.S(provider, "health"), 12, true);
            refreshers.Add(() => { var row = J.A(backend.State["providers"]).FirstOrDefault(n => J.S(n, "key") == key); enabled.IsOn = J.B(row, "enabled"); health.Text = J.S(row, "health"); });
            var up = Button("上移", async () => await Call("moveProvider", J.A(backend.State["providers"]).Select(n => J.S(n, "key")).ToList().IndexOf(key), -1), true);
            var down = Button("下移", async () => await Call("moveProvider", J.A(backend.State["providers"]).Select(n => J.S(n, "key")).ToList().IndexOf(key), 1), true);
            var content = Column(Text("服务凭据"), BoundPassword("服务凭据", "question_bank", secret), BuildGroups(bankMap[key]),
                Button("真实连接检查…", async () => { if (await Confirm("真实服务连接检查", "将向「" + title + "」发送一道最小测试题，可能消耗服务额度。", "发送测试题")) await Call("checkBank", key); }, true, "#7C3AED"));
            fieldGroups["question_bank." + secret] = bankMap[key];
            if (key == "TikuDeclarative") content.Children.Add(Row(Button("导入 JSON", () => FileAction("definitionAction", ["import"], false, "json"), true), Button("导出模板", () => FileAction("definitionAction", ["export"], true, "json", "question-bank"), true)));
            var expander = new Expander { Header = Column(StretchRow(enabled, Row(up, down)), health), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
            bankExpanders.Add(key, expander); bankStack.Children.Add(expander);
        }
        refreshers.Add(() => { int position = 2; foreach (var p in J.A(backend.State["providers"])) { var expander = bankExpanders[J.S(p, "key")]; if (bankStack.Children.IndexOf(expander) != position) { bankStack.Children.Remove(expander); bankStack.Children.Insert(position, expander); } position++; } });
        bankStack.Children.Add(Button("离线检查配置", async () => await Call("offlineCheck"), true));
        var aiHealth = Text("尚未测试连接", 12, true);
        refreshers.Add(() => aiHealth.Text = J.S(backend.State["serviceHealth"], "ai") + "\n" + J.S(backend.State, "aiWarning"));
        var ai = Column(Button("命名 AI 档案…", () => { EnqueueDialog(ShowProfiles); return Task.CompletedTask; }, true), BuildGroups("ai"), Button("测试 AI 连接…", async () => { if (await Confirm("主动测试 AI 服务", "将向当前配置的 AI 服务发送“回复 OK”，可能消耗额度。", "发送测试请求")) await Call("checkAi"); }, true, "#7C3AED"), aiHealth);
        var serviceGrid = new Grid { ColumnSpacing = 16 };
        serviceGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }); serviceGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var banksScroll = Scroll(bankStack); var aiScroll = Scroll(ai); serviceGrid.Children.Add(banksScroll); serviceGrid.Children.Add(aiScroll); Grid.SetColumn(aiScroll, 1);
        bool aiSelected = false;
        void ArrangeServices()
        {
            bool wide = serviceGrid.ActualWidth > 880;
            banksScroll.Visibility = aiSelected ? Visibility.Collapsed : Visibility.Visible;
            aiScroll.Visibility = aiSelected || wide ? Visibility.Visible : Visibility.Collapsed;
            Grid.SetColumn(aiScroll, !aiSelected && wide ? 1 : 0);
            Grid.SetColumnSpan(banksScroll, wide && !aiSelected ? 1 : 2);
            Grid.SetColumnSpan(aiScroll, wide && !aiSelected ? 1 : 2);
        }
        serviceGrid.SizeChanged += (_, _) => ArrangeServices(); ArrangeServices();
        var tabs = Tabs(("服务连接", serviceGrid), ("答案处理", Scroll(BuildGroups("answers"))), ("结束通知", Scroll(BuildGroups("notification"))), ("讨论任务", PreviewSettings("discussion")), ("投票／问卷", PreviewSettings("activity")));
        var selector = (Pivot)tabs.Children[0]; selector.Margin = new Thickness(-12, 0, 110, 8);
        Button? aiSwitch = null;
        aiSwitch = Button("AI 设置", () => { aiSelected = !aiSelected; aiSwitch!.Content = aiSelected ? "题库列表" : "AI 设置"; ArrangeServices(); return Task.CompletedTask; });
        aiSwitch.HorizontalAlignment = HorizontalAlignment.Right; aiSwitch.VerticalAlignment = VerticalAlignment.Center; tabs.Children.Add(aiSwitch);
        revealServiceGroup = group =>
        {
            selector.SelectedIndex = group switch { "answers" => 1, "notification" => 2, "discussion" => 3, "activity" => 4, _ => 0 };
            aiSelected = group == "ai"; aiSwitch.Content = aiSelected ? "题库列表" : "AI 设置"; ArrangeServices();
            foreach (var bank in bankExpanders) if (bankMap[bank.Key] == group) bank.Value.IsExpanded = true;
        };
        var pipeline = Text("01 题库查询     →     02 AI 补全     →     03 人工补全     →     04 随机补全", 14);
        var pipelineHint = Text("仅处理前一步未解决的题目 · 随机补全默认关闭，自动提交独立控制", 12, true);
        selector.SelectionChanged += (_, _) =>
        {
            aiSwitch.Visibility = selector.SelectedIndex == 0 ? Visibility.Visible : Visibility.Collapsed;
            pipeline.Text = selector.SelectedIndex == 4 ? "01 发现活动     →     02 核实本人状态     →     03 逐题草稿     →     04 提交与分步核验" : selector.SelectedIndex == 3 ? "01 识别话题     →     02 检查本人回复     →     03 生成草稿     →     04 发布与核验" : "01 题库查询     →     02 AI 补全     →     03 人工补全     →     04 随机补全";
            pipelineHint.Text = selector.SelectedIndex == 4 ? "选择题与文本题分别配置 · 自动提交独立控制 · 提交未知时仅只读核验" : selector.SelectedIndex == 3 ? "只处理章节必做讨论 · 发布与任务完成分别确认，未知结果不重复提交" : "仅处理前一步未解决的题目 · 随机补全默认关闭，自动提交独立控制";
        };
        var banner = Card(Column(pipeline, pipelineHint)); banner.Background = new SolidColorBrush(ParseColor("#EDF2FC")); banner.Padding = new Thickness(16);
        var root = new Grid { RowSpacing = 16 }; root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); root.Children.Add(banner); root.Children.Add(tabs); Grid.SetRow(tabs, 1); return root;
    }
    private UIElement PreviewSettings(string kind)
    {
        var topic = new TextBox { PlaceholderText = "输入示例主题，预览不会读取或提交课程", AcceptsReturn = true, Height = 100, TextWrapping = TextWrapping.Wrap };
        var output = new TextBox { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 120 };
        refreshers.Add(() => output.Text = J.S(backend.State[kind + "Preview"], "content") + "\n" + J.S(backend.State[kind + "Preview"], "reason"));
        return Scroll(Column(BuildGroups(kind), Card(Column(Text("示例预览", 18), topic, Button("生成预览…", async () => { if (await Confirm("生成示例预览", "AI 策略会请求当前服务，可能消耗额度；固定好或本地随机策略完全本地。", "生成预览")) await Call(kind == "discussion" ? "previewDiscussion" : "previewActivity", topic.Text); }, true), output))));
    }
    private UIElement BuildBackup() => Card(Column(Text("配置与数据", 18),
        Row(Button("导入 INI 配置", () => FileAction("fileAction", ["import_config"], false, "ini"), true), Button("导出排障配置", () => FileAction("fileAction", ["export_diagnostics"], true, "ini", "diagnostics"), true)),
        Row(Button("导出完整 INI（含凭据）…", async () => { if (await Confirm("导出完整 INI", "文件包含密码与密钥，请仅作为个人备份保管。", "选择保存位置")) await FileAction("fileAction", ["export_config"], true, "ini", "config"); }, true),
            Button("数据与容量说明", async () => await ShowText("本地数据与备份", J.S(backend.State, "dataExplanation"))))));

    private Grid Tabs(params (string Title, UIElement Content)[] items)
    {
        var selector = new Pivot { Margin = new Thickness(-12, 0, 0, 8) };
        var host = new Grid(); var grid = new Grid(); grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        grid.Children.Add(selector); grid.Children.Add(host); Grid.SetRow(host, 1);
        foreach (var item in items) { selector.Items.Add(new PivotItem { Header = new TextBlock { Text = item.Title, FontSize = 14 } }); host.Children.Add(item.Content); }
        var views = host.Children.Cast<FrameworkElement>().ToArray();
        ClipContent(host);
        int previous = 0;
        selector.SelectionChanged += (_, _) => { int selected = selector.SelectedIndex; SwitchContent(host, views, selected, selected >= previous ? 18 : -18); previous = selected; };
        selector.SelectedIndex = 0; SwitchContent(host, views, 0, animate: false);
        return grid;
    }
    private sealed record ChoiceItem(string Label, string Value);
    private sealed record AccountItem(string Id, string Display);
}

internal sealed class ToggleButtonCompat : Microsoft.UI.Xaml.Controls.Primitives.ToggleButton
{
    public ToggleButtonCompat(string title, Action<bool> action) { Content = title; Click += (_, _) => action(IsChecked == true); }
}
