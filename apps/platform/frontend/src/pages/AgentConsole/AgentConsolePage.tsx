import { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Typography,
  Tag,
  Table,
  Badge,
  Space,
  Row,
  Col,
  Statistic,
  Progress,
  Empty,
  Spin,
  message,
} from 'antd';
import {
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  PieChartOutlined,
} from '@ant-design/icons';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { ColumnsType } from 'antd/es/table';
import { listAgents, listTasks, listOrchestrationRuns } from '../../services/api';
import type { Agent, SchedulerTask, OrchestrationRun } from '../../types';
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

export default function AgentConsolePage() {
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
      setTasks(taskRes.items || []);
      setRuns(runRes.items || []);
    } catch {
      message.error('加载 Agent 数据失败');
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchAllData().finally(() => setLoading(false));
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

  // ---- 统计指标 ----
  const onlineCount = agents.filter(
    (a) => a.status === 'online' || a.status === 'busy'
  ).length;
  const avgLoad =
    agents.length > 0
      ? Math.round(agents.reduce((s, a) => s + (a.load_score || 0), 0) / agents.length)
      : 0;

  const taskStatusCounts: Record<string, number> = {};
  tasks.forEach((t) => {
    taskStatusCounts[t.status] = (taskStatusCounts[t.status] || 0) + 1;
  });
  const pieData = Object.entries(taskStatusCounts).map(([status, count]) => ({
    name: statusLabelMap[status] || status,
    value: count,
  }));

  // ---- Agent 列定义 ----
  const agentColumns: ColumnsType<Agent> = [
    {
      title: 'Agent 名称',
      dataIndex: 'agent_name',
      key: 'agent_name',
      width: 200,
      render: (name: string, record: Agent) => (
        <Space>
          <RobotOutlined style={{ color: '#1677ff' }} />
          <Text strong>{name || record.agent_key}</Text>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'agent_type',
      key: 'agent_type',
      width: 130,
      render: (t: string) => <Tag color="blue">{t}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => statusTagMap[s] || <Badge status="default" text={s} />,
    },
    {
      title: '地址',
      key: 'address',
      width: 180,
      render: (_: unknown, r: Agent) => `${r.host}:${r.port}`,
    },
    {
      title: '负载',
      dataIndex: 'load_score',
      key: 'load_score',
      width: 160,
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
      width: 160,
      render: (t: string) =>
        t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
  ];

  // ---- 编排运行列定义 ----
  const runColumns: ColumnsType<OrchestrationRun> = [
    {
      title: 'Run ID',
      dataIndex: 'id',
      key: 'id',
      width: 200,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => {
        const colorMap: Record<string, string> = {
          running: 'processing',
          success: 'success',
          failure: 'error',
          pending: 'gold',
        };
        return <Tag color={colorMap[s] || 'default'}>{statusLabelMap[s] || s}</Tag>;
      },
    },
    {
      title: '任务数',
      key: 'taskCount',
      width: 80,
      render: (_: unknown, r: OrchestrationRun) => r.tasks?.length ?? 0,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
  ];

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: '15%' }}>
        <Spin size="large" tip="加载 Agent 数据中..." />
      </div>
    );
  }

  return (
    <div>
      {/* 标题栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          <RobotOutlined /> Agent 控制台
        </Title>
        <Space>
          <Tag color="blue">{agents.length} 个 Agent</Tag>
          <Tag color="green">{onlineCount} 在线</Tag>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="在线 Agent"
              value={onlineCount}
              suffix={`/ ${agents.length}`}
              valueStyle={{ color: '#1677ff' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="总任务数"
              value={tasks.length}
              valueStyle={{ color: '#52c41a' }}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="平均负载"
              value={avgLoad}
              suffix="%"
              valueStyle={{ color: '#fa8c16' }}
              prefix={<SyncOutlined spin={avgLoad > 60} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="编排运行"
              value={runs.length}
              valueStyle={{ color: '#722ed1' }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Agent 列表 + 饼图 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={16}>
          <Card
            title="Agent 列表"
            extra={
              <ReloadOutlined
                spin={refreshing}
                style={{ fontSize: 16, cursor: 'pointer' }}
                onClick={handleRefresh}
              />
            }
          >
            {agents.length === 0 ? (
              <Empty description="暂无 Agent 数据" />
            ) : (
              <Table<Agent>
                columns={agentColumns}
                dataSource={agents}
                rowKey="agent_key"
                pagination={false}
                size="middle"
                scroll={{ x: 800 }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title={<><PieChartOutlined /> 任务状态分布</>} style={{ height: '100%' }}>
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

      {/* 编排运行列表 */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title="最近的编排运行">
            {runs.length === 0 ? (
              <Empty description="暂无编排运行记录" />
            ) : (
              <Table<OrchestrationRun>
                columns={runColumns}
                dataSource={runs}
                rowKey="id"
                pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
                size="middle"
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
