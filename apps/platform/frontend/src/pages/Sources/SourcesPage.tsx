import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
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
import { createSource, getSources, toggleSource, triggerFetch, updateSource } from '../../services/api';
import type { SourceSubscription, SourceSubscriptionPayload } from '../../types';

const { Title, Text } = Typography;

const sourceTypeOptions = [
  { label: 'RSS', value: 'rss' },
  { label: 'GitHub', value: 'github' },
  { label: 'Reddit', value: 'reddit' },
  { label: 'CNBlogs', value: 'cnblogs' },
  { label: 'Bilibili', value: 'bilibili' },
];

const initialValues: SourceSubscriptionPayload = {
  source_type: 'rss',
  source_name: '',
  account_identifier: '',
  feed_url: '',
  schedule_expression: '',
  category: '',
  default_tags: '',
};

export default function SourcesPage() {
  const [items, setItems] = useState<SourceSubscription[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<SourceSubscription | null>(null);
  const [form] = Form.useForm<SourceSubscriptionPayload>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSources();
      setItems(data || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载信源失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(initialValues);
    setDrawerOpen(true);
  };

  const openEdit = (item: SourceSubscription) => {
    setEditing(item);
    form.setFieldsValue({
      source_type: item.source_type,
      source_name: item.source_name,
      account_identifier: item.account_identifier || '',
      feed_url: item.feed_url || '',
      category: item.category || '',
      default_tags: item.default_tags || '',
      schedule_expression: '',
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editing) {
        await updateSource(editing.id, values);
        message.success('信源已更新');
      } else {
        await createSource(values);
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

  const handleToggle = async (item: SourceSubscription, enabled: boolean) => {
    try {
      await toggleSource(item.id, enabled);
      message.success(enabled ? '信源已启用' : '信源已停用');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '状态更新失败');
    }
  };

  const handleTriggerFetch = async (item: SourceSubscription) => {
    try {
      await triggerFetch(item.id);
      message.success(`已触发 ${item.source_name} 抓取任务`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发抓取失败');
    }
  };

  const columns = useMemo<ColumnsType<SourceSubscription>>(
    () => [
      {
        title: '信源',
        key: 'source_name',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.source_name}</Text>
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
          <Switch checked={value} onChange={(checked) => handleToggle(record, checked)} />
        ),
      },
      {
        title: '分类',
        dataIndex: 'category',
        key: 'category',
        width: 140,
        render: (value?: string) => value || '-',
      },
      {
        title: '账号 / Feed',
        key: 'account_identifier',
        render: (_, record) => record.account_identifier || record.feed_url || '-',
      },
      {
        title: '游标',
        dataIndex: 'last_cursor',
        key: 'last_cursor',
        width: 220,
        ellipsis: true,
        render: (value?: string) => value || '-',
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 180,
        render: (value?: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
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
            <Button size="small" type="primary" onClick={() => handleTriggerFetch(record)}>
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
          <Text type="secondary">查看、启停和新增信源，并手动触发抓取。</Text>
        </div>
        <Space>
          <Button onClick={load}>刷新</Button>
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
            <Button type="primary" loading={submitting} onClick={handleSubmit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" initialValues={initialValues}>
          <Form.Item name="source_type" label="来源类型" rules={[{ required: true, message: '请选择来源类型' }]}>
            <Select options={sourceTypeOptions} disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="source_name" label="信源名称" rules={[{ required: true, message: '请输入信源名称' }]}>
            <Input placeholder="例如：Tech Radar RSS" />
          </Form.Item>
          <Form.Item name="account_identifier" label="账号标识">
            <Input placeholder="例如：openai / python" />
          </Form.Item>
          <Form.Item name="feed_url" label="Feed URL">
            <Input placeholder="例如：https://example.com/feed.xml" />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Input placeholder="例如：AI / Backend" />
          </Form.Item>
          <Form.Item name="default_tags" label="默认标签">
            <Input placeholder="例如：ai, llm, tooling" />
          </Form.Item>
          <Form.Item name="schedule_expression" label="调度表达式">
            <Input placeholder="可选，后端当前未在更新接口持久化" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
