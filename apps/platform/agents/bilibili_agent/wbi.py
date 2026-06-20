"""Bilibili wbi 签名实现。

B 站 API（v2 版本）请求需要 wbi 签名，流程如下：
1. 访问 /x/web-interface/nav 获取 wbi_img.img_url 和 wbi_img.sub_url
2. 从 URL 中提取 img_key 和 sub_key（文件名部分，去掉 .png）
3. 拼接后按固定索引数组取 32 个字符生成 mixin_key
4. 请求参数添加 wts（时间戳），排序后拼接 query_string + mixin_key，取 md5 前 16 位作为 w_rid
"""
from __future__ import annotations

import hashlib
import time
import urllib.parse

# 固定索引数组，B 站 wbi mixin_key 生成标准
MIXIN_KEY_IDX = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 11, 42, 52, 37, 17, 19, 24, 28, 36, 51, 39,
]


def _extract_filename(url: str) -> str:
    """从 URL 中提取文件名（去掉扩展名）。"""
    path = urllib.parse.urlparse(url).path
    return path.split("/")[-1].split(".")[0]


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    """用 img_key + sub_key 生成 mixin_key。"""
    s = img_key + sub_key
    return "".join(s[i] for i in MIXIN_KEY_IDX)


def encode_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数添加 wbi 签名（wts + w_rid）。"""
    mixin_key = _get_mixin_key(img_key, sub_key)
    # 过滤空值
    filtered = {k: v for k, v in params.items() if v not in (None, "", [], {})}
    filtered["wts"] = int(time.time())
    # 按 key 排序，生成 query string
    sorted_params = sorted(filtered.items())
    query = urllib.parse.urlencode(sorted_params)
    w_rid = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    filtered["w_rid"] = w_rid
    return filtered
