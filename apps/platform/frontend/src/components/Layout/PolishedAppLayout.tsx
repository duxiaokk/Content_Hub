import { useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Dropdown, Layout, Menu, Space, Typography } from 'antd';
import {
  AppstoreOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  LogoutOutlined,
  ProfileOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAuthStore } from '../../stores/authStore';

const { Header, Content, Footer } = Layout;
const { Text } = Typography;

const navItems: NonNullable<MenuProps['items']> = [
  { key: '/', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/sources', icon: <DatabaseOutlined />, label: '信源管理' },
  {
    key: 'content-hub',
    icon: <AppstoreOutlined />,
    label: '内容中心',
    children: [
      { key: '/content-queue', icon: <ProfileOutlined />, label: '内容队列' },
      { key: '/posts', icon: <FileTextOutlined />, label: '文章管理' },
      { key: '/fetch-runs', icon: <FileSearchOutlined />, label: '采集监控' },
    ],
  },
  { key: '/review-queue', icon: <EditOutlined />, label: '审核队列' },
  { key: '/digests', icon: <FileTextOutlined />, label: '日报' },
  { key: '/agent', icon: <RobotOutlined />, label: '任务调度' },
];

export default function PolishedAppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, role, email, logout } = useAuthStore();

  const selectedKey = useMemo(() => {
    const path = location.pathname;
    const exactMatch = navItems.find((item) => item && 'key' in item && item.key === path);
    if (exactMatch && typeof exactMatch.key === 'string') {
      return exactMatch.key;
    }

    if (path.startsWith('/posts/')) return '/posts';
    if (path.startsWith('/fetch-runs')) return '/fetch-runs';
    if (path.startsWith('/content-queue')) return '/content-queue';
    if (path.startsWith('/review-queue')) return '/review-queue';
    if (path.startsWith('/digests')) return '/digests';
    return '/';
  }, [location.pathname]);

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'info',
      disabled: true,
      label: (
        <div style={{ padding: '4px 0' }}>
          <Text strong>{username || 'Unknown User'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {email || role || ''}
          </Text>
        </div>
      ),
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: () => {
        logout();
        navigate('/login', { replace: true });
      },
    },
  ];

  return (
    <Layout className="console-shell">
      <Header className="console-shell__header">
        <div className="console-shell__header-left">
          <div className="console-brand" onClick={() => navigate('/')}>
            <span className="console-brand__mark">Jk</span>
            <span className="console-brand__text">
              <span className="console-brand__title">Content Hub</span>
              <span className="console-brand__subtitle">Editorial Console</span>
            </span>
          </div>
          <Menu
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            className="console-shell__menu"
          />
        </div>

        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" arrow>
          <Space className="console-shell__user" style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#3b82f6' }} />
            <Text>{username || '用户'}</Text>
          </Space>
        </Dropdown>
      </Header>

      <Content className="console-shell__content">
        <Outlet />
      </Content>

      <Footer style={{ background: 'transparent', padding: 0 }}>
        <div className="console-shell__footer">Content Hub Console &copy; {new Date().getFullYear()}</div>
      </Footer>
    </Layout>
  );
}
