# 抖音数据到飞书表格字段映射

## 核心字段映射表

| 抖音 API 字段 | 飞书表格字段名 | 类型 | 说明 |
|--------------|---------------|------|------|
| `data.aweme_id` | 视频ID | 文本 | 抖音视频唯一标识，19位数字 |
| `data.share_url` | 视频链接 | 链接 | 格式: `{"text": "查看视频", "link": "url"}` |
| `data.desc` | 标题描述 | 文本 | 视频标题/描述文字 |
| `data.author.nickname` | 作者昵称 | 文本 | 作者显示名称 |
| `data.author.unique_id` | 作者ID | 文本 | 作者抖音号 |
| `data.create_time` | 发布时间 | 日期 | 毫秒时间戳格式 |
| `data.duration` | 视频时长(秒) | 数字 | API返回毫秒，转换为秒 |
| `data.statistics.play_count` | 播放量 | 数字 | 视频播放次数 |
| `data.statistics.digg_count` | 点赞数 | 数字 | 点赞数量 |
| `data.statistics.comment_count` | 评论数 | 数字 | 评论数量 |
| `data.statistics.share_count` | 分享数 | 数字 | 分享次数 |
| `data.statistics.collect_count` | 收藏数 | 数字 | 收藏数量 |
| `data.text_extra` | 话题标签 | 文本 | 格式: `#标签1 #标签2` |
| - | 采集时间 | 日期 | 数据获取时的时间戳 |
| `data._data_source` | 数据来源 | 文本 | `Web API` 或 `App API` |

## 商品相关字段

| 抖音 API 字段 | 飞书表格字段名 | 类型 | 说明 |
|--------------|---------------|------|------|
| `data.promotions` | 是否挂车 | 复选框 | 是否有商品链接 |
| `promotions[0].title` | 商品标题 | 文本 | 商品名称 |
| `promotions[0].price` | 商品价格(元) | 数字 | API返回分，转换为元 |
| `promotions[0].sales` | 商品销量 | 数字 | 商品销售数量 |
| `promotions[0].url` | 商品链接 | 链接 | 商品详情页链接 |

## 数据类型转换规则

### 时间戳转换
```python
# 飞书日期字段需要毫秒级时间戳
feishu_timestamp = unix_timestamp * 1000
```

### 视频时长转换
```python
# API返回毫秒，转换为秒并保留2位小数
duration_seconds = round(duration_ms / 1000, 2)
```

### 链接字段格式
```python
# 飞书链接字段格式
link_field = {"text": "显示文本", "link": "https://..."}
```

### 统计数据处理
- 所有统计数据强制转换为 `int` 类型
- 空值或异常值默认为 `0`

## 数据来源优先级

播放量获取策略：
1. 优先使用 App API (`/api/v1/douyin/app/v3/fetch_video_statistics`)
2. 回退使用 Web API 数据
3. 采用"最大值"策略：`final_val = max(app_val, web_val)`

## 下架视频处理

当视频不可访问时：
- `标题描述` 设为 `"视频已下架"`
- `status.is_delete` 为 `True`
- 统计数据保持为 `0`
