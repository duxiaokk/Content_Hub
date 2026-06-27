import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Collapse,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import {
  createSourceConfig,
  deleteSourceConfig,
  listSourceConfigs,
  triggerSourceRun,
  updateSourceConfig,
} from '../../services/api';
import type { SourceConfig, SourceConfigPayload } from '../../types';

const { Title, Text } = Typography;

const sourceTypeOptions = [
  { label: 'RSS', value: 'rss' },
  { label: 'GitHub Trending', value: 'github_trending' },
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

interface SourceFormValues extends Omit<SourceConfigPayload, 'config'> {
  configText: string;
  schedule_expression?: string;
  retry_times?: number;
  retry_backoff_seconds?: number;
  request_timeout_seconds?: number;
  require_source_url?: boolean;
  require_raw_content?: boolean;
  alert_on_empty?: boolean;
  alert_webhook_url?: string;
  config_feed_url?: string;
  config_subreddit?: string;
  config_language?: string;
  config_since?: string;
  config_urls?: string;
}

function buildSourceIdentifier(item: SourceConfig): string {
  const config = item.config || {};
  if (typeof config.feed_url === 'string' && config.feed_url.trim()) {
    return config.feed_url.trim();
  }
  if (typeof config.subreddit === 'string' && config.subreddit.trim()) {
    return `r/${config.subreddit.trim()}`;
  }
  if (typeof config.language === 'string' && config.language.trim()) {
    return `language:${config.language.trim()}`;
  }
  if (Array.isArray(config.urls) && config.urls.length > 0) {
    return `${config.urls.length} links`;
  }
  if (item.channels?.length) {
    return item.channels.join(', ');
  }
  return '-';
}

export default function PolishedSourcesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<SourceConfig | null>(null);
  const [importUrl, setImportUrl] = useState('');
  const [form] = Form.useForm<SourceFormValues>();
  const sourceType = Form.useWatch('source_type', form);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSourceConfigs();
      setItems(data || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load sources');
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
      schedule_expression: '0 */6 * * *',
      retry_times: 2,
      retry_backoff_seconds: 1,
      request_timeout_seconds: 30,
      require_source_url: false,
      require_raw_content: false,
      alert_on_empty: false,
      alert_webhook_url: '',
      config_feed_url: '',
      config_subreddit: '',
      config_language: '',
      config_since: 'daily',
      config_urls: '',
    });
    setImportUrl('');
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
      schedule_expression: (cfg.schedule_expression as string) || '',
      retry_times: Number(cfg.retry_times || 0),
      retry_backoff_seconds: Number(cfg.retry_backoff_seconds || 0),
      request_timeout_seconds: Number(cfg.request_timeout_seconds || 30),
      require_source_url: Boolean(cfg.validation_rules && (cfg.validation_rules as Record<string, unknown>).require_source_url),
      require_raw_content: Boolean(cfg.validation_rules && (cfg.validation_rules as Record<string, unknown>).require_raw_content),
      alert_on_empty: Boolean(cfg.alert_on_empty),
      alert_webhook_url:
        (cfg.alert_policy && ((cfg.alert_policy as Record<string, unknown>).webhook_url as string)) || '',
      config_feed_url: (cfg.feed_url as string) || '',
      config_subreddit: (cfg.subreddit as string) || '',
      config_language: (cfg.language as string) || '',
      config_since: (cfg.since as string) || 'daily',
      config_urls: Array.isArray(cfg.urls) ? (cfg.urls as string[]).join('\n') : ((cfg.urls as string) || ''),
    });
    setDrawerOpen(true);
  };

  const extractUrls = (text: string): string[] => {
    const regex = /https?:\/\/[^\s"'<>]+/gi;
    return text.match(regex) || [];
  };

  const parseLink = (url: string): { source_type: string; config: Record<string, unknown> } | null => {
    const raw = url.trim();
    if (!raw) return null;

    let targetUrl: string | null = null;
    try {
      new URL(raw);
      targetUrl = raw;
    } catch {
      const extracted = extractUrls(raw);
      targetUrl = extracted.length > 0 ? extracted[extracted.length - 1] : null;
      if (!targetUrl) return null;
    }

    try {
      const u = new URL(targetUrl);
      const hostname = u.hostname.toLowerCase();

      if (hostname.includes('xiaohongshu.com') || hostname.includes('xhslink.com')) {
        return { source_type: 'xiaohongshu', config: { urls: [targetUrl] } };
      }
      if (hostname.includes('bilibili.com')) {
        const spaceMatch = u.pathname.match(/\/space\/(\d+)/);
        if (spaceMatch) {
          return {
            source_type: 'bilibili',
            config: { feed_url: `https://rsshub.app/bilibili/user/video/${spaceMatch[1]}` },
          };
        }
        return { source_type: 'bilibili', config: { feed_url: targetUrl } };
      }
      if (hostname.includes('reddit.com') || hostname.includes('redd.it')) {
        const match = u.pathname.match(/\/r\/([^/]+)/);
        if (match) {
          return { source_type: 'reddit', config: { subreddit: match[1] } };
        }
      }
      if (hostname.includes('github.com') && u.pathname.includes('/trending')) {
        const langMatch = u.pathname.match(/\/trending\/([^/]+)/);
        return {
          source_type: 'github_trending',
          config: langMatch ? { language: langMatch[1] } : {},
        };
      }
      if (hostname.includes('cnblogs.com') || hostname.includes('feed.cnblogs.com')) {
        return { source_type: 'cnblogs', config: { feed_url: targetUrl } };
      }
      if (hostname.includes('rsshub.app') || targetUrl.endsWith('.xml') || targetUrl.endsWith('.rss') || targetUrl.includes('/feed')) {
        return { source_type: 'rss', config: { feed_url: targetUrl } };
      }
      return null;
    } catch {
      return null;
    }
  };

  const handleParseLink = () => {
    if (!importUrl.trim()) {
      message.warning('请先粘贴链接');
      return;
    }

    const result = parseLink(importUrl);
    if (!result) {
      message.error('无法识别该链接，请手动选择来源类型');
      return;
    }

    const { source_type, config } = result;
    const updates: Record<string, unknown> = { source_type };
    if (source_type === 'xiaohongshu') {
      updates.config_urls = Array.isArray(config.urls) ? (config.urls as string[]).join('\n') : '';
    } else if (source_type === 'reddit') {
      updates.config_subreddit = config.subreddit || '';
    } else if (source_type === 'github_trending') {
      updates.config_language = config.language || '';
      updates.config_since = 'daily';
    } else if (source_type === 'rss' || source_type === 'cnblogs' || source_type === 'bilibili') {
      updates.config_feed_url = config.feed_url || '';
    }

    form.setFieldsValue(updates);
    message.success(`已识别为 ${source_type}，配置已自动填充`);
    setImportUrl('');
  };

  const buildConfig = (values: SourceFormValues): Record<string, unknown> => {
    const config: Record<string, unknown> = {};
    const st = values.source_type;

    if (st === 'rss' || st === 'cnblogs' || st === 'bilibili') {
      if (values.config_feed_url?.trim()) config.feed_url = values.config_feed_url.trim();
    } else if (st === 'github_trending') {
      if (values.config_language?.trim()) config.language = values.config_language.trim();
      if (values.config_since) config.since = values.config_since;
    } else if (st === 'reddit') {
      if (values.config_subreddit?.trim()) config.subreddit = values.config_subreddit.trim();
    } else if (st === 'xiaohongshu') {
      if (values.config_urls?.trim()) {
        config.urls = values.config_urls
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean);
      }
    }

    if (values.schedule_expression?.trim()) config.schedule_expression = values.schedule_expression.trim();
    config.retry_times = Number(values.retry_times || 0);
    config.retry_backoff_seconds = Number(values.retry_backoff_seconds || 0);
    config.request_timeout_seconds = Number(values.request_timeout_seconds || 30);
    config.validation_rules = {
      require_source_url: Boolean(values.require_source_url),
      require_raw_content: Boolean(values.require_raw_content),
    };
    config.alert_on_empty = Boolean(values.alert_on_empty);
    config.alert_policy = {
      channels: values.alert_webhook_url?.trim() ? ['log', 'webhook'] : ['log'],
      webhook_url: values.alert_webhook_url?.trim() || undefined,
      volume_anomaly_ratio: 0.7,
    };

    const text = values.configText?.trim();
    if (text && text !== '{}') {
      const override = JSON.parse(text) as Record<string, unknown>;
      return { ...config, ...override };
    }

    return config;
  };

  const validateConfig = (config: Record<string, unknown>, st: string): string | null => {
    if (st === 'rss') {
      const url = (config.feed_url as string) || '';
      if (!url) return 'RSS 链接不能为空';
      try {
        new URL(url);
      } catch {
        return 'RSS 链接格式不正确，需要以 http:// 或 https:// 开头';
      }
    } else if (st === 'cnblogs' || st === 'bilibili') {
      const url = (config.feed_url as string) || '';
      if (url) {
        try {
          new URL(url);
        } catch {
          return 'RSS 链接格式不正确，需要以 http:// 或 https:// 开头';
        }
      }
    } else if (st === 'reddit') {
      const sub = (config.subreddit as string) || '';
      if (!sub) return 'Subreddit 名称不能为空';
      if (!/^[a-zA-Z0-9_-]+$/.test(sub)) {
        return 'Subreddit 名称只能包含字母、数字、下划线和连字符';
      }
    } else if (st === 'github_trending') {
      const lang = (config.language as string) || '';
      if (lang && !/^[a-zA-Z0-9+#\s-]+$/.test(lang)) {
        return '编程语言名称格式不正确';
      }
    } else if (st === 'xiaohongshu') {
      const urls = config.urls;
      if (!Array.isArray(urls) || urls.length === 0) return '至少填写一个笔记链接';
      for (const url of urls) {
        if (typeof url !== 'string') return '链接格式不正确';
        try {
          new URL(url);
        } catch {
          return `链接格式不正确: ${url}`;
        }
      }
    }
    return null;
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
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
    const configError = validateConfig(config, values.source_type);
    if (configError) {
      message.error(configError);
      return;
    }

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
      const errorMsg = error instanceof Error ? error.message : '保存失败';
      if (errorMsg.toLowerCase().includes('conflict') || errorMsg.includes('409')) {
        message.error('该信源名称已存在，请更换名称');
      } else {
        message.error(errorMsg);
      }
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
      message.success(`已提交抓取，fetch_run_id=${result.fetch_run_id}。请到“采集监控”查看执行状态。`, 5);
      navigate('/fetch-runs');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发抓取失败');
    }
  };

  const handleDelete = (item: SourceConfig) => {
    Modal.confirm({
      title: '确认删除信源',
      content: `确定要删除“${item.name}”吗？关联的采集历史也会一并删除。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        try {
          await deleteSourceConfig(item.id);
          message.success('信源已删除');
          await load();
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败');
        }
      },
    });
  };

  const columns = useMemo<ColumnsType<SourceConfig>>(
    () => [
      {
        title: '信源',
        key: 'name',
        width: 220,
        render: (_, record) => (
          <div className="source-cell">
            <Text strong className="source-cell__title">
              {record.name}
            </Text>
            <Text type="secondary">{record.source_type}</Text>
          </div>
        ),
      },
      {
        title: '状态',
        dataIndex: 'enabled',
        key: 'enabled',
        width: 96,
        render: (value: boolean, record) => (
          <Switch checked={value} onChange={(checked) => void handleToggle(record, checked)} />
        ),
      },
      {
        title: '链接 / 标识',
        key: 'identifier',
        width: 320,
        render: (_, record) => (
          <div className="source-identifier">
            <Text className="source-identifier__value">{buildSourceIdentifier(record)}</Text>
            {record.channels?.length ? (
              <Text type="secondary" className="source-identifier__meta">
                {record.channels.join(', ')}
              </Text>
            ) : null}
          </div>
        ),
      },
      {
        title: '频率',
        dataIndex: 'schedule_expression',
        key: 'schedule_expression',
        width: 150,
        render: (value?: string | null) => <span className="mono-truncate">{value || '-'}</span>,
      },
      {
        title: '标签',
        dataIndex: 'keywords',
        key: 'keywords',
        width: 220,
        render: (value?: string[]) =>
          value && value.length ? (
            <Space wrap size={[4, 4]} className="source-tag-list">
              {value.map((keyword) => (
                <Tag key={keyword}>{keyword}</Tag>
              ))}
            </Space>
          ) : (
            '-'
          ),
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
          <Space wrap size={8} className="source-actions">
            <Button size="small" onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Button size="small" type="primary" onClick={() => void handleTriggerFetch(record)}>
              手动抓取
            </Button>
            <Button size="small" danger onClick={() => handleDelete(record)}>
              删除
            </Button>
          </Space>
        ),
      },
    ],
    []
  );

  const renderDynamicConfig = () => {
    switch (sourceType) {
      case 'rss':
        return (
          <Form.Item
            name="config_feed_url"
            label="RSS 链接"
            rules={[
              { required: true, message: 'RSS 链接不能为空' },
              { type: 'url', message: 'RSS 链接格式不正确' },
            ]}
            tooltip="RSS 订阅地址，例如 https://rsshub.app/36kr/news"
          >
            <Input placeholder="https://rsshub.app/..." />
          </Form.Item>
        );
      case 'cnblogs':
      case 'bilibili':
        return (
          <Form.Item
            name="config_feed_url"
            label="RSS 链接"
            tooltip={
              sourceType === 'cnblogs'
                ? '留空则使用默认博客园 RSS'
                : '留空则使用默认 Bilibili 用户 RSS'
            }
          >
            <Input
              placeholder={
                sourceType === 'cnblogs'
                  ? 'https://feed.cnblogs.com/blog/u/xxx/rss'
                  : 'https://rsshub.app/bilibili/user/video/xxx'
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
              tooltip="例如 python、javascript、go。留空表示全部语言"
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
            rules={[
              { required: true, message: 'Subreddit 名称不能为空' },
              { pattern: /^[a-zA-Z0-9_-]+$/, message: '只能包含字母、数字、下划线和连字符' },
            ]}
            tooltip="例如 artificial、programming"
          >
            <Input placeholder="artificial" />
          </Form.Item>
        );
      case 'xiaohongshu':
        return (
          <Form.Item
            name="config_urls"
            label="笔记链接"
            rules={[{ required: true, message: '至少填写一个笔记链接' }]}
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
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Source Console</span>
          <Title level={3} className="page-header__title">
            信源管理
          </Title>
          <Text className="page-header__description">
            查看、启停和新增信源，统一维护采集频率、校验规则与告警策略，并可直接触发抓取任务。
          </Text>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => void load()}>刷新</Button>
          <Button type="primary" onClick={openCreate}>
            新增信源
          </Button>
        </div>
      </div>

      <Card className="surface-card table-card">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={false}
          scroll={{ x: 1280 }}
        />
      </Card>

      <Drawer
        title={editing ? '编辑信源' : '新增信源'}
        width={560}
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
          <Card size="small" className="surface-card detail-card" title="快速导入" style={{ marginBottom: 16 }}>
            <Form.Item label="从链接导入" style={{ marginBottom: 0 }}>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder="粘贴 RSS / Reddit / 小红书 / B 站空间 / GitHub Trending 链接..."
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  onPressEnter={handleParseLink}
                />
                <Button onClick={handleParseLink}>解析</Button>
              </Space.Compact>
            </Form.Item>
            <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
              支持 RSS、Reddit 社区、小红书笔记、Bilibili 空间、GitHub Trending 等链接。
            </Text>
          </Card>

          <Form.Item name="source_type" label="来源类型" rules={[{ required: true, message: '请选择来源类型' }]}>
            <Select options={sourceTypeOptions} />
          </Form.Item>
          <Form.Item name="name" label="信源名称" rules={[{ required: true, message: '请输入信源名称' }]}>
            <Input placeholder="例如 Tech Radar RSS" />
          </Form.Item>
          <Form.Item name="channels" label="渠道">
            <Select mode="tags" tokenSeparators={[',']} placeholder="例如 web, rss" />
          </Form.Item>
          <Form.Item name="keywords" label="关键词">
            <Select mode="tags" tokenSeparators={[',']} placeholder="例如 ai, llm, tooling" />
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
          <Form.Item
            name="schedule_expression"
            label="采集频率（Cron）"
            tooltip="支持 *, */n, 逗号和固定值，例如 0 */6 * * *"
          >
            <Input placeholder="0 */6 * * *" />
          </Form.Item>
          <Form.Item name="retry_times" label="网络重试次数">
            <Input type="number" min={0} max={10} />
          </Form.Item>
          <Form.Item name="retry_backoff_seconds" label="重试退避秒数">
            <Input type="number" min={0} max={30} step="0.5" />
          </Form.Item>
          <Form.Item name="request_timeout_seconds" label="请求超时秒数">
            <Input type="number" min={5} max={300} />
          </Form.Item>
          <Form.Item name="require_source_url" label="要求来源链接" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="require_raw_content" label="要求原始正文" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="alert_on_empty" label="空结果告警" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="alert_webhook_url" label="告警 Webhook">
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>

          {renderDynamicConfig()}

          <Collapse ghost>
            <Collapse.Panel header="高级配置（JSON）" key="advanced">
              <Form.Item
                name="configText"
                tooltip="按 source_type 填写实际抓取参数，可覆盖上方表单值。"
              >
                <Input.TextArea
                  rows={6}
                  placeholder={"{\n  \"urls\": [\n    \"https://www.xiaohongshu.com/discovery/item/xxx?xsec_token=...\"\n  ]\n}"}
                />
              </Form.Item>
            </Collapse.Panel>
          </Collapse>
        </Form>
      </Drawer>
    </div>
  );
}
