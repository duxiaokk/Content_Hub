import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Collapse,
  Image,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { getReviews, listConsoleContentItems, publishConsoleContentItem } from '../../services/api';
import type { ContentItem, ReviewItem } from '../../types';

const { Title, Text, Paragraph } = Typography;

const reviewStatusOptions = [
  { label: 'pending', value: 'pending' },
  { label: 'approved', value: 'approved' },
  { label: 'rejected', value: 'rejected' },
  { label: 'archived', value: 'archived' },
  { label: 'pending_review', value: 'pending_review' },
];

function extractMediaUrls(metadata?: Record<string, unknown> | null): string[] {
  if (!metadata) return [];
  const urls: string[] = [];
  const cover = metadata.cover_url || metadata.cover;
  if (typeof cover === 'string' && cover) urls.push(cover);

  const media = metadata.media;
  if (Array.isArray(media)) {
    for (const item of media) {
      if (typeof item === 'string' && item) {
        urls.push(item);
      } else if (typeof item === 'object' && item && typeof (item as Record<string, unknown>).url === 'string') {
        urls.push((item as Record<string, unknown>).url as string);
      }
    }
  }
  return urls;
}

function buildContentIdentifier(item: ContentItem): string {
  if (item.source_url?.trim()) {
    return item.source_url.trim();
  }
  if (item.source_id?.trim()) {
    return item.source_id.trim();
  }
  return '-';
}

export default function PolishedContentQueuePage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [publishingId, setPublishingId] = useState<number | null>(null);
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
      message.error(error instanceof Error ? error.message : 'Failed to load content queue');
    } finally {
      setLoading(false);
    }
  }, [pipelineStatus, reviewStatus, sourceType]);

  useEffect(() => {
    void load();
  }, [load]);

  const openReview = async (item: ContentItem) => {
    try {
      const reviewList = await getReviews({ page: 1, page_size: 100, content_item_id: item.id });
      const review = (reviewList.items || []).find((entry: ReviewItem) => entry.content_item_id === item.id);
      if (!review) {
        message.warning('未找到对应审核记录');
        return;
      }
      navigate('/review-queue', { state: { reviewId: review.id } });
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load review detail');
    }
  };

  const handlePublish = async (item: ContentItem) => {
    setPublishingId(item.id);
    try {
      const result = await publishConsoleContentItem(item.id, {
        title: item.rewritten_title || item.title,
        content: item.rewritten_content || item.processed_content || item.raw_content || undefined,
        tech_tags: item.tags?.join(','),
      });
      message.success(
        `发布成功。post_id=${result.post_id}，post_path=${result.post_path}，publish_status=${result.publish_status}`,
        6
      );
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to publish to post');
    } finally {
      setPublishingId(null);
    }
  };

  const columns = useMemo<ColumnsType<ContentItem>>(
    () => [
      {
        title: '标题 / 来源',
        key: 'title',
        width: 320,
        render: (_, record) => (
          <div className="queue-title-cell">
            <Text strong className="queue-title-cell__title">
              {record.rewritten_title || record.title}
            </Text>
            <Text type="secondary" className="queue-title-cell__meta">
              {record.source_type}
            </Text>
            <Text type="secondary" className="queue-title-cell__meta">
              {buildContentIdentifier(record)}
            </Text>
          </div>
        ),
      },
      {
        title: '摘要',
        key: 'summary',
        width: 340,
        render: (_, record) => (
          <div className="queue-summary-cell">
            <Paragraph ellipsis={{ rows: 3, expandable: false }} className="queue-summary-cell__text">
              {record.summary || record.processed_content || record.raw_content || '-'}
            </Paragraph>
            {record.tags?.length ? (
              <Space wrap size={[4, 4]} className="queue-tag-list">
                {record.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </Space>
            ) : null}
          </div>
        ),
      },
      {
        title: '流水状态',
        dataIndex: 'pipeline_status',
        key: 'pipeline_status',
        width: 132,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: '审核状态',
        dataIndex: 'review_status',
        key: 'review_status',
        width: 132,
        render: (value: string) => <Tag color={value === 'approved' ? 'green' : 'gold'}>{value}</Tag>,
      },
      {
        title: '发布状态',
        dataIndex: 'publish_status',
        key: 'publish_status',
        width: 132,
        render: (value: string) => <Tag color={value === 'published' ? 'blue' : 'default'}>{value}</Tag>,
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
        width: 220,
        render: (_, record) => (
          <Space wrap size={8} className="queue-actions">
            <Button size="small" onClick={() => void openReview(record)}>
              去审核
            </Button>
            {(record.review_status === 'approved' || record.pipeline_status === 'processed') &&
            record.publish_status !== 'published' ? (
              <Button
                size="small"
                type="primary"
                loading={publishingId === record.id}
                onClick={() => void handlePublish(record)}
              >
                发布到 Post
              </Button>
            ) : null}
          </Space>
        ),
      },
    ],
    [publishingId]
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
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Content Pipeline</span>
          <Title level={3} className="page-header__title">
            内容队列
          </Title>
          <Text className="page-header__description">
            查看抓取入库内容，按流水和审核状态筛选，进入审核工作台，或直接发布已通过内容。
          </Text>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => void load()}>刷新</Button>
        </div>
      </div>

      <Card className="surface-card toolbar-card" style={{ marginBottom: 16 }}>
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

      <Card className="surface-card table-card">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={false}
          scroll={{ x: 1500 }}
          expandable={{
            expandedRowRender: (record) => {
              const mediaUrls = extractMediaUrls(record.metadata);
              return (
                <Collapse
                  items={[
                    {
                      key: 'summary',
                      label: '摘要',
                      children: (
                        <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                          {record.summary || '-'}
                        </Paragraph>
                      ),
                    },
                    {
                      key: 'raw',
                      label: '原始内容',
                      children: (
                        <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                          {record.raw_content || '-'}
                        </Paragraph>
                      ),
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
                    ...(mediaUrls.length > 0
                      ? [
                          {
                            key: 'media',
                            label: '图片 / 媒体',
                            children: (
                              <Space wrap>
                                {mediaUrls.map((url, index) => (
                                  <Image
                                    key={index}
                                    src={url}
                                    alt={`media-${index}`}
                                    style={{ maxHeight: 160, objectFit: 'cover' }}
                                    fallback="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                                  />
                                ))}
                              </Space>
                            ),
                          },
                        ]
                      : []),
                  ]}
                />
              );
            },
          }}
        />
      </Card>
    </div>
  );
}
