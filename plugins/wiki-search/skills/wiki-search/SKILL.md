---
name: wiki-search
description: 搜索华为 WIKI 文档或用户提供的本地 WIKI 资料库；需要按关键词、标题、正文、知识库、类目或文档子树查找资料时使用。
---

# WIKI 搜索

使用 `wiki-cli` 提供的 `wiki doc search` 搜索华为 WIKI。默认优先全系统搜索；用户明确限定范围时遵循其范围。

## 本地优先与前置条件

用户提供本地资料库地址时，先用文本搜索工具递归检索其中的 `_index.md`，例如：

```bash
rg -n -i --glob '_index.md' -- "关键词" "本地资料库路径"
```

本地有相关结果就直接使用；找不到相关结果再调用线上 API。本地检索无需认证。

线上搜索前运行 `wiki auth status`，确认返回 `✓ 已认证`。若命令不可用或未认证，说明缺失的条件，待用户完成安装或认证后继续，不伪造搜索结果。

CLI 的本机参考：`C:\Users\<username>\.cac\skills\wiki-cli\references\wiki-doc.md` 的 `search` 一节；可用时读取以核对当前版本。也可用 `wiki doc search --help` 核对参数；该 Windows 路径不是跨平台固定路径。

## 命令格式与参数

```bash
wiki doc search [OPTIONS] {search_key}
```

`search_key` 是非空位置参数，必须放在所有选项后面。参考文档 URL 必须通过 `--url` 传入，不作为额外位置参数。

| 参数 | 必填 | 说明 |
|---|---|---|
| `search_key` | 是 | 非空搜索关键词，放在最后 |
| `--range, -r` | 是 | `知识库`、`类目`、`当前文档及子文档`、`全系统` |
| `--url` | 条件必填 | 除全系统外必填；含 `WIKI` 标识符的具体文档链接，用于解析 domain/kanban/sn |
| `--scope` | 否 | `全部`（默认）、`标题`、`正文`、`创建人` |
| `--exact` | 否 | 包含全部关键词（精确匹配） |
| `--sort-field` | 否 | `默认`（默认）、`创建时间`、`更新时间`、`阅读量` |
| `--sort-way` | 否 | `正序`、`倒序`（默认） |
| `--page, -p` | 否 | 页码，默认 1 |
| `--page-size, -s` | 否 | 每页条数，默认 100，最大 100 |

## 范围选择

| 用户意图 | `--range` | `--url` |
|---|---|---|
| 整个平台搜索（默认优先） | `全系统` | 可省略 |
| 某个 domain 内 | `知识库` | 该知识库任一文档 URL |
| 某个 kanban 内 | `类目` | 该类目下任一文档 URL |
| 某文档及其子文档内 | `当前文档及子文档` | 该文档 URL |

范围递减：全系统 > 知识库 > 类目 > 当前文档及子文档。限定范围但缺少 URL 时，向用户索取相应文档链接。

## 常用示例

```bash
# 全局搜索，无需 URL
wiki doc search --range 全系统 "SCALARLDST"

# 只匹配标题，每页 20 条
wiki doc search --range 全系统 --scope 标题 --page-size 20 "昇腾"

# 知识库搜索，URL 用于解析 domain_id
wiki doc search --range 知识库 --url "https://wiki.huawei.com/domains/68949/wiki/113424/WIKI202307291683600" "算子"

# 类目和文档子树搜索；将“文档URL”替换为具体文档链接
wiki doc search --range 类目 --url "文档URL" "架构"
wiki doc search --range 当前文档及子文档 --url "文档URL" "部署指南"

# 包含全部关键词
wiki doc search --range 全系统 --exact "AI Agent 部署"

# 按更新时间倒序
wiki doc search --range 全系统 --sort-field 更新时间 --sort-way 倒序 "性能分析"

# 获取下一页
wiki doc search --range 全系统 --page 2 --page-size 20 "昇腾"
```

## 返回结构与结果使用

```json
{
  "total_records": 46,
  "page": 1,
  "page_size": 20,
  "records": [
    {
      "title": "文档标题",
      "url": "https://wiki.huawei.com/domains/.../WIKI...",
      "created_by": "创建人",
      "attachment_names": [],
      "content_match_snippets": ["正文匹配片段1", "片段2"]
    }
  ]
}
```

默认按相关度返回，指定排序时遵循排序字段和方向。结合标题与 `content_match_snippets` 判断相关性，向用户提供相关文档标题、链接和匹配摘要；片段不能当作已读取的完整正文。按需翻页，勿把单页结果当作全部结果。

## 常见错误

- 关键词后写选项（如 `wiki doc search "关键词" --range 知识库`）会报 `Got unexpected extra argument(s)`；所有选项放在关键词前。
- 漏掉必填的 `--range`，或非全系统范围漏掉 `--url`，无法执行。
- URL 必须是含 `WIKI` 标识符的具体文档链接。
- `--page-size` 超过 100 会报错；空关键词会返回 400。
