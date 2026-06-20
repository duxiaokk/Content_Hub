import httpx, re, json

def check_cookie(cookie: str) -> None:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Cookie': cookie,
        'Referer': 'https://www.xiaohongshu.com/explore',
    }
    resp = httpx.get('https://www.xiaohongshu.com/explore/67ba0d7c000000002203f3c9', headers=headers, timeout=30, follow_redirects=True)
    print(f"Status: {resp.status_code}")
    print(f"URL: {resp.url}")
    
    # 检查是否被重定向到登录页
    if 'login' in str(resp.url) or '手机' in resp.text or '验证码' in resp.text:
        print("Cookie 无效：被重定向到登录页")
        return
    
    # 检查页面是否有笔记数据
    match = re.search(r'window\.__INITIAL_STATE__=({.+?});?</script>', resp.text, re.DOTALL)
    if match:
        content = match.group(1).replace('undefined', 'null')
        data = json.loads(content)
        if 'note' in data and 'noteDetailMap' in data['note']:
            ndm = data['note']['noteDetailMap']
            if ndm and 'null' not in str(ndm.keys()):
                print("Cookie 有效：能获取笔记数据")
                return
    
    print("Cookie 可能无效：页面无笔记数据")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        check_cookie(sys.argv[1])
    else:
        print("用法: python check_cookie.py '你的Cookie字符串'")
