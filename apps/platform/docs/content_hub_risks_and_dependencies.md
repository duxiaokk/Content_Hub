# Content Hub 椋庨櫓涓庡閮ㄤ緷璧栨竻鍗?

## 1. 鐩殑

鏈枃浠惰褰曞綋鍓嶆敼閫犻樁娈垫墍鏈夊凡鐭ラ闄┿€佸閮ㄤ緷璧栥€佸叧閿厤缃」銆佸緟纭鍙傛暟鍜岃繍琛屽墠鎻愩€?

浣滅敤锛?

1. 閬垮厤鍚庣画鎺ㄨ繘鏃堕仐婕忛樆濉為」
2. 鏄庣‘鍝簺鍊煎繀椤荤敱浜哄伐鎻愪緵
3. 鍖哄垎鈥滀唬鐮佸凡灏辩华鈥濆拰鈥滃閮ㄦ潯浠舵湭婊¤冻鈥?

## 2. 褰撳墠闃舵鐩爣

褰撳墠鐩爣涓嶆槸瀹屾暣涓夊眰涓彴锛岃€屾槸鍏堣窇閫氳繖涓€鏉￠棴鐜細

`CNBlogs / Bilibili -> AI Rewrite -> Blog Draft Publish`

鎵€浠ユ湰鏂囧彧璁板綍鍜岃繖鏉′富閾捐矾鐩存帴鐩稿叧鐨勯闄╁拰渚濊禆銆?

## 3. 宸茬煡鏋舵瀯椋庨櫓

### 3.1 `apps/platform` 涓?Python 鏍囧噯搴?`platform` 鍐茬獊

椋庨櫓绛夌骇锛氶珮

鐜拌薄锛?

- 褰?`apps` 琚姞鍏?`sys.path` 鍓嶉儴鏃讹紝`import platform` 鍙兘璇懡涓?`apps/platform`
- 浼氳繛甯﹀奖鍝?`sqlalchemy`銆乣httpx`銆乣attr` 绛変緷璧栧鍏?

褰撳墠鐘舵€侊細

- 历史上曾通过 legacy_paths.py 做临时兜底
- 该桥接层现已移除，当前不再依赖旧目录注入

寤鸿锛?

- 灏藉揩灏?`apps/platform` 杩佺Щ涓?`apps/web_console`

### 3.2 鐜版湁浠ｇ爜浠嶅浜庘€滄ˉ鎺ユ棫瀹炵幇鈥濈姸鎬?

椋庨櫓绛夌骇锛氫腑楂?

鐜拌薄锛?

- `fetcher_engine` 澶嶇敤浜?`ado_repost`
- `rewrite processor` 澶嶇敤浜?`platform/services/llm_client.py`
- `publisher_engine` 灏嗗鐢?`ado_repost/publishing`

褰卞搷锛?

- 鏃х洰褰曞拰鏂扮洰褰曚細骞跺瓨涓€娈垫椂闂?
- 涓€鏃︽棫瀹炵幇琛屼负鍙樺寲锛屾ˉ鎺ュ眰涔熶細鍙楀奖鍝?

寤鸿锛?

- 绗竴闃舵鍏佽妗ユ帴
- 绗簩闃舵鍐嶉€愭鎶婃姄鍙栥€丄I銆佸彂甯冨畬鍏ㄨ縼鍒版柊寮曟搸鐩綍

### 3.3 宸ヤ綔娴佺洰鍓嶄粎鏀寔绾挎€ф祦姘寸嚎

椋庨櫓绛夌骇锛氫腑

鐜扮姸锛?

- 鍙敮鎸?`fetch -> process -> publish`

褰卞搷锛?

- 鏆傛椂涓嶆敮鎸佹潯浠跺垎鏀€佷汉宸ュ鏍歌妭鐐广€佸苟琛屾姄鍙栧悎娴?

寤鸿锛?

- 鍏堢敤杩欐潯闂幆楠岃瘉涓氬姟鍙鎬э紝涓嶆彁鍓嶆墿灞?DAG

### 3.4 鍐呭妯″瀷浠嶆槸鏈€灏忚〃

椋庨櫓绛夌骇锛氫綆涓?

鐜扮姸锛?

- 褰撳墠鍙惤涓€寮?`content_items` 琛?

褰卞搷锛?

- 鐭湡瓒冲
- 鍚庣画濡傛灉瑕佹敮鎸佸鐗堟湰鏀瑰啓銆佸鐩爣鍙戝竷銆佸杞鏍革紝闇€瑕佹墿妯″瀷

