import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Drawer, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import {
  approveConsoleContentItem,
  listConsoleContentItems,
  publishConsoleContentItem,
  rejectConsoleContentItem,
} from '../../services/api';
import type { ContentItem } from '../../types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

export default function ContentQueuePage() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<string | undefined>('pending_review');
  const [selected, setSelected] = useState<ContentItem | null>(null);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listConsoleContentItems(1, 100, { review_status: reviewStatus });
      setItems(data?.items || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载内容池失败');
    } finally {
      setLoading(false);
    }
  }, [reviewStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: 'approve' | 'reject' | 'publish') => {
    if (!selected) return;
    try {
      if (action === 'approve') {
        await approveConsoleContentItem(selected.id, reason || undefined);
      } else if (action === 'reject') {
        await rejectConsoleContentItem(selected.id, reason || undefined);
      } else {
        await publishConsoleContentItem(selected.id);
      }
      message.success('操作已完成');
      setSelected(null);
      setReason('');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const columns = useMemo<ColumnsType<ContentItem>>(
    () => [
      {
        title: '标题',
        key: 'title',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.title}</Text>
            <Text type="secondary">{record.source_type}</Text>
          </Space>
        ),
      },
      {
        title: '流水线',
        dataIndex: 'pipeline_status',
        key: 'pipeline_status',
        width: 120,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: '审核',
        dataIndex: 'review_status',
        key: 'review_status',
        width: 140,
        render: (value: string) => (
          <Tag color={value === 'approved' ? 'green' : value === 'rejected' ? 'red' : 'gold'}>
            {value}
          </Tag>
        ),
      },
      {
        title: '发布',
        dataIndex: 'publish_status',
        key: 'publish_status',
        width: 120,
        render: (value: string) => <Tag color={value === 'published' ? 'green' : 'default'}>{value}</Tag>,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (value?: string | null) =>
          value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-',
      },
      {
        title: '操作',
        key: 'actions',
        width: 100,
        render: (_, record) => (
          <Button size="small" onClick={() => setSelected(record)}>
            审核
          </Button>
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
            内容审核队列
          </Title>
          <Text type="secondary">从内容池进入审核，通过后可直接转为 Post。</Text>
        </div>
        <Space>
          <Select
            style={{ width: 220 }}
            allowClear
            value={reviewStatus}
            onChange={(value) => setReviewStatus(value)}
            options={['pending_review', 'approved', 'rejected'].map((item) => ({
              label: item,
              value: item,
            }))}
          />
          <Button onClick={load}>刷新</Button>
        </Space>
      </div>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} />
      </Card>

      <Drawer
        title={selected?.title || '审核详情'}
        width={720}
        open={Boolean(selected)}
        onClose={() => {
          setSelected(null);
          setReason('');
        }}
        extra={
          <Space>
            <Button onClick={() => act('reject')} danger>
              驳回
            </Button>
            <Button onClick={() => act('approve')}>通过</Button>
            <Button type="primary" onClick={() => act('publish')}>
              转为 Post
            </Button>
          </Space>
        }
      >
        {selected && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card size="small" title="原文">
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{selected.raw_content || '-'}</Paragraph>
            </Card>
            <Card size="small" title="处理结果">
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{selected.processed_content || '-'}</Paragraph>
            </Card>
            <Card size="small" title="审核备注">
              <TextArea
                rows={4}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="填写通过备注或驳回原因"
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
