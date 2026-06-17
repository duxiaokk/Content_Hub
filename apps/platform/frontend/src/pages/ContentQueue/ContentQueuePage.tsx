import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Collapse,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { getReview, listConsoleContentItems } from '../../services/api';
import type { ContentItem } from '../../types';

const { Title, Text, Paragraph } = Typography;

const reviewStatusOptions = [
  { label: 'pending', value: 'pending' },
  { label: 'approved', value: 'approved' },
  { label: 'rejected', value: 'rejected' },
  { label: 'archived', value: 'archived' },
  { label: 'pending_review', value: 'pending_review' },
];

export default function ContentQueuePage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string | undefined>();
  const [reviewStatus, setReviewStatus] = useState<string | undefined>();
  const [sourceType, setSourceType] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listConsoleContentItems(1, 100, {
        review_status: reviewStatus,
      });
      let result = data?.items || [];
      if (pipelineStatus) {
        result = result.filter((item) => item.pipeline_status === pipelineStatus);
      }
      if (sourceType) {
        result = result.filter((item) => item.source_type === sourceType);
      }
      setItems(result);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载内容列表失败');
    } finally {
      setLoading(false);
    }
  }, [pipelineStatus, reviewStatus, sourceType]);

  useEffect(() => {
    load();
  }, [load]);

  const openReview = async (item: ContentItem) => {
    try {
      const review = await getReview(item.id);
      navigate('/review-queue', { state: { reviewId: review.id } });
    } catch {
      message.warning('未找到对应审核记录');
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
        title: '流水状态',
        dataIndex: 'pipeline_status',
        key: 'pipeline_status',
        width: 140,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: '审核状态',
        dataIndex: 'review_status',
        key: 'review_status',
        width: 140,
        render: (value: string) => <Tag color={value === 'approved' ? 'green' : 'gold'}>{value}</Tag>,
      },
      {
        title: '分数',
        dataIndex: 'score',
        key: 'score',
        width: 100,
        render: (value?: number | null) => (typeof value === 'number' ? value.toFixed(2) : '-'),
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: '操作',
        key: 'actions',
        width: 140,
        render: (_, record) => (
          <Button size="small" onClick={() => openReview(record)}>
            去审核
          </Button>
        ),
      },
    ],
    []
  );

  const sourceTypeOptions = Array.from(new Set(items.map((item) => item.source_type))).map((value) => ({
    label: value,
    value,
  }));
  const pipelineStatusOptions = Array.from(new Set(items.map((item) => item.pipeline_status))).map((value) => ({
    label: value,
    value,
  }));

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            内容列表
          </Title>
          <Text type="secondary">查看抓取入库内容，按状态筛选并展开查看摘要与改写结果。</Text>
        </div>
        <Button onClick={load}>刷新</Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            allowClear
            style={{ width: 180 }}
            placeholder="按流水状态筛选"
            value={pipelineStatus}
            onChange={setPipelineStatus}
            options={pipelineStatusOptions}
          />
          <Select
            allowClear
            style={{ width: 180 }}
            placeholder="按审核状态筛选"
            value={reviewStatus}
            onChange={setReviewStatus}
            options={reviewStatusOptions}
          />
          <Select
            allowClear
            style={{ width: 180 }}
            placeholder="按来源类型筛选"
            value={sourceType}
            onChange={setSourceType}
            options={sourceTypeOptions}
          />
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          expandable={{
            expandedRowRender: (record) => (
              <Collapse
                items={[
                  {
                    key: 'summary',
                    label: '摘要',
                    children: <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{record.summary || '-'}</Paragraph>,
                  },
                  {
                    key: 'rewrite',
                    label: '改写结果',
                    children: (
                      <div>
                        <Paragraph strong>{record.rewritten_title || record.title}</Paragraph>
                        <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                          {record.rewritten_content || record.processed_content || '-'}
                        </Paragraph>
                      </div>
                    ),
                  },
                ]}
              />
            ),
          }}
          pagination={false}
        />
      </Card>
    </div>
  );
}
