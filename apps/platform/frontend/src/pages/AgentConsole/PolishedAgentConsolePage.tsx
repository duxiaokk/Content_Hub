import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  PieChartOutlined,
  ReloadOutlined,
  RobotOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { ColumnsType } from 'antd/es/table';
import { listAgents, listOrchestrationRuns, listTasks } from '../../services/api';
import type { Agent, OrchestrationRun, SchedulerTask } from '../../types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const PIE_COLORS = ['#52c41a', '#1677ff', '#fa8c16', '#ff4d4f', '#d9d9d9'];

const statusLabelMap: Record<string, string> = {
  pending: '待处理',
  running: '运行中',
  success: '已完成',
  failure: '失败',
  retrying: '重试中',
};

const statusTagMap: Record<string, React.ReactNode> = {
  online: <Badge status="success" text="在线" />,
  offline: <Badge status="error" text="离线" />,
  busy: <Badge status="processing" text="忙碌" />,
};

export default function PolishedAgentConsolePage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<SchedulerTask[]>([]);
  const [runs, setRuns] = useState<OrchestrationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAllData = useCallback(async () => {
    try {
      const [agentRes, taskRes, runRes] = await Promise.all([
        listAgents(),
        listTasks(1, 100),
        listOrchestrationRuns(1, 20),
      ]);
      setAgents(Array.isArray(agentRes) ? agentRes : []);
      setTasks(taskRes?.items || []);
      setRuns(runRes?.items || []);
    } catch {
      message.error('Failed to load agent console data');
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    void fetchAllData().finally(() => setLoading(false));
  }, [fetchAllData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchAllData();
      message.success('刷新成功');
    } finally {
      setRefreshing(false);
    }
  };

  const onlineCount = agents.filter((agent) => agent.status === 'online' || agent.status === 'busy').length;
  const avgLoad =
    agents.length > 0
      ? Math.round(agents.reduce((sum, agent) => sum + (agent.load_score || 0), 0) / agents.length)
      : 0;

  const taskStatusCounts: Record<string, number> = {};
  tasks.forEach((task) => {
    taskStatusCounts[task.status] = (taskStatusCounts[task.status] || 0) + 1;
  });

  const pieData = Object.entries(taskStatusCounts).map(([status, count]) => ({
    name: statusLabelMap[status] || status,
    value: count,
  }));

  const agentColumns: ColumnsType<Agent> = useMemo(
    () => [
      {
        title: 'Agent 名称',
        dataIndex: 'agent_name',
        key: 'agent_name',
        width: 220,
        render: (name: string, record: Agent) => (
          <Space>
            <RobotOutlined style={{ color: '#3b82f6' }} />
            <Text strong>{name || record.agent_key}</Text>
          </Space>
        ),
      },
      {
        title: '类型',
        dataIndex: 'agent_type',
        key: 'agent_type',
        width: 130,
        render: (value: string) => <Tag color="blue">{value}</Tag>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (value: string) => statusTagMap[value] || <Badge status="default" text={value} />,
      },
      {
        title: '地址',
        key: 'address',
        width: 180,
        render: (_, record: Agent) => `${record.host}:${record.port}`,
      },
      {
        title: '负载',
        dataIndex: 'load_score',
        key: 'load_score',
        width: 170,
        render: (load: number) => (
          <Progress
            percent={Math.round(load)}
            size="small"
            status={load > 80 ? 'exception' : load > 60 ? 'active' : 'normal'}
          />
        ),
      },
      {
        title: '最近心跳',
        dataIndex: 'last_heartbeat',
        key: 'last_heartbeat',
        width: 180,
        render: (value: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
    ],
    []
  );

  const runColumns: ColumnsType<OrchestrationRun> = useMemo(
    () => [
      {
        title: 'Run ID',
        dataIndex: 'id',
        key: 'id',
        width: 220,
        ellipsis: true,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (value: string) => {
          const colorMap: Record<string, string> = {
            running: 'processing',
            success: 'success',
            failure: 'error',
            pending: 'gold',
          };
          return <Tag color={colorMap[value] || 'default'}>{statusLabelMap[value] || value}</Tag>;
        },
      },
      {
        title: '任务数',
        key: 'taskCount',
        width: 100,
        render: (_, record: OrchestrationRun) => record.tasks?.length ?? 0,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (value: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
    ],
    []
  );

  if (loading) {
    return (
      <div className="agent-loading">
        <Spin size="large" tip="加载 Agent 数据中..." />
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Runtime Console</span>
          <Title level={3} className="page-header__title">
            Agent 控制台
          </Title>
          <Text className="page-header__description">
            统一查看 Agent 在线状态、任务分布、平均负载以及最近编排运行情况。
          </Text>
        </div>
        <div className="page-header__actions">
          <Tag color="blue">{agents.length} 个 Agent</Tag>
          <Tag color="green">{onlineCount} 在线</Tag>
          <Button icon={<ReloadOutlined spin={refreshing} />} onClick={() => void handleRefresh()}>
            刷新
          </Button>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="在线 Agent" value={onlineCount} suffix={`/ ${agents.length}`} prefix={<CheckCircleOutlined />} />
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="总任务数" value={tasks.length} prefix={<ThunderboltOutlined />} />
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="平均负载" value={avgLoad} suffix="%" prefix={<SyncOutlined spin={avgLoad > 60} />} />
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="surface-card summary-card metric-card">
            <div className="stat-card">
              <Statistic title="编排运行" value={runs.length} prefix={<ClockCircleOutlined />} />
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={16}>
          <Card className="surface-card table-card" title="Agent 列表">
            {agents.length === 0 ? (
              <Empty description="暂无 Agent 数据" />
            ) : (
              <Table<Agent>
                columns={agentColumns}
                dataSource={agents}
                rowKey="agent_key"
                pagination={false}
                size="middle"
                scroll={{ x: 820 }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card className="surface-card detail-card" title={<><PieChartOutlined /> 任务状态分布</>}>
            {pieData.length === 0 ? (
              <Empty description="暂无任务数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={90}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {pieData.map((_, index) => (
                      <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
      </Row>

      <Card className="surface-card table-card" title="最近的编排运行">
        {runs.length === 0 ? (
          <Empty description="暂无编排运行记录" />
        ) : (
          <Table<OrchestrationRun>
            columns={runColumns}
            dataSource={runs}
            rowKey="id"
            pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
            size="middle"
          />
        )}
      </Card>
    </div>
  );
}
