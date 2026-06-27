import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import {
  getFetchMonitorOverview,
  getFetchRunDetail,
  listFetchRuns,
  listSourceConfigs,
  processFetchRun,
} from '../../services/api';
import type { FetchMonitorOverview, FetchRun, FetchRunMonitorDetail, SourceConfig } from '../../types';

const { Title, Text } = Typography;

const statusColors: Record<string, string> = {
  pending: 'gold',
  running: 'processing',
  success: 'success',
  failure: 'error',
  retrying: 'orange',
};

export default function PolishedFetchRunsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<FetchRun[]>([]);
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [sourceId, setSourceId] = useState<number | undefined>(undefined);
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [overview, setOverview] = useState<FetchMonitorOverview | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<FetchRunMonitorDetail | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sourceList, runList, monitorOverview] = await Promise.all([
        listSourceConfigs(),
        listFetchRuns(1, 100, {
          source_config_id: sourceId,
          status,
        }),
        getFetchMonitorOverview(),
      ]);
      setSources(sourceList || []);
      setItems(runList?.items || []);
      setOverview(monitorOverview);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load fetch runs');
    } finally {
      setLoading(false);
    }
  }, [sourceId, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleProcessRun = async (item: FetchRun) => {
    setProcessingId(item.id);
    try {
      const result = await processFetchRun(item.id, {
        limit: Math.max(item.inserted_count || item.fetched_count || 20, 1),
        source_type: item.source_type,
      });
      message.success(
        `处理任务已提交。fetch_run_id=${result.fetch_run_id}，task_id=${result.task_id || '-'}，review_status=${result.review_status}`,
        6
      );
      navigate('/review-queue');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '处理抓取结果失败');
    } finally {
      setProcessingId(null);
    }
  };

  const handleOpenDetail = async (fetchRunId: number) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const data = await getFetchRunDetail(fetchRunId);
      setDetail(data);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载运行详情失败');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const columns = useMemo<ColumnsType<FetchRun>>(
    () => [
      {
        title: '运行 ID',
        dataIndex: 'id',
        key: 'id',
        width: 90,
      },
      {
        title: '数据源',
        key: 'source_name',
        render: (_, record) => (
          <Space direction="vertical" size={2}>
            <Text strong>{record.source_name}</Text>
            <Text type="secondary">{record.source_type}</Text>
          </Space>
        ),
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (value: string) => <Tag color={statusColors[value] || 'default'}>{value}</Tag>,
      },
      {
        title: '任务 ID',
        dataIndex: 'task_id',
        key: 'task_id',
        width: 220,
        ellipsis: true,
        render: (value?: string | null) => <span className="mono-truncate">{value || '-'}</span>,
      },
      {
        title: '统计',
        key: 'counts',
        width: 260,
        render: (_, record) => `抓取 ${record.fetched_count} / 新增 ${record.inserted_count} / 去重 ${record.deduped_count}`,
      },
      {
        title: '开始时间',
        dataIndex: 'started_at',
        key: 'started_at',
        width: 180,
        render: (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: '耗时',
        dataIndex: 'duration_ms',
        key: 'duration_ms',
        width: 100,
        render: (value?: number | null) => (value ? `${value} ms` : '-'),
      },
      {
        title: '错误',
        dataIndex: 'error_message',
        key: 'error_message',
        ellipsis: true,
        render: (value?: string | null) => value || '-',
      },
      {
        title: '操作',
        key: 'actions',
        width: 260,
        render: (_, record) => (
          <Space wrap>
            <Button size="small" onClick={() => void handleOpenDetail(record.id)}>
              查看详情
            </Button>
            {record.status === 'success' ? (
              <Button
                size="small"
                type="primary"
                loading={processingId === record.id}
                onClick={() => void handleProcessRun(record)}
              >
                处理本次抓取
              </Button>
            ) : null}
          </Space>
        ),
      },
    ],
    [processingId]
  );

  return (
    <div>
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Fetch Monitoring</span>
          <Title level={3} className="page-header__title">
            采集历史与监控
          </Title>
          <Text className="page-header__description">
            查看采集任务状态、告警、校验问题和执行日志，并对成功抓取结果继续发起处理流程。
          </Text>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => void load()}>刷新</Button>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="总运行数" value={overview?.total_runs || 0} />
            </div>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="成功率" value={overview?.success_rate || 0} precision={2} suffix="%" />
            </div>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="失败运行" value={overview?.failed_runs || 0} />
            </div>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="运行中 / 待执行" value={overview?.running_runs || 0} />
            </div>
          </Card>
        </Col>
      </Row>

      <Card className="surface-card toolbar-card" style={{ marginBottom: 16 }}>
        <Space wrap>
          <div>
            <div className="section-caption" style={{ marginBottom: 8 }}>筛选</div>
            <Space wrap>
              <Select
                allowClear
                placeholder="按数据源筛选"
                style={{ width: 220 }}
                value={sourceId}
                onChange={(value) => setSourceId(value)}
                options={sources.map((item) => ({ label: item.name, value: item.id }))}
              />
              <Select
                allowClear
                placeholder="按状态筛选"
                style={{ width: 180 }}
                value={status}
                onChange={(value) => setStatus(value)}
                options={['pending', 'running', 'success', 'failure', 'retrying'].map((item) => ({
                  label: item,
                  value: item,
                }))}
              />
            </Space>
          </div>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card className="surface-card detail-card" title="最近告警">
            {!overview?.recent_alerts?.length ? (
              <Empty description="暂无告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                className="list-soft"
                size="small"
                dataSource={overview.recent_alerts.slice(0, 6)}
                renderItem={(item) => (
                  <List.Item>
                    <Space direction="vertical" size={4}>
                      <Text strong>{item.source_name || item.source}</Text>
                      <Tag color={item.severity === 'critical' ? 'error' : item.severity === 'warning' ? 'orange' : 'blue'}>
                        {item.alert_type}
                      </Tag>
                      <Text>{item.message}</Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card className="surface-card detail-card" title="数据源成功率">
            {!overview?.source_summaries?.length ? (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                className="list-soft"
                size="small"
                dataSource={overview.source_summaries.slice(0, 6)}
                renderItem={(item) => (
                  <List.Item>
                    <Text>{`${item.source_name} (${item.source_type}) | 成功率 ${item.success_rate}% | 成功 ${item.success_runs} / 总计 ${item.total_runs}`}</Text>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Card className="surface-card table-card">
        <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} />
      </Card>

      <Drawer
        title={detail?.fetch_run?.source_name ? `${detail.fetch_run.source_name} 运行详情` : '运行详情'}
        width={760}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        destroyOnClose
      >
        {detailLoading || !detail ? (
          <Text type="secondary">加载中...</Text>
        ) : (
          <Space direction="vertical" size={16} className="detail-stack">
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="状态">{detail.fetch_run.status}</Descriptions.Item>
              <Descriptions.Item label="任务 ID">{detail.fetch_run.task_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="抓取">{detail.fetch_run.fetched_count}</Descriptions.Item>
              <Descriptions.Item label="新增">{detail.fetch_run.inserted_count}</Descriptions.Item>
              <Descriptions.Item label="去重">{detail.fetch_run.deduped_count}</Descriptions.Item>
              <Descriptions.Item label="错误">{detail.fetch_run.error_message || '-'}</Descriptions.Item>
            </Descriptions>

            <Card size="small" className="surface-card detail-card" title="告警">
              {!detail.alerts.length ? (
                <Empty description="暂无告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  className="list-soft"
                  size="small"
                  dataSource={detail.alerts}
                  renderItem={(item) => (
                    <List.Item>
                      <Text>{`${item.alert_type} | ${item.message}`}</Text>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card size="small" className="surface-card detail-card" title="按源统计">
              {!detail.source_stats.length ? (
                <Empty description="暂无明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  className="list-soft"
                  size="small"
                  dataSource={detail.source_stats}
                  renderItem={(item) => (
                    <List.Item>
                      <Text>{`${item.source} | 抓取 ${item.fetched_count} | 新增 ${item.inserted_count} | 无效 ${item.invalid_count} | 重试 ${item.retried_count}`}</Text>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card size="small" className="surface-card detail-card" title="校验问题">
              {!detail.validation_issues.length ? (
                <Empty description="暂无脏数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  className="list-soft"
                  size="small"
                  dataSource={detail.validation_issues}
                  renderItem={(item) => (
                    <List.Item>
                      <Text>{`${String(item.reason || '-')} | ${String(item.source_id || '-')} | ${String(item.detail || '-')}`}</Text>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card size="small" className="surface-card detail-card" title="任务日志">
              {!detail.logs.length ? (
                <Empty description="暂无日志" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  className="list-soft"
                  size="small"
                  dataSource={detail.logs}
                  renderItem={(item) => (
                    <List.Item>
                      <Text>{`${dayjs(item.created_at).format('MM-DD HH:mm:ss')} [${item.level}] ${item.message}`}</Text>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
