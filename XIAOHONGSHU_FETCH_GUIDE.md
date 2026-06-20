# 小红书抓取使用指南

## 一、环境准备

1. XHS-Downloader 已放在 `D:\Python\content_hub\XHS-Downloader`
2. 依赖已安装（`httpx`, `lxml`, `playwright` 等）

## 二、配置 Cookie（关键步骤）

Cookie 已写入 `.env` 文件：
```bash
CONTENT_HUB_XIAOHONGSHU_COOKIE=...
```

⚠️ **当前 Cookie 已过期**（`ets=1781234978679` = 2026-06-12）。抓取前请更新。

### 更新 Cookie 步骤

1. 打开 Chrome **无痕模式**（Ctrl+Shift+N）
2. 访问 `https://www.xiaohongshu.com/explore`
3. 按 `F12` → `网络` 选项卡
4. 勾选 `保留日志`，选择 `Fetch/XHR`
5. 在过滤框输入：`cookie-name:web_session`
6. **点击页面中任意一篇笔记**打开
7. 在左侧 Network 列表中找到 `feed` 请求，点击
8. 在右侧展开 `请求标头` → 找到 `Cookie:` 字段
9. **复制整行 Cookie 值**（从 Cookie= 后面的全部内容）
10. 替换 `.env` 中的 `CONTENT_HUB_XIAOHONGSHU_COOKIE` 值

### 验证 Cookie 是否有效

```bash
cd D:\Python\content_hub
python check_cookie.py "你的Cookie"
```

输出 `Cookie 有效` 即可使用。

## 三、获取笔记链接（以 littlekycap 为例）

XiaohongshuFetcher 只接受**具体的笔记链接**，不支持按博主 ID 自动遍历。

### 方法：使用 XHS-Downloader 用户脚本

1. 安装浏览器扩展 **Tampermonkey**
2. 导入脚本：`XHS-Downloader/static/XHS-Downloader.js`
3. 打开 `https://www.xiaohongshu.com/user/profile/littlekycap`
4. 点击脚本按钮，提取所有笔记链接
5. 保存为列表，如：
```json
[
  "https://www.xiaohongshu.com/explore/xxx",
  "https://www.xiaohongshu.com/explore/yyy",
  "https://www.xiaohongshu.com/explore/zzz"
]
```

## 四、配置 content_hub 信源

### 方式 1：控制台前端（推荐）

1. 启动 content_hub 服务
2. 打开控制台 → Sources 页面
3. 新建信源：
   - 类型：`xiaohongshu`
   - 名称：`littlekycap`
   - 配置：
     ```json
     {
       "urls": [
         "https://www.xiaohongshu.com/explore/xxx",
         "https://www.xiaohongshu.com/explore/yyy"
       ]
     }
     ```

### 方式 2：直接调用 API

```bash
curl -X POST http://localhost:8000/api/internal/content/fetch-runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "source_type": "xiaohongshu",
    "source_name": "littlekycap",
    "config": {
      "urls": ["https://www.xiaohongshu.com/explore/xxx"]
    }
  }'
```

## 五、触发抓取

1. 在控制台点击信源的 `运行` 按钮
2. 或提交 `FetchBatchRequest`：
   ```json
   {
     "run_id": "run-xhs-001",
     "sources": ["xiaohongshu"]
   }
   ```

## 六、抓取结果

成功入库后，`content_items` 表中会包含：
- `title`：笔记标题
- `raw_content`：正文 + 图片 markdown（`![图片](url)`）
- `metadata`：作者、类型、图片 URL、视频 URL、封面等

后续自动进入 AI 处理 → 审核队列 → 可发布。

## 七、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 抓取返回空 | Cookie 过期 | 更新 `.env` 中的 Cookie |
| 只返回标题无图片 | 未配置 Cookie 或 Cookie 失效 | 同上 |
| 视频笔记无视频 | 视频 URL 需要更高权限 | 配置有效 Cookie |
| 部分笔记失败 | 笔记被删除或设为私密 | 正常，跳过即可 |

## 八、免 Cookie 抓取（备选）

如果 Cookie 始终无法获取，可以修改 `XiaohongshuFetcher` 使用 **Playwright 浏览器自动化** 抓取公开笔记（无需 Cookie，但速度较慢）。如需此方案，联系我实现。
