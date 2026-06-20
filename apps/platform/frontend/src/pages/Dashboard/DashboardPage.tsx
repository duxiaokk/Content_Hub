import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Statistic,
  Button,
  Typography,
  List,
  Tag,
  Skeleton,
  Space,
  Empty,
  message,
} from 'antd';
import {
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  RobotOutlined,
  RightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { listFetchRuns, listConsoleContentItems, getReviews } from '../../services/api';
import type { FetchRun, ContentItem, ReviewItem } from '../../types';
import dayjs from 'dayjs';

const { Title, Paragraph } = Typography;

interface DashboardStats {
  todayFetchCount: number;
  pendingReviewCount: number;
  publishedCount: number;
  agentStatus: '正常' | '异常';
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats>({
    todayFetchCount: 0,
    pendingReviewCount: 0,
    publishedCount: 0,
    agentStatus: '正常',
  });
  const [loading, setLoading] = useState(true);
  const [recentFetchRuns, setRecentFetchRuns] = useState<FetchRun[]>([]);
  const [recentContentItems, setRecentContentItems] = useState<ContentItem[]>([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      // 并行加载数据
      const [fetchRunsRes, contentItemsRes, reviewsRes] = await Promise.all([
        listFetchRuns(1, 5).catch(() => null),
        listConsoleContentItems(1, 5, { publish_status: 'published' }).catch(() => null),
        getReviews({ status: 'pending', page_size: 1 }).catch(() => null),
      ]);

      const fetchRuns = fetchRunsRes?.items || [];
      const publishedItems = contentItemsRes?.items || [];
      const pendingReviewTotal = reviewsRes?.total || 0;

      // 计算今日抓取数
      const today = dayjs().format('YYYY-MM-DD');
      const todayFetchCount = fetchRuns.filter(
        (run) => run.created_at && dayjs(run.created_at).format('YYYY-MM-DD') === today
      ).length;

      setStats({
        todayFetchCount: todayFetchCount || fetchRuns.length,
        pendingReviewCount: pendingReviewTotal,
        publishedCount: publishedItems.length,
        agentStatus: '正常',
      });

      setRecentFetchRuns(fetchRuns.slice(0, 5));
      setRecentContentItems(publishedItems.slice(0, 5));
    } catch (err) {
      console.error('Dashboard load error:', err);
      message.error('加载工作台数据失败');
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      title: '今日抓取',
      value: stats.todayFetchCount,
      icon: <SyncOutlined style={{ color: '#1677ff' }} />,
      onClick: () => navigate('/fetch-runs'),
    },
    {
      title: '待审核',
      value: stats.pendingReviewCount,
      icon: <EditOutlined style={{ color: '#fa8c16' }} />,
      onClick: () => navigate('/review-queue'),
    },
    {
      title: '已发布',
      value: stats.publishedCount,
      icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
      onClick: () => navigate('/content-queue'),
    },
    {
      title: 'Agent 状态',
      value: stats.agentStatus,
      icon: <RobotOutlined style={{ color: stats.agentStatus === '正常' ? '#52c41a' : '#f5222d' }} />,
      onClick: () => navigate('/agent'),
    },
  ];

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      success: { color: 'success', text: '成功' },
      failed: { color: 'error', text: '失败' },
      running: { color: 'processing', text: '运行中' },
      pending: { color: 'warning', text: '等待中' },
      fetched: { color: 'blue', text: '已抓取' },
      processed: { color: 'purple', text: '已处理' },
      published: { color: 'green', text: '已发布' },
    };
    const cfg = map[status] || { color: 'default', text: status };
    return <Tag color={cfg.color}>{cfg.text}</Tag>;
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>
          Content Hub 工作台
        </Title>
        <Paragraph type="secondary" style={{ marginTop: 4 }}>
          内容自动化工作流总览
        </Paragraph>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((card) => (
          <Col xs={12} sm={12} md={6} key={card.title}>
            <Card
              hoverable
              onClick={card.onClick}
              bodyStyle={{ padding: 20, cursor: 'pointer' }}
            >
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space>
                  {card.icon}
                  <span style={{ color: '#666', fontSize: 14 }}>{card.title}</span>
                </Space>
                <Statistic
                  value={card.value}
                  valueStyle={{
                    fontSize: 28,
                    fontWeight: 600,
                    color: '#1f1f1f',
                  }}
                />
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 快捷操作 */}
      <Card title="快捷操作" style={{ marginBottom: 24 }}>
        <Space wrap>
          <Button type="primary" icon={<FileSearchOutlined />} onClick={() => navigate('/sources')}>
            开始抓取
          </Button>
          <Button icon={<EditOutlined />} onClick={() => navigate('/review-queue')}>
            去审核队列
          </Button>
          <Button icon={<FileTextOutlined />} onClick={() => navigate('/digests')}>
            查看日报
          </Button>
          <Button icon={<DatabaseOutlined />} onClick={() => navigate('/sources')}>
            管理信源
          </Button>
        </Space>
      </Card>

      {/* 双栏布局：最近抓取 + 最近发布 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card
            title="最近抓取运行"
            extra={
              <Button type="link" onClick={() => navigate('/fetch-runs')}>
                查看全部 <RightOutlined />
              </Button>
            }
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : recentFetchRuns.length === 0 ? (
              <Empty description="暂无抓取记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                dataSource={recentFetchRuns}
                renderItem={(run) => (
                  <List.Item
                    style={{ padding: '12px 0', cursor: 'pointer' }}
                    onClick={() => navigate('/fetch-runs')}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <span>{run.source_name || run.source_type}</span>
                          {getStatusTag(run.status)}
                        </Space>
                      }
                      description={
                        <Space size={16} style={{ marginTop: 4 }}>
                          <span style={{ color: '#999', fontSize: 12 }}>
                            <ClockCircleOutlined style={{ marginRight: 4 }} />
                            {run.created_at ? dayjs(run.created_at).format('MM-DD HH:mm') : '-'}
                          </span>
                          <span style={{ color: '#999', fontSize: 12 }}>
                            抓取: {run.fetched_count || 0} | 入库: {run.inserted_count || 0}
                          </span>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card
            title="最近发布内容"
            extra={
              <Button type="link" onClick={() => navigate('/content-queue')}>
                查看全部 <RightOutlined />
              </Button>
            }
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : recentContentItems.length === 0 ? (
              <Empty description="暂无发布内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                dataSource={recentContentItems}
                renderItem={(item) => (
                  <List.Item
                    style={{ padding: '12px 0', cursor: 'pointer' }}
                    onClick={() => navigate('/content-queue')}
                  >
                    <List.Item.Meta
                      title={
                        <span
                          style={{
                            fontWeight: 500,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: '100%',
                            display: 'block',
                          }}
                        >
                          {item.title}
                        </span>
                      }
                      description={
                        <Space size={16} style={{ marginTop: 4 }}>
                          <span style={{ color: '#999', fontSize: 12 }}>
                            <ClockCircleOutlined style={{ marginRight: 4 }} />
                            {item.created_at ? dayjs(item.created_at).format('MM-DD HH:mm') : '-'}
                          </span>
                          <span style={{ color: '#999', fontSize: 12 }}>
                            {item.source_type}
                          </span>
                          {item.score && (
                            <Tag color={item.score >= 80 ? 'green' : item.score >= 60 ? 'orange' : 'red'}>
                              {item.score}分
                            </Tag>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
