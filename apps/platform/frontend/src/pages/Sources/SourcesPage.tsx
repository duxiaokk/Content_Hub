import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Collapse, Drawer, Form, Input, Select, Space, Switch, Table, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { createSourceConfig, listSourceConfigs, triggerSourceRun, updateSourceConfig } from '../../services/api';
import type { SourceConfig, SourceConfigPayload } from '../../types';

const { Title, Text } = Typography;

const sourceTypeOptions = [
  { label: 'RSS', value: 'rss' },
  { label: 'GitHub', value: 'github_trending' },
  { label: 'Reddit', value: 'reddit' },
  { label: 'CNBlogs', value: 'cnblogs' },
  { label: 'Bilibili', value: 'bilibili' },
  { label: '小红书', value: 'xiaohongshu' },
];

const sinceOptions = [
  { label: 'Daily', value: 'daily' },
  { label: 'Weekly', value: 'weekly' },
  { label: 'Monthly', value: 'monthly' },
];

const initialValues: SourceConfigPayload = {
  name: '',
  source_type: 'rss',
  enabled: true,
  channels: [],
  keywords: [],
  lookback_hours: 24,
  item_limit: 20,
  dedup_window_hours: 24,
  config: {},
};

// 扩展表单值，包含动态配置字段
interface SourceFormValues extends Omit<SourceConfigPayload, 'config'> {
  configText: string;
  config_feed_url?: string;
  config_subreddit?: string;
  config_language?: string;
  config_since?: string;
  config_urls?: string;
}

