# Content Hub 鏀瑰姩涓庤繘搴﹁褰?

## 1. 鐩殑

鏈枃浠惰褰曟湰杞敼閫犲凡缁忎慨鏀逛簡浠€涔堛€佸綋鍓嶈繘搴﹀埌鍝噷銆佷笅涓€姝ュ噯澶囧仛浠€涔堛€?

鏇存柊鍘熷垯锛?

1. 璁板綍鐪熷疄宸茶惤搴?宸茶惤浠ｇ爜鐨勫唴瀹?
2. 涓嶆妸鈥滆鍒掍腑鈥濆啓鎴愨€滃凡瀹屾垚鈥?
3. 鍚庣画姣忔帹杩涗竴闃舵缁х画杩藉姞

## 2. 褰撳墠鎬昏繘搴?

褰撳墠闃舵鐩爣锛?

`CNBlogs / Bilibili -> AI Rewrite -> Blog Draft Publish`

鎬讳綋杩涘害鍒ゆ柇锛?

- 鏋舵瀯钃濆浘锛氬凡瀹屾垚
- 椋庨櫓涓庝緷璧栬褰曪細宸插畬鎴?
- 鏈€灏忓唴瀹规ā鍨嬶細宸插畬鎴?
- 鏂板紩鎿庣洰褰曢鏋讹細宸插畬鎴?
- 閲囬泦妗ユ帴锛氬凡瀹屾垚
- AI 鏀瑰啓妗ユ帴锛氬凡瀹屾垚
- 鑽夌鍙戝竷妗ユ帴锛氬凡瀹屾垚
- `content_items` 鐘舵€佸洖鍐欙細宸插畬鎴?
- `scheduler_center` 鎺ョ嚎鎬?pipeline锛氬凡瀹屾垚鍩虹鎺ュ叆
- 鐪熷疄闂幆鑱旇皟锛氭湭瀹屾垚

## 3. 宸蹭慨鏀瑰唴瀹?

### 3.1 鏂囨。

鏂板锛?

- [content_hub_target_architecture.md](/D:/Python/content_hub/apps/platform/docs/content_hub_target_architecture.md)
- [content_hub_risks_and_dependencies.md](/D:/Python/content_hub/apps/platform/docs/content_hub_risks_and_dependencies.md)
- [content_hub_change_log_and_progress.md](/D:/Python/content_hub/apps/platform/docs/content_hub_change_log_and_progress.md)

浣滅敤锛?

- 鐩爣鏋舵瀯钃濆浘
- 椋庨櫓銆佷緷璧栥€佸閮ㄥ弬鏁版竻鍗?
- 鏈枃浠讹細鏀瑰姩涓庤繘搴︽寔缁褰?

### 3.2 鏁版嵁妯″瀷涓庤縼绉?

淇敼锛?

- [models.py](/D:/Python/content_hub/apps/platform/models.py)

鏂板锛?

- [f3a1c2d4e5f6_add_content_items.py](/D:/Python/content_hub/apps/platform/migrations/versions/f3a1c2d4e5f6_add_content_items.py)

鍐呭锛?

- 鏂板 `ContentItem`
- 鏂板 `content_items` 琛?
- 澧炲姞鍞竴閿細`source_type + source_id`
- 澧炲姞 `pipeline_status` / `publish_status` 绛夎繍琛屾€佸瓧娈?

### 3.3 CRUD 灞?

鏂板锛?

- [crud_content_item.py](/D:/Python/content_hub/apps/platform/crud/crud_content_item.py)

淇敼锛?

- [__init__.py](/D:/Python/content_hub/apps/platform/crud/__init__.py)

鍐呭锛?

- 鏂板 `content_items` 鐨勬煡璇€佸垱寤恒€佹洿鏂版搷浣?

### 3.4 鏂板紩鎿庣洰褰曢鏋?

鏂板鐩綍锛?

- [apps/fetcher_engine](/D:/Python/content_hub/apps/fetcher_engine)
- [apps/ai_processor](/D:/Python/content_hub/apps/ai_processor)
- [apps/publisher_engine](/D:/Python/content_hub/apps/publisher_engine)
- [apps/workflow_engine](/D:/Python/content_hub/apps/workflow_engine)

鍐呭锛?

- 鍩虹鍖呯粨鏋?
- runtime / connectors / processors / adapters / registry / pipeline

### 3.5 宸ヤ綔娴佸绾︿笌娉ㄥ唽琛?

鏂板锛?

- [contracts.py](/D:/Python/content_hub/apps/workflow_engine/registry/contracts.py)
- [plugin_registry.py](/D:/Python/content_hub/apps/workflow_engine/registry/plugin_registry.py)
- [static_registry.py](/D:/Python/content_hub/apps/workflow_engine/registry/static_registry.py)
- [settings.py](/D:/Python/content_hub/apps/workflow_engine/registry/settings.py)
- [bootstrap.py](/D:/Python/content_hub/apps/workflow_engine/registry/bootstrap.py)

