import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Select, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listFetchRuns, listSourceConfigs } from '../../services/api';
import type { FetchRun, SourceConfig } from '../../types';

const { Title, Text } = Typography;

const statusColors: Record<string, string> = {
  pending: 'gold',
  running: 'processing',
  success: 'success',
  failure: 'error',
  retrying: 'orange',
};

export default function FetchRunsPage() {
  const [items, setItems] = useState<FetchRun[]>([]);
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceId, setSourceId] = useState<number | undefined>(undefined);
  const [status, setStatus] = useState<string | undefined>(undefined);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sourceList, runList] = await Promise.all([
        listSourceConfigs(),
        listFetchRuns(1, 100, {
          source_config_id: sourceId,
          status,
        }),
      ]);
      setSources(sourceList || []);
      setItems(runList?.items || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载采集历史失败');
    } finally {
      setLoading(false);
    }
  }, [sourceId, status]);

  useEffect(() => {
    load();
  }, [load]);

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
          <Space direction="vertical" size={0}>
            <Text strong>{record.source_name}</Text>
            <Text type="secondary">{record.source_type}</Text>
          </Space>
        ),
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 110,
        render: (value: string) => <Tag color={statusColors[value] || 'default'}>{value}</Tag>,
      },
      {
        title: '任务 ID',
        dataIndex: 'task_id',
        key: 'task_id',
        width: 220,
        ellipsis: true,
      },
      {
        title: '统计',
        key: 'counts',
        width: 240,
        render: (_, record) =>
          `抓取 ${record.fetched_count} / 新增 ${record.inserted_count} / 去重 ${record.deduped_count}`,
      },
      {
        title: '开始时间',
        dataIndex: 'started_at',
        key: 'started_at',
        width: 180,
        render: (value?: string | null) =>
          value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-',
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
    ],
    []
  );

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            采集历史
          </Title>
          <Text type="secondary">查看每次采集任务的提交、状态和结果摘要。</Text>
        </Col>
        <Col>
          <Button onClick={load}>刷新</Button>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
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
      </Card>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} />
      </Card>
    </div>
  );
}
