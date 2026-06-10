import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
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
  listSourceConfigs,
  triggerSourceRun,
  updateSourceConfig,
} from '../../services/api';
import type { SourceConfig, SourceConfigPayload } from '../../types';

const { Title, Text } = Typography;

const sourceOptions = [
  { label: 'X', value: 'x' },
  { label: 'YouTube', value: 'youtube' },
  { label: 'Instagram', value: 'instagram' },
  { label: 'RSS', value: 'rss' },
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

export default function SourcesPage() {
  const [items, setItems] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<SourceConfig | null>(null);
  const [form] = Form.useForm<SourceConfigPayload>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSourceConfigs();
      setItems(data || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载数据源失败');
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

  const openEdit = (item: SourceConfig) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      source_type: item.source_type,
      enabled: item.enabled,
      channels: item.channels,
      keywords: item.keywords,
      lookback_hours: item.lookback_hours,
      item_limit: item.item_limit,
      dedup_window_hours: item.dedup_window_hours,
      config: item.config,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editing) {
        await updateSourceConfig(editing.id, values);
        message.success('数据源已更新');
      } else {
        await createSourceConfig(values);
        message.success('数据源已创建');
      }
      setDrawerOpen(false);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRun = async (item: SourceConfig) => {
    try {
      await triggerSourceRun(item.id, {});
      message.success(`已触发 ${item.name}`);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发失败');
    }
  };

  const columns = useMemo<ColumnsType<SourceConfig>>(
    () => [
      {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        render: (value: string, record) => (
          <Space direction="vertical" size={0}>
            <Text strong>{value}</Text>
            <Text type="secondary">{record.source_type}</Text>
          </Space>
        ),
      },
      {
        title: '状态',
        dataIndex: 'enabled',
        key: 'enabled',
        width: 100,
        render: (value: boolean) => (
          <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag>
        ),
      },
      {
        title: '频道/账号',
        dataIndex: 'channels',
        key: 'channels',
        render: (value: string[]) => (value?.length ? value.join(', ') : '-'),
      },
      {
        title: '关键词',
        dataIndex: 'keywords',
        key: 'keywords',
        render: (value: string[]) => (value?.length ? value.join(', ') : '-'),
      },
      {
        title: '采集窗口',
        key: 'lookback_hours',
        width: 140,
        render: (_, record) => `${record.lookback_hours}h / ${record.item_limit} 条`,
      },
      {
        title: '最近运行',
        dataIndex: 'last_run_at',
        key: 'last_run_at',
        width: 180,
        render: (value?: string | null) =>
          value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-',
      },
      {
        title: '操作',
        key: 'actions',
        width: 180,
        render: (_, record) => (
          <Space>
            <Button size="small" onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Button size="small" type="primary" onClick={() => handleRun(record)}>
              立即采集
            </Button>
          </Space>
        ),
      },
    ],
    []
  );

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            数据源配置
          </Title>
          <Text type="secondary">配置采集源，并从平台统一触发运行。</Text>
        </Col>
        <Col>
          <Space>
            <Button onClick={load}>刷新</Button>
            <Button type="primary" onClick={openCreate}>
              新建数据源
            </Button>
          </Space>
        </Col>
      </Row>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} />
      </Card>

      <Drawer
        title={editing ? '编辑数据源' : '新建数据源'}
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
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：RSS-Tech-News" />
          </Form.Item>
          <Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}>
            <Select options={sourceOptions} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="channels" label="频道/账号">
            <Select mode="tags" tokenSeparators={[',']} placeholder="输入频道、账号或 feed URL" />
          </Form.Item>
          <Form.Item name="keywords" label="关键词">
            <Select mode="tags" tokenSeparators={[',']} placeholder="输入关键词" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="lookback_hours" label="回看小时">
                <InputNumber min={1} max={720} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="item_limit" label="抓取上限">
                <InputNumber min={1} max={500} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="dedup_window_hours" label="去重窗口">
                <InputNumber min={1} max={720} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Drawer>
    </div>
  );
}