鍐呭锛?

- `Fetcher / Processor / Publisher`
- `SourceItem / ContentAsset / PublishResult`
- `AIProcessorConfig`
- 闈欐€佹敞鍐岃〃
- 榛樿娉ㄥ唽鍏ュ彛

### 3.6 閲囬泦鍣ㄦ帴鍏?

鏂板鎴栦慨鏀癸細

- [base.py](/D:/Python/content_hub/apps/fetcher_engine/runtime/base.py)
- [fetcher.py](/D:/Python/content_hub/apps/fetcher_engine/connectors/cnblogs/fetcher.py)
- [fetcher.py](/D:/Python/content_hub/apps/fetcher_engine/connectors/bilibili/fetcher.py)

鍐呭锛?

- `CNBlogsFetcher` 澶嶇敤 `ado_repost` RSS 閫傞厤鍣?
- `BilibiliFetcher` 澶嶇敤 `ado_repost` RSS 閫傞厤鍣?

### 3.7 AI 鏀瑰啓鎺ュ叆

鏂板鎴栦慨鏀癸細

- [base.py](/D:/Python/content_hub/apps/ai_processor/runtime/base.py)
- [processor.py](/D:/Python/content_hub/apps/ai_processor/processors/rewrite/processor.py)

鍐呭锛?

- 鎺ュ叆鐜版湁 `llm_client.py`
- 鏀寔 `local / openai / anthropic` 閰嶇疆璺緞
- 鏀寔 `skip / raw / retry` 闄嶇骇绛栫暐

### 3.8 鍙戝竷鍣ㄦ帴鍏?

鏂板鎴栦慨鏀癸細

- [base.py](/D:/Python/content_hub/apps/publisher_engine/runtime/base.py)
- [settings.py](/D:/Python/content_hub/apps/publisher_engine/runtime/settings.py)
- [publisher.py](/D:/Python/content_hub/apps/publisher_engine/adapters/blog/publisher.py)

鍐呭锛?

- 澶嶇敤 `ado_repost` draft publishing client
- 褰撳墠鐩爣鏄?platform 鍐呴儴鑽夌鎺ュ彛
- disabled 妯″紡瀹夊叏杩斿洖锛屼笉璇彂璇锋眰

### 3.9 绾挎€ф祦姘寸嚎

鏂板鎴栦慨鏀癸細

- [linear_pipeline.py](/D:/Python/content_hub/apps/workflow_engine/pipeline/linear_pipeline.py)
- [payloads.py](/D:/Python/content_hub/apps/workflow_engine/pipeline/payloads.py)
- [content_repository.py](/D:/Python/content_hub/apps/workflow_engine/runtime/content_repository.py)

鍐呭锛?

- `fetch -> process -> publish`
- 璋冨害 payload 瑙ｆ瀽
- 鎶撳彇/澶勭悊/鍙戝竷鐘舵€佸啓鍥?`content_items`
- 已移除对旧目录桥接导入的依赖

### 3.10 璋冨害涓績鎺ュ叆

淇敼锛?

- [dispatcher.py](/D:/Python/content_hub/apps/platform/scheduler_center/dispatcher.py)
- [__init__.py](/D:/Python/content_hub/apps/platform/scheduler_center/__init__.py)

鍐呭锛?

- 鏂板 `content.pipeline.linear` 鏈湴鎵ц鍒嗘敮
- 閬囧埌璇ヤ换鍔＄被鍨嬫椂涓嶅啀璧拌繙绔?agent HTTP
- 鐩存帴鍦ㄨ皟搴﹁繘绋嬪唴杩愯 `LinearPipelineRunner`
- 瀵?`platform` 鏍囧噯搴撳啿绐佸鍔犺皟搴︿晶瀵煎叆淇

## 4. 宸茶ˉ娴嬭瘯

鏂板锛?

- [test_content_pipeline_contracts.py](/D:/Python/content_hub/apps/platform/tests/test_content_pipeline_contracts.py)
- [test_content_item_crud.py](/D:/Python/content_hub/apps/platform/tests/test_content_item_crud.py)
- [test_registry_bootstrap.py](/D:/Python/content_hub/apps/workflow_engine/tests/test_registry_bootstrap.py)
- [test_linear_pipeline_payload.py](/D:/Python/content_hub/apps/workflow_engine/tests/test_linear_pipeline_payload.py)
- [test_blog_publisher.py](/D:/Python/content_hub/apps/publisher_engine/tests/test_blog_publisher.py)

褰撳墠楠岃瘉杩囩殑鐐癸細

