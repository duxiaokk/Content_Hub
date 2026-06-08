import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Form,
  Input,
  Button,
  Card,
  Typography,
  Divider,
  message,
  Space,
  Select,
} from 'antd';
import { SendOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { createPost } from '../../services/api';
import type { CreatePostRequest } from '../../types';

const { Title } = Typography;
const { TextArea } = Input;

const tagOptions = [
  { value: 'Python', label: 'Python' },
  { value: 'JavaScript', label: 'JavaScript' },
  { value: 'TypeScript', label: 'TypeScript' },
  { value: 'React', label: 'React' },
  { value: 'Vue', label: 'Vue' },
  { value: 'Node.js', label: 'Node.js' },
  { value: 'Java', label: 'Java' },
  { value: 'Go', label: 'Go' },
  { value: 'Rust', label: 'Rust' },
  { value: 'Docker', label: 'Docker' },
  { value: 'Kubernetes', label: 'Kubernetes' },
  { value: 'AI/ML', label: 'AI/ML' },
  { value: 'DevOps', label: 'DevOps' },
  { value: '数据库', label: '数据库' },
  { value: '前端', label: '前端' },
  { value: '后端', label: '后端' },
  { value: '架构', label: '架构' },
  { value: '面试', label: '面试' },
  { value: '开源', label: '开源' },
];

export default function PostCreatePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const onFinish = async (values: {
    title: string;
    content: string;
    tags: string[];
    status: 'draft' | 'published';
  }) => {
    setLoading(true);
    try {
      const data: CreatePostRequest = {
        title: values.title,
        content: values.content,
        tech_tags: values.tags && values.tags.length > 0 ? values.tags.join(',') : undefined,
        status: values.status || 'published',
      };
      await createPost(data);
      message.success('文章发布成功');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '发布失败，请稍后重试';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDraft = async () => {
    try {
      const values = await form.validateFields(['title', 'content']);
      setLoading(true);
      const data: CreatePostRequest = {
        title: values.title || '无标题草稿',
        content: values.content || '',
        tech_tags: undefined,
        status: 'draft',
      };
      await createPost(data);
      message.success('草稿已保存');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
      // validation error, ignore
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          返回
        </Button>
      </Space>

      <Card bodyStyle={{ padding: 32 }}>
        <Title level={3} style={{ marginBottom: 4 }}>
          写文章
        </Title>
        <Divider />

        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ status: 'published', tags: [] }}
        >
          <Form.Item
            name="title"
            label="文章标题"
            rules={[{ required: true, message: '请输入文章标题' }]}
          >
            <Input
              placeholder="输入文章标题..."
              maxLength={200}
              showCount
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="tags"
            label="标签"
          >
            <Select
              mode="tags"
              placeholder="选择或输入标签，如 Python、React"
              options={tagOptions}
              maxTagCount={8}
            />
          </Form.Item>

          <Form.Item
            name="content"
            label="文章内容（Markdown）"
            rules={[{ required: true, message: '请输入文章内容' }]}
            extra="支持 Markdown 语法：标题、代码块、列表、链接、图片等"
          >
            <TextArea
              rows={18}
              placeholder={`使用 Markdown 语法编写文章内容...

## 二级标题

这是正文内容，支持 **粗体** 和 *斜体*。

\`\`\`python
print("Hello, World!")
\`\`\`

- 列表项 1
- 列表项 2

> 引用文字

[链接文本](https://example.com)

![图片描述](https://example.com/image.png)
`}
              maxLength={100000}
              showCount
              style={{ fontFamily: 'Consolas, Monaco, "Courier New", monospace', fontSize: 14 }}
            />
          </Form.Item>

          <Form.Item name="status" label="发布状态">
            <Select
              options={[
                { value: 'published', label: '直接发布' },
                { value: 'draft', label: '保存为草稿' },
              ]}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space size={16}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                icon={<SendOutlined />}
                size="large"
              >
                发布文章
              </Button>
              <Button size="large" onClick={handleSaveDraft}>
                保存草稿
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* Markdown 预览提示 */}
      <Card
        size="small"
        style={{ marginTop: 16, background: '#f6ffed', border: '1px solid #b7eb8f' }}
      >
        <Typography.Text type="success">
          提示：内容区域支持完整的 Markdown 语法。你可以使用标题、代码块、表格、引用等格式来美化文章。
        </Typography.Text>
      </Card>
    </div>
  );
}
