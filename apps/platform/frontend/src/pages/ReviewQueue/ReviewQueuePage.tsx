import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { approveReview, archiveReview, getReview, getReviews, rejectReview } from '../../services/api';
import type { ReviewItem } from '../../types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

type LocationState = {
  reviewId?: number;
};

export default function ReviewQueuePage() {
  const location = useLocation();
  const state = (location.state || {}) as LocationState;
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(state.reviewId || null);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [editedTitle, setEditedTitle] = useState('');
  const [editedContent, setEditedContent] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getReviews({ page: 1, page_size: 100, status: 'pending' });
      setItems(data.items || []);
      const nextId = selectedId || state.reviewId || data.items?.[0]?.id || null;
      setSelectedId(nextId);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载审核队列失败');
    } finally {
      setLoading(false);
    }
  }, [selectedId, state.reviewId]);

  const loadSelected = useCallback(async (reviewId: number | null) => {
    if (!reviewId) {
      setSelected(null);
      return;
    }
    try {
      const detail = await getReview(reviewId);
      setSelected(detail);
      setEditedTitle(detail.candidate_title || detail.original_title || '');
      setEditedContent(detail.candidate_content || detail.summary || detail.original_content || '');
      setReviewNote(detail.review_note || '');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载审核详情失败');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadSelected(selectedId);
  }, [loadSelected, selectedId]);

  const handleApprove = async () => {
    if (!selected) return;
    setActionLoading(true);
    try {
      await approveReview(selected.id, {
        reviewer: 'admin',
        edited_title: editedTitle || undefined,
        edited_content: editedContent || undefined,
      });
      message.success('审核已通过');
      setSelected(null);
      setSelectedId(null);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '通过失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selected) return;
    setActionLoading(true);
    try {
      await rejectReview(selected.id, reviewNote);
      message.success('审核已驳回');
      setSelected(null);
      setSelectedId(null);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '驳回失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleArchive = async () => {
    if (!selected) return;
    setActionLoading(true);
    try {
      await archiveReview(selected.id);
      message.success('审核已归档');
      setSelected(null);
      setSelectedId(null);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '归档失败');
    } finally {
      setActionLoading(false);
    }
  };

  const columns = useMemo<ColumnsType<ReviewItem>>(
    () => [
      {
        title: '标题',
        key: 'original_title',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.original_title}</Text>
            <Text type="secondary">{record.source_url || '-'}</Text>
          </Space>
        ),
      },
      {
        title: '分数',
        dataIndex: 'score',
        key: 'score',
        width: 100,
        render: (value: number) => (typeof value === 'number' ? value.toFixed(2) : '-'),
      },
      {
        title: '标签',
        dataIndex: 'tags',
        key: 'tags',
        render: (value: string[]) => (
          <Space wrap>
            {(value || []).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Space>
        ),
      },
      {
        title: '入队时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (value?: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
    ],
    []
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            审核队列
          </Title>
          <Text type="secondary">待审核内容采用三栏视图，支持编辑改写稿后通过、驳回和归档。</Text>
        </div>
        <Button onClick={load}>刷新</Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={false}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedId ? [selectedId] : [],
            onChange: (keys) => setSelectedId((keys[0] as number) || null),
          }}
        />
      </Card>

      {!selected ? (
        <Empty description="请选择一条待审核记录" />
      ) : (
        <Row gutter={16} align="stretch">
          <Col span={8}>
            <Card title="原文" style={{ height: '100%' }}>
              <Paragraph strong>{selected.original_title}</Paragraph>
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{selected.original_content || '-'}</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card
              title="摘要与改写稿"
              extra={
                <Space>
                  <Button danger loading={actionLoading} onClick={handleReject}>
                    驳回
                  </Button>
                  <Button loading={actionLoading} onClick={handleArchive}>
                    归档
                  </Button>
                  <Button type="primary" loading={actionLoading} onClick={handleApprove}>
                    通过
                  </Button>
                </Space>
              }
              style={{ height: '100%' }}
            >
              <Text type="secondary">摘要</Text>
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{selected.summary || '-'}</Paragraph>
              <Text type="secondary">改写标题</Text>
              <Input value={editedTitle} onChange={(e) => setEditedTitle(e.target.value)} style={{ margin: '8px 0 16px' }} />
              <Text type="secondary">改写内容</Text>
              <TextArea rows={16} value={editedContent} onChange={(e) => setEditedContent(e.target.value)} />
            </Card>
          </Col>
          <Col span={8}>
            <Card title="元数据" style={{ height: '100%' }}>
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <div>
                  <Text type="secondary">状态</Text>
                  <div>
                    <Tag color="gold">{selected.status}</Tag>
                  </div>
                </div>
                <div>
                  <Text type="secondary">分数</Text>
                  <div>{typeof selected.score === 'number' ? selected.score.toFixed(2) : '-'}</div>
                </div>
                <div>
                  <Text type="secondary">标签</Text>
                  <div>
                    <Space wrap>
                      {(selected.tags || []).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </div>
                </div>
                <div>
                  <Text type="secondary">来源链接</Text>
                  <div style={{ wordBreak: 'break-all' }}>{selected.source_url || '-'}</div>
                </div>
                <div>
                  <Text type="secondary">审核备注</Text>
                  <TextArea rows={6} value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="驳回时填写原因" />
                </div>
              </Space>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
}