- `content_items` 寤鸿〃
- `content_items` CRUD
- registry bootstrap
- linear payload 瑙ｆ瀽
- blog publisher disabled 妯″紡
- scheduler dispatcher 鍙鍏ュ苟璇嗗埆鏈湴 pipeline 鍒嗘敮

## 5. 褰撳墠浠嶆湭瀹屾垚鐨勪簨椤?

### 楂樹紭鍏堢骇

1. 鎻愪氦涓€涓湡瀹炵殑 `content.pipeline.linear` 璋冨害浠诲姟骞惰窇閫?
2. 灏嗘姄鍙栫粨鏋滅湡姝ｅ啓鍏ユ暟鎹簱鍚庢煡鐪嬪唴瀹规槸鍚︽纭?
3. 楠岃瘉 AI 鏀瑰啓鍚?`processed_content` 鏄惁钀藉簱
4. 楠岃瘉鍙戝竷鎴愬姛鍚?`publish_status` 鏄惁鏇存柊

### 涓紭鍏堢骇

1. 鐢ㄧ湡瀹?feed URL 鏇挎崲榛樿鍗犱綅鍊?
2. 鐢ㄧ湡瀹?LLM API 璺戜竴杞敼鍐?
3. 鎶婅皟搴﹀叆鍙ｅ寘瑁呮垚鏇存槗璋冪敤鐨勫唴閮?API

### 浣庝紭鍏堢骇

1. 鎶婃棫妗ユ帴瀹炵幇閫愭杩佸嚭
2. 褰诲簳娑堥櫎 `apps/platform` 鍛藉悕鍐茬獊
3. 閫愭杩佸線 `apps/web_console`

## 6. 褰撳墠闃诲

鏈€涓昏鐨勯樆濉炲凡缁忎粠鈥滀唬鐮佹病鏈夆€濆彉鎴愨€滃閮ㄥ弬鏁拌繕娌″畾鈥濓細

1. 鍗氬鍥湡瀹?feed URL
2. B 绔欑湡瀹?feed URL / UP 涓?ID
3. 鐪熷疄 LLM API key
4. 鐪熷疄 LLM base URL
5. 鐪熷疄妯″瀷鍚?
6. 鏄惁缁х画鍏堟姇閫掑埌 platform 鑽夌绠?

## 7. 涓嬩竴姝ュ缓璁?

鏈€鍚堢悊鐨勪笅涓€姝ワ細

1. 鏂板涓€涓唴閮ㄨЕ鍙戝叆鍙ｏ紝涓撻棬鎻愪氦 `content.pipeline.linear`
2. 鐢ㄤ竴缁勫浐瀹氭祴璇?payload 璺戜竴娆¤皟搴︿换鍔?
3. 璇诲洖 `scheduler_tasks` 鍜?`content_items` 楠岃瘉鍏ㄩ摼璺粨鏋?

## 8. 鏈闃舵琛ュ厖

鏈樁娈垫柊澧烇細

- 鍐呴儴瑙﹀彂鍏ュ彛 `/api/internal/tasks/content-pipeline/linear/run`
- 瀵瑰簲 schema 鏂囦欢 [pipeline.py](/D:/Python/content_hub/apps/platform/schemas/pipeline.py)
- `schemas/__init__.py` 宸插鍑虹嚎鎬?pipeline 璇锋眰妯″瀷
- `routers/internal_tasks.py` 宸叉敮鎸佹彁浜?`content.pipeline.linear`

鏂板楠岃瘉锛?

- 鏂?pipeline schema 鍙鍏?
- internal task 璺敱鍙鍏ユ柊鐨?linear pipeline 瑙﹀彂鍏ュ彛

褰撳墠鎺ㄨ崘鐨勫疄闄呰仈璋冨叆鍙ｏ細

- 閫氳繃 `/api/internal/tasks/content-pipeline/linear/run` 鎻愪氦涓€鏉′换鍔?
- 鐒跺悗鏌ヨ scheduler task 鐘舵€?
- 鍐嶆鏌?`content_items` 琛ㄤ腑鐨勭姸鎬佸彉鍖?

## 9. 鏈闃舵缁撹

鍒板綋鍓嶄负姝紝宸茬粡涓嶆槸鈥滄灦鏋勮璁洪樁娈碘€濓紝鑰屾槸鈥滈棴鐜仈璋冨墠闃舵鈥濄€?

涔熷氨鏄锛?

- 钃濆浘鏈変簡
- 椋庨櫓璁拌处鏈変簡
- 鏁版嵁妯″瀷鏈変簡
- 涓夌被寮曟搸楠ㄦ灦鏈変簡
- 璋冨害鎺ョ嚎涔熸湁浜?

鐜板湪宸殑鏄竴杞湡瀹炰换鍔℃墽琛岄獙璇併€?