寤鸿锛?

- 鍗婂勾鍐呬繚鎸佽交閲?
- 寰呴棴鐜ǔ瀹氬悗鍐嶆媶 `publication_records` 绛変粠琛?

## 4. 澶栭儴渚濊禆娓呭崟

### 4.1 LLM 渚濊禆

褰撳墠鎺ュ叆鏂瑰紡锛?

- 澶嶇敤 [llm_client.py](/D:/Python/content_hub/apps/platform/services/llm_client.py)
- `openai` / `anthropic` 褰撳墠閮借蛋 OpenAI-compatible 妯″紡
- `local` 褰撳墠璧?mock provider

闇€瑕侀厤缃殑椤癸細

- `SECRET_KEY`
- `CONTENT_HUB_LLM_PROVIDER`
- `CONTENT_HUB_LLM_MODEL`
- `CONTENT_HUB_LLM_MAX_TOKENS`
- `CONTENT_HUB_LLM_TIMEOUT_SECONDS`
- `CONTENT_HUB_LLM_FALLBACK`
- `CONTENT_HUB_LLM_COST_TRACKING`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `MOCK_LLM`

寰呯‘璁わ細

- 浣犳渶缁堣鐢ㄧ殑 provider 鏄?`openai`銆乣anthropic` 杩樻槸鍏煎缃戝叧
- 瀹為檯妯″瀷鍚嶇О
- 鍗曟鏈€澶?token 涓婇檺
- 澶辫触鏃舵槸 `raw` 杩樻槸 `retry`

### 4.2 閲囬泦婧愪緷璧?

褰撳墠鎺ュ叆鏂瑰紡锛?

- `CNBlogsFetcher` 鍏堣蛋 RSS
- `BilibiliFetcher` 鍏堣蛋 RSS feed

闇€瑕侀厤缃殑椤癸細

- `CONTENT_HUB_CNBLOGS_FEED_URL`
- `CONTENT_HUB_BILIBILI_FEED_URL`

寰呯‘璁わ細

- 鍏蜂綋鎶撳摢涓崥瀹㈠洯鍗氫富
- 鍏蜂綋鎶撳摢涓?B 绔?UP 涓?
- 瀵瑰簲 feed URL 鏄惁绋冲畾鍙闂?

### 4.3 鍙戝竷鐩爣渚濊禆

褰撳墠鎺ュ叆鏂瑰紡锛?

- 澶嶇敤 `ado_repost` 鐨?draft publishing client
- 鐩爣鏄?platform 鐨勫唴閮ㄨ崏绋挎帴鍙?

鐩稿叧浠ｇ爜锛?

- [client.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/client.py)
- [config.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/config.py)
- [models.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/models.py)

闇€瑕侀厤缃殑椤癸細

- `ADO_PUBLISH_ENABLED`
- `ADO_PUBLISH_ENDPOINT_URL`
- `ADO_INTERNAL_TOKEN`
- `ADO_PUBLISH_TIMEOUT_SECONDS`
- `ADO_SOURCE_PLATFORM`

榛樿鐩爣鎺ュ彛锛?

- `http://127.0.0.1:8000/api/internal/agent/drafts`

寰呯‘璁わ細

- 褰撳墠鏄惁缁х画鍏堝彂甯冨埌 platform 鑽夌绠?
- 杩樻槸瑕佺洿鎺ュ彂甯冨埌鐪熷疄鍗氬 API

## 5. 鍏抽敭 URL / ID / 鍙傛暟璁板綍

### 5.1 褰撳墠浠ｇ爜榛樿鍊?

#### CNBlogs

- 榛樿 feed URL:
  `https://feed.cnblogs.com/blog/u/126286/rss`

璇存槑锛?

- 杩欐槸鍗犱綅榛樿鍊?
- 闇€瑕佹浛鎹㈡垚浣犵殑鐩爣鍗氬鍥崥涓?feed

#### Bilibili

- 榛樿 feed URL:
  `https://rsshub.app/bilibili/user/video/2267573`

璇存槑锛?

- 褰撳墠閫氳繃 RSSHub 褰㈠紡鍗犱綅
- `2267573` 鏄綋鍓嶉粯璁ゅ崰浣?UP 涓?ID
- 闇€瑕佹浛鎹㈡垚浣犵殑鐩爣 UP 涓?ID 鎴栦綘鑷繁鐨?RSS 浠ｇ悊鍦板潃

#### YouTube

