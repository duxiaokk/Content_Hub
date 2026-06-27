import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  Empty,
  List,
  Row,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  RightOutlined,
  RobotOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { getReviews, listConsoleContentItems, listFetchRuns } from '../../services/api';
import type { ContentItem, FetchRun } from '../../types';

const { Title, Text } = Typography;

interface DashboardStats {
  todayFetchCount: number;
  pendingReviewCount: number;
  publishedCount: number;
  agentStatus: '正常' | '异常';
}

const QUICK_ACTIONS = [
  { key: 'sources', label: '管理信源', icon: <DatabaseOutlined />, path: '/sources' },
  { key: 'fetch-runs', label: '查看采集监控', icon: <FileSearchOutlined />, path: '/fetch-runs' },
  { key: 'review-queue', label: '处理审核队列', icon: <EditOutlined />, path: '/review-queue' },
  { key: 'digests', label: '查看日报', icon: <FileTextOutlined />, path: '/digests' },
];

export default function PolishedDashboardPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats>({
    todayFetchCount: 0,
    pendingReviewCount: 0,
    publishedCount: 0,
    agentStatus: '正常',
  });
  const [recentFetchRuns, setRecentFetchRuns] = useState<FetchRun[]>([]);
  const [recentContentItems, setRecentContentItems] = useState<ContentItem[]>([]);

  useEffect(() => {
    void loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [fetchRunsRes, contentItemsRes, reviewsRes] = await Promise.all([
        listFetchRuns(1, 5).catch(() => null),
        listConsoleContentItems(1, 5, { publish_status: 'published' }).catch(() => null),
        getReviews({ status: 'pending', page_size: 1 }).catch(() => null),
      ]);

      const fetchRuns = fetchRunsRes?.items || [];
      const publishedItems = contentItemsRes?.items || [];
      const pendingReviewTotal = reviewsRes?.total || 0;
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
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const statCards = useMemo(
    () => [
      {
        title: '今日采集',
        value: stats.todayFetchCount,
        icon: <SyncOutlined style={{ color: '#3b82f6' }} />,
        path: '/fetch-runs',
      },
      {
        title: '待审核',
        value: stats.pendingReviewCount,
        icon: <EditOutlined style={{ color: '#d97706' }} />,
        path: '/review-queue',
      },
      {
        title: '已发布',
        value: stats.publishedCount,
        icon: <CheckCircleOutlined style={{ color: '#16a34a' }} />,
        path: '/content-queue',
      },
      {
        title: 'Agent 状态',
        value: stats.agentStatus,
        icon: <RobotOutlined style={{ color: stats.agentStatus === '正常' ? '#16a34a' : '#dc2626' }} />,
        path: '/agent',
      },
    ],
    [stats]
  );

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      success: { color: 'success', text: '成功' },
      failure: { color: 'error', text: '失败' },
      failed: { color: 'error', text: '失败' },
      running: { color: 'processing', text: '运行中' },
      pending: { color: 'warning', text: '等待中' },
      retrying: { color: 'orange', text: '重试中' },
      fetched: { color: 'blue', text: '已抓取' },
      processed: { color: 'purple', text: '已处理' },
      published: { color: 'green', text: '已发布' },
    };
    const cfg = map[status] || { color: 'default', text: status };
    return <Tag color={cfg.color}>{cfg.text}</Tag>;
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Overview</span>
          <Title level={3} className="page-header__title">
            工作台
          </Title>
          <Text className="page-header__description">
            汇总内容采集、审核与发布链路的关键指标，方便快速进入当日最重要的处理动作。
          </Text>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => void loadDashboardData()}>刷新数据</Button>
          <Button type="primary" icon={<FileSearchOutlined />} onClick={() => navigate('/sources')}>
            新增信源
          </Button>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        {statCards.map((card) => (
          <Col xs={12} sm={12} md={6} key={card.title}>
            <Card className="surface-card summary-card metric-card" hoverable onClick={() => navigate(card.path)}>
              <div className="stat-card">
                <Space style={{ marginBottom: 12 }}>{card.icon}<Text type="secondary">{card.title}</Text></Space>
                <Statistic value={card.value} />
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="surface-card toolbar-card" style={{ marginBottom: 20 }}>
        <div className="section-caption" style={{ marginBottom: 12 }}>
          快捷操作
        </div>
        <Space wrap>
          {QUICK_ACTIONS.map((action) => (
            <Button key={action.key} icon={action.icon} onClick={() => navigate(action.path)}>
              {action.label}
            </Button>
          ))}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card
            className="surface-card detail-card"
            title="最近采集运行"
            extra={
              <Button type="link" onClick={() => navigate('/fetch-runs')}>
                查看全部 <RightOutlined />
              </Button>
            }
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : recentFetchRuns.length === 0 ? (
              <Empty description="暂无采集记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                className="list-soft"
                dataSource={recentFetchRuns}
                renderItem={(run) => (
                  <List.Item style={{ cursor: 'pointer' }} onClick={() => navigate('/fetch-runs')}>
                    <List.Item.Meta
                      title={
                        <Space wrap>
                          <span>{run.source_name || run.source_type}</span>
                          {getStatusTag(run.status)}
                        </Space>
                      }
                      description={
                        <Space size={16} wrap>
                          <span>
                            <ClockCircleOutlined style={{ marginRight: 4 }} />
                            {run.created_at ? dayjs(run.created_at).format('MM-DD HH:mm') : '-'}
                          </span>
                          <span>抓取 {run.fetched_count || 0}</span>
                          <span>入库 {run.inserted_count || 0}</span>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card
            className="surface-card detail-card"
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
                className="list-soft"
                dataSource={recentContentItems}
                renderItem={(item) => (
                  <List.Item style={{ cursor: 'pointer' }} onClick={() => navigate('/content-queue')}>
                    <List.Item.Meta
                      title={
                        <span className="dashboard-item-title">
                          {item.title}
                        </span>
                      }
                      description={
                        <Space size={16} wrap>
                          <span>
                            <ClockCircleOutlined style={{ marginRight: 4 }} />
                            {item.created_at ? dayjs(item.created_at).format('MM-DD HH:mm') : '-'}
                          </span>
                          <span>{item.source_type}</span>
                          {item.score ? (
                            <Tag color={item.score >= 80 ? 'green' : item.score >= 60 ? 'orange' : 'red'}>
                              {item.score} 分
                            </Tag>
                          ) : null}
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