export default function SourcesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<SourceConfig | null>(null);
  const [form] = Form.useForm<SourceFormValues>();

  // 监听来源类型变化，用于动态渲染字段
  const sourceType = Form.useWatch('source_type', form);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSourceConfigs();
      setItems(data || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载信源失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      ...initialValues,
      configText: '{}',
      config_feed_url: '',
      config_subreddit: '',
      config_language: '',
      config_since: 'daily',
      config_urls: '',
    });
    setDrawerOpen(true);
  };

  const openEdit = (item: SourceConfig) => {
    setEditing(item);
    const cfg = item.config || {};
    form.setFieldsValue({
      name: item.name,
      source_type: item.source_type,
      enabled: item.enabled,
      channels: item.channels || [],
      keywords: item.keywords || [],
      lookback_hours: item.lookback_hours,
      item_limit: item.item_limit,
      dedup_window_hours: item.dedup_window_hours,
      configText: JSON.stringify(cfg, null, 2),
      // 反解析动态字段
      config_feed_url: (cfg.feed_url as string) || '',
      config_subreddit: (cfg.subreddit as string) || '',
      config_language: (cfg.language as string) || '',
      config_since: (cfg.since as string) || 'daily',
      config_urls: Array.isArray(cfg.urls) ? (cfg.urls as string[]).join('\n') : (cfg.urls as string) || '',
    });
    setDrawerOpen(true);
  };

  // 根据当前 source_type 和表单值自动组装 config
  const buildConfig = (values: SourceFormValues): Record<string, unknown> => {
    const config: Record<string, unknown> = {};
    const st = values.source_type;

    if (st === 'rss' || st === 'cnblogs' || st === 'bilibili') {
      if (values.config_feed_url?.trim()) {
        config.feed_url = values.config_feed_url.trim();
      }
    } else if (st === 'github_trending') {
      if (values.config_language?.trim()) {
        config.language = values.config_language.trim();
      }
      if (values.config_since) {
        config.since = values.config_since;
      }
    } else if (st === 'reddit') {
      if (values.config_subreddit?.trim()) {
        config.subreddit = values.config_subreddit.trim();
      }
    } else if (st === 'xiaohongshu') {
      if (values.config_urls?.trim()) {
        config.urls = values.config_urls
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }

    // 高级 JSON 覆盖（如果用户填写了且不为空对象）
    const text = values.configText?.trim();
    if (text && text !== '{}') {
      try {
        const override = JSON.parse(text) as Record<string, unknown>;
        return { ...config, ...override };
      } catch {
        // 格式错误已在 handleSubmit 中拦截
      }
    }
    return config;
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();

    // 校验高级 JSON 是否合法（如果用户填了）
    const text = values.configText?.trim();
    if (text && text !== '{}') {
      try {
        JSON.parse(text);
      } catch {
        message.error('配置 JSON 格式不正确');
        return;
      }
    }

    const config = buildConfig(values);
    const payload: SourceConfigPayload = {
      name: values.name,
      source_type: values.source_type,
      enabled: values.enabled,
      channels: values.channels,
      keywords: values.keywords,
      lookback_hours: Number(values.lookback_hours),
      item_limit: Number(values.item_limit),
      dedup_window_hours: Number(values.dedup_window_hours),
      config,
    };
    setSubmitting(true);
    try {
      if (editing) {
        await updateSourceConfig(editing.id, payload);
        message.success('信源已更新');
      } else {
        await createSourceConfig(payload);
        message.success('信源已创建');
      }
      setDrawerOpen(false);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggle = async (item: SourceConfig, enabled: boolean) => {
    try {
      await updateSourceConfig(item.id, { enabled });
      message.success(enabled ? '信源已启用' : '信源已停用');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '状态更新失败');
    }
  };

  const handleTriggerFetch = async (item: SourceConfig) => {
    try {
      const result = await triggerSourceRun(item.id, {
        lookback_hours: item.lookback_hours,
        item_limit: item.item_limit,
      });
      message.success(`已提交抓取，fetch_run_id=${result.fetch_run_id}。请到“采集历史”查看执行情况。`, 5);
      navigate('/fetch-runs');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发抓取失败');
    }
  };

  const columns = useMemo<ColumnsType<SourceConfig>>(
    () => [
      {
        title: '信源',
        key: 'name',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.name}</Text>
            <Text type="secondary">{record.source_type}</Text>
          </Space>
        ),
      },
      {
        title: '启用',
        dataIndex: 'enabled',
        key: 'enabled',
        width: 100,
        render: (value: boolean, record) => (
          <Switch checked={value} onChange={(checked) => void handleToggle(record, checked)} />
        ),
      },
      {
        title: '渠道',
        dataIndex: 'channels',
        key: 'channels',
        width: 180,
        render: (value?: string[]) => (value && value.length ? value.join(', ') : '-'),
      },
      {
        title: '关键词',
        dataIndex: 'keywords',
        key: 'keywords',
        render: (value?: string[]) => (value && value.length ? value.join(', ') : '-'),
      },
      {
        title: '游标',
        dataIndex: 'last_cursor',
        key: 'last_cursor',
        width: 220,
        ellipsis: true,
        render: (value?: SourceConfig['last_cursor']) =>
          value === null || value === undefined ? '-' : typeof value === 'string' ? value : JSON.stringify(value),
      },
      {
        title: '最近运行',
        dataIndex: 'last_run_at',
        key: 'last_run_at',
        width: 180,
        render: (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 180,
        render: (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        render: (_, record) => (
          <Space>
            <Button size="small" onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Button size="small" type="primary" onClick={() => void handleTriggerFetch(record)}>
              手动抓取
            </Button>
          </Space>
        ),
      },
    ],
    []
  );

  // 根据来源类型渲染动态配置字段
  const renderDynamicConfig = () => {
    switch (sourceType) {
      case 'rss':
      case 'cnblogs':
      case 'bilibili':
        return (
          <Form.Item
            name="config_feed_url"
            label="RSS 链接"
            tooltip={
              sourceType === 'cnblogs'
                ? '留空则使用默认博客园 RSS'
                : sourceType === 'bilibili'
                  ? '留空则使用默认 UP 主 RSS（RSSHUB）'
                  : 'RSS 订阅地址，例如 https://rsshub.app/36kr/news'
            }
          >
            <Input
              placeholder={
                sourceType === 'cnblogs'
                  ? 'https://feed.cnblogs.com/blog/u/xxx/rss'
                  : sourceType === 'bilibili'
                    ? 'https://rsshub.app/bilibili/user/video/xxx'
                    : 'https://rsshub.app/...'
              }
            />
          </Form.Item>
        );
      case 'github_trending':
        return (
          <>
            <Form.Item
              name="config_language"
              label="编程语言"
              tooltip="例如：python, javascript, go。留空表示全语言"
            >
              <Input placeholder="python" />
            </Form.Item>
            <Form.Item name="config_since" label="时间周期" initialValue="daily">
              <Select options={sinceOptions} />
            </Form.Item>
          </>
        );
      case 'reddit':
        return (
          <Form.Item
            name="config_subreddit"
            label="Subreddit"
            tooltip="Reddit 社区名称，例如：artificial, programming"
          >
            <Input placeholder="artificial" />
          </Form.Item>
        );
      case 'xiaohongshu':
        return (
          <Form.Item
            name="config_urls"
            label="笔记链接"
            tooltip="每行一个笔记分享链接，自动解析内容"
          >
            <Input.TextArea
              rows={4}
              placeholder="https://www.xiaohongshu.com/discovery/item/xxx?xsec_token=..."
            />
          </Form.Item>
        );
      default:
        return null;
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            信源管理
          </Title>
          <Text type="secondary">查看、启停和新增信源，并直接提交抓取任务。</Text>
        </div>
        <Space>
          <Button onClick={() => void load()}>刷新</Button>
          <Button type="primary" onClick={openCreate}>
            新增信源
          </Button>
        </Space>
      </div>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} />
      </Card>

      <Drawer
        title={editing ? '编辑信源' : '新增信源'}
        width={520}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
              保存
            </Button>
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            ...initialValues,
            configText: '{}',
            config_since: 'daily',
          }}
        >
          <Form.Item name="source_type" label="来源类型" rules={[{ required: true, message: '请选择来源类型' }]}>
            <Select options={sourceTypeOptions} />
          </Form.Item>
          <Form.Item name="name" label="信源名称" rules={[{ required: true, message: '请输入信源名称' }]}>
            <Input placeholder="例如：Tech Radar RSS" />
          </Form.Item>
          <Form.Item name="channels" label="渠道">
            <Select mode="tags" tokenSeparators={[',']} placeholder="例如：web, rss" />
          </Form.Item>
          <Form.Item name="keywords" label="关键词">
            <Select mode="tags" tokenSeparators={[',']} placeholder="例如：ai, llm, tooling" />
          </Form.Item>
          <Form.Item name="lookback_hours" label="回看小时数" rules={[{ required: true, message: '请输入回看小时数' }]}>
            <Input type="number" min={1} max={720} />
          </Form.Item>
          <Form.Item name="item_limit" label="抓取条数" rules={[{ required: true, message: '请输入抓取条数' }]}>
            <Input type="number" min={1} max={500} />
          </Form.Item>
          <Form.Item
            name="dedup_window_hours"
            label="去重窗口小时数"
            rules={[{ required: true, message: '请输入去重窗口小时数' }]}
          >
            <Input type="number" min={1} max={720} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>

          {/* 动态配置字段 */}
          {renderDynamicConfig()}

          {/* 高级 JSON 配置（可选） */}
          <Collapse ghost>
            <Collapse.Panel header="高级配置（JSON）" key="advanced">
              <Form.Item
                name="configText"
                tooltip="按不同 source_type 填写实际抓取参数，可覆盖上方表单值。"
              >
                <Input.TextArea
                  rows={6}
                  placeholder={
                    '{\n  "urls": [\n    "https://www.xiaohongshu.com/discovery/item/xxx?xsec_token=..."\n  ]\n}'
                  }
                />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </Form>
      </Drawer>
    </div>
  );
}
