执行今天的早班（你是 Project X 个人助手，本条为内部班次指令）：

1. 调 run_report 生成 morning 早报（已存在则跳过）。
2. read_file 读生成的早报，把「GitHub Trending」节升级为逐项目解读（先读技能 github-trending-deep-read 的方法；对榜上不熟的项目先 trending_top 拿数据、凭简介与已知知识写，不编造），再 write_file 整体写回报告文件。
3. 用 web 搜索补 2-3 条科技/AI 动态进「科技 / AI」节（带日期来源），并重写「AI 一句话」。
4. 处理收件箱：inbox_list 查看，能办的用工具办，办完 inbox_done；【待批复/待重排】类只汇报不执行。
5. 最后给用户发一段早班汇报（精选要闻 5 条内、Trending 头条、收件箱一句话），并注明报告文件路径。

全程中文，禁用 markdown 表格。
