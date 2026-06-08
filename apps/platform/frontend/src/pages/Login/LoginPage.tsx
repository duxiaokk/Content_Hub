import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons';
import { login as loginApi } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';

const { Title, Text } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const storeLogin = useAuthStore((s) => s.login);

  const onFinish = async (values: {
    username: string;
    password: string;
    remember: boolean;
  }) => {
    setLoading(true);
    try {
      const data = await loginApi(values);
      storeLogin(data.access_token, values.username, 'user');
      message.success('登录成功，欢迎回来！');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败，请检查用户名和密码';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      }}
    >
      <Card
        bordered={false}
        style={{
          width: 420,
          borderRadius: 12,
          boxShadow: '0 8px 40px rgba(0, 0, 0, 0.12)',
        }}
        bodyStyle={{ padding: '40px 32px' }}
      >
        <Space
          direction="vertical"
          size="large"
          style={{ width: '100%', textAlign: 'center' }}
        >
          <div>
            <RobotOutlined style={{ fontSize: 48, color: '#1677ff' }} />
            <Title level={2} style={{ marginTop: 12, marginBottom: 4 }}>
              Ado_Jk
            </Title>
            <Text type="secondary">Multi-Agent Content Orchestration Platform</Text>
          </div>

          <Form
            name="login"
            initialValues={{ remember: true }}
            onFinish={onFinish}
            size="large"
            layout="vertical"
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="用户名"
                autoFocus
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="密码"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登 录
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Text type="secondary">
                还没有账号？{' '}
                <Link to="/register" style={{ color: '#1677ff' }}>
                  立即注册
                </Link>
              </Text>
            </div>
          </Form>

          <Text type="secondary" style={{ fontSize: 12 }}>
            仅限授权用户访问 | Ado_Jk Platform v1.0
          </Text>
        </Space>
      </Card>
    </div>
  );
}
