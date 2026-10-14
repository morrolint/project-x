# 巨构套件（megastructure kit）

> 源自用户自有项目 `~/Projects/arcology`（巨构个人站，零依赖科幻风），2026-10-14 经用户指令移入 Project X，
> 作为桌面助手 UI 的设计底座。**Project X 是本体，套件是皮肤**——样式服务数据，不反向。

## 三个部件

| 文件 | 是什么 | 用法 |
|---|---|---|
| `megastructure.css` | 设计系统全量：`:root` 令牌（`--cyan` #38e1ff / `--amber` / `--bg` #05070a，Rajdhani + Noto Sans SC + JetBrains Mono）+ 氛围层（网格/辉光/扫描线/噪点/雾）+ HUD 组件（boot 开机层、ticker 跑马灯、reveal 进场、skill 计数条、module 卡、顶栏/进度条） | `<link>` 引入；改主色只动 `:root` 里的 `--cyan` |
| `megastructure.js` | 行为件：开机自检打字机（点击/按键跳过，`prefers-reduced-motion` 全局降级）、实时时钟、IntersectionObserver 进场与计数、导航高亮、滚动进度条 + Hero 视差 | `<script>` 引入；依赖的 DOM 标记见文件头注释（`#boot`/`#clock`/`.reveal` 等，缺哪个就自动跳过哪个，不会报错） |
| `skyline.svg` | 巨构天际线：三层视差建筑 + 空中巨环 + 红色信标 + 电梯光点 + 星点 | 内嵌进页面用（`<img>` 引用会丢 `.beacon/.lift/.twinkle` 动画，因为动画定义在 css） |

## 契约要点

- **零依赖铁律同源**：无构建步骤、无第三方库；字体走 Google Fonts（Rajdhani 等），断网自动回退系统字体不破相——与 assistant 全链路"纯标准库"哲学一致。
- 无障碍已内建：`prefers-reduced-motion` 下开机动画与动效全关；`noscript` 回退样式在原项目 index.html 里有现成写法。
- 开机文案 `LINES` 数组在 `megastructure.js` 顶部，控制台上线后可改为真实自检数据（模型/记忆条数/registry 状态）。

## 登记

registry 条目 `ui-kit-megastructure`（type: ui-kit，active）。
