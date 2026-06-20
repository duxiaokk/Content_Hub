import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Drawer, Form, Input, Select, Space, Switch, Table, Typography, message } from 'antd';
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

type SourceFormValues = Omit<SourceConfigPayload, 'config'> & {
  configText: string;
};

export default function SourcesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<SourceConfig | null>(null);
  const [form] = Form.useForm<SourceFormValues>();

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
    });
    setDrawerOpen(true);
  };

  const openEdit = (item: SourceConfig) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      source_type: item.source_type,
      enabled: item.enabled,
      channels: item.channels || [],
      keywords: item.keywords || [],
      lookback_hours: item.lookback_hours,
      item_limit: item.item_limit,
      dedup_window_hours: item.dedup_window_hours,
      configText: JSON.stringify(item.config || {}, null, 2),
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    let config: Record<string, unknown> = {};
    try {
      config = values.configText ? (JSON.parse(values.configText) as Record<string, unknown>) : {};
    } catch {
      message.error('配置 JSON 格式不正确');
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
          <Form.Item
            name="configText"
            label="配置 JSON"
            tooltip="按不同 source_type 填写实际抓取参数，例如 feed_url、subreddit、username、urls 等。"
          >
            <Input.TextArea rows={8} placeholder={'{\n  "urls": [\n    "https://www.xiaohongshu.com/discovery/item/xxx?xsec_token=..."\n  ]\n}'} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
