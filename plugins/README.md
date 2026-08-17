# 插件目录

本目录由主框架 + 独立插件仓库组成：

- **`wordlib.py`** — 词库插件（核心插件，随主仓库发布）：关键词匹配回复、签到好感度、自定义昵称、排行榜、赞我、转码
- **其他插件**（结婚、JM下载、伪人、视频解析等）已拆分到独立仓库 [NapCat-WordLibBot-Plugins](https://github.com/Bdlxx/NapCat-WordLibBot-Plugins)，由安装脚本 `install.sh` 在部署/更新实例时自动拉取到本目录

## 手动安装/更新插件

```bash
# 方式一：通过安装脚本（推荐）
bash install.sh → 实例管理 → 更新插件

# 方式二：手动拉取
git clone --depth 1 https://github.com/Bdlxx/NapCat-WordLibBot-Plugins.git /tmp/napbot_plugin_repo
cp /tmp/napbot_plugin_repo/*.py plugins/
```

新插件放入 `plugins/` 目录（需导出 `handle(event)` 函数并声明 `__plugin_name_cn__` 等 SDK 元数据变量）后，主程序自动加载，Web 面板自动识别，无需改任何代码。