鐜版湁 `ado_repost` 榛樿鍊间粛瀛樺湪锛?

- channel id:
  `UCln9P4Qm3-EAY4aiEPmRwEA`

璇存槑锛?

- 褰撳墠闃舵涓婚摼璺湭浣跨敤
- 浣嗘棫鎶撳彇閫昏緫涓粛淇濈暀璇ラ粯璁ゅ€?

#### 鍙戝竷鎺ュ彛

- platform internal draft endpoint:
  `http://127.0.0.1:8000/api/internal/agent/drafts`

### 5.2 蹇呴』鐢变綘纭鎴栨彁渚涚殑鍊?

浠ヤ笅鍊煎繀椤绘渶缁堢‘璁わ紝鍚﹀垯鍙兘鍋滅暀鍦ㄢ€滆兘璺戞牱渚嬧€濓細

1. 鍗氬鍥洰鏍囧崥涓?feed URL
2. B 绔欑洰鏍?UP 涓?ID 鎴?feed URL
3. LLM provider
4. LLM model
5. LLM API key
6. LLM base URL
7. 鍙戝竷鐩爣鏄?platform 鑽夌绠辫繕鏄湡瀹炲崥瀹?API
8. 濡傛灉鏄湡瀹炲崥瀹?API锛屽搴?endpoint銆乼oken銆佸瓧娈垫牸寮?

## 6. 褰撳墠浠ｇ爜鐘舵€佹竻鍗?

### 宸插畬鎴?

- `content_items` 鏈€灏忔ā鍨嬪凡钀藉簱
- `Fetcher / Processor / Publisher / PluginRegistry` 宸插缓
- `CNBlogsFetcher` 宸叉帴 RSS 閫傞厤鍣?
- `BilibiliFetcher` 宸叉帴 RSS 閫傞厤鍣?
- `RewriteProcessor` 宸叉帴 LLM client
- `LinearPipelineRunner` 宸插氨浣?
- `scheduler_center` 宸叉帴 `content.pipeline.linear` 鍩虹鎵ц鍒嗘敮

### 杩涜涓?

- 璋冨害浠诲姟鐪熷疄闂幆鑱旇皟

### 鏈畬鎴?

- 鐪熷疄閰嶇疆鏂囦欢钀藉湴
- 鎶撳彇缁撴灉鍐欏洖 `content_items`
- 鍙戝竷缁撴灉鍥炲啓 `content_items`
- 鐪熷疄鍗氬 API 鍙戝竷

## 7. 褰撳墠闃舵寤鸿鐨勭幆澧冨彉閲忔ā鏉?

```env
SECRET_KEY=replace-with-real-secret

CONTENT_HUB_CNBLOGS_FEED_URL=https://feed.cnblogs.com/blog/u/<your-id>/rss
CONTENT_HUB_BILIBILI_FEED_URL=https://rsshub.app/bilibili/user/video/<your-up-id>

CONTENT_HUB_LLM_PROVIDER=openai
CONTENT_HUB_LLM_MODEL=gpt-4.1-mini
CONTENT_HUB_LLM_MAX_TOKENS=4000
CONTENT_HUB_LLM_TIMEOUT_SECONDS=60
CONTENT_HUB_LLM_FALLBACK=raw
CONTENT_HUB_LLM_COST_TRACKING=true

LLM_API_KEY=replace-with-real-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
MOCK_LLM=false

ADO_PUBLISH_ENABLED=true
ADO_PUBLISH_ENDPOINT_URL=http://127.0.0.1:8000/api/internal/agent/drafts
ADO_INTERNAL_TOKEN=local-dev-internal-token
ADO_PUBLISH_TIMEOUT_SECONDS=15
ADO_SOURCE_PLATFORM=cnblogs
```

## 8. 闃诲椤规€荤粨

鐪熸浼氶樆濉為棴鐜獙璇佺殑锛屼笉鏄唬鐮佺粨鏋勶紝鑰屾槸涓嬮潰杩欎簺澶栭儴淇℃伅锛?

1. 鐩爣鍗氬鍥?feed URL
2. 鐩爣 B 绔?feed URL / UP 涓?ID
3. 鍙敤鐨?LLM API key
4. 鍙敤鐨?LLM base URL
5. 鏈€缁堟ā鍨嬪悕
6. 鍙戝竷鐩爣鎺ュ彛鏄惁宸茬粡纭畾

杩欎簺鍊间竴鏃︽槑纭紝闂幆楠岃瘉灏卞彲浠ュ線鍓嶆帹杩涖€?
